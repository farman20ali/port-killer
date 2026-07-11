# 🚀 kport v3.2.6 — Release Notes

**Release Date:** July 11, 2026  
**Tag:** `v3.2.6`  
**Previous Version:** [v3.2.5](./RELEASE_NOTES_3.2.5.md)

---

## Overview

kport 3.2.6 is a **code quality, security hardening, and developer infrastructure** release.

This version completes the Phase 1–3 items from the [kport improvement plan](../kport_improvement_plan.md): full Apache 2.0 license alignment across all project components, a native package discovery fix that makes `pip install` and `python -m kport` work reliably without needing a `setup.py`, a safety hardening pass (irreversible Docker `rm` now requires explicit `--force`), a versioned JSON output contract, cross-platform multi-port watch, named port profiles, an audit log, desktop notifications, shell completion, and a fully wired README usage auto-generator backed by CI. No new external dependencies are required.

---

## 🆕 What's New

### ⚖️ Apache 2.0 License — Full Alignment
The project now consistently carries **Apache License 2.0** everywhere:
- Root `LICENSE` file contains the verbatim Apache 2.0 text with the correct copyright notice (Farman Ali Ujjan, 2026).
- `pyproject.toml` uses the modern PEP 639 SPDX expression `license = "Apache-2.0"` and `license-files = ["LICENSE"]`.
- `vscode-extension/LICENSE` updated from AGPL-3.0 to Apache 2.0 to match the rest of the project.
- `CONTRIBUTING.md` updated with an explicit contributor license agreement paragraph.
- `NOTICE` file added at repo root per Apache 2.0 best practices.
- CI lint job now includes a **license drift guard** step: any future commit that reintroduces `AGPL` or `GNU Affero` strings outside of historical release notes will fail the build immediately.

### 📦 Packaging — Reliable `pip install` on All Environments
Added explicit setuptools package discovery in `pyproject.toml`:
```toml
[tool.setuptools.packages.find]
where = ["src"]
```
This resolves a `DistutilsOptionError: The parameter packages or py_modules was not specified` error that occurred in freshly-isolated pip build environments and Docker images where setuptools fell back to `setup.py` auto-discovery.

### 🐳 Docker `rm` — Hard Confirmation Gate (Phase 2.1)
`docker rm -f` is irreversible and loses non-persisted container state. It now requires **both** `--yes` **and** `--force` to proceed non-interactively:
```bash
kport kill 8080 --docker-action rm --yes --force   # works
kport kill 8080 --docker-action rm --yes            # blocked: PERMISSION error
```
The interactive path (no `--yes`) still prompts the user to type the container name to confirm — matching `git branch -D` style confirmation for dangerous operations.

### 📝 Versioned JSON Output Contract (Phase 2.5)
Every `--json` subcommand now emits a **stable, versioned envelope**:
```json
{"schema_version": 1, "command": "inspect", "data": {...}}
```
The `schema_version` key allows downstream scripts and AI agents to detect breaking changes without brittle string parsing. All subcommands (`inspect`, `explain`, `kill`, `kill-process`, `list`, `docker`, `conflicts`, `watch`) now emit this envelope consistently.

### 🌳 Process-Tree-Aware Kill (Phase 5, Tier 1)
`PsutilInspector.get_child_pids()` now uses `psutil.Process(pid).children(recursive=True)` to collect all descendant PIDs. `BaseInspector.kill_process_tree()` kills children depth-first before the root, preventing orphaned zombie processes when a parent (`npm run dev`, `gunicorn master`) is killed before its workers.

### 📋 Audit Log (Phase 5, Tier 1)
Every destructive action (`kill_port`, `kill_pid`, `docker_action`) is now appended to `~/.kport/audit.log` in NDJSON format:
```json
{"ts":"2026-07-11T03:30:00Z","version":"3.2.6","user":"farman","action":"kill_port","target":{"port":8080,"pids":[12345]},"dry_run":false,"success":true,"message":"Terminated gracefully"}
```
- Auto-rotates when the file exceeds 10 MiB (`audit.log` → `audit.log.1`).
- Audit failure is **non-fatal** — a write error never blocks the main operation.
- Fields are documented and stable; new fields may be added in future versions, but existing fields will not be removed.

### 👁️ Watch Mode — Multiple Ports & Port Ranges (Phase 5, Tier 1)
`kport watch` now accepts multiple ports and port ranges:
```bash
kport watch --ports 3000 5432 8080           # explicit list
kport watch --range 3000-3010                 # inclusive range
kport watch 8080 --notify                     # single port + OS notification
```
Desktop notifications are dispatched via the new `src/kport/notify.py` module, with platform-native dispatch (`plyer` on Windows/macOS, `notify-send` on Linux, graceful no-op fallback).

### 🗂️ Named Port Profiles (Phase 5, Tier 2)
Users can now define named groups of ports in `.kport.json` and operate on them as a unit:
```json
{"profiles": {"backend-dev": [8080, 5432, 6379], "frontend": [3000, 3001]}}
```
```bash
kport kill --profile backend-dev
kport inspect --profile backend-dev
```

### ✅ Shell Completion (Phase 5, Tier 1)
```bash
kport completion bash   | sudo tee /etc/bash_completion.d/kport
kport completion zsh    >> ~/.zshrc
kport completion fish   > ~/.config/fish/completions/kport.fish
kport completion powershell  # prints to stdout; source it or pipe to $PROFILE
```

### 📖 README Auto-Generator + CI Drift Guard (Phase 3.3)
`scripts/gen_readme_usage.py` regenerates the `## Usage` section of `README.md` directly from live `--help` output. CI now fails if the README is stale relative to the CLI:
```bash
python scripts/gen_readme_usage.py           # update in-place
python scripts/gen_readme_usage.py --check   # fail if stale (used in CI)
```

### 🛡️ TTY Gating Comment — Escalated Kill (Phase 2.4)
`base.py` now carries an explicit comment explaining why escalated kills require a TTY or `--yes`:
```python
# Escalated (sudo/UAC) kills are the most destructive action this tool can take.
# We deliberately refuse to auto-escalate in non-interactive contexts unless the
# operator has explicitly passed --yes. Do not relax this without a corresponding
# audit-log feature.
```
This prevents future contributors from accidentally relaxing the check.

### 🔒 Inspector Selection — Documented & Tested (Phase 3.1)
`src/kport/inspectors/__init__.py` now carries a full module docstring documenting the selection order (psutil preferred, FallbackInspector on permission denial or absence), per-platform behavior, and the snap confinement edge case. Two new unit tests verify both code paths via mock.

### 🔧 PyPI Publish Pre-flight (Phase 4.5)
`scripts/publish_pypi.py` now runs a pre-flight license consistency check before building or publishing. It will abort with a clear error if:
- `pyproject.toml` does not contain `license = "Apache-2.0"`
- The root `LICENSE` file does not contain Apache 2.0 body text

---

## 🧪 Test Suite — 52 Tests

| File | Count | New in 3.2.6 |
|------|-------|-------------|
| `tests/test_cli.py` | 13 | — |
| `tests/test_commands.py` | 21 | 9 (JSON schema, docker rm gate, profiles) |
| `tests/test_mcp.py` | 10 | — |
| `tests/test_new_features.py` | 8 | 8 (profiles, notify, inspector fallback, child PIDs) |
| **Total** | **52** | **17 new** |

Run all tests:
```bash
pytest -q
```

---

## 🐛 Bug Fixes

| Area | Fix |
|------|-----|
| `pyproject.toml` | Removed `License :: OSI Approved :: Apache Software License` classifier — PEP 639 environments reject it when the SPDX `license` string field is also set |
| `pyproject.toml` | Added `[tool.setuptools.packages.find] where = ["src"]` to prevent package-not-found build failures in fresh isolated environments |
| `scripts/publish_pypi.py` | Added `reconfigure(encoding="utf-8")` on Windows to prevent emoji `UnicodeEncodeError` when running the publishing menu |
| `ci.yml` | License drift guard now excludes `docs/` folder (historical release notes reference AGPL) |
| `inspectors/__init__.py` | `_psutil_accessible` now catches all psutil exception types, not just `PermissionError`, to handle strict snap AppArmor confinement |

---

## 📋 Full Changelog

| Area | Type | Summary |
|------|------|---------|
| license | feat | Replace AGPL-3.0 with Apache 2.0 across all project components |
| license | feat | Add `NOTICE` file at repo root |
| license | feat | Update `CONTRIBUTING.md` with CLA paragraph |
| license | chore | Update `vscode-extension/LICENSE` to Apache 2.0 |
| packaging | fix | Add `[tool.setuptools.packages.find]` to fix `pip install` in isolated environments |
| packaging | fix | Remove conflicting PEP 639 license classifier |
| cli | feat | Add `confirm_docker_rm()` — require `--force` in addition to `--yes` for irreversible `docker rm` |
| cli | feat | Add `--profile` flag to `inspect` and `kill` subcommands |
| cli | feat | Add `completion` subcommand for bash/zsh/fish/PowerShell |
| cli | feat | Extend `watch` to support `--ports` list and `--range` args |
| cli | feat | Add `--notify` flag to `watch` for desktop notifications |
| cli | feat | Consistent parent_parser shared across all subcommands |
| cli | fix | All `--json` paths emit versioned `{"schema_version": 1, "command": "...", "data": {...}}` envelope |
| core | feat | Add `src/kport/audit.py` — NDJSON audit log with auto-rotation |
| core | feat | Add `src/kport/notify.py` — cross-platform desktop notification with graceful fallback |
| core | feat | Add `src/kport/profile.py` — named port profile loading and resolution |
| core | feat | Implement `PsutilInspector.get_child_pids()` — recursive child PID collection |
| core | feat | Add `BaseInspector.kill_process_tree()` — depth-first child-before-parent kill |
| core | feat | Add TTY gating comment explaining why escalated kills require interactive context |
| inspectors | docs | Add full module docstring to `inspectors/__init__.py` documenting selection order |
| scripts | feat | Add `scripts/gen_readme_usage.py` — README usage auto-regeneration from `--help` |
| scripts | fix | Add UTF-8 stdout config to `publish_pypi.py` for Windows emoji safety |
| scripts | feat | Add `check_license_metadata()` pre-flight in `publish_pypi.py` |
| ci | feat | Add 3-OS × 2-Python matrix CI (Ubuntu, macOS, Windows × Python 3.8, 3.12) |
| ci | feat | Add coverage reporting via `pytest-cov` |
| ci | feat | Add license drift guard (fails on `AGPL`/`GNU Affero` outside changelog/docs) |
| ci | feat | Add README usage drift check (`gen_readme_usage.py --check`) |
| ci | feat | Add `dependabot.yml` for `pip` and `github-actions` dependency updates |
| tests | feat | 17 new tests: JSON schema round-trip, docker rm gate, profiles, inspector fallback, child PIDs |
| vscode | feat | Update extension `package.json` and `LICENSE` to Apache 2.0 |

---

## 🔄 Backward Compatibility

✅ **Fully backward compatible with kport 3.2.5.**  
All existing CLI commands, flags, configuration keys, MCP tools, and JSON output fields remain unchanged. The new `schema_version` envelope wraps the existing `data` object — existing scripts that parse the raw output will need to access `.data` if using `--json` mode.

> **Note for `--json` consumers:** Output is now wrapped: `{"schema_version": 1, "command": "...", "data": {...}}`. If you were parsing the raw top-level keys, update to access `result["data"]` instead.

---

## ⬆️ Upgrade

```bash
pip install --upgrade kport
# or
pipx upgrade kport
```

Verify:
```bash
python -m kport --version
# kport 3.2.6
```
