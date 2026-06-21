# Developer Packaging Guide

This guide explains how to package `kport` into platform-native installation packages (Windows `.exe`, Chocolatey `.nupkg`, macOS `.pkg`, Linux `.rpm`, Debian `.deb`, Snap `.snap`, PyPI wheels, and VS Code `.vsix`).

> **Quick start** — use `manage.py` at the repo root for all packaging tasks. Direct script invocation (shown below) is for advanced users and CI pipelines.

---

## Directory Layout

All packaging metadata, specs, and configurations live under `packaging/` and build scripts under `scripts/`:

```
port-killer/
├── manage.py                   # Universal developer entrypoint  ← START HERE
├── packaging/
│   ├── windows/
│   │   ├── kport.spec          # PyInstaller bundle specification
│   │   ├── installer.nsi       # NSIS installer script
│   │   ├── version.txt         # Windows PE metadata resource
│   │   └── EnvVarUpdate.nsh    # PATH editor dependency for NSIS
│   ├── macos/
│   │   ├── distribution.xml    # productbuild installer distribution
│   │   └── scripts/postinstall # post-installation launcher symlinker
│   ├── linux/
│   │   └── kport.spec.template # RPM packaging spec template
│   ├── snap/
│   │   ├── snapcraft.yaml.template
│   │   └── launcher            # Snap app entrypoint wrapper
│   └── chocolatey/
│       ├── kport.nuspec.template
│       └── tools/chocolateyinstall.ps1.template
├── scripts/
│   ├── build_win.py            # Windows builder (PyInstaller + NSIS)
│   ├── build_mac.py            # macOS builder (PyInstaller + pkgbuild)
│   ├── build_snap.py           # Snap builder (snapcraft)
│   ├── build_choco.py          # Chocolatey builder (.nupkg)
│   ├── build_rpm.py            # RPM builder (rpmbuild)
│   ├── build_deb.py            # Debian builder (dpkg-buildpackage)
│   ├── build_packages.py       # Unified multi-target orchestrator
│   ├── publish_pypi.py         # PyPI uploader (twine)
│   └── publish_snap.py         # Snap Store publisher
└── vscode-extension/           # VS Code extension (MCP + port commands)
```

---

## Tool Prerequisites

Each package format relies on specific compilation tools. Run the prerequisite check before building:

```bash
python manage.py build --check
```

### 1. Python Environment
```bash
python manage.py setup   # installs all dev/packaging dependencies
```

### 2. Windows (`.exe` Installer)
- **PyInstaller**: installed via `python manage.py setup`
- **NSIS (Nullsoft Scriptable Install System)**:
  - Via winget: `winget install NSIS.NSIS`
  - Via Chocolatey: `choco install nsis`
  - Download: [nsis.sourceforge.io](https://nsis.sourceforge.io/Download)

### 3. macOS (`.pkg` Installer)
- **PyInstaller**: installed via `python manage.py setup`
- **Xcode Command Line Tools** (includes `pkgbuild` and `productbuild`):
  ```bash
  xcode-select --install
  ```

### 4. Debian / Ubuntu (`.deb` Package)
- **dpkg tools**: Standard on Debian/Ubuntu (`dpkg-deb`, `fakeroot`)

### 5. RHEL / Fedora / CentOS / openSUSE (`.rpm` Package)
- **rpmbuild**:
  - Fedora/RHEL: `sudo dnf install rpm-build python3-devel`
  - openSUSE: `sudo zypper install rpm-build`

### 6. Snap (`.snap` Package)

> **Important — Classic Confinement and Snap Store Approval**
>
> `kport` requires **`confinement: classic`** because it must send OS signals
> (SIGTERM, SIGKILL) to arbitrary host processes. Strict sandboxing prevents
> this even with the `process-control` plug connected.
>
> Classic confinement requires **manual review and approval** from the Snap
> Store team before you can release to the stable channel:
> 1. Build locally: `python manage.py build --snap`
> 2. Test install: `sudo snap install dist/snap/kport_*.snap --classic --dangerous`
> 3. Submit a store request at: https://forum.snapcraft.io/c/store-requests/
>    — explain that `kport` is a CLI process manager that must signal host PIDs.
>
> `devmode` is **not** a suitable alternative for distribution — it cannot
> be released to the stable channel and does not appear in search results.
> Prefer the `.deb`, `.rpm`, or PyPI package for Linux distribution until
> Store approval is granted.

```bash
python manage.py build --snap
# or directly:
python scripts/build_snap.py --check    # verify snapcraft is installed
python scripts/build_snap.py --build    # build .snap
python scripts/build_snap.py --dry-run  # preview snapcraft.yaml only
```

### 7. Chocolatey (`.nupkg` Package)
- **Chocolatey CLI** (Windows): [chocolatey.org/install](https://chocolatey.org/install)
- The `.nupkg` downloads the installer from the GitHub release URL at install time — no embedded `.exe`.
- A checksum of the GitHub release installer is required:

```powershell
# Option A — compute from local build:
python manage.py build --win
python manage.py build --choco --installer dist/win/kport-3.2.3-setup.exe

# Option B — provide checksum directly (from CI artifact):
python scripts/build_choco.py --build --checksum <SHA256_HEX>
```

### 8. VS Code Extension (`.vsix`)
- **Node.js 20+** and npm

---

## Building Packages with `manage.py`

```bash
# Check all tool prerequisites first:
python manage.py build --check

# Build all packages for the current platform:
python manage.py build --all

# Build specific targets:
python manage.py build --win
python manage.py build --win --choco
python manage.py build --deb --rpm --snap
python manage.py build --pypi

# Preview without writing files:
python manage.py build --all --dry-run
```

---

## CI/CD and Release Workflow

All native packages are fully automated in the release pipeline:
1. **Workflow Trigger**: When a new tag (e.g. `v3.2.3`) is pushed to GitHub, the `.github/workflows/build-packages.yml` pipeline triggers.
2. **Parallel Building**: The workflow spins up separate runners in parallel:
   - `windows-latest` → Builds `.exe` installer + Chocolatey `.nupkg`
   - `macos-latest` → Builds `.pkg` installer
   - `ubuntu-latest` → Builds `.deb`, `.rpm`, `.snap`, and PyPI packages
3. **Automatic Release Attachment**: The pipeline gathers all generated packages and uploads them to the GitHub release page.
