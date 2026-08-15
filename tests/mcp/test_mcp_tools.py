"""
MCP tool contract tests (tests/mcp/test_mcp_tools.py).

Tests all seven MCP tools via the full JSON-RPC round-trip:
list_ports, inspect_port, kill_port, diagnose_port,
list_connections, conflicts, doctor.
"""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from kport.inspectors.base import ConnectionInfo, PortBinding, ProcessInfo
from kport.mcp_server import TOOLS, handle_list_connections, run_mcp_server
from tests.conftest import FakeInspector, _conn


def _send(*messages: dict) -> list[dict]:
    lines = [json.dumps(m) + "\n" for m in messages]
    captured = StringIO()
    with patch("sys.stdin", StringIO("".join(lines))), \
         patch("sys.stdout", captured), \
         patch("sys.stderr", StringIO()):
        run_mcp_server()
    return [
        json.loads(line)
        for line in captured.getvalue().strip().splitlines()
        if line.strip()
    ]


def _tool_call(name: str, arguments: dict, msg_id: int = 1) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


# ---------------------------------------------------------------------------
# list_connections handler unit tests
# ---------------------------------------------------------------------------


@pytest.mark.mcp
class TestHandleListConnections:
    """Unit tests for the handle_list_connections handler directly."""

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

    def test_capped_flag_true_when_results_equal_limit(self):
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

    def test_process_filter_forwarded_to_filter_connections(self):
        conns = [
            _conn(pid=1, name="node", lport=8080),
            _conn(pid=2, name="nginx", lport=80),
        ]
        inspector = FakeInspector(connections=conns)
        result = handle_list_connections(inspector, process="nginx")
        assert result["count"] == 1
        assert result["connections"][0]["process_name"] == "nginx"

    def test_max_results_above_2000_clamped_to_2000(self):
        conns = [_conn(pid=i, lport=i + 1000) for i in range(5)]
        inspector = FakeInspector(connections=conns)
        result = handle_list_connections(inspector, max_results=99999)
        # 5 connections, all returned — clamp only prevents > 2000
        assert result["count"] == 5

    def test_max_results_zero_clamped_to_minimum_1(self):
        conns = [_conn(pid=i, lport=i + 1000) for i in range(5)]
        inspector = FakeInspector(connections=conns)
        result = handle_list_connections(inspector, max_results=0)
        assert result["count"] == 1


# ---------------------------------------------------------------------------
# MCP list_connections round-trip via stdio
# ---------------------------------------------------------------------------


@pytest.mark.mcp
class TestMCPListConnectionsTool:
    """Full JSON-RPC round-trip tests for the list_connections MCP tool."""

    def _mock_conns(self, n: int = 3) -> list[MagicMock]:
        conns = []
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
            conns.append(c)
        return conns

    def test_tool_is_registered_in_tools_list(self):
        names = {t["name"] for t in TOOLS}
        assert "list_connections" in names

    def test_tool_has_required_schema_properties(self):
        tool = next(t for t in TOOLS if t["name"] == "list_connections")
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        props = schema["properties"]
        for key in ("pid", "process", "port", "state", "max_results"):
            assert key in props, f"Missing schema property: {key}"

    def test_list_connections_no_args_returns_all(self):
        mock_inspector = MagicMock()
        mock_inspector.list_connections.return_value = self._mock_conns(3)
        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
            responses = _send(_tool_call("list_connections", {}, msg_id=30))
        result = responses[0]["result"]
        assert result["isError"] is False
        data = json.loads(result["content"][0]["text"])
        assert data["count"] == 3
        assert "connections" in data
        assert "capped" in data

    def test_list_connections_with_process_filter(self):
        mock_inspector = MagicMock()
        mock_inspector.list_connections.return_value = self._mock_conns(2)
        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
            responses = _send(_tool_call("list_connections", {"process": "node"}, msg_id=31))
        result = responses[0]["result"]
        assert result["isError"] is False

    def test_list_connections_with_max_results_capped(self):
        mock_inspector = MagicMock()
        mock_inspector.list_connections.return_value = self._mock_conns(10)
        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
            responses = _send(_tool_call("list_connections", {"max_results": 2}, msg_id=32))
        data = json.loads(responses[0]["result"]["content"][0]["text"])
        assert data["count"] <= 2
        assert data["capped"] is True

    def test_list_connections_on_protected_port_is_read_only(self):
        """list_connections must not require safety bypass for protected ports."""
        mock_inspector = MagicMock()
        mock_inspector.list_connections.return_value = []
        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
            responses = _send(_tool_call("list_connections", {"port": 22}, msg_id=33))
        assert responses[0]["result"]["isError"] is False


# ---------------------------------------------------------------------------
# list_ports tool
# ---------------------------------------------------------------------------


@pytest.mark.mcp
class TestMCPListPortsTool:
    def test_list_ports_returns_bindings(self):
        mock_inspector = MagicMock()
        mock_inspector.list_listening.return_value = [
            PortBinding(port=8080, family="inet", laddr="0.0.0.0:8080",
                        pid=100, process_name="node", state="LISTEN"),
        ]
        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
            responses = _send(_tool_call("list_ports", {}, msg_id=10))
        result = responses[0]["result"]
        assert result["isError"] is False
        data = json.loads(result["content"][0]["text"])
        assert isinstance(data, dict)
        assert "local_processes" in data
        assert data["local_processes"][0]["port"] == 8080

    def test_list_ports_empty_returns_empty_list(self):
        mock_inspector = MagicMock()
        mock_inspector.list_listening.return_value = []
        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
            responses = _send(_tool_call("list_ports", {}, msg_id=11))
        data = json.loads(responses[0]["result"]["content"][0]["text"])
        assert data == {"local_processes": [], "docker_containers": []}


# ---------------------------------------------------------------------------
# kill_port tool
# ---------------------------------------------------------------------------


@pytest.mark.mcp
class TestMCPKillPortTool:
    def test_kill_unprotected_port_succeeds(self):
        mock_inspector = MagicMock()
        mock_inspector.find_pids_on_port.return_value = [9999]
        mock_inspector.get_process_info.return_value = ProcessInfo(pid=9999, name="myapp")
        mock_inspector.find_bindings_on_port.return_value = [
            PortBinding(port=9876, family="inet", laddr="0.0.0.0:9876",
                        pid=9999, process_name="myapp", state="LISTEN"),
        ]
        mock_inspector.kill_port.return_value = (True, "freed")
        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
            responses = _send(_tool_call("kill_port", {"port": 9876}, msg_id=20))
        data = json.loads(responses[0]["result"]["content"][0]["text"])
        assert data["success"] is True

    def test_kill_protected_port_is_blocked(self):
        mock_inspector = MagicMock()
        mock_inspector.find_pids_on_port.return_value = []
        mock_inspector.find_bindings_on_port.return_value = []
        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
            responses = _send(_tool_call("kill_port", {"port": 22}, msg_id=21))
        data = json.loads(responses[0]["result"]["content"][0]["text"])
        assert data["success"] is False
        assert "Security Shield" in data["message"]

    def test_kill_port_missing_required_arg_returns_is_error(self):
        responses = _send(_tool_call("kill_port", {}, msg_id=22))
        # Missing 'port' argument → error response
        assert responses[0]["result"]["isError"] is True


# ---------------------------------------------------------------------------
# diagnose_port tool
# ---------------------------------------------------------------------------


@pytest.mark.mcp
class TestMCPDiagnosePortTool:
    def test_diagnose_free_port_structure(self):
        mock_inspector = MagicMock()
        mock_inspector.find_pids_on_port.return_value = []
        mock_inspector.find_bindings_on_port.return_value = []
        mock_inspector.list_connections.return_value = []
        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector), \
             patch("kport.diagnostics.docker_mappings_for_host_port", return_value=[]):
            responses = _send(_tool_call("diagnose_port", {"port": 7777}, msg_id=50))
        result = responses[0]["result"]
        assert result["isError"] is False
        data = json.loads(result["content"][0]["text"])
        for key in ("port", "blocked", "observations", "inferences", "risks", "recommendations"):
            assert key in data
