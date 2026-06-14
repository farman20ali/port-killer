#!/usr/bin/env python3
"""VS Code extension builder and publisher for KPort.

Builds the KPort VS Code extension (.vsix) and publishes to the marketplace.

Usage (automated / CI):
    python vscode_build.py --check        # Check all prerequisites
    python vscode_build.py --build        # Build .vsix file
    python vscode_build.py --install      # Install locally
    python vscode_build.py --publish      # Publish to marketplace (requires token)
    python vscode_build.py --dry-run      # Show what would happen

Interactive (recommended for first-time setup):
    python vscode_build.py                # Interactive menu

Output:
    vscode-extension/kport-vscode-<version>.vsix
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

REPO_ROOT = Path(__file__).resolve().parent
VSCODE_EXT = REPO_ROOT / "vscode-extension"
PACKAGE_JSON = VSCODE_EXT / "package.json"


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


def check_node_installed() -> bool:
    """Check if Node.js and npm are installed"""
    result = subprocess.run(
        "node --version && npm --version",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


def check_vsce_installed() -> bool:
    """Check if vsce is installed"""
    result = subprocess.run(
        "npm list -g @vscode/vsce",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


def check_vscode_installed() -> bool:
    """Check if VS Code CLI is available"""
    result = subprocess.run(
        "code --version",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


def get_extension_version() -> str:
    """Extract version from package.json"""
    try:
        with open(PACKAGE_JSON) as f:
            data = json.load(f)
            return data.get("version", "unknown")
    except Exception as e:
        err(f"Failed to read version: {e}")
        return "unknown"


def check_requirements() -> bool:
    """Check all prerequisites for building/publishing"""
    print("\n" + "="*60)
    print("📋 Checking prerequisites")
    print("="*60)
    
    checks = [
        ("Node.js & npm", check_node_installed),
        ("VS Code CLI", check_vscode_installed),
        ("vsce (VS Code Extension CLI)", check_vsce_installed),
    ]
    
    all_ok = True
    for name, check_fn in checks:
        if check_fn():
            ok(f"{name} is installed")
        else:
            err(f"{name} is NOT installed")
            all_ok = False
    
    # Check vscode-extension directory
    if VSCODE_EXT.exists():
        ok(f"Extension directory exists: {VSCODE_EXT}")
    else:
        err(f"Extension directory NOT found: {VSCODE_EXT}")
        all_ok = False
    
    # Check package.json
    if PACKAGE_JSON.exists():
        version = get_extension_version()
        ok(f"package.json found (version: {version})")
    else:
        err(f"package.json NOT found: {PACKAGE_JSON}")
        all_ok = False
    
    return all_ok


def build_extension(dry_run: bool = False) -> int:
    """Build the VS Code extension (.vsix file)"""
    if not VSCODE_EXT.exists():
        err(f"Extension directory not found: {VSCODE_EXT}")
        return 1
    
    version = get_extension_version()
    info(f"Building KPort VS Code extension v{version}")
    
    cmd = f"cd {VSCODE_EXT} && npm install && npm run package"
    
    if dry_run:
        print(f"\n[DRY-RUN] Would execute:\n$ {cmd}")
        return 0
    
    return run_cmd(cmd, "Building VS Code extension (.vsix)", check=True)


def install_extension(dry_run: bool = False) -> int:
    """Install the extension locally for testing"""
    version = get_extension_version()
    vsix_file = VSCODE_EXT / f"kport-vscode-{version}.vsix"
    
    if not vsix_file.exists():
        err(f"VSIX file not found: {vsix_file}")
        warn("Run --build first to create the VSIX file")
        return 1
    
    cmd = f"code --install-extension {vsix_file}"
    
    if dry_run:
        print(f"\n[DRY-RUN] Would execute:\n$ {cmd}")
        return 0
    
    return run_cmd(cmd, "Installing extension locally", check=True)


def publish_extension(dry_run: bool = False) -> int:
    """Publish the extension to VS Code Marketplace"""
    version = get_extension_version()
    info(f"Publishing KPort VS Code extension v{version}")
    
    # Check for PAT token
    import os
    pat = os.environ.get("VSCE_PAT")
    
    if not pat:
        warn("VSCE_PAT environment variable not set")
        print("\nTo publish, you need:")
        print("1. A VS Code Marketplace Publisher account")
        print("2. A Personal Access Token (PAT)")
        print("3. Set the environment variable: VSCE_PAT=your_token")
        print("\nSee: https://code.visualstudio.com/api/working-with-extensions/publishing-extension")
        return 1
    
    cmd = f"cd {VSCODE_EXT} && vsce publish"
    
    if dry_run:
        print(f"\n[DRY-RUN] Would execute:\n$ {cmd}")
        print("[DRY-RUN] (with VSCE_PAT set)")
        return 0
    
    return run_cmd(cmd, "Publishing to VS Code Marketplace", check=True)


def interactive_menu() -> int:
    """Show interactive menu"""
    print("\n" + "="*60)
    print("🔨 KPort VS Code Extension Builder")
    print("="*60)
    
    version = get_extension_version()
    print(f"\nVersion: {version}")
    print("\nWhat would you like to do?")
    print("  1. Check prerequisites")
    print("  2. Build extension (.vsix)")
    print("  3. Install locally (for testing)")
    print("  4. Publish to marketplace")
    print("  5. Build → Install (build & test locally)")
    print("  6. Build → Publish (build & publish)")
    print("  0. Exit")
    
    choice = input("\nEnter choice (0-6): ").strip()
    
    if choice == "0":
        return 0
    elif choice == "1":
        check_requirements()
        return 0
    elif choice == "2":
        return build_extension()
    elif choice == "3":
        return install_extension()
    elif choice == "4":
        return publish_extension()
    elif choice == "5":
        ret = build_extension()
        if ret == 0:
            return install_extension()
        return ret
    elif choice == "6":
        ret = build_extension()
        if ret == 0:
            return publish_extension()
        return ret
    else:
        err("Invalid choice")
        return 1


def main() -> int:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Build and publish KPort VS Code extension",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check all prerequisites"
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build .vsix file"
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install extension locally"
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish to VS Code Marketplace (requires VSCE_PAT token)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without doing it"
    )
    
    args = parser.parse_args()
    
    # Interactive mode if no args
    if not any([args.check, args.build, args.install, args.publish]):
        return interactive_menu()
    
    # Execute requested operations
    if args.check:
        check_requirements()
        return 0
    
    if args.build:
        return build_extension(dry_run=args.dry_run)
    
    if args.install:
        return install_extension(dry_run=args.dry_run)
    
    if args.publish:
        return publish_extension(dry_run=args.dry_run)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
