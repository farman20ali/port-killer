# 🔪 kport - Cross-Platform Port Inspector and Killer

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/farman20ali/port-killer)
[![Python](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](https://github.com/farman20ali/port-killer)

A simple, powerful command-line tool to inspect and kill processes using specific ports on Windows, Linux, and macOS.

## ✨ Features

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
- 🚀 **Easy to use** - Simple command-line interface

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

### PRODUCT.md command style (recommended)

These commands are Docker-aware by default:

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

> Note: `--json`, `--dry-run`, `--yes`, and `--debug` work with subcommands.

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

### Config file support (Phase 2)

You can set default flags via JSON config:

- `.kport.json` (current directory)
- `~/.kport.json`
- `~/.config/kport/config.json`

Example:

```json
{
  "yes": true,
  "dry_run": false,
  "force": false,
  "graceful_timeout": 5,
  "docker_action": "stop"
}
```

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

## 📚 Command-Line Options

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

- Python 3.6 or higher
- No external dependencies (uses only Python standard library)

### Platform-specific tools

The tool uses platform-native commands:

- **Windows**: `netstat`, `tasklist`, `taskkill`
- **Linux/macOS**: `lsof`, `ps`, `kill`

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
- **[Publishing Guide](PUBLISH.md)** - How to publish kport
- **[Release Guide](RELEASE_GUIDE.md)** - Creating releases (manual & automated)
- **[Debian Release](DEB_RELEASE.md)** - Debian packaging and APT distribution
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
