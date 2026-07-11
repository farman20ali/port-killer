#!/usr/bin/env python3
"""macOS .pkg installer builder for kport.

Builds a standalone kport binary using PyInstaller, then packages it
into a macOS .pkg installer using pkgbuild and productbuild (both
included in Xcode Command Line Tools).

Usage (interactive):
    python mac_build.py

Usage (automated / CI):
    python mac_build.py --build       # full build: PyInstaller + pkgbuild + productbuild
    python mac_build.py --check       # check prerequisites only
    python mac_build.py --pyinstaller # PyInstaller step only
    python mac_build.py --pkg         # pkg step only (binary must exist)
    python mac_build.py --dry-run     # preview without executing

Output:
    dist/mac/kport           — standalone binary
    dist/mac/kport-<v>.pkg   — installer package
"""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Configure UTF-8 encoding for standard streams on Windows/narrow consoles
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

REPO_ROOT    = Path(__file__).resolve().parents[1]
DIST_MAC     = REPO_ROOT / "dist" / "mac"
SCRIPTS_DIR  = REPO_ROOT / "packaging" / "macos" / "scripts"
DIST_XML     = REPO_ROOT / "packaging" / "macos" / "distribution.xml"
INSTALL_DIR  = "/usr/local/kport"

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

# ── checks ────────────────────────────────────────────────────────────────────

def check_prerequisites() -> dict[str, bool]:
    checks: dict[str, bool] = {}
    checks["python3"] = True  # already running
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True, check=True,
        )
        checks["pyinstaller"] = True
    except Exception:
        checks["pyinstaller"] = False

    checks["pkgbuild"]     = command_exists("pkgbuild")
    checks["productbuild"] = command_exists("productbuild")
    return checks


def print_check_results(checks: dict[str, bool]) -> bool:
    header("Prerequisites Check")
    all_ok = True
    for tool, present in checks.items():
        if present:
            ok(f"{tool} — found")
        else:
            err(f"{tool} — NOT found")
            all_ok = False

    if not checks.get("pyinstaller"):
        print("\nInstall PyInstaller:  pip install pyinstaller")
    if not checks.get("pkgbuild") or not checks.get("productbuild"):
        print("\nInstall Xcode Command Line Tools:")
        print("  xcode-select --install")
    return all_ok

# ── build steps ───────────────────────────────────────────────────────────────

def build_pyinstaller(dry_run: bool = False) -> bool:
    header("Building standalone kport binary (PyInstaller)")
    DIST_MAC.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--console",
        "--name", "kport",
        "--icon", str(REPO_ROOT / "assets" / "icons" / "icon_512_512.png"),
        "--distpath", str(DIST_MAC),
        "--workpath", str(REPO_ROOT / "build" / "pyinstaller_mac"),
        "--paths", str(REPO_ROOT / "src"),
        "--hidden-import", "kport",
        "--hidden-import", "kport.cli",
        "--hidden-import", "kport.formatter",
        "--hidden-import", "kport.exceptions",
        "--hidden-import", "kport.docker_engine",
        "--hidden-import", "kport.inspectors",
        "--hidden-import", "psutil",
        str(REPO_ROOT / "__main__.py"),
    ]
    if not run(cmd, "PyInstaller — bundle kport binary", dry_run):
        return False

    binary = DIST_MAC / "kport"
    if not dry_run and not binary.exists():
        err(f"Expected binary not found: {binary}")
        return False

    ok(f"Binary: {binary}")
    return True


def build_pkg(version: str, dry_run: bool = False) -> Path | None:
    header(f"Building kport-{version}.pkg")

    binary = DIST_MAC / "kport"
    if not dry_run and not binary.exists():
        err(f"Binary not found: {binary}. Run --pyinstaller first.")
        return None

    with tempfile.TemporaryDirectory(prefix="kport-mac-") as td:
        tmp = Path(td)

        # Build a payload root: /usr/local/kport/kport
        payload_root = tmp / "payload"
        install_bin = payload_root / "usr" / "local" / "kport"
        install_bin.mkdir(parents=True)

        if not dry_run:
            shutil.copy2(binary, install_bin / "kport")
            (install_bin / "kport").chmod(0o755)

        component_pkg = tmp / "kport-component.pkg"

        # Step 1: pkgbuild — component package
        pkgbuild_cmd = [
            "pkgbuild",
            "--root",       str(payload_root),
            "--identifier", "com.alienhub.kport",
            "--version",    version,
            "--scripts",    str(SCRIPTS_DIR),
            "--install-location", "/",
            str(component_pkg),
        ]
        if not run(pkgbuild_cmd, "pkgbuild — component package", dry_run):
            return None

        # Patch distribution.xml with actual version
        dist_xml_content = DIST_XML.read_text(encoding="utf-8") if DIST_XML.exists() else ""
        dist_xml_content = dist_xml_content.replace("3.2.0", version)
        # Point pkg-ref to component pkg name
        dist_xml_patched = tmp / "distribution.xml"
        dist_xml_patched.write_text(dist_xml_content, encoding="utf-8")

        DIST_MAC.mkdir(parents=True, exist_ok=True)
        final_pkg = DIST_MAC / f"kport-{version}.pkg"

        # Step 2: productbuild — distribution package
        productbuild_cmd = [
            "productbuild",
            "--distribution", str(dist_xml_patched),
            "--package-path", str(tmp),
            str(final_pkg),
        ]
        if not run(productbuild_cmd, "productbuild — final installer", dry_run):
            return None

        if not dry_run:
            if final_pkg.exists():
                ok(f"Installer: {final_pkg}")
                print(f"\nInstall: double-click {final_pkg.name}")
                print("Then run: kport --version")
            else:
                err(f"Expected .pkg not found: {final_pkg}")
                return None

        return final_pkg

# ── interactive menu ───────────────────────────────────────────────────────────

def interactive_menu(version: str) -> None:
    header(f"🍎 kport macOS Build Tool  (v{version})")

    if platform.system() != "Darwin":
        warn("Not macOS — pkgbuild/productbuild require macOS.")

    print("What would you like to do?")
    print("  1. Check prerequisites")
    print("  2. Build standalone binary (PyInstaller only)")
    print("  3. Full build: binary + .pkg installer")
    print("  4. .pkg step only (binary must already exist)")
    print("  0. Exit")

    choice = input("\nEnter choice (0-4): ").strip()

    if choice == "0":
        print("👋 Goodbye!")
        return

    if choice == "1":
        checks = check_prerequisites()
        print_check_results(checks)
        return

    if choice in ("2", "3"):
        if not build_pyinstaller():
            sys.exit(1)

    if choice in ("3", "4"):
        if not build_pkg(version):
            sys.exit(1)

    if choice not in ("0", "1", "2", "3", "4"):
        err("Invalid choice")
        sys.exit(1)

# ── CLI entry-point ────────────────────────────────────────────────────────────

def main() -> None:
    version = read_version()

    parser = argparse.ArgumentParser(
        description="Build kport macOS .pkg installer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--check",        action="store_true", help="Check prerequisites")
    parser.add_argument("--build",        action="store_true", help="Full build: PyInstaller + .pkg")
    parser.add_argument("--pyinstaller",  action="store_true", help="PyInstaller step only")
    parser.add_argument("--pkg",          action="store_true", help=".pkg step only")
    parser.add_argument("--dry-run",      action="store_true", help="Preview without executing")
    parser.add_argument("--version",      default=version,     help=f"Version (default: {version})")
    args = parser.parse_args()

    version = args.version

    if args.check:
        checks = check_prerequisites()
        ok_all = print_check_results(checks)
        sys.exit(0 if ok_all else 1)

    if args.pyinstaller or args.build:
        if not build_pyinstaller(args.dry_run):
            sys.exit(1)

    if args.pkg or args.build:
        path = build_pkg(version, args.dry_run)
        if not path and not args.dry_run:
            sys.exit(1)

    if any([args.check, args.build, args.pyinstaller, args.pkg]):
        return

    interactive_menu(version)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled")
        sys.exit(0)
