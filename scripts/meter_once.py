"""One electricity-meter reading for GitHub Actions (.github/workflows/update_data.yml), so no computer has to stay on.

The workflow restores the Tuya token (scripts/token_box.py open), this script renews it when it is getting old, reads the
meter and merges the reading into the raw store (data/raw/iot/thingsboard_long.parquet, device "pm"); update_store.py
then turns it into pm.* columns of the 10-min table like on the Mac. The renewed token is kept for the next run
(scripts/token_box.py seal). Nothing secret is printed.

GitHub runs the schedule late at busy times, so the token is renewed whenever it has less than TUYA_RENEW_MARGIN_S
(default 90 min) left; it lives 2 h.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd  # noqa: E402
from pfal_twin import store, thingsboard as tb, tuya_meter as T  # noqa: E402


def merge(rows: list[dict]) -> int:
    """Meter readings (ts, device, key, value) -> the raw store (thingsboard_long.parquet, next to the sensors)."""
    new = pd.DataFrame(rows)
    new["ts"] = pd.to_datetime(new["ts"], utc=True).dt.tz_convert(T.TZ)
    new["value"] = pd.to_numeric(new["value"], errors="coerce")
    allf = pd.concat([tb.load_long(store.LONG), new[["ts", "device", "key", "value"]]], ignore_index=True)
    allf = allf.drop_duplicates(["ts", "device", "key"]).sort_values(["device", "key", "ts"]).reset_index(drop=True)
    allf.to_parquet(store.LONG, index=False)
    return len(new)


info = T.load_token(None)
if not info:
    sys.exit("no Tuya token: run scripts/tuya_login.py --github on a computer (scan the QR once)")
meter = T.TuyaMeter(info, **T.tuya_settings(), db=None)
meter.keep_alive(int(os.environ.get("TUYA_RENEW_MARGIN_S", 5400)))
r = meter.read()
now = pd.Timestamp.now(tz=T.TZ).floor("s")
n = merge([{"ts": now.isoformat(), "device": T.DEVICE, "key": k, "value": v} for k, v in r.items()])
print(f"meter {now:%Y-%m-%d %H:%M}: {r.get('power', float('nan')):.0f} W, {r.get('energy', float('nan')):.2f} kWh, "
      f"token {meter.token_left_s / 60:.0f} min left; {n} rows merged into the store")
