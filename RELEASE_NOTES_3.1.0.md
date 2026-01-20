# kport v3.1.0 Release Notes

**Release Date:** January 20, 2026

Cross-platform port inspector and killer with Docker support, safe termination features, and multiple output formats.

---

## 🎉 Highlights

- **Docker-aware port detection** - Automatically detects ports published by Docker containers
- **Safe process termination** - Interactive confirmations with graceful shutdown (SIGTERM) and force option
- **Multiple interfaces** - Both legacy flags (`-k`, `-l`, `-i`) and modern subcommands (`kill`, `list`, `inspect`)
- **JSON output** - Machine-readable output for automation and scripting
- **Hidden PID handling** - Correctly detects when system services hide PIDs (requires elevated privileges)
- **Cross-platform** - Works on Linux, macOS, and Windows with intelligent fallbacks

---

## ✨ Features

### Port Management
- **Inspect ports** - `kport inspect 8080` - Check what's using a specific port
- **Explain ports** - `kport explain 8080` - Get detailed information about port usage
- **Kill processes** - `kport kill 8080` - Safely terminate processes using a port
- **List all ports** - `kport list` - View all listening ports and their processes

### Docker Integration
- **Docker port mapping** - `kport docker` - List all Docker container port mappings
- **Container detection** - Automatically identifies when a port is mapped to a Docker container
- **Container actions** - Stop or kill Docker containers directly from kport

### Safety Features
- **Confirmation prompts** - Interactive confirmation before killing processes
- **Dry-run mode** - Preview actions without executing them (`--dry-run`)
- **Force option** - Send SIGKILL when graceful termination fails (`--force`)
- **Permission detection** - Clear messages when elevated privileges are required

### Conflict Detection
- **Port conflicts** - `kport conflicts` - Find multiple processes trying to use the same port
- **Range scanning** - Check port ranges for conflicts

### Configuration
- **Config file support** - Use `.kport.json` for default settings
- **Config locations** - Project-level, user home, or XDG config directory
- **CLI override** - `--config` flag to specify custom config file

---

## 🐧 Installation

### PyPI (pip)
```bash
pip install kport==3.1.0
# or user install (recommended)
pip install --user kport==3.1.0
```

### Debian/Ubuntu
```bash
wget https://github.com/farman20ali/port-killer/releases/download/v3.1.0/kport_3.1.0-1_all.deb
sudo dpkg -i kport_3.1.0-1_all.deb
```

### From Source
```bash
pip install git+https://github.com/farman20ali/port-killer.git@v3.1.0
```

---

## 📋 Usage Examples

```bash
# List all listening ports
kport list

# Check what's using port 8080
kport inspect 8080

# Get detailed explanation for port 3000
kport explain 3000

# Kill process on port 5000 (with confirmation)
kport kill 5000

# Kill without confirmation
kport kill 8080 --yes

# List Docker port mappings
kport docker

# Find port conflicts
kport conflicts

# JSON output for scripting
kport inspect 8080 --json
```

---

## 🔧 Technical Details

### Dependencies
- **Python:** 3.6 or higher
- **Required:** `psutil >= 5.9.0` (for best cross-platform support)
- **Optional:** Docker CLI (for Docker features)

### Platform Support
- **Linux** - Full support (uses `psutil`, falls back to `lsof`/`ss`/`netstat`)
- **macOS** - Full support (uses `psutil`, falls back to `lsof`)
- **Windows** - Full support (uses `psutil`, falls back to PowerShell/`netstat`)

### Exit Codes
- `0` - Success
- `1` - General error
- `2` - Port not in use or not found
- `3` - Permission denied
- `4` - Port used by Docker container
- `5` - Port is free

---

## 📚 Documentation

- **Installation Guide:** [INSTALL.md](https://github.com/farman20ali/port-killer/blob/main/INSTALL.md)
- **Quick Start:** [QUICKSTART.md](https://github.com/farman20ali/port-killer/blob/main/QUICKSTART.md)
- **Release Guide:** [RELEASE_GUIDE.md](https://github.com/farman20ali/port-killer/blob/main/RELEASE_GUIDE.md)
- **Contributing:** [CONTRIBUTING.md](https://github.com/farman20ali/port-killer/blob/main/CONTRIBUTING.md)

---

## 🐛 Known Issues

- On some Linux systems, detecting PIDs for system services requires `sudo` or root privileges
- Docker detection requires Docker CLI to be installed and accessible in PATH
- Color output may not work on older Windows versions (< Windows 10)

---

## 🙏 Credits

Thanks to all contributors and users who provided feedback and bug reports.

---

## 📝 License

GNU Affero General Public License v3.0 (AGPL-3.0) - see [LICENSE](https://github.com/farman20ali/port-killer/blob/main/LICENSE) for details.

**This license requires sharing source code modifications, even for network/SaaS use.**

---

**Full Changelog:** https://github.com/farman20ali/port-killer/commits/v3.1.0
