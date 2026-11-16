#!/bin/bash
# install_cassiopeia.sh
# Purpose : Make Cassiopeia start when you log in and keep running, and add a
#           Cassiopeia app to ~/Applications that opens its window.
# Run     : bash scripts/install_cassiopeia.sh      (once, from the project folder)
# Undo    : bash scripts/uninstall_cassiopeia.sh
# UNTESTED: written without access to a Mac. If a step fails, the message says which.
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT/.venv/bin/python"
LABEL="local.cassiopeia"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
APP="$HOME/Applications/Cassiopeia.app"

[ -x "$PYTHON" ] || { echo "No virtual environment at $PROJECT/.venv. Create it first (see SETUP_GUIDE.md)."; exit 1; }
case "$PROJECT" in
  "$HOME/Desktop"/*|"$HOME/Documents"/*|"$HOME/Downloads"/*)
    echo "Warning: macOS restricts background programs in Desktop, Documents and Downloads."
    echo "If Cassiopeia fails to start at login, move the project (for example to ~/Developer) and run this again." ;;
esac

# 1. The background service: starts at login, restarts if it stops.
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST_END
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PYTHON</string><string>-m</string><string>cassiopeia</string><string>--service</string></array>
  <key>WorkingDirectory</key><string>$PROJECT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$PROJECT/cassiopeia.log</string>
  <key>StandardErrorPath</key><string>$PROJECT/cassiopeia.log</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>$HOME/.local/bin:$HOME/.claude/local:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict></plist>
PLIST_END
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Background service installed: $PLIST"

# 2. The app icon: a tiny app whose only job is to open the window.
mkdir -p "$APP/Contents/MacOS"
cat > "$APP/Contents/MacOS/Cassiopeia" <<APP_END
#!/bin/bash
cd "$PROJECT" && exec "$PYTHON" -m cassiopeia
APP_END
chmod +x "$APP/Contents/MacOS/Cassiopeia"
cat > "$APP/Contents/Info.plist" <<INFO_END
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Cassiopeia</string>
  <key>CFBundleIdentifier</key><string>local.cassiopeia.app</string>
  <key>CFBundleExecutable</key><string>Cassiopeia</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>0.1.0</string>
</dict></plist>
INFO_END
echo "App installed: $APP  (open it from Spotlight or drag it to the Dock)"
echo "Cassiopeia is now running. Log file: $PROJECT/cassiopeia.log"
