# 🚀 kport v5.0.0 — Release Notes (Unreleased)

**Release Date:** *Unreleased / In Development*  
**Tag:** *Unreleased*  
**Branch:** `features`  

---

## Overview

kport 5.0.0 is a major evolutionary release transforming `kport` from a port inspection and termination tool into a comprehensive local development diagnostic intelligence platform.

Major highlights include:
1. **Diagnostic Intelligence (`kport diagnose` / `diagnose_port` MCP)**: Rich structured analysis providing observations, root-cause inferences, operational risk warnings, and actionable remediation recommendations.
2. **Environment Diagnostics (`kport doctor` / `doctor` MCP)**: Aggregated health check reporting platform capabilities, backend status (psutil/fallback), listening sockets, active connection summary, process metadata, and Docker mappings.
3. **Active Connection Inspection (`kport connections` / `list_connections` MCP)**: High-performance connection enumeration and filtering across TCP/UDP with configurable result bounding.
4. **Centralized Safety Policy (`kport.safety`)**: Consolidated safety checks and protected resource lists into a single source of truth across CLI, TUI, and MCP, featuring additive configuration semantics.
5. **Deep Context & Lineage**: Enriched process inspection with parent process lineage (`parent_name`, `ppid`), Git project/worktree resolution with credential sanitization, and Windows Service detection.

---

## 🌟 New Features & Capabilities

### 1. Structured Port Diagnostics (`kport diagnose` / `diagnose_port`)
Runs semantic diagnostic analysis on any port to answer not just *what* is using a port, but *why* and *how to safely fix it*.
- **Observations:** Local bindings, PIDs, active connections (bounded to 50), and Docker container mappings.
- **Inferences:** Automated detection of process managers (systemd, PM2, supervisord, Windows Services), Docker network isolation, and Git repository context.
- **Risks:** Highlights wildcard binding (`0.0.0.0` / `::`), auto-restart loops from service managers, and protected port/process flags.
- **Recommendations:** Suggests context-aware commands (e.g. `systemctl stop`, `Stop-Service`, `docker stop`, or `kport kill`).

### 2. Environment Doctor (`kport doctor` / `doctor`)
A full environment-wide audit tool:
- Summarizes inspection platform capabilities and active inspector backend.
- Reports all listening sockets and flags wildcard exposures.
- Aggregates TCP connection states (`LISTEN`, `ESTABLISHED`, `TIME_WAIT`, `CLOSE_WAIT`).
- Inspects and displays process owners, service managers, and Git project context for all active listeners.
- Queries Docker for published container port mappings.

### 3. Active Network Connection Enumeration (`kport connections` / `list_connections`)
- Lists and filters active host connections by PID, process name (case-insensitive substring), port (local or remote), and state.
- Hard-capped results (`max_results`, default 500) prevent payload explosion on busy development machines.
- Clean JSON output and table presentation without internal sentinel pollution.

### 4. Docker Conflict Detection (`conflicts` MCP)
- Detects host ports mapped to Docker containers that are concurrently occupied or bound by native host processes.

### 5. Centralized Safety Policy (`src/kport/safety.py`)
- Single source of truth for safety enforcement across CLI, TUI (`interactive.py`), and MCP (`mcp_server.py`).
- **Additive Configuration:** Configured `protected_ports` and `protected_processes` now extend the default safety shield rather than replacing it.
- **MCP Safety Guarantee:** MCP server strictly enforces safety policy on `kill_port` with no dynamic bypass.

### 6. Process Lineage & Project Detection
- Enriched `ProcessInfo` with `ppid`, `cwd`, `start_time`, and parent process name (`parent_name`).
- Windows Service resolution via `tasklist /SVC`.
- Native Git root, branch, worktree, and credential-sanitized remote URL resolution via `project.py`.

---

## 🤖 MCP Server Capabilities

kport's Model Context Protocol (MCP) server provides 7 native tools for AI coding assistants:

| Tool | Purpose | Read-Only | Safety Protected |
|---|---|---|---|
| `list_ports` | List active listening ports (local + Docker) | Yes | N/A |
| `inspect_port` | Detailed metadata for a single port | Yes | N/A |
| `kill_port` | Safely terminate process or stop container | No | Enforced |
| `diagnose_port` | Structured observations, inferences, risks, recommendations | Yes | N/A |
| `list_connections` | Enumerate and filter active network connections | Yes | N/A |
| `conflicts` | Detect Docker vs native port collisions | Yes | N/A |
| `doctor` | Environment-wide health check and listener summary | Yes | N/A |

---

## 📊 Test Verification

| Test Module | Tests | Status |
|---|---|---|
| `test_audit.py` | 10 | ✅ Passed |
| `test_cli.py` | 13 | ✅ Passed |
| `test_commands.py` | 21 | ✅ Passed |
| `test_connections.py` | 8 | ✅ Passed |
| `test_diagnose.py` | 13 | ✅ Passed |
| `test_doctor.py` | 20 | ✅ Passed |
| `test_enrichment.py` | 5 | ✅ Passed |
| `test_mcp.py` | 14 | ✅ Passed |
| `test_new_features.py` | 38 (2 skipped) | ✅ Passed |
| `test_phase4.py` | 23 | ✅ Passed |
| `test_process_manager_win.py` | 5 | ✅ Passed |
| `test_project.py` | 14 | ✅ Passed |
| `test_publish_pypi.py` | 1 | ✅ Passed |
| **Total** | **193 passed, 2 skipped** | ✅ |
