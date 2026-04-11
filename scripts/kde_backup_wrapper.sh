#!/bin/bash
# Wrapper script for KDE backup that provides default profile name to avoid interactive input

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

cd "$REPO_DIR"
echo "kde-profile" | python3 "$SCRIPT_DIR/kde_backup_restore.py" --full