"""Client for the PFAL SQL API (sis.ku.ac.th/pfal-api): one HTTP endpoint that runs SQL with a 24-h bearer token.

Credentials are read, in order, from the environment (PFAL_DB_USER / PFAL_DB_PASS -- GitHub Actions secrets) or from
`.streamlit/secrets.toml` / Streamlit Cloud secrets, section [pfal_db] with keys `user` and `pass`.
They are never printed, logged or put into error messages.

    db = SqlApi.from_secrets()
    db.select("SELECT COUNT(*) n FROM iot_long")    # -> list of row dicts
    db.execute("INSERT ...")                        # writes: GitHub Actions only (read_only=False)
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

import requests

BASE_URL = "https://sis.ku.ac.th/pfal-api/public/index.php"
SECRETS = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"
_READ_ONLY_SQL = re.compile(r"^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN|WITH)\b", re.I)


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
        self._token, self._expires_at = None, 0.0
        self.s = requests.Session()

    @classmethod
    def from_secrets(cls, **kw) -> "SqlApi":
        return cls(*load_credentials(), **kw)

    def __repr__(self):  # keep credentials out of tracebacks / st.write
        return f"SqlApi({self.base_url}, read_only={self.read_only}, logged_in={self._token is not None})"

    # -- auth
    def login(self):
        r = self.s.post(f"{self.base_url}?route=login", json={"db_user": self._user, "db_pass": self._pass}, timeout=self.timeout)
        if not r.ok:
            raise SqlApiError(f"login failed: HTTP {r.status_code} {_err(r)}")
        js = r.json()
        self._token, self._expires_at = js["token"], time.time() + js.get("expires_in", 86400) - 60

    def _post_query(self, sql: str):
        return self.s.post(f"{self.base_url}?route=query", json={"sql": sql}, timeout=self.timeout,
                           headers={"Authorization": f"Bearer {self._token}"})

    def run(self, sql: str) -> list:
        """Run one or more `;`-separated statements; returns the API's `results` list (one element per statement)."""
        if self.read_only and not _READ_ONLY_SQL.match(sql):
            raise SqlApiError("read-only client: only SELECT/SHOW/DESCRIBE/EXPLAIN are allowed")
        if self._token is None or time.time() >= self._expires_at:
            self.login()
        r = self._post_query(sql)
        if r.status_code == 401:  # token expired early or was revoked
            self.login()
            r = self._post_query(sql)
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
