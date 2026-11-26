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
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import pandas as pd  # noqa: E402
from pfal_twin import tuya_meter as T  # noqa: E402
import collector as C  # noqa: E402

info = T.load_token(None)
if not info:
    sys.exit("no Tuya token: run scripts/tuya_login.py --github on a computer (scan the QR once)")
meter = T.TuyaMeter(info, **T.tuya_settings(), db=None)
meter.keep_alive(int(os.environ.get("TUYA_RENEW_MARGIN_S", 5400)))
r = meter.read()
now = pd.Timestamp.now(tz=T.TZ).floor("s")
C.append_log([{"ts": now.isoformat(), "device": T.DEVICE, "key": k, "value": v} for k, v in r.items()])
n = C.merge_readings()
print(f"meter {now:%Y-%m-%d %H:%M}: {r.get('power', float('nan')):.0f} W, {r.get('energy', float('nan')):.2f} kWh, "
      f"token {meter.token_left_s / 60:.0f} min left; {n} rows merged into the store")
