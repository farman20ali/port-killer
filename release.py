#!/usr/bin/env python3
"""Automated release script for kport.

This script automates the entire release process:
- Validates version and git state
- Creates and pushes git tags
- Builds PyPI and Debian packages
- Optionally creates GitHub releases with gh CLI

Usage:
  python3 release.py [--version VERSION] [--no-pypi] [--no-deb] [--dry-run]

Examples:
  python3 release.py                    # Interactive mode
  python3 release.py --version 3.1.2    # Release specific version
  python3 release.py --dry-run          # Preview without making changes
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
SETUP_PY = REPO_ROOT / "setup.py"


class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(msg: str) -> None:
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{msg}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.END}")


def print_step(msg: str) -> None:
    print(f"\n{Colors.CYAN}▶ {msg}{Colors.END}")


def print_success(msg: str) -> None:
    print(f"{Colors.GREEN}✅ {msg}{Colors.END}")


def print_error(msg: str) -> None:
    print(f"{Colors.RED}❌ {msg}{Colors.END}", file=sys.stderr)


def print_warning(msg: str) -> None:
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.END}")


def run_command(cmd: list[str], description: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a command with status reporting."""
    print_step(description)
    print(f"$ {' '.join(cmd)}")
    
    kwargs = {"cwd": str(REPO_ROOT)}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    
    result = subprocess.run(cmd, **kwargs)
    
    if check and result.returncode != 0:
        print_error(f"Failed: {description}")
        sys.exit(result.returncode)
    
    if result.returncode == 0:
        print_success(description)
    
    return result


def command_exists(name: str) -> bool:
    """Check if a command exists."""
    return shutil.which(name) is not None


def read_version_from_setup() -> str | None:
    """Extract version from setup.py."""
    if not SETUP_PY.exists():
        return None
    text = SETUP_PY.read_text(encoding="utf-8")
    m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', text)
    if not m:
        return None
    return m.group(1).strip()


def check_git_status() -> bool:
    """Check if working directory is clean."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True
    )
    return len(result.stdout.strip()) == 0


def check_tag_exists(tag: str) -> bool:
    """Check if a git tag already exists."""
    result = subprocess.run(
        ["git", "tag", "-l", tag],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True
    )
    return len(result.stdout.strip()) > 0


def get_release_notes(version: str) -> str:
    """Generate or prompt for release notes."""
    default_notes = f"""Release {version}

Changes in this release:
- Bug fixes and improvements
- See commit history for details

Install:
  pip install kport=={version}
"""
    
    print_step("Release notes")
    print("Default release notes:")
    print("-" * 60)
    print(default_notes)
    print("-" * 60)
    
    use_default = input("\nUse default release notes? (Y/n): ").strip().lower()
    if use_default in ("", "y", "yes"):
        return default_notes
    
    print("\nEnter custom release notes (Ctrl+D when done):")
    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass
    
    return "\n".join(lines) or default_notes


def build_pypi_packages(dry_run: bool = False) -> bool:
    """Build PyPI packages using publish.py."""
    if dry_run:
        print_warning("DRY RUN: Would build PyPI packages")
        return True
    
    print_header("Building PyPI Packages")
    
    # Check if build tools exist
    if not command_exists("python3"):
        print_error("python3 not found")
        return False
    
    publish_script = REPO_ROOT / "publish.py"
    if not publish_script.exists():
        print_error("publish.py not found")
        return False
    
    # Run publish.py in automated mode (option 1: just build)
    result = subprocess.run(
        ["python3", str(publish_script)],
        cwd=str(REPO_ROOT),
        input="1\n",
        text=True
    )
    
    if result.returncode != 0:
        print_error("PyPI package build failed")
        return False
    
    # Check if dist files were created
    dist_dir = REPO_ROOT / "dist"
    if not dist_dir.exists() or not list(dist_dir.glob("*.whl")):
        print_error("No .whl files found in dist/")
        return False
    
    print_success("PyPI packages built successfully")
    return True


def build_debian_package(dry_run: bool = False) -> bool:
    """Build Debian package using deb_publish.py."""
    if dry_run:
        print_warning("DRY RUN: Would build Debian package")
        return True
    
    print_header("Building Debian Package")
    
    deb_script = REPO_ROOT / "deb_publish.py"
    if not deb_script.exists():
        print_error("deb_publish.py not found")
        return False
    
    # Run deb_publish.py in automated mode (option 3: just build)
    result = subprocess.run(
        ["python3", str(deb_script)],
        cwd=str(REPO_ROOT),
        input="3\n",
        text=True
    )
    
    if result.returncode != 0:
        print_warning("Debian package build failed (may not be on Debian/Ubuntu)")
        return False
    
    # Check if .deb was created
    deb_dir = REPO_ROOT / "dist" / "deb"
    if not deb_dir.exists() or not list(deb_dir.glob("*.deb")):
        print_warning("No .deb files found in dist/deb/")
        return False
    
    print_success("Debian package built successfully")
    return True


def create_github_release(version: str, tag: str, notes: str, dry_run: bool = False) -> bool:
    """Create GitHub release using gh CLI."""
    if not command_exists("gh"):
        print_warning("GitHub CLI (gh) not installed - skipping GitHub release")
        print("Install: https://cli.github.com/")
        print("Then run manually:")
        print(f"  gh release create {tag} --title 'kport {version}' --notes '{notes}' dist/*.tar.gz dist/*.whl dist/deb/*.deb")
        return False
    
    if dry_run:
        print_warning(f"DRY RUN: Would create GitHub release {tag}")
        return True
    
    print_header("Creating GitHub Release")
    
    # Collect release assets (built artifacts only - GitHub auto-attaches source)
    assets = []
    dist_dir = REPO_ROOT / "dist"
    
    # Add Python wheel (built artifact)
    assets.extend(str(f) for f in dist_dir.glob("*.whl"))
    
    # Add Debian package (built artifact)
    deb_dir = dist_dir / "deb"
    if deb_dir.exists():
        assets.extend(str(f) for f in deb_dir.glob("*.deb"))
    
    # Note: We don't attach .tar.gz - GitHub automatically provides source archives
    
    if not assets:
        print_warning("No release assets found")
    
    # Build gh command
    cmd = [
        "gh", "release", "create", tag,
        "--title", f"kport {version}",
        "--notes", notes
    ]
    cmd.extend(assets)
    
    result = run_command(cmd, f"Create GitHub release {tag}", check=False)
    
    if result.returncode != 0:
        print_error("GitHub release creation failed")
        print("You can create it manually at:")
        print(f"  https://github.com/farman20ali/port-killer/releases/new?tag={tag}")
        return False
    
    print_success(f"GitHub release {tag} created")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Automated release script for kport")
    parser.add_argument("--version", help="Version to release (e.g., 3.1.2)")
    parser.add_argument("--no-pypi", action="store_true", help="Skip PyPI package build")
    parser.add_argument("--no-deb", action="store_true", help="Skip Debian package build")
    parser.add_argument("--no-github", action="store_true", help="Skip GitHub release creation")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    args = parser.parse_args()
    
    print_header("🚀 kport Automated Release")
    
    # Step 1: Read version from setup.py
    current_version = read_version_from_setup()
    if not current_version:
        print_error("Could not read version from setup.py")
        sys.exit(1)
    
    version = args.version or current_version
    tag = f"v{version}"
    
    print(f"\n{Colors.BOLD}Release version:{Colors.END} {version}")
    print(f"{Colors.BOLD}Git tag:{Colors.END} {tag}")
    
    if args.dry_run:
        print_warning("\n🧪 DRY RUN MODE - No changes will be made")
    
    # Step 2: Validate git state
    print_header("Pre-flight Checks")
    
    if not check_git_status():
        print_error("Working directory has uncommitted changes")
        print("Commit or stash changes before releasing")
        sys.exit(1)
    print_success("Working directory is clean")
    
    if check_tag_exists(tag):
        print_error(f"Tag {tag} already exists")
        print("Delete it first or use a different version:")
        print(f"  git tag -d {tag}")
        print(f"  git push origin :refs/tags/{tag}")
        sys.exit(1)
    print_success(f"Tag {tag} is available")
    
    # Step 3: Confirm release
    if not args.dry_run:
        print(f"\n{Colors.YELLOW}Ready to release kport {version}{Colors.END}")
        confirm = input("Proceed? (y/N): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("❌ Release cancelled")
            sys.exit(0)
    
    # Step 4: Create and push git tag
    print_header("Creating Git Tag")
    
    if not args.dry_run:
        run_command(["git", "tag", "-a", tag, "-m", f"Release {version}"], f"Create tag {tag}")
        run_command(["git", "push", "origin", "main"], "Push commits")
        run_command(["git", "push", "origin", "--tags"], "Push tags")
    else:
        print_warning(f"DRY RUN: Would create and push tag {tag}")
    
    # Step 5: Build packages
    pypi_success = True
    deb_success = True
    
    if not args.no_pypi:
        pypi_success = build_pypi_packages(args.dry_run)
    
    if not args.no_deb:
        deb_success = build_debian_package(args.dry_run)
    
    # Step 6: Get release notes
    if not args.no_github and not args.dry_run:
        notes = get_release_notes(version)
    else:
        notes = f"Release {version}"
    
    # Step 7: Create GitHub release
    if not args.no_github:
        create_github_release(version, tag, notes, args.dry_run)
    
    # Summary
    print_header("✅ Release Complete")
    print(f"\n{Colors.BOLD}Version:{Colors.END} {version}")
    print(f"{Colors.BOLD}Tag:{Colors.END} {tag}")
    
    if pypi_success:
        print(f"{Colors.GREEN}✅ PyPI packages built{Colors.END}")
    if deb_success:
        print(f"{Colors.GREEN}✅ Debian package built{Colors.END}")
    
    print(f"\n{Colors.BOLD}Next steps:{Colors.END}")
    
    if not args.no_pypi and pypi_success and not args.dry_run:
        print(f"  1. Upload to PyPI: python3 publish.py (choose option 3 or 5)")
    
    print(f"  2. Check GitHub release: https://github.com/farman20ali/port-killer/releases/tag/{tag}")
    print(f"  3. Test installation:")
    print(f"     pip install kport=={version}")
    
    if not args.dry_run:
        print(f"\n{Colors.GREEN}🎉 Release {version} published!{Colors.END}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Release cancelled by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
