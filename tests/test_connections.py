import os
import sys
from unittest.mock import patch, MagicMock
import pytest

from kport.cli import handle_connections
from kport.inspectors.base import ConnectionInfo
from kport.inspectors.psutil_impl import PsutilInspector
from kport.inspectors.system_impl import FallbackInspector, _parse_proc_net_connections


def test_connection_info_dataclass():
    """Verify ConnectionInfo dataclass initialization and field defaults."""
    conn = ConnectionInfo(
        pid=1234,
        process_name="test-proc",
        proto="tcp",
        local_address="127.0.0.1",
        local_port=8080,
        remote_address="*",
        remote_port=None,
        state="LISTEN",
    )
    assert conn.pid == 1234
    assert conn.process_name == "test-proc"
    assert conn.proto == "tcp"
    assert conn.local_address == "127.0.0.1"
    assert conn.local_port == 8080
    assert conn.remote_address == "*"
    assert conn.remote_port is None
    assert conn.state == "LISTEN"


def test_list_connections_psutil_and_fallback_live():
    """Smoke test: Query connections on the host machine using both backends."""
    # Verifies that both inspectors run and execute native calls without crashing.
    p_inspector = PsutilInspector()
    p_conns = p_inspector.list_connections()
    assert isinstance(p_conns, list)

    f_inspector = FallbackInspector()
    f_conns = f_inspector.list_connections()
    assert isinstance(f_conns, list)


def test_linux_proc_net_tcp_parsing(tmp_path):
    """Verify proc net tcp connection string parses states and address hex strings correctly."""
    # 127.0.0.1:8080 -> 127.0.0.1:80, state ESTABLISHED (01)
    # 0.0.0.0:80 -> 0.0.0.0:0, state LISTEN (0A)
    fake_content = (
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 0100007F:1F90 0200007F:0050 01 00000000:00000000 00:00000000 00000000  1000        0 12345 1 abcdef\n"
        "   1: 00000000:0050 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 12346 1 abcdef\n"
    )
    tcp_file = tmp_path / "tcp"
    tcp_file.write_text(fake_content)

    res = _parse_proc_net_connections(str(tcp_file), "IPv4")
    assert len(res) == 2

    # 127.0.0.1:8080 -> 127.0.0.2:80 (0200007F little-endian = 127.0.0.2), state ESTABLISHED
    assert res[0][0] == "127.0.0.1"
    assert res[0][1] == 8080
    assert res[0][2] == "127.0.0.2"
    assert res[0][3] == 80
    assert res[0][4] == "ESTABLISHED"
    assert res[0][5] == 12345

    # 0.0.0.0:80 LISTEN -> remote masked to *
    assert res[1][0] == "0.0.0.0"
    assert res[1][1] == 80
    assert res[1][2] == "*"
    assert res[1][3] == 0
    assert res[1][4] == "LISTEN"
    assert res[1][5] == 12346


def test_handle_connections_cli_filtering(capsys):
    """Verify handle_connections formats, prints, and filters connection details correctly."""
    mock_conns = [
        ConnectionInfo(100, "java", "tcp", "127.0.0.1", 8080, "127.0.0.1", 5432, "ESTABLISHED"),
        ConnectionInfo(200, "python", "tcp", "127.0.0.1", 5000, "*", None, "LISTEN"),
        ConnectionInfo(100, "java", "tcp", "127.0.0.1", 8081, "*", None, "LISTEN"),
    ]
    inspector = MagicMock()
    inspector.list_connections.return_value = mock_conns

    # 1. No filters
    args = MagicMock(pid=None, process=None, port=None, state=None, json=False)
    status = handle_connections(args, inspector)
    assert status == 0
    out, _ = capsys.readouterr()
    assert "java" in out
    assert "python" in out
    assert "3 connection(s) found." in out

    # 2. Filter by PID
    args = MagicMock(pid=200, process=None, port=None, state=None, json=False)
    handle_connections(args, inspector)
    out, _ = capsys.readouterr()
    assert "python" in out
    assert "java" not in out
    assert "1 connection(s) found." in out

    # 3. Filter by process name (case-insensitive substring)
    args = MagicMock(pid=None, process="PyTh", port=None, state=None, json=False)
    handle_connections(args, inspector)
    out, _ = capsys.readouterr()
    assert "python" in out
    assert "java" not in out

    # 4. Filter by port (matches local or remote)
    args = MagicMock(pid=None, process=None, port=5432, state=None, json=False)
    handle_connections(args, inspector)
    out, _ = capsys.readouterr()
    assert "5432" in out
    assert "8080" in out
    assert "8081" not in out

    # 5. Filter by state
    args = MagicMock(pid=None, process=None, port=None, state="established", json=False)
    handle_connections(args, inspector)
    out, _ = capsys.readouterr()
    assert "ESTABLISHED" in out
    assert "LISTEN" not in out

    # 6. JSON output verification
    args = MagicMock(pid=None, process=None, port=None, state=None, json=True)
    handle_connections(args, inspector)
    out, _ = capsys.readouterr()
    assert '"schema_version": 1' in out
    assert '"command": "connections"' in out
    assert '"count": 3' in out
