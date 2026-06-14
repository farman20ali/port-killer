#!/usr/bin/env python3
"""Unified build orchestrator for KPort.

Orchestrates building and packaging across all platforms and formats.
Provides a unified interface for creating and publishing builds.

Usage (automated / CI):
    python kport_orchestrate.py --check              # Check all prerequisites
    python kport_orchestrate.py --build-all          # Build all packages
    python kport_orchestrate.py --build-pypi         # Build Python packages only
    python kport_orchestrate.py --build-vscode       # Build VS Code extension only
    python kport_orchestrate.py --build-snap         # Build snap package only
    python kport_orchestrate.py --publish-all        # Publish all packages
    python kport_orchestrate.py --publish-pypi       # Publish to PyPI
    python kport_orchestrate.py --publish-vscode     # Publish VS Code extension
    python kport_orchestrate.py --publish-snap       # Publish to Snap Store
    python kport_orchestrate.py --dry-run            # Show what would happen

Interactive (recommended):
    python kport_orchestrate.py                      # Interactive menu

Full workflow examples:
    python kport_orchestrate.py --build-all && python kport_orchestrate.py --publish-all
    python kport_orchestrate.py --build-vscode --install
    python kport_orchestrate.py --build-snap --publish-snap --channel edge
"""

from __future__ import annotations

import argparse
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


def section(title: str) -> None:
    """Print section header"""
    print(_c(f"\n{'='*60}", "96"))
    print(_c(f"{title}", "96"))
    print(_c(f"{'='*60}", "96"))


def run_script(script: str, args: str = "", dry_run: bool = False) -> int:
    """Run a build script"""
    python = sys.executable
    cmd = f"{python} {REPO_ROOT / script} {args}"
    
    if dry_run:
        print(f"[DRY-RUN] Would execute: {cmd}")
        return 0
    
    print(f"$ {cmd}\n")
    result = subprocess.run(cmd, shell=True, cwd=REPO_ROOT)
    return result.returncode


def check_all_requirements(dry_run: bool = False) -> bool:
    """Check prerequisites for all build types"""
    section("Checking All Prerequisites")
    
    scripts = [
        ("build_packages.py", "--check", "Python packages"),
        ("vscode_build.py", "--check", "VS Code extension"),
        ("snap_publish.py", "--check", "Snap package"),
    ]
    
    all_ok = True
    for script, arg, desc in scripts:
        print(f"\n>>> Checking {desc}...")
        ret = run_script(script, arg, dry_run=dry_run)
        if ret != 0:
            all_ok = False
    
    return all_ok


def build_all(dry_run: bool = False) -> int:
    """Build all packages"""
    section("Building All Packages")
    
    builds = [
        ("build_packages.py", "--all", "Python packages"),
        ("vscode_build.py", "--build", "VS Code extension"),
        ("snap_build.py", "--build", "Snap package"),
    ]
    
    failed = []
    for script, arg, desc in builds:
        print(f"\n>>> Building {desc}...")
        ret = run_script(script, arg, dry_run=dry_run)
        if ret != 0:
            failed.append(desc)
    
    if failed:
        err(f"Failed builds: {', '.join(failed)}")
        return 1
    else:
        ok("All packages built successfully")
        return 0


def build_pypi(dry_run: bool = False) -> int:
    """Build Python packages (PyPI)"""
    section("Building Python Packages")
    return run_script("build_packages.py", "--pypi", dry_run=dry_run)


def build_vscode(dry_run: bool = False) -> int:
    """Build VS Code extension"""
    section("Building VS Code Extension")
    return run_script("vscode_build.py", "--build", dry_run=dry_run)


def build_snap(dry_run: bool = False) -> int:
    """Build snap package"""
    section("Building Snap Package")
    return run_script("snap_build.py", "--build", dry_run=dry_run)


def publish_all(dry_run: bool = False) -> int:
    """Publish all packages"""
    section("Publishing All Packages")
    
    publishes = [
        ("publish.py", "", "PyPI"),
        ("vscode_build.py", "--publish", "VS Code extension"),
        ("snap_publish.py", "--publish", "Snap package"),
    ]
    
    failed = []
    for script, arg, desc in publishes:
        print(f"\n>>> Publishing {desc}...")
        ret = run_script(script, arg, dry_run=dry_run)
        if ret != 0:
            failed.append(desc)
    
    if failed:
        warn(f"Some publishes failed: {', '.join(failed)}")
        return 1
    else:
        ok("All packages published successfully")
        return 0


def publish_pypi(dry_run: bool = False) -> int:
    """Publish to PyPI"""
    section("Publishing to PyPI")
    return run_script("publish.py", "", dry_run=dry_run)


def publish_vscode(dry_run: bool = False) -> int:
    """Publish VS Code extension"""
    section("Publishing VS Code Extension")
    return run_script("vscode_build.py", "--publish", dry_run=dry_run)


def publish_snap(channel: str = "stable", dry_run: bool = False) -> int:
    """Publish snap package"""
    section(f"Publishing Snap Package (channel: {channel})")
    return run_script("snap_publish.py", f"--publish --channel {channel}", dry_run=dry_run)


def interactive_menu() -> int:
    """Show interactive menu"""
    section("KPort Unified Build Orchestrator")
    
    print("\n📦 Build Options:")
    print("  1. Check all prerequisites")
    print("  2. Build all packages")
    print("  3. Build Python packages (PyPI)")
    print("  4. Build VS Code extension")
    print("  5. Build snap package")
    
    print("\n📤 Publish Options:")
    print("  6. Publish all packages")
    print("  7. Publish to PyPI")
    print("  8. Publish VS Code extension")
    print("  9. Publish snap (stable)")
    print("  10. Publish snap (edge)")
    print("  11. Publish snap (candidate)")
    
    print("\n🔗 Workflows:")
    print("  12. Build all + Install VS Code extension locally")
    print("  13. Build all + Publish all")
    
    print("\n0. Exit")
    
    choice = input("\nEnter choice (0-13): ").strip()
    
    if choice == "0":
        return 0
    elif choice == "1":
        return 0 if check_all_requirements() else 1
    elif choice == "2":
        return build_all()
    elif choice == "3":
        return build_pypi()
    elif choice == "4":
        return build_vscode()
    elif choice == "5":
        return build_snap()
    elif choice == "6":
        return publish_all()
    elif choice == "7":
        return publish_pypi()
    elif choice == "8":
        return publish_vscode()
    elif choice == "9":
        return publish_snap(channel="stable")
    elif choice == "10":
        return publish_snap(channel="edge")
    elif choice == "11":
        return publish_snap(channel="candidate")
    elif choice == "12":
        ret = build_all()
        if ret == 0:
            return run_script("vscode_build.py", "--install")
        return ret
    elif choice == "13":
        ret = build_all()
        if ret == 0:
            return publish_all()
        return ret
    else:
        err("Invalid choice")
        return 1


def main() -> int:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Unified build orchestrator for KPort",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    group = parser.add_argument_group("checking")
    group.add_argument(
        "--check",
        action="store_true",
        help="Check all prerequisites"
    )
    
    group = parser.add_argument_group("building")
    group.add_argument(
        "--build-all",
        action="store_true",
        help="Build all packages"
    )
    group.add_argument(
        "--build-pypi",
        action="store_true",
        help="Build Python packages (PyPI)"
    )
    group.add_argument(
        "--build-vscode",
        action="store_true",
        help="Build VS Code extension"
    )
    group.add_argument(
        "--build-snap",
        action="store_true",
        help="Build snap package"
    )
    group.add_argument(
        "--install-vscode",
        action="store_true",
        help="Install VS Code extension locally (requires --build-vscode)"
    )
    
    group = parser.add_argument_group("publishing")
    group.add_argument(
        "--publish-all",
        action="store_true",
        help="Publish all packages"
    )
    group.add_argument(
        "--publish-pypi",
        action="store_true",
        help="Publish to PyPI"
    )
    group.add_argument(
        "--publish-vscode",
        action="store_true",
        help="Publish VS Code extension"
    )
    group.add_argument(
        "--publish-snap",
        action="store_true",
        help="Publish snap package"
    )
    group.add_argument(
        "--snap-channel",
        choices=["stable", "candidate", "edge"],
        default="stable",
        help="Snap release channel (default: stable)"
    )
    
    group = parser.add_argument_group("options")
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without doing it"
    )
    
    args = parser.parse_args()
    
    # Interactive mode if no args
    if not any([
        args.check, args.build_all, args.build_pypi, args.build_vscode,
        args.build_snap, args.publish_all, args.publish_pypi,
        args.publish_vscode, args.publish_snap
    ]):
        return interactive_menu()
    
    # Execute requested operations in order
    ret = 0
    
    if args.check:
        check_all_requirements(dry_run=args.dry_run)
    
    if args.build_all:
        ret = build_all(dry_run=args.dry_run)
    
    if args.build_pypi:
        ret = build_pypi(dry_run=args.dry_run)
    
    if args.build_vscode:
        ret = build_vscode(dry_run=args.dry_run)
    
    if args.build_snap:
        ret = build_snap(dry_run=args.dry_run)
    
    if args.install_vscode:
        ret = run_script("vscode_build.py", "--install", dry_run=args.dry_run)
    
    if args.publish_all and ret == 0:
        ret = publish_all(dry_run=args.dry_run)
    
    if args.publish_pypi and ret == 0:
        ret = publish_pypi(dry_run=args.dry_run)
    
    if args.publish_vscode and ret == 0:
        ret = publish_vscode(dry_run=args.dry_run)
    
    if args.publish_snap and ret == 0:
        ret = publish_snap(channel=args.snap_channel, dry_run=args.dry_run)
    
    return ret


if __name__ == "__main__":
    sys.exit(main())
