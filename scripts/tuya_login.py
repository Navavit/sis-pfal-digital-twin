"""Log GitHub Actions in to the Tuya device-sharing API with the team's app account (see pfal_twin/tuya_meter.py), when
its login is lost (the update-data run then says "no Tuya token" or "sign invalid").

Needs [tuya] user_code (Tuya app: Me -> Settings -> Account and Security -> User Code) and device_id in
.streamlit/secrets.toml. Shows a QR code: scan it in the Tuya app (Me -> scan icon, top right) and confirm. The token goes
straight into the repository secret TUYA_TOKEN_SEED (and a key TUYA_BOX_KEY is made once) with the `gh` command line,
logged in as someone who may set the repository's secrets; it is never printed or written to disk. Tuya keeps one login
of this client at a time, so a new login replaces the one GitHub had.

    .venv/bin/python scripts/tuya_login.py --github
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

s = T.tuya_settings()
if "--github" not in sys.argv:
    sys.exit(__doc__)
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

# straight into the repository secrets, never on screen or disk
have = subprocess.run(["gh", "secret", "list"], capture_output=True, text=True).stdout
if "TUYA_BOX_KEY" not in have:
    from cryptography.fernet import Fernet
    subprocess.run(["gh", "secret", "set", "TUYA_BOX_KEY"], input=Fernet.generate_key().decode(), text=True, check=True)
import json
subprocess.run(["gh", "secret", "set", "TUYA_TOKEN_SEED"], input=json.dumps(info), text=True, check=True)
sys.exit("logged in for GitHub Actions: secrets TUYA_TOKEN_SEED (and TUYA_BOX_KEY) set - run the update-data workflow")
