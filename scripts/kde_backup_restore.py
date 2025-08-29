#!/usr/bin/env python3
"""
Minimal KDE backup/restore helper using konsave + package/flatpak lists.
- Backup: exports a konsave profile (.knsv) and saves package/flatpak lists.
- Restore: imports/applies the konsave profile and prints safe install commands for packages/flatpaks.

No external Python deps; relies on shell tools: konsave, rpm/apt/pacman/zypper, flatpak.
"""
import sys
import json
import shutil
import tarfile
import zipfile
import subprocess
import platform
import re
from pathlib import Path
from datetime import datetime
import shlex
import filecmp

BACKUP_ROOT = Path.cwd() / "kde-backups"
DEFAULT_PROFILE = "kde-profile"

# --------------------- helpers ---------------------

def run(cmd, check=True, capture_output=True, text=True):
    return subprocess.run(cmd, check=check, capture_output=capture_output, text=text)


def which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# --------------------- sync helpers ---------------------

def _copy_if_changed(src: Path, dst: Path):
    """Copy file if destination missing or size/mtime differ."""
    if not dst.exists():
        ensure_dir(dst.parent)
        shutil.copy2(src, dst)
        return
    try:
        src_stat = src.stat()
        dst_stat = dst.stat()
        if src_stat.st_size != dst_stat.st_size or int(src_stat.st_mtime) != int(dst_stat.st_mtime):
            ensure_dir(dst.parent)
            shutil.copy2(src, dst)
    except OSError:
        ensure_dir(dst.parent)
        shutil.copy2(src, dst)


def _sync_tree(src_dir: Path, dst_dir: Path):
    """One-way sync: copy new/changed files from src_dir to dst_dir and remove deleted ones in dst_dir."""
    ensure_dir(dst_dir)
    desired: set[Path] = set()
    for p in src_dir.rglob("*"):
        if p.is_file():
            rel = p.relative_to(src_dir)
            dst = dst_dir / rel
            _copy_if_changed(p, dst)
            desired.add(dst)
    # Remove extraneous files in dst_dir
    for p in list(dst_dir.rglob("*")):
        if p.is_file() and p not in desired:
            try:
                p.unlink()
            except OSError:
                pass
    # Clean up empty dirs
    for d in sorted((x for x in dst_dir.rglob("*") if x.is_dir()), reverse=True):
        try:
            next(d.rglob("*")).__class__  # any content?
        except StopIteration:
            try:
                d.rmdir()
            except OSError:
                pass


def detect_pkg_manager() -> str:
    # Simple detection order by popularity
    if which("dnf"):
        return "dnf"
    if which("apt") or which("apt-get"):
        return "apt"
    if which("pacman"):
        return "pacman"
    if which("zypper"):
        return "zypper"
    # Fallback to rpm query for list only
    if which("rpm"):
        return "rpm"
    return "unknown"


def list_installed_packages(pm: str) -> list[str]:
    try:
        if pm == "dnf":
            # Use rpm to get clean names
            res = run(["rpm", "-qa", "--qf", "%{NAME}\n"])  # type: ignore
            return sorted(set(line.strip() for line in res.stdout.splitlines() if line.strip()))
        if pm == "rpm":
            res = run(["rpm", "-qa", "--qf", "%{NAME}\n"])  # type: ignore
            return sorted(set(line.strip() for line in res.stdout.splitlines() if line.strip()))
        if pm == "apt":
            if which("apt-mark"):
                res = run(["apt-mark", "showmanual"])  # user-installed
                return sorted(set(line.strip() for line in res.stdout.splitlines() if line.strip()))
            # Fallback: dpkg -l
            res = run(["dpkg", "-l"])  # noisy, but usable
            pkgs = []
            for line in res.stdout.splitlines():
                if line.startswith("ii "):
                    parts = line.split()
                    if len(parts) >= 2:
                        pkgs.append(parts[1])
            return sorted(set(pkgs))
        if pm == "pacman":
            res = run(["bash", "-lc", "pacman -Qqe | sed 's/$//'"],)  # explicit + deps
            return sorted(set(line.strip() for line in res.stdout.splitlines() if line.strip()))
        if pm == "zypper":
            # Extract package names column
            res = run(["bash", "-lc", "zypper se -i | awk 'NR>2 && $1!~/(Loading|S|#)/ {print $3}'"],)
            return sorted(set(line.strip() for line in res.stdout.splitlines() if line.strip()))
    except subprocess.CalledProcessError:
        pass
    return []


def list_flatpaks() -> list[str]:
    if not which("flatpak"):
        return []
    try:
        res = run(["flatpak", "list", "--app", "--columns=ref"])
        return sorted(set(line.strip() for line in res.stdout.splitlines() if line.strip()))
    except subprocess.CalledProcessError:
        return []


def write_text(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------- meta/tag/scope helpers ---------------------

SCOPE_KEYS = {"konsave", "packages", "flatpak", "extra_config", "extra_data"}


def parse_scope(scope_str: str | None) -> set[str] | None:
    if not scope_str:
        return None
    parts = {p.strip() for p in scope_str.split(",") if p.strip()}
    invalid = parts - SCOPE_KEYS
    if invalid:
        print(f"[!] Geçersiz scope anahtarları: {', '.join(sorted(invalid))}\n    Geçerli: {', '.join(sorted(SCOPE_KEYS))}")
        parts = parts & SCOPE_KEYS
    return parts


def effective_scope(meta: dict, override: set[str] | None) -> set[str]:
    if override:
        return override
    m = meta.get("scope") or {}
    enabled = {k for k, v in m.items() if v}
    return enabled if enabled else set(SCOPE_KEYS)


def load_meta(backup_dir: Path) -> dict:
    meta_p = backup_dir / "meta.json"
    if meta_p.exists():
        try:
            return json.loads(read_text(meta_p))
        except (json.JSONDecodeError, OSError, ValueError):
            return {}
    return {}


def find_backup_by_tag(tag: str) -> Path | None:
    if not BACKUP_ROOT.exists():
        return None
    candidates = []
    for p in sorted([x for x in BACKUP_ROOT.iterdir() if x.is_dir()]):
        meta = load_meta(p)
        tags = [t.lower() for t in meta.get("tags", [])]
        if tag.lower() in tags:
            candidates.append(p)
    return candidates[-1] if candidates else None


def _find_knsv(backup_dir: Path) -> Path | None:
    files = sorted(backup_dir.glob("*.knsv"))
    return files[-1] if files else None


# --------------------- konsave ops ---------------------

def check_konsave():
    if not which("konsave"):
        print("[!] konsave bulunamadı. Kurulum: python -m pip install konsave", file=sys.stderr)
        return False
    return True


KONSAVE = "konsave"
KONSAVE_EXTRA_ARGS: list[str] = []  # filled by --konsave-args


def konsave_save_and_export(profile: str, backup_dir: Path, archive_name: str = DEFAULT_PROFILE) -> Path:
    # Save profile (overwrite allowed)
    cmd_save = [KONSAVE, "save", profile]
    if KONSAVE_EXTRA_ARGS:
        cmd_save += KONSAVE_EXTRA_ARGS
    run(cmd_save)
    export_path = backup_dir / f"{archive_name}.knsv"
    cmd_export = [KONSAVE, "export", "-n", str(export_path)]
    if KONSAVE_EXTRA_ARGS:
        cmd_export += KONSAVE_EXTRA_ARGS
    run(cmd_export)
    return export_path


def konsave_import_and_apply(knsv_path: Path, profile: str):
    run(["konsave", "-i", str(knsv_path)], check=True)
    run(["konsave", "-a", profile], check=True)
    print("[i] Değişikliklerin tamamı için oturum kapat/aç gerekebilir.")


# --------------------- backup / restore ---------------------

def do_backup(tags: list[str] | None = None, scope_override: set[str] | None = None):
    if not check_konsave():
        return

    ensure_dir(BACKUP_ROOT)
    ts = timestamp()
    backup_dir = BACKUP_ROOT / ts
    ensure_dir(backup_dir)

    profile = input(f"Profil adı (Enter={DEFAULT_PROFILE}): ") or DEFAULT_PROFILE

    print("[i] KDE ayarları export ediliyor (konsave)...")
    knsv = konsave_save_and_export(profile, backup_dir, archive_name=profile)

    print("[i] Paket listesi alınıyor...")
    pm = detect_pkg_manager()
    pkgs = list_installed_packages(pm)
    write_text(backup_dir / "packages.txt", "\n".join(pkgs) + "\n")

    print("[i] Flatpak uygulamaları listeleniyor...")
    fps = list_flatpaks()
    write_text(backup_dir / "flatpaks.txt", "\n".join(fps) + "\n")

    # Extra: kritik KDE config dosyalarını ayrıca yedekle (konsave eksikse garanti olsun)
    extra_root = backup_dir / "extra-config"
    ensure_dir(extra_root)
    home = Path.home()
    extra_targets = [
        Path(".config/plasma-org.kde.plasma.desktop-appletsrc"),
        Path(".config/kdeglobals"),
        Path(".config/kwinrc"),
    ]
    saved_extra: list[str] = []
    for rel in extra_targets:
        src = home / rel
        if src.exists():
            dst = extra_root / rel
            ensure_dir(dst.parent)
            try:
                shutil.copy2(src, dst)
                saved_extra.append(str(rel))
            except OSError:
                pass

    # Extra-data: kullanıcının önemli gördüğü veri klasörleri
    extra_data_root = backup_dir / "extra-data"
    ensure_dir(extra_data_root)
    extra_data_targets = [
        Path(".local/share/applications"),
        Path(".local/share/plasma_notes"),
        Path(".local/share/plasma-systemmonitor"),
        Path(".local/zed-preview.app"),
    ]
    saved_extra_data: list[str] = []
    for rel in extra_data_targets:
        src_dir = home / rel
        if src_dir.exists():
            # Klasör ağacını file-by-file kopyala (izinler korunarak)
            for p in src_dir.rglob("*"):
                if p.is_file():
                    dst = extra_data_root / p.relative_to(home)
                    ensure_dir(dst.parent)
                    try:
                        shutil.copy2(p, dst)
                    except OSError:
                        pass
            saved_extra_data.append(str(rel))

    # scope in meta: if override provided, persist it; else default all true
    eff_scope = scope_override or set(SCOPE_KEYS)
    meta = {
        "created": ts,
        "host": platform.node(),
        "os": platform.platform(),
        "pkg_manager": pm,
        "profile": profile,
        "tags": tags or [],
        "scope": {
            "konsave": "konsave" in eff_scope,
            "packages": "packages" in eff_scope,
            "flatpak": "flatpak" in eff_scope,
            "extra_config": "extra_config" in eff_scope,
            "extra_data": "extra_data" in eff_scope,
        },
        "files": {
            "konsave_profile": str(knsv.name),
            "packages": "packages.txt",
            "flatpaks": "flatpaks.txt",
        },
        "extra_config": saved_extra,
        "extra_data": saved_extra_data,
    }
    write_text(backup_dir / "meta.json", json.dumps(meta, indent=2, ensure_ascii=False))

    print("\n[✓] Yedek tamamlandı:")
    print(f"  Dizin: {backup_dir}")
    print(f"  Profil: {profile}")
    print("  İçerik: .knsv, packages.txt, flatpaks.txt, meta.json")


def do_restore(selected_backup: Path | None = None, scope_override: set[str] | None = None, tag: str | None = None, timestamp_hint: str | None = None,
               yes_extra_config: bool | None = None, yes_extra_data: bool | None = None):
    """Restore flow respecting scope and selection by tag/timestamp.
    - selected_backup: direct path to backup dir
    - tag: if provided, pick latest backup with this tag
    - timestamp_hint: prefix or 'latest'
    - scope_override: set of scope keys overriding meta
    """
    # Resolve backup dir
    backup_dir: Path | None = selected_backup
    if backup_dir is None:
        if tag:
            backup_dir = find_backup_by_tag(tag)
        elif timestamp_hint == "latest":
            backup_dir = BACKUP_ROOT / "latest"
        elif timestamp_hint:
            cands = sorted([p for p in BACKUP_ROOT.iterdir() if p.is_dir() and p.name.startswith(timestamp_hint)])
            backup_dir = cands[-1] if cands else None
        else:
            backup_dir = pick_backup_dir()
    if not backup_dir or not backup_dir.exists():
        print("[!] Restore için yedek bulunamadı.")
        return

    print(f"[i] Restore kaynağı: {backup_dir}")
    meta = load_meta(backup_dir)
    scope = effective_scope(meta, scope_override)

    # Konsave import/apply
    if "konsave" in scope:
        knsv = _find_knsv(backup_dir)
        if not knsv:
            print("[!] .knsv bulunamadı. Konsave kısmı atlandı.")
        else:
            profile = meta.get("profile") or DEFAULT_PROFILE
            print("[i] Konsave profili içe aktarılıyor ve uygulanıyor...")
            konsave_import_and_apply(knsv, profile)
    else:
        print("[i] Scope gereği konsave uygulanmıyor.")

    # Packages commands (print only)
    if "packages" in scope:
        pm = detect_pkg_manager()
        desired = set(_list_lines(backup_dir / "packages.txt"))
        if desired:
            current = set(list_installed_packages(pm))
            to_install = sorted(desired - current)
            if to_install:
                if pm == "dnf" or pm == "rpm":
                    print("\n[Pkg] Kurulum komutu (örnek):")
                    print("sudo dnf install -y ", " ".join(shlex.quote(x) for x in to_install))
                elif pm == "apt":
                    print("\n[Pkg] Kurulum komutu (örnek):")
                    print("sudo apt install -y ", " ".join(shlex.quote(x) for x in to_install))
                elif pm == "pacman":
                    print("\n[Pkg] Kurulum komutu (örnek):")
                    print("sudo pacman -S --needed ", " ".join(shlex.quote(x) for x in to_install))
                elif pm == "zypper":
                    print("\n[Pkg] Kurulum komutu (örnek):")
                    print("sudo zypper install -y ", " ".join(shlex.quote(x) for x in to_install))
    else:
        print("[i] Scope gereği paket adımı atlandı.")

    # Flatpak commands (print only)
    if "flatpak" in scope:
        desired_fp = set(_list_lines(backup_dir / "flatpaks.txt"))
        if desired_fp:
            current_fp = set(list_flatpaks())
            to_install_fp = sorted(desired_fp - current_fp)
            if to_install_fp:
                print("\n[Flatpak] Kurulum komutu (örnek):")
                print("flatpak install -y --noninteractive ", " ".join(shlex.quote(x) for x in to_install_fp))
    else:
        print("[i] Scope gereği flatpak adımı atlandı.")

    # Extra-config copy
    extra_root = backup_dir / "extra-config"
    if extra_root.exists() and "extra_config" in scope:
        if yes_extra_config is None:
            ans = input("\nEk KDE config dosyalarını (extra-config) yerine kopyalayayım mı? (E/h): ").strip().lower()
            do_copy = ans in {"e", "evet", "y", "yes"}
        else:
            do_copy = yes_extra_config
        if do_copy:
            base = Path.home()
            for p in sorted(extra_root.rglob("*")):
                if p.is_file():
                    rel = p.relative_to(extra_root)
                    dest = base / rel
                    ensure_dir(dest.parent)
                    try:
                        shutil.copy2(p, dest)
                    except OSError as e:
                        print(f"[!] Kopyalanamadı: {p} -> {dest}: {e}")
    elif extra_root.exists():
        print("[i] Scope gereği extra-config kopyalanmıyor.")

    # Extra-data copy
    extra_data_root = backup_dir / "extra-data"
    if extra_data_root.exists() and "extra_data" in scope:
        if yes_extra_data is None:
            ans = input("Ek veri klasörlerini (extra-data) yerine kopyalayayım mı? (E/h): ").strip().lower()
            do_copy = ans in {"e", "evet", "y", "yes"}
        else:
            do_copy = yes_extra_data
        if do_copy:
            base = Path.home()
            for p in sorted(extra_data_root.rglob("*")):
                if p.is_file():
                    rel = p.relative_to(extra_data_root)
                    dest = base / rel
                    ensure_dir(dest.parent)
                    try:
                        shutil.copy2(p, dest)
                    except OSError as e:
                        print(f"[!] Kopyalanamadı: {p} -> {dest}: {e}")
    elif extra_data_root.exists():
        print("[i] Scope gereği extra-data kopyalanmıyor.")

    print("\n[✓] Restore tamamlandı (paket/flatpak komutları yalnızca gösterildi).")


def do_quick_backup():
    """Incremental sync of extra-config and extra-data into kde-backups/latest.
    Optionally export konsave as well (skipped by default for speed)."""
    latest_dir = BACKUP_ROOT / "latest"
    ensure_dir(latest_dir)

    home = Path.home()
    # extra-config files
    extra_cfg = [
        Path(".config/plasma-org.kde.plasma.desktop-appletsrc"),
        Path(".config/kdeglobals"),
        Path(".config/kwinrc"),
    ]
    dst_cfg_root = latest_dir / "extra-config"
    ensure_dir(dst_cfg_root)
    desired_cfg: set[Path] = set()
    for rel in extra_cfg:
        src = home / rel
        dst = dst_cfg_root / rel
        if src.exists():
            _copy_if_changed(src, dst)
            desired_cfg.add(dst)
    # remove files in extra-config not desired anymore
    for p in list(dst_cfg_root.rglob("*")):
        if p.is_file() and p not in desired_cfg:
            try:
                p.unlink()
            except OSError:
                pass

    # extra-data directories
    extra_data_dirs = [
        Path(".local/share/applications"),
        Path(".local/share/plasma_notes"),
        Path(".local/share/plasma-systemmonitor"),
        Path(".local/zed-preview.app"),
    ]
    dst_data_root = latest_dir / "extra-data"
    ensure_dir(dst_data_root)
    for rel in extra_data_dirs:
        src_dir = home / rel
        dst_dir = dst_data_root / rel
        if src_dir.exists():
            _sync_tree(src_dir, dst_dir)
        else:
            # Source missing -> ensure dest removed
            if dst_dir.exists():
                # Remove directory tree safely
                for p in sorted(dst_dir.rglob("*"), reverse=True):
                    try:
                        p.unlink() if p.is_file() else p.rmdir()
                    except OSError:
                        pass
                try:
                    dst_dir.rmdir()
                except OSError:
                    pass

    # meta.json
    ts = timestamp()
    meta = {
        "created": ts,
        "host": platform.node(),
        "os": platform.platform(),
        "profile": "quick",
        "notes": "Incremental sync: extra-config and extra-data into latest/",
    }
    write_text(latest_dir / "meta.json", json.dumps(meta, indent=2, ensure_ascii=False))

    # optional konsave export
    if check_konsave():
        ans = input("Konsave export da yapılsın mı? (varsayılan: h) (E/h): ").strip().lower()
        if ans in {"e", "evet", "y", "yes"}:
            profile = input(f"Profil adı (Enter={DEFAULT_PROFILE}): ") or DEFAULT_PROFILE
            print("[i] KDE ayarları export ediliyor (konsave, hızlı)...")
            konsave_save_and_export(profile, latest_dir, archive_name=profile)
            # not touching packages/flatpaks in quick mode for speed
    print("\n[✓] Quick Backup tamamlandı: kde-backups/latest/")


def _list_lines(p: Path) -> list[str]:
    if not p.exists():
        return []
    return [x.strip() for x in p.read_text().splitlines() if x.strip()]


def _diff_sets(desired: set[str], current: set[str]) -> tuple[set[str], set[str]]:
    to_install = desired - current
    missing = desired - current
    to_remove = current - desired
    return to_install, to_remove


def do_preview(target: str | None = None, scope_override: set[str] | None = None, tag: str | None = None):
    """Show what would change if restore is run for the selected backup.
    target: 'latest' or a timestamp prefix (e.g., 20250829-151354)."""
    # Resolve backup dir
    if target is None and not tag:
        backup_dir = pick_backup_dir()
    else:
        if target == "latest":
            backup_dir = BACKUP_ROOT / "latest"
        else:
            backup_dir = None
            if tag:
                backup_dir = find_backup_by_tag(tag)
            elif target:
                cands = sorted([p for p in BACKUP_ROOT.iterdir() if p.is_dir() and p.name.startswith(target)])
                backup_dir = cands[-1] if cands else None
    if not backup_dir or not backup_dir.exists():
        print("[!] Önizleme için yedek bulunamadı.")
        return

    print(f"[i] Önizleme için yedek: {backup_dir}")
    meta = load_meta(backup_dir)
    scope = effective_scope(meta, scope_override)

    # Packages diff (scope)
    pkg_file = backup_dir / "packages.txt"
    desired_pkgs = set(_list_lines(pkg_file))
    current_pkgs = set(list_installed_packages(detect_pkg_manager())) if desired_pkgs and ("packages" in scope) else set()
    to_install = desired_pkgs - current_pkgs
    to_remove = current_pkgs - desired_pkgs if desired_pkgs else set()

    # Flatpaks diff (scope)
    fp_file = backup_dir / "flatpaks.txt"
    desired_fp = set(_list_lines(fp_file))
    current_fp = set(list_flatpaks()) if desired_fp and ("flatpak" in scope) else set()
    fp_install = desired_fp - current_fp
    fp_remove = current_fp - desired_fp if desired_fp else set()

    # extra-config
    base = Path.home()
    xc_root = backup_dir / "extra-config"
    xc_new: list[Path] = []
    xc_change: list[Path] = []
    if xc_root.exists():
        for f in sorted(xc_root.rglob("*")):
            if f.is_file():
                rel = f.relative_to(xc_root)
                dest = base / rel
                if not dest.exists():
                    xc_new.append(rel)
                else:
                    same = filecmp.cmp(f, dest, shallow=False)
                    if not same:
                        xc_change.append(rel)

    # extra-data
    xd_root = backup_dir / "extra-data"
    xd_new: list[Path] = []
    xd_change: list[Path] = []
    if xd_root.exists():
        for f in sorted(xd_root.rglob("*")):
            if f.is_file():
                rel = f.relative_to(xd_root)
                dest = base / rel
                if not dest.exists():
                    xd_new.append(rel)
                else:
                    same = filecmp.cmp(f, dest, shallow=False)
                    if not same:
                        xd_change.append(rel)

    # .knsv summary
    knsv = _find_knsv(backup_dir)

    def _sample(items: list, n: int = 8):
        return [str(x) for x in items[:n]]

    print("\n[Preview]")
    # Konsave
    if knsv and ("konsave" in scope):
        print(f"  • Konsave profili uygulanacak: {knsv.name}")
    else:
        print("  • Konsave uygulanmayacak veya profil yok.")
    # Packages
    if desired_pkgs and ("packages" in scope):
        print(f"  • Paketler: kurulacak {len(to_install)}, (isteğe bağlı) kaldırılabilir {len(to_remove)}")
        if to_install:
            print("    Örnek (install):", ", ".join(sorted(list(to_install))[:8]))
    # Flatpaks
    if desired_fp and ("flatpak" in scope):
        print(f"  • Flatpak: kurulacak {len(fp_install)}, (isteğe bağlı) kaldırılabilir {len(fp_remove)}")
        if fp_install:
            print("    Örnek (install):", ", ".join(sorted(list(fp_install))[:8]))
    # Extra-config
    if xc_root.exists() and ("extra_config" in scope):
        print(f"  • extra-config: yeni {len(xc_new)}, üzerine yazılacak {len(xc_change)} (silme yapılmaz)")
        for s in _sample(xc_new):
            print(f"    + {s}")
        for s in _sample(xc_change):
            print(f"    ~ {s}")
    # Extra-data
    if xd_root.exists() and ("extra_data" in scope):
        print(f"  • extra-data: yeni {len(xd_new)}, üzerine yazılacak {len(xd_change)} (silme yapılmaz)")
        for s in _sample(xd_new):
            print(f"    + {s}")
        for s in _sample(xd_change):
            print(f"    ~ {s}")
    print("\nNot: Restore, extra-* için dosya KOPYALAR; mevcut fazladan dosyaları silmez.")


def _human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    s = float(n)
    for u in units:
        if s < 1024.0:
            return f"{s:.1f} {u}"
        s /= 1024.0
    return f"{s:.1f} PB"


def _estimate_pkg_sizes(pm: str, packages: list[str], sample: int = 12) -> tuple[int, int]:
    """Best-effort rough size estimate (bytes) using package manager info for a small sample.
    Returns (sample_total, estimated_total) where estimated extrapolates to full set.
    If not available, returns (0, 0)."""
    pkgs = packages[:sample]
    if not pkgs:
        return 0, 0
    total = 0
    def parse_size(out: str) -> int:
        # Try to find numeric bytes in output lines like "Size : 12 M" or "Installed-Size: 3456 kB"
        m = re.search(r"(Installed-Size|Size)\s*[:=]?\s*([0-9]+)\s*(kB|KB|MB|GB)?", out, re.IGNORECASE)
        if not m:
            return 0
        val = int(m.group(2))
        unit = (m.group(3) or "B").upper()
        if unit in {"KB", "KB"}:
            return val * 1024
        if unit == "MB":
            return val * 1024 * 1024
        if unit == "GB":
            return val * 1024 * 1024 * 1024
        # Some managers report in kB textually lowercase
        if unit == "KB":
            return val * 1024
        return val
    try:
        for p in pkgs:
            if pm in {"dnf", "rpm"}:
                r = run(["bash", "-lc", f"dnf info {shlex.quote(p)} 2>/dev/null || rpm -qi {shlex.quote(p)} 2>/dev/null"], check=False)
                total += parse_size(r.stdout)
            elif pm == "apt":
                r = run(["bash", "-lc", f"apt show {shlex.quote(p)} 2>/dev/null || apt-cache show {shlex.quote(p)} 2>/dev/null"], check=False)
                total += parse_size(r.stdout)
            elif pm == "pacman":
                r = run(["bash", "-lc", f"pacman -Si {shlex.quote(p)} 2>/dev/null"], check=False)
                total += parse_size(r.stdout)
            elif pm == "zypper":
                r = run(["bash", "-lc", f"zypper info {shlex.quote(p)} 2>/dev/null"], check=False)
                total += parse_size(r.stdout)
    except (subprocess.CalledProcessError, OSError, ValueError):
        return 0, 0
    est = int(total * (len(packages) / max(1, len(pkgs))))
    return total, est


def do_restore_dry_run(target: str | None = None, scope_override: set[str] | None = None, tag: str | None = None):
    """Simulate restore actions with rsync-like output and rough size estimates."""
    # Reuse preview to compute diffs
    # Resolve backup dir
    if target is None and not tag:
        backup_dir = pick_backup_dir()
    else:
        if target == "latest":
            backup_dir = BACKUP_ROOT / "latest"
        else:
            backup_dir = None
            if tag:
                backup_dir = find_backup_by_tag(tag)
            elif target:
                cands = sorted([p for p in BACKUP_ROOT.iterdir() if p.is_dir() and p.name.startswith(target)])
                backup_dir = cands[-1] if cands else None
    if not backup_dir or not backup_dir.exists():
        print("[!] Dry-run için yedek bulunamadı.")
        return

    print(f"[i] Dry-run için yedek: {backup_dir}")
    meta = load_meta(backup_dir)
    scope = effective_scope(meta, scope_override)

    # Konsave
    knsv = _find_knsv(backup_dir)
    if "konsave" in scope:
        if knsv:
            print(f"[DRY] konsave -i {knsv.name} && konsave -a {meta.get('profile') or DEFAULT_PROFILE}")
        else:
            print("[DRY] .knsv yok -> konsave adımı atlanır")

    # Packages
    if "packages" in scope:
        pm = detect_pkg_manager()
        desired = set(_list_lines(backup_dir / "packages.txt"))
        current = set(list_installed_packages(pm)) if desired else set()
        to_install = sorted(desired - current)
        if to_install:
            sample, est = _estimate_pkg_sizes(pm, to_install)
            note = f" (tahmini boyut ~{_human_size(est)})" if est else ""
            print(f"[DRY] Paket kurulumu: {len(to_install)} paket{note}")
            if pm in {"dnf", "rpm"}:
                print("      sudo dnf install -y ", " ".join(shlex.quote(x) for x in to_install[:15]), (" ..." if len(to_install) > 15 else ""))
            elif pm == "apt":
                print("      sudo apt install -y ", " ".join(shlex.quote(x) for x in to_install[:15]), (" ..." if len(to_install) > 15 else ""))
            elif pm == "pacman":
                print("      sudo pacman -S --needed ", " ".join(shlex.quote(x) for x in to_install[:15]), (" ..." if len(to_install) > 15 else ""))
            elif pm == "zypper":
                print("      sudo zypper install -y ", " ".join(shlex.quote(x) for x in to_install[:15]), (" ..." if len(to_install) > 15 else ""))

    # Flatpaks
    if "flatpak" in scope:
        desired_fp = set(_list_lines(backup_dir / "flatpaks.txt"))
        current_fp = set(list_flatpaks()) if desired_fp else set()
        to_install_fp = sorted(desired_fp - current_fp)
        if to_install_fp:
            print(f"[DRY] Flatpak kurulumu: {len(to_install_fp)} uygulama (boyut değişken, flathub'a bağlı)")
            print("      flatpak install -y --noninteractive ", " ".join(shlex.quote(x) for x in to_install_fp[:15]), (" ..." if len(to_install_fp) > 15 else ""))

    # Extra-* rsync-like
    home = Path.home()
    for label, sub, enabled in (("extra-config", "extra-config", "extra_config" in scope), ("extra-data", "extra-data", "extra_data" in scope)):
        root = backup_dir / sub
        if root.exists() and enabled:
            print(f"[DRY] rsync --dry-run {sub}/ -> ~/")
            for f in sorted(root.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(root)
                    dest = home / rel
                    sign = "+" if not dest.exists() else ("~" if not filecmp.cmp(f, dest, shallow=False) else "=")
                    if sign != "=":
                        try:
                            sz = f.stat().st_size
                        except OSError:
                            sz = 0
                        print(f"      {sign} {rel} ({_human_size(sz)})")


def pick_backup_dir() -> Path | None:
    if not BACKUP_ROOT.exists():
        print("[!] Yedek dizini bulunamadı:", BACKUP_ROOT)
        return None
    entries = sorted([p for p in BACKUP_ROOT.iterdir() if p.is_dir()])
    if not entries:
        print("[!] Hiç yedek bulunamadı.")
        return None
    print("Mevcut yedekler:")
    for i, p in enumerate(entries, 1):
        print(f"  {i}) {p.name}")
    choice = input(f"Seçim (1-{len(entries)}) veya boş bırak=son: ").strip()
    if not choice:
        return entries[-1]
    try:
        idx = int(choice)
        if 1 <= idx <= len(entries):
            return entries[idx - 1]
    except ValueError:
        pass
    print("[!] Geçersiz seçim.")
    return None

def verify_backup(target: str | None = None, tag: str | None = None):
    """Inspect .knsv contents and report presence of core KDE items."""
    # Resolve backup dir
    if target is None and not tag:
        backup_dir = pick_backup_dir()
    else:
        if target == "latest":
            backup_dir = BACKUP_ROOT / "latest"
        else:
            backup_dir = None
            if tag:
                backup_dir = find_backup_by_tag(tag)
            elif target:
                cands = sorted([p for p in BACKUP_ROOT.iterdir() if p.is_dir() and p.name.startswith(target)])
                backup_dir = cands[-1] if cands else None
    if not backup_dir or not backup_dir.exists():
        print("[!] Verify için yedek bulunamadı.")
        return

    knsv = _find_knsv(backup_dir)
    if not knsv:
        print("[!] .knsv bulunamadı.")
        return

    wanted_files_suffix = [
        ".config/plasma-org.kde.plasma.desktop-appletsrc",
        ".config/kdeglobals",
        ".config/kwinrc",
    ]
    wanted_dirs_prefix = [
        ".local/share/plasma/plasmoids/",
        ".local/share/plasma/look-and-feel",
        ".local/share/icons",
        ".local/share/color-schemes",
        ".local/share/aurorae",
        ".local/share/konsole",
    ]
    colorizer_hints = [r"colorizer", r"panel.*color", r"Colorizer"]

    found_files = {s: False for s in wanted_files_suffix}
    found_dirs = {p: False for p in wanted_dirs_prefix}
    found_colorizer = False
    sample_hits: list[str] = []

    try:
        names: list[str] = []
        if tarfile.is_tarfile(knsv):
            with tarfile.open(knsv, "r:*") as tf:
                names = tf.getnames()
        elif zipfile.is_zipfile(knsv):
            with zipfile.ZipFile(knsv, "r") as zf:
                names = zf.namelist()
        else:
            print("[!] Arşiv biçimi tanınmadı (ne tar ne zip).")
            return

        def normalize(path: str) -> str:
            path = re.sub(r"^export/config_folder/", ".config/", path)
            path = re.sub(r"^export/share_folder/", ".local/share/", path)
            path = re.sub(r"^home/[^/]+/", "", path)
            return path

        for name in names:
            n = normalize(name)
            for suf in wanted_files_suffix:
                if n.endswith(suf):
                    found_files[suf] = True
            for pref in wanted_dirs_prefix:
                if n.startswith(pref):
                    found_dirs[pref] = True
            if not found_colorizer:
                for hint in colorizer_hints:
                    if re.search(hint, name, flags=re.IGNORECASE):
                        found_colorizer = True
                        if len(sample_hits) < 10:
                            sample_hits.append(name)
                        break
    except (tarfile.TarError, zipfile.BadZipFile, OSError) as e:
        print(f"[!] Arşiv okunamadı: {e}")
        return

    print("\n[Verify]")
    def ok(b: bool) -> str:
        return "✓" if b else "✗"
    print(f"  {ok(found_files[wanted_files_suffix[0]])} Panel yerleşimi: ~/.config/plasma-org.kde.plasma.desktop-appletsrc")
    print(f"  {ok(found_files[wanted_files_suffix[1]])} Genel KDE: ~/.config/kdeglobals")
    print(f"  {ok(found_files[wanted_files_suffix[2]])} KWin: ~/.config/kwinrc")
    print(f"  {ok(found_dirs[wanted_dirs_prefix[0]])} Plasmoid dizinleri: ~/.local/share/plasma/plasmoids/")
    print(f"  {ok(found_dirs[wanted_dirs_prefix[1]])} Look-and-feel: ~/.local/share/plasma/look-and-feel/")
    print(f"  {ok(found_dirs[wanted_dirs_prefix[2]])} Icon themes: ~/.local/share/icons/")
    print(f"  {ok(found_dirs[wanted_dirs_prefix[3]])} Color schemes: ~/.local/share/color-schemes/")
    print(f"  {ok(found_dirs[wanted_dirs_prefix[4]])} Aurorae: ~/.local/share/aurorae/")
    print(f"  {ok(found_dirs[wanted_dirs_prefix[5]])} Konsole profilleri: ~/.local/share/konsole/")
    print(f"  {ok(found_colorizer)} Panel Colorizer ile ilişkili girdiler")


def _resolve_backup_selector(sel: str | None, tag: str | None) -> Path | None:
    if sel is None and not tag:
        return pick_backup_dir()
    if sel == "latest":
        return BACKUP_ROOT / "latest"
    b: Path | None = None
    if tag:
        b = find_backup_by_tag(tag)
    elif sel:
        cands = sorted([p for p in BACKUP_ROOT.iterdir() if p.is_dir() and p.name.startswith(sel)])
        b = cands[-1] if cands else None
    return b


def compare_backups(a: str, b: str):
    """Compare two backups by timestamp prefix or tag.
    Accepts values like 'latest', timestamp prefix, or 'tag:<name>'."""
    def resolve(x: str) -> Path | None:
        if x == "latest":
            return BACKUP_ROOT / "latest"
        if x.startswith("tag:"):
            return find_backup_by_tag(x.split(":", 1)[1])
        cands = sorted([p for p in BACKUP_ROOT.iterdir() if p.is_dir() and p.name.startswith(x)])
        return cands[-1] if cands else None

    a_dir = resolve(a)
    b_dir = resolve(b)
    if not a_dir or not a_dir.exists() or not b_dir or not b_dir.exists():
        print("[!] Karşılaştırma için yedek(ler) bulunamadı.")
        return

    print(f"[i] Karşılaştırılıyor: {a_dir.name}  vs  {b_dir.name}")
    # Packages
    a_pkgs = set(_list_lines(a_dir / "packages.txt"))
    b_pkgs = set(_list_lines(b_dir / "packages.txt"))
    add_pkgs = sorted(b_pkgs - a_pkgs)
    rm_pkgs = sorted(a_pkgs - b_pkgs)
    # Flatpaks
    a_fp = set(_list_lines(a_dir / "flatpaks.txt"))
    b_fp = set(_list_lines(b_dir / "flatpaks.txt"))
    add_fp = sorted(b_fp - a_fp)
    rm_fp = sorted(a_fp - b_fp)
    # Konsave archive contents (names only)
    def list_archive_names(p: Path) -> set[str]:
        k = _find_knsv(p)
        names: set[str] = set()
        if not k:
            return names
        try:
            if tarfile.is_tarfile(k):
                with tarfile.open(k, "r:*") as tf:
                    names = set(tf.getnames())
            elif zipfile.is_zipfile(k):
                with zipfile.ZipFile(k, "r") as zf:
                    names = set(zf.namelist())
        except Exception:
            pass
        return names
    a_kn = list_archive_names(a_dir)
    b_kn = list_archive_names(b_dir)
    add_kn = sorted(b_kn - a_kn)[:20]
    rm_kn = sorted(a_kn - b_kn)[:20]
    # Extra dirs
    def scan_files(root: Path) -> set[str]:
        out: set[str] = set()
        if root.exists():
            for f in root.rglob("*"):
                if f.is_file():
                    out.add(str(f.relative_to(root)))
        return out
    a_xc = scan_files(a_dir / "extra-config")
    b_xc = scan_files(b_dir / "extra-config")
    add_xc = sorted(b_xc - a_xc)[:20]
    rm_xc = sorted(a_xc - b_xc)[:20]
    a_xd = scan_files(a_dir / "extra-data")
    b_xd = scan_files(b_dir / "extra-data")
    add_xd = sorted(b_xd - a_xd)[:20]
    rm_xd = sorted(a_xd - b_xd)[:20]

    print("\n[Compare]")
    print(f"  • Packages: +{len(add_pkgs)}, -{len(rm_pkgs)}")
    if add_pkgs:
        print("    + ", ", ".join(add_pkgs[:15]), (" ..." if len(add_pkgs) > 15 else ""))
    if rm_pkgs:
        print("    - ", ", ".join(rm_pkgs[:15]), (" ..." if len(rm_pkgs) > 15 else ""))
    print(f"  • Flatpaks: +{len(add_fp)}, -{len(rm_fp)}")
    if add_fp:
        print("    + ", ", ".join(add_fp[:15]), (" ..." if len(add_fp) > 15 else ""))
    if rm_fp:
        print("    - ", ", ".join(rm_fp[:15]), (" ..." if len(rm_fp) > 15 else ""))
    print(f"  • Konsave archive entries: +{len(b_kn - a_kn)}, -{len(a_kn - b_kn)}")
    if add_kn:
        print("    + ", ", ".join(add_kn))
    if rm_kn:
        print("    - ", ", ".join(rm_kn))
    print(f"  • extra-config files: +{len(b_xc - a_xc)}, -{len(a_xc - b_xc)}")
    if add_xc:
        print("    + ", ", ".join(add_xc))
    if rm_xc:
        print("    - ", ", ".join(rm_xc))
    print(f"  • extra-data files: +{len(b_xd - a_xd)}, -{len(a_xd - b_xd)}")
    if add_xd:
        print("    + ", ", ".join(add_xd))
    if rm_xd:
        print("    - ", ", ".join(rm_xd))


def restore_import_bundle(bundle_path: Path, scope_override: set[str] | None = None,
                          yes_extra_config: bool | None = None, yes_extra_data: bool | None = None):
    """Apply a shared bundle directory that contains .knsv + meta.json (+ optional extra-*)"""
    if not bundle_path.exists() or not bundle_path.is_dir():
        print("[!] Geçersiz bundle yolu.")
        return
    meta = load_meta(bundle_path)
    scope = effective_scope(meta, scope_override)
    profile = meta.get("profile") or DEFAULT_PROFILE
    # konsave
    if "konsave" in scope:
        knsv = _find_knsv(bundle_path)
        if knsv:
            print("[i] Konsave bundle uygulanıyor...")
            konsave_import_and_apply(knsv, profile)
        else:
            print("[!] Bundle içinde .knsv bulunamadı.")
    # extra-*
    if (bundle_path / "extra-config").exists() and "extra_config" in scope:
        if yes_extra_config is None:
            ans = input("Bundle extra-config kopyalansın mı? (E/h): ").strip().lower()
            do_copy = ans in {"e", "evet", "y", "yes"}
        else:
            do_copy = yes_extra_config
        if do_copy:
            for p in (bundle_path / "extra-config").rglob("*"):
                if p.is_file():
                    dest = Path.home() / p.relative_to(bundle_path / "extra-config")
                    ensure_dir(dest.parent)
                    try:
                        shutil.copy2(p, dest)
                    except OSError:
                        pass
    if (bundle_path / "extra-data").exists() and "extra_data" in scope:
        if yes_extra_data is None:
            ans = input("Bundle extra-data kopyalansın mı? (E/h): ").strip().lower()
            do_copy = ans in {"e", "evet", "y", "yes"}
        else:
            do_copy = yes_extra_data
        if do_copy:
            for p in (bundle_path / "extra-data").rglob("*"):
                if p.is_file():
                    dest = Path.home() / p.relative_to(bundle_path / "extra-data")
                    ensure_dir(dest.parent)
                    try:
                        shutil.copy2(p, dest)
                    except OSError:
                        pass

# --------------------- UI ---------------------

def main():
    print("\nKDE Backup/Restore (konsave + package/flatpak)")
    print("===========================================")
    while True:
        print("\nMenü:")
        print("  1) Full Backup (konsave + packages + flatpak + extra-*)")
        print("  2) Restore (konsave import/apply + opsiyonel extra-*)")
        print("  3) Quick Backup (incremental extra-*)")
        print("  4) Verify (son/ seçili yedekte .knsv içeriğini denetle)")
        print("  5) Preview (önizleme)")
        print("  6) Restore Dry-Run (simülasyon)")
        print("  7) Compare (iki yedeği karşılaştır)")
        print("  8) Import Bundle (paylaşılan profil klasörü)")
        print("  9) Çıkış")
        choice = input("Seçiminiz: ").strip()
        if choice == "1":
            try:
                do_backup()
            except subprocess.CalledProcessError as e:
                print("[!] Komut hatası:", e, file=sys.stderr)
                if e.stdout:
                    print(e.stdout)
                if e.stderr:
                    print(e.stderr, file=sys.stderr)
        elif choice == "2":
            try:
                do_restore()
            except subprocess.CalledProcessError as e:
                print("[!] Komut hatası:", e, file=sys.stderr)
                if e.stdout:
                    print(e.stdout)
                if e.stderr:
                    print(e.stderr, file=sys.stderr)
        elif choice == "3":
            do_quick_backup()
        elif choice == "4":
            verify_backup()
        elif choice == "5":
            # Preview
            sel = input("Hedef (boş=son, latest=<son>, ya da timestamp öneki): ").strip() or "latest"
            tag = None
            if sel.startswith("tag:"):
                tag = sel.split(":", 1)[1]
                sel = None
            do_preview(target=sel, tag=tag)
        elif choice == "6":
            # Dry-run
            sel = input("Hedef (boş=son, latest=<son>, ya da timestamp öneki): ").strip() or "latest"
            tag = None
            if sel.startswith("tag:"):
                tag = sel.split(":", 1)[1]
                sel = None
            do_restore_dry_run(target=sel, tag=tag)
        elif choice == "7":
            a = input("İlk yedek (latest | timestamp | tag:<isim>): ").strip() or "latest"
            b = input("İkinci yedek (latest | timestamp | tag:<isim>): ").strip() or "latest"
            compare_backups(a, b)
        elif choice == "8":
            p = input("Bundle klasörü yolu: ").strip()
            if p:
                restore_import_bundle(Path(p))
        elif choice == "9" or choice.lower() in {"q", "quit", "exit"}:
            break
        else:
            print("[!] Geçersiz seçim.")


if __name__ == "__main__":
    try:
        # Simple CLI shortcuts for automation
        args = sys.argv[1:]
        if args:
            # Parse optional --konsave-args before command for simplicity
            if "--konsave-args" in args:
                i = args.index("--konsave-args")
                if i + 1 < len(args):
                    KONSAVE_EXTRA_ARGS = shlex.split(args[i + 1])
                # remove parsed pieces
                del args[i:i+2]
            cmd = args[0].lower()
            # common optional flags
            scope_set = None
            tags_list = None
            tag_filter = None
            ts_hint = None
            # parse simple flags
            def _pop_opt(opt: str) -> str | None:
                if opt in args:
                    j = args.index(opt)
                    if j + 1 < len(args):
                        val = args[j + 1]
                        del args[j:j+2]
                        return val
                return None

            scope_val = _pop_opt("--scope")
            if scope_val:
                scope_set = parse_scope(scope_val)
            tags_val = _pop_opt("--tags")
            if tags_val:
                tags_list = [t.strip() for t in tags_val.split(",") if t.strip()]
            tag_val = _pop_opt("--tag")
            if tag_val:
                tag_filter = tag_val

            # yes flags for non-interactive extra-* copy
            yes_extra_config = None
            yes_extra_data = None
            if "--yes-extra-all" in args:
                yes_extra_config = True
                yes_extra_data = True
                args.remove("--yes-extra-all")
            if "--yes-extra-config" in args:
                yes_extra_config = True
                args.remove("--yes-extra-config")
            if "--no-extra-config" in args:
                yes_extra_config = False
                args.remove("--no-extra-config")
            if "--yes-extra-data" in args:
                yes_extra_data = True
                args.remove("--yes-extra-data")
            if "--no-extra-data" in args:
                yes_extra_data = False
                args.remove("--no-extra-data")

            # timestamp/target hint for commands that accept it
            if len(args) > 1 and not args[1].startswith("--"):
                ts_hint = args[1]

            if cmd in {"--quick", "quick"}:
                do_quick_backup()
                sys.exit(0)
            elif cmd in {"--full", "full"}:
                do_backup(tags=tags_list, scope_override=scope_set)
                sys.exit(0)
            elif cmd in {"--verify", "verify"}:
                verify_backup(target=ts_hint, tag=tag_filter)
                sys.exit(0)
            elif cmd in {"--restore", "restore"}:
                do_restore(scope_override=scope_set, tag=tag_filter, timestamp_hint=ts_hint,
                           yes_extra_config=yes_extra_config, yes_extra_data=yes_extra_data)
                sys.exit(0)
            elif cmd in {"--preview", "preview"}:
                do_preview(target=ts_hint, scope_override=scope_set, tag=tag_filter)
                sys.exit(0)
            elif cmd in {"--dry-run", "dry-run", "--restore-dry-run"}:
                do_restore_dry_run(target=ts_hint, scope_override=scope_set, tag=tag_filter)
                sys.exit(0)
            elif cmd in {"--compare", "compare"}:
                # Expect two selectors after command, support tag:<name>
                if len(args) >= 3:
                    a_sel = args[1]
                    b_sel = args[2]
                    compare_backups(a_sel, b_sel)
                else:
                    print("Kullanım: --compare <A> <B>  (ör: latest 20250822-093012 veya tag:gaming tag:workstation)")
                sys.exit(0)
            elif cmd in {"--import-bundle", "import-bundle"}:
                # Next arg must be a path
                bundle = None
                if len(args) >= 2 and not args[1].startswith("--"):
                    bundle = Path(args[1])
                if bundle is None:
                    print("Kullanım: --import-bundle <klasör>")
                else:
                    restore_import_bundle(bundle, scope_override=scope_set,
                                          yes_extra_config=yes_extra_config, yes_extra_data=yes_extra_data)
                sys.exit(0)
        # interactive menu fallback
        main()
    except KeyboardInterrupt:
        print("\n[i] İptal edildi.")
