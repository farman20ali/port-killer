"""
Phase 4 tests for kport (tests/test_phase4.py).

Covers:
  - filter_connections: max_results bounding
  - diagnose_port: parent_name lineage enrichment + connections in observations
  - MCP list_connections tool: routing, filters, capped flag
  - MCP isError consistency (list responses from conflicts/doctor)

Run with:  pytest tests/test_phase4.py -v
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from kport.diagnostics import filter_connections
from kport.inspectors.base import ConnectionInfo, ProcessInfo
from kport.mcp_server import TOOLS, handle_list_connections, run_mcp_server
from tests.test_commands import FakeInspector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _conn(
    pid=100,
    name="node",
    proto="tcp",
    laddr="127.0.0.1",
    lport=8080,
    raddr="127.0.0.1",
    rport=50000,
    state="ESTABLISHED",
) -> ConnectionInfo:
    return ConnectionInfo(
        pid=pid,
        process_name=name,
        proto=proto,
        local_address=laddr,
        local_port=lport,
        remote_address=raddr,
        remote_port=rport,
        state=state,
    )


def _send_messages(*messages: dict) -> list[dict]:
    """Feed JSON-RPC messages to the MCP server and collect responses."""
    lines = [json.dumps(m) + "\n" for m in messages]
    captured = StringIO()
    with (
        patch("sys.stdin", StringIO("".join(lines))),
        patch("sys.stdout", captured),
        patch("sys.stderr", StringIO()),
    ):
        run_mcp_server()
    return [json.loads(line) for line in captured.getvalue().strip().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# filter_connections unit tests
# ---------------------------------------------------------------------------


class TestFilterConnections:
    def test_returns_all_by_default(self):
        conns = [_conn(pid=i, lport=i + 1000) for i in range(5)]
        inspector = FakeInspector(connections=conns)
        result = filter_connections(inspector)
        assert len(result) == 5

    def test_filter_by_pid(self):
        conns = [_conn(pid=1, lport=1001), _conn(pid=2, lport=1002)]
        inspector = FakeInspector(connections=conns)
        result = filter_connections(inspector, pid=1)
        assert len(result) == 1
        assert result[0]["pid"] == 1

    def test_filter_by_process_name_case_insensitive(self):
        conns = [_conn(name="NODE", lport=1001), _conn(name="nginx", lport=1002)]
        inspector = FakeInspector(connections=conns)
        result = filter_connections(inspector, process="node")
        assert len(result) == 1
        assert result[0]["process_name"] == "NODE"

    def test_filter_by_port_local(self):
        conns = [_conn(lport=8080, rport=50000), _conn(lport=9090, rport=51000)]
        inspector = FakeInspector(connections=conns)
        result = filter_connections(inspector, port=8080)
        assert len(result) == 1
        assert result[0]["local_port"] == 8080

    def test_filter_by_port_remote(self):
        conns = [_conn(lport=8080, rport=9090), _conn(lport=8888, rport=7070)]
        inspector = FakeInspector(connections=conns)
        result = filter_connections(inspector, port=9090)
        assert len(result) == 1

    def test_filter_by_state_case_insensitive(self):
        conns = [
            _conn(state="ESTABLISHED", lport=1001),
            _conn(state="TIME_WAIT", lport=1002),
        ]
        inspector = FakeInspector(connections=conns)
        result = filter_connections(inspector, state="established")
        assert len(result) == 1
        assert result[0]["state"] == "ESTABLISHED"

    def test_max_results_cap(self):
        conns = [_conn(pid=i, lport=i + 1000) for i in range(100)]
        inspector = FakeInspector(connections=conns)
        result = filter_connections(inspector, max_results=10)
        assert len(result) == 10

    def test_max_results_no_truncation_when_under_cap(self):
        conns = [_conn(pid=i, lport=i + 1000) for i in range(5)]
        inspector = FakeInspector(connections=conns)
        result = filter_connections(inspector, max_results=10)
        assert len(result) == 5

    def test_result_schema(self):
        conns = [_conn(pid=42, name="python", lport=5000, rport=60000)]
        inspector = FakeInspector(connections=conns)
        result = filter_connections(inspector)
        assert len(result) == 1
        row = result[0]
        assert row["pid"] == 42
        assert row["process_name"] == "python"
        assert row["local_port"] == 5000
        assert row["remote_port"] == 60000
        assert "protocol" in row
        assert "state" in row
        # No sentinel / metadata keys
        assert "_truncated" not in row

    def test_no_sentinel_in_result_even_when_capped(self):
        """Ensure the list never contains any internal _truncated sentinel dict."""
        conns = [_conn(pid=i, lport=i + 1000) for i in range(20)]
        inspector = FakeInspector(connections=conns)
        result = filter_connections(inspector, max_results=5)
        for row in result:
            assert "_truncated" not in row
            assert "pid" in row


# ---------------------------------------------------------------------------
# diagnose_port enrichment: parent_name + connections in observations
# ---------------------------------------------------------------------------


class TestDiagnosePortEnrichment:
    def test_observations_has_connections_key(self):
        """diagnose_port observations must include a 'connections' list."""
        from kport.diagnostics import diagnose_port

        inspector = FakeInspector()
        with patch("kport.diagnostics.docker_mappings_for_host_port", return_value=[]):
            result = diagnose_port(8080, inspector)

        assert "connections" in result["observations"]
        assert isinstance(result["observations"]["connections"], list)

    def test_observations_connections_bounded_to_50(self):
        """Active connections in observations must be capped at 50."""
        from kport.diagnostics import diagnose_port

        many_conns = [_conn(pid=i, lport=8080, rport=50000 + i) for i in range(80)]
        inspector = FakeInspector(connections=many_conns)
        with patch("kport.diagnostics.docker_mappings_for_host_port", return_value=[]):
            result = diagnose_port(8080, inspector)

        obs_conns = result["observations"]["connections"]
        assert len(obs_conns) <= 50

    def test_process_enriched_with_parent_name(self):
        """When a process has a ppid, observations.processes[n].parent_name should be set."""
        from kport.diagnostics import diagnose_port
        from kport.inspectors.base import PortBinding

        parent_pi = ProcessInfo(pid=1, name="systemd")
        child_pi = ProcessInfo(pid=1234, name="node", ppid=1)
        inspector = FakeInspector(
            pids_on_port={8080: [1234]},
            process_info={1: parent_pi, 1234: child_pi},
            bindings_on_port={
                8080: [
                    PortBinding(
                        port=8080,
                        family="inet",
                        laddr="127.0.0.1:8080",
                        pid=1234,
                        process_name="node",
                        state="LISTEN",
                    )
                ]
            },
        )
        with (
            patch("kport.diagnostics.docker_mappings_for_host_port", return_value=[]),
            patch("kport.diagnostics.detect_process_manager", return_value=None),
        ):
            result = diagnose_port(8080, inspector)

        processes = result["observations"]["processes"]
        assert len(processes) == 1
        proc = processes[0]
        assert proc["pid"] == 1234
        assert proc["ppid"] == 1
        assert proc["parent_name"] == "systemd"

    def test_process_without_ppid_has_parent_name_none(self):
        """When a process has no ppid, parent_name should be None."""
        from kport.diagnostics import diagnose_port
        from kport.inspectors.base import PortBinding

        pi = ProcessInfo(pid=500, name="nginx")  # ppid defaults to None
        inspector = FakeInspector(
            pids_on_port={80: [500]},
            process_info={500: pi},
            bindings_on_port={
                80: [
                    PortBinding(
                        port=80,
                        family="inet",
                        laddr="0.0.0.0:80",
                        pid=500,
                        process_name="nginx",
                        state="LISTEN",
                    )
                ]
            },
        )
        with (
            patch("kport.diagnostics.docker_mappings_for_host_port", return_value=[]),
            patch("kport.diagnostics.detect_process_manager", return_value=None),
        ):
            result = diagnose_port(80, inspector, bypass_safety=True)

        proc = result["observations"]["processes"][0]
        assert proc["parent_name"] is None

    def test_unknown_process_has_parent_name_key(self):
        """When PID info is unavailable, the process dict must still have parent_name."""
        from kport.diagnostics import diagnose_port
        from kport.inspectors.base import PortBinding

        # Empty process_info: get_process_info returns None -> unknown process path
        inspector = FakeInspector(
            pids_on_port={9000: [9999]},
            process_info={},  # PID 9999 unknown
            bindings_on_port={
                9000: [
                    PortBinding(
                        port=9000,
                        family="inet",
                        laddr="0.0.0.0:9000",
                        pid=9999,
                        process_name=None,
                        state="LISTEN",
                    )
                ]
            },
        )
        with patch("kport.diagnostics.docker_mappings_for_host_port", return_value=[]):
            result = diagnose_port(9000, inspector)

        proc = result["observations"]["processes"][0]
        assert "parent_name" in proc
        assert proc["pid"] == 9999


# ---------------------------------------------------------------------------
# handle_list_connections unit tests
# ---------------------------------------------------------------------------


class TestHandleListConnections:
    def test_returns_correct_structure(self):
        conns = [_conn(lport=8080), _conn(lport=9000)]
        inspector = FakeInspector(connections=conns)
        result = handle_list_connections(inspector)
        assert "connections" in result
        assert "count" in result
        assert "capped" in result
        assert isinstance(result["connections"], list)
        assert result["count"] == 2
        assert result["capped"] is False

    def test_capped_flag_true_when_at_limit(self):
        conns = [_conn(pid=i, lport=i + 1000) for i in range(10)]
        inspector = FakeInspector(connections=conns)
        result = handle_list_connections(inspector, max_results=10)
        assert result["capped"] is True
        assert result["count"] == 10

    def test_capped_flag_false_when_under_limit(self):
        conns = [_conn(pid=i, lport=i + 1000) for i in range(5)]
        inspector = FakeInspector(connections=conns)
        result = handle_list_connections(inspector, max_results=10)
        assert result["capped"] is False

    def test_filters_forwarded_to_filter_connections(self):
        conns = [
            _conn(pid=1, name="node", lport=8080),
            _conn(pid=2, name="nginx", lport=80),
        ]
        inspector = FakeInspector(connections=conns)
        result = handle_list_connections(inspector, process="nginx")
        assert result["count"] == 1
        assert result["connections"][0]["process_name"] == "nginx"

    def test_max_results_clamped_to_schema_max(self):
        """max_results > 2000 must be clamped to 2000."""
        conns = [_conn(pid=i, lport=i + 1000) for i in range(5)]
        inspector = FakeInspector(connections=conns)
        result = handle_list_connections(inspector, max_results=99999)
        assert result["count"] == 5  # only 5 conns, all returned

    def test_max_results_clamped_to_minimum(self):
        """max_results < 1 must be clamped to 1."""
        conns = [_conn(pid=i, lport=i + 1000) for i in range(5)]
        inspector = FakeInspector(connections=conns)
        result = handle_list_connections(inspector, max_results=0)
        assert result["count"] == 1


# ---------------------------------------------------------------------------
# MCP list_connections tool: full round-trip tests
# ---------------------------------------------------------------------------


class TestMCPListConnections:
    def _mock_conns(self, n=3):
        mock_c_list = []
        for i in range(n):
            c = MagicMock(spec=ConnectionInfo)
            c.pid = 100 + i
            c.process_name = "node"
            c.proto = "tcp"
            c.local_address = "127.0.0.1"
            c.local_port = 8080 + i
            c.remote_address = "127.0.0.1"
            c.remote_port = 50000 + i
            c.state = "ESTABLISHED"
            mock_c_list.append(c)
        return mock_c_list

    def test_list_connections_tool_in_tools_list(self):
        names = {t["name"] for t in TOOLS}
        assert "list_connections" in names

    def test_list_connections_tool_has_schema(self):
        tool = next(t for t in TOOLS if t["name"] == "list_connections")
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        props = schema["properties"]
        assert "pid" in props
        assert "process" in props
        assert "port" in props
        assert "state" in props
        assert "max_results" in props

    def test_list_connections_no_args_returns_all(self):
        mock_inspector = MagicMock()
        mock_inspector.list_connections.return_value = self._mock_conns(3)

        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
            responses = _send_messages(
                {
                    "jsonrpc": "2.0",
                    "id": 30,
                    "method": "tools/call",
                    "params": {"name": "list_connections", "arguments": {}},
                }
            )

        assert len(responses) == 1
        result = responses[0]["result"]
        assert result["isError"] is False
        data = json.loads(result["content"][0]["text"])
        assert "connections" in data
        assert "count" in data
        assert "capped" in data
        assert data["count"] == 3

    def test_list_connections_with_process_filter(self):
        mock_inspector = MagicMock()
        mock_inspector.list_connections.return_value = self._mock_conns(2)

        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
            responses = _send_messages(
                {
                    "jsonrpc": "2.0",
                    "id": 31,
                    "method": "tools/call",
                    "params": {
                        "name": "list_connections",
                        "arguments": {"process": "node"},
                    },
                }
            )

        result = responses[0]["result"]
        assert result["isError"] is False
        data = json.loads(result["content"][0]["text"])
        assert data["count"] >= 0

    def test_list_connections_with_max_results(self):
        mock_inspector = MagicMock()
        mock_inspector.list_connections.return_value = self._mock_conns(10)

        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
            responses = _send_messages(
                {
                    "jsonrpc": "2.0",
                    "id": 32,
                    "method": "tools/call",
                    "params": {
                        "name": "list_connections",
                        "arguments": {"max_results": 2},
                    },
                }
            )

        data = json.loads(responses[0]["result"]["content"][0]["text"])
        assert data["count"] <= 2
        assert data["capped"] is True

    def test_list_connections_is_read_only_no_safety_check(self):
        """list_connections must work on protected ports without any safety error."""
        mock_inspector = MagicMock()
        mock_inspector.list_connections.return_value = []

        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
            responses = _send_messages(
                {
                    "jsonrpc": "2.0",
                    "id": 33,
                    "method": "tools/call",
                    "params": {
                        "name": "list_connections",
                        "arguments": {"port": 22},
                    },
                }
            )

        result = responses[0]["result"]
        assert result["isError"] is False


# ---------------------------------------------------------------------------
# MCP isError consistency
# ---------------------------------------------------------------------------


class TestMCPIsErrorConsistency:
    """Verify isError=False for tools that return lists (conflicts) or dicts without success."""

    def test_conflicts_is_error_false(self):
        mock_inspector = MagicMock()
        mock_inspector.list_listening.return_value = []

        with (
            patch("kport.mcp_server.get_inspector", return_value=mock_inspector),
            patch("kport.mcp_server.list_docker_mappings", return_value=[]),
        ):
            responses = _send_messages(
                {
                    "jsonrpc": "2.0",
                    "id": 40,
                    "method": "tools/call",
                    "params": {"name": "conflicts", "arguments": {}},
                }
            )

        assert responses[0]["result"]["isError"] is False

    def test_doctor_is_error_false(self):
        mock_inspector = MagicMock()
        mock_inspector.list_listening.return_value = []
        mock_inspector.list_connections.return_value = []

        with (
            patch("kport.mcp_server.get_inspector", return_value=mock_inspector),
            patch("kport.diagnostics.docker_available", return_value=False),
        ):
            responses = _send_messages(
                {
                    "jsonrpc": "2.0",
                    "id": 41,
                    "method": "tools/call",
                    "params": {"name": "doctor", "arguments": {}},
                }
            )

        assert responses[0]["result"]["isError"] is False

    def test_list_connections_is_error_false(self):
        mock_inspector = MagicMock()
        mock_inspector.list_connections.return_value = []

        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
            responses = _send_messages(
                {
                    "jsonrpc": "2.0",
                    "id": 42,
                    "method": "tools/call",
                    "params": {"name": "list_connections", "arguments": {}},
                }
            )

        assert responses[0]["result"]["isError"] is False
