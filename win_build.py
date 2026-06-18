#!/usr/bin/env python3
"""Windows installer builder for kport.

Builds a standalone kport.exe using PyInstaller, then wraps it in an
NSIS installer (.exe setup wizard) using makensis.

Usage (interactive):
    python win_build.py

Usage (automated / CI):
    python win_build.py --build          # PyInstaller + NSIS
    python win_build.py --check          # check prerequisites only
    python win_build.py --pyinstaller    # PyInstaller step only
    python win_build.py --nsis           # NSIS step only (requires kport.exe)
    python win_build.py --dry-run        # preview without executing

Outputs:
    dist/win/kport.exe            — standalone executable
    dist/win/kport-<v>-setup.exe  — installer wizard
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Configure UTF-8 encoding for standard streams on Windows to avoid UnicodeEncodeError
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    # Dynamic path enhancement for Windows build tools
    extra_paths = [
        r"C:\Program Files (x86)\NSIS",
        r"C:\Program Files\NSIS",
        r"C:\ProgramData\chocolatey\bin",
    ]
    path_env = os.environ.get("PATH", "")
    paths = [p.strip() for p in path_env.split(os.pathsep) if p.strip()]
    added = False
    for p in extra_paths:
        if os.path.exists(p) and p not in paths:
            paths.append(p)
            added = True
    if added:
        os.environ["PATH"] = os.pathsep.join(paths)

REPO_ROOT = Path(__file__).resolve().parent
DIST_WIN  = REPO_ROOT / "dist" / "win"
SPEC_FILE = REPO_ROOT / "packaging" / "windows" / "kport.spec"
NSI_FILE  = REPO_ROOT / "packaging" / "windows" / "installer.nsi"

# ── helpers ──────────────────────────────────────────────────────────────────

def _c(text: str, code: str) -> str:
    """Colorise text if stdout is a TTY."""
    if sys.stdout.isatty() and platform.system() != "Windows":
        return f"\033[{code}m{text}\033[0m"
    return text

def ok(msg: str)   -> None: print(_c(f"✅ {msg}", "92"))
def err(msg: str)  -> None: print(_c(f"❌ {msg}", "91"), file=sys.stderr)
def warn(msg: str) -> None: print(_c(f"⚠️  {msg}", "93"))
def step(msg: str) -> None: print(_c(f"\n▶ {msg}", "96"))
def header(msg: str) -> None:
    sep = "=" * 60
    print(_c(f"\n{sep}\n{msg}\n{sep}", "95"))


def run(cmd: list[str], description: str, dry_run: bool = False,
        cwd: Path | None = None) -> bool:
    step(description)
    print("$", " ".join(str(c) for c in cmd))
    if dry_run:
        warn("DRY RUN — skipping execution")
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

# ── checks ───────────────────────────────────────────────────────────────────

def check_prerequisites() -> dict[str, bool]:
    checks: dict[str, bool] = {}

    # Python
    checks["python3"] = True  # we're running inside Python already

    # PyInstaller
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True, check=True,
        )
        checks["pyinstaller"] = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        checks["pyinstaller"] = False

    # NSIS
    checks["makensis"] = command_exists("makensis")

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

    if not checks["pyinstaller"]:
        print("\nInstall PyInstaller:")
        print("  pip install pyinstaller")
    if not checks["makensis"]:
        print("\nInstall NSIS (Windows):")
        print("  https://nsis.sourceforge.io/Download")
        print("  winget install NSIS.NSIS")
        print("  choco install nsis")

    return all_ok

# ── build steps ──────────────────────────────────────────────────────────────

def generate_version_txt(version: str) -> None:
    """Dynamically generate the Windows version.txt resource file."""
    # Convert version string (e.g. "3.2.0") to a 4-tuple of integers (e.g. 3, 2, 0, 0)
    version_digits = [int(d) for d in re.findall(r"\d+", version)[:4]]
    while len(version_digits) < 4:
        version_digits.append(0)
    v_tuple = tuple(version_digits)
    v_str = ".".join(str(d) for d in version_digits)

    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={v_tuple},
    prodvers={v_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [
            StringStruct(u'CompanyName',      u'Farman Ali'),
            StringStruct(u'FileDescription',  u'kport — Cross-platform port inspector and killer'),
            StringStruct(u'FileVersion',      u'{v_str}'),
            StringStruct(u'InternalName',     u'kport'),
            StringStruct(u'LegalCopyright',   u'Copyright (C) 2024 Farman Ali. GNU AGPL v3.'),
            StringStruct(u'OriginalFilename', u'kport.exe'),
            StringStruct(u'ProductName',      u'kport'),
            StringStruct(u'ProductVersion',   u'{v_str}'),
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [0x0409, 1200])])
  ]
)
"""
    version_file = REPO_ROOT / "packaging" / "windows" / "version.txt"
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(content, encoding="utf-8")


def build_pyinstaller(dry_run: bool = False) -> bool:
    header("Building standalone kport.exe (PyInstaller)")
    DIST_WIN.mkdir(parents=True, exist_ok=True)

    if not SPEC_FILE.exists():
        err(f"Spec file not found: {SPEC_FILE}")
        return False

    version = read_version()
    if not dry_run:
        generate_version_txt(version)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--distpath", str(DIST_WIN),
        "--workpath", str(REPO_ROOT / "build" / "pyinstaller_win"),
        str(SPEC_FILE),
    ]
    if not run(cmd, "PyInstaller — bundle kport.exe", dry_run):
        return False

    exe_path = DIST_WIN / "kport.exe"
    if not dry_run and not exe_path.exists():
        err(f"Expected output not found: {exe_path}")
        return False

    if not dry_run:
        ok(f"Standalone exe: {exe_path}")
    return True


def build_nsis(version: str, dry_run: bool = False) -> bool:
    header("Building Windows Installer (NSIS)")

    if not NSI_FILE.exists():
        err(f"NSIS script not found: {NSI_FILE}")
        return False

    exe_src = DIST_WIN / "kport.exe"
    if not dry_run and not exe_src.exists():
        err(f"kport.exe not found at {exe_src}. Run --pyinstaller first.")
        return False

    out_file = DIST_WIN / f"kport-{version}-setup.exe"
    DIST_WIN.mkdir(parents=True, exist_ok=True)

    cmd = [
        "makensis",
        f"/DVERSION={version}",
        f"/DOUTFILE={out_file}",
        f"/DKPORT_EXE={exe_src}",
        str(NSI_FILE),
    ]
    if not run(cmd, "NSIS — compile installer", dry_run):
        return False

    if not dry_run:
        if out_file.exists():
            ok(f"Installer: {out_file}")
            print(f"\nSilent install:  {out_file.name} /S")
            print(f"Normal install:  {out_file.name}")
        else:
            err(f"Installer not found at expected path: {out_file}")
            return False
    return True

# ── interactive menu ─────────────────────────────────────────────────────────

def interactive_menu(version: str) -> None:
    header(f"🪟 kport Windows Build Tool  (v{version})")
    print("What would you like to do?")
    print("  1. Check prerequisites")
    print("  2. Build standalone kport.exe (PyInstaller only)")
    print("  3. Build Windows installer kport-setup.exe (PyInstaller + NSIS)")
    print("  4. NSIS step only (kport.exe must already exist)")
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
        checks = check_prerequisites()
        if not checks["pyinstaller"]:
            err("PyInstaller not found. Install it first: pip install pyinstaller")
            sys.exit(1)
        if not build_pyinstaller():
            sys.exit(1)

    if choice in ("3",):
        checks = check_prerequisites()
        if not checks["makensis"]:
            err("NSIS (makensis) not found. Install from https://nsis.sourceforge.io/")
            sys.exit(1)
        if not build_nsis(version):
            sys.exit(1)

    if choice == "4":
        checks = check_prerequisites()
        if not checks["makensis"]:
            err("NSIS (makensis) not found.")
            sys.exit(1)
        if not build_nsis(version):
            sys.exit(1)

    if choice not in ("0", "1", "2", "3", "4"):
        err("Invalid choice")
        sys.exit(1)

# ── CLI entry-point ──────────────────────────────────────────────────────────

def main() -> None:
    version = read_version()

    parser = argparse.ArgumentParser(
        description="Build kport Windows installer (.exe)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--check",        action="store_true", help="Check prerequisites and exit")
    parser.add_argument("--build",        action="store_true", help="Full build: PyInstaller + NSIS")
    parser.add_argument("--pyinstaller",  action="store_true", help="PyInstaller step only")
    parser.add_argument("--nsis",         action="store_true", help="NSIS step only")
    parser.add_argument("--dry-run",      action="store_true", help="Preview without executing")
    parser.add_argument("--version",      default=version,     help=f"Version string (default: {version})")
    args = parser.parse_args()

    version = args.version

    # --- Non-interactive mode ---
    if args.check:
        checks = check_prerequisites()
        ok_all = print_check_results(checks)
        sys.exit(0 if ok_all else 1)

    if args.pyinstaller or args.build:
        if not build_pyinstaller(args.dry_run):
            sys.exit(1)

    if args.nsis or args.build:
        if not build_nsis(version, args.dry_run):
            sys.exit(1)

    if any([args.check, args.build, args.pyinstaller, args.nsis]):
        return  # non-interactive done

    # --- Interactive mode ---
    interactive_menu(version)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled")
        sys.exit(0)
