"""Read the PFAL electricity meter once and store the readings in the SIS PFAL database (iot_long, device "pm").
Run by .github/workflows/update_data.yml after the ThingsBoard update; by hand:  .venv/bin/python scripts/read_meter.py

The energy counter only grows, so readings hours apart still give complete kWh per day (pfal_twin.tuya_meter.daily_energy).
Needs PFAL_DB_USER/PASS (or .streamlit/secrets.toml) and the Tuya login token in the database (scripts/tuya_login.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd  # noqa: E402
from pfal_twin import dbstore, tuya_meter as T  # noqa: E402
from pfal_twin.sqlapi import SqlApi  # noqa: E402

db = SqlApi.from_secrets(read_only=False)
meter = T.TuyaMeter.from_store(db)
reading = meter.read()
now = pd.Timestamp.now(tz=T.TZ).floor("s")
long = pd.DataFrame({"ts": now, "device": T.DEVICE, "key": list(reading), "value": list(reading.values())})
n = dbstore.insert_long(db, long)
print(f"meter {now:%Y-%m-%d %H:%M:%S}: {reading.get('power', float('nan')):.0f} W, counter {reading.get('energy', float('nan')):.2f} kWh "
      f"-> {n} rows stored")
