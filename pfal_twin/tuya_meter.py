"""PFAL electricity meter (Tuya) read through the Tuya *device sharing* API - the one Home Assistant uses - with the
team's own app account (a member of the "PFAL" home), because the official cloud-project route only sees devices of the
home owner.

One-time login (scripts/tuya_login.py): the app account's User Code + a QR code scanned in the Tuya app -> a token
(access + refresh). The token is kept in the SIS PFAL database (store_meta, name='tuya_token') so every run - GitHub
Actions or a laptop - can use it and write back the refreshed one, and in .streamlit/tuya_token.json (git-ignored) as a
local copy for when the database is unreachable. It is never printed.

    meter = TuyaMeter.from_store()      # token from the database
    meter.status()                      # raw Tuya data points of the breaker
    meter.read()                        # {"power": 4118.0, "power_a": 1255.0, ..., "energy": 20.55, "temp": 38.0}

The meter is a 3-phase smart breaker (Tuya category dlq). Each phase_x data point is 8 bytes: voltage (2 bytes, 0.1 V),
current (3 bytes, mA), active power (3 bytes, W). total_forward_energy counts 0.01 kWh (checked against the measured
power: +16 counts in 2.6 min at 4.1 kW). Stored in the database as device "pm" (see docs/DATA_DICTIONARY.md).
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pandas as pd

from .sqlapi import SqlApi, load_credentials  # noqa: F401  (credentials for the database that holds the token)

# Home Assistant's public client of the Tuya device-sharing API (from its open-source Tuya integration): Tuya issues
# these clients to integrators only, so this is the one available. The app shows the link as "Home Assistant".
CLIENT_ID = "HA_3y9q4ak7g4ephrvke"
SCHEMA = "haauthorize"
QR_PREFIX = "tuyaSmart--qrLogin?token="
TOKEN_ROW = "tuya_token"
DEVICE = "pm"                     # device name of the meter in the database
TZ = "Asia/Bangkok"
ENERGY_PER_COUNT = 0.01           # kWh per count of total_forward_energy
LOCAL_TOKEN = Path(__file__).resolve().parents[1] / ".streamlit" / "tuya_token.json"


def tuya_settings() -> dict:
    """[tuya] from the environment (TUYA_USER_CODE, TUYA_DEVICE_ID) or .streamlit/secrets.toml / Streamlit secrets."""
    import os
    out = {"user_code": os.environ.get("TUYA_USER_CODE", ""), "device_id": os.environ.get("TUYA_DEVICE_ID", "")}
    if out["user_code"] and out["device_id"]:
        return out
    try:
        import streamlit as st
        sec = dict(st.secrets["tuya"])
    except Exception:
        from .sqlapi import SECRETS
        import toml
        sec = toml.load(SECRETS).get("tuya", {}) if SECRETS.exists() else {}
    return {k: out[k] or sec.get(k, "") for k in out}


def save_token(db: SqlApi | None, info: dict) -> bool:
    """Local copy always (when the folder exists, i.e. on a laptop); the database when reachable. True if the database took it."""
    if LOCAL_TOKEN.parent.exists():
        LOCAL_TOKEN.write_text(json.dumps(info))
        LOCAL_TOKEN.chmod(0o600)
    if db is None:
        return False
    js = json.dumps(info).replace("\\", "\\\\").replace("'", "''")
    try:
        db.execute(f"REPLACE INTO store_meta (name, value) VALUES ('{TOKEN_ROW}', '{js}')")
        return True
    except Exception:
        return False


def load_token(db: SqlApi | None) -> dict | None:
    """The newest of the database copy and the local copy (both carry the time `t` the token was issued)."""
    found = []
    if db is not None:
        try:
            rows = db.select(f"SELECT value FROM store_meta WHERE name = '{TOKEN_ROW}'")
            found += [json.loads(rows[0]["value"])] if rows else []
        except Exception:
            pass
    if LOCAL_TOKEN.exists():
        found.append(json.loads(LOCAL_TOKEN.read_text()))
    return max(found, key=lambda i: i.get("t", 0)) if found else None


class TuyaMeter:
    def __init__(self, info: dict, user_code: str, device_id: str, db: SqlApi | None = None):
        from tuya_sharing import Manager, SharingTokenListener

        outer = self

        class _Saver(SharingTokenListener):           # the SDK refreshes the access token itself; keep the new one
            def update_token(self, token_info: dict):
                outer.info.update(token_info)
                if outer.db is not None:
                    save_token(outer.db, outer.info)

        self.info, self.db, self.device_id = dict(info), db, device_id
        self.manager = Manager(CLIENT_ID, user_code, info["terminal_id"], info["endpoint"], info, _Saver())

    @classmethod
    def from_store(cls, db: SqlApi | None = None) -> "TuyaMeter":
        db = db or SqlApi.from_secrets(read_only=False)
        info = load_token(db)
        if not info:
            raise RuntimeError("no Tuya token in the database: run scripts/tuya_login.py once")
        s = tuya_settings()
        return cls(info, s["user_code"], s["device_id"], db)

    def devices(self) -> dict:
        self.manager.update_device_cache()
        return self.manager.device_map

    def status(self) -> dict:
        """Raw data points of the meter (code -> value) and when they were read."""
        dev = self.devices().get(self.device_id)
        if dev is None:
            raise RuntimeError(f"meter {self.device_id} not among the account's devices")
        return dict(dev.status, _online=dev.online, _read_at=time.time())

    def read(self) -> dict:
        """Decoded readings (W, V, A, kWh, degC) of the meter right now."""
        return decode(self.status())


def decode(st: dict) -> dict:
    """Raw data points of the 3-phase breaker -> metric -> value (the metric names used in the database)."""
    out = {}
    for ph in "abc":
        raw = st.get(f"phase_{ph}")
        if not raw:
            continue
        b = base64.b64decode(raw)
        out[f"voltage_{ph}"] = int.from_bytes(b[0:2], "big") / 10
        out[f"current_{ph}"] = int.from_bytes(b[2:5], "big") / 1000
        out[f"power_{ph}"] = float(int.from_bytes(b[5:8], "big"))
    if any(k.startswith("power_") for k in out):
        out["power"] = sum(v for k, v in out.items() if k.startswith("power_"))
    if st.get("total_forward_energy") is not None:
        out["energy"] = st["total_forward_energy"] * ENERGY_PER_COUNT
    for src, dst in (("temp_current", "temp"), ("leakage_current", "leakage"), ("fault", "fault")):
        if st.get(src) is not None:
            out[dst] = float(st[src])
    if "switch" in st:
        out["switch"] = 1.0 if st["switch"] else 0.0
    return out


def energy_counter_at(samples: pd.Series, t: pd.Timestamp) -> float:
    """Energy counter (kWh) at time t, interpolated between the readings around it (the counter only grows, so a
    straight line between two readings is a fair estimate); nan when there is no reading on both sides."""
    s = samples.dropna().sort_index()
    before, after = s[s.index <= t], s[s.index >= t]
    if before.empty or after.empty:
        return float("nan")
    t0, v0, t1, v1 = before.index[-1], before.iloc[-1], after.index[0], after.iloc[0]
    return v0 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)


def daily_energy(samples: pd.Series, now_kwh: float | None = None, now: pd.Timestamp | None = None) -> pd.Series:
    """kWh per day (Asia/Bangkok) from the energy counter readings (+ an optional live reading for today).
    A counter reset (value drops) starts a new count instead of giving a negative day."""
    s = samples.dropna().sort_index()
    if now_kwh is not None and now_kwh == now_kwh:
        live = pd.Series([now_kwh], index=pd.DatetimeIndex([now or pd.Timestamp.now(tz=TZ)]))
        s = pd.concat([s, live]).sort_index() if len(s) else live
    if len(s) < 2:
        return pd.Series(dtype=float)
    s = s.where(s.diff().fillna(0) >= 0)                                  # reading after a reset: drop it
    s = s.dropna()
    days = pd.date_range(s.index[0].normalize(), s.index[-1].normalize() + pd.Timedelta("1D"), freq="D", tz=TZ)
    at = pd.Series([energy_counter_at(s, d) for d in days], index=days)
    at.iloc[-1] = at.iloc[-1] if at.iloc[-1] == at.iloc[-1] else s.iloc[-1]   # today: up to the last reading
    first = at.first_valid_index()
    if first is not None and first > days[0]:                             # first day: from the first reading
        at[days[0]] = s.iloc[0]
    out = at.diff().shift(-1).dropna()
    return out[out >= 0]

