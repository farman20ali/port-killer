# kport v4.0.3 — Repository Audit Report

**Date:** 2026-08-08
**Branch:** `features` (HEAD = `45f2df2`, tag `v4.0.3`)
**Auditor:** AI engineering agent per `AI_PROMPT.md` instructions
**Test baseline:** 82 passed, 2 skipped — ✅ clean

---

## 1. Module Map

| File | Role | Size |
|---|---|---|
| `src/kport/__init__.py` | Version string (`4.0.3`) | small |
| `src/kport/cli.py` | Monolithic CLI entry-point — all subcommands, all routing | 2962 lines |
| `src/kport/constants.py` | `PROTECTED_PORTS`, `PROTECTED_PROCESS_NAMES`, `RUNTIME_ENRICHMENT_NAMES` | shared safety source-of-truth |
| `src/kport/exceptions.py` | `KPortError`, `InvalidPortError`, `PermissionDeniedError`, `DockerError`, `PortBlockedError`, `ProcessNotFoundError` | 6 classes |
| `src/kport/audit.py` | NDJSON audit log → `~/.kport/audit.log` (kill_port / kill_pid / docker_action) | with rotation |
| `src/kport/formatter.py` | Rich terminal output helpers, color, tables | |
| `src/kport/inspectors/__init__.py` | Backend selection: PsutilInspector > FallbackInspector | runtime dispatch |
| `src/kport/inspectors/base.py` | `PortBinding`, `ProcessInfo`, `BaseInspector`, kill flow | 530 lines |
| `src/kport/inspectors/psutil_impl.py` | psutil-backed inspector (preferred) | |
| `src/kport/inspectors/system_impl.py` | `/proc`/ctypes/`lsof` fallback inspector | 61 KB |
| `src/kport/docker_engine.py` | Docker CLI integration (list, inspect, stop/restart/rm) | |
| `src/kport/mcp_server.py` | Stdio JSON-RPC MCP server (manual, no SDK) | 393 lines |
| `src/kport/process_manager.py` | systemd/PM2/Supervisor detection | |
| `src/kport/profile.py` | Named port profiles from `.kport.json` | |
| `src/kport/notify.py` | Desktop notification (optional) | |
| `src/kport/interactive.py` | curses TUI port picker | |

---

## 2. Public Command Map

```
kport inspect <port>           # docker-aware port inspection
kport explain <port>           # why is a port blocked? (process manager + recommendations)
kport kill <port>              # kill port (docker-aware, graceful → force)
kport kill-process <name>      # kill processes by name
kport list                     # list all listening ports (local + docker)
kport docker                   # list Docker-published ports
kport conflicts                # detect docker/local port conflicts
kport watch <port>             # live TUI monitoring of port ownership
kport mcp                      # start stdio MCP server
kport interactive              # launch curses TUI port picker
kport completion               # shell autocompletion scripts

Legacy short flags (all preserved):
  -i/-im/-ir/-ip  inspect
  -k/-kp/-ka/-kr  kill
  -l              list
  --json / --dry-run / -y / --debug / --force / --kill-tree
  --proto tcp|udp|both
  --bypass-safety
  --config <path>
  --profile <name>
```

---

## 3. Feature Matrix

| Proposed capability | Exists? | Quality | Tests? | Gap | Action |
|---|---|---|---|---|---|
| Port inspection (TCP) | ✅ Full | Good | ✅ | None | Maintain |
| Port inspection (UDP) | ✅ Full | Good | ✅ | None | Maintain |
| Port inspection (IPv4/IPv6) | ✅ Partial | OK | Partial | IPv6 state reporting thin | Minor P2 |
| Process info (PID/name/exe/cmdline/user) | ✅ Full | Good | ✅ | No ppid/cwd/start_time in `ProcessInfo` | P2 extension |
| Process enrichment (runtime names) | ✅ Full | Good | ✅ | None | Maintain |
| Process tree kill (`--kill-tree`) | ✅ Full | Good | ✅ | None | Maintain |
| Docker integration (list/stop/restart/rm) | ✅ Full | Good | ✅ | None | Maintain |
| Watch mode (live TUI) | ✅ Exists | Good | ✅ | Polling only (no event-driven) | P2 review |
| TUI interactive picker (curses) | ✅ Full | Good | ✅ | None | Maintain |
| Safety / protected ports | ✅ Full | Good | ✅ | Centralized in `constants.py`, shared CLI+MCP | Maintain |
| Bypass safety (`--bypass-safety`) | ✅ Full | Good | ✅ | None | Maintain |
| Audit logging | ✅ Full | Good | ❌ No tests | Tests completely absent | **P1 add tests** |
| MCP server | ✅ Exists | Manual JSON-RPC | ✅ | `force=True` default is unsafe | **P1 fix** |
| Service managers (systemd/PM2/Supervisor) | ✅ Full | Good | ✅ | Windows Service detection missing | P2 |
| `explain` command | ✅ Full | Good | ✅ | No structured OBS/INF/REC separation | Basis for `diagnose` |
| `conflicts` command | ✅ Full | Good | ✅ | Local vs Docker conflict detection | Maintain |
| Port profiles | ✅ Full | Good | ✅ | None | Maintain |
| JSON output (`--json`) | ✅ Full | Good | ✅ | `schema_version: 1` already present in CLI | Maintain |
| Privilege escalation (sudo/UAC) | ✅ Full | Good | ✅ | None | Maintain |
| Configuration (`.kport.json`) | ✅ Full | Good | ✅ | None | Maintain |
| Shell autocompletion | ✅ Exists | Basic | None | No tests | P3 |
| Desktop notifications | ✅ Exists | Optional | ✅ | None | Maintain |
| VS Code extension | ✅ Exists | TypeScript | CI only | Separate codebase | Maintain separately |
| Packaging (PyPI/Snap/Choco/AUR/Homebrew/winget) | ✅ Full | Good | CI | Version consistency check needed | P2 verify |
| CI/CD | ✅ Full | Good | ✅ | — | Maintain |
| `diagnose` command | ❌ Missing | — | — | Structured OBS/INF/REC reasoning | **P1 implement** |
| `doctor` command | ❌ Missing | — | — | Environment-wide scan | P2 |
| `connections` command | ❌ Missing | — | — | Established connections (not just LISTEN) | P2 |
| Project detection | ❌ Missing | — | — | Port → git repo / project files | P2 |
| Dependency graph | ❌ Missing | — | — | Frontend→API→DB graph | P3 |
| Platform capability matrix doc | ❌ Missing | — | — | No formal doc | **P1 create** |
| `docs/engineering/AUDIT.md` | ❌ Missing | — | — | — | **This document** |

---

## 4. Architecture Assessment

### What works well

- **Inspector abstraction** is clean. `BaseInspector` → `PsutilInspector` / `FallbackInspector` with runtime
  selection based on actual psutil accessibility (not just presence).
- **Safety centralization** in `constants.py` — shared by CLI and MCP, additive merge from config.
- **Escalated kill flow** (SIGTERM → poll → SIGKILL → sudo/UAC) is well-designed with dry_run and assume_yes.
- **Audit log** is NDJSON, versioned, rotated, non-fatal on write failure — good design; just needs tests.
- **Process enrichment** (`node (server.js)`, `python (-m http.server)`) is clean and tested.
- **Docker awareness** is threaded consistently through inspect/kill/list/conflicts.
- **Test infrastructure** uses mock inspectors — no real network access required.

### Technical Debt / Risks

1. **`cli.py` is 2,962 lines** — monolithic. Nearly all business logic lives here. The architecture diagram
   from PLAN.md (domain → application → CLI) is not yet implemented. Not an emergency, but a long-term
   maintenance risk.

2. **MCP uses manual JSON-RPC** — declares `protocolVersion: 2024-11-05`, implements initialize /
   tools/list / tools/call correctly. The `mcp>=0.1.0` optional dependency is declared in `pyproject.toml`
   but is not actually used. Hand-rolled implementation is currently correct. SDK migration is optional.

3. **`force=True` default in MCP `kill_port`** — the tool schema and Python function signature both default
   to `force=True`. Per PLAN.md §20 this is against the safety model for AI-driven destructive operations.
   **Active safety issue.**

4. **No `diagnose` command** — the Plan's Phase 7 is the highest-value missing feature. `explain` partially
   overlaps but does not structure output into OBSERVATION / INFERENCE / RECOMMENDATION.

5. **Audit log is completely untested** — zero test coverage for write, rotation, or field validation.

6. **Windows Service detection missing** in `process_manager.py` — only systemd/PM2/Supervisor.

7. **No established-connections listing** — `list_listening()` covers LISTEN state only.

---

## 5. Identified Gaps — Priority Order

### P1 (Active issues — fix before adding features)

| # | Gap | File(s) | Effort |
|---|---|---|---|
| P1-A | MCP `force=True` default → should be `false` | `mcp_server.py` | 15 min |
| P1-B | Audit log tests absent | new `tests/test_audit.py` | 2 hrs |
| P1-C | `kport diagnose` command missing | `cli.py`, new `tests/test_diagnose.py` | half day |
| P1-D | Platform capability matrix | new `docs/engineering/PLATFORM.md` | 1 hr |

### P2 (High-value additions, after P1 stable)

- `kport doctor` environment scan
- `kport connections` (ESTABLISHED connections, not just LISTEN)
- Project detection (port → git root / project files)
- `ProcessInfo` ppid/cwd/start_time enrichment
- Windows Service detection in `process_manager.py`

### P3 (Later)

- `cli.py` domain/application/presentation layer split
- MCP SDK migration (hand-rolled is currently correct)
- Dependency graph
- JSON schema versioning in MCP output (CLI already has it)

---

## 6. MCP Audit

| Aspect | Status |
|---|---|
| Protocol version | `2024-11-05` ✅ |
| `initialize` | Returns `protocolVersion`, `capabilities`, `serverInfo` ✅ |
| `tools/list` | Returns `{tools: [...]}` ✅ |
| `tools/call` | Returns `{content: [{type, text}], isError}` ✅ |
| Input schemas | Defined inline with `required`, `minimum`, `maximum` ✅ |
| stderr logging | `log()` writes to stderr only ✅ |
| stdout purity | Only JSON-RPC on stdout ✅ |
| `notifications/initialized` | Handled (no response) ✅ |
| Unknown method | Returns `{error: {code: -32601}}` ✅ |
| Unknown tool | Raises `ValueError` → caught → `isError: true` ✅ |
| `force` default | `true` ⚠️ **Must be changed to `false`** |
| Official SDK usage | `mcp>=0.1.0` declared but unused — hand-rolled is correct for now |

---

## 7. Test Suite Baseline

```
82 passed, 2 skipped  (< 2s)
```

Skipped: 2 tests in `test_new_features.py` — Unix-only `/proc` path checks (expected on Windows).

Coverage gaps:
- Audit log writes (no assertions on NDJSON output)
- `kport diagnose` (not yet implemented)
- `kport doctor` (not yet implemented)
- Shell autocompletion scripts
- Established-connections path

---

## 8. Packaging Status

| Channel | File(s) | Version consistent? |
|---|---|---|
| PyPI | `pyproject.toml` | ✅ `4.0.3` |
| Snap | `packaging/snap/` | Needs verification before next release |
| Chocolatey | `packaging/chocolatey/` | Needs verification before next release |
| AUR | `packaging/aur/` | Needs verification before next release |
| Homebrew | `packaging/homebrew/` | Needs verification before next release |
| winget | `packaging/winget/` | Needs verification before next release |
| Native | `packaging/linux/` + `packaging/macos/` | Needs verification before next release |

---

## 9. Rejected Roadmap Items

| Item | Reason |
|---|---|
| Packet capture | Out of scope per PLAN.md §33 |
| Full network scanner | Out of scope |
| Kubernetes dashboard | Out of scope unless explicit user need |
| Desktop GUI | CLI/core architecture not mature enough yet |
| Giant plugin framework | Unjustified complexity |
| Autonomous destructive AI | Explicitly prohibited by PLAN.md §2.5 |

---

## 10. Implementation Order (confirmed)

```
Phase 0   Repository audit + docs/engineering/AUDIT.md    ← THIS DOCUMENT
Phase 1A  MCP force=False fix                             ← NEXT
Phase 1B  Audit log tests
Phase 1C  kport diagnose command
Phase 1D  docs/engineering/PLATFORM.md
Phase 2   doctor / connections / project detection
Phase 3   cli.py refactor / MCP SDK / graph
```
