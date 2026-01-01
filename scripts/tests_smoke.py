#!/usr/bin/env python3
"""
Lightweight smoke tests for KDE backup tool: preview, dry-run, compare, import-bundle, verify.
Creates temporary backup structures under ./kde-backups/ and exercises functions.
"""

from pathlib import Path
import json
import shutil
import shutil as sys_shutil
import time
import zipfile

from kde_backup_restore import (
    BACKUP_ROOT,
    write_text,
    ensure_dir,
    do_preview,
    do_restore_dry_run,
    compare_backups,
    restore_import_bundle,
    verify_backup,
)


def konsave_available():
    """Check if konsave is available in PATH."""
    return sys_shutil.which("konsave") is not None


def make_backup(ts: str, with_knsv: bool = False):
    b = BACKUP_ROOT / ts
    ensure_dir(b)
    # minimal files
    write_text(b / "packages.txt", "htop\nnonexistent-pkg-xyz\n")
    write_text(b / "flatpaks.txt", "org.nonexistent.App\n")
    # extra-config file
    cfg_dir = b / "extra-config/.config"
    ensure_dir(cfg_dir)
    write_text(cfg_dir / "kdeglobals", "[General]\nColorScheme=Breeze\n")
    # extra-data file
    data_dir = b / "extra-data/.local/share/applications"
    ensure_dir(data_dir)
    write_text(
        data_dir / "foo.desktop",
        "[Desktop Entry]\nName=Foo\nExec=foo\nType=Application\n",
    )
    # meta
    meta = {
        "created": ts,
        "host": "test-host",
        "os": "Linux",
        "pkg_manager": "unknown",
        "profile": f"{ts}_kde",
        "tags": ["smoke"],
        "scope": {
            "konsave": True,
            "packages": True,
            "flatpak": True,
            "extra_config": True,
            "extra_data": True,
        },
        "files": {
            "konsave_profile": f"{ts}_kde.knsv",
            "packages": "packages.txt",
            "flatpaks": "flatpaks.txt",
        },
    }
    write_text(b / "meta.json", json.dumps(meta, indent=2))
    # optional dummy .knsv
    if with_knsv:
        (b / f"{ts}_kde.knsv").write_bytes(b"\x50\x4b\x03\x04")  # zip header
    return b


def make_backup_with_valid_knsv(ts: str):
    """Create a backup with a valid .knsv containing expected KDE config files."""
    b = BACKUP_ROOT / ts
    ensure_dir(b)

    # Create meta.json
    meta = {
        "created": ts,
        "host": "test-host",
        "os": "Linux",
        "pkg_manager": "unknown",
        "profile": f"{ts}_kde",
        "tags": ["smoke-verify"],
        "scope": {
            "konsave": True,
            "packages": True,
            "flatpak": False,
            "extra_config": True,
            "extra_data": False,
        },
        "files": {
            "konsave_profile": f"{ts}_kde.knsv",
        },
    }
    write_text(b / "meta.json", json.dumps(meta, indent=2))

    # Create a valid .knsv (ZIP format) with expected KDE config files
    knsv_path = b / f"{ts}_kde.knsv"
    with zipfile.ZipFile(knsv_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add expected config files that verify_backup looks for
        zf.writestr(
            "export/config_folder/.config/plasma-org.kde.plasma.desktop-appletsrc",
            "[General]\n",
        )
        zf.writestr(
            "export/config_folder/.config/kdeglobals",
            "[General]\nColorScheme=BreezeDark\n",
        )
        zf.writestr("export/config_folder/.config/kwinrc", "[Windows]\n")
        # Add a plasmoid directory (verify_backup checks for this)
        zf.writestr(
            "export/share_folder/.local/share/plasma/plasmoids/test/contents/config/main.xml",
            "<config>\n</config>\n",
        )
        # Add look-and-feel
        zf.writestr(
            "export/share_folder/.local/share/plasma/look-and-feel/test/metadata.desktop",
            "[Desktop Entry]\nType=LookAndFeel\n",
        )

    return b


def main():
    print("[smoke] preparing test backups under:", BACKUP_ROOT)
    ensure_dir(BACKUP_ROOT)

    ts1 = time.strftime("%Y%m%d-%H%M%S")
    b1 = make_backup(ts1, with_knsv=True)
    time.sleep(1)
    ts2 = time.strftime("%Y%m%d-%H%M%S")
    b2 = make_backup(ts2, with_knsv=False)

    # latest points to ts2 content (copy)
    latest = BACKUP_ROOT / "latest"
    if latest.exists():
        shutil.rmtree(latest, ignore_errors=True)
    shutil.copytree(b2, latest)

    print("\n[smoke] do_preview on latest")
    do_preview(target="latest")

    print("\n[smoke] do_restore_dry_run on ts1")
    do_restore_dry_run(target=ts1)

    print("\n[smoke] compare_backups ts1 vs ts2")
    compare_backups(ts1, ts2)

    # Only run import-bundle test if konsave is available
    if konsave_available():
        print("\n[smoke] import-bundle from ts1 directory (acts like bundle)")
        restore_import_bundle(b1, yes_extra_config=False, yes_extra_data=False)
    else:
        print("\n[smoke] Skipping import-bundle test (konsave not available)")

    # Test verify_backup with a properly constructed .knsv
    print("\n[smoke] Testing verify_backup with valid .knsv")
    ts_verify = time.strftime("%Y%m%d-%H%M%S")
    b_verify = make_backup_with_valid_knsv(ts_verify)
    verify_backup(target=ts_verify)

    print("\n[smoke] Testing verify_backup on 'latest'")
    verify_backup(target="latest")

    print("\n[smoke] OK")


if __name__ == "__main__":
    main()
