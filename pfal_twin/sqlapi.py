"""Client for the PFAL SQL API (sis.ku.ac.th/pfal-api): one HTTP endpoint that runs SQL with a 24-h bearer token.

Credentials are read, in order, from the environment (PFAL_DB_USER / PFAL_DB_PASS -- GitHub Actions secrets) or from
`.streamlit/secrets.toml` / Streamlit Cloud secrets, section [pfal_db] with keys `user` and `pass`.
They are never printed, logged or put into error messages.

Token: one login per process. The token is shared by every SqlApi of the same account (the web app creates a client
on each sync) and is reused until it expires (`expires_in` from /login, minus a safety margin); only then -- or if
the server answers 401 to it -- does the client log in again.

    db = SqlApi.from_secrets()
    db.select("SELECT COUNT(*) n FROM iot_long")    # -> list of row dicts
    db.execute("INSERT ...")                        # writes: GitHub Actions only (read_only=False)
"""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

import requests

BASE_URL = "https://sis.ku.ac.th/pfal-api/public/index.php"
SECRETS = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"
_READ_ONLY_SQL = re.compile(r"^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN|WITH)\b", re.I)
EXPIRY_MARGIN_S = 60      # treat the token as expired this long before the server does

_tokens: dict[tuple[str, str], tuple[str, float]] = {}   # (base_url, user) -> (token, expires_at epoch s)
_tokens_lock = threading.Lock()


class SqlApiError(RuntimeError):
    """API/SQL failure. The message carries the HTTP status and the server's error text, never credentials."""


def load_credentials() -> tuple[str, str]:
    user, pw = os.environ.get("PFAL_DB_USER"), os.environ.get("PFAL_DB_PASS")
    if user and pw:
        return user, pw
    try:  # inside a Streamlit app (local secrets.toml or Streamlit Cloud secrets)
        import streamlit as st
        sec = st.secrets["pfal_db"]
        return sec["user"], sec["pass"]
    except Exception:
        pass
    if SECRETS.exists():
        import toml
        sec = toml.load(SECRETS).get("pfal_db", {})
        if sec.get("user") and sec.get("pass"):
            return sec["user"], sec["pass"]
    raise SqlApiError("no PFAL DB credentials: set PFAL_DB_USER/PFAL_DB_PASS or [pfal_db] in .streamlit/secrets.toml")


class SqlApi:
    def __init__(self, user: str, password: str, base_url: str = BASE_URL, read_only: bool = True, timeout: int = 60):
        self._user, self._pass = user, password
        self.base_url, self.read_only, self.timeout = base_url, read_only, timeout
        self.s = requests.Session()

    @classmethod
    def from_secrets(cls, **kw) -> "SqlApi":
        return cls(*load_credentials(), **kw)

    def __repr__(self):  # keep credentials out of tracebacks / st.write
        return f"SqlApi({self.base_url}, read_only={self.read_only}, token_valid={self.token_valid})"

    # -- auth
    @property
    def _key(self) -> tuple[str, str]:
        return self.base_url, self._user

    @property
    def token_valid(self) -> bool:
        """True if a token for this account is cached and has not reached its expiry time."""
        tok = _tokens.get(self._key)
        return tok is not None and time.time() < tok[1]

    def login(self) -> str:
        """Get a new token from /login and cache it for every client of this account."""
        r = self.s.post(f"{self.base_url}?route=login", json={"db_user": self._user, "db_pass": self._pass}, timeout=self.timeout)
        if not r.ok:
            raise SqlApiError(f"login failed: HTTP {r.status_code} {_err(r)}")
        js = r.json()
        token, expires_at = js["token"], time.time() + int(js.get("expires_in", 86400)) - EXPIRY_MARGIN_S
        _tokens[self._key] = (token, expires_at)
        return token

    def token(self) -> str:
        """The cached token if it has not expired yet; otherwise log in again."""
        with _tokens_lock:
            tok = _tokens.get(self._key)
            if tok is not None and time.time() < tok[1]:
                return tok[0]
            return self.login()

    def _renew_after_401(self, rejected: str) -> str:
        """The server refused `rejected` before its expiry time (revoked, server restart ...): log in again, unless
        another thread already replaced it."""
        with _tokens_lock:
            tok = _tokens.get(self._key)
            if tok is not None and tok[0] != rejected and time.time() < tok[1]:
                return tok[0]
            return self.login()

    def _post_query(self, sql: str, token: str):
        return self.s.post(f"{self.base_url}?route=query", json={"sql": sql}, timeout=self.timeout,
                           headers={"Authorization": f"Bearer {token}"})

    def run(self, sql: str) -> list:
        """Run one or more `;`-separated statements; returns the API's `results` list (one element per statement)."""
        if self.read_only and not _READ_ONLY_SQL.match(sql):
            raise SqlApiError("read-only client: only SELECT/SHOW/DESCRIBE/EXPLAIN are allowed")
        token = self.token()                       # 1) reuse the token unless it has expired
        r = self._post_query(sql, token)
        if r.status_code == 401:                   # 2) rejected anyway -> new token, one retry
            r = self._post_query(sql, self._renew_after_401(token))
        if not r.ok:
            raise SqlApiError(f"query failed: HTTP {r.status_code} {_err(r)}")
        return r.json()["results"]

    def select(self, sql: str) -> list[dict]:
        """Rows of the first (or only) statement."""
        res = self.run(sql)
        return res[0] if res and isinstance(res[0], list) else []

    def execute(self, sql: str) -> list:
        if self.read_only:
            raise SqlApiError("read-only client: create it with read_only=False to write")
        return self.run(sql)


def _err(r: requests.Response) -> str:
    try:
        return str(r.json().get("error", ""))[:300]
    except ValueError:
        return r.text[:300]
