"""One-time login to the Tuya device-sharing API with the team's app account (see pfal_twin/tuya_meter.py).

Needs [tuya] user_code (Tuya app: Me -> Settings -> Account and Security -> User Code) and device_id in
.streamlit/secrets.toml. Shows a QR code: scan it in the Tuya app (Me -> scan icon, top right) and confirm. The token is
stored in the SIS PFAL database; nothing secret is printed. Then lists the account's devices and the meter's readings.

    .venv/bin/python scripts/tuya_login.py
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qrcode  # noqa: E402
from tuya_sharing import LoginControl  # noqa: E402

from pfal_twin import tuya_meter as T  # noqa: E402
from pfal_twin.sqlapi import SqlApi  # noqa: E402

s = T.tuya_settings()
if "--push" in sys.argv:                                  # copy the local token to the database (after an outage)
    info = T.load_token(None)
    sys.exit("pushed to the database" if info and T.save_token(SqlApi.from_secrets(read_only=False), info) else "nothing pushed")
if not s["user_code"]:
    sys.exit("add user_code to [tuya] in .streamlit/secrets.toml (Tuya app: Me -> Settings -> Account and Security -> User Code)")

login = LoginControl()
r = login.qr_code(T.CLIENT_ID, T.SCHEMA, s["user_code"])
if not r.get("success"):
    sys.exit(f"QR request refused: {r.get('msg') or r.get('code')}  (check the User Code)")
qr_token = r["result"]["qrcode"]
png = Path(tempfile.gettempdir()) / "pfal_tuya_login_qr.png"
qrcode.make(T.QR_PREFIX + qr_token).save(png)
subprocess.run(["open", str(png)], check=False)          # macOS: show it
print(f"QR code opened ({png}). Scan it in the Tuya app: Me -> scan icon (top right), then confirm. Waiting up to 3 min ...")

for _ in range(60):
    time.sleep(3)
    ok, info = login.login_result(qr_token, T.CLIENT_ID, s["user_code"])
    if ok:
        break
else:
    sys.exit("no confirmation within 3 min: run the script again")
png.unlink(missing_ok=True)

db = SqlApi.from_secrets(read_only=False)
in_db = T.save_token(db, info)
print("logged in; token saved locally (.streamlit/tuya_token.json)"
      + (" and in the database (store_meta.tuya_token)" if in_db else " - database unreachable: run scripts/tuya_login.py --push later"))

meter = T.TuyaMeter(info, s["user_code"], s["device_id"], db)
devs = meter.devices()
print(f"{len(devs)} device(s) visible to the account:")
for d in devs.values():
    print(f"  {'*' if d.id == s['device_id'] else ' '} {d.id}  {d.name}  [{d.category}/{d.product_name}]  online={d.online}")
if s["device_id"] in devs:
    print("meter data points:", {k: v for k, v in devs[s["device_id"]].status.items()})
