# Debian Release Guide (kport)

This repo can build a `.deb` without committing a `debian/` directory.

- The script `deb_publish.py` generates a minimal Debian packaging skeleton in a temporary directory.
- The produced `.deb` is copied into `dist/deb/`.

> Note: The generated package is intentionally minimal (installs a `kport` executable script and depends on `python3` + `python3-psutil`).

---

## 1) Build the `.deb`

On Debian/Ubuntu:

```bash
python3 deb_publish.py
```

Choose:
- `3` to build, or
- `4` to build and print install commands.

Output location:
- `dist/deb/kport_*_all.deb`

Install locally:

```bash
sudo dpkg -i dist/deb/kport_*_all.deb
kport --version
kport list
```

---

## 2) Create a GitHub Release and attach the `.deb`

### A) Prepare the tag

1. Bump the version in `setup.py` (example: `3.1.0` → `3.1.1`).
2. Build the `.deb` using `deb_publish.py`.
3. Commit the version bump:

```bash
git add setup.py
git commit -m "Bump version to 3.1.1"
```

4. Create and push a tag:

```bash
git tag -a v3.1.1 -m "kport v3.1.1"
git push origin main --tags
```

### B) Publish the Release

1. Go to GitHub Releases:
   - https://github.com/farman20ali/port-killer/releases/new
2. Select tag `v3.1.1`.
3. Upload the `.deb` file from `dist/deb/` as a release asset.
4. Publish.

This makes the `.deb` publicly downloadable, but users must install it manually with `dpkg -i`.

---

## 3) Make it “public on Debian” (APT install)

There are 3 levels of “public”:

### Option 1 (simplest): GitHub Releases (download + `dpkg -i`)

- Pros: easiest, no hosting setup.
- Cons: not an APT repository; no `apt install kport`.

### Option 2: Host your own APT repository (users can `apt install kport`)

You can publish an APT repository and host it anywhere static:
- GitHub Pages
- an S3-compatible bucket
- a normal web server

High-level steps:
1. Create a repo layout with `dists/` and `pool/`.
2. Add packages and generate metadata with a tool like `reprepro` or `aptly`.
3. Sign the repo with a GPG key.
4. Publish the directory and give users:
   - the repo URL
   - your signing key (or a `signed-by=` keyring file)

Example end-user experience:
- add a line under `/etc/apt/sources.list.d/kport.list`
- `sudo apt update`
- `sudo apt install kport`

If you want, I can add a second script to generate an APT repo folder (and an example `sources.list` snippet) using `reprepro` or `aptly`.

### Option 3 (hardest): get into official Debian repositories

This is possible, but it’s a real packaging + review process.

Typical requirements:
- Debian Policy-compliant packaging
- correct licensing + source distribution format expectations
- ongoing maintenance

Typical process:
- file an ITP (Intent To Package)
- prepare Debian packaging, ideally on Debian Salsa
- have a Debian Developer sponsor or become a maintainer
- go through NEW queue / reviews

If “official Debian” is your goal, we should switch from the intentionally-minimal packaging to a full Debian packaging flow (and align with Debian’s Python packaging practices).
