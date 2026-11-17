#!/bin/bash
# Install / remove the collector (scripts/collector.py) as a launchd agent of this Mac user: it starts at login and is
# restarted if it stops.  Log: ~/Library/Logs/pfal-collector.log
#   scripts/install_collector.sh            install (or reinstall) and start
#   scripts/install_collector.sh remove     stop and remove
set -e
LABEL=th.ac.ku.sis.pfal-collector
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "$1" = "remove" ]; then rm -f "$PLIST"; echo "collector removed"; exit 0; fi
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$ROOT/.venv/bin/python</string><string>$ROOT/scripts/collector.py</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>300</integer>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/pfal-collector.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/pfal-collector.log</string>
  <key>EnvironmentVariables</key><dict><key>PYTHONWARNINGS</key><string>ignore</string></dict>
</dict></plist>
EOF
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "collector installed: $PLIST  (log: ~/Library/Logs/pfal-collector.log)"
