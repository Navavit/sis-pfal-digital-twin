"""Where the IoT history lives when the app runs in the cloud.

GitHub Actions (.github/workflows/update_data.yml) pulls new telemetry from ThingsBoard every 30 min and force-pushes
the store to the orphan branch `data` of the repo (one commit, history discarded, so the repo never grows):

    data/raw/iot/thingsboard_long.parquet   raw samples (long format)
    data/processed/iot_10min.parquet        10-min table used by the twin
    data/processed/store_manifest.json      {"updated_at": ..., "rows": ..., "span": [...]} -- what the app polls

`sync_from_github()` downloads the 10-min table when the branch has a newer manifest than the local copy.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from . import IOT_RAW, PROCESSED

REPO = "Navavit/sis-pfal-digital-twin"
BRANCH = "data"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
MANIFEST = PROCESSED / "store_manifest.json"
WIDE = PROCESSED / "iot_10min.parquet"
LONG = IOT_RAW / "thingsboard_long.parquet"


def write_manifest(wide: pd.DataFrame, long_rows: int | None = None, path: Path = MANIFEST) -> dict:
    m = dict(updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
             span=[wide.index.min().isoformat(), wide.index.max().isoformat()], bins=int(len(wide)), columns=int(wide.shape[1]),
             long_rows=long_rows)
    path.write_text(json.dumps(m, indent=1))
    return m


def local_manifest(path: Path = MANIFEST) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def remote_manifest(timeout=10) -> dict | None:
    try:
        r = requests.get(f"{RAW_BASE}/data/processed/store_manifest.json", timeout=timeout, headers={"Cache-Control": "no-cache"})
        return r.json() if r.ok else None
    except requests.RequestException:
        return None


def sync_from_github(force: bool = False, with_long: bool = False, timeout=60) -> dict:
    """Download the store from the `data` branch if it is newer than the local copy. Returns a small status dict."""
    rm = remote_manifest()
    lm = local_manifest()
    if rm is None:
        return dict(action="offline", local=lm)
    if not force and lm and lm.get("updated_at", "") >= rm.get("updated_at", "") and WIDE.exists():
        return dict(action="up-to-date", local=lm, remote=rm)
    files = [("data/processed/iot_10min.parquet", WIDE)] + ([("data/raw/iot/thingsboard_long.parquet", LONG)] if with_long else [])
    for rel, dst in files:
        r = requests.get(f"{RAW_BASE}/{rel}", timeout=timeout); r.raise_for_status()
        dst.parent.mkdir(parents=True, exist_ok=True); dst.write_bytes(r.content)
    MANIFEST.write_text(json.dumps(rm, indent=1))
    return dict(action="downloaded", local=rm, remote=rm)
