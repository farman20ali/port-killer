#!/usr/bin/env python3
"""Unified package builder for kport.

Builds all platform installation artifacts in one command.
Each platform target can also be built independently with its
dedicated script (win_build.py, mac_build.py, rpm_build.py,
deb_publish.py, publish.py).

Usage:
    python build_packages.py --all          # Build everything for current platform
    python build_packages.py --win          # Windows .exe installer
    python build_packages.py --deb          # Debian .deb package
    python build_packages.py --rpm          # Linux .rpm package
    python build_packages.py --mac          # macOS .pkg installer
    python build_packages.py --pypi         # PyPI wheel + sdist
    python build_packages.py --snap         # Snap package (.snap)
    python build_packages.py --choco        # Chocolatey package (.nupkg)

    python build_packages.py --all --check  # Check all prerequisites
    python build_packages.py --all --dry-run

    python build_packages.py --win --rpm    # Multiple targets at once

Platform-aware defaults when --all is used:
    Windows  → --win  + --pypi
    macOS    → --mac  + --pypi
    Linux    → --deb  + --rpm + --pypi
    (other)  → --pypi only

Outputs (relative to repo root):
    dist/win/kport-<v>-setup.exe   Windows installer
    dist/mac/kport-<v>.pkg         macOS installer
    dist/deb/kport_<v>-1_all.deb   Debian package
    dist/rpm/kport-<v>-1.*.rpm     RPM package
    dist/snap/kport_<v>_*.snap     Snap package
    dist/choco/kport.<v>.nupkg     Chocolatey package
    dist/*.whl, dist/*.tar.gz       PyPI packages

Return codes:
    0  all requested targets succeeded
    1  one or more targets failed
"""

from __future__ import annotations

import argparse
import platform
import re
import subprocess
import sys
from pathlib import Path

# Configure UTF-8 encoding for standard streams on Windows/narrow consoles
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

REPO_ROOT = Path(__file__).resolve().parent

# ── helpers ──────────────────────────────────────────────────────────────────

def _c(text: str, code: str) -> str:
    if sys.stdout.isatty() and sys.platform != "win32":
        return f"\033[{code}m{text}\033[0m"
    return text

def ok(msg: str)       -> None: print(_c(f"  ✅ {msg}", "92"))
def err(msg: str)      -> None: print(_c(f"  ❌ {msg}", "91"), file=sys.stderr)
def warn(msg: str)     -> None: print(_c(f"  ⚠️  {msg}", "93"))
def info(msg: str)     -> None: print(_c(f"  ℹ️  {msg}", "96"))
def target(msg: str)   -> None: print(_c(f"\n{'─'*60}\n🎯 {msg}\n{'─'*60}", "94"))
def header(msg: str)   -> None:
    sep = "═" * 60
    print(_c(f"\n{sep}\n  {msg}\n{sep}", "95;1"))


def read_version() -> str:
    for candidate in [
        REPO_ROOT / "pyproject.toml",
        REPO_ROOT / "setup.py",
        REPO_ROOT / "src" / "kport" / "__init__.py",
    ]:
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8", errors="ignore")
            m = re.search(
                r"""(?:^version\s*=\s*["']|__version__\s*=\s*["'])([^"']+)""",
                text, re.MULTILINE,
            )
            if m:
                return m.group(1).strip()
    return "0.0.0"


def _run_script(script: str, extra_args: list[str], dry_run: bool) -> bool:
    """Invoke a sibling build script as a subprocess."""
    script_path = REPO_ROOT / script
    if not script_path.exists():
        err(f"Build script not found: {script_path}")
        return False

    cmd = [sys.executable, str(script_path)] + extra_args
    if dry_run:
        cmd.append("--dry-run")

    print(f"$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    return result.returncode == 0

# ── per-target builders ───────────────────────────────────────────────────────

def build_win(version: str, check: bool, dry_run: bool) -> bool:
    target("Windows   →  dist/win/kport-{v}-setup.exe")
    if sys.platform != "win32" and not check:
        warn("Not on Windows — PyInstaller can cross-compile but NSIS requires Windows.")
        warn("Skipping Windows build on non-Windows host.")
        warn("To force: run win_build.py --build on a Windows machine or CI runner.")
        return True  # non-fatal skip

    args = ["--check"] if check else ["--build"]
    ok_result = _run_script("win_build.py", args, dry_run)
    if ok_result and not check and not dry_run:
        matches = list((REPO_ROOT / "dist" / "win").glob("kport-*-setup.exe"))
        if matches:
            ok(f"Windows installer → {matches[-1].name}")
        else:
            warn("Installer not found in dist/win/ (NSIS may not be installed)")
    return ok_result


def build_mac(version: str, check: bool, dry_run: bool) -> bool:
    target("macOS     →  dist/mac/kport-{v}.pkg")
    if sys.platform != "darwin" and not check:
        warn("Not on macOS — pkgbuild/productbuild require macOS.")
        warn("Skipping macOS build on non-macOS host.")
        return True  # non-fatal skip

    args = ["--check"] if check else ["--build"]
    ok_result = _run_script("mac_build.py", args, dry_run)
    if ok_result and not check and not dry_run:
        matches = list((REPO_ROOT / "dist" / "mac").glob("kport-*.pkg"))
        if matches:
            ok(f"macOS installer   → {matches[-1].name}")
    return ok_result


def build_deb(version: str, check: bool, dry_run: bool) -> bool:
    target("Debian    →  dist/deb/kport_<v>-1_all.deb")
    if sys.platform == "win32" and not check:
        warn("Debian build requires Linux — skipping on Windows host.")
        return True

    if check:
        # Use deb_publish.py option 1 (check tools) in auto mode
        script_path = REPO_ROOT / "deb_publish.py"
        if not script_path.exists():
            err("deb_publish.py not found")
            return False
        result = subprocess.run(
            [sys.executable, str(script_path)],
            input="1\n", text=True, cwd=str(REPO_ROOT),
        )
        return result.returncode == 0

    # Non-interactive build: send "3\n" (just build)
    script_path = REPO_ROOT / "deb_publish.py"
    if not script_path.exists():
        err("deb_publish.py not found")
        return False

    if dry_run:
        warn("DRY RUN — would run: python deb_publish.py  [choice: 3]")
        return True

    result = subprocess.run(
        [sys.executable, str(script_path)],
        input="3\n", text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode == 0:
        matches = list((REPO_ROOT / "dist" / "deb").glob("*.deb"))
        if matches:
            ok(f"Debian package    → {matches[-1].name}")
        return True
    return False


def build_rpm(version: str, check: bool, dry_run: bool) -> bool:
    target("RPM       →  dist/rpm/kport-<v>-1.<arch>.rpm")
    if sys.platform == "win32" and not check:
        warn("RPM build requires Linux — skipping on Windows host.")
        return True

    args = ["--check"] if check else ["--build"]
    ok_result = _run_script("rpm_build.py", args, dry_run)
    if ok_result and not check and not dry_run:
        matches = list((REPO_ROOT / "dist" / "rpm").glob("*.rpm"))
        if matches:
            ok(f"RPM package       → {matches[-1].name}")
    return ok_result


def build_snap(version: str, check: bool, dry_run: bool) -> bool:
    target("Snap      →  dist/snap/kport_<v>_*.snap")
    if sys.platform == "win32" and not check:
        warn("Snap build requires Linux — skipping on Windows host.")
        return True

    args = ["--check"] if check else ["--build"]
    ok_result = _run_script("snap_build.py", args, dry_run)
    if ok_result and not check and not dry_run:
        matches = list((REPO_ROOT / "dist" / "snap").glob("*.snap"))
        if matches:
            ok(f"Snap package      → {matches[-1].name}")
    return ok_result


def build_choco(version: str, check: bool, dry_run: bool) -> bool:
    target("Chocolatey →  dist/choco/kport.<v>.nupkg")
    if sys.platform != "win32" and not check and not dry_run:
        warn("Chocolatey packaging requires Windows — skipping on non-Windows host.")
        return True

    args = ["--check"] if check else ["--build"]
    ok_result = _run_script("choco_build.py", args, dry_run)
    if ok_result and not check and not dry_run:
        matches = list((REPO_ROOT / "dist" / "choco").glob("*.nupkg"))
        if matches:
            ok(f"Chocolatey pkg    → {matches[-1].name}")
    return ok_result


def build_pypi(version: str, check: bool, dry_run: bool) -> bool:
    target("PyPI      →  dist/*.whl  dist/*.tar.gz")

    if check:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "show", "build"],
                capture_output=True, check=True,
            )
            ok("build — found")
        except subprocess.CalledProcessError:
            err("build not found. Install: pip install build")
            return False
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "show", "twine"],
                capture_output=True, check=True,
            )
            ok("twine — found")
        except subprocess.CalledProcessError:
            warn("twine not found (only needed for upload). Install: pip install twine")
        return True

    if dry_run:
        warn("DRY RUN — would run: python -m build")
        return True

    result = subprocess.run(
        [sys.executable, "-m", "build"],
        cwd=str(REPO_ROOT),
    )
    if result.returncode == 0:
        matches = list((REPO_ROOT / "dist").glob("*.whl"))
        if matches:
            ok(f"Wheel             → {matches[-1].name}")
        ok("PyPI packages built. Upload with: python publish.py")
        return True
    return False

# ── platform-aware --all resolution ──────────────────────────────────────────

def resolve_all_targets(args: argparse.Namespace) -> argparse.Namespace:
    """When --all is set, activate the targets appropriate for this platform."""
    if not args.all:
        return args

    plat = platform.system()
    info(f"Platform: {plat} — auto-selecting targets")

    if plat == "Windows":
        args.win   = True
        args.choco = True
        args.pypi  = True
        info("Auto-selected: --win --choco --pypi")
    elif plat == "Darwin":
        args.mac  = True
        args.pypi = True
        info("Auto-selected: --mac --pypi")
    elif plat == "Linux":
        args.deb  = True
        args.rpm  = True
        args.snap = True
        args.pypi = True
        info("Auto-selected: --deb --rpm --snap --pypi")
    else:
        args.pypi = True
        info("Auto-selected: --pypi (unknown platform)")

    return args

# ── summary printer ───────────────────────────────────────────────────────────

def print_summary(results: dict[str, bool | None]) -> None:
    header("Build Summary")
    for name, result in results.items():
        if result is None:
            print(f"  {'─':2} {name:12} (skipped)")
        elif result:
            ok(f"{name:12} SUCCESS")
        else:
            err(f"{name:12} FAILED")
    print()

# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    version = read_version()

    parser = argparse.ArgumentParser(
        prog="build_packages.py",
        description="Build kport installation packages for all platforms",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── Target flags ──
    tgroup = parser.add_argument_group("targets")
    tgroup.add_argument("--all",   action="store_true",
                        help="Build all targets appropriate for current platform")
    tgroup.add_argument("--win",   action="store_true",
                        help="Windows .exe installer (via PyInstaller + NSIS)")
    tgroup.add_argument("--mac",   action="store_true",
                        help="macOS .pkg installer (via PyInstaller + pkgbuild)")
    tgroup.add_argument("--deb",   action="store_true",
                        help="Debian .deb package (via deb_publish.py)")
    tgroup.add_argument("--rpm",   action="store_true",
                        help="Linux .rpm package (via rpmbuild)")
    tgroup.add_argument("--pypi",  action="store_true",
                        help="PyPI wheel + sdist (via python -m build)")
    tgroup.add_argument("--snap",  action="store_true",
                        help="Snap package (via snapcraft)")
    tgroup.add_argument("--choco", action="store_true",
                        help="Chocolatey .nupkg (wraps Windows .exe installer)")

    # ── Mode flags ──
    mgroup = parser.add_argument_group("modes")
    mgroup.add_argument("--check",   action="store_true",
                        help="Check prerequisites for selected targets (no build)")
    mgroup.add_argument("--dry-run", action="store_true",
                        help="Preview commands without executing them")
    mgroup.add_argument("--version", default=version,
                        help=f"Override version string (default: {version})")
    mgroup.add_argument("--list-outputs", action="store_true",
                        help="List all existing built artifacts in dist/")

    args = parser.parse_args()
    version = args.version

    # ── --list-outputs shortcut ──
    if args.list_outputs:
        header("Built Artifacts")
        dist = REPO_ROOT / "dist"
        found_any = False
        for pattern, label in [
            ("win/kport-*-setup.exe", "Windows installer"),
            ("mac/kport-*.pkg",       "macOS installer"),
            ("deb/*.deb",             "Debian package"),
            ("rpm/*.rpm",             "RPM package"),
            ("snap/*.snap",           "Snap package"),
            ("choco/*.nupkg",         "Chocolatey package"),
            ("*.whl",                 "Python wheel"),
            ("*.tar.gz",              "Source dist"),
        ]:
            matches = list(dist.glob(pattern))
            for f in matches:
                print(f"  {label:20} {f.relative_to(REPO_ROOT)}")
                found_any = True
        if not found_any:
            warn("No build artifacts found in dist/")
        return

    # ── Validate: at least one target ──
    any_target = any([
        args.all, args.win, args.mac, args.deb, args.rpm, args.pypi, args.snap, args.choco,
    ])
    if not any_target:
        parser.print_help()
        print()
        warn("No target selected. Use --all or specify one of: --win --mac --deb --rpm --snap --choco --pypi")
        sys.exit(0)

    # ── Resolve --all → individual flags ──
    args = resolve_all_targets(args)

    header(f"🚀 kport Package Builder  v{version}")

    if args.dry_run:
        warn("DRY RUN mode — no files will be written")
    if args.check:
        info("CHECK mode — verifying prerequisites only")

    results: dict[str, bool | None] = {}

    if args.win:
        results["Windows (.exe)"] = build_win(version, args.check, args.dry_run)

    if args.mac:
        results["macOS (.pkg)"]   = build_mac(version, args.check, args.dry_run)

    if args.deb:
        results["Debian (.deb)"]  = build_deb(version, args.check, args.dry_run)

    if args.rpm:
        results["Linux (.rpm)"]   = build_rpm(version, args.check, args.dry_run)

    if args.snap:
        results["Snap (.snap)"]   = build_snap(version, args.check, args.dry_run)

    if args.choco:
        results["Chocolatey"]     = build_choco(version, args.check, args.dry_run)

    if args.pypi:
        results["PyPI (.whl)"]    = build_pypi(version, args.check, args.dry_run)

    print_summary(results)

    failed = [name for name, r in results.items() if r is False]
    if failed:
        err(f"Failed targets: {', '.join(failed)}")
        sys.exit(1)

    if not args.check and not args.dry_run:
        ok("All requested packages built successfully.")
        info("Run with --list-outputs to see all artifacts in dist/")

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled")
        sys.exit(0)
