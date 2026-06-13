# 🔪 kport - Cross-Platform Port Inspector and Killer

[![Version](https://img.shields.io/badge/version-3.2.0-blue.svg)](https://github.com/farman20ali/port-killer)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](https://github.com/farman20ali/port-killer)

A powerful, cross-platform command-line tool to inspect, kill, and monitor processes using specific ports — with **AI safety shields**, **Watch Mode**, **Docker awareness**, and an **MCP server** for AI agent integration.

## ✨ Features

### Core
- 🔍 **Inspect ports** - Find which process is using a specific port
- 🔎 **Inspect multiple ports** - Check multiple ports at once
- 🔍 **Inspect port range** - Scan a range of ports (e.g., 3000-3010)
- 🔎 **Inspect by process name** - Find all processes matching a name and their ports
- 🔪 **Kill processes** - Terminate processes using specific ports
- 💥 **Kill port range** - Terminate processes on a range of ports
- 🔫 **Kill multiple ports** - Kill processes on multiple ports at once
- 🎯 **Kill by process name** - Kill all processes matching a name (e.g., "node", "python")
- 📋 **List all ports** - View all listening ports and their processes
- 🐳 **Docker-aware** - Detect ports published by Docker containers (even when you don't see a host process)
- 🎨 **Colorized output** - Easy-to-read colored terminal output
- ✅ **Confirmation prompts** - Safety confirmation before killing processes
- 🌍 **Cross-platform** - Works on Windows, Linux, and macOS

### Phase 2 Pro (v3.2.0)
- 👁️ **Watch Mode** - Monitor a port in real-time and auto-kill on new connections
- 🛡️ **Safety Shield** - Block kills on critical system ports (SSH, DNS, DB, K8s) and protected processes by default
- ⚙️ **Config File** - Set persistent defaults via `.kport.json` (project, home, or global)
- 🔓 **Bypass Safety** - Override safety shields with `--bypass-safety` when needed
- 🤖 **MCP Server** - Model Context Protocol server for AI agent integration (Claude, Copilot, Cursor, etc.)
- 📦 **Cross-platform packaging** - Native builds for Windows (`.exe`), macOS (`.pkg`), Debian (`.deb`), and RPM

## 📦 Installation

Pre-compiled platform-native packages are available on the [GitHub Releases](https://github.com/farman20ali/port-killer/releases) page.

| Platform | Format | Quick Install |
|---|---|---|
| 🪟 **Windows** | `.exe` Setup Wizard | Download and run `kport-setup.exe` (adds to PATH) |
| 🍎 **macOS** | `.pkg` Installer | Download and run `kport.pkg` |
| 🐧 **Debian / Ubuntu** | `.deb` Package | `sudo dpkg -i kport_*.deb` |
| 🐧 **RHEL / Fedora** | `.rpm` Package | `sudo rpm -i kport-*.rpm` |
| 🌍 **Python (Any OS)** | PyPI Package | `pip install --user kport` |

---

### Installing via pip (PyPI)

```bash
# Recommended: Install to user directory
pip install --user kport

# Or install system-wide (requires admin/sudo)
pip install kport
```

### Install from GitHub

```bash
pip install --user git+https://github.com/farman20ali/port-killer.git
```

### Install from Source

```bash
# Clone the repository
git clone https://github.com/farman20ali/port-killer.git
cd port-killer

# Install to user directory (recommended)
pip install --user .
```

### Run Without Installing

```bash
python kport.py -h
```

> 💡 **Tip:** If the `kport` command doesn't work after installation, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
>
> 📖 For detailed platform installation options, see [INSTALL.md](INSTALL.md)
>
> 🛠️ For packaging development and local compilation instructions, see [PACKAGING.md](PACKAGING.md)

## 🚀 Usage

### Core commands (Docker-aware by default)

```bash
# Inspect a port (local or docker)
kport inspect 8080

# Explain why a port is blocked
kport explain 8080

# Safely free a port (will offer docker stop/restart/remove if needed)
kport kill 8080

# List ports (local + docker)
kport list

# List docker published ports
kport docker

# Detect port conflicts (docker + local)
kport conflicts
```

> Note: `--json`, `--dry-run`, `--yes`, and `--debug` work with all subcommands.

### 👁️ Watch Mode (v3.2.0)

Continuously monitor a port and automatically kill any process that starts using it:

```bash
# Watch port 8080 and auto-kill any process that binds to it (check every 1s)
kport watch 8080

# Watch with custom interval (every 2.5 seconds)
kport watch 8080 --interval 2.5

# Watch in dry-run mode (just print alerts, don't kill)
kport watch 8080 --dry-run

# Watch with JSON output (for CI/automation)
kport watch 8080 --json
```

### 🛡️ Safety Shield (v3.2.0)

The Safety Shield prevents accidental termination of critical system services:

```bash
# This will be BLOCKED by the Safety Shield (port 22 = SSH):
kport kill 22
# Output: 🛡️ Security Shield Active: Port 22 is a protected port.

# Override the shield when you REALLY need to (use with caution):
kport kill 22 --bypass-safety

# The shield also protects critical processes:
kport kill 8080
# Output if sshd or docker is found: 🛡️ Security Shield: critical process 'docker' ...
```

**Default protected ports:** `22` (SSH), `53` (DNS), `80` (HTTP), `443` (HTTPS), `3306` (MySQL), `5432` (PostgreSQL), `6379` (Redis), `6443` (Kubernetes API)

**Default protected processes:** `systemd`, `init`, `docker`, `dockerd`, `sshd`, `explorer.exe`, `lsass.exe`, `services.exe`

### 🤖 MCP Server (AI Agent Integration)

Run kport as an MCP server so AI assistants can inspect and free ports on your behalf:

```bash
# Start the MCP server (stdio transport)
kport --mcp
# or
python -m kport.mcp_server
```

**Available MCP tools:**
- `list_ports` — List all active listening ports (local + Docker)
- `inspect_port` — Detailed info about a specific port
- `kill_port` — Free a port (always respects the Safety Shield)

Configure in Claude Desktop / Cursor / VS Code Copilot:

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

### Why a port may show without PID

On Linux, some ports may appear as `LISTEN` but the owning PID/process name is not visible without elevated privileges (common with system services).

If you see `local-unknown` in `inspect` / `explain`, try:

```bash
sudo -E kport inspect 6379
sudo -E kport explain 6379
```

If you installed with `pip install --user kport`, `sudo` may not find `kport` because root's `PATH` doesn't include your user scripts directory.

Alternatives:

```bash
# Option 1: keep your PATH when using sudo
sudo -E "$HOME/.local/bin/kport" inspect 6379

# Option 2: run the module via the system python (when working from repo)
sudo -E python3 kport.py inspect 6379
```

### ⚙️ Config file support

Set persistent defaults via a JSON config file (searched in this priority order):

1. `.kport.json` (current directory — project-level)
2. `~/.kport.json` (user-level)
3. `~/.config/kport/config.json` (XDG-compliant)

**Full example config:**

```json
{
  "yes": true,
  "dry_run": false,
  "force": false,
  "graceful_timeout": 5,
  "docker_action": "stop",
  "protected_ports": [8080, 9090],
  "protected_processes": ["my-critical-app", "postgres"]
}
```

> **Note:** Setting `protected_ports` or `protected_processes` in your config **replaces** (not extends) the default Safety Shield lists.

### Inspect a port

Find out which process is using a specific port:

```bash
kport -i 8080
```

Example output:
```
🔍 Inspecting port 8080...

✓ Port 8080 is being used by PID 12345

Process Information:
──────────────────────────────────────────────────
PID: 12345
Image Name: node.exe
Session Name: Console
Mem Usage: 45,678 K
```

### Inspect by process name

Find all processes matching a name and see what ports they're using:

```bash
kport -ip node
```

Example output:
```
🔍 Inspecting processes matching 'node'...

Found 3 connection(s) for processes matching 'node':

PID        Process                   Port       State          
──────────────────────────────────────────────────────────────────────
12345      node.exe                  3000       LISTENING      
                                     3001       LISTENING      
12346      node.exe                  8080       LISTENING      

✓ Total processes found: 2
✓ Total connections: 3
```

### Inspect multiple ports

Check multiple ports at once:

```bash
kport -im 3000 3001 8080 8081
```

Example output:
```
🔍 Inspecting 4 port(s)...

Port       PID        Process                       
────────────────────────────────────────────────────────────
3000       12345      node.exe                      
3001       12346      node.exe                      
8080       12347      python.exe                    

✓ Found processes on 3/4 port(s)
```

### Inspect port range

Scan a range of ports:

```bash
kport -ir 3000-3010
```

Example output:
```
🔍 Inspecting port range 3000-3010 (11 ports)...

Port       PID        Process                       
────────────────────────────────────────────────────────────
3000       12345      node.exe                      
3001       12346      node.exe                      
3005       12347      python.exe                    

✓ Found processes on 3/11 port(s) in range
```

### Kill a process on a port

Terminate the process using a specific port:

```bash
kport -k 8080
```

Example output:
```
🔪 Attempting to kill process on port 8080...

Found PID 12345 using port 8080

Process to be terminated:
PID: 12345
Image Name: node.exe

Are you sure you want to kill this process? (y/N): y

✓ Successfully killed process 12345
Port 8080 is now free.
```

### List all listening ports

View all active listening ports and their associated processes:

```bash
kport -l
```

Example output:
```
📋 Listing all active ports...

Protocol   Local Address            State           PID       
──────────────────────────────────────────────────────────────────────
TCP        0.0.0.0:80               LISTENING       1234      
TCP        0.0.0.0:443              LISTENING       1234      
TCP        0.0.0.0:3000             LISTENING       5678      
TCP        0.0.0.0:8080             LISTENING       9012
```

### Kill by process name

Kill all processes matching a specific name:

```bash
kport -kp node
```

Example output:
```
🔪 Killing all processes matching 'node'...

Found 3 process(es) matching 'node':
──────────────────────────────────────────────────
  PID 12345: node.exe
  PID 12346: node.exe
  PID 12347: node.exe

Are you sure you want to kill 3 process(es)? (y/N): y

✓ Killed PID 12345
✓ Killed PID 12346
✓ Killed PID 12347

✓ Successfully killed 3/3 process(es)
```

### Kill multiple ports at once

Kill processes on multiple ports simultaneously:

```bash
kport -ka 3000 3001 3002
```

Example output:
```
🔪 Killing processes on 3 port(s)...

Found processes on 3 port(s):
──────────────────────────────────────────────────
  Port 3000: PID 12345 (node.exe)
  Port 3001: PID 12346 (node.exe)
  Port 3002: PID 12347 (python.exe)

Are you sure you want to kill 3 process(es)? (y/N): y

✓ Killed process on port 3000 (PID 12345)
✓ Killed process on port 3001 (PID 12346)
✓ Killed process on port 3002 (PID 12347)

✓ Successfully killed 3/3 process(es)
Ports freed: 3000, 3001, 3002
```

### Kill port range

Kill all processes on a range of ports:

```bash
kport -kr 3000-3010
```

Example output:
```
🔪 Killing processes on port range 3000-3010 (11 ports)...

Found processes on 3 port(s) in range:
──────────────────────────────────────────────────
  Port 3000: PID 12345 (node.exe)
  Port 3001: PID 12346 (node.exe)
  Port 3005: PID 12347 (python.exe)

Are you sure you want to kill 3 process(es)? (y/N): y

✓ Killed process on port 3000 (PID 12345)
✓ Killed process on port 3001 (PID 12346)
✓ Killed process on port 3005 (PID 12347)

✓ Successfully killed 3/3 process(es)
Ports freed: 3000, 3001, 3005
```

### Show help

```bash
kport -h
```

### Show version

```bash
kport -v
```

## 📚 Command-Line Reference

### Subcommands (Recommended)

| Subcommand | Description |
|------------|-------------|
| `kport list` | List all listening ports (local + Docker) |
| `kport inspect PORT` | Inspect port (local or Docker) |
| `kport explain PORT` | Explain why a port is occupied (with conflict analysis) |
| `kport kill PORT` | Free a port (safety-shielded, Docker-aware) |
| `kport watch PORT` | Monitor port in real-time and auto-kill on activity |
| `kport docker` | List Docker-published ports |
| `kport conflicts` | Detect port conflicts between Docker and local processes |

### Subcommand Flags

| Flag | Commands | Description |
|------|----------|-------------|
| `--json` | all | Output results as JSON |
| `--dry-run` | kill, watch | Simulate actions without killing |
| `--yes` | kill, watch | Skip confirmation prompts |
| `--force` | kill, watch | Force kill (SIGKILL after SIGTERM) |
| `--debug` | all | Enable verbose debug output |
| `--bypass-safety` | kill, watch | Override Safety Shield for protected ports/processes |
| `--interval SECS` | watch | Poll interval in seconds (default: 1.0) |
| `--graceful-timeout SECS` | kill, watch | Seconds to wait for graceful shutdown (default: 3.0) |
| `--docker-action` | kill | Docker action: `stop`, `restart`, or `rm` |
| `--mcp` | (root flag) | Start the MCP JSON-RPC server on stdio |

### Legacy Flags (still supported)

| Option | Long Form | Description |
|--------|-----------|-------------|
| `-i PORT` | `--inspect PORT` | Inspect which process is using the specified port |
| `-im PORT [PORT ...]` | `--inspect-multiple PORT [PORT ...]` | Inspect multiple ports at once |
| `-ir RANGE` | `--inspect-range RANGE` | Inspect port range (e.g., 3000-3010) |
| `-ip NAME` | `--inspect-process NAME` | Inspect all processes matching the given name and their ports |
| `-k PORT` | `--kill PORT` | Kill the process using the specified port |
| `-kp NAME` | `--kill-process NAME` | Kill all processes matching the given name |
| `-ka PORT [PORT ...]` | `--kill-all PORT [PORT ...]` | Kill processes on multiple ports at once |
| `-kr RANGE` | `--kill-range RANGE` | Kill processes on port range (e.g., 3000-3010) |
| `-l` | `--list` | List all listening ports and their processes |
| `-v` | `--version` | Show version information |
| `-h` | `--help` | Show help message |

## 🛠️ Requirements

- Python 3.8 or higher
- No mandatory external dependencies (uses only Python standard library by default)

### Optional Dependencies

| Package | Purpose | Install |
|---------|---------|------|
| `psutil` | Faster, richer process info | `pip install psutil` |
| `mcp` | MCP server SDK (alternative transport) | `pip install mcp` |

### Platform-specific tools (fallback if psutil not available)

- **Windows**: `netstat`, `tasklist`, `taskkill`
- **Linux/macOS**: `lsof`, `ss`, `fuser`, `ps`, `kill`

These tools are typically pre-installed on all platforms.

## 🔧 Development

### Clone and setup

```bash
git clone https://github.com/farman20ali/port-killer.git
cd port-killer

# Install in development mode
pip install -e .
```

### Run tests

```bash
# Test inspecting a port
kport -i 80

# Test listing ports
kport -l
```

## 📚 Documentation

- **[Installation Guide](INSTALL.md)** - Detailed installation instructions
- **[Quick Start](QUICKSTART.md)** - Get started quickly
- **[Packaging Guide](PACKAGING.md)** - Cross-platform binary and package builds
- **[Publishing Guide](PUBLISH.md)** - How to publish kport to PyPI
- **[Release Guide](docs/RELEASE_GUIDE.md)** - Creating releases (manual & automated)
- **[Release Notes v3.2.0](docs/RELEASE_NOTES_3.2.0.md)** - What's new in 3.2.0
- **[Contributing](CONTRIBUTING.md)** - How to contribute

## 🚀 For Maintainers

### Creating a Release

Automated release (recommended):

```bash
python3 release.py
```

This script handles:
- Git tagging
- PyPI package building
- Debian package building  
- GitHub release creation

See [RELEASE_GUIDE.md](RELEASE_GUIDE.md) for manual release steps and troubleshooting.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the GNU Affero General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

**What this means:**
- ✅ Free to use, modify, and distribute
- ✅ Must share source code of any modifications
- ✅ **Network use = distribution**: If you run a modified version as a service, you must share the source code
- ❌ Cannot use in proprietary SaaS without sharing modifications

For commercial licensing or if AGPL doesn't fit your use case, contact: alienhub.dev@gmail.com

## ⚠️ Important Notes

- **Administrator/sudo privileges**: Killing processes may require elevated privileges on some systems
- **Port validation**: Port numbers must be between 1 and 65535
- **Safety**: The tool asks for confirmation before killing any process
- **Multiple processes**: If multiple processes use the same port, the first one found will be shown/killed

## 🐛 Troubleshooting

### "Permission denied" errors

On Linux/macOS, you may need to run with sudo:
```bash
sudo kport -k 80
```

On Windows, run your terminal as Administrator.

### Stubborn processes that won't die

Some processes (especially Java applications) may not respond to graceful termination. Use the `--force` flag which automatically uses a multi-tier kill strategy (SIGTERM → SIGKILL → fuser):

```bash
kport -k 8081 --force
```

On Linux, `kport` will automatically use `fuser -k` as a fallback when standard kill methods fail. This is extremely effective for stubborn Java/Node/Python processes:

```bash
# Install fuser for best results (Ubuntu/Debian)
sudo apt-get install psmisc

# Install fuser (RHEL/CentOS/Fedora)
sudo yum install psmisc

# Then kport will automatically use it when needed
kport -k 8081 --force
```

**What happens:**
1. First tries SIGTERM (graceful shutdown)
2. Then tries SIGKILL after timeout
3. Finally uses `fuser -k 8081/tcp` if process still lives (Linux only)

**Manual alternative:** You can also kill a port directly with fuser:
```bash
# Kill all processes using port 8081 (requires sudo)
sudo fuser -k 8081/tcp
```

### Port not found

Make sure the port number is correct and that a process is actually using it. Use `kport -l` to see all active ports.

### Color output not working on Windows

Colors should work on Windows 10 and later. If you're on an older version, colors may not display correctly.

## 📧 Contact

Farman Ali Ujjan - [alienhub.dev@gmail.com]

Project Link: [https://github.com/farman20ali/port-killer](https://github.com/farman20ali/port-killer)

---

Made with ❤️ for developers who are tired of hunting down processes
