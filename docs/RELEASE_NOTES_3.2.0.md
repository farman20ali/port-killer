# 🚀 kport v3.2.0 — Release Notes

**Release Date:** June 2026
**Branch:** `refactor`
**Previous Version:** 3.1.2

---

## Overview

kport 3.2.0 is the **Phase 2 Pro** release, delivering a full suite of advanced port management features designed for professional developers, DevOps engineers, and AI agent workflows. This release brings real-time port monitoring, AI safety guardrails, comprehensive configuration support, and a standards-compliant MCP (Model Context Protocol) server.

---

## 🆕 New Features

### 👁️ Watch Mode — `kport watch PORT`

Continuously polls a port at a configurable interval and **automatically kills** any process that starts using it.

```bash
kport watch 8080              # monitor with 1s interval (default)
kport watch 8080 --interval 2 # poll every 2 seconds
kport watch 8080 --dry-run    # alert only, do not kill
kport watch 8080 --json       # JSON output for scripting
kport watch 8080 --yes        # skip kill confirmation
```

- Respects the Safety Shield — will not auto-kill protected ports/processes unless `--bypass-safety` is set.
- Supports graceful kill with configurable timeout before escalating to force kill.
- Handles `KeyboardInterrupt` (Ctrl+C) cleanly.

---

### 🛡️ Safety Shield — Protected Ports & Processes

A configurable safety layer that prevents accidental termination of critical system services. Active by default on all `kill` and `watch` operations.

**Default protected ports:**

| Port | Service |
|------|---------|
| 22   | SSH |
| 53   | DNS |
| 80   | HTTP |
| 443  | HTTPS |
| 3306 | MySQL |
| 5432 | PostgreSQL |
| 6379 | Redis |
| 6443 | Kubernetes API |

**Default protected processes:** `systemd`, `init`, `docker`, `dockerd`, `sshd`, `explorer.exe`, `lsass.exe`, `services.exe`

To override the shield:
```bash
kport kill 22 --bypass-safety
kport watch 80 --bypass-safety --dry-run
```

To customize protected lists, set `protected_ports` and `protected_processes` in your `.kport.json` config — this **replaces** (not extends) the default lists.

---

### ⚙️ Enhanced Config File Support

The config file now supports `protected_ports` and `protected_processes` fields, making Safety Shield customizable per-project or globally.

**Config lookup order:**
1. `.kport.json` (current directory — project-level)
2. `~/.kport.json` (user-level)
3. `~/.config/kport/config.json` (XDG-compliant global)

**Full config schema:**
```json
{
  "yes": false,
  "dry_run": false,
  "force": false,
  "debug": false,
  "graceful_timeout": 3.0,
  "docker_action": "stop",
  "protected_ports": [22, 53, 80, 443],
  "protected_processes": ["sshd", "systemd"]
}
```

---

### 🤖 MCP Server — AI Agent Integration

kport now ships a standards-compliant **Model Context Protocol (MCP)** server that AI assistants (Claude, Copilot, Cursor, etc.) can call to inspect and manage ports autonomously — with Safety Shield always active.

```bash
kport --mcp                  # start MCP server on stdio
python -m kport.mcp_server   # alternative invocation
```

**MCP Tools:**

| Tool | Description |
|------|-------------|
| `list_ports` | Lists all local + Docker listening ports |
| `inspect_port` | Returns detailed info on a specific port |
| `kill_port` | Frees a port (safety-shielded, Docker-aware) |

The MCP server dynamically loads `.kport.json` config on each `kill_port` call, so safety policies can be updated without restarting the server.

**Claude Desktop / Cursor integration:**
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

---

## 📦 Cross-Platform Packaging

Native distribution packages are now automated via dedicated build scripts:

| Platform | Script | Output |
|---------|--------|--------|
| Windows | `python win_build.py` | `.exe` NSIS installer |
| macOS | `python mac_build.py` | `.pkg` installer |
| Debian/Ubuntu | `python deb_publish.py` | `.deb` package |
| RHEL/Fedora | `python rpm_build.py` | `.rpm` package |
| PyPI (any OS) | `python -m build` | `.whl` + `.tar.gz` |

The Debian package correctly installs both the `kport` entry-point binary and the full `src/kport/` library to Python's standard dist-packages path.

---

## 🔧 Improvements

- **Cross-platform inspector**: `psutil`-based `PsutilInspector` is now the default when psutil is installed; `FallbackInspector` (using native system commands) is used transparently when psutil is absent.
- **JSON output**: All subcommands now support `--json` for machine-readable output.
- **Graceful kill strategy**: SIGTERM → wait → SIGKILL → fuser (Linux fallback) chain is now consistent across CLI and MCP paths.
- **Debug mode**: `--debug` now prints full process resolution steps and kill attempt sequences.
- **Version**: Updated to `3.2.0` across `pyproject.toml`, `setup.py`, CLI parser, and MCP server info.

---

## 🧪 Test Suite

The test suite in `tests/test_cli.py` has been extended with:

- Safety Shield unit tests (default protection, bypass, custom config, process shield)
- `watch` command parser validation
- `apply_config_defaults` unit tests
- `FallbackInspector` initialization test
- Port range parsing edge-case coverage

Run all tests:
```bash
python run_tests.py
# or
pytest tests/ -v
```

---

## 🐛 Bug Fixes

- Fixed Debian `rules` file generator in `deb_publish.py` to correctly copy the full `src/kport/` module tree during `override_dh_auto_install`.
- Fixed MCP server version string to `3.2.0` (was `3.1.2`).
- Resolved setuptools deprecation warnings for `project.license` and `keywords` metadata.

---

## ⬆️ Upgrade Notes

- Minimum Python version is now **3.8** (was 3.6).
- The `protected_ports` and `protected_processes` config keys are new. If you had an existing `.kport.json`, no action is required — the Safety Shield defaults will apply automatically.
- The `--bypass-safety` flag is new. Old scripts that did not set it will now get Safety Shield protection by default.

---

## 📄 Full Changelog

- Added `watch` subcommand with auto-kill and polling loop
- Added `bypass_safety` flag to `kill` and `watch` subcommands
- Added `check_safety_policy()` function in `cli.py`
- Added `load_mcp_config()` in `mcp_server.py` with dynamic policy resolution
- Added `win_build.py`, `mac_build.py`, `rpm_build.py`, `deb_publish.py` build scripts
- Added `packaging/windows/installer.nsi` NSIS installer template
- Added `PACKAGING.md` guide
- Updated `README.md` and `QUICKSTART.md` for v3.2.0
- Bumped version to `3.2.0` across all package metadata files
