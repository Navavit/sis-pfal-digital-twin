"""The IoT store in the SIS PFAL SQL database (MariaDB `pfal`, reached through the PFAL SQL API -- see sqlapi.py).

Tables (times are Asia/Bangkok local time):

    iot_long    raw samples as the devices sent them      ts DATETIME(3), device, metric, value   PK (device, metric, ts)
    iot_10min   10-min table used by the twin             ts DATETIME PK + one DOUBLE column per variable
                (column `gc1_ec` = variable `gc1.ec`: the device prefix is joined with "_" instead of ".")
    store_meta  name -> value; name='manifest' holds the store manifest JSON (updated_at, span, bins, ...)

GitHub Actions writes (publish(), incremental: the last `overlap` of data is re-sent, INSERT IGNORE / REPLACE);
the web app reads (pull_wide(), incremental from its local copy).

Requests: the API runs several `;`-separated statements in one request, so a publish is 1 login + 2 queries (read the
database state, then all writes; more only if the writes exceed MAX_SQL_BYTES), and a web-app check is 1 query
(+1 per 5000 rows when the store changed).
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
    db.execute(";\n".join(DDL))


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


def _chunks(head: str, rows: list[str]) -> list[str]:
    """INSERT head + rows as statements of at most MAX_SQL_BYTES each."""
    out, buf, size = [], [], len(head)
    for r in rows:
        if buf and size + len(r) + 1 > MAX_SQL_BYTES:
            out.append(head + ",".join(buf)); buf, size = [], len(head)
        buf.append(r); size += len(r) + 1
    if buf:
        out.append(head + ",".join(buf))
    return out


def _run_packed(db: SqlApi, stmts: list[tuple[str, str]]) -> dict[str, int]:
    """Run (tag, sql) statements in order in as few requests as possible (each under MAX_SQL_BYTES).
    Returns affected rows per tag."""
    n, batch, size = {}, [], 0
    for item in stmts + [None]:
        if item is None or (batch and size + len(item[1]) + 2 > MAX_SQL_BYTES):
            if batch:
                for (tag, _), res in zip(batch, db.execute(";\n".join(sql for _, sql in batch))):
                    n[tag] = n.get(tag, 0) + (res.get("affected_rows", 0) if isinstance(res, dict) else 0)
            batch, size = [], 0
        if item is not None:
            batch.append(item); size += len(item[1]) + 2
    return n


def _max_ts(rows: list[dict]) -> pd.Timestamp | None:
    v = rows[0]["t"] if rows else None
    return pd.Timestamp(v).tz_localize(TZ) if v else None


def _fields(rows: list[dict]) -> list[str]:
    return [r["Field"] for r in rows if r["Field"] != "ts"]


def max_ts(db: SqlApi, table: str) -> pd.Timestamp | None:
    return _max_ts(db.select(f"SELECT MAX(ts) AS t FROM {table}"))


def wide_columns(db: SqlApi) -> list[str]:
    return _fields(db.select(f"SHOW COLUMNS FROM {WIDE_T}"))


# --------------------------------------------------------------------------- write (GitHub Actions)

def long_statements(long: pd.DataFrame, since=None) -> list[str]:
    if since is not None:
        long = long[long["ts"] >= since]
    rows = [f"('{t}','{d}','{k}',{_num(v)})" for t, d, k, v in
            zip(_ts_sql(long["ts"], ms=True), long["device"], long["key"], long["value"].to_numpy())]
    return _chunks(f"INSERT IGNORE INTO {LONG_T} (ts, device, metric, value) VALUES ", rows)


def wide_statements(wide: pd.DataFrame, have: list[str], since=None) -> list[str]:
    """REPLACE the bins from `since` on (recent bins change as late samples arrive), after an ALTER that adds columns
    for variables the table (`have` = its columns) does not have yet."""
    if since is not None:
        wide = wide.loc[wide.index >= since]
    new = [c for c in wide.columns if db_col(c) not in set(have)]
    alter = [f"ALTER TABLE {WIDE_T} " + ", ".join(f"ADD COLUMN `{db_col(c)}` DOUBLE NULL" for c in new)] if new else []
    cols = ", ".join(["ts"] + [f"`{db_col(c)}`" for c in wide.columns])
    vals = wide.to_numpy(dtype=float)
    rows = [f"('{t}'," + ",".join(_num(v) for v in row) + ")" for t, row in zip(_ts_sql(wide.index, ms=False), vals)]
    return alter + _chunks(f"REPLACE INTO {WIDE_T} ({cols}) VALUES ", rows)


def manifest_statement(manifest: dict) -> str:
    js = json.dumps(manifest).replace("\\", "\\\\").replace("'", "''")
    return f"REPLACE INTO {META_T} (name, value) VALUES ('manifest', '{js}')"


def publish(db: SqlApi, long: pd.DataFrame, wide: pd.DataFrame, manifest: dict, overlap: str = "3D", full: bool = False) -> dict:
    """Send what is new since the database's last timestamp (minus `overlap`), then the manifest (last, so readers
    only see a new version once its data is in).
    Two queries: 1) create the tables if needed + read their last timestamps and the 10-min columns, 2) all writes."""
    state = db.execute(";\n".join(DDL + [f"SELECT MAX(ts) AS t FROM {LONG_T}", f"SELECT MAX(ts) AS t FROM {WIDE_T}",
                                          f"SHOW COLUMNS FROM {WIDE_T}"]))
    last_long, last_wide, have = _max_ts(state[-3]), _max_ts(state[-2]), _fields(state[-1])
    since = {k: None if full or v is None else v - pd.Timedelta(overlap) for k, v in (("long", last_long), ("wide", last_wide))}
    stmts = [("long", s) for s in long_statements(long, since["long"])]
    stmts += [("wide", s) for s in wide_statements(wide, have, since["wide"])]
    if len(wide):   # the 10-min table is rebuilt every run: bins past its end (e.g. later excluded by QC) are stale
        end = _ts_sql(pd.DatetimeIndex([wide.index.max()]), ms=False)[0]
        stmts.append(("deleted", f"DELETE FROM {WIDE_T} WHERE ts > '{end}'"))
    stmts.append(("manifest", manifest_statement(manifest)))
    n = _run_packed(db, stmts)
    fmt = lambda s: str(s) if s is not None else "all"
    return dict(long=dict(since=fmt(since["long"]), affected=n.get("long", 0)),
                wide=dict(since=fmt(since["wide"]), affected=n.get("wide", 0), deleted_after_end=n.get("deleted", 0)))


def insert_long(db: SqlApi, long: pd.DataFrame) -> int:
    """Add raw samples (ts, device, key, value) to iot_long - e.g. the electricity meter, which is not in ThingsBoard."""
    return _run_packed(db, [("long", s) for s in long_statements(long)]).get("long", 0)


# --------------------------------------------------------------------------- read (web app)

def remote_manifest(db: SqlApi) -> dict | None:
    rows = db.select(f"SELECT value FROM {META_T} WHERE name = 'manifest'")
    return json.loads(rows[0]["value"]) if rows else None


def pull_wide(db: SqlApi, since=None, page_rows: int = 5000) -> pd.DataFrame:
    """10-min table from `since` on (all if None), paged by time so each response stays small (SELECT *: no extra
    request for the column list)."""
    lo = "1970-01-01 00:00:00" if since is None else _ts_sql(pd.DatetimeIndex([since]), ms=False)[0]
    frames, op = [], ">="
    while True:
        rows = db.select(f"SELECT * FROM {WIDE_T} WHERE ts {op} '{lo}' ORDER BY ts LIMIT {page_rows}")
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        lo, op = rows[-1]["ts"], ">"
        if len(rows) < page_rows:
            break
    if not frames:
        return pd.DataFrame(columns=[app_col(c) for c in wide_columns(db)], index=pd.DatetimeIndex([], tz=TZ, name="ts"), dtype=float)
    df = pd.concat(frames, ignore_index=True)
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("ts"))).tz_localize(TZ)
    df.index.name = None
    df = df.apply(pd.to_numeric, errors="coerce").astype(float)  # the API returns numbers as strings
    df.columns = [app_col(c) for c in df.columns]
    return df


def pull_device(db: SqlApi, device: str, metrics: list[str], since=None) -> pd.DataFrame:
    """Raw samples of one device as a wide table (index ts, one column per metric), from `since` on."""
    lo = "1970-01-01 00:00:00" if since is None else _ts_sql(pd.DatetimeIndex([since]), ms=False)[0]
    keys = ", ".join(f"'{m}'" for m in metrics)
    rows = db.select(f"SELECT ts, metric, value FROM {LONG_T} WHERE device = '{device}' AND metric IN ({keys}) "
                     f"AND ts >= '{lo}' ORDER BY ts")
    if not rows:
        return pd.DataFrame(columns=metrics, index=pd.DatetimeIndex([], tz=TZ), dtype=float)
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize(TZ)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.pivot_table(index="ts", columns="metric", values="value", aggfunc="last").reindex(columns=metrics)


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
