# Publishing Guide for kport

This guide will help you publish `kport` so anyone can easily install it.

## 📋 Prerequisites

1. **GitHub account** - For hosting the code
2. **PyPI account** - For publishing to Python Package Index
   - Sign up at: https://pypi.org/account/register/
   - Sign up for Test PyPI: https://test.pypi.org/account/register/

3. **Install required tools**:
```bash
pip install build twine
```

---

## 🚀 Method 1: Publish to PyPI (RECOMMENDED)

### Step 1: Prepare Your Package

Update `setup.py` with your information:
- Change `author` and `author_email`
- Update `url` with your GitHub repository
- Update `project_urls`

### Step 2: Build the Package

```bash
# Clean previous builds
Remove-Item -Recurse -Force dist, build, *.egg-info -ErrorAction SilentlyContinue

# Build the package
python -m build
```

### Step 3: Test on Test PyPI (RECOMMENDED)

```bash
# Upload to Test PyPI first
python -m twine upload --repository testpypi dist/*

# Test installation from Test PyPI
pip install --index-url https://test.pypi.org/simple/ kport
or 
pip install --index-url https://test.pypi.org/simple/ --no-deps kport==1.0.0

```

### Step 4: Upload to Production PyPI

```bash
# Upload to PyPI
python -m twine upload dist/*
```

### Step 5: Verify

After uploading, anyone can install with:
```bash
# Recommended: Install to user directory (avoids permission issues)
pip install --user kport

# Or install system-wide (may require admin/sudo)
pip install kport
```

> 💡 **Important:** Recommend users to install with `--user` flag to avoid permission issues!

---

## 🐙 Method 2: GitHub Installation

### Step 1: Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/farman20ali/port-killer.git
git push -u origin main
```

### Step 2: Create a Release

1. Go to: https://github.com/farman20ali/port-killer/releases/new
2. Create a new tag: `v1.0.0`
3. Set release title: `kport v1.0.0 - Cross-Platform Port Inspector & Killer`
4. Add release notes describing features:
   - Inspect ports by port number or process name
   - Kill processes by port, process name, or multiple ports
   - List all active listening ports
   - Cross-platform support (Windows, Linux, macOS)
   - Colorized terminal output
   - Confirmation prompts for safety
5. Publish release

### Step 3: Installation

Anyone can now install with:
```bash
pip install git+https://github.com/farman20ali/port-killer.git
```

Or install a specific version:
```bash
pip install git+https://github.com/farman20ali/port-killer.git@v1.0.0
```

---

## 🔧 Method 3: Create Standalone Executables

For users without Python, create standalone executables:

### Windows (.exe)

```powershell
# Install PyInstaller
pip install pyinstaller

# Create standalone executable
pyinstaller --onefile --name kport kport.py

# Executable will be in dist/kport.exe
```

### Linux

```bash
# Install PyInstaller
pip install pyinstaller

# Create standalone executable
pyinstaller --onefile --name kport kport.py

# Executable will be in dist/kport
```

Then distribute the executables via GitHub Releases.

---

## 🎯 Quick Publish Script

We've included a helper script to make publishing easier:

```bash
python publish.py
```

This interactive script will:
1. Check and install requirements
2. Clean build directories
3. Build the package
4. Upload to Test PyPI
5. Upload to Production PyPI

---

## 📦 Configure PyPI Credentials

### Option 1: Use API Token (Recommended)

1. Generate token at: https://pypi.org/manage/account/token/
2. Create `~/.pypirc` (or `%USERPROFILE%\.pypirc` on Windows):

```ini
[pypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmcC...your-token-here

[testpypi]
username = __token__
password = pypi-AgENdGVzdC5weXBpLm9yZwI...your-token-here
```

### Option 2: Username/Password

Twine will prompt you for credentials when uploading.

---

## ✅ Verification Checklist

Before publishing, ensure:

- [ ] All features work correctly
- [ ] README.md is complete and accurate
- [ ] setup.py contains correct information
- [ ] License file is included
- [ ] Version number is correct
- [ ] Code is committed to GitHub
- [ ] Tests pass (if you have any)
- [ ] Documentation is up to date

---

## 🔄 Updating Your Package

When you want to release a new version:

1. Update version in `setup.py`
2. Update version in `kport.py`
3. Update CHANGELOG or release notes
4. Rebuild and republish:

```bash
# Clean old builds
Remove-Item -Recurse -Force dist, build, *.egg-info -ErrorAction SilentlyContinue

# Build and upload
python -m build
python -m twine upload dist/*
```

---

## 📊 After Publishing

### Promote Your Tool

1. **GitHub**: Add badges to README.md
```markdown
![PyPI](https://img.shields.io/pypi/v/kport)
![Python Version](https://img.shields.io/pypi/pyversions/kport)
![Downloads](https://img.shields.io/pypi/dm/kport)
```

2. **Share on**:
   - Reddit (r/Python, r/commandline)
   - Twitter/X
   - Dev.to
   - Hacker News

3. **Add to package managers**:
   - Homebrew (for macOS)
   - Chocolatey (for Windows)
   - Snap Store (for Linux)

---

## 🆘 Troubleshooting

### Upload fails with 403 error
- Check your API token or credentials
- Ensure package name is not taken

### Upload fails with "File already exists"
- You cannot overwrite a version
- Increment version number in setup.py

### Package not installing
- Check PyPI page: https://pypi.org/project/kport/
- Verify package name is correct
- Try with `--no-cache-dir`: `pip install --no-cache-dir kport`

---

## 📚 Resources

- PyPI: https://pypi.org/
- PyPI Help: https://pypi.org/help/
- Python Packaging Guide: https://packaging.python.org/
- Twine Documentation: https://twine.readthedocs.io/
