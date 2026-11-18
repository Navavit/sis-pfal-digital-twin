"""Collector on the team Mac: the electricity meter and the hourly store update, in one store with the sensors.

Every 10 min: renew the Tuya token ahead of time (it lives 2 h) and read the electricity meter; the reading goes to
              data/raw/meter/readings.csv (device "pm").
Every hour:   merge those readings into the raw store (thingsboard_long.parquet: ThingsBoard sensors + meter), pull new
              ThingsBoard telemetry and rebuild the 10-min table (update_store.py), publish it to the SIS PFAL database
              (publish_db.py) and push the store to branch `data` - the same files and steps GitHub Actions uses. So the
              meter lives exactly where the sensors live: iot_long + iot_10min (pm.* columns) + branch `data`.
If the database is down (server outage, the server move of Nov 2026), branch `data` and the local files still get
everything, and the database catches up at the first hour it answers again (publish_db re-sends what it is missing).

Runs under launchd (scripts/install_collector.sh); by hand:  .venv/bin/python scripts/collector.py [--once]
It keeps the Mac awake while it runs (caffeinate; keep the Mac on mains power with the lid open). If the Tuya login is
lost anyway (the Mac off or asleep for more than ~2 h), it logs that and keeps trying with whatever token
scripts/tuya_login.py saves next - scan the QR once more and it carries on by itself.
"""
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd  # noqa: E402
from pfal_twin import store, thingsboard as tb, tuya_meter as T  # noqa: E402
from pfal_twin.sqlapi import SqlApi  # noqa: E402

METER_EVERY, STORE_EVERY = 600, 3600
LOG = ROOT / "data" / "raw" / "meter" / "readings.csv"       # every reading, until it is merged into the raw store
PENDING = ROOT / "data" / "raw" / "meter" / "pending.jsonl"  # left over from the earlier collector: merged once
LOCK = ROOT / "data" / "raw" / "meter" / "collector.lock"   # one collector at a time: two would renew the token in turn
# the store files published to branch `data` (as in .github/workflows/update_data.yml)
DATA_FILES = ["data/raw/iot/thingsboard_long.parquet", "data/processed/iot_10min.parquet",
              "data/processed/store_manifest.json", "data/processed/iot_qc_report.csv"]


def log(msg: str):
    print(f"{pd.Timestamp.now(tz=T.TZ):%Y-%m-%d %H:%M:%S}  {msg}", flush=True)


def append_log(rows: list[dict]):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    with LOG.open("a") as f:
        if new:
            f.write("ts,device,key,value\n")
        f.writelines(f"{r['ts']},{r['device']},{r['key']},{r['value']}\n" for r in rows)


def meter_once(db: SqlApi, meter):
    """One reading into readings.csv; returns the meter object to use next time (a new one after a re-login)."""
    try:
        if meter is None:
            meter = T.TuyaMeter(T.load_token(db), **T.tuya_settings(), db=db)
        meter.keep_alive()
        r = meter.read()
    except Exception as e:
        log(f"meter: {str(e)[:120]} - if the login was lost: .venv/bin/python scripts/tuya_login.py (scan the QR)")
        return None
    now = pd.Timestamp.now(tz=T.TZ).floor("s")
    append_log([{"ts": now.isoformat(), "device": T.DEVICE, "key": k, "value": v} for k, v in r.items()])
    log(f"meter {r.get('power', float('nan')):.0f} W, {r.get('energy', float('nan')):.2f} kWh, token {meter.token_left_s / 60:.0f} min left")
    return meter


def merge_readings() -> int:
    """Meter readings (readings.csv + any left-over pending.jsonl) -> the raw store; readings.csv is then emptied."""
    parts = []
    if LOG.exists():
        parts.append(pd.read_csv(LOG))
    if PENDING.exists():
        parts.append(pd.DataFrame([json.loads(line) for line in PENDING.read_text().splitlines()]))
    if not parts:
        return 0
    new = pd.concat(parts, ignore_index=True)
    new["ts"] = pd.to_datetime(new["ts"], utc=True).dt.tz_convert(T.TZ)
    new["value"] = pd.to_numeric(new["value"], errors="coerce")
    old = tb.load_long(store.LONG)
    allf = pd.concat([old, new[["ts", "device", "key", "value"]]], ignore_index=True)
    allf = allf.drop_duplicates(["ts", "device", "key"]).sort_values(["device", "key", "ts"]).reset_index(drop=True)
    allf.to_parquet(store.LONG, index=False)
    LOG.unlink(missing_ok=True)
    PENDING.unlink(missing_ok=True)
    return len(new)


def run(script: str) -> bool:
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, capture_output=True, text=True, timeout=1800)
    last = (p.stdout.strip().splitlines() or [""])[-1]
    log(f"{script}: {'ok' if p.returncode == 0 else 'FAILED'} {last[:160] if p.returncode == 0 else p.stderr.strip()[-200:]}")
    return p.returncode == 0


def push_data_branch():
    """The store files -> branch `data` (one commit, force-pushed: the repository does not grow), as GitHub Actions does."""
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
        for f in DATA_FILES:
            (Path(tmp) / f).parent.mkdir(parents=True, exist_ok=True)
            (Path(tmp) / f).write_bytes((ROOT / f).read_bytes())
        git = lambda *a: subprocess.run(["git", *a], cwd=tmp, capture_output=True, text=True, timeout=300)
        git("init", "-q", "-b", "data")
        git("add", "-A")
        git("-c", "user.name=sis-pfal-collector", "-c", "user.email=actions@users.noreply.github.com",
            "commit", "-q", "-m", f"store {pd.Timestamp.now(tz='UTC'):%Y-%m-%dT%H:%MZ} (collector)")
        p = git("push", "-q", "--force", url, "data")
    log("branch data: pushed" if p.returncode == 0 else f"branch data FAILED: {p.stderr.strip()[-160:]}")


def store_once():
    n = merge_readings()
    if n:
        log(f"{n} meter rows merged into the store")
    if run("update_store.py"):
        push_data_branch()
        run("publish_db.py")              # may fail while the database is down: it re-sends what it lacks next time


def main():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock = open(LOCK, "w")
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:              # another collector runs: wait (launchd would only restart this one)
            if "--once" in sys.argv:
                sys.exit("another collector is running")
            time.sleep(300)
    # Keep the Mac awake while the collector runs: asleep, nothing renews the Tuya token (it lives 2 h) and the login is
    # lost. caffeinate -i (no idle sleep) -s (no system sleep on mains power) ends with this process. A closed lid on
    # battery still sleeps.
    subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())])
    db = SqlApi.from_secrets(read_only=False)
    meter, next_store = None, 0.0
    while True:
        t0 = time.time()
        meter = meter_once(db, meter)
        if t0 >= next_store:
            store_once()
            next_store = t0 + STORE_EVERY
        if "--once" in sys.argv:
            return
        time.sleep(max(30, METER_EVERY - (time.time() - t0)))


if __name__ == "__main__":
    main()
