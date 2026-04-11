#!/bin/bash

# Setup script for KDE weekly backup service

# Create the systemd user directory if it doesn't exist
mkdir -p ~/.config/systemd/user

# Copy the service and timer files to the user systemd directory
cp kde-weekly-backup.service ~/.config/systemd/user/
cp kde-weekly-backup.timer ~/.config/systemd/user/

# Reload the systemd user daemon
systemctl --user daemon-reload

# Enable and start the timer
systemctl --user enable kde-weekly-backup.timer
systemctl --user start kde-weekly-backup.timer

echo "KDE weekly backup service and timer have been installed and started."
echo "To check the status, run: systemctl --user status kde-weekly-backup.timer"
echo "To view logs, run: journalctl --user -u kde-weekly-backup.service -f"