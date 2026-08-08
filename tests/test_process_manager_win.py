import os
import subprocess
from unittest.mock import patch, MagicMock
import pytest

from kport.process_manager import detect_process_manager


def test_detect_windows_service_success():
    """Verify that detect_process_manager correctly identifies Windows services."""
    # Simulate a successful tasklist /SVC return mapping a service
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = '"svchost.exe","1308","BrokerInfrastructure,DcomLaunch,PlugPlay"\n'
    
    with patch("os.name", "nt"), \
         patch("subprocess.run", return_value=mock_proc) as mock_run:
        res = detect_process_manager(1308)
        
        assert res is not None
        assert res["manager"] == "windows-service"
        assert res["name"] == "BrokerInfrastructure,DcomLaunch,PlugPlay"
        assert res["managed_by"] == "windows-service:BrokerInfrastructure,DcomLaunch,PlugPlay"
        assert "Killing PID triggers auto-restart" in res["warning"]
        
        # Verify correct tasklist parameters were passed
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "tasklist" in args
        assert "/SVC" in args
        assert "PID eq 1308" in args[2]


def test_detect_windows_service_na():
    """Verify that detect_process_manager returns None if process has no associated service (N/A)."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = '"chrome.exe","4567","N/A"\n'
    
    with patch("os.name", "nt"), \
         patch("subprocess.run", return_value=mock_proc):
        res = detect_process_manager(4567)
        assert res is None


def test_detect_windows_service_no_process():
    """Verify that detect_process_manager returns None gracefully if no tasks are running."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = 'INFO: No tasks are running which match the specified criteria.\n'
    
    with patch("os.name", "nt"), \
         patch("subprocess.run", return_value=mock_proc):
        res = detect_process_manager(99999)
        assert res is None


def test_detect_windows_service_error():
    """Verify that detect_process_manager returns None gracefully on subprocess failures."""
    with patch("os.name", "nt"), \
         patch("subprocess.run", side_effect=subprocess.SubprocessError("Failed to execute")):
        res = detect_process_manager(1234)
        assert res is None


def test_detect_windows_service_skipped_on_unix():
    """Verify that Windows Service check is skipped completely on non-Windows platforms."""
    # Even if tasklist somehow returned a service, if os.name is 'posix' it should skip and check systemd/PM2
    with patch("os.name", "posix"), \
         patch("kport.process_manager._get_cgroup_systemd_unit", return_value=None), \
         patch("kport.process_manager._get_proc_environ", return_value={}):
        res = detect_process_manager(1234)
        assert res is None
