"""ThingsBoard REST client for the Civic Agrotech "Vertical Smart Farming" dashboard
(cat-smartgrow.com) + storage / QC helpers for the PFAL twin.

Data model
----------
long  : one row per sample  -> columns  ts (tz-aware, Asia/Bangkok), device (alias), key, value (float)
wide  : one column per "alias.key", regular time index (default 10 min means)

Devices visible to the public dashboard user (GrowController3-5 return 403).
The public token is enough for reading; if the dashboard is ever made private,
pass a ThingsBoard username/password to `Client.login_user` instead.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import IOT_RAW, PROCESSED

BASE_URL = "https://cat-smartgrow.com"
PUBLIC_ID = "b9506720-6f7f-11f1-ba97-e955dcdab604"       # public dashboard user
DASHBOARD_ID = "c55eb730-6f7d-11f1-ba97-e955dcdab604"    # "Vertical Smart Farming"
TZ = "Asia/Bangkok"

# alias -> ThingsBoard device
DEVICES = {
    "gw":  dict(id="0f6e9810-6f7c-11f1-ba97-e955dcdab604", name="DOAIoTGateway",
                role="IoT gateway: 5x XY-MD02 T/RH (Modbus addr 20-24, one per tier) + water level"),
    "gc1": dict(id="0c57be70-ea22-11f0-b1a2-73df645d4b4b", name="GrowControllerPlus_30c922faf128",
                role="Grow Controller at the rack END - GROWING-STAGE loop: 200 L tank, tiers 2-5 (confirmed on site 2026-09-14)"),
    "gc2": dict(id="580b20b0-ea21-11f0-b1a2-73df645d4b4b", name="GrowControllerPlus_30c922fa7390",
                role="Grow Controller at the rack SIDE - NURSERY-2 dosing set: 100 L tank under tier 1, far end (nursery 1 has no controller)"),
    "co2": dict(id="ffc4b1f0-d733-11f0-a4c7-9fcb6bb5dc6d", name="co2AndEnvironmentMeter_30c922faf2ec",
                role="CO2 & environment controller"),
}

# keys worth storing (None = every key the device exposes). Firmware / calibration /
# heap keys of the grow controllers are skipped.
GC_KEYS = ["ec", "ph", "waterTemperature", "ambTemperature", "ambHumidity",
           "led", "currentStageBrightness1", "currentStageBrightness2", "currentStageBrightness3", "currentStageBrightness4",
           "pumpA", "pumpB", "pumpPH", "pwmWater", "mode", "stage", "plantDay",
           "ecSetPoint", "pHSetPoint", "alarmEC", "ecDosingCount", "pHDosingCount",
           # extended (not on the public dashboard, added 2026-09-14): dosing configuration, pump modes, controller health
           "task", "aDosingTime", "bDosingTime", "pHDosingTime", "ecWaiting", "pHWaiting",
           "pumpASpeed", "pumpBSpeed", "pumpPHSpeed", "modePumpA", "modePumpB", "modePumpPH", "modePumpWater", "pumpTypeEnable",
           "ecStamp", "pHStamp", "upTime"]
EXTENDED_KEYS = GC_KEYS[22:]
KEYS = {
    "gw":  None,
    "gc1": GC_KEYS,
    "gc2": GC_KEYS + ["rssiWiFi"],
    "co2": ["CO2", "temperature", "humidity", "VPD", "VOC", "pressure", "Relay_co2"],
}

# environment variables (state of the room) vs. control variables (inputs / actuator state)
ENV_KEYS = {"xy_md_20_t", "xy_md_21_t", "xy_md_22_t", "xy_md_23_t", "xy_md_24_t",
            "xy_md_20_h", "xy_md_21_h", "xy_md_22_h", "xy_md_23_h", "xy_md_24_h",
            "waterLevel_1", "ec", "ph", "CO2", "temperature", "humidity", "VPD", "VOC", "pressure"}
CONTROL_KEYS = {"led", "pumpA", "pumpB", "pumpPH", "pwmWater", "Relay_co2", "mode", "stage",
                "currentStageBrightness1", "currentStageBrightness2", "currentStageBrightness3", "currentStageBrightness4",
                "ecSetPoint", "pHSetPoint", "plantDay", "alarmEC", "ecDosingCount", "pHDosingCount",
                "task", "aDosingTime", "bDosingTime", "pHDosingTime", "ecWaiting", "pHWaiting",
                "pumpASpeed", "pumpBSpeed", "pumpPHSpeed", "modePumpA", "modePumpB", "modePumpPH", "modePumpWater", "pumpTypeEnable",
                "ecStamp", "pHStamp", "upTime"}
# human labels for the extended keys (web app / notebooks)
KEY_LABELS = {
    "task": "controller task", "stage": "growth stage", "mode": "controller mode", "plantDay": "plant day",
    "aDosingTime": "part-A dose (s per shot)", "bDosingTime": "part-B dose (s per shot)", "pHDosingTime": "acid dose (s per shot)",
    "ecWaiting": "wait between EC doses (s)", "pHWaiting": "wait between pH doses (s)",
    "pumpASpeed": "pump A speed (%)", "pumpBSpeed": "pump B speed (%)", "pumpPHSpeed": "pump pH speed (%)",
    "modePumpA": "pump A mode", "modePumpB": "pump B mode", "modePumpPH": "pump pH mode", "modePumpWater": "circulation pump mode",
    "pumpTypeEnable": "pump type enable", "ecStamp": "EC at last dose", "pHStamp": "pH at last dose", "upTime": "controller uptime",
    "ecDosingCount": "EC doses (count)", "pHDosingCount": "pH doses (count)", "pwmWater": "circulation pump", "led": "LED",
    "waterTemperature": "water temperature (probe)", "ambTemperature": "controller ambient T", "ambHumidity": "controller ambient RH",
    "Relay_co2": "CO₂ valve relay", "waterLevel_1": "water level sensor",
}
PUMP_MODE = {0: "off", 1: "manual", 2: "auto"}

# which controller drives which nutrient loop (site-confirmed 2026-09-14; the dashboard block titles are misleading)
LOOPS = {"growing": "gc1", "nursery2": "gc2", "nursery1": None}
LOOP_LABEL = {"gc1": "growing stage (tiers 2-5, 200 L)", "gc2": "nursery 2 (T1-N2, 100 L)", "n1": "nursery 1 (T1-N1, no controller)"}

# Exactly what the public ThingsBoard dashboard "Vertical Smart Farming" displays (widget datasources, checked 2026-09-14).
# The public web app must not show more than this; everything else stays in the local notebooks.
DASHBOARD_COLUMNS = (
    [f"gw.xy_md_{a}_{v}" for a in (20, 21, 22, 23, 24) for v in ("t", "h")]
    + ["co2.CO2", "co2.VPD", "co2.VOC"]
    + [f"{d}.{k}" for d in ("gc1", "gc2") for k in ("ec", "ph", "ecSetPoint", "pHSetPoint", "task", "pumpA", "pumpB", "pumpPH")]
)


def public_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only the columns the public dashboard shows."""
    return df[[c for c in DASHBOARD_COLUMNS if c in df.columns]]


LONG_PARQUET = IOT_RAW / "thingsboard_long.parquet"
WIDE_PARQUET = PROCESSED / "iot_10min.parquet"


# --------------------------------------------------------------------------- client

class Client:
    def __init__(self, base_url: str = BASE_URL, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()
        self._token = None

    # -- auth
    def login_public(self, public_id: str = PUBLIC_ID) -> "Client":
        r = self.s.post(f"{self.base_url}/api/auth/login/public", json={"publicId": public_id}, timeout=self.timeout)
        r.raise_for_status()
        self._set_token(r.json()["token"])
        return self

    def login_user(self, username: str, password: str) -> "Client":
        r = self.s.post(f"{self.base_url}/api/auth/login", json={"username": username, "password": password}, timeout=self.timeout)
        r.raise_for_status()
        self._set_token(r.json()["token"])
        return self

    def _set_token(self, token: str):
        self._token = token
        self.s.headers["X-Authorization"] = f"Bearer {token}"

    @property
    def authenticated(self) -> bool:
        return self._token is not None

    def _get(self, path: str, **params):
        r = self.s.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # -- metadata
    def dashboard(self, dashboard_id: str = DASHBOARD_ID) -> dict:
        return self._get(f"/api/dashboard/{dashboard_id}")

    def keys(self, device_id: str) -> list[str]:
        return self._get(f"/api/plugins/telemetry/DEVICE/{device_id}/keys/timeseries")

    def latest(self, device_id: str, keys: list[str] | None = None) -> pd.DataFrame:
        params = {"keys": ",".join(keys)} if keys else {}
        js = self._get(f"/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries", **params)
        return _json_to_long(js)

    # -- history
    def timeseries(self, device_id: str, keys: list[str], start, end,
                   interval_ms: int | None = None, agg: str = "NONE", limit: int = 50000) -> pd.DataFrame:
        """Raw (agg=NONE) or aggregated (agg=AVG/MIN/MAX + interval_ms) history as a long frame."""
        params = dict(keys=",".join(keys), startTs=_ms(start), endTs=_ms(end), limit=limit, agg=agg, orderBy="ASC")
        if agg != "NONE":
            params["interval"] = int(interval_ms)
        js = self._get(f"/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries", **params)
        return _json_to_long(js)

    def earliest_ts(self, device_id: str, key: str, search_from="2024-01-01") -> pd.Timestamp | None:
        js = self._get(f"/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries",
                       keys=key, startTs=_ms(search_from), endTs=_ms(datetime.now(timezone.utc)), limit=1, agg="NONE", orderBy="ASC")
        pts = js.get(key, [])
        return pd.Timestamp(pts[0]["ts"], unit="ms", tz="UTC").tz_convert(TZ) if pts else None


# --------------------------------------------------------------------------- fetch / store

def fetch_history(client: Client, start, end=None, devices: dict = DEVICES, keys: dict = KEYS,
                  chunk_days: int = 7, pause_s: float = 0.2, verbose: bool = True) -> pd.DataFrame:
    """Download raw telemetry for all devices in `chunk_days` windows -> long frame."""
    end = pd.Timestamp.now(tz=TZ) if end is None else pd.Timestamp(end)
    start = pd.Timestamp(start)
    if start.tzinfo is None:
        start = start.tz_localize(TZ)
    if end.tzinfo is None:
        end = end.tz_localize(TZ)
    frames = []
    for alias, dev in devices.items():
        ks = keys.get(alias) or client.keys(dev["id"])
        if not ks:
            continue
        t0 = start
        n = 0
        while t0 < end:
            t1 = min(t0 + timedelta(days=chunk_days), end)
            try:
                df = client.timeseries(dev["id"], ks, t0, t1)
            except requests.HTTPError as e:
                if verbose:
                    print(f"  {alias}: {t0.date()}–{t1.date()} -> HTTP {e.response.status_code}, skipped")
                df = pd.DataFrame()
            if len(df):
                df["device"] = alias
                frames.append(df)
                n += len(df)
            t0 = t1
            time.sleep(pause_s)
        if verbose:
            print(f"{alias:4s} {dev['name']:40s} {n:8,d} samples, {len(ks)} keys")
    if not frames:
        return pd.DataFrame(columns=["ts", "device", "key", "value"])
    out = pd.concat(frames, ignore_index=True)[["ts", "device", "key", "value"]]
    return out.drop_duplicates(["ts", "device", "key"]).sort_values(["device", "key", "ts"]).reset_index(drop=True)


def update_store(client: Client, path: Path = LONG_PARQUET, backfill_from="2025-11-01", overlap_days: int = 1, **kw) -> pd.DataFrame:
    """Incremental download: append everything newer than what is already in `path`."""
    old = load_long(path) if path.exists() else None
    start = backfill_from if old is None or old.empty else old["ts"].max() - timedelta(days=overlap_days)
    new = fetch_history(client, start, **kw)
    allf = new if old is None else pd.concat([old, new], ignore_index=True)
    allf = allf.drop_duplicates(["ts", "device", "key"]).sort_values(["device", "key", "ts"]).reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    allf.to_parquet(path, index=False)
    return allf


def backfill_keys(client: Client, keys_by_device: dict, path: Path = LONG_PARQUET, start="2025-12-20", verbose=True) -> pd.DataFrame:
    """Download the full history of keys that were added to KEYS later, and merge them into the store."""
    old = load_long(path) if path.exists() else None
    devs = {a: DEVICES[a] for a in keys_by_device}
    new = fetch_history(client, start, devices=devs, keys=keys_by_device, verbose=verbose)
    allf = new if old is None else pd.concat([old, new], ignore_index=True)
    allf = allf.drop_duplicates(["ts", "device", "key"]).sort_values(["device", "key", "ts"]).reset_index(drop=True)
    allf.to_parquet(path, index=False)
    return allf


def load_long(path: Path = LONG_PARQUET) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(TZ)
    return df


# --------------------------------------------------------------------------- reshape / QC

def to_wide(long_df: pd.DataFrame, freq: str = "10min", how: str = "mean") -> pd.DataFrame:
    """long -> wide 'alias.key' columns on a regular grid (mean within each bin; NaN where no sample)."""
    d = long_df.copy()
    d["col"] = d["device"] + "." + d["key"]
    d["bin"] = d["ts"].dt.floor(freq)
    is_ctrl = d["key"].isin(CONTROL_KEYS)      # state/setpoint keys: keep the last value in the bin, not the mean
    w = pd.concat([d[~is_ctrl].pivot_table(index="bin", columns="col", values="value", aggfunc=how),
                   d[is_ctrl].pivot_table(index="bin", columns="col", values="value", aggfunc="last")], axis=1)
    w.index.name = "time"
    full = pd.date_range(w.index.min(), w.index.max(), freq=freq, tz=TZ)
    return w.reindex(full)


# physically plausible ranges per key (outside -> NaN)
QC_RANGES = {
    "_t": (5, 50), "temperature": (5, 50),
    "_h": (5, 100), "humidity": (5, 100), "ambHumidity": (5, 100), "ambTemperature": (5, 60),
    "CO2": (300, 5000), "VPD": (0, 6), "VOC": (0, 1000), "pressure": (95, 106),
    "ec": (0.1, 6), "ph": (3, 10),
}
# columns that are known to be meaningless in this installation
QC_DROP = ["gc1.waterTemperature", "gc2.waterTemperature"]     # probe reads 42-54 °C -> not connected


def clean_wide(w: pd.DataFrame, drop=QC_DROP, ranges=QC_RANGES) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply plausibility ranges and drop known-bad channels. Returns (clean, qc_report)."""
    w = w.drop(columns=[c for c in drop if c in w.columns])
    rows = []
    for c in w.columns:
        key = c.split(".", 1)[1]
        rng = None
        for pat, r in ranges.items():
            if key == pat or (pat.startswith("_") and key.endswith(pat)):
                rng = r
        n = w[c].notna().sum()
        if rng is None or n == 0:
            rows.append(dict(column=c, n=n, range=None, removed=0))
            continue
        bad = w[c].notna() & ((w[c] < rng[0]) | (w[c] > rng[1]))
        rows.append(dict(column=c, n=n, range=f"{rng[0]}–{rng[1]}", removed=int(bad.sum())))
        w.loc[bad, c] = np.nan
    return w, pd.DataFrame(rows).set_index("column")


def availability(w: pd.DataFrame, freq: str = "1D") -> pd.DataFrame:
    """Fraction of bins with data per device per period (0..1)."""
    dev = w.columns.str.split(".").str[0]
    has = w.notna().T.groupby(dev).any().T
    return has.resample(freq).mean()


def vpd_kpa(t_c, rh_pct):
    """Vapour-pressure deficit (kPa) from air temperature (°C) and RH (%), Tetens."""
    es = 0.6108 * np.exp(17.27 * t_c / (t_c + 237.3))
    return es * (1 - rh_pct / 100.0)


# --------------------------------------------------------------------------- helpers

def _ms(t) -> int:
    t = pd.Timestamp(t)
    if t.tzinfo is None:
        t = t.tz_localize(TZ)
    return int(t.timestamp() * 1000)


def _to_float(v):
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower()
    if s in ("true", "on", "1"):
        return 1.0
    if s in ("false", "off", "0"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return np.nan


def _json_to_long(js: dict) -> pd.DataFrame:
    rows = [(pt["ts"], k, _to_float(pt["value"])) for k, pts in js.items() for pt in pts]
    if not rows:
        return pd.DataFrame(columns=["ts", "key", "value"])
    df = pd.DataFrame(rows, columns=["ts", "key", "value"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_convert(TZ)
    return df.dropna(subset=["value"])


def sample_csv_to_long(path: Path = IOT_RAW / "sample_thingsboard_7d_hourly.csv") -> pd.DataFrame:
    """Fallback when offline: the 7-day hourly CSV exported earlier -> long frame."""
    w = pd.read_csv(path, index_col=0, parse_dates=True)
    w.index = pd.to_datetime(w.index, utc=True).tz_convert(TZ)
    long = w.stack().reset_index()
    long.columns = ["ts", "col", "value"]
    long[["device", "key"]] = long["col"].str.split(".", n=1, expand=True)
    return long[["ts", "device", "key", "value"]]


def split_env_control(w: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Wide frame -> (environment columns, control/state columns)."""
    keys = w.columns.str.split(".", n=1).str[1]
    is_ctrl = keys.isin(CONTROL_KEYS)
    return w.loc[:, ~is_ctrl], w.loc[:, is_ctrl]


def state_ffill(ctrl: pd.DataFrame, limit_bins: int = 6 * 24 * 7) -> pd.DataFrame:
    """Control/state keys are only published when they change -> hold the last value
    forward (at most `limit_bins` bins, default 7 days at 10 min)."""
    return ctrl.ffill(limit=limit_bins)


# XY-MD02 channels -> physical units. Labels come from the ThingsBoard dashboard widget config (2026-09-14):
# 20 = "Inside", 24 = "Outside", 21/22/23 = "Grower Room 1/2/3". Units W1-W6 are in layout.SENSORS; the order
# 1/2/3 along the wall (door -> far end) is assumed.
CHANNELS = {
    "xy_md_21": dict(unit="XY-MD02 W1 (by CO2 display)",                 short="Grower room 1 (wall, X 1.25 m)", zone="room"),
    "xy_md_22": dict(unit="XY-MD02 W2 (under AC 1)",                     short="Grower room 2 (wall, X 3.6 m)",  zone="room"),
    "xy_md_23": dict(unit="XY-MD02 W3 (by conduit, above the nursery-2 tank)", short="Grower room 3 (wall, X 5.65 m)", zone="room"),
    "xy_md_20": dict(unit="XY-MD02 W4 (ANTEROOM, above the door)",       short="Inside = anteroom (above the door)", zone="anteroom"),
    "xy_md_24": dict(unit="XY-MD02 W6 (OUTSIDE, on CO2 box)",            short="Outside (on the CO2 box)",        zone="outside"),
}
ROOM_CHANNELS = ["xy_md_21", "xy_md_22", "xy_md_23"]
CHANNEL_ORDER = ["xy_md_21", "xy_md_22", "xy_md_23", "xy_md_20", "xy_md_24"]
# legacy (pre-2026-09-14) hypothesis, kept only so old code paths do not break
TIER_SENSOR = {1: "xy_md_20", 2: "xy_md_21", 3: "xy_md_22", 4: "xy_md_23", 5: "xy_md_24"}
OUTDOOR_CANDIDATE = {"xy_md_24"}


def tier_frame(w: pd.DataFrame, var: str = "t") -> pd.DataFrame:
    """LEGACY: columns tier 1..5 under the old one-channel-per-tier hypothesis. Use channel_frame() instead."""
    cols = {f"gw.{s}_{var}": t for t, s in TIER_SENSOR.items()}
    return w[[c for c in cols if c in w.columns]].rename(columns=cols).sort_index(axis=1)


def channel_frame(w: pd.DataFrame, var: str = "t", channels=None) -> pd.DataFrame:
    """Columns = XY-MD02 channel ids (xy_md_21, ...) of temperature ('t') or humidity ('h')."""
    chs = channels or CHANNEL_ORDER
    cols = {f"gw.{c}_{var}": c for c in chs if f"gw.{c}_{var}" in w.columns}
    return w[list(cols)].rename(columns=cols)


def channel_label(c: str) -> str:
    return f"{c} — {CHANNELS[c]['short']}" if c in CHANNELS else c
