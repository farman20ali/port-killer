# 🚀 Quick Start Guide — kport v3.2.0

## Installation (Choose One Method)

### ✅ Run directly from source
```bash
python -m kport --help
python -m kport list
```

### 📦 Install globally (Recommended — no admin needed)
```bash
# Install to user directory
pip install --user .
```

After installation:
```bash
kport --version   # kport 3.2.0
kport list        # show all listening ports
```

### 🌍 Install from PyPI
```bash
pip install kport
```

---

## 🎯 Core Commands

```bash
# List all listening ports (local + Docker)
kport list

# Show Docker-published ports only
kport docker

# Inspect a specific port
kport inspect 8080

# Explain why a port is occupied (conflict analysis)
kport explain 8080

# Kill a process on a port (safety-shielded, Docker-aware)
kport kill 8080

# Dry-run: show what would happen without killing
kport kill 8080 --dry-run

# Skip confirmation prompt
kport kill 8080 --yes

# Output in JSON format (CI/automation)
kport kill 8080 --json

# Detect conflicts between Docker and local processes
kport conflicts
```

---

## 👁️ Watch Mode (v3.2.0)

Monitor a port and automatically kill processes that start using it:

```bash
# Watch port 8080 — kill anything that binds to it
kport watch 8080

# Custom poll interval (seconds)
kport watch 8080 --interval 2.5

# Dry-run (print alerts, don't kill)
kport watch 8080 --dry-run

# JSON output for CI pipelines
kport watch 8080 --json
```

---

## 🛡️ Safety Shield (v3.2.0)

Critical ports and processes are protected by default:

```bash
# This will be BLOCKED (port 22 = SSH):
kport kill 22
# → 🛡️ Security Shield Active: Port 22 is a protected port.

# Override when you really need to:
kport kill 22 --bypass-safety
```

**Protected ports by default:** 22, 53, 80, 443, 3306, 5432, 6379, 6443

**Protected processes by default:** systemd, init, docker, sshd, lsass.exe, services.exe

---

## ⚙️ Config File

Create `.kport.json` in your project root (or `~/.kport.json` for global defaults):

```json
{
  "yes": true,
  "dry_run": false,
  "force": false,
  "graceful_timeout": 5,
  "docker_action": "stop",
  "protected_ports": [8080, 9090],
  "protected_processes": ["my-critical-app"]
}
```

---

## 🤖 MCP Server (AI Agent Integration)

Run kport as an MCP server for Claude, Copilot, Cursor, and other AI assistants:

```bash
kport --mcp
```

Add to your Claude Desktop / Cursor config:

```json
{
  "mcpServers": {
    "kport": {
      "command": "kport",
      "args": ["--mcp"]
    }
  }
}
```

**MCP tools available:** `list_ports`, `inspect_port`, `kill_port` (all safety-shielded)

---

  ## 🔧 Legacy Flags (still supported)

  ```bash
  python -m kport -l                  # list all ports
  python -m kport -i 8080             # inspect port
  python -m kport -im 3000 3001 8080  # inspect multiple
  python -m kport -ir 3000-3010       # inspect range
  python -m kport -ip node            # inspect by process name
  python -m kport -k 8080             # kill port
  python -m kport -kp node            # kill by process name
  python -m kport -ka 3000 3001 3002  # kill multiple ports
  python -m kport -kr 3000-3010       # kill port range
  ```

---

## 📤 Packaging and Distribution

```bash
# Build PIP wheel + sdist
python -m build

# Build Windows .exe installer
python win_build.py

# Build macOS .pkg installer
python mac_build.py

# Build Debian .deb package
python deb_publish.py

# Build RPM package
python rpm_build.py
```

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| `README.md` | Main documentation |
| `INSTALL.md` | Detailed installation |
| `PACKAGING.md` | Cross-platform packaging |
| `PUBLISH.md` | PyPI publishing guide |
| `docs/RELEASE_NOTES_3.2.0.md` | What's new in 3.2.0 |
| `CONTRIBUTING.md` | How to contribute |
