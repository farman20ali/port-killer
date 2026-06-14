#!/usr/bin/env python3
"""Snap package publisher for KPort.

Publishes built .snap packages to the Snap Store.

Usage (automated / CI):
    python snap_publish.py --check              # Check prerequisites
    python snap_publish.py --publish            # Publish snap
    python snap_publish.py --publish --edge     # Publish to edge channel
    python snap_publish.py --dry-run            # Show what would happen

Interactive (recommended for first-time setup):
    python snap_publish.py                      # Interactive menu

Requirements:
    - Built .snap file from snap_build.py
    - Snapcraft login with valid credentials
    - snapcraft CLI installed
"""

from __future__ import annotations

import argparse
import re
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
DIST_SNAP = REPO_ROOT / "dist" / "snap"


def _c(text: str, code: str) -> str:
    """Colorize output on supporting terminals"""
    if sys.stdout.isatty() and sys.platform != "win32":
        return f"\033[{code}m{text}\033[0m"
    return text


def ok(msg: str) -> None:
    """Print success message"""
    print(_c(f"✅ {msg}", "92"))


def err(msg: str) -> None:
    """Print error message"""
    print(_c(f"❌ {msg}", "91"), file=sys.stderr)


def warn(msg: str) -> None:
    """Print warning message"""
    print(_c(f"⚠️  {msg}", "93"))


def info(msg: str) -> None:
    """Print info message"""
    print(_c(f"ℹ️  {msg}", "94"))


def run_cmd(cmd: str, description: str, check: bool = True) -> int:
    """Run a command and return exit code"""
    print(f"\n{'='*60}")
    print(f"🔄 {description}")
    print(f"{'='*60}")
    print(f"$ {cmd}\n")
    
    result = subprocess.run(cmd, shell=True)
    
    if check and result.returncode != 0:
        err(f"Failed: {description}")
        return result.returncode
    
    if result.returncode == 0:
        ok(f"Success: {description}")
    
    return result.returncode


def check_snapcraft_installed() -> bool:
    """Check if snapcraft is installed"""
    result = subprocess.run(
        "snapcraft --version",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


def check_snapcraft_authenticated() -> bool:
    """Check if snapcraft is authenticated with Snap Store"""
    # Try to get whoami output
    result = subprocess.run(
        "snapcraft whoami",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if result.returncode == 0:
        return bool(result.stdout.strip())
    return False


def find_snap_file() -> Path | None:
    """Find the built .snap file"""
    if not DIST_SNAP.exists():
        return None
    
    snap_files = list(DIST_SNAP.glob("*.snap"))
    
    if not snap_files:
        return None
    
    # Return the most recent snap file
    return sorted(snap_files, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def get_snap_version(snap_file: Path) -> str:
    """Extract version from snap filename"""
    # Format: kport_<version>_<arch>.snap
    match = re.search(r"kport_([^_]+)_", snap_file.name)
    return match.group(1) if match else "unknown"


def check_requirements() -> bool:
    """Check all prerequisites for publishing"""
    print("\n" + "="*60)
    print("📋 Checking prerequisites")
    print("="*60)
    
    all_ok = True
    
    # Check snapcraft
    if check_snapcraft_installed():
        ok("snapcraft is installed")
    else:
        err("snapcraft is NOT installed")
        print("  Install: sudo apt install snapcraft")
        all_ok = False
    
    # Check Snap Store authentication
    if check_snapcraft_authenticated():
        ok("snapcraft is authenticated with Snap Store")
    else:
        warn("snapcraft is NOT authenticated")
        print("  Run: snapcraft login")
    
    # Check for built snap file
    snap_file = find_snap_file()
    if snap_file:
        version = get_snap_version(snap_file)
        ok(f"Built snap file found: {snap_file.name} (v{version})")
    else:
        err(f"No built snap file found in {DIST_SNAP}")
        print("  Run: python snap_build.py --build")
        all_ok = False
    
    return all_ok


def publish_snap(channel: str = "stable", dry_run: bool = False) -> int:
    """Publish snap to the Snap Store"""
    snap_file = find_snap_file()
    
    if not snap_file:
        err(f"No snap file found in {DIST_SNAP}")
        warn("Run: python snap_build.py --build")
        return 1
    
    version = get_snap_version(snap_file)
    info(f"Publishing {snap_file.name} to '{channel}' channel")
    
    # Check authentication
    if not check_snapcraft_authenticated():
        err("Not authenticated with Snap Store")
        print("\nRun: snapcraft login")
        print("Then: python snap_publish.py --publish")
        return 1
    
    cmd = f"snapcraft upload {snap_file} --release {channel}"
    
    if dry_run:
        print(f"\n[DRY-RUN] Would execute:\n$ {cmd}")
        return 0
    
    return run_cmd(cmd, f"Publishing snap v{version} to {channel} channel", check=True)


def login_snapcraft(dry_run: bool = False) -> int:
    """Authenticate with Snap Store"""
    info("Authenticating with Snap Store")
    print("\nYou will be prompted for your Snap Store credentials.")
    print("Get your credentials at: https://snapcraft.io/account")
    
    cmd = "snapcraft login"
    
    if dry_run:
        print(f"\n[DRY-RUN] Would execute:\n$ {cmd}")
        return 0
    
    return run_cmd(cmd, "Authenticating with Snap Store", check=True)


def interactive_menu() -> int:
    """Show interactive menu"""
    print("\n" + "="*60)
    print("📦 KPort Snap Package Publisher")
    print("="*60)
    
    snap_file = find_snap_file()
    if snap_file:
        version = get_snap_version(snap_file)
        print(f"\nFound: {snap_file.name} (v{version})")
    else:
        warn("No built snap file found")
    
    print("\nWhat would you like to do?")
    print("  1. Check prerequisites")
    print("  2. Login to Snap Store")
    print("  3. Publish to stable channel")
    print("  4. Publish to edge channel (testing)")
    print("  5. Publish to candidate channel (release candidate)")
    print("  0. Exit")
    
    choice = input("\nEnter choice (0-5): ").strip()
    
    if choice == "0":
        return 0
    elif choice == "1":
        check_requirements()
        return 0
    elif choice == "2":
        return login_snapcraft()
    elif choice == "3":
        return publish_snap(channel="stable")
    elif choice == "4":
        return publish_snap(channel="edge")
    elif choice == "5":
        return publish_snap(channel="candidate")
    else:
        err("Invalid choice")
        return 1


def main() -> int:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Publish KPort snap package to Snap Store",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check all prerequisites"
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Authenticate with Snap Store"
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish snap to Snap Store"
    )
    parser.add_argument(
        "--channel",
        choices=["stable", "candidate", "edge"],
        default="stable",
        help="Release channel (default: stable)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without doing it"
    )
    
    args = parser.parse_args()
    
    # Interactive mode if no args
    if not any([args.check, args.login, args.publish]):
        return interactive_menu()
    
    # Execute requested operations
    if args.check:
        check_requirements()
        return 0
    
    if args.login:
        return login_snapcraft(dry_run=args.dry_run)
    
    if args.publish:
        return publish_snap(channel=args.channel, dry_run=args.dry_run)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
