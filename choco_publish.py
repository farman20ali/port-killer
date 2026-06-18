#!/usr/bin/env python3
"""Chocolatey package publisher for KPort.

Publishes built .nupkg packages to the Chocolatey Community Repository.

Usage (automated / CI):
    python choco_publish.py --check                        # Check prerequisites
    python choco_publish.py --publish                      # Publish .nupkg
    python choco_publish.py --publish --skip-if-no-credentials  # CI: skip when no API key
    python choco_publish.py --dry-run                        # Show what would happen

Interactive (recommended for first-time setup):
    python choco_publish.py                                # Interactive menu

Requirements:
    - Built .nupkg file from choco_build.py
    - Chocolatey CLI installed
    - CHOCO_API_KEY environment variable (or choco apikey configured locally)

Get an API key at: https://community.chocolatey.org/account
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

REPO_ROOT = Path(__file__).resolve().parent
DIST_CHOCO = REPO_ROOT / "dist" / "choco"
CHOCO_SOURCE = "https://push.chocolatey.org/"


def _c(text: str, code: str) -> str:
    if sys.stdout.isatty() and sys.platform != "win32":
        return f"\033[{code}m{text}\033[0m"
    return text


def ok(msg: str) -> None:
    print(_c(f"✅ {msg}", "92"))


def err(msg: str) -> None:
    print(_c(f"❌ {msg}", "91"), file=sys.stderr)


def warn(msg: str) -> None:
    print(_c(f"⚠️  {msg}", "93"))


def info(msg: str) -> None:
    print(_c(f"ℹ️  {msg}", "94"))


def run_cmd(cmd: list[str], description: str, check: bool = True) -> int:
    print(f"\n{'='*60}")
    print(f"🔄 {description}")
    print(f"{'='*60}")
    print("$", " ".join(cmd), "\n")

    result = subprocess.run(cmd, cwd=str(REPO_ROOT))

    if check and result.returncode != 0:
        err(f"Failed: {description}")
        return result.returncode

    if result.returncode == 0:
        ok(f"Success: {description}")

    return result.returncode


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def get_api_key() -> str | None:
    key = os.environ.get("CHOCO_API_KEY", "").strip()
    return key or None


def check_choco_installed() -> bool:
    return command_exists("choco")


def find_nupkg_file() -> Path | None:
    if not DIST_CHOCO.exists():
        return None

    nupkgs = list(DIST_CHOCO.glob("kport.*.nupkg"))
    if not nupkgs:
        return None

    return sorted(nupkgs, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def get_nupkg_version(nupkg_file: Path) -> str:
    match = re.search(r"kport\.([^/\\]+)\.nupkg$", nupkg_file.name)
    return match.group(1) if match else "unknown"


def check_requirements() -> bool:
    print("\n" + "=" * 60)
    print("📋 Checking prerequisites")
    print("=" * 60)

    all_ok = True

    if check_choco_installed():
        ok("choco CLI is installed")
    else:
        err("choco CLI is NOT installed")
        print("  Install: https://chocolatey.org/install")
        all_ok = False

    api_key = get_api_key()
    if api_key:
        ok("CHOCO_API_KEY is set")
    else:
        warn("CHOCO_API_KEY is NOT set")
        print("  Get a key at: https://community.chocolatey.org/account")
        print("  Then: set CHOCO_API_KEY=your-key-here   (PowerShell)")
        print("    or: export CHOCO_API_KEY=your-key-here (bash)")

    nupkg_file = find_nupkg_file()
    if nupkg_file:
        version = get_nupkg_version(nupkg_file)
        ok(f"Built package found: {nupkg_file.name} (v{version})")
    else:
        err(f"No built .nupkg found in {DIST_CHOCO}")
        print("  Run: python choco_build.py --build")
        print("  Ensure GitHub release asset exists before users install via choco")
        all_ok = False

    return all_ok


def publish_choco(
    dry_run: bool = False,
    skip_if_no_credentials: bool = False,
) -> int:
    nupkg_file = find_nupkg_file()
    if not nupkg_file:
        err(f"No .nupkg found in {DIST_CHOCO}")
        warn("Run: python choco_build.py --build")
        print(f"  Release asset must exist at GitHub before install works")
        return 1

    version = get_nupkg_version(nupkg_file)
    info(f"Publishing {nupkg_file.name} to Chocolatey Community")

    if not check_choco_installed():
        err("choco CLI not found")
        return 1

    api_key = get_api_key()
    if not api_key:
        if skip_if_no_credentials:
            warn("CHOCO_API_KEY not configured — skipping Chocolatey publish")
            return 0

        err("CHOCO_API_KEY environment variable not set")
        print("\nTo publish, you need:")
        print("1. A Chocolatey Community account: https://community.chocolatey.org/")
        print("2. An API key from: https://community.chocolatey.org/account")
        print("3. Set the environment variable: CHOCO_API_KEY=your-key-here")
        print("\nThen: python choco_publish.py --publish")
        return 1

    cmd = [
        "choco",
        "push",
        str(nupkg_file),
        "--source",
        CHOCO_SOURCE,
        "--api-key",
        api_key,
    ]

    if dry_run:
        print(f"\n[DRY-RUN] Would execute:")
        print(f"$ choco push {nupkg_file.name} --source {CHOCO_SOURCE} --api-key ***")
        return 0

    return run_cmd(cmd, f"Publishing kport v{version} to Chocolatey Community", check=True)


def interactive_menu() -> int:
    print("\n" + "=" * 60)
    print("📦 KPort Chocolatey Package Publisher")
    print("=" * 60)

    nupkg_file = find_nupkg_file()
    if nupkg_file:
        version = get_nupkg_version(nupkg_file)
        print(f"\nFound: {nupkg_file.name} (v{version})")
    else:
        warn("No built .nupkg found")

    print("\nWhat would you like to do?")
    print("  1. Check prerequisites")
    print("  2. Publish to Chocolatey Community")
    print("  0. Exit")

    choice = input("\nEnter choice (0-2): ").strip()

    if choice == "0":
        return 0
    if choice == "1":
        check_requirements()
        return 0
    if choice == "2":
        return publish_choco()
    err("Invalid choice")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish KPort Chocolatey package to community.chocolatey.org",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("--check", action="store_true", help="Check all prerequisites")
    parser.add_argument("--publish", action="store_true", help="Publish .nupkg to Chocolatey")
    parser.add_argument(
        "--skip-if-no-credentials",
        action="store_true",
        help="Exit 0 (skip) when CHOCO_API_KEY is not set — for CI",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without doing it",
    )

    args = parser.parse_args()

    if not any([args.check, args.publish]):
        return interactive_menu()

    if args.check:
        check_requirements()
        return 0

    if args.publish:
        return publish_choco(
            dry_run=args.dry_run,
            skip_if_no_credentials=args.skip_if_no_credentials,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
