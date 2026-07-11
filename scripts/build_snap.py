#!/usr/bin/env python3
"""Snap package builder for kport.

Builds a .snap package using snapcraft from packaging/snap/snapcraft.yaml.template.

Usage (automated / CI):
    python snap_build.py --build
    python snap_build.py --check
    python snap_build.py --dry-run

Output:
    dist/snap/kport_<version>_amd64.snap  (or arm64 on ARM runners)
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

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_SNAP = REPO_ROOT / "dist" / "snap"
SNAP_DIR = REPO_ROOT / "packaging" / "snap"
TEMPLATE = SNAP_DIR / "snapcraft.yaml.template"


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


def check_prerequisites() -> dict[str, bool]:
    return {
        "snapcraft": command_exists("snapcraft"),
        "python3": command_exists("python3") or command_exists("python"),
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

    if not checks["snapcraft"]:
        print("\nInstall snapcraft:")
        print("  sudo snap install snapcraft --classic")
        print("  # or: sudo apt-get install snapcraft")
    return all_ok


def _prepare_build_dir(version: str, build_root: Path) -> Path:
    """Create a snapcraft project directory with generated yaml and source copies."""
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Snap template not found: {TEMPLATE}")

    yaml_content = TEMPLATE.read_text(encoding="utf-8").replace("{VERSION}", version)
    (build_root / "snapcraft.yaml").write_text(yaml_content, encoding="utf-8")

    for name in ("launcher",):
        src = SNAP_DIR / name
        if src.exists():
            dest = build_root / name
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dest)
                dest.chmod(0o755)

    for rel in ("src/kport", "__main__.py", "assets"):
        src = REPO_ROOT / rel
        dest = build_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)

    return build_root


def build_snap(version: str, dry_run: bool = False) -> Path | None:
    header(f"Building kport {version} snap")

    with tempfile.TemporaryDirectory(prefix="kport-snap-") as td:
        build_root = _prepare_build_dir(version, Path(td))

        cmd = ["snapcraft", "pack", "--destructive-mode"]
        print("$", " ".join(cmd), f"(cwd={build_root})")

        if dry_run:
            warn("DRY RUN — skipping snapcraft")
            print("\nGenerated snapcraft.yaml:\n" + (build_root / "snapcraft.yaml").read_text())
            return None

        result = subprocess.run(cmd, cwd=str(build_root))
        if result.returncode != 0:
            err("snapcraft pack failed")
            return None

        snaps = list(build_root.glob("*.snap"))
        if not snaps:
            err("No .snap produced")
            return None

        DIST_SNAP.mkdir(parents=True, exist_ok=True)
        dest = DIST_SNAP / snaps[0].name
        shutil.copy2(snaps[0], dest)
        ok(f"Snap built: {dest}")
        print("\nInstall with:")
        print(f"  sudo snap install {dest} --dangerous")
        return dest


def main() -> None:
    version = read_version()

    parser = argparse.ArgumentParser(
        description="Build kport Snap package",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--check", action="store_true", help="Check prerequisites and exit")
    parser.add_argument("--build", action="store_true", help="Build .snap package")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--version", default=version, help=f"Version string (default: {version})")
    args = parser.parse_args()

    version = args.version

    if args.check:
        ok_all = print_check_results(check_prerequisites())
        sys.exit(0 if ok_all else 1)

    if args.build:
        if sys.platform == "win32" and not args.dry_run:
            err("Snap builds require Linux")
            sys.exit(1)
        checks = check_prerequisites()
        if not checks["snapcraft"] and not args.dry_run:
            err("snapcraft not found")
            sys.exit(1)
        path = build_snap(version, args.dry_run)
        sys.exit(0 if path or args.dry_run else 1)

    parser.print_help()
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled")
        sys.exit(0)
