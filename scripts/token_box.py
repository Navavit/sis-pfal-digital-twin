"""Keep the Tuya token between GitHub Actions runs, encrypted (the repository is public and its caches can be read by
other workflows; the key is the TUYA_BOX_KEY secret, which they cannot read).

    python scripts/token_box.py open    .tuya_box/token.enc (cache) or the TUYA_TOKEN_SEED secret, whichever is newer
                                        -> .streamlit/tuya_token.json
    python scripts/token_box.py seal    .streamlit/tuya_token.json -> .tuya_box/token.enc (saved to the cache next)

TUYA_TOKEN_SEED holds a token from a fresh QR login (scripts/tuya_login.py --github); after that the runs renew it
themselves. Nothing secret is printed.
"""
import json
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / ".tuya_box" / "token.enc"
TOKEN = ROOT / ".streamlit" / "tuya_token.json"
key = os.environ.get("TUYA_BOX_KEY", "").encode()
if not key:
    sys.exit("TUYA_BOX_KEY is not set")
f = Fernet(key)

if sys.argv[1:] == ["open"]:
    found = []
    if BOX.exists():
        try:
            found.append(("cache", json.loads(f.decrypt(BOX.read_bytes()))))
        except (InvalidToken, ValueError):
            print("cached token unreadable (key changed?) - ignored")
    if os.environ.get("TUYA_TOKEN_SEED"):
        found.append(("seed", json.loads(os.environ["TUYA_TOKEN_SEED"])))
    if not found:
        sys.exit("no Tuya token: run scripts/tuya_login.py --github on a computer (scan the QR once)")
    src, info = max(found, key=lambda x: x[1].get("t", 0))
    TOKEN.parent.mkdir(exist_ok=True)
    TOKEN.write_text(json.dumps(info)); TOKEN.chmod(0o600)
    print(f"token from the {src}")
elif sys.argv[1:] == ["seal"]:
    if not TOKEN.exists():
        sys.exit("no token to keep")
    BOX.parent.mkdir(exist_ok=True)
    BOX.write_bytes(f.encrypt(TOKEN.read_bytes()))
    print("token sealed")
else:
    sys.exit(__doc__)
