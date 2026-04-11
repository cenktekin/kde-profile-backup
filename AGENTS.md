# AGENTS.md — KDE Profile Backup

## Project Overview

KDE Plasma desktop environment backup/restore tool. Main logic in `scripts/kde_backup_restore.py` (~1586 lines Python 3). Uses `konsave` for KDE config export, saves package lists (pacman/dnf/apt/zypper), Flatpak apps, and extra config/data directories.

Supporting files:
- `scripts/kde_backup_restore.py` — main script (backup, restore, preview, verify, compare, import-bundle)
- `scripts/tests_smoke.py` — smoke tests
- `scripts/kde_backup_wrapper.sh` — non-interactive wrapper for cron/systemd
- `backup-weekly.sh` — systemd/cron entry point
- `setup-systemd.sh` — systemd user timer installer

## Build / Lint / Test Commands

```bash
# Run smoke tests (creates temp backups under ./kde-backups/)
cd scripts && python3 tests_smoke.py

# Check Python syntax
python3 -m py_compile scripts/kde_backup_restore.py

# Check shell script syntax
bash -n scripts/kde_backup_wrapper.sh
bash -n backup-weekly.sh
bash -n setup-systemd.sh

# Run CI-equivalent checks
python3 -m py_compile scripts/kde_backup_restore.py && cd scripts && python3 tests_smoke.py

# Run a single smoke test (edit tests_smoke.py main() or call function directly)
cd scripts && python3 -c "from tests_smoke import *; make_backup('20250101-120000'); print('OK')"
```

No linting tools (ruff/flake8/etc.) are configured. No `requirements.txt` or `pyproject.toml` — the project has zero Python dependencies (stdlib only).

## Code Style

### Imports
- Group stdlib imports at top, no third-party imports (project has none)
- Order: sys, json, shutil, tarfile, zipfile, subprocess, platform, re, pathlib, datetime, shlex, filecmp
- Use `from pathlib import Path` and `from datetime import datetime`

### Types & Hints
- Python 3.10+ union syntax: `str | None`, `list[str]`, `dict[str, str]`, `set[str] | None`
- Type hints on function signatures, not on local variables
- Use `-> Path | None`, `-> list[str]`, `-> dict[str, list[str]]` for return types

### Formatting
- 4-space indentation, no tabs
- Blank lines separate logical sections with `# --------------------- section name -----` comments
- Functions grouped into sections: helpers, sync helpers, package detection, meta/tag/scope, konsave ops, backup/restore, UI
- Keep functions focused and relatively short

### Naming
- Functions: `snake_case` (`detect_pkg_manager`, `list_installed_packages`, `do_quick_backup`)
- Constants: `UPPER_SNAKE_CASE` (`BACKUP_ROOT`, `DEFAULT_PROFILE`, `KONSAVE`, `SCOPE_KEYS`)
- Private helpers prefixed with underscore: `_copy_if_changed`, `_sync_tree`, `_find_knsv`

### Error Handling
- Wrap subprocess calls in try/except `subprocess.CalledProcessError`
- Wrap file I/O in try/except `OSError`
- Use `shutil.which()` to check tool availability before use
- Return empty lists/dicts on failure, don't crash
- Print user-facing errors with `[!]` prefix to stderr

### Shell Scripts
- Use `#!/bin/bash` shebang
- Set `export DISPLAY=:0` when GUI tools might be needed
- Use absolute paths for Python: `/usr/bin/python3`

## Important Conventions

- **Backup directory**: `kde-backups/` is gitignored — never commit backup data
- **Timestamps**: Format `%Y%m%d-%H%M%S` (e.g., `20250829-151354`)
- **CLI modes**: Support both `--flag` style and positional shortcuts (e.g., `--full`, `--quick`, `--verify`)
- **Meta files**: Every backup has `meta.json` with `created`, `profile`, `tags`, `scope`, `files` keys
- **Turkish UI**: Interactive menu and user messages are in Turkish
- **Non-destructive**: Preview/dry-run modes show changes without applying them

## Directory Structure

```
.
├── scripts/
│   ├── kde_backup_restore.py    # Main script
│   ├── tests_smoke.py           # Smoke tests
│   └── kde_backup_wrapper.sh    # Non-interactive wrapper
├── .github/workflows/ci.yml     # CI: syntax check + smoke tests
├── backup-weekly.sh             # Cron/systemd entry point
├── setup-systemd.sh             # systemd timer installer
├── kde-weekly-backup.service    # systemd unit file
├── kde-weekly-backup.timer      # systemd timer file
├── kde-backups/                 # Backup output (gitignored)
└── AGENTS.md                    # This file
```

## What NOT to Modify

- `kde-backups/` — runtime output, gitignored
- `HISTORY.local.md` — local changelog, gitignored
- `*_input.txt` — test input files, gitignored
- `.ruff_cache/` — auto-generated
