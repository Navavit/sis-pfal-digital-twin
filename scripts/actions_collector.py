"""The collector as one long GitHub Actions run (.github/workflows/update_data.yml), so no computer has to stay on.

GitHub starts scheduled workflows late or not at all at busy times (a "*/10" schedule ran twice in 22 h on 26-27 Nov
2026), so one run does the work itself for about 5.5 h and then starts the next run (workflow_dispatch):
    every 10 min   read the electricity meter into the raw store (scripts/meter_once.py)
    every 30 min   ThingsBoard -> 10-min table (update_store.py), push branch `data`, publish the database (publish_db.py)
The Tuya token is sealed after every reading (scripts/token_box.py) and the workflow saves it to the cache at the end.

    python scripts/actions_collector.py [minutes]       (default 330; GitHub stops a job at 360)
Needs PUSH_URL (https://x-access-token:...@github.com/<repo>.git) for branch `data`; nothing secret is printed.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METER_EVERY, STORE_EVERY = 600, 1800
DATA_FILES = ["data/raw/iot/thingsboard_long.parquet", "data/processed/iot_10min.parquet",
              "data/processed/store_manifest.json", "data/processed/iot_qc_report.csv"]


def log(msg):
    print(time.strftime("%H:%M:%S", time.gmtime(time.time() + 7 * 3600)), msg, flush=True)


def run(*cmd) -> bool:
    p = subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True, timeout=1500)
    out = (p.stdout.strip().splitlines() or [""])[-1] if p.returncode == 0 else p.stderr.strip()[-200:]
    log(f"{cmd[0]}: {'ok' if p.returncode == 0 else 'FAILED'} {out[:200]}")
    return p.returncode == 0


def push() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        for f in DATA_FILES:
            (Path(tmp) / f).parent.mkdir(parents=True, exist_ok=True)
            (Path(tmp) / f).write_bytes((ROOT / f).read_bytes())
        git = lambda *a: subprocess.run(["git", *a], cwd=tmp, capture_output=True, text=True, timeout=300)
        git("init", "-q", "-b", "data"); git("add", "-A")
        git("-c", "user.name=sis-pfal-bot", "-c", "user.email=actions@users.noreply.github.com", "commit", "-q", "-m",
            f"store {time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime())}")
        ok = git("push", "-q", "--force", os.environ["PUSH_URL"], "data").returncode == 0
    log("branch data: " + ("pushed" if ok else "push FAILED"))
    return ok


def main():
    minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 330
    end, next_meter, next_store = time.time() + minutes * 60, 0.0, 0.0
    while time.time() < end:
        now = time.time()
        if now >= next_meter:
            if run("scripts/meter_once.py"):
                run("scripts/token_box.py", "seal")
            next_meter = now + METER_EVERY
        if now >= next_store:
            if run("scripts/update_store.py"):
                push()
                run("scripts/publish_db.py")          # the database refuses servers abroad for now: a failure is logged only
            next_store = now + STORE_EVERY
        time.sleep(max(5.0, min(next_meter, next_store, end) - time.time()))


if __name__ == "__main__":
    main()
