# Changelog

All notable changes to `kport` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [4.0.0] - 2026-07-21

### Added
- **Interactive TUI Picker Mode** (`kport -I` / `kport interactive`): Live interactive curses interface with fuzzy search, multi-selection, and bulk kill, with graceful text menu fallback.
- **Process Manager Awareness**: `explain` now cgroup-detects systemd units (`systemd:unit.service`), PM2 worker processes (`pm2:app-name`), and supervisorctl tasks.
- **Advanced Watch Mode**: `--until free` and `--until occupied` flags with optional `--timeout <seconds>`.
- **UDP Protocol Support**: `--proto tcp|udp|both` across all commands (`list`, `inspect`, `kill`, `conflicts`, `watch`).
- **Recursive Process Tree Kill**: `--kill-tree` flag on all kill commands (traverses children depth-first).
- **Wait for Exit**: `--wait-for-exit <seconds>` option to block script execution until the target port socket is fully closed.
- **Optional High Performance**: `fast` installation extra (`pip install kport[fast]`) allowing users to choose high-performance psutil backend while keeping the core package zero-dependency.

### Changed
- Moved `psutil` package from required dependencies to optional dependencies.
- Standardized shell autocompletions for all shells (`bash`, `zsh`, `fish`, `powershell`) with support for the new flags.

---

## [3.2.6] - 2026-07-11

### Added
- Root `NOTICE` file per Apache 2.0 license best practices.
- Stable, versioned JSON output envelope contract (`schema_version: 1`).
- Named Port Profiles support (`--profile <name>`) read from `.kport.json` config.
- Desktop notification dispatch mechanism via `src/kport/notify.py` module.
- NDJSON-formatted audit logging (`~/.kport/audit.log`) for all destructive operations.
- CLI-driven autocompletion script generation (`kport completion <shell>`).
- License drift guard to check and prevent AGPL/GPL dependencies in CI.

### Changed
- Upgraded `vscode-extension/LICENSE` from AGPL-3.0 to Apache 2.0.
- Hard-gated Docker container removal (`docker_action=rm`) to require both `--yes` and `--force`.

---

## [3.2.5] - 2026-06-18

### Changed
- Standardized Apache 2.0 licensing headers on code files.
- Improved Linux native netstat parser to handle container edge-cases.

---

## [3.2.0] - 2026-05-10

### Added
- Live watch mode monitoring port ownership.
- Core safety shields block list preventing accidental termination of critical system ports (SSH, K8s, DB, DNS).
- Config file loading defaults via `.kport.json`.
- Stable Model Context Protocol (MCP) server integration.
