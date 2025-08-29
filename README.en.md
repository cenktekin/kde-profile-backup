# KDE Backup & Restore (konsave + packages + flatpaks)

A minimal, safe, and scriptable helper for backing up and restoring KDE Plasma settings using konsave profiles plus package/flatpak lists and extra user config/data layers.

- Backups are stored under `kde-backups/<timestamp>/`.
- Quick incremental backups go to `kde-backups/latest/`.
- Restore is safe: it applies konsave and prints install commands for packages/flatpaks (it does not auto-install).

## Features
- konsave profile export/import (`.knsv`).
- Distro packages and Flatpak apps lists for reproducible setups.
- Extra layers beyond konsave:
  - `extra-config/`: critical KDE config files (e.g., `kdeglobals`, `kwinrc`, applets layout).
  - `extra-data/`: selected user data directories (e.g., `.local/share/applications/`, Plasma notes/system monitor, `.local/zed-preview.app`).
- Quick incremental backup to `latest/` (fast weekly snapshot of extra-*/ layers).
- Restore Preview: see what would change before applying.
- Tagging & Scope: label backups with tags and choose which parts to apply on restore/preview.
- Systemd user timer example for automation.

## Requirements
- Python 3.8+
- konsave (Python package / CLI)
- A package manager (`dnf`, `apt`, `pacman`, or `zypper`) – for listing packages
- flatpak (optional) – for listing/installing flatpaks

## Usage
Run from repository root.

### Full Backup
```bash
python scripts/kde_backup_restore.py --full
```
- Exports konsave profile, writes `packages.txt` and `flatpaks.txt`, and stores extra config/data.

### Quick Backup (Incremental extra-*)
```bash
python scripts/kde_backup_restore.py --quick
```
- Fast one-way sync into `kde-backups/latest/`.
- Optionally exports konsave (prompted).

### Restore (Interactive selection by default)
```bash
python scripts/kde_backup_restore.py --restore
```
- Imports/applies konsave profile.
- Prints the install commands for packages/flatpaks.
- Asks confirmation to copy `extra-config/` and `extra-data/`.

### Preview Mode
- `--preview [latest|<timestamp>]` shows planned changes before restore:
  - Packages to install/removable deltas
  - Missing flatpaks
  - Files to be added/overwritten under `extra-config/` and `extra-data/` (sample list)
- Note: Preview only shows what will happen; it does not delete files.

#### Interactive Menu (updated)
```
1) Full Backup (konsave + packages + flatpak + extra-*)
2) Restore (konsave import/apply + optional extra-*)
3) Quick Backup (incremental extra-*)
4) Verify (inspect .knsv contents in latest/selected backup)
5) Preview
6) Restore Dry-Run (simulation)
7) Compare (diff two backups)
8) Import Bundle (shared profile folder)
9) Exit
```

### Restore Preview (Dry-run)
```bash
python scripts/kde_backup_restore.py --preview latest
python scripts/kde_backup_restore.py --preview 20250829-151354
```
- Shows diffs: packages/flatpaks to install, and `extra-*` new/changed files.
- Does not delete anything; only reports.

### Verify Backup (.knsv content hints)
```bash
python scripts/kde_backup_restore.py --verify latest
python scripts/kde_backup_restore.py --verify 20250829-151354
```
- Checks the archive for presence of common KDE paths (panel layout, kwin, etc.).

## Advanced: konsave extra arguments
Pass-through extra args to konsave (if supported by your konsave version):
```bash
python scripts/kde_backup_restore.py --full --konsave-args "<konsave-args>"
```

## Tagging & Scope
Tag backups and control which parts to apply during restore/preview/verify.

- Create a tagged backup and define scope:
```bash
python scripts/kde_backup_restore.py --full \
  --tags "gaming,workstation" \
  --scope "konsave,packages,flatpak,extra_config,extra_data"
```
- Restore latest backup with tag "gaming", but only apply konsave + extra-config:
```bash
python scripts/kde_backup_restore.py --restore --tag gaming --scope "konsave,extra_config"
```
- Preview by tag or timestamp:
```bash
python scripts/kde_backup_restore.py --preview --tag gaming
python scripts/kde_backup_restore.py --preview 20250829-151354
```
- Verify by tag or timestamp:
```bash
python scripts/kde_backup_restore.py --verify --tag gaming
```

### Compare Backups
Compare two backups by timestamp prefix, `latest`, or `tag:<name>`:
```bash
python scripts/kde_backup_restore.py --compare 20250829-151354 20250822-093012
python scripts/kde_backup_restore.py --compare latest tag:gaming
```
Shows diffs for packages, flatpaks, konsave archive entries, and `extra-*` files.

Supported scope keys:
- `konsave`, `packages`, `flatpak`, `extra_config`, `extra_data`

`meta.json` example saved with each full backup:
```json
{
  "created": "2025-08-29-151354",
  "host": "my-host",
  "os": "Linux ...",
  "pkg_manager": "dnf",
  "profile": "20250829_kde",
  "tags": ["minimal", "gaming", "workstation"],
  "scope": {
    "konsave": true,
    "packages": true,
    "flatpak": false,
    "extra_config": true,
    "extra_data": true
  },
  "files": {
    "konsave_profile": "20250829_kde.knsv",
    "packages": "packages.txt",
    "flatpaks": "flatpaks.txt"
  }
}
```

## Backup Output Structure
```
kde-backups/
  <timestamp>/
    meta.json
    20250829_kde.knsv
    packages.txt
    flatpaks.txt
    extra-config/
      .config/...
    extra-data/
      .local/share/...
  latest/
    meta.json
    [optional] <profile>.knsv
    extra-config/
    extra-data/
```

## Automation (systemd user timer)
1) `~/.config/systemd/user/kde-quick-backup.service`
```
[Unit]
Description=KDE Quick Backup (incremental)

[Service]
Type=oneshot
ExecStart=/usr/bin/env bash -lc 'printf "h\n" | python %h/path/to/repo/scripts/kde_backup_restore.py --quick'
```
2) `~/.config/systemd/user/kde-quick-backup.timer`
```
[Unit]
Description=Run KDE Quick Backup weekly

[Timer]
OnCalendar=weekly
Persistent=true

[Install]
WantedBy=default.target
```
3) Enable
```bash
systemctl --user enable --now kde-quick-backup.timer
```

## Topgrade + systemd Quick Backup
- Run a quick backup automatically before Topgrade upgrades. Add to `~/.config/topgrade.toml`:
  ```toml
  [pre_commands]
  "KDE Quick Backup" = "bash -lc 'cd /mnt/ee8bf59b-815d-47bd-b440-5ba8ae82ff4a/projects/kde-profile-backup && printf \"h\\n\" | python3 scripts/kde_backup_restore.py --quick'"
  ```
  - `printf "h\n"` answers the konsave export prompt with “no”.
  - Target directory is `kde-backups/latest/` (gitignored).

## systemd: Weekly Quick Backup (Sunday 22:00)
User units configured to run on Sundays at 22:00:

1) `~/.config/systemd/user/kde-full-backup.service`
```ini
[Unit]
Description=KDE Quick Backup (headless-safe)

[Service]
Type=oneshot
WorkingDirectory=/mnt/ee8bf59b-815d-47bd-b440-5ba8ae82ff4a/projects/kde-profile-backup
ExecStart=/usr/bin/env bash -lc 'printf "h\n" | python3 scripts/kde_backup_restore.py --quick'
```

2) `~/.config/systemd/user/kde-full-backup.timer`
```ini
[Unit]
Description=Run KDE Quick Backup weekly (Sun 22:00)

[Timer]
OnCalendar=Sun 22:00
Persistent=true

[Install]
WantedBy=timers.target
```

3) Reload and enable
```bash
systemctl --user daemon-reload
systemctl --user enable --now kde-full-backup.timer
systemctl --user list-timers --no-pager | grep kde-full-backup
```

## Weekly Full Backup (with konsave) via cron (while logged in)
Since konsave may require an active session, schedule full backups with cron when you are logged in:
```bash
crontab -e
# Sunday 22:10 (example):
10 22 * * 0 cd /mnt/ee8bf59b-815d-47bd-b440-5ba8ae82ff4a/projects/kde-profile-backup && printf "\n" | python3 scripts/kde_backup_restore.py --full
```

## Notes & Safety
- The script does NOT automatically install packages/flatpaks; it prints commands.
- `extra-*` restore copies files; it never deletes your existing files.
- konsave changes may require relogin or a reboot to fully apply.

> “Your KDE environment isn’t just a desktop; it’s the digital reflection of your productivity and identity. This tool helps you protect and share it.”

### Community Profile Bundle
Apply a shared profile directory that contains `.knsv` + `meta.json` (+ optional `extra-*`).
```bash
python scripts/kde_backup_restore.py --import-bundle /path/to/profile_bundle --scope "konsave,extra_config"
```

## Troubleshooting
- Ensure `konsave` is installed and on PATH.
- If package listing fails, check that your system package manager is available.
- Flatpak section is skipped if `flatpak` is not installed.

## License
MIT (or your preferred license).
