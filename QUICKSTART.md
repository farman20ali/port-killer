# 🚀 Quick Start Guide

## Installation (Choose One Method)

### ✅ Already on your machine!
```powershell
# Run directly from this directory
python kport.py -h
```

### 📦 Install globally (RECOMMENDED - no admin needed)
```powershell
# Install to user directory
pip install --user .

# Add to PATH if needed
$userScriptsPath = "$env:APPDATA\Python\Python311\Scripts"
[Environment]::SetEnvironmentVariable("Path", "$env:Path;$userScriptsPath", "User")
$env:Path += ";$userScriptsPath"
```

After installation:
```bash
kport -h
kport --version  # Should show: kport 1.0.0
```

> 💡 **Note:** Replace `Python311` with your Python version (e.g., `Python310`, `Python312`)

---

## 🎯 Quick Commands

```bash
# List all ports
python kport.py -l

# Inspect a specific port
python kport.py -i 8080

# Inspect multiple ports
python kport.py -im 3000 3001 8080

# Inspect port range
python kport.py -ir 3000-3010

# Inspect processes by name
python kport.py -ip node

# Kill process on a port
python kport.py -k 8080

# Kill all processes matching name
python kport.py -kp node

# Kill multiple ports
python kport.py -ka 3000 3001 3002

# Kill port range
python kport.py -kr 3000-3010
```

---

## 📤 To Share With Others

### Option 1: PyPI (Python Package Index)
**Best for**: Python users worldwide

1. Create PyPI account: https://pypi.org/account/register/
2. Run the publish script:
```powershell
python publish.py
```
3. Users install with:
```bash
pip install kport
```

### Option 2: GitHub
**Best for**: Developers and open source

1. Push to GitHub:
```bash
git init
git add .
git commit -m "Initial release"
git remote add origin https://github.com/farman20ali/port-killer.git
git push -u origin main
```

2. Users install with:
```bash
pip install git+https://github.com/farman20ali/port-killer.git
```

### Option 3: Standalone Executable
**Best for**: Users without Python

```powershell
# Install PyInstaller
pip install pyinstaller

# Create standalone .exe
pyinstaller --onefile --name kport kport.py

# Share the dist\kport.exe file
```

---

## 🔧 Your Next Steps

1. **Test it**: Run `python kport.py -l` to see it work ✅
2. **Push to GitHub**: Share your code
3. **Publish to PyPI**: Make it `pip install`-able
4. **Promote**: Share on social media, Reddit, etc.

---

## 📚 Documentation Files

- `README.md` - Main documentation
- `INSTALL.md` - Detailed installation instructions
- `PUBLISH.md` - How to publish to PyPI
- `publish.py` - Automated publishing helper script

---

## 💡 Tips

- Always test in Test PyPI before production
- Update version number for each release
- Keep README.md up to date
- Add badges to show downloads/version
- Respond to GitHub issues

---

**Your tool is ready to use RIGHT NOW!**
Just run: `python kport.py -l`
