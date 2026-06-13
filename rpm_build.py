#!/usr/bin/env python3
"""RPM package builder for kport.

Builds a .rpm package for RHEL/Fedora/CentOS/openSUSE using rpmbuild.
The spec file is generated from packaging/linux/kport.spec.template.

Usage (interactive):
    python rpm_build.py

Usage (automated / CI):
    python rpm_build.py --build       # build .rpm
    python rpm_build.py --check       # check prerequisites only
    python rpm_build.py --dry-run     # preview without executing

Output:
    dist/rpm/kport-<version>-1.<arch>.rpm
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Configure UTF-8 encoding for standard streams on Windows/narrow consoles
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

REPO_ROOT     = Path(__file__).resolve().parent
DIST_RPM      = REPO_ROOT / "dist" / "rpm"
SPEC_TEMPLATE = REPO_ROOT / "packaging" / "linux" / "kport.spec.template"

# ── helpers ──────────────────────────────────────────────────────────────────

def _c(text: str, code: str) -> str:
    if sys.stdout.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text

def ok(msg: str)     -> None: print(_c(f"✅ {msg}", "92"))
def err(msg: str)    -> None: print(_c(f"❌ {msg}", "91"), file=sys.stderr)
def warn(msg: str)   -> None: print(_c(f"⚠️  {msg}", "93"))
def step(msg: str)   -> None: print(_c(f"\n▶ {msg}", "96"))
def header(msg: str) -> None:
    sep = "=" * 60
    print(_c(f"\n{sep}\n{msg}\n{sep}", "95"))


def run(cmd: list[str], description: str, dry_run: bool = False,
        cwd: Path | None = None) -> bool:
    step(description)
    print("$", " ".join(str(c) for c in cmd))
    if dry_run:
        warn("DRY RUN — skipping")
        return True
    result = subprocess.run(cmd, cwd=str(cwd or REPO_ROOT))
    if result.returncode != 0:
        err(f"Failed: {description}")
        return False
    ok(description)
    return True


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


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


def _rpmdate() -> str:
    return datetime.now(timezone.utc).strftime("%a %b %d %Y")

# ── checks ───────────────────────────────────────────────────────────────────

def check_prerequisites() -> dict[str, bool]:
    return {
        "rpmbuild": command_exists("rpmbuild"),
        "python3":  command_exists("python3") or command_exists("python"),
    }


def print_check_results(checks: dict[str, bool]) -> bool:
    header("Prerequisites Check")
    all_ok = True
    for tool, present in checks.items():
        if present:
            ok(f"{tool} — found")
        else:
            err(f"{tool} — NOT found")
            all_ok = False

    if not checks["rpmbuild"]:
        print("\nInstall rpmbuild:")
        print("  # Fedora/RHEL/CentOS:")
        print("  sudo dnf install rpm-build python3-devel")
        print("  # openSUSE:")
        print("  sudo zypper install rpm-build")
    return all_ok

# ── build ─────────────────────────────────────────────────────────────────────

def build_rpm(version: str, dry_run: bool = False) -> Path | None:
    header(f"Building kport-{version}.rpm")

    if not SPEC_TEMPLATE.exists():
        err(f"Spec template not found: {SPEC_TEMPLATE}")
        return None

    # Read and fill the template
    template = SPEC_TEMPLATE.read_text(encoding="utf-8")
    spec_content = (
        template.replace("{VERSION}", version)
        .replace("{DATE}", _rpmdate())
        .replace("{SRC_KPORT}", str(REPO_ROOT / "src" / "kport").replace("\\", "/"))
        .replace("{REPO_ROOT}", str(REPO_ROOT).replace("\\", "/"))
    )

    with tempfile.TemporaryDirectory(prefix="kport-rpm-") as td:
        tmp = Path(td)

        # Standard rpmbuild directory layout
        for d in ("BUILD", "BUILDROOT", "RPMS", "SOURCES", "SPECS", "SRPMS"):
            (tmp / d).mkdir()

        spec_path = tmp / "SPECS" / "kport.spec"
        spec_path.write_text(spec_content, encoding="utf-8")

        if dry_run:
            warn("DRY RUN — would run rpmbuild")
            print(f"\nGenerated spec:\n{'─'*40}")
            print(spec_content)
            return None

        result = subprocess.run(
            [
                "rpmbuild", "-bb",
                "--define", f"_topdir {tmp}",
                str(spec_path),
            ],
            cwd=str(REPO_ROOT),
        )
        if result.returncode != 0:
            err("rpmbuild failed")
            return None

        # Find the produced .rpm
        rpms = list((tmp / "RPMS").rglob("*.rpm"))
        rpms = [r for r in rpms if "debuginfo" not in r.name]
        if not rpms:
            err("No .rpm produced in RPMS/")
            return None

        DIST_RPM.mkdir(parents=True, exist_ok=True)
        dest = DIST_RPM / rpms[0].name
        shutil.copy2(rpms[0], dest)
        ok(f"RPM built: {dest}")
        print(f"\nInstall with:")
        print(f"  sudo rpm -i {dest}")
        print(f"  # or via dnf: sudo dnf install {dest}")
        return dest

# ── interactive menu ──────────────────────────────────────────────────────────

def interactive_menu(version: str) -> None:
    header(f"🐧 kport RPM Build Tool  (v{version})")

    if platform.system() != "Linux":
        warn("This does not appear to be a Linux system.")
        warn("rpmbuild typically requires Linux (RHEL/Fedora/CentOS/openSUSE).")

    print("What would you like to do?")
    print("  1. Check prerequisites")
    print("  2. Build .rpm package")
    print("  3. Build .rpm and show install command")
    print("  0. Exit")

    choice = input("\nEnter choice (0-3): ").strip()

    if choice == "0":
        print("👋 Goodbye!")
        return

    if choice == "1":
        checks = check_prerequisites()
        print_check_results(checks)
        return

    if choice in ("2", "3"):
        checks = check_prerequisites()
        if not checks["rpmbuild"]:
            err("rpmbuild not found. Install rpm-build package first.")
            sys.exit(1)
        rpm_path = build_rpm(version)
        if not rpm_path:
            sys.exit(1)
        if choice == "3":
            ok("Build complete")
            print(f"\n.rpm: {rpm_path}")
        return

    err("Invalid choice")
    sys.exit(1)

# ── CLI entry-point ───────────────────────────────────────────────────────────

def main() -> None:
    version = read_version()

    parser = argparse.ArgumentParser(
        description="Build kport RPM package",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--check",   action="store_true", help="Check prerequisites and exit")
    parser.add_argument("--build",   action="store_true", help="Build .rpm")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--version", default=version,     help=f"Version string (default: {version})")
    args = parser.parse_args()

    version = args.version

    if args.check:
        checks = check_prerequisites()
        ok_all = print_check_results(checks)
        sys.exit(0 if ok_all else 1)

    if args.build:
        checks = check_prerequisites()
        if not checks["rpmbuild"] and not args.dry_run:
            err("rpmbuild not found")
            sys.exit(1)
        path = build_rpm(version, args.dry_run)
        sys.exit(0 if path or args.dry_run else 1)

    interactive_menu(version)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled")
        sys.exit(0)
