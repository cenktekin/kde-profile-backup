#!/bin/bash
# Wrapper script for KDE backup that provides default profile name to avoid interactive input

cd /home/cenk/Belgeler/projects/kde-profile-backup
echo "kde-profile" | python3 /home/cenk/Belgeler/projects/kde-profile-backup/scripts/kde_backup_restore.py --full