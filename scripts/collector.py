"""Collector on the team Mac while the PFAL SQL API refuses servers abroad (GitHub Actions, Streamlit Cloud: HTTP 500
since the outage of 12 Nov 2026; it answers from Thai networks).

Every 10 min: renew the Tuya token ahead of time and store one electricity-meter reading (device "pm") in the database.
Every hour:   pull new ThingsBoard telemetry into the local store and publish it to the database (update_store.py +
              publish_db.py, the same steps GitHub Actions runs), and copy the meter readings to branch `meter` on
              GitHub for the web app on Streamlit Cloud, which the database refuses.
A reading that cannot reach the database waits in data/raw/meter/pending.jsonl and goes in with the next one.

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
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd  # noqa: E402
from pfal_twin import dbstore, tuya_meter as T  # noqa: E402
from pfal_twin.sqlapi import SqlApi  # noqa: E402

METER_EVERY, STORE_EVERY = 600, 3600
PENDING = ROOT / "data" / "raw" / "meter" / "pending.jsonl"
LOCK = ROOT / "data" / "raw" / "meter" / "collector.lock"   # one collector at a time: two would renew the token in turn


def log(msg: str):
    print(f"{pd.Timestamp.now(tz=T.TZ):%Y-%m-%d %H:%M:%S}  {msg}", flush=True)


def flush(db: SqlApi, rows: list[dict]) -> int:
    """Write the waiting readings + `rows`; keep them on disk if the database is unreachable. Returns rows stored."""
    waiting = [json.loads(line) for line in PENDING.read_text().splitlines()] if PENDING.exists() else []
    allrows = waiting + rows
    if not allrows:
        return 0
    long = pd.DataFrame(allrows)
    long["ts"] = pd.to_datetime(long["ts"]).dt.tz_convert(T.TZ)
    try:
        dbstore.insert_long(db, long)
    except Exception as e:
        PENDING.parent.mkdir(parents=True, exist_ok=True)
        PENDING.write_text("".join(json.dumps(r) + "\n" for r in allrows))
        log(f"database unreachable ({str(e)[:80]}); {len(allrows)} meter rows kept in {PENDING.name}")
        return 0
    PENDING.unlink(missing_ok=True)
    return len(allrows)


def meter_once(db: SqlApi, meter):
    """One reading; returns the meter object to use next time (a new one after a re-login)."""
    try:
        if meter is None:
            meter = T.TuyaMeter(T.load_token(db), **T.tuya_settings(), db=db)
        meter.keep_alive()
        r = meter.read()
    except Exception as e:
        log(f"meter: {str(e)[:120]} - if the login was lost: .venv/bin/python scripts/tuya_login.py (scan the QR)")
        n = flush(db, [])                    # readings kept while the database was down still go in
        if n:
            log(f"{n} waiting meter rows stored")
        return None
    now = pd.Timestamp.now(tz=T.TZ).floor("s")
    n = flush(db, [{"ts": now.isoformat(), "device": T.DEVICE, "key": k, "value": v} for k, v in r.items()])
    log(f"meter {r.get('power', float('nan')):.0f} W, {r.get('energy', float('nan')):.2f} kWh, token {meter.token_left_s / 60:.0f} min left"
        + (f" -> {n} rows stored" if n else ""))
    return meter


def store_once():
    for script in ("update_store.py", "publish_db.py"):
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, capture_output=True, text=True, timeout=1800)
        last = (p.stdout.strip().splitlines() or [""])[-1]
        log(f"{script}: {'ok' if p.returncode == 0 else 'FAILED'} {last[:160] if p.returncode == 0 else p.stderr.strip()[-200:]}")
        if p.returncode:
            break


def publish_meter_backup(db: SqlApi, days: int = 120):
    """Meter readings of the last `days` -> pm.parquet on branch `meter` (one commit, force-pushed: the repository does
    not grow)."""
    import tempfile
    df = dbstore.pull_device(db, T.DEVICE, T.METRICS, since=pd.Timestamp.now(tz=T.TZ) - pd.Timedelta(days=days))
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
        df.to_parquet(Path(tmp) / T.BACKUP_FILE)
        git = lambda *a: subprocess.run(["git", *a], cwd=tmp, capture_output=True, text=True, timeout=120)
        git("init", "-q", "-b", "meter")
        git("add", T.BACKUP_FILE)
        git("-c", "user.name=sis-pfal-collector", "-c", "user.email=actions@users.noreply.github.com",
            "commit", "-q", "-m", f"meter readings {pd.Timestamp.now(tz=T.TZ):%Y-%m-%d %H:%M}")
        p = git("push", "-q", "--force", url, "meter")
    log(f"meter backup: {len(df)} readings -> branch meter" if p.returncode == 0 else f"meter backup FAILED: {p.stderr.strip()[-160:]}")


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
            try:
                publish_meter_backup(db)
            except Exception as e:
                log(f"meter backup: {str(e)[:120]}")
            next_store = t0 + STORE_EVERY
        if "--once" in sys.argv:
            return
        time.sleep(max(30, METER_EVERY - (time.time() - t0)))


if __name__ == "__main__":
    main()
