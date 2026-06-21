# 🚀 kport v3.2.5 — Release Notes

**Release Date:** June 21, 2026
**Tag:** `v3.2.5`
**Previous Version:** [v3.2.4](./RELEASE_NOTES_3.2.4.md)

---

## Overview

kport 3.2.5 is a **developer infrastructure and project quality release**.

It focuses on eliminating technical debt introduced by `setup.py`, consolidating
the test suite, raising automated test coverage across MCP and CLI subcommands,
and modernising all developer documentation to use the single `manage.py`
entrypoint. No user-facing CLI behaviour changes are included in this release.

---

## 🆕 What's New

### 🗑️ `setup.py` Fully Removed

The legacy `setup.py` file has been deleted. `pyproject.toml` is now the sole
source of project metadata and version.

**Migration:** All build and packaging scripts that previously read the version
from `setup.py` now read only from `pyproject.toml` → `src/kport/__init__.py`.

To bump the version going forward:

```bash
python manage.py sync-version 3.2.6
```

This updates both `pyproject.toml` and `src/kport/__init__.py` in one shot.

---

### 🧪 Automated Test Suite Expanded (34 tests total)

Two new test files bring kport's automated coverage up to full subcommand parity:

#### `tests/test_mcp.py` — 10 new tests
Verifies the JSON-RPC protocol layer of the MCP server in isolation (mocked
stdin/stdout — no subprocess spawning):

| Test | What it checks |
|------|---------------|
| `test_initialize_returns_protocol_version` | `initialize` handshake returns `protocolVersion: 2024-11-05` |
| `test_tools_list_returns_all_tools` | `tools/list` returns exactly `list_ports`, `inspect_port`, `kill_port` |
| `test_tools_have_required_schema_fields` | Every tool has `name`, `description`, `inputSchema` |
| `test_list_ports_returns_dict_with_lists` | `list_ports` returns `{local_processes, docker_containers}` |
| `test_inspect_port_free` | `inspect_port` on unused port → `type: free` |
| `test_inspect_port_out_of_bounds_raises` | Port 99999 → `isError: true` |
| `test_kill_port_protected_port_is_blocked` | Protected port (e.g. 22) → `Security Shield` message |
| `test_kill_port_free_port_succeeds` | Free port kill → `success: true` |
| `test_initialized_notification_produces_no_response` | Notification → no response line |
| `test_unknown_method_returns_method_not_found` | Unknown method → error code `-32601` |

#### `tests/test_commands.py` — 12 new tests
Integration tests for every CLI subcommand via `handle_product_command()`:

`list`, `docker`, `inspect`, `explain`, `kill` (free port, protected port, bypass),
`kill-process`, `conflicts`

---

### 🧹 Standalone Test Scripts Removed

The two standalone test scripts that lived outside of pytest are deleted:

- ~~`scripts/run_tests.py`~~ — replaced by `pytest` directly
- ~~`scripts/test_mcp_manual.py`~~ — replaced by `tests/test_mcp.py`

Run all tests:

```bash
pytest           # 34 tests, ~1.5 s
pytest -v        # verbose with test names
```

---

### 📦 Snap Package: Strict Confinement with Interfaces

`packaging/snap/snapcraft.yaml.template` updated to use `confinement: strict`
with the correct interface plugs, allowing the Snap Store to review it without
requiring the harder-to-obtain classic confinement approval:

```yaml
confinement: strict
apps:
  kport:
    plugs:
      - network
      - network-observe
      - network-bind
      - system-observe
      - process-control    # required to send signals to host PIDs
      - hardware-observe
```

The template also now includes the full Snap Store metadata fields (`contact`,
`website`, `issues`, `source-code`, `icon`) required for a quality listing.

---

### 📝 Documentation Overhaul

All developer-facing docs updated to reflect the current tooling:

| File | What changed |
|------|-------------|
| `docs/PACKAGING.md` | Uses `manage.py build` commands; Snap Store approval guide added |
| `docs/RELEASE_GUIDE.md` | Full rewrite — `manage.py release` workflow, `sync-version` instruction, multi-platform release table |
| `docs/QUICKSTART.md` | Replace root-level script invocations with `manage.py` commands; Windows/Linux install options added |
| `docs/PUBLISH.md` | Remove `setup.py` references; use `pyproject.toml` + `manage.py sync-version` |

---

## 🐛 Bug Fixes

### `build_deb.py` version reader
`read_project_version()` previously read only `setup.py`. It now reads
`pyproject.toml` (preferred) → `src/kport/__init__.py` (fallback) and
`check_layout()` now validates `pyproject.toml` instead of `setup.py`.

### `test_commands.py` `asdict()` crash
The initial test stub used a plain Python class as a `PortBinding` stand-in.
`handle_product_command` calls `dataclasses.asdict()` on bindings — which
requires a real `@dataclass` instance. Fixed by replacing the stub with a
`_binding()` factory function that returns a proper `PortBinding` dataclass.

---

## 🔄 Backward Compatibility

✅ **Fully backward compatible with kport 3.2.4.**

All CLI commands, flags, config file keys, and MCP tool names are unchanged.

---

## 📋 Full Changelog

| Area | Type | Summary |
|------|------|---------|
| build | chore | Delete `setup.py`; `pyproject.toml` is sole metadata source |
| scripts | chore | Remove `setup.py` from version-candidate lists in all 8 build scripts + `kport.spec` |
| scripts | chore | Delete `scripts/run_tests.py` and `scripts/test_mcp_manual.py` |
| tests | feat | Add `tests/test_mcp.py` — 10 MCP JSON-RPC protocol tests |
| tests | feat | Add `tests/test_commands.py` — 12 CLI subcommand integration tests |
| tests | fix | Fix `asdict()` crash in `test_commands.py` (use real `PortBinding` dataclass) |
| snap | feat | Switch snap template to strict confinement + process-control plug |
| snap | feat | Add full Snap Store metadata fields to `snapcraft.yaml.template` |
| docs | chore | Rewrite `RELEASE_GUIDE.md` to use `manage.py` workflow |
| docs | chore | Rewrite `QUICKSTART.md` to use `manage.py build` commands |
| docs | chore | Rewrite `PACKAGING.md` — manage.py, snap confinement warning |
| docs | chore | Update `PUBLISH.md` — remove `setup.py`, use `sync-version` |

---

## 📦 Installation

| Platform | Command |
|---|---|
| **PyPI** | `pip install kport==3.2.5` |
| **Linux DEB** | See [Releases](https://github.com/farman20ali/port-killer/releases/tag/v3.2.5) |
| **Linux RPM** | See [Releases](https://github.com/farman20ali/port-killer/releases/tag/v3.2.5) |
| **Linux Snap** | `sudo snap install kport` |
| **macOS** | See [Releases](https://github.com/farman20ali/port-killer/releases/tag/v3.2.5) |
| **Windows EXE** | See [Releases](https://github.com/farman20ali/port-killer/releases/tag/v3.2.5) |
| **Windows Chocolatey** | `choco install kport` |
| **VS Code** | Extensions marketplace → search "kport" |

---

## 🛠️ For Developers & Maintainers

### Building from Source

```bash
# Prerequisites check
python manage.py build --check

# Build everything for the current platform
python manage.py build --all

# Build individual formats
python manage.py build --pypi      # PyPI wheel + sdist
python manage.py build --win       # Windows .exe installer
python manage.py build --deb       # Debian .deb
python manage.py build --rpm       # RHEL .rpm
python manage.py build --snap      # Snap .snap
```

### Running Tests

```bash
pytest        # 34 tests, ~1.5 s
pytest -v     # verbose output
```

### Publishing

```bash
python manage.py publish --pypi    # upload to PyPI
python manage.py publish --snap    # push to Snap Store
python manage.py publish --choco   # push to Chocolatey
```

---

## 📖 Resources

- [GitHub Repository](https://github.com/farman20ali/port-killer)
- [PyPI Package](https://pypi.org/project/kport/)
- [Snap Package](https://snapcraft.io/kport)
- [VS Code Extension](https://marketplace.visualstudio.com/items?itemName=alienhub.kport-vscode)
- [Issue Tracker](https://github.com/farman20ali/port-killer/issues)
- [Build Guide](PACKAGING.md)
- [Release Guide](RELEASE_GUIDE.md)
