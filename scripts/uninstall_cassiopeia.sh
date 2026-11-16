#!/bin/bash
# uninstall_cassiopeia.sh
# Purpose : Stop Cassiopeia starting at login and remove its app icon. Your data is untouched.
# Run     : bash scripts/uninstall_cassiopeia.sh
LABEL="local.cassiopeia"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
[ -f "$HOME/Library/LaunchAgents/$LABEL.plist" ] && mv "$HOME/Library/LaunchAgents/$LABEL.plist" "$HOME/.Trash/" 2>/dev/null
[ -d "$HOME/Applications/Cassiopeia.app" ] && mv "$HOME/Applications/Cassiopeia.app" "$HOME/.Trash/Cassiopeia-$(date +%s).app" 2>/dev/null
echo "Cassiopeia no longer starts at login. The service file and app icon are in the Trash."
