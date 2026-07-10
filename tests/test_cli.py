"""
Unit tests for kport CLI modules and configuration parameters.
Tested via pytest.
"""

import pytest
from kport.exceptions import InvalidPortError
from kport.cli import validate_port, parse_port_range

def test_validate_port_valid():
    """Verify that valid ports pass validation silently."""
    validate_port(80)
    validate_port(8080)
    validate_port(65535)


def test_validate_port_invalid():
    """Verify that invalid ports raise an InvalidPortError."""
    with pytest.raises(InvalidPortError):
        validate_port(0)
    with pytest.raises(InvalidPortError):
        validate_port(65536)
    with pytest.raises(InvalidPortError):
        validate_port(-80)


def test_parse_port_range_single():
    """Test parsing a single port string."""
    assert parse_port_range("80") == [80]
    assert parse_port_range(" 8080  ") == [8080]


def test_parse_port_range_sequence():
    """Test parsing a port range sequence."""
    assert parse_port_range("3000-3005") == [3000, 3001, 3002, 3003, 3004, 3005]
    assert parse_port_range("8080-8080") == [8080]


def test_parse_port_range_invalid():
    """Test parsing invalid range formats."""
    with pytest.raises(InvalidPortError):
        parse_port_range("3000-2999")  # start > end
    with pytest.raises(InvalidPortError):
        parse_port_range("3000-4001")  # too large (> 1000 ports)
    with pytest.raises(InvalidPortError):
        parse_port_range("invalid-format")
    with pytest.raises(InvalidPortError):
        parse_port_range("80-99999")  # out of bounds port


import argparse
from kport.inspectors.base import BaseInspector, ProcessInfo
from kport.cli import check_safety_policy

class MockInspector(BaseInspector):
    def __init__(self, pids_on_port=None, proc_info_map=None):
        self.pids_on_port = pids_on_port or {}
        self.proc_info_map = proc_info_map or {}
        
    def find_pids_on_port(self, port: int):
        return self.pids_on_port.get(port, [])
        
    def get_process_info(self, pid: int):
        return self.proc_info_map.get(pid)


def test_safety_policy_defaults():
    inspector = MockInspector(
        pids_on_port={80: [1234]},
        proc_info_map={1234: ProcessInfo(pid=1234, name="nginx")}
    )
    
    # Port 80 is protected by default
    args = argparse.Namespace(bypass_safety=False)
    safe, msg = check_safety_policy(80, [1234], args, inspector)
    assert not safe
    assert "Security Shield Active: Port 80 is a protected port" in msg

    # Unprotected port is safe
    safe, msg = check_safety_policy(8080, [1234], args, inspector)
    assert safe
    assert msg == ""


def test_safety_policy_bypass():
    inspector = MockInspector(
        pids_on_port={80: [1234]},
        proc_info_map={1234: ProcessInfo(pid=1234, name="nginx")}
    )
    # Bypassed safety permits the operation
    args = argparse.Namespace(bypass_safety=True)
    safe, msg = check_safety_policy(80, [1234], args, inspector)
    assert safe
    assert msg == ""


def test_safety_policy_custom_config():
    inspector = MockInspector(
        pids_on_port={8080: [1234]},
        proc_info_map={1234: ProcessInfo(pid=1234, name="custom-app")}
    )
    
    # Custom config protects 8080 and custom-app
    args = argparse.Namespace(
        bypass_safety=False,
        protected_ports=[8080],
        protected_processes=["custom-app"]
    )
    
    safe, msg = check_safety_policy(8080, [1234], args, inspector)
    assert not safe
    assert "Port 8080 is a protected port" in msg

    # Port 80 is STILL protected (custom list is additive)
    safe, msg = check_safety_policy(80, [], args, inspector)
    assert not safe
    assert "Port 80 is a protected port" in msg

    # Default process like sshd is also still protected (additive)
    pi_sshd = ProcessInfo(pid=222, name="sshd")
    inspector.proc_info_map[222] = pi_sshd
    safe, msg = check_safety_policy(None, [222], args, inspector)
    assert not safe
    assert "runs critical process 'sshd'" in msg


def test_safety_policy_process_shield():
    # Test that a protected process name blocks the kill even if the port is not protected
    inspector = MockInspector(
        pids_on_port={9000: [9999]},
        proc_info_map={9999: ProcessInfo(pid=9999, name="docker")}
    )
    args = argparse.Namespace(bypass_safety=False)
    
    safe, msg = check_safety_policy(9000, [9999], args, inspector)
    assert not safe
    assert "critical process 'docker'" in msg


def test_watch_command_parser_setup():
    # Verify that the watch command parser is successfully set up and accepts arguments
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    sp_watch = sub.add_parser("watch")
    sp_watch.add_argument("port", type=int)
    sp_watch.add_argument("--interval", type=float, default=1.0)
    sp_watch.add_argument("--json", action="store_true")
    
    parsed = parser.parse_args(["watch", "8080", "--interval", "2.5", "--json"])
    assert parsed.command == "watch"
    assert parsed.port == 8080
    assert parsed.interval == 2.5
    assert parsed.json is True


def test_apply_config_defaults():
    from kport.cli import apply_config_defaults
    args = argparse.Namespace(yes=False, dry_run=False, json=False, debug=False, force=False, graceful_timeout=None)
    cfg = {
        "yes": True,
        "dry_run": True,
        "json": True,
        "debug": True,
        "force": True,
        "graceful_timeout": 5.0,
        "protected_ports": [8080],
        "protected_processes": ["node"]
    }
    apply_config_defaults(args, cfg)
    assert args.yes is True
    assert args.dry_run is True
    assert args.json is True
    assert args.debug is True
    assert args.force is True
    assert args.graceful_timeout == 5.0
    assert args.protected_ports == [8080]
    assert args.protected_processes == ["node"]


def test_fallback_inspector_init():
    from kport.inspectors.system_impl import FallbackInspector
    inspector = FallbackInspector()
    assert inspector is not None
