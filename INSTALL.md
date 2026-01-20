# Installation Guide

## 🚀 Quick Install

### For End Users

#### Option 1: Install from PyPI (Once Published)
```bash
pip install kport
```

#### Option 2: Install from GitHub
```bash
pip install git+https://github.com/farman20ali/port-killer.git
```

#### Option 3: Install from Source
```bash
# Clone the repository
git clone https://github.com/farman20ali/port-killer.git
cd port-killer

# Install
pip install .
```

### Verify Installation
After installation, verify it works:
```bash
kport --version
kport -h

# Docker-aware command style
kport list
kport docker
kport inspect 8080
```

---

## 🔧 For Developers

### Development Installation
```bash
# Clone the repository
git clone https://github.com/farman20ali/port-killer.git
cd port-killer

# Install in editable mode
pip install -e .
```

### Testing Your Installation
```bash
# Test basic commands
kport -l
kport -i 8080
```

---

## 🐧 Linux Installation

### Method 1: Using pip (Recommended)
```bash
# Install for current user (RECOMMENDED - avoids permission issues)
pip install --user kport

# Or install system-wide (requires sudo)
sudo pip install kport
```

> 💡 **Tip:** If the `kport` command doesn't work after installation, see the "command not found" section below.

> Note: if you install with `--user`, root may not find `kport` via `sudo`.
> Use `sudo -E` or run the full path (usually `~/.local/bin/kport`).

### Method 2: From Source
```bash
git clone https://github.com/farman20ali/port-killer.git
cd port-killer
sudo pip install .
```

### Make it Globally Accessible
If installed with `--user` and command not found, add to PATH:
```bash
# For bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# For zsh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

> 💡 **Verify:** Check if it's already in PATH with `echo $PATH`

---

## 🪟 Windows Installation

### Method 1: Using pip (Recommended)
```powershell
# Install to user directory (RECOMMENDED - no admin needed)
pip install --user kport

# If command not found, add to PATH:
$userScriptsPath = "$env:APPDATA\Python\Python311\Scripts"
[Environment]::SetEnvironmentVariable("Path", "$env:Path;$userScriptsPath", "User")
$env:Path += ";$userScriptsPath"

# Or install system-wide (requires admin)
pip install kport
```

> 💡 **Troubleshooting:** If `kport` command doesn't work, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

### Method 2: From Source
```powershell
git clone https://github.com/farman20ali/port-killer.git
cd port-killer
pip install .
```

### Method 3: Run Without Installing
```powershell
python kport.py -h
```

---

## 🍎 macOS Installation

### Method 1: Using pip (Recommended)
```bash
# Install for current user
pip3 install --user kport

# Or install system-wide
sudo pip3 install kport
```

### Method 2: Using Homebrew (If you create a formula)
```bash
brew tap yourusername/kport
brew install kport
```

---

## 🗑️ Uninstallation

```bash
pip uninstall kport
```

---

## ⚠️ Troubleshooting

### "kport: command not found" after installation

**This is the most common issue!** The executable is installed but not in your PATH.

**Linux/macOS:**
```bash
# Add pip's bin directory to PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

**Windows:**
Make sure Python's Scripts directory is in your PATH:
- `C:\Users\YourUsername\AppData\Local\Programs\Python\Python3X\Scripts\`

### Permission errors

**Linux/macOS:**
```bash
# Use --user flag
pip install --user kport

# Or use sudo
sudo pip install kport
```

**Windows:**
Run PowerShell or Command Prompt as Administrator

### Python not found

Make sure Python 3.6+ is installed:
```bash
python --version
# or
python3 --version
```

Download Python from: https://www.python.org/downloads/
