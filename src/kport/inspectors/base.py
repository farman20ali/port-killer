"""
Base inspector interface and class definitions for kport.
Implements the unified, escalated port-killing and validation workflow.
"""

import platform
import subprocess
import shutil
import signal
import time
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass

@dataclass
class ProcessInfo:
    pid: int
    name: str
    exe: Optional[str] = None
    cmdline: Optional[List[str]] = None
    user: Optional[str] = None


@dataclass
class PortBinding:
    port: int
    family: str
    laddr: str
    pid: Optional[int] = None
    process_name: Optional[str] = None
    state: Optional[str] = None


class BaseInspector:
    def list_listening(self) -> List[PortBinding]:
        """List all active listening ports."""
        raise NotImplementedError()

    def find_pids_on_port(self, port: int) -> List[int]:
        """Find PIDs currently bound to a port."""
        raise NotImplementedError()

    def find_bindings_on_port(self, port: int) -> List[PortBinding]:
        """Find listening bindings for a specific port."""
        return [b for b in self.list_listening() if b.port == port]

    def get_process_info(self, pid: int) -> Optional[ProcessInfo]:
        """Get details about a specific process PID."""
        raise NotImplementedError()

    def find_pids_by_name(self, name: str, exact: bool = False) -> List[int]:
        """Find PIDs matching a process name."""
        raise NotImplementedError()

    def find_ports_by_process_name(self, name: str, exact: bool = False) -> List[PortBinding]:
        """Find port bindings matching a process name."""
        raise NotImplementedError()

    def send_signal(self, pid: int, sig: int) -> bool:
        """Send a standard signal (TERM, KILL) to target PID."""
        raise NotImplementedError()

    def is_process_alive(self, pid: int) -> bool:
        """Check if process is active."""
        raise NotImplementedError()

    def kill_pid(self, pid: int, graceful_timeout: float = 3.0, force: bool = False, dry_run: bool = False) -> Tuple[bool, str]:
        """
        Attempt to terminate a process by sending SIGTERM,
        waiting up to graceful_timeout, and escalating to SIGKILL if forced.
        """
        if dry_run:
            return True, "Dry-run: would terminate process"

        # Stage 1: Graceful SIGTERM
        try:
            self.send_signal(pid, signal.SIGTERM)
        except ProcessLookupError:
            return True, "Process disappeared before signal"
        except PermissionError:
            return False, "Permission denied"
        except Exception as e:
            return False, f"SIGTERM error: {e}"

        # Stage 2: Wait & Poll
        start = time.time()
        while time.time() - start < graceful_timeout:
            time.sleep(0.1)
            if not self.is_process_alive(pid):
                return True, "Terminated gracefully"

        if not force:
            return False, "Still running after graceful timeout"

        # Stage 3: Forceful SIGKILL
        try:
            self.send_signal(pid, signal.SIGKILL)
            time.sleep(0.3)  # Wait for kernel scheduling
            if not self.is_process_alive(pid):
                return True, "Killed (force)"
            return False, "Process ignored SIGKILL"
        except ProcessLookupError:
            return True, "Process disappeared"
        except PermissionError:
            return False, "Permission denied on force kill"
        except Exception as e:
            return False, f"SIGKILL error: {e}"

    def kill_port(self, port: int, graceful_timeout: float = 3.0, force: bool = False, dry_run: bool = False, debug: bool = False) -> Tuple[bool, str]:
        """
        Kill all processes using a specific port.
        Executes a bulletproof multi-stage kill escalation path:
        1. Find PIDs on port.
        2. Send SIGTERM.
        3. Poll wait up to timeout.
        4. If PIDs survive and force is True, send SIGKILL.
        5. If Linux and PIDs still survive, execute fuser fallback as a system utility.
        6. Verify socket.
        """
        if dry_run:
            return True, f"Dry-run: would terminate port {port}"

        pids = self.find_pids_on_port(port)
        if not pids:
            return True, "No process found on port"

        killed_count = 0
        errors = []
        remaining_pids = []

        # Step 1: Kill individual PIDs using standard escalation signals
        for pid in pids:
            ok, msg = self.kill_pid(pid, graceful_timeout, force, dry_run)
            if ok:
                killed_count += 1
            else:
                remaining_pids.append(pid)
                errors.append(f"PID {pid}: {msg}")

        # Step 2: System-level fuser fallback on Linux (if forced and fuser exists)
        if remaining_pids and platform.system() != "Windows" and force and shutil.which("fuser"):
            if debug:
                print(f"[debug] PIDs {remaining_pids} survived standard signals. Triggering fuser fallback...", file=sys.stderr)
            try:
                # fuser -k sends SIGKILL directly to all processes bound to the port
                subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True, text=True, timeout=5)
                time.sleep(0.5)
                remaining_pids = [p for p in remaining_pids if self.is_process_alive(p)]
                if not remaining_pids:
                    return True, f"Port {port} successfully freed via fuser fallback"
            except Exception as e:
                errors.append(f"fuser fallback failed: {e}")

        if not remaining_pids:
            return True, f"Killed {len(pids)} process(es)"

        # Step 3: Final socket verification check
        actual_remaining = self.find_pids_on_port(port)
        if actual_remaining:
            return False, f"Failed to free port. Remaining PIDs: {actual_remaining}. Errors: {'; '.join(errors)}"

        return True, "Port successfully freed"
