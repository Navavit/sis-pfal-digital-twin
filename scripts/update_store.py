"""Pull new telemetry from ThingsBoard into the local store and rebuild the 10-min table (+ manifest).
Used by GitHub Actions every 30 min and by hand:  .venv/bin/python scripts/update_store.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pfal_twin import thingsboard as tb, store, PROCESSED  # noqa: E402
import pandas as pd  # noqa: E402

client = tb.Client().login_public()
long = tb.update_store(client, backfill_from="2025-12-20", verbose=True)
w, qc = tb.clean_wide(tb.to_wide(long, "10min"))
env, ctrl = tb.split_env_control(w)
w = pd.concat([env, tb.state_ffill(ctrl)], axis=1)
w.to_parquet(tb.WIDE_PARQUET)
qc.to_csv(PROCESSED / "iot_qc_report.csv")
m = store.write_manifest(w, long_rows=len(long))
print(f"store: {len(long):,} raw samples -> {len(w):,} x 10-min bins, {w.shape[1]} columns, {w.index.min():%Y-%m-%d} -> {w.index.max():%Y-%m-%d %H:%M} | manifest {m['updated_at']}")
