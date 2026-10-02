"""Check the PFAL SQL API connection and what the account may do. Prints no credentials or token.
    .venv/bin/python scripts/check_db.py"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pfal_twin.sqlapi import SqlApi, SqlApiError  # noqa: E402

db = SqlApi.from_secrets()
try:
    db.login()
    print("login: OK")
except SqlApiError as e:
    sys.exit(f"login: {e}")

for sql in ["SELECT VERSION() AS version, DATABASE() AS db, CURRENT_USER() AS account", "SHOW GRANTS", "SHOW TABLES",
            "SHOW VARIABLES WHERE Variable_name IN ('max_allowed_packet', 'max_execution_time', 'wait_timeout')"]:
    try:
        rows = db.select(sql)
        print(f"\n# {sql}")
        for row in rows:
            line = "  ".join(f"{k}={v}" for k, v in row.items())
            print("  ", re.sub(r"PASSWORD '[^']*'", "PASSWORD '***'", line))
    except SqlApiError as e:
        print(f"\n# {sql}\n   {e}")
