#!/bin/bash

# Weekly KDE backup script
# This script can be called by cron or systemd

# Set the working directory
cd /home/$(whoami)/Belgeler/projects/kde-profile-backup

# Set display environment if needed for GUI elements
export DISPLAY=:0

# Create the backup
/usr/bin/python3 scripts/kde_backup_restore.py --full

# Optionally, add notification when backup is complete
if command -v notify-send &> /dev/null; then
    notify-send "KDE Backup" "Weekly backup completed" --icon=system-run
fi