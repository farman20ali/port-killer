"""
Automated unit tests for kport MCP server (tests/test_mcp.py).

Tests the JSON-RPC protocol handler in isolation by mocking
stdin/stdout and calling run_mcp_server() in a controlled loop.

Run with:  pytest tests/test_mcp.py -v
"""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import MagicMock, patch


from kport.mcp_server import run_mcp_server, TOOLS, PROTECTED_PORTS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _send_messages(*messages: dict) -> list[dict]:
    """
    Feed a sequence of JSON-RPC messages to the MCP server and collect responses.
    Notifications (no 'id') produce no response.
    """
    lines = [json.dumps(m) + "\n" for m in messages]
    stdin_data = "".join(lines)

    captured_stdout = StringIO()

    with patch("sys.stdin", StringIO(stdin_data)):
        with patch("sys.stdout", captured_stdout):
            with patch("sys.stderr", StringIO()):   # suppress MCP debug logs
                run_mcp_server()

    raw = captured_stdout.getvalue()
    responses = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if line:
            responses.append(json.loads(line))
    return responses


# ---------------------------------------------------------------------------
# initialize
# ---------------------------------------------------------------------------

def test_initialize_returns_protocol_version():
    """initialize must echo back protocolVersion 2024-11-05 and server name."""
    responses = _send_messages(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "0.1"},
            },
        }
    )
    assert len(responses) == 1
    result = responses[0]["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "kport"


# ---------------------------------------------------------------------------
# tools/list
# ---------------------------------------------------------------------------

def test_tools_list_returns_all_tools():
    """tools/list must return all three registered tools."""
    responses = _send_messages(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    )
    assert len(responses) == 1
    tool_names = {t["name"] for t in responses[0]["result"]["tools"]}
    assert tool_names == {"list_ports", "inspect_port", "kill_port"}


def test_tools_have_required_schema_fields():
    """Each tool must declare name, description, and inputSchema."""
    for tool in TOOLS:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool


# ---------------------------------------------------------------------------
# tools/call – list_ports
# ---------------------------------------------------------------------------

def test_list_ports_returns_dict_with_lists():
    """list_ports must return a dict with local_processes and docker_containers keys."""
    mock_inspector = MagicMock()
    mock_inspector.list_listening.return_value = []

    with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
        with patch("kport.mcp_server.list_docker_mappings", return_value=[]):
            responses = _send_messages(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "list_ports", "arguments": {}},
                }
            )

    assert len(responses) == 1
    content_text = responses[0]["result"]["content"][0]["text"]
    data = json.loads(content_text)
    assert "local_processes" in data
    assert "docker_containers" in data
    assert isinstance(data["local_processes"], list)
    assert isinstance(data["docker_containers"], list)


# ---------------------------------------------------------------------------
# tools/call – inspect_port
# ---------------------------------------------------------------------------

def test_inspect_port_free():
    """inspect_port on a port with no listeners must return type=free."""
    mock_inspector = MagicMock()
    mock_inspector.find_bindings_on_port.return_value = []
    mock_inspector.find_pids_on_port.return_value = []

    with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
        with patch("kport.mcp_server.docker_mappings_for_host_port", return_value=[]):
            responses = _send_messages(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "inspect_port", "arguments": {"port": 19999}},
                }
            )

    data = json.loads(responses[0]["result"]["content"][0]["text"])
    assert data["type"] == "free"
    assert data["port"] == 19999


def test_inspect_port_out_of_bounds_raises():
    """inspect_port with an invalid port number must return an isError response."""
    responses = _send_messages(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "inspect_port", "arguments": {"port": 99999}},
        }
    )
    assert len(responses) == 1
    assert responses[0]["result"]["isError"] is True


# ---------------------------------------------------------------------------
# tools/call – kill_port (safety shield tests)
# ---------------------------------------------------------------------------

def test_kill_port_protected_port_is_blocked():
    """kill_port on a protected port must return success=False without executing kill."""
    protected = next(iter(PROTECTED_PORTS))  # e.g. 22

    responses = _send_messages(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "kill_port", "arguments": {"port": protected}},
        }
    )

    data = json.loads(responses[0]["result"]["content"][0]["text"])
    assert data["success"] is False
    assert "Security Shield" in data["message"]


def test_kill_port_free_port_succeeds():
    """kill_port on a free port must report success=True (nothing to kill)."""
    mock_inspector = MagicMock()
    mock_inspector.find_pids_on_port.return_value = []
    mock_inspector.find_bindings_on_port.return_value = []

    with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
        with patch("kport.mcp_server.docker_mappings_for_host_port", return_value=[]):
            responses = _send_messages(
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "kill_port",
                        "arguments": {"port": 19998, "force": True},
                    },
                }
            )

    data = json.loads(responses[0]["result"]["content"][0]["text"])
    assert data["success"] is True


# ---------------------------------------------------------------------------
# Notification – no response expected
# ---------------------------------------------------------------------------

def test_initialized_notification_produces_no_response():
    """notifications/initialized is a one-way message and must produce no response."""
    responses = _send_messages(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    assert responses == []


# ---------------------------------------------------------------------------
# Unknown method
# ---------------------------------------------------------------------------

def test_unknown_method_returns_method_not_found():
    """An unknown method with an id must return error code -32601."""
    responses = _send_messages(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "does/not/exist",
            "params": {},
        }
    )
    assert len(responses) == 1
    error = responses[0]["error"]
    assert error["code"] == -32601
    assert "not found" in error["message"].lower()
