# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for kport — Windows standalone .exe
Build: pyinstaller packaging/windows/kport.spec
"""

import sys
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Detect version from pyproject.toml (fallback: setup.py, then __init__.py)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(SPECPATH).resolve().parents[1]

def _read_version() -> str:
    for candidate in [
        REPO_ROOT / "pyproject.toml",
        REPO_ROOT / "setup.py",
        REPO_ROOT / "src" / "kport" / "__init__.py",
    ]:
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"""(?:^version\s*=\s*["']|__version__\s*=\s*["'])([^"']+)""", text, re.MULTILINE)
            if m:
                return m.group(1).strip()
    return "0.0.0"

VERSION = _read_version()

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [str(REPO_ROOT / "__main__.py")],
    pathex=[str(REPO_ROOT / "src")],
    binaries=[],
    datas=[],
    hiddenimports=[
        "kport",
        "kport.cli",
        "kport.formatter",
        "kport.exceptions",
        "kport.docker_engine",
        "kport.inspectors",
        "kport.mcp_server",
        # psutil is optional; include if available
        "psutil",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy stdlib modules not needed for a CLI
        "tkinter",
        "unittest",
        "test",
        "distutils",
        "setuptools",
        "pkg_resources",
        "email",
        "html",
        "http",
        "xmlrpc",
        "pydoc",
        "_bootsubprocess",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="kport",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX disabled — avoids antivirus false positives
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,        # CLI tool — keep console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(REPO_ROOT / "packaging" / "windows" / "version.txt"),
    icon=str(REPO_ROOT / "assets" / "icons" / "windows" / "icon_256_256_ico.ico"),
)
