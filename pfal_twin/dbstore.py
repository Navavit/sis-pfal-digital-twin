"""The IoT store in the SIS PFAL SQL database (MariaDB `pfal`, reached through the PFAL SQL API -- see sqlapi.py).

Tables (times are Asia/Bangkok local time):

    iot_long    raw samples as the devices sent them      ts DATETIME(3), device, metric, value   PK (device, metric, ts)
    iot_10min   10-min table used by the twin             ts DATETIME PK + one DOUBLE column per variable
                (column `gc1_ec` = variable `gc1.ec`: the device prefix is joined with "_" instead of ".")
    store_meta  name -> value; name='manifest' holds the store manifest JSON (updated_at, span, bins, ...)

GitHub Actions writes (publish(), incremental: the last `overlap` of data is re-sent, INSERT IGNORE / REPLACE);
the web app reads (pull_wide(), incremental from its local copy).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .sqlapi import SqlApi, SqlApiError

TZ = "Asia/Bangkok"
LONG_T, WIDE_T, META_T = "iot_long", "iot_10min", "store_meta"
MAX_SQL_BYTES = 2_000_000   # per request; the API took 1.8 MB inserts in 0.3 s (max_allowed_packet is 16 MB)

DDL = [
    f"""CREATE TABLE IF NOT EXISTS {LONG_T} (
        ts DATETIME(3) NOT NULL COMMENT 'Asia/Bangkok local time',
        device VARCHAR(8) NOT NULL COMMENT 'gw / gc1 / gc2 / co2 -- see docs/DATA_DICTIONARY.md',
        metric VARCHAR(40) NOT NULL COMMENT 'ThingsBoard telemetry key',
        value DOUBLE NULL,
        PRIMARY KEY (device, metric, ts), KEY ix_ts (ts)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='raw ThingsBoard samples'""",
    f"""CREATE TABLE IF NOT EXISTS {WIDE_T} (
        ts DATETIME NOT NULL COMMENT 'start of the 10-min bin, Asia/Bangkok local time',
        PRIMARY KEY (ts)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='10-min table: one column per variable, device_metric'""",
    f"""CREATE TABLE IF NOT EXISTS {META_T} (
        name VARCHAR(40) NOT NULL PRIMARY KEY,
        value TEXT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8""",
]


def create_tables(db: SqlApi):
    for sql in DDL:
        db.execute(sql)


# --------------------------------------------------------------------------- helpers

def db_col(var: str) -> str:
    """'gc1.ec' -> 'gc1_ec' (device names have no underscore, so this is reversible)."""
    return var.replace(".", "_", 1)


def app_col(col: str) -> str:
    return col.replace("_", ".", 1)


def _ts_sql(idx: pd.Series | pd.DatetimeIndex, ms: bool) -> list[str]:
    t = pd.DatetimeIndex(idx)
    t = t.tz_convert(TZ).tz_localize(None) if t.tz is not None else t
    return list(t.strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3] if ms else t.strftime("%Y-%m-%d %H:%M:%S"))


def _num(v) -> str:
    return "NULL" if v is None or (isinstance(v, float) and not np.isfinite(v)) else repr(float(v))


def _send_chunked(db: SqlApi, head: str, rows: list[str], tail: str = "") -> int:
    """INSERT head + rows, split so each request stays under MAX_SQL_BYTES. Returns affected rows."""
    n, buf, size = 0, [], len(head)
    for r in rows + [None]:
        if r is None or (buf and size + len(r) + 1 > MAX_SQL_BYTES):
            if buf:
                n += db.execute(head + ",".join(buf) + tail)[0].get("affected_rows", 0)
            buf, size = [], len(head)
        if r is not None:
            buf.append(r); size += len(r) + 1
    return n


def max_ts(db: SqlApi, table: str) -> pd.Timestamp | None:
    v = db.select(f"SELECT MAX(ts) AS t FROM {table}")[0]["t"]
    return pd.Timestamp(v).tz_localize(TZ) if v else None


def wide_columns(db: SqlApi) -> list[str]:
    return [r["Field"] for r in db.select(f"SHOW COLUMNS FROM {WIDE_T}") if r["Field"] != "ts"]


# --------------------------------------------------------------------------- write (GitHub Actions)

def push_long(db: SqlApi, long: pd.DataFrame, since=None) -> int:
    if since is not None:
        long = long[long["ts"] >= since]
    rows = [f"('{t}','{d}','{k}',{_num(v)})" for t, d, k, v in
            zip(_ts_sql(long["ts"], ms=True), long["device"], long["key"], long["value"].to_numpy())]
    return _send_chunked(db, f"INSERT IGNORE INTO {LONG_T} (ts, device, metric, value) VALUES ", rows)


def push_wide(db: SqlApi, wide: pd.DataFrame, since=None) -> int:
    """REPLACE the bins from `since` on (recent bins change as late samples arrive); adds columns for new variables."""
    if since is not None:
        wide = wide.loc[wide.index >= since]
    have = set(wide_columns(db))
    new = [c for c in wide.columns if db_col(c) not in have]
    if new:
        db.execute(f"ALTER TABLE {WIDE_T} " + ", ".join(f"ADD COLUMN `{db_col(c)}` DOUBLE NULL" for c in new))
    cols = ", ".join(["ts"] + [f"`{db_col(c)}`" for c in wide.columns])
    vals = wide.to_numpy(dtype=float)
    rows = [f"('{t}'," + ",".join(_num(v) for v in row) + ")" for t, row in zip(_ts_sql(wide.index, ms=False), vals)]
    return _send_chunked(db, f"REPLACE INTO {WIDE_T} ({cols}) VALUES ", rows)


def push_manifest(db: SqlApi, manifest: dict):
    js = json.dumps(manifest).replace("\\", "\\\\").replace("'", "''")
    db.execute(f"REPLACE INTO {META_T} (name, value) VALUES ('manifest', '{js}')")


def publish(db: SqlApi, long: pd.DataFrame, wide: pd.DataFrame, manifest: dict, overlap: str = "3D", full: bool = False) -> dict:
    """Send what is new since the database's last timestamp (minus `overlap`), then the manifest (last, so readers
    only see a new version once its data is in)."""
    create_tables(db)
    out = {}
    for name, table, push, df in [("long", LONG_T, push_long, long), ("wide", WIDE_T, push_wide, wide)]:
        last = None if full else max_ts(db, table)
        since = None if last is None else last - pd.Timedelta(overlap)
        out[name] = dict(since=str(since) if since is not None else "all", affected=push(db, df, since))
    push_manifest(db, manifest)
    return out


# --------------------------------------------------------------------------- read (web app)

def remote_manifest(db: SqlApi) -> dict | None:
    rows = db.select(f"SELECT value FROM {META_T} WHERE name = 'manifest'")
    return json.loads(rows[0]["value"]) if rows else None


def pull_wide(db: SqlApi, since=None, page_rows: int = 5000) -> pd.DataFrame:
    """10-min table from `since` on (all if None), paged by time so each response stays small."""
    cols = wide_columns(db)
    sel = ", ".join(["ts"] + [f"`{c}`" for c in cols])
    lo = "1970-01-01 00:00:00" if since is None else _ts_sql(pd.DatetimeIndex([since]), ms=False)[0]
    frames, op = [], ">="
    while True:
        rows = db.select(f"SELECT {sel} FROM {WIDE_T} WHERE ts {op} '{lo}' ORDER BY ts LIMIT {page_rows}")
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        lo, op = rows[-1]["ts"], ">"
        if len(rows) < page_rows:
            break
    if not frames:
        return pd.DataFrame(columns=[app_col(c) for c in cols], index=pd.DatetimeIndex([], tz=TZ, name="ts"), dtype=float)
    df = pd.concat(frames, ignore_index=True)
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("ts"))).tz_localize(TZ)
    df.index.name = None
    df = df.apply(pd.to_numeric, errors="coerce").astype(float)  # the API returns numbers as strings
    df.columns = [app_col(c) for c in df.columns]
    return df


def pull_long(db: SqlApi, since=None, window: str = "2D") -> pd.DataFrame:
    """Raw samples (ts, device, key, value) from `since` on, fetched in time windows (~10k rows each; halved on HTTP 500)."""
    lo = pd.Timestamp(db.select(f"SELECT MIN(ts) AS t FROM {LONG_T}")[0]["t"] or "2100-01-01") if since is None else \
        pd.Timestamp(since).tz_convert(TZ).tz_localize(None)
    hi = pd.Timestamp.now(tz=TZ).tz_localize(None) + pd.Timedelta("1D")
    frames, step = [], pd.Timedelta(window)
    while lo < hi:
        nxt = lo + step
        a, b = _ts_sql(pd.DatetimeIndex([lo, nxt]), ms=True)
        try:
            rows = db.select(f"SELECT ts, device, metric, value FROM {LONG_T} WHERE ts >= '{a}' AND ts < '{b}' ORDER BY ts, device, metric")
        except SqlApiError as e:  # HTTP 500 = response too big for the API server: halve the window and retry
            if "HTTP 500" in str(e) and step > pd.Timedelta("1h"):
                step /= 2
                continue
            raise
        if rows:
            frames.append(pd.DataFrame(rows))
        lo = nxt
    if not frames:
        return pd.DataFrame({"ts": pd.DatetimeIndex([], tz=TZ), "device": [], "key": [], "value": []})
    df = pd.concat(frames, ignore_index=True).rename(columns={"metric": "key"})
    df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize(TZ)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df
