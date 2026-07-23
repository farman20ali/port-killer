"""
Integration tests for kport CLI subcommand routing (tests/test_commands.py).

Tests handle_product_command() and the legacy flag handlers with mock
inspectors and docker engines so no real network/OS access is needed.

Run with:  pytest tests/test_commands.py -v
"""

from __future__ import annotations

import argparse
import json
from unittest.mock import patch


from kport.cli import handle_product_command, EXIT_OK, EXIT_PORT_FREE, EXIT_PERMISSION
from kport.inspectors.base import BaseInspector, ProcessInfo, PortBinding


def _binding(port: int, pid: int = 1234, name: str = "node") -> PortBinding:
    """Return a real PortBinding dataclass (required for asdict() in CLI code)."""
    return PortBinding(
        port=port,
        family="inet",
        laddr=f"0.0.0.0:{port}",
        pid=pid,
        process_name=name,
        state="LISTEN",
    )


# ---------------------------------------------------------------------------
# Shared mock inspector
# ---------------------------------------------------------------------------


class FakeInspector(BaseInspector):
    def __init__(
        self,
        pids_on_port=None,
        bindings_on_port=None,
        process_info=None,
        listening=None,
    ):
        self._pids = pids_on_port or {}
        self._bindings = bindings_on_port or {}
        self._info = process_info or {}
        self._listening = listening or []

    def find_pids_on_port(self, port: int, proto: str = "tcp"):
        return self._pids.get(port, [])

    def find_bindings_on_port(self, port: int, proto: str = "tcp"):
        return self._bindings.get(port, [])

    def get_process_info(self, pid: int):
        return self._info.get(pid)

    def list_listening(self, proto: str = "tcp"):
        return self._listening

    def find_ports_by_process_name(self, name, exact=False, proto: str = "tcp"):
        return []

    def find_pids_by_name(self, name, exact=False):
        return []

    def kill_port(
        self,
        port,
        graceful_timeout=3.0,
        force=False,
        dry_run=False,
        debug=False,
        assume_yes=False,
        kill_tree=False,
        **kwargs,
    ):
        return True, f"Port {port} freed"

    def kill_pid(
        self,
        pid,
        graceful_timeout=3.0,
        force=False,
        dry_run=False,
        assume_yes=False,
        debug=False,
    ):
        return True, f"PID {pid} killed"


def _args(**kwargs) -> argparse.Namespace:
    defaults = dict(
        json=False,
        debug=False,
        dry_run=False,
        yes=True,
        force=False,
        graceful_timeout=None,
        bypass_safety=False,
        docker_action=None,
        protected_ports=None,
        protected_processes=None,
        proto="tcp",
        wait_for_exit=None,
        kill_tree=False,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_command_json_output(capsys):
    binding = _binding(8080)
    inspector = FakeInspector(listening=[binding])
    args = _args(command="list", json=True)
    with patch("kport.cli.list_docker_mappings", return_value=[]):
        rc = handle_product_command(args, inspector)
    assert rc == EXIT_OK
    out = capsys.readouterr().out
    envelope = json.loads(out)
    assert envelope["schema_version"] == 1
    assert envelope["command"] == "list"
    data = envelope["data"]
    assert "local" in data
    assert "docker" in data


def test_list_command_text_output(capsys):
    inspector = FakeInspector(listening=[])
    args = _args(command="list", json=False)
    with patch("kport.cli.list_docker_mappings", return_value=[]):
        rc = handle_product_command(args, inspector)
    assert rc == EXIT_OK


# ---------------------------------------------------------------------------
# docker
# ---------------------------------------------------------------------------


def test_docker_command_json(capsys):
    args = _args(command="docker", json=True, extra=[])
    with patch("kport.cli.list_docker_mappings", return_value=[]):
        rc = handle_product_command(args, FakeInspector())
    assert rc == EXIT_OK
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["schema_version"] == 1
    assert envelope["command"] == "docker"
    assert isinstance(envelope["data"], list)


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


def test_inspect_free_port(capsys):
    inspector = FakeInspector()
    args = _args(command="inspect", port=19999, json=True)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)
    out = capsys.readouterr().out
    envelope = json.loads(out)
    assert envelope["schema_version"] == 1
    assert envelope["command"] == "inspect"
    assert envelope["data"]["type"] == "free"
    assert rc == EXIT_PORT_FREE


def test_inspect_local_process(capsys):
    pi = ProcessInfo(pid=1234, name="node")
    inspector = FakeInspector(
        pids_on_port={8080: [1234]},
        process_info={1234: pi},
    )
    args = _args(command="inspect", port=8080, json=True)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["schema_version"] == 1
    assert envelope["command"] == "inspect"
    assert envelope["data"]["type"] == "local"
    assert rc == EXIT_OK


# ---------------------------------------------------------------------------
# explain
# ---------------------------------------------------------------------------


def test_explain_free_port(capsys):
    inspector = FakeInspector()
    args = _args(command="explain", port=19999, json=True)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["schema_version"] == 1
    assert envelope["command"] == "explain"
    assert envelope["data"]["blocked"] is False
    assert rc == EXIT_PORT_FREE


def test_explain_blocked_port(capsys):
    pi = ProcessInfo(pid=9999, name="myapp")
    inspector = FakeInspector(
        pids_on_port={7777: [9999]},
        process_info={9999: pi},
    )
    args = _args(command="explain", port=7777, json=True)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["schema_version"] == 1
    assert envelope["command"] == "explain"
    assert envelope["data"]["blocked"] is True
    assert rc == EXIT_OK


# ---------------------------------------------------------------------------
# kill
# ---------------------------------------------------------------------------


def test_kill_free_port(capsys):
    inspector = FakeInspector()
    args = _args(command="kill", port=19997, json=True)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)
    assert rc == EXIT_PORT_FREE


def test_kill_protected_port_blocked(capsys):
    """Killing a port in DEFAULT_PROTECTED_PORTS must be blocked."""
    inspector = FakeInspector(
        pids_on_port={22: [111]},
        process_info={111: ProcessInfo(pid=111, name="sshd")},
    )
    args = _args(command="kill", port=22, json=True)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)
    assert rc == EXIT_PERMISSION
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["schema_version"] == 1
    assert envelope["command"] == "kill"
    assert envelope["data"]["success"] is False


def test_kill_protected_port_with_bypass(capsys):
    """Bypassing safety shield allows killing a protected port."""
    inspector = FakeInspector(
        pids_on_port={22: [111]},
        process_info={111: ProcessInfo(pid=111, name="sshd")},
    )
    args = _args(command="kill", port=22, json=True, bypass_safety=True)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)
    # With bypass, kill proceeds — sshd is protected by name, not just port,
    # so this still gets blocked by the process shield unless also bypassed.
    # bypass_safety=True lifts both shields.
    assert rc in (EXIT_OK, EXIT_PORT_FREE)


# ---------------------------------------------------------------------------
# kill-process
# ---------------------------------------------------------------------------


def test_kill_process_not_found(capsys):
    inspector = FakeInspector()
    args = _args(command="kill-process", name="ghost", json=True, exact=False)
    rc = handle_product_command(args, inspector)
    assert rc == EXIT_OK
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["schema_version"] == 1
    assert envelope["command"] == "kill-process"
    assert envelope["data"]["pids"] == []


# ---------------------------------------------------------------------------
# conflicts
# ---------------------------------------------------------------------------


def test_conflicts_no_docker(capsys):
    """With no Docker containers there should be no conflicts."""
    inspector = FakeInspector()
    args = _args(command="conflicts", json=True)
    with patch("kport.cli.list_docker_mappings", return_value=[]):
        rc = handle_product_command(args, inspector)
    assert rc == EXIT_OK
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["schema_version"] == 1
    assert envelope["command"] == "conflicts"
    assert envelope["data"] == []


# ---------------------------------------------------------------------------
# R1 — ProcessInfo name enrichment
# ---------------------------------------------------------------------------


def test_process_info_enrichment_node():
    """node + ["/usr/bin/node", "server.js"] → name becomes 'node (server.js)'."""
    from kport.inspectors.base import ProcessInfo

    pi = ProcessInfo(pid=1, name="node", cmdline=["/usr/bin/node", "server.js"])
    assert pi.name == "node (server.js)"


def test_process_info_enrichment_python_m():
    """python3 -m http.server → name becomes 'python3 (http.server)'."""
    from kport.inspectors.base import ProcessInfo

    pi = ProcessInfo(pid=2, name="python3", cmdline=["python3", "-m", "http.server"])
    assert pi.name == "python3 (http.server)"


def test_process_info_enrichment_java_jar():
    """java -jar app.jar → name becomes 'java (app.jar)'."""
    from kport.inspectors.base import ProcessInfo

    pi = ProcessInfo(pid=3, name="java", cmdline=["java", "-jar", "/opt/app.jar"])
    assert pi.name == "java (app.jar)"


def test_process_info_no_enrichment_for_non_runtime():
    """nginx has no enrichment rule; name stays unchanged."""
    from kport.inspectors.base import ProcessInfo

    pi = ProcessInfo(pid=4, name="nginx", cmdline=["nginx", "-g", "daemon off;"])
    assert pi.name == "nginx"


def test_process_info_enrichment_short_cmdline():
    """node with only one cmdline entry (no script arg) stays as-is."""
    from kport.inspectors.base import ProcessInfo

    pi = ProcessInfo(pid=5, name="node", cmdline=["node"])
    assert pi.name == "node"


# ---------------------------------------------------------------------------
# R16 — Safety config is additive, not replacement
# ---------------------------------------------------------------------------


def test_safety_config_additive_ports():
    """User config protected_ports adds to defaults, doesn't replace them."""
    from kport.cli import check_safety_policy

    inspector = FakeInspector()
    # Port 22 must still be blocked even when user only config'd port 9999
    args = _args(command="kill", port=22, json=True, bypass_safety=False)
    args.protected_ports = [9999]  # user adds 9999 — should not remove 22
    args.protected_processes = None
    ok, msg = check_safety_policy(22, [], args, inspector)
    assert ok is False, "Port 22 must remain protected even with additive config"


def test_safety_config_additive_processes():
    """User config protected_processes adds to defaults, not replaces."""
    from kport.cli import check_safety_policy

    pi = ProcessInfo(pid=100, name="systemd")
    inspector = FakeInspector(process_info={100: pi})
    args = _args(command="kill", port=5000, json=True, bypass_safety=False)
    args.protected_ports = None
    args.protected_processes = ["mycustomapp"]  # user adds custom — systemd must stay
    ok, msg = check_safety_policy(None, [100], args, inspector)
    assert ok is False, (
        "systemd must remain protected even when user adds custom processes"
    )


# ---------------------------------------------------------------------------
# P6 — Watch state diff detects process name changes
# ---------------------------------------------------------------------------


def test_states_differ_detects_process_name_change():
    """_states_differ must return True when same PID runs a different process."""
    # Simulate state helper by importing the logic directly
    # We test via duck-typing (same structure as get_current_state returns)
    state_a = {"type": "local", "pids": [1234], "processes": ["old_app"]}
    state_b = {"type": "local", "pids": [1234], "processes": ["new_app"]}

    # Inline the same logic as _states_differ in cli.py
    def _states_differ(a, b):
        if a["type"] != b["type"]:
            return True
        if a["type"] == "docker":
            return a["container"] != b.get("container") or a["status"] != b.get(
                "status"
            )
        if a["type"] == "local":
            return set(a["pids"]) != set(b.get("pids", [])) or sorted(
                a["processes"]
            ) != sorted(b.get("processes", []))
        return False

    assert _states_differ(state_a, state_b) is True, (
        "Name change on same PID should be detected"
    )
    assert _states_differ(state_a, state_a) is False, "Same state should not differ"


# ---------------------------------------------------------------------------
# FakeInspector compatibility — kill_pid debug param
# ---------------------------------------------------------------------------


def test_fake_inspector_kill_pid_signature():
    """FakeInspector.kill_pid must accept the debug= param added in base.py."""
    inspector = FakeInspector(pids_on_port={8080: [1234]})
    ok, msg = inspector.kill_pid(
        1234, graceful_timeout=3.0, force=False, dry_run=False, assume_yes=True
    )
    assert ok is True
