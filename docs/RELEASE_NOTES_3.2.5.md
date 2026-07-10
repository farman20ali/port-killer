# 🚀 kport v3.2.5 — Release Notes

**Release Date:** July 10, 2026  
**Tag:** `v3.2.5`  
**Previous Version:** [v3.2.4](./RELEASE_NOTES_3.2.4.md)

---

## Overview

kport 3.2.5 is a major **reliability, safety, performance, and developer infrastructure** release.

It introduces native process name enrichment (helping developers know exactly which script or application is bound to a port), targeted privilege escalation that only triggers when needed, unified safety configurations, and significant bug fixes in CLI JSON output, stale cache management, and system-level performance. Additionally, it eliminates technical debt by fully transitioning to `pyproject.toml`, consolidating the test suite to 43 automated tests, and modernising all developer documentation.

---

## 🆕 What's New

### 🧠 Process Name Enrichment for Runtimes
Generic process names like `python3`, `node`, or `java` make it difficult to identify the actual application listening on a port. kport now inspects the process command-line arguments and automatically enriches runtime names:
* `node` + `server.js` ➜ `node (server.js)`
* `python3` + `-m http.server` ➜ `python3 (http.server)`
* `java` + `-jar app.jar` ➜ `java (app.jar)`
* Supports 20+ runtime environments including Bun, Deno, Tsx, Ruby, PHP, Perl, and Dotnet.

### 🔐 Targeted Privilege Escalation (Sudo/UAC)
Previously, attempting to inspect or kill a port owned by another user or system process required running the entire `kport` command under `sudo` or Administrator command prompt.
* **Smart Escalation:** `kport` now runs as a normal user. Only when a signal/kill action encounters a `PermissionError` will it prompt the user for targeted privilege escalation (`sudo kill` on Unix-like systems or UAC elevated `taskkill` via PowerShell on Windows).

### 🛡️ Additive Safety Shields
Custom safety configurations defined in `.kport.json` (such as `protected_ports` or `protected_processes`) are now **additive** rather than overrides. 
* Specifying custom ports to protect now preserves default system ports (like SSH, DNS, HTTP, Postgres, and Redis) instead of silently unprotecting them.

### 🗑️ `setup.py` Fully Removed
The legacy `setup.py` file has been deleted. `pyproject.toml` is now the sole source of project metadata and version.
* Syncing version metadata is now managed in one place via:
  ```bash
  python manage.py sync-version 3.2.5
  ```

### 📦 Snap Package: Strict Confinement with Interfaces
`packaging/snap/snapcraft.yaml.template` updated to use `confinement: strict` with the correct interface plugs (`network`, `network-observe`, `network-bind`, `system-observe`, `process-control`, `hardware-observe`), allowing snap store review without classic confinement.

---

## 🧪 Automated Test Suite Expanded (43 tests total)

The test suite has been consolidated and expanded to bring kport to full subcommand parity:
* `tests/test_mcp.py` — 10 new tests verifying JSON-RPC protocol layer in isolation.
* `tests/test_commands.py` — 12 CLI subcommand integration tests.
* `tests/test_cli.py` & `test_commands.py` — 9 regression tests for safety config additive rules, process name enrichment, and watch mode state difference detection.

Run all tests:
```bash
pytest
pytest -v
```

---

## 🐛 Bug Fixes & Refactoring

### 🧹 Stale Cache Clearing
Fixed a critical bug where long-running modes (Watch Mode, MCP Server) would report stale process names for recycled PIDs. The `FallbackInspector` cache is now cleared at the beginning of every query.

### ⚡ Optimized Native Socket Lookup
* Replaced redundant process info lookups when parsing `/proc` on Linux. Sockets share a single process-level cache built once per query, preventing O(N) subprocess overhead.
* Excluded `kport`'s own PID from matching when searching for process names (preventing kport from accidentally targeting itself during wildcard name searches).

### 📋 Tabular Formatting & Column Widths
* Compute table column widths dynamically from actual data instead of hardcoded lengths, preventing silent truncation of long image names and enriched process names.
* Removed redundant platform ANSI configuration calls on Windows (runs once at startup instead of per-colorize call).

### 📦 CLI JSON Output Consistency
* In JSON mode with `--yes`, legacy `-kp`/`--kill-process` flags now output exactly one clean JSON block containing the operation's outcome, instead of multiple consecutive blocks.

---

## 🔄 Backward Compatibility

✅ **Fully backward compatible with kport 3.2.4.**  
All CLI commands, flags, configuration keys, and MCP tools remain unchanged.

---

## 📋 Changelog

| Area | Type | Summary |
|------|------|---------|
| core | feat | Implement process name enrichment for generic runtimes |
| core | feat | Implement smart privilege escalation (targeted `sudo` / UAC `taskkill` prompt) |
| core | fix | Fix stale process info cache in long-running modes (Watch Mode / MCP) |
| core | fix | Fix `find_ports_by_process_name` logic and remove dead code |
| core | fix | Optimize Linux native lookup by resolving PIDs once per list query |
| core | fix | Filter self-PID from process name searches |
| core | refactor | Deduplicate elevation check into unified `_is_elevated()` helper |
| core | feat | Add `ProcessNotFoundError` exception for cleaner error handling |
| build | chore | Delete `setup.py`; `pyproject.toml` is sole metadata source |
| scripts | chore | Delete standalone scripts (`run_tests.py`, `test_mcp_manual.py`) |
| docker | fix | Add descriptive warning for Docker socket permission issues and irreversible flags |
| formatter | fix | Dynamic column sizing and truncation with `…` suffix |
| formatter | fix | Setup ANSI output once at import time rather than per-color call |
| cli | fix | Replace port value truthiness checks with `is not None` |
| cli | fix | Merge safety config with default policies rather than replacing them |
| cli | fix | Ensure `kill-process` in legacy JSON mode outputs exactly one clean JSON block |
| mcp | refactor | Share a single inspector instance per server lifecycle |
| tests | feat | Add 43 tests total verifying subcommands, protocol, safety, and enrichment |
| snap | feat | Switch snap template to strict confinement + process-control plug |
| docs | chore | Update installation, release guide, packaging, and publish documentation to use `manage.py` |
