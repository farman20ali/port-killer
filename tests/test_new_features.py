import json
from unittest.mock import MagicMock, patch

from kport.profile import load_profiles, resolve_profile
from kport.notify import notify as _desktop_notify
from kport.cli import handle_product_command
from kport.mcp_server import handle_kill_port
from kport.inspectors import get_inspector
# pyrefly: ignore [missing-import]
from tests.test_commands import FakeInspector, _args


# 1. Profile Module Tests
def test_load_profiles():
    config = {
        "profiles": {
            "dev": [8080, "9000", "invalid"],
            "prod": 80,  # invalid type
        }
    }
    profiles = load_profiles(config)
    assert "dev" in profiles
    assert profiles["dev"] == [8080, 9000]
    assert "prod" not in profiles


def test_resolve_profile():
    profiles = {"dev-stack": [8080, 9000]}
    assert resolve_profile("dev-stack", profiles) == [8080, 9000]
    assert resolve_profile("DEV-stack", profiles) == [8080, 9000]
    assert resolve_profile("missing", profiles) is None


# 2. Desktop Notification Test
@patch("kport.notify._dispatch")
def test_desktop_notify_success(mock_dispatch):
    _desktop_notify("Title", "Message")
    mock_dispatch.assert_called_once_with("Title", "Message")


# 3. CLI --profile support
def test_cli_inspect_with_profile(capsys):
    config = {
        "profiles": {
            "web": [8080]
        }
    }
    inspector = FakeInspector()
    args = _args(command="inspect", profile="web", json=True)
    with patch("kport.cli.load_config", return_value=config):
        with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
            rc = handle_product_command(args, inspector)

    assert rc == 5  # EXIT_PORT_FREE
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["schema_version"] == 1
    assert envelope["command"] == "inspect"
    assert envelope["data"]["type"] == "free"


# 4. MCP Server Safety Config Additive Check
def test_mcp_safety_config_additive():
    # Mock load_mcp_config to return custom protected ports
    config = {"protected_ports": [9999]}
    mock_inspector = MagicMock()
    mock_inspector.find_pids_on_port.return_value = []
    mock_inspector.find_bindings_on_port.return_value = []

    with patch("kport.mcp_server.load_mcp_config", return_value=config):
        with patch("kport.mcp_server.get_inspector", return_value=mock_inspector):
            # Port 22 (default protected) must still be blocked!
            res_22 = handle_kill_port(mock_inspector, 22)
            assert res_22["success"] is False
            assert "Security Shield" in res_22["message"]

            # Port 9999 (config protected) must also be blocked!
            res_9999 = handle_kill_port(mock_inspector, 9999)
            assert res_9999["success"] is False
            assert "Security Shield" in res_9999["message"]

            # Port 8080 (unprotected) must succeed
            res_8080 = handle_kill_port(mock_inspector, 8080)
            assert res_8080["success"] is True


# 5. Inspector Selection Logic Tests
def test_get_inspector_fallback():
    from kport.inspectors.system_impl import FallbackInspector

    with patch("kport.inspectors._psutil_accessible", return_value=False):
        inspector = get_inspector()
        assert isinstance(inspector, FallbackInspector)


def test_get_inspector_psutil():
    from kport.inspectors.psutil_impl import PsutilInspector

    with patch("kport.inspectors._psutil_accessible", return_value=True):
        inspector = get_inspector()
        assert isinstance(inspector, PsutilInspector)


# 6. Child PID Fetching Tests
def test_psutil_inspector_get_child_pids():
    from kport.inspectors.psutil_impl import PsutilInspector
    
    mock_child1 = MagicMock()
    mock_child1.pid = 5678
    mock_child2 = MagicMock()
    mock_child2.pid = 9012
    
    mock_process = MagicMock()
    mock_process.children.return_value = [mock_child1, mock_child2]
    
    with patch("psutil.Process", return_value=mock_process):
        inspector = PsutilInspector()
        children = inspector.get_child_pids(1234)
        assert children == [5678, 9012]
        mock_process.children.assert_called_once_with(recursive=True)

