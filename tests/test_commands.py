"""
Integration tests for kport CLI subcommand routing (tests/test_commands.py).

Tests handle_product_command() and the legacy flag handlers with mock
inspectors and docker engines so no real network/OS access is needed.

Run with:  pytest tests/test_commands.py -v
"""

from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock, patch

import pytest

from kport.cli import handle_product_command, EXIT_OK, EXIT_PORT_FREE, EXIT_PERMISSION, EXIT_PORT_DOCKER
from kport.inspectors.base import BaseInspector, ProcessInfo, PortBinding


def _binding(port: int, pid: int = 1234, name: str = "node") -> PortBinding:
    """Return a real PortBinding dataclass (required for asdict() in CLI code)."""
    return PortBinding(port=port, family="inet", laddr=f"0.0.0.0:{port}",
                       pid=pid, process_name=name, state="LISTEN")


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

    def find_pids_on_port(self, port: int):
        return self._pids.get(port, [])

    def find_bindings_on_port(self, port: int):
        return self._bindings.get(port, [])

    def get_process_info(self, pid: int):
        return self._info.get(pid)

    def list_listening(self):
        return self._listening

    def find_ports_by_process_name(self, name, exact=False):
        return []

    def find_pids_by_name(self, name, exact=False):
        return []

    def kill_port(self, port, graceful_timeout=3.0, force=False, dry_run=False, debug=False):
        return True, f"Port {port} freed"

    def kill_pid(self, pid, graceful_timeout=3.0, force=False, dry_run=False):
        return True, f"PID {pid} killed"


def _args(**kwargs) -> argparse.Namespace:
    defaults = dict(json=False, debug=False, dry_run=False, yes=True, force=False,
                    graceful_timeout=None, bypass_safety=False, docker_action=None,
                    protected_ports=None, protected_processes=None)
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
    data = json.loads(out)
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
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------

def test_inspect_free_port(capsys):
    inspector = FakeInspector()
    args = _args(command="inspect", port=19999, json=True)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["type"] == "free"
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
    data = json.loads(capsys.readouterr().out)
    assert data["type"] == "local"
    assert rc == EXIT_OK


# ---------------------------------------------------------------------------
# explain
# ---------------------------------------------------------------------------

def test_explain_free_port(capsys):
    inspector = FakeInspector()
    args = _args(command="explain", port=19999, json=True)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)
    data = json.loads(capsys.readouterr().out)
    assert data["blocked"] is False
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
    data = json.loads(capsys.readouterr().out)
    assert data["blocked"] is True
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
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is False


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
    data = json.loads(capsys.readouterr().out)
    assert data["pids"] == []


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
    data = json.loads(capsys.readouterr().out)
    assert data == []
