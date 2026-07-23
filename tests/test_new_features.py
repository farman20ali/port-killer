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
    config = {"profiles": {"web": [8080]}}
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


# 7. Wait For Exit Tests
def test_wait_for_exit_success(capsys):
    from kport.cli import handle_product_command
    from kport.inspectors.base import PortBinding

    polled = []

    class DynamicFakeInspector(FakeInspector):
        def find_pids_on_port(self, port: int, proto: str = "tcp"):
            return [1234]

        def find_bindings_on_port(self, port: int, proto: str = "tcp"):
            polled.append(1)
            if len(polled) == 1:
                return [
                    PortBinding(
                        port=port,
                        family="inet",
                        laddr=f"0.0.0.0:{port}",
                        pid=1234,
                        process_name="node",
                        state="LISTEN",
                    )
                ]
            return []

        def kill_port(self, port, **kwargs):
            return True, "freed"

    inspector = DynamicFakeInspector()
    args = _args(command="kill", port=8080, json=True, wait_for_exit=1.0)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)

    assert rc == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["schema_version"] == 1
    assert envelope["command"] == "kill"
    assert envelope["data"]["success"] is True
    assert envelope["data"]["wait_for_exit_ok"] is True
    assert len(polled) > 1


def test_wait_for_exit_timeout(capsys):
    from kport.cli import handle_product_command
    from kport.inspectors.base import PortBinding

    class TimeoutFakeInspector(FakeInspector):
        def find_pids_on_port(self, port: int, proto: str = "tcp"):
            return [1234]

        def find_bindings_on_port(self, port: int, proto: str = "tcp"):
            return [
                PortBinding(
                    port=port,
                    family="inet",
                    laddr=f"0.0.0.0:{port}",
                    pid=1234,
                    process_name="node",
                    state="LISTEN",
                )
            ]

        def kill_port(self, port, **kwargs):
            return True, "freed"

    inspector = TimeoutFakeInspector()
    args = _args(command="kill", port=8080, json=True, wait_for_exit=0.1)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)

    assert rc == 1  # EXIT_GENERAL_ERROR on wait timeout
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["data"]["success"] is True
    assert envelope["data"]["wait_for_exit_ok"] is False


def test_get_child_pids_unix():
    from kport.inspectors.system_impl import FallbackInspector

    inspector = FallbackInspector()

    # Mock self.system and self._run_subprocess
    inspector.system = "Linux"

    mock_ps_output = (
        " PPID   PID\n    1   100\n  100   101\n  101   102\n  100   103\n    2   200\n"
    )

    class FakeProc:
        returncode = 0
        stdout = mock_ps_output
        stderr = ""

    with patch.object(inspector, "_run_subprocess", return_value=FakeProc()):
        children = inspector.get_child_pids(100)
        # Should recursively get 101, 102, 103
        assert sorted(children) == [101, 102, 103]


def test_kill_process_tree_logic():
    from kport.inspectors.system_impl import FallbackInspector

    inspector = FallbackInspector()

    killed_pids = []

    def mock_kill_pid(pid, **kwargs):
        killed_pids.append(pid)
        return True, "killed"

    with patch.object(inspector, "get_child_pids", return_value=[101, 102]):
        with patch.object(inspector, "kill_pid", side_effect=mock_kill_pid):
            ok, msg = inspector.kill_process_tree(100)
            assert ok is True
            # Depth-first order: [101, 102, 100]
            assert killed_pids == [101, 102, 100]


def test_cli_kill_tree_option(capsys):
    from kport.cli import handle_product_command

    called_kill_tree = []

    class TreeFakeInspector(FakeInspector):
        def find_pids_on_port(self, port: int, proto: str = "tcp"):
            return [500]

        def kill_port(self, port, **kwargs):
            if kwargs.get("kill_tree"):
                called_kill_tree.append(port)
            return True, "Port freed"

    inspector = TreeFakeInspector()
    args = _args(command="kill", port=8080, json=True, kill_tree=True)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)

    assert rc == 0
    assert called_kill_tree == [8080]


# ---------------------------------------------------------------------------
# 8. UDP Support Tests (Phase 1.2)
# ---------------------------------------------------------------------------


# 8.1 PortBinding.proto field defaults to "tcp"
def test_port_binding_proto_default():
    from kport.inspectors.base import PortBinding

    b = PortBinding(
        port=5353,
        family="inet",
        laddr="0.0.0.0:5353",
        pid=42,
        process_name="mdnsd",
        state="LISTEN",
    )
    assert b.proto == "tcp"


# 8.2 PortBinding.proto can be set to "udp"
def test_port_binding_proto_udp():
    from kport.inspectors.base import PortBinding

    b = PortBinding(
        port=5353,
        family="inet",
        laddr="0.0.0.0:5353",
        pid=42,
        process_name="mdnsd",
        state="UDP",
        proto="udp",
    )
    assert b.proto == "udp"


# 8.3 PsutilInspector.list_listening filters by proto=tcp
def test_psutil_list_listening_tcp_only():
    from kport.inspectors.psutil_impl import PsutilInspector

    tcp_conn = MagicMock()
    tcp_conn.laddr = MagicMock(ip="0.0.0.0", port=8080)
    tcp_conn.family = MagicMock(name="AF_INET")
    tcp_conn.status = "LISTEN"
    tcp_conn.pid = 111

    udp_conn = MagicMock()
    udp_conn.laddr = MagicMock(ip="0.0.0.0", port=5353)
    udp_conn.family = MagicMock(name="AF_INET")
    udp_conn.status = ""
    udp_conn.pid = 222

    inspector = PsutilInspector()

    with patch("psutil.net_connections", return_value=[tcp_conn]):
        with patch("psutil.Process") as mock_proc:
            mock_proc.return_value.name.return_value = "node"
            result = inspector.list_listening(proto="tcp")

    assert all(b.proto == "tcp" for b in result)
    ports = [b.port for b in result]
    assert 8080 in ports
    assert 5353 not in ports


# 8.4 PsutilInspector.list_listening with proto=udp skips tcp LISTEN filter
def test_psutil_list_listening_udp_only():
    from kport.inspectors.psutil_impl import PsutilInspector

    udp_conn = MagicMock()
    udp_conn.laddr = MagicMock(ip="0.0.0.0", port=5353)
    udp_conn.family = MagicMock(name="AF_INET")
    udp_conn.status = ""
    udp_conn.pid = 222

    inspector = PsutilInspector()

    with patch("psutil.net_connections", return_value=[udp_conn]):
        with patch("psutil.Process") as mock_proc:
            mock_proc.return_value.name.return_value = "mdnsd"
            result = inspector.list_listening(proto="udp")

    assert all(b.proto == "udp" for b in result)
    ports = [b.port for b in result]
    assert 5353 in ports


# 8.5 PsutilInspector.list_listening with proto=both returns tcp and udp
def test_psutil_list_listening_both():
    from kport.inspectors.psutil_impl import PsutilInspector

    tcp_conn = MagicMock()
    tcp_conn.laddr = MagicMock(ip="0.0.0.0", port=8080)
    tcp_conn.family = MagicMock(name="AF_INET")
    tcp_conn.status = "LISTEN"
    tcp_conn.pid = 111

    udp_conn = MagicMock()
    udp_conn.laddr = MagicMock(ip="0.0.0.0", port=5353)
    udp_conn.family = MagicMock(name="AF_INET")
    udp_conn.status = ""
    udp_conn.pid = 222

    inspector = PsutilInspector()

    # "both" calls net_connections twice: once for 'tcp', once for 'udp'
    def fake_net_connections(kind):
        if kind == "tcp":
            return [tcp_conn]
        return [udp_conn]

    with patch("psutil.net_connections", side_effect=fake_net_connections):
        with patch("psutil.Process") as mock_proc:
            mock_proc.return_value.name.return_value = "svc"
            result = inspector.list_listening(proto="both")

    protos = {b.proto for b in result}
    assert "tcp" in protos
    assert "udp" in protos


# 8.6 PsutilInspector.find_bindings_on_port proto-filtering
def test_psutil_find_bindings_on_port_proto():
    from kport.inspectors.psutil_impl import PsutilInspector

    udp_conn = MagicMock()
    udp_conn.laddr = MagicMock(ip="0.0.0.0", port=5353)
    udp_conn.family = MagicMock(name="AF_INET")
    udp_conn.status = ""
    udp_conn.pid = 999

    inspector = PsutilInspector()

    with patch("psutil.net_connections", return_value=[udp_conn]):
        with patch("psutil.Process") as mock_proc:
            mock_proc.return_value.name.return_value = "mdnsd"
            bindings = inspector.find_bindings_on_port(5353, proto="udp")

    assert len(bindings) == 1
    assert bindings[0].proto == "udp"
    assert bindings[0].port == 5353


# 8.7 FallbackInspector.list_listening proto-filters native linux results
def test_fallback_list_listening_filters_proto():
    from kport.inspectors.system_impl import FallbackInspector
    from kport.inspectors.base import PortBinding

    inspector = FallbackInspector()
    inspector.system = "Linux"

    tcp_binding = PortBinding(
        port=8080,
        family="inet",
        laddr="0.0.0.0:8080",
        pid=1,
        process_name="node",
        state="LISTEN",
        proto="tcp",
    )
    udp_binding = PortBinding(
        port=5353,
        family="inet",
        laddr="0.0.0.0:5353",
        pid=2,
        process_name="mdnsd",
        state="UDP",
        proto="udp",
    )

    with patch(
        "kport.inspectors.system_impl._list_listening_linux_native",
        return_value=[tcp_binding, udp_binding],
    ):
        tcp_only = inspector.list_listening(proto="tcp")
        udp_only = inspector.list_listening(proto="udp")
        both = inspector.list_listening(proto="both")

    assert all(b.proto == "tcp" for b in tcp_only)
    assert all(b.proto == "udp" for b in udp_only)
    assert len(both) == 2


# 8.8 CLI list command passes proto to inspector
def test_cli_list_command_proto_udp(capsys):
    from kport.inspectors.base import PortBinding

    received_proto = []

    class UDPFakeInspector(FakeInspector):
        def list_listening(self, proto: str = "tcp"):
            received_proto.append(proto)
            if proto in ("udp", "both"):
                return [
                    PortBinding(
                        port=5353,
                        family="inet",
                        laddr="0.0.0.0:5353",
                        pid=10,
                        process_name="mdnsd",
                        state="UDP",
                        proto="udp",
                    )
                ]
            return []

    inspector = UDPFakeInspector()
    args = _args(command="list", json=True, proto="udp")
    with patch("kport.cli.list_docker_mappings", return_value=[]):
        rc = handle_product_command(args, inspector)

    assert rc == 0
    assert received_proto == ["udp"]
    out = json.loads(capsys.readouterr().out)
    local = out["data"]["local"]
    assert any(b.get("proto") == "udp" for b in local)


# 8.9 CLI inspect command passes proto=both; proto is forwarded to inspector
def test_cli_inspect_command_proto_both(capsys):
    from kport.inspectors.base import PortBinding

    called_with_proto = []

    class BothFakeInspector(FakeInspector):
        def find_bindings_on_port(self, port: int, proto: str = "tcp"):
            called_with_proto.append(proto)
            # Return bindings with no visible PID mapping (triggers local-unknown path)
            # which exposes the 'bindings' field in JSON output.
            return [
                PortBinding(
                    port=port,
                    family="inet",
                    laddr=f"0.0.0.0:{port}",
                    pid=None,
                    process_name=None,
                    state="LISTEN",
                    proto="tcp",
                ),
                PortBinding(
                    port=port,
                    family="inet",
                    laddr=f"0.0.0.0:{port}",
                    pid=None,
                    process_name=None,
                    state="UDP",
                    proto="udp",
                ),
            ]

        def find_pids_on_port(self, port: int, proto: str = "tcp"):
            return []  # No visible PIDs → triggers local-unknown branch with bindings in JSON

    inspector = BothFakeInspector()
    args = _args(command="inspect", port=8080, json=True, proto="both")
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)

    assert rc == 0
    # Verify proto was forwarded to the inspector
    assert called_with_proto == ["both"]
    out = json.loads(capsys.readouterr().out)
    assert out["command"] == "inspect"
    # With no pids but bindings present → type=local-unknown, bindings list exposed
    data = out["data"]
    assert data["type"] == "local-unknown"
    bindings = data.get("bindings", [])
    protos = {b.get("proto") for b in bindings}
    assert "tcp" in protos
    assert "udp" in protos


# 8.10 CLI kill command with proto=udp kills UDP binding
def test_cli_kill_command_proto_udp(capsys):
    from kport.inspectors.base import PortBinding

    killed = []

    class UDPKillInspector(FakeInspector):
        def find_pids_on_port(self, port: int, proto: str = "tcp"):
            if proto == "udp":
                return [777]
            return []

        def find_bindings_on_port(self, port: int, proto: str = "tcp"):
            if proto == "udp":
                return [
                    PortBinding(
                        port=port,
                        family="inet",
                        laddr=f"0.0.0.0:{port}",
                        pid=777,
                        process_name="dnsmasq",
                        state="UDP",
                        proto="udp",
                    )
                ]
            return []

        def kill_port(self, port, **kwargs):
            killed.append((port, kwargs.get("proto", "tcp")))
            return True, "killed"

    inspector = UDPKillInspector()
    args = _args(command="kill", port=5353, json=True, proto="udp")
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["data"]["success"] is True


# ---------------------------------------------------------------------------
# 9. Process Manager Awareness Tests (Phase 3.1)
# ---------------------------------------------------------------------------


# 9.1 Invalid PID returns None
def test_detect_process_manager_invalid_pid():
    from kport.process_manager import detect_process_manager

    assert detect_process_manager(0) is None
    assert detect_process_manager(-1) is None


# 9.2 systemd service detection via /proc/<pid>/cgroup
def test_detect_process_manager_systemd():
    from kport.process_manager import detect_process_manager
    from unittest.mock import mock_open

    cgroup_data = "0::/system.slice/nginx.service\n"
    m_open = mock_open(read_data=cgroup_data)
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", m_open):
            res = detect_process_manager(1234)

    assert res is not None
    assert res["manager"] == "systemd"
    assert res["name"] == "nginx.service"
    assert res["managed_by"] == "systemd:nginx.service"
    assert "systemctl stop nginx.service" in res["warning"]


# 9.3 PM2 app detection via /proc/<pid>/environ
def test_detect_process_manager_pm2():
    from kport.process_manager import _detect_pm2_app

    env = {"PM2_HOME": "/home/user/.pm2", "name": "api-server"}
    res = _detect_pm2_app(5678, env)
    assert res == "api-server"


# 9.4 Supervisor app detection via supervisorctl
def test_detect_process_manager_supervisor():
    from kport.process_manager import detect_process_manager

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "worker_01   RUNNING   pid 4321, uptime 0:05:00\n"

    with patch("shutil.which", return_value="/usr/bin/supervisorctl"):
        with patch("subprocess.run", return_value=mock_proc):
            with patch(
                "kport.process_manager._get_cgroup_systemd_unit", return_value=None
            ):
                res = detect_process_manager(4321)

    assert res is not None
    assert res["manager"] == "supervisor"
    assert res["name"] == "worker_01"
    assert res["managed_by"] == "supervisor:worker_01"


# 9.5 CLI explain command includes managed_by in JSON envelope
def test_cli_explain_managed_by_json(capsys):
    from kport.inspectors.base import ProcessInfo

    class ManagedFakeInspector(FakeInspector):
        def find_pids_on_port(self, port: int, proto: str = "tcp"):
            return [999]

        def get_process_info(self, pid: int):
            return ProcessInfo(
                pid=999, name="nginx", exe="/usr/sbin/nginx", cmdline=["nginx"]
            )

    inspector = ManagedFakeInspector()
    args = _args(command="explain", port=80, json=True)

    pm_res = {
        "manager": "systemd",
        "name": "nginx.service",
        "managed_by": "systemd:nginx.service",
        "warning": "Managed by systemd",
    }

    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        with patch("kport.cli.detect_process_manager", return_value=pm_res):
            rc = handle_product_command(args, inspector)

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["command"] == "explain"
    assert out["data"]["managed_by"] == "systemd:nginx.service"


# ---------------------------------------------------------------------------
# 10. Watch Mode --until & --timeout Tests (Phase 3.3)
# ---------------------------------------------------------------------------


# 10.1 watch --until free satisfied immediately if port is free
def test_cli_watch_until_free_initial():
    inspector = FakeInspector()
    args = _args(command="watch", port=8080, until="free", interval=0.01)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)
    assert rc == 0


# 10.2 watch --until occupied satisfied immediately if port is occupied
def test_cli_watch_until_occupied_initial():
    from kport.inspectors.base import PortBinding

    inspector = FakeInspector(
        bindings_on_port={
            8080: [
                PortBinding(
                    port=8080,
                    family="inet",
                    laddr="0.0.0.0:8080",
                    pid=10,
                    process_name="node",
                    state="LISTEN",
                )
            ]
        },
        pids_on_port={8080: [10]},
    )
    args = _args(command="watch", port=8080, until="occupied", interval=0.01)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)
    assert rc == 0


# 10.3 watch --until free transitions from occupied to free
def test_cli_watch_until_free_transitions():
    from kport.inspectors.base import PortBinding

    polls = [0]

    class TransitionFakeInspector(FakeInspector):
        def find_pids_on_port(self, port: int, proto: str = "tcp"):
            polls[0] += 1
            if polls[0] == 1:
                return [100]
            return []

        def find_bindings_on_port(self, port: int, proto: str = "tcp"):
            if polls[0] == 1:
                return [
                    PortBinding(
                        port=port,
                        family="inet",
                        laddr=f"0.0.0.0:{port}",
                        pid=100,
                        process_name="node",
                        state="LISTEN",
                    )
                ]
            return []

    inspector = TransitionFakeInspector()
    args = _args(command="watch", port=8080, until="free", interval=0.01)
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)

    assert rc == 0
    assert polls[0] >= 2


# 10.4 watch --until free times out if condition not met
def test_cli_watch_until_timeout(capsys):
    from kport.inspectors.base import PortBinding

    inspector = FakeInspector(
        bindings_on_port={
            8080: [
                PortBinding(
                    port=8080,
                    family="inet",
                    laddr="0.0.0.0:8080",
                    pid=10,
                    process_name="node",
                    state="LISTEN",
                )
            ]
        },
        pids_on_port={8080: [10]},
    )
    args = _args(
        command="watch", port=8080, until="free", timeout=0.02, interval=0.01, json=True
    )
    with patch("kport.cli.docker_mappings_for_host_port", return_value=[]):
        rc = handle_product_command(args, inspector)

    assert rc == 1
    lines = [line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()]
    # Last line is the timeout JSON output
    out = json.loads(lines[-1])
    assert out["event"] == "timeout"
    assert out["success"] is False


# ---------------------------------------------------------------------------
# 11. Interactive Picker Tests (Phase 3.2)
# ---------------------------------------------------------------------------


# 11.1 _fetch_interactive_rows gathers local and docker rows
def test_fetch_interactive_rows():
    from kport.interactive import _fetch_interactive_rows
    from kport.inspectors.base import PortBinding

    inspector = FakeInspector(
        listening=[
            PortBinding(
                port=8080,
                family="inet",
                laddr="0.0.0.0:8080",
                pid=123,
                process_name="python",
                state="LISTEN",
            )
        ]
    )

    with patch("kport.interactive.list_docker_mappings", return_value=[]):
        rows = _fetch_interactive_rows(inspector)

    assert len(rows) == 1
    assert rows[0]["port"] == 8080
    assert rows[0]["process"] == "python"
    assert rows[0]["type"] == "local"


# 11.2 fallback_numbered_menu execution with selection
def test_fallback_numbered_menu_selection():
    from kport.interactive import _fallback_numbered_menu
    from kport.inspectors.base import PortBinding

    killed_ports = []

    class CustomInspector(FakeInspector):
        def list_listening(self, proto: str = "tcp"):
            return [
                PortBinding(
                    port=3000,
                    family="inet",
                    laddr="0.0.0.0:3000",
                    pid=55,
                    process_name="vite",
                    state="LISTEN",
                )
            ]

        def kill_port(self, port, **kwargs):
            killed_ports.append(port)
            return True, "killed"

    inspector = CustomInspector()
    args = _args(command="interactive", yes=True)

    with patch("builtins.input", return_value="1"):
        with patch("kport.interactive.list_docker_mappings", return_value=[]):
            rc = _fallback_numbered_menu(inspector, args)

    assert rc == 0
    assert killed_ports == [3000]


# 11.3 run_interactive_picker degrades gracefully in non-TTY mode
def test_run_interactive_picker_non_tty():
    from kport.interactive import run_interactive_picker

    inspector = FakeInspector()
    args = _args(command="interactive")

    with patch("sys.stdin.isatty", return_value=False):
        with patch("kport.interactive.list_docker_mappings", return_value=[]):
            rc = run_interactive_picker(inspector, args)

    assert rc == 0


# 11.4 _execute_kills confirmation yes
def test_execute_kills_confirmation_yes():
    from kport.interactive import _execute_kills

    inspector = FakeInspector()
    killed_ports = []
    inspector.kill_port = lambda port, **kwargs: (killed_ports.append(port) or True, "killed")

    args = _args(command="interactive", yes=False)
    selected_rows = [
        {"type": "local", "port": 8080, "pid": 123, "process": "node", "proto": "tcp", "state": "LISTEN", "managed_by": ""}
    ]

    with patch("kport.interactive.confirm_prompt", return_value=True) as mock_confirm:
        rc = _execute_kills(inspector, selected_rows, args)

    assert rc == 0
    assert killed_ports == [8080]
    mock_confirm.assert_called_once()


# 11.5 _execute_kills confirmation no
def test_execute_kills_confirmation_no():
    from kport.interactive import _execute_kills

    inspector = FakeInspector()
    killed_ports = []
    inspector.kill_port = lambda port, **kwargs: (killed_ports.append(port) or True, "killed")

    args = _args(command="interactive", yes=False)
    selected_rows = [
        {"type": "local", "port": 8080, "pid": 123, "process": "node", "proto": "tcp", "state": "LISTEN", "managed_by": ""}
    ]

    with patch("kport.interactive.confirm_prompt", return_value=False) as mock_confirm:
        rc = _execute_kills(inspector, selected_rows, args)

    assert rc == 0
    assert killed_ports == []
    mock_confirm.assert_called_once()


# 11.6 _curses_main key handling (search, quit /q, reload /r, Ctrl-r, Esc)
def test_curses_main_key_handling():
    from kport.interactive import run_interactive_picker
    from unittest.mock import MagicMock, patch
    from kport.inspectors.base import PortBinding

    # Mock inspector listening ports
    inspector = FakeInspector(
        listening=[
            PortBinding(
                port=8080,
                family="inet",
                laddr="0.0.0.0:8080",
                pid=123,
                process_name="node",
                state="LISTEN",
            )
        ]
    )
    args = _args(command="interactive", yes=True) # skip final prompt

    # Mock stdscr
    mock_stdscr = MagicMock()
    mock_stdscr.getmaxyx.return_value = (24, 80)

    # Scenario: User types 'n', then Esc (27) to clear, then types '/' then 'q' to quit
    keys = [ord('n'), 27, ord('/'), ord('q')]
    mock_stdscr.getch.side_effect = keys

    with patch("sys.stdin.isatty", return_value=True), \
         patch("sys.stdout.isatty", return_value=True), \
         patch("kport.interactive.list_docker_mappings", return_value=[]), \
         patch("curses.wrapper", side_effect=lambda func: func(mock_stdscr)), \
         patch("curses.curs_set"), \
         patch("curses.start_color"), \
         patch("curses.use_default_colors"), \
         patch("curses.init_pair"), \
         patch("curses.color_pair"):
             
        rc = run_interactive_picker(inspector, args)
        assert rc == 0


# 11.7 _curses_main reload key handling (Ctrl-r and /r)
def test_curses_main_reload_handling():
    from kport.interactive import run_interactive_picker
    from unittest.mock import MagicMock, patch

    inspector = FakeInspector()
    args = _args(command="interactive", yes=True)

    mock_stdscr = MagicMock()
    mock_stdscr.getmaxyx.return_value = (24, 80)

    # Scenario: Ctrl-r (18) then /r (ord('/'), ord('r')) then Esc (27) to quit
    keys = [18, ord('/'), ord('r'), 27]
    mock_stdscr.getch.side_effect = keys

    with patch("sys.stdin.isatty", return_value=True), \
         patch("sys.stdout.isatty", return_value=True), \
         patch("kport.interactive.list_docker_mappings", return_value=[]), \
         patch("curses.wrapper", side_effect=lambda func: func(mock_stdscr)), \
         patch("curses.curs_set"), \
         patch("curses.start_color"), \
         patch("curses.use_default_colors"), \
         patch("curses.init_pair"), \
         patch("curses.color_pair"):
             
        rc = run_interactive_picker(inspector, args)
        assert rc == 0
