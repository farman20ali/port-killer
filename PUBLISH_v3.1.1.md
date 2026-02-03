# Publishing kport v3.1.1

Quick guide to publish the new version with enhanced kill improvements.

## 📋 Pre-publish Checklist

- [x] Version bumped to 3.1.1 in `setup.py`
- [x] Version bumped to 3.1.1 in `kport.py`
- [x] Release notes created: `RELEASE_NOTES_3.1.1.md`
- [x] README.md updated with troubleshooting info
- [x] Code changes implemented and tested

## 🚀 Publishing Steps

### 1. Add and Commit Changes

```bash
# Add the test script to ignore if desired
echo "test_kill_improvements.sh" >> .gitignore

# Add all changes
git add .

# Commit
git commit -m "Release v3.1.1: Enhanced kill mechanism with fuser fallback"
```

### 2. Create Git Tag

```bash
# Create annotated tag
git tag -a v3.1.1 -m "kport v3.1.1 - Enhanced kill mechanism for stubborn processes"

# Verify tag
git tag -l v3.1.1
```

### 3. Push to GitHub

```bash
# Push commits
git push origin main

# Push tag
git push origin v3.1.1
```

### 4. Build Package

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build source and wheel distributions
python3 setup.py sdist bdist_wheel

# Verify build
ls -lh dist/
```

### 5. Publish to PyPI

```bash
# Install/upgrade twine if needed
pip install --upgrade twine

# Upload to PyPI (you'll need PyPI credentials)
twine upload dist/*

# Or test on TestPyPI first
twine upload --repository testpypi dist/*
```

### 6. Create GitHub Release

1. Go to: https://github.com/farman20ali/port-killer/releases/new
2. Select tag: `v3.1.1`
3. Release title: `kport v3.1.1 - Enhanced Kill Mechanism`
4. Description: Copy from `RELEASE_NOTES_3.1.1.md`
5. Upload dist files (optional):
   - `kport-3.1.1.tar.gz`
   - `kport-3.1.1-py3-none-any.whl`
6. Click "Publish release"

### 7. Build Debian Package (Optional)

```bash
# Build .deb package
python3 deb_publish.py

# This creates: kport_3.1.1-1_all.deb

# Test installation
sudo dpkg -i kport_3.1.1-1_all.deb

# Upload to GitHub release as asset
```

## 🧪 Post-publish Testing

```bash
# Test installation from PyPI
pip install --user --upgrade kport

# Verify version
kport -v
# Should show: kport 3.1.1

# Test the new kill feature
kport kill 8081 --force
```

## 📢 Announcement

After publishing, announce on:

1. **GitHub Release**: Auto-generated, followers notified
2. **README badges**: Already updated
3. **Social media**: Share the key improvement:
   ```
   🎉 kport v3.1.1 is out! 
   
   Now reliably kills stubborn Java/Node processes that ignore normal kill signals!
   Uses multi-tier strategy: SIGTERM → SIGKILL → fuser fallback
   
   Try it: pip install --upgrade kport
   ```

## 🔍 Verification Checklist

After publishing:

- [ ] PyPI shows v3.1.1: https://pypi.org/project/kport/
- [ ] GitHub release created: https://github.com/farman20ali/port-killer/releases/tag/v3.1.1
- [ ] `pip install kport` installs v3.1.1
- [ ] `kport -v` shows 3.1.1
- [ ] `kport kill --help` shows updated help text mentioning fuser

## 🐛 Rollback (if needed)

If issues are discovered:

```bash
# Delete tag locally
git tag -d v3.1.1

# Delete tag remotely
git push origin :refs/tags/v3.1.1

# Delete release on GitHub (via web interface)

# Yank version from PyPI (doesn't delete, but hides)
# Contact PyPI support or use: pip yank kport==3.1.1
```

## 📝 Notes

- **Breaking changes**: None - fully backward compatible
- **Migration**: Users just need to upgrade, no config changes needed
- **Fuser**: Optional - works without it, just less effective for stubborn processes
- **Platform**: Enhanced kill primarily benefits Linux users

## ✅ Ready to Publish!

All files are ready. Just follow the steps above to publish v3.1.1.
