"""Publish the local store (raw samples + 10-min table + manifest) to the SIS PFAL SQL database.
Incremental by default (only what is newer than the database, minus a 3-day overlap); --full sends everything.
Used by GitHub Actions after update_store.py, and by hand for the first load:

    .venv/bin/python scripts/publish_db.py [--full] [--dir DIR]   # DIR holds the three store files (default: data/)
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd  # noqa: E402
from pfal_twin import store, dbstore  # noqa: E402
from pfal_twin.sqlapi import SqlApi  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--full", action="store_true")
ap.add_argument("--dir", type=Path, help="folder with thingsboard_long.parquet, iot_10min.parquet, store_manifest.json")
a = ap.parse_args()
long_p, wide_p, man_p = ((a.dir / store.LONG.name, a.dir / store.WIDE.name, a.dir / store.MANIFEST.name) if a.dir
                         else (store.LONG, store.WIDE, store.MANIFEST))

long, wide, manifest = pd.read_parquet(long_p), pd.read_parquet(wide_p), json.loads(man_p.read_text())
db = SqlApi.from_secrets(read_only=False)
out = dbstore.publish(db, long, wide, manifest, full=a.full)
print(f"database: raw since {out['long']['since']} -> {out['long']['affected']:,} new rows; "
      f"10-min since {out['wide']['since']} -> {out['wide']['affected']:,} rows written | manifest {manifest['updated_at']}")
