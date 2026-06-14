#!/usr/bin/env python3
"""Chocolatey package builder for kport.

Wraps the Windows NSIS installer (.exe) in a Chocolatey .nupkg.

Usage (automated / CI):
    python choco_build.py --build
    python choco_build.py --build --installer dist/win/kport-3.2.2-setup.exe
    python choco_build.py --check

Output:
    dist/choco/kport.{version}.nupkg
"""

from __future__ import annotations

import argparse
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
DIST_CHOCO = REPO_ROOT / "dist" / "choco"
CHOCO_DIR = REPO_ROOT / "packaging" / "chocolatey"
NUSPEC_TEMPLATE = CHOCO_DIR / "kport.nuspec.template"
INSTALL_TEMPLATE = CHOCO_DIR / "tools" / "chocolateyinstall.ps1.template"


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


def header(msg: str) -> None:
    sep = "=" * 60
    print(_c(f"\n{sep}\n{msg}\n{sep}", "95"))


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
                text,
                re.MULTILINE,
            )
            if m:
                return m.group(1).strip()
    return "0.0.0"


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def find_installer(version: str, explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit)
        return path if path.exists() else None

    matches = sorted((REPO_ROOT / "dist" / "win").glob(f"kport-{version}-setup.exe"))
    if matches:
        return matches[-1]

    matches = sorted((REPO_ROOT / "dist" / "win").glob("kport-*-setup.exe"))
    return matches[-1] if matches else None


def check_prerequisites() -> dict[str, bool]:
    return {"choco": command_exists("choco")}


def print_check_results(checks: dict[str, bool]) -> bool:
    header("Prerequisites Check")
    all_ok = True
    for tool, present in checks.items():
        if present:
            ok(f"{tool} — found")
        else:
            err(f"{tool} — NOT found")
            all_ok = False

    if not checks["choco"]:
        print("\nInstall Chocolatey CLI:")
        print("  https://chocolatey.org/install")
        print("  # or on CI: choco is pre-installed on windows-latest runners")
    return all_ok


def build_choco(version: str, installer: Path, dry_run: bool = False) -> Path | None:
    header(f"Building kport {version} Chocolatey package")

    if not NUSPEC_TEMPLATE.exists() or not INSTALL_TEMPLATE.exists():
        err("Chocolatey templates missing in packaging/chocolatey/")
        return None

    with tempfile.TemporaryDirectory(prefix="kport-choco-") as td:
        pkg_root = Path(td) / f"kport.{version}"
        tools_dir = pkg_root / "tools"
        tools_dir.mkdir(parents=True)

        nuspec = NUSPEC_TEMPLATE.read_text(encoding="utf-8").replace("{VERSION}", version)
        (pkg_root / "kport.nuspec").write_text(nuspec, encoding="utf-8")

        install_ps1 = INSTALL_TEMPLATE.read_text(encoding="utf-8").replace("{VERSION}", version)
        (tools_dir / "chocolateyinstall.ps1").write_text(install_ps1, encoding="utf-8")

        dest_installer = tools_dir / installer.name
        if dry_run:
            warn(f"DRY RUN — would copy {installer} → {dest_installer}")
        else:
            shutil.copy2(installer, dest_installer)

        cmd = ["choco", "pack", str(pkg_root / "kport.nuspec"), "--output-directory", str(DIST_CHOCO)]
        print("$", " ".join(cmd))

        if dry_run:
            warn("DRY RUN — skipping choco pack")
            return None

        DIST_CHOCO.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(cmd, cwd=str(REPO_ROOT))
        if result.returncode != 0:
            err("choco pack failed")
            return None

        nupkgs = sorted(DIST_CHOCO.glob(f"kport.{version}.nupkg"))
        if not nupkgs:
            nupkgs = sorted(DIST_CHOCO.glob("kport.*.nupkg"))
        if not nupkgs:
            err("No .nupkg produced")
            return None

        ok(f"Chocolatey package built: {nupkgs[-1]}")
        print("\nTest locally with:")
        print(f"  choco install {nupkgs[-1]} -s {DIST_CHOCO} -y")
        return nupkgs[-1]


def main() -> None:
    version = read_version()

    parser = argparse.ArgumentParser(
        description="Build kport Chocolatey package",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--check", action="store_true", help="Check prerequisites and exit")
    parser.add_argument("--build", action="store_true", help="Build .nupkg")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--installer", default=None, help="Path to kport-*-setup.exe")
    parser.add_argument("--version", default=version, help=f"Version string (default: {version})")
    args = parser.parse_args()

    version = args.version

    if args.check:
        ok_all = print_check_results(check_prerequisites())
        sys.exit(0 if ok_all else 1)

    if args.build:
        if sys.platform != "win32" and not args.dry_run:
            warn("Chocolatey packaging is intended for Windows hosts.")
            warn("On Linux/macOS use --dry-run or run on a Windows CI runner.")

        checks = check_prerequisites()
        if not checks["choco"] and not args.dry_run:
            err("choco not found")
            sys.exit(1)

        installer = find_installer(version, args.installer)
        if not installer and not args.dry_run:
            err(
                "Windows installer not found. Build it first:\n"
                "  python win_build.py --build\n"
                "  # or pass --installer path/to/kport-*-setup.exe"
            )
            sys.exit(1)
        if not installer and args.dry_run:
            installer = REPO_ROOT / "dist" / "win" / f"kport-{version}-setup.exe"

        path = build_choco(version, installer, args.dry_run)
        sys.exit(0 if path or args.dry_run else 1)

    parser.print_help()
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled")
        sys.exit(0)
