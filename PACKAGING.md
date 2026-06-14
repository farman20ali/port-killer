# Developer Packaging Guide

This guide explains how to package `kport` into platform-native installation packages (Windows `.exe`, Chocolatey `.nupkg`, macOS `.pkg`, Linux `.rpm`, Debian `.deb`, Snap `.snap`, PyPI wheels, and VS Code `.vsix`).

---

## Directory Layout

All packaging metadata, specs, and configurations live under `packaging/`:

```
port-killer/
├── packaging/
│   ├── windows/
│   │   ├── kport.spec          # PyInstaller bundle specification
│   │   ├── installer.nsi       # NSIS installer script
│   │   ├── version.txt         # Windows PE metadata resource
│   │   └── EnvVarUpdate.nsh    # PATH editor dependency for NSIS
│   ├── macos/
│   │   ├── distribution.xml    # productbuild installer distribution
│   │   └── scripts/
│   │       └── postinstall     # post-installation launcher symlinker
│   ├── linux/
│   │   └── kport.spec.template # RPM packaging spec template
│   ├── snap/
│   │   ├── snapcraft.yaml.template
│   │   └── launcher            # Snap app entrypoint wrapper
│   └── chocolatey/
│       ├── kport.nuspec.template
│       └── tools/chocolateyinstall.ps1.template
├── win_build.py                # Standalone Windows builder
├── mac_build.py                # Standalone macOS builder
├── snap_build.py               # Standalone Snap builder
├── choco_build.py              # Standalone Chocolatey builder
├── rpm_build.py                # Standalone RPM builder
├── deb_publish.py              # Standalone Debian builder
├── publish.py                  # Standalone PyPI publisher
├── vscode-extension/           # VS Code extension (MCP + port commands)
├── build_packages.py           # Unified orchestrator (with --all)
└── release.py                  # Release orchestrator (prepares tag & pushes to GitHub)
```

---

## Tool Prerequisites

Each package format relies on specific compilation tools. To test or compile packages locally, ensure the relevant utilities are installed.

### 1. Python Environment
Install the Python build dependencies:
```bash
pip install -e .[packaging]
```
*(This installs `pyinstaller` and `build` as defined in `pyproject.toml`)*.

### 2. Windows (`.exe` Installer)
*   **PyInstaller**: Installed via `pip`.
*   **NSIS (Nullsoft Scriptable Install System)**:
    *   Via winget: `winget install NSIS.NSIS`
    *   Via Chocolatey: `choco install nsis`
    *   Or download from: [nsis.sourceforge.io](https://nsis.sourceforge.io/Download)

### 3. macOS (`.pkg` Installer)
*   **PyInstaller**: Installed via `pip`.
*   **Xcode Command Line Tools** (includes `pkgbuild` and `productbuild`):
    ```bash
    xcode-select --install
    ```

### 4. Debian / Ubuntu (`.deb` Package)
*   **dpkg tools**: Standard on Debian/Ubuntu systems (`dpkg-deb`, `fakeroot`).

### 5. RHEL / Fedora / CentOS / openSUSE (`.rpm` Package)
*   **rpmbuild**:
    *   Fedora/RHEL: `sudo dnf install rpm-build python3-devel`
    *   openSUSE: `sudo zypper install rpm-build`

### 6. Snap (`.snap` Package)
*   **snapcraft**:
    ```bash
    sudo snap install snapcraft --classic
    ```

### 7. Chocolatey (`.nupkg` Package)
*   **Chocolatey CLI** (Windows): [chocolatey.org/install](https://chocolatey.org/install)
*   Requires a built Windows installer (`dist/win/kport-*-setup.exe`)

### 8. VS Code Extension (`.vsix`)
*   **Node.js 20+** and npm
*   Build from `vscode-extension/` with `npm run package`

---

## Standalone Build Helpers

Each script can be run interactively (with menus) or automated (for CI).

### Windows Setup: `win_build.py`
```powershell
python win_build.py --check          # Check if tools are installed
python win_build.py --build          # Full build: PyInstaller + NSIS
python win_build.py --pyinstaller    # PyInstaller step only (outputs dist/win/kport.exe)
python win_build.py --nsis           # NSIS wizard compile step only
python win_build.py --dry-run        # Preview steps without writing files
```

### macOS Package: `mac_build.py`
```bash
python mac_build.py --check          # Check tools (pkgbuild, productbuild, etc.)
python mac_build.py --build          # Full build (PyInstaller + pkgbuild + productbuild)
python mac_build.py --pyinstaller    # PyInstaller step only (outputs dist/mac/kport)
python mac_build.py --pkg            # package compilation step only
python mac_build.py --dry-run        # Preview steps without writing files
```

### RPM Package: `rpm_build.py`
```bash
python rpm_build.py --check          # Check for rpmbuild
python rpm_build.py --build          # Build .rpm from spec template
python rpm_build.py --dry-run        # Preview generated spec file and compile command
```

### Snap Package: `snap_build.py`
```bash
python snap_build.py --check         # Check for snapcraft
python snap_build.py --build         # Build .snap (classic confinement)
python snap_build.py --dry-run       # Preview generated snapcraft.yaml
```

### Chocolatey Package: `choco_build.py`
```powershell
python choco_build.py --check        # Check for choco CLI
python win_build.py --build          # Build installer first
python choco_build.py --build        # Wrap installer in .nupkg
```

---

## Unified Orchestrator: `build_packages.py`

Use `build_packages.py` to trigger multiple targets or automatically build everything supported on the current system host.

```bash
# Build all packages appropriate for the current platform:
#   Windows  -> .exe installer + Chocolatey + PyPI packages
#   macOS    -> .pkg installer + PyPI packages
#   Linux    -> .deb + .rpm + .snap + PyPI packages
python build_packages.py --all

# Preview what will be built (highly recommended for debugging pipelines):
python build_packages.py --all --dry-run

# Check all target tools:
python build_packages.py --all --check

# Target specific packages explicitly:
python build_packages.py --win --rpm

# List all compiled artifacts currently in dist/:
python build_packages.py --list-outputs
```

---

## CI/CD and Release Workflow

All native packages are fully automated in the release pipeline:
1.  **Workflow Trigger**: When a new tag (e.g. `v3.2.0`) is pushed to GitHub, the `.github/workflows/build-packages.yml` pipeline triggers.
2.  **Parallel Building**: The workflow spins up separate runners in parallel:
    *   `windows-latest` -> Builds `.exe` installer + Chocolatey `.nupkg`.
    *   `macos-latest` -> Builds `.pkg` installer.
    *   `ubuntu-latest` -> Builds `.deb`, `.rpm`, `.snap`, and PyPI packages.
    *   `vscode-extension.yml` -> Builds `.vsix` on tag pushes.
3.  **Automatic Release Attachment**: The pipeline gathers all generated packages and uploads them to the GitHub release page.
