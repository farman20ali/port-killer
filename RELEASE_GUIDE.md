# Release Guide for kport

This document describes how to create and publish releases for kport.

---

## Quick Start: Automated Release

Use the automated release script:

```bash
python3 release.py
```

This script handles:
- ✅ Version validation
- ✅ Git tag creation
- ✅ PyPI package building and publishing
- ✅ Debian package building
- ✅ GitHub Release creation with all assets
- ✅ Release notes generation

---

## Manual Release Process

If you prefer manual control, follow these steps:

### 1. Pre-Release Checklist

- [ ] All tests pass
- [ ] Documentation is up to date
- [ ] CHANGELOG or release notes prepared
- [ ] Version bumped in `setup.py`
- [ ] No uncommitted changes

### 2. Version Update

Edit `setup.py` and update the version:

```python
version="3.1.1",  # Change this
```

Commit the version change:

```bash
git add setup.py
git commit -m "Bump version to 3.1.1"
```

### 3. Create Git Tag

```bash
# Create annotated tag
git tag -a v3.1.1 -m "Release v3.1.1"

# Push commits and tags
git push origin main
git push origin --tags
```

### 4. Build Packages

#### PyPI Package

```bash
python3 publish.py
```

Choose option 3 or 5 to build and upload to PyPI.

#### Debian Package

```bash
python3 deb_publish.py
```

Choose option 3 or 4 to build the `.deb`.

Output: `dist/deb/kport_*_all.deb`

### 5. Create GitHub Release

#### Option A: GitHub Web UI

1. Go to: https://github.com/farman20ali/port-killer/releases/new
2. Select tag: `v3.1.1`
3. Release title: `kport v3.1.1`
4. Add release notes (features, fixes, breaking changes)
5. Attach assets:
   - `dist/kport-*.tar.gz` (source)
   - `dist/kport-*.whl` (Python wheel)
   - `dist/deb/kport_*_all.deb` (Debian package)
6. Click "Publish release"

#### Option B: GitHub CLI (if installed)

```bash
gh release create v3.1.1 \
  --title "kport v3.1.1" \
  --notes "Release notes here" \
  dist/*.tar.gz \
  dist/*.whl \
  dist/deb/*.deb
```

---

## Release Checklist

### Before Release

- [ ] Version updated in `setup.py`
- [ ] All changes committed
- [ ] No uncommitted or untracked files
- [ ] Tests pass locally
- [ ] Documentation reviewed

### During Release

- [ ] Git tag created and pushed
- [ ] PyPI package built
- [ ] PyPI upload successful
- [ ] Debian package built
- [ ] GitHub Release created
- [ ] Release assets uploaded

### After Release

- [ ] Test PyPI installation: `pip install kport`
- [ ] Test Debian installation: `sudo dpkg -i kport_*.deb`
- [ ] Test GitHub installation: `pip install git+https://github.com/farman20ali/port-killer.git@v3.1.1`
- [ ] Update documentation if needed
- [ ] Announce release (social media, mailing lists, etc.)

---

## Distribution Channels

### PyPI (pip install kport)

Users can install via pip:

```bash
pip install kport
pip install --user kport  # User install (recommended)
```

### Debian Package

Direct download from GitHub Releases:

```bash
wget https://github.com/farman20ali/port-killer/releases/download/v3.1.1/kport_3.1.1-1_all.deb
sudo dpkg -i kport_3.1.1-1_all.deb
```

### GitHub Direct Install

```bash
pip install git+https://github.com/farman20ali/port-killer.git
pip install git+https://github.com/farman20ali/port-killer.git@v3.1.1  # Specific version
```

---

## Making Debian Package Public via APT

See [DEB_RELEASE.md](DEB_RELEASE.md) for advanced options:
- **Option 1**: GitHub Releases (simplest, manual `dpkg -i` install)
- **Option 2**: Host your own APT repository (enables `apt install kport`)
- **Option 3**: Submit to official Debian repositories (most complex)

---

## Troubleshooting

### PyPI Upload Fails

1. Check credentials: `~/.pypirc`
2. Ensure version doesn't already exist
3. Try Test PyPI first: `python3 publish.py` → option 2

### Git Tag Already Exists

Delete and recreate:

```bash
git tag -d v3.1.1
git push origin :refs/tags/v3.1.1
git tag -a v3.1.1 -m "Release v3.1.1"
git push origin --tags
```

### Debian Build Fails

Check build dependencies:

```bash
python3 deb_publish.py  # Choose option 1 to check
```

Install missing tools:

```bash
sudo apt-get update
sudo apt-get install -y debhelper build-essential python3-all
```

---

## Release Scripts

- **`release.py`**: Automated full release workflow
- **`publish.py`**: PyPI publishing (interactive)
- **`deb_publish.py`**: Debian package building (interactive)

Run any script with Python 3:

```bash
python3 release.py
```
