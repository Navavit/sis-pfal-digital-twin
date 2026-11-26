#!/bin/bash
# Install / remove the collector (scripts/collector.py) as a systemd service on an always-on Linux machine in Thailand
# (Raspberry Pi in the room, or a campus server): it starts at boot and is restarted if it stops. No Mac needed.
#   sudo scripts/install_collector_linux.sh            install (or reinstall) and start
#   sudo scripts/install_collector_linux.sh remove     stop and remove
#   journalctl -u pfal-collector -f                     log
# Before: clone the repo, python3 -m venv .venv && .venv/bin/pip install -r requirements.txt, copy
# .streamlit/secrets.toml ([pfal_db], [tuya]) from the Mac, give `git push` to the repo (a deploy key with write access),
# then stop the Mac's collector (scripts/install_collector.sh remove) - one collector at a time.
set -e
NAME=pfal-collector
UNIT=/etc/systemd/system/$NAME.service
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_AS="${SUDO_USER:-$(id -un)}"
systemctl disable --now $NAME 2>/dev/null || true
if [ "$1" = "remove" ]; then rm -f "$UNIT"; systemctl daemon-reload; echo "collector removed"; exit 0; fi
cat > "$UNIT" <<UNIT
[Unit]
Description=SIS PFAL collector (electricity meter + hourly store update)
After=network-online.target
Wants=network-online.target

[Service]
User=$RUN_AS
WorkingDirectory=$ROOT
Environment=PYTHONWARNINGS=ignore
ExecStart=$ROOT/.venv/bin/python $ROOT/scripts/collector.py
Restart=always
RestartSec=300

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now $NAME
echo "collector installed: $UNIT  (log: journalctl -u $NAME -f)"
