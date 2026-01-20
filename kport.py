#!/usr/bin/env python3
"""
kport - Cross-platform port inspector and killer (upgraded)

Features:
- Uses psutil when available for reliable cross-platform behavior.
- Safe subprocess usage (no shell=True).
- Class-based inspector architecture: UnixInspector / WindowsInspector.
- JSON output (--json).
- Dry-run (--dry-run).
- Graceful kill (SIGTERM) then forced kill (SIGKILL) fallback with timeout.
- --exact matching for process names, --yes to skip confirmations.
- Port range parsing with limit (max 1000 ports).
- Dependency checks and helpful error messages.
- Exit codes: 0 OK, 1 general error, 2 invalid input, 3 permission denied, 4 port used by Docker, 5 port free.
- Friendly tables with color, and machine-readable JSON.

Usage examples:
    kport.py -i 8080
    kport.py -im 3000 3001 3002
    kport.py -ir 3000-3010
    kport.py -ip node --exact
    kport.py -k 8080 --yes
    kport.py -kp node --dry-run --json

    # PRODUCT.md subcommand interface
    kport.py inspect 8080 --json
    kport.py explain 8080
    kport.py kill 8080
    kport.py list
    kport.py docker
    kport.py conflicts
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple, Any

# Try optional psutil for robust cross-platform behavior
try:
    import psutil  # type: ignore
    USING_PSUTIL = True
except Exception:
    USING_PSUTIL = False

# Colors (simple)
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def colorize(text: str, color: str) -> str:
    # basic check for Windows ANSI support: modern terminals typically handle this
    if platform.system() == "Windows":
        # Attempt simple enable; no-op if unsupported
        try:
            os.system("")  # enable ANSI processing in some terminals
        except Exception:
            pass
    return f"{color}{text}{Colors.RESET}"

def check_dependency(cmd: str) -> bool:
    """Return True if `cmd` is found on PATH."""
    return shutil.which(cmd) is not None

# Exit codes
EXIT_OK = 0
EXIT_GENERAL_ERROR = 1
EXIT_INVALID_INPUT = 2
EXIT_PERMISSION = 3
EXIT_PORT_DOCKER = 4
EXIT_PORT_FREE = 5


def debug_log(enabled: bool, msg: str) -> None:
    if enabled:
        print(colorize(f"[debug] {msg}", Colors.BLUE), file=sys.stderr)


def _default_config_paths() -> List[str]:
    home = os.path.expanduser("~")
    return [
        os.path.join(os.getcwd(), ".kport.json"),
        os.path.join(home, ".kport.json"),
        os.path.join(home, ".config", "kport", "config.json"),
    ]


def load_config(config_path: Optional[str], debug: bool = False) -> Dict[str, Any]:
    """Load JSON config file if present.

    Config is optional; parse failures are treated as invalid input.
    """
    candidate_paths: List[str] = []
    if config_path:
        candidate_paths = [config_path]
    else:
        candidate_paths = _default_config_paths()

    for path in candidate_paths:
        if not path:
            continue
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                debug_log(debug, f"Loaded config: {path}")
                return data
            debug_log(debug, f"Ignoring non-object config: {path}")
        except json.JSONDecodeError as e:
            print(colorize(f"Error: invalid JSON in config file {path}: {e}", Colors.RED), file=sys.stderr)
            sys.exit(EXIT_INVALID_INPUT)
        except Exception as e:
            print(colorize(f"Error: failed to read config file {path}: {e}", Colors.RED), file=sys.stderr)
            sys.exit(EXIT_INVALID_INPUT)
    return {}


def apply_config_defaults(args: argparse.Namespace, cfg: Dict[str, Any]) -> None:
    """Apply config as defaults (never overriding explicit CLI choices).

    Supported keys:
      - yes: bool
      - dry_run: bool
      - json: bool
      - debug: bool
      - force: bool
      - graceful_timeout: number
      - docker_action: "stop"|"restart"|"rm"
    """
    def _set_bool(name: str, key: str) -> None:
        if hasattr(args, name) and getattr(args, name) is False and isinstance(cfg.get(key), bool):
            setattr(args, name, cfg[key])

    def _set_num(name: str, key: str) -> None:
        if hasattr(args, name) and cfg.get(key) is not None:
            try:
                current = getattr(args, name)
                # Only apply if still at argparse default
                if name == "graceful_timeout" and float(current) == 3.0:
                    setattr(args, name, float(cfg[key]))
            except Exception:
                pass

    _set_bool("yes", "yes")
    _set_bool("dry_run", "dry_run")
    _set_bool("json", "json")
    _set_bool("debug", "debug")
    _set_bool("force", "force")
    _set_num("graceful_timeout", "graceful_timeout")

    if hasattr(args, "docker_action") and getattr(args, "docker_action", None) is None:
        v = cfg.get("docker_action")
        if v in ("stop", "restart", "rm"):
            setattr(args, "docker_action", v)

# Validation helpers
def validate_port(port: int) -> None:
    if not (1 <= port <= 65535):
        print(colorize(f"Error: Port {port} is not valid. Must be 1-65535.", Colors.RED), file=sys.stderr)
        sys.exit(EXIT_INVALID_INPUT)

def parse_port_range(port_range: str, max_ports: int = 1000) -> List[int]:
    """
    Parse a port or range string:
      - "8080" -> [8080]
      - "3000-3010" -> [3000..3010] (limit enforced)
    """
    try:
        if '-' in port_range:
            start_s, end_s = port_range.split('-', 1)
            start = int(start_s.strip())
            end = int(end_s.strip())
            if start > end:
                print(colorize(f"Error: invalid range {port_range}: start > end", Colors.RED), file=sys.stderr)
                sys.exit(EXIT_INVALID_INPUT)
            total = end - start + 1
            if total > max_ports:
                print(colorize(f"Error: range too large ({total} ports). Maximum {max_ports} allowed.", Colors.RED), file=sys.stderr)
                sys.exit(EXIT_INVALID_INPUT)
            for p in (start, end):
                validate_port(p)
            return list(range(start, end + 1))
        else:
            port = int(port_range.strip())
            validate_port(port)
            return [port]
    except ValueError:
        print(colorize(f"Error: invalid port or range format: {port_range}", Colors.RED), file=sys.stderr)
        sys.exit(EXIT_INVALID_INPUT)

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


@dataclass
class DockerPortMapping:
    container_id: str
    container_name: str
    image: str
    status: str
    host_ip: Optional[str]
    host_port: int
    container_port: int
    proto: str


def _run_docker(args: List[str], debug: bool = False) -> subprocess.CompletedProcess:
    debug_log(debug, f"docker {' '.join(args)}")
    return subprocess.run(["docker", *args], capture_output=True, text=True)


def docker_available() -> bool:
    return check_dependency("docker")


def list_docker_mappings(debug: bool = False) -> List[DockerPortMapping]:
    """Return host-port mappings for running containers via `docker ps` + `docker port`.

    This is intentionally CLI-based (no extra deps) and works on Linux/macOS/Windows
    where Docker CLI is present.
    """
    if not docker_available():
        return []

    ps = _run_docker(["ps", "--no-trunc", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}"], debug=debug)
    if ps.returncode != 0:
        debug_log(debug, f"docker ps failed: {ps.stderr.strip()}")
        return []

    mappings: List[DockerPortMapping] = []
    for line in (ps.stdout or "").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        container_id, name, image, status = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
        if not container_id:
            continue

        port_out = _run_docker(["port", container_id], debug=debug)
        if port_out.returncode != 0:
            debug_log(debug, f"docker port {container_id} failed: {port_out.stderr.strip()}")
            continue
        for pline in (port_out.stdout or "").splitlines():
            # Example lines:
            #   80/tcp -> 0.0.0.0:8080
            #   80/tcp -> :::8080
            pline = pline.strip()
            if not pline or "->" not in pline or "/" not in pline:
                continue

            left, right = [p.strip() for p in pline.split("->", 1)]
            # left: "80/tcp"
            m = re.match(r"^(\d+)\/(tcp|udp)$", left)
            if not m:
                continue
            container_port = int(m.group(1))
            proto = m.group(2)

            # right: "0.0.0.0:8080" or ":::8080" etc.
            # Parse host port as last :<digits> segment.
            host_ip: Optional[str] = None
            host_port: Optional[int] = None
            m2 = re.search(r":(\d+)$", right)
            if not m2:
                continue
            try:
                host_port = int(m2.group(1))
            except Exception:
                continue
            host_ip = right[: right.rfind(":")].strip() or None

            mappings.append(
                DockerPortMapping(
                    container_id=container_id,
                    container_name=name,
                    image=image,
                    status=status,
                    host_ip=host_ip,
                    host_port=host_port,
                    container_port=container_port,
                    proto=proto,
                )
            )

    # De-duplicate (Docker can return IPv4 + IPv6 lines for same mapping)
    seen = set()
    uniq: List[DockerPortMapping] = []
    for m in mappings:
        # docker often reports the same published port once for IPv4 (0.0.0.0)
        # and once for IPv6 (:::) — treat those as the same mapping for display.
        key = (m.container_id, m.host_port, m.container_port, m.proto)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(m)

    # Sort by host port, then name
    return sorted(uniq, key=lambda x: (x.host_port, x.container_name))


def docker_mappings_for_host_port(port: int, debug: bool = False) -> List[DockerPortMapping]:
    return [m for m in list_docker_mappings(debug=debug) if m.host_port == port]


def docker_action_on_container(container_id: str, action: str, dry_run: bool, debug: bool = False) -> Tuple[bool, str]:
    if dry_run:
        return True, f"Dry-run: would docker {action} {container_id}"
    if action == "stop":
        r = _run_docker(["stop", container_id], debug=debug)
    elif action == "restart":
        r = _run_docker(["restart", container_id], debug=debug)
    elif action == "rm":
        r = _run_docker(["rm", "-f", container_id], debug=debug)
    else:
        return False, f"Unknown docker action: {action}"
    if r.returncode == 0:
        return True, (r.stdout or "").strip() or f"docker {action} succeeded"
    return False, (r.stderr or r.stdout or "").strip() or f"docker {action} failed"

# Base inspector
class BaseInspector:
    def list_listening(self) -> List[PortBinding]:
        raise NotImplementedError()

    def find_pids_on_port(self, port: int) -> List[int]:
        raise NotImplementedError()

    def get_process_info(self, pid: int) -> Optional[ProcessInfo]:
        raise NotImplementedError()

    def find_pids_by_name(self, name: str, exact: bool = False) -> List[int]:
        raise NotImplementedError()

    def find_ports_by_process_name(self, name: str, exact: bool = False) -> List[PortBinding]:
        raise NotImplementedError()

    def kill_pid(self, pid: int, graceful_timeout: float = 3.0, force: bool = False, dry_run: bool = False) -> Tuple[bool, str]:
        """
        Attempt to kill process:
        - Try graceful termination first (SIGTERM / terminate)
        - Wait graceful_timeout seconds
        - If still alive and force True, force kill (SIGKILL / taskkill / /F)
        Returns (success, message)
        """
        raise NotImplementedError()

# psutil-based inspector (best behavior cross-platform)
class PsutilInspector(BaseInspector):
    def list_listening(self) -> List[PortBinding]:
        bindings: Dict[Tuple[int, str], PortBinding] = {}
        # net_connections returns many entries; filter relevant ones
        for conn in psutil.net_connections(kind='inet'):
            # laddr may be empty for some connection types
            if not conn.laddr:
                continue
            laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if hasattr(conn.laddr, 'ip') else f"{conn.laddr[0]}:{conn.laddr[1]}"
            port = conn.laddr.port if hasattr(conn.laddr, 'port') else conn.laddr[1]
            family = 'IPv6' if conn.family.name == 'AF_INET6' else 'IPv4'
            state = conn.status
            pid = conn.pid
            key = (port, state)
            proc_name = None
            if pid:
                try:
                    p = psutil.Process(pid)
                    proc_name = p.name()
                except Exception:
                    proc_name = None
            if (port, state) not in bindings:
                bindings[(port, state)] = PortBinding(
                    port=port,
                    family=family,
                    laddr=laddr,
                    pid=pid,
                    process_name=proc_name,
                    state=state
                )
        # Return sorted by port
        return sorted(bindings.values(), key=lambda b: b.port)

    def find_pids_on_port(self, port: int) -> List[int]:
        pids = set()
        for conn in psutil.net_connections(kind='inet'):
            if not conn.laddr:
                continue
            try:
                conn_port = conn.laddr.port if hasattr(conn.laddr, 'port') else conn.laddr[1]
            except Exception:
                continue
            if conn_port == port and conn.pid:
                pids.add(conn.pid)
        return sorted(pids)

    def get_process_info(self, pid: int) -> Optional[ProcessInfo]:
        try:
            p = psutil.Process(pid)
            return ProcessInfo(
                pid=pid,
                name=p.name(),
                exe=p.exe() if p.exe() else None,
                cmdline=p.cmdline() if p.cmdline() else None,
                user=p.username() if hasattr(p, 'username') else None
            )
        except Exception:
            return None

    def find_pids_by_name(self, name: str, exact: bool = False) -> List[int]:
        out = []
        name_lower = name.lower()
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                pname = (p.info['name'] or '')
                if pname is None:
                    pname = ''
                compare = pname.lower()
                match = (compare == name_lower) if exact else (name_lower in compare or any(name_lower in (c or '').lower() for c in (p.info.get('cmdline') or [])))
                if match:
                    out.append(p.info['pid'])
            except Exception:
                continue
        return sorted(set(out))

    def find_ports_by_process_name(self, name: str, exact: bool = False) -> List[PortBinding]:
        results: List[PortBinding] = []
        name_lower = name.lower()
        for conn in psutil.net_connections(kind='inet'):
            if not conn.laddr:
                continue
            pid = conn.pid
            if not pid:
                continue
            try:
                p = psutil.Process(pid)
                pname = (p.name() or '').lower()
                cmdline = ' '.join(p.cmdline() or []).lower()
                matched = (pname == name_lower) if exact else (name_lower in pname or name_lower in cmdline)
                if matched:
                    laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if hasattr(conn.laddr, 'ip') else f"{conn.laddr[0]}:{conn.laddr[1]}"
                    family = 'IPv6' if conn.family.name == 'AF_INET6' else 'IPv4'
                    results.append(PortBinding(
                        port=conn.laddr.port if hasattr(conn.laddr, 'port') else conn.laddr[1],
                        family=family,
                        laddr=laddr,
                        pid=pid,
                        process_name=p.name(),
                        state=conn.status
                    ))
            except Exception:
                continue
        return sorted(results, key=lambda b: (b.pid or 0, b.port))

    def kill_pid(self, pid: int, graceful_timeout: float = 3.0, force: bool = False, dry_run: bool = False) -> Tuple[bool, str]:
        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return False, "No such process"
        except Exception as e:
            return False, f"Failed to access process: {e}"

        if dry_run:
            return True, "Dry-run: would terminate process"

        try:
            proc.terminate()
        except psutil.AccessDenied:
            return False, "Permission denied"
        except Exception as e:
            return False, f"Error terminating: {e}"

        try:
            proc.wait(timeout=graceful_timeout)
            return True, "Terminated gracefully"
        except psutil.TimeoutExpired:
            if not force:
                return False, "Still running after graceful timeout"
            # force kill
            try:
                proc.kill()
                proc.wait(timeout=2)
                return True, "Killed (force)"
            except psutil.NoSuchProcess:
                return True, "Process disappeared after kill"
            except psutil.AccessDenied:
                return False, "Permission denied on force kill"
            except Exception as e:
                return False, f"Error on force kill: {e}"
        except Exception as e:
            return False, f"Error waiting for termination: {e}"

# Fallback inspector using shell utilities (safe subprocess calls without shell=True)
class FallbackInspector(BaseInspector):
    def __init__(self):
        self.system = platform.system()
        self._ps_exe = None
        if self.system == "Windows":
            self._ps_exe = shutil.which("powershell") or shutil.which("pwsh")

    def _powershell(self) -> Optional[str]:
        return self._ps_exe

    def _run_powershell_json(self, script: str) -> Optional[Any]:
        ps = self._powershell()
        if not ps:
            return None
        try:
            cmd = [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                return None
            out = (proc.stdout or "").strip()
            if not out:
                return None
            return json.loads(out)
        except Exception:
            return None

    def list_listening(self) -> List[PortBinding]:
        if self.system == "Windows":
            return self._windows_listening()
        else:
            return self._unix_listening()

    def _windows_listening(self) -> List[PortBinding]:
        bindings: List[PortBinding] = []
        # Prefer PowerShell (PRODUCT.md Phase 2) when available
        ps_data = self._run_powershell_json(
            "Get-NetTCPConnection -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess,State | ConvertTo-Json -Depth 3"
        )
        if ps_data is not None:
            items = ps_data if isinstance(ps_data, list) else [ps_data]
            for it in items:
                try:
                    port = int(it.get("LocalPort"))
                except Exception:
                    continue
                pid = None
                try:
                    pid = int(it.get("OwningProcess"))
                except Exception:
                    pid = None
                laddr = f"{it.get('LocalAddress')}:{port}"
                state = it.get("State")
                pname = None
                if pid:
                    info = self.get_process_info(pid)
                    pname = info.name if info else None
                bindings.append(PortBinding(port=port, family='IPv4', laddr=laddr, pid=pid, process_name=pname, state=state))
            return sorted(bindings, key=lambda b: b.port)

        # Fallback to `netstat -ano` and `tasklist` for process names
        if not check_dependency("netstat"):
            print(colorize("Error: netstat not found on PATH.", Colors.RED), file=sys.stderr)
            return bindings
        try:
            proc = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            lines = proc.stdout.splitlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Typical netstat line: TCP    0.0.0.0:80      0.0.0.0:0      LISTENING       1234
                parts = re.split(r'\s+', line)
                if len(parts) >= 5 and parts[0].upper() in ("TCP", "UDP"):
                    proto = parts[0]
                    local_addr = parts[1]
                    state = parts[3] if len(parts) >= 5 else ""
                    pid = None
                    try:
                        pid = int(parts[-1])
                    except Exception:
                        pid = None
                    # Extract port if local_addr contains :
                    if ':' in local_addr:
                        port_str = local_addr.rsplit(':', 1)[-1]
                        try:
                            port = int(port_str)
                        except ValueError:
                            continue
                        pname = None
                        if pid:
                            info = self.get_process_info(pid)
                            pname = info.name if info else None
                        bindings.append(PortBinding(port=port, family='IPv4', laddr=local_addr, pid=pid, process_name=pname, state=state))
        except Exception:
            pass
        return sorted(bindings, key=lambda b: b.port)

    def _unix_listening(self) -> List[PortBinding]:
        bindings: List[PortBinding] = []
        # Prefer lsof if available
        if check_dependency("lsof"):
            try:
                proc = subprocess.run(["lsof", "-i", "-P", "-n"], capture_output=True, text=True)
                lines = proc.stdout.splitlines()
                for line in lines:
                    if "LISTEN" not in line and "LISTENING" not in line:
                        continue
                    parts = re.split(r'\s+', line)
                    # Format often: COMMAND PID USER ... NAME
                    if len(parts) < 9:
                        continue
                    command = parts[0]
                    pid = None
                    user = parts[2] if len(parts) > 2 else None
                    try:
                        pid = int(parts[1])
                    except Exception:
                        pid = None
                    name_field = parts[8]
                    # address may be like *:8080 or 127.0.0.1:8080
                    if ':' in name_field:
                        port = None
                        try:
                            port = int(name_field.rsplit(':', 1)[-1])
                        except Exception:
                            continue
                        bindings.append(PortBinding(port=port, family='IPv4', laddr=name_field, pid=pid, process_name=command, state="LISTEN"))
            except Exception:
                pass
        else:
            # fallback to ss if available
            if check_dependency("ss"):
                try:
                    proc = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True)
                    lines = proc.stdout.splitlines()
                    # parse lines for LISTEN
                    for line in lines:
                        if "LISTEN" not in line:
                            continue
                        # example: LISTEN 0      128         127.0.0.1:8080     0.0.0.0:*    users:(("python3",pid=1234,fd=3))
                        parts = re.split(r'\s+', line)
                        for token in parts:
                            if ':' in token and re.search(r':\d+$', token):
                                try:
                                    port = int(token.rsplit(':', 1)[-1])
                                    # pid parse from users:(("name",pid=1234,fd=3))
                                    m = re.search(r'pid=(\d+)', line)
                                    pid = int(m.group(1)) if m else None
                                    pname = None
                                    if pid:
                                        info = self.get_process_info(pid)
                                        pname = info.name if info else None
                                    bindings.append(PortBinding(port=port, family='IPv4', laddr=token, pid=pid, process_name=pname, state="LISTEN"))
                                    break
                                except Exception:
                                    continue
                except Exception:
                    pass
        return sorted(bindings, key=lambda b: b.port)

    def find_pids_on_port(self, port: int) -> List[int]:
        if self.system == "Windows":
            return self._windows_pids_on_port(port)
        else:
            return self._unix_pids_on_port(port)

    def _windows_pids_on_port(self, port: int) -> List[int]:
        pids = set()
        # Prefer PowerShell
        ps_data = self._run_powershell_json(
            f"Get-NetTCPConnection -State Listen -LocalPort {port} | Select-Object -ExpandProperty OwningProcess | ConvertTo-Json -Depth 2"
        )
        if ps_data is not None:
            if isinstance(ps_data, list):
                for v in ps_data:
                    try:
                        pids.add(int(v))
                    except Exception:
                        continue
            else:
                try:
                    pids.add(int(ps_data))
                except Exception:
                    pass
            return sorted(pids)
        if not check_dependency("netstat"):
            return []
        proc = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        for line in proc.stdout.splitlines():
            parts = re.split(r'\s+', line.strip())
            if len(parts) >= 5:
                local_addr = parts[1]
                if ':' in local_addr and local_addr.rsplit(':', 1)[-1] == str(port):
                    try:
                        pid = int(parts[-1])
                        pids.add(pid)
                    except Exception:
                        continue
        return sorted(pids)

    def _unix_pids_on_port(self, port: int) -> List[int]:
        pids = set()
        # Prefer lsof
        if check_dependency("lsof"):
            proc = subprocess.run(["lsof", "-t", "-i", f":{port}"], capture_output=True, text=True)
            for line in proc.stdout.splitlines():
                try:
                    pids.add(int(line.strip()))
                except Exception:
                    continue
        else:
            # fallback to ss/grep netstat parsing
            if check_dependency("ss"):
                proc = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True)
                for line in proc.stdout.splitlines():
                    if f":{port} " in line or f":{port}\n" in line:
                        m = re.search(r'pid=(\d+)', line)
                        if m:
                            try:
                                pids.add(int(m.group(1)))
                            except Exception:
                                continue
        return sorted(pids)

    def get_process_info(self, pid: int) -> Optional[ProcessInfo]:
        try:
            if self.system == "Windows":
                # Prefer PowerShell
                ps_data = self._run_powershell_json(
                    f"Get-Process -Id {pid} | Select-Object Id,ProcessName,Path | ConvertTo-Json -Depth 3"
                )
                if isinstance(ps_data, dict):
                    name = ps_data.get("ProcessName")
                    exe = ps_data.get("Path")
                    if name:
                        return ProcessInfo(pid=pid, name=str(name), exe=str(exe) if exe else None)

                # fallback: tasklist
                proc = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True)
                out = proc.stdout.strip()
                if not out:
                    return None
                # Format: "Image Name","PID","Session Name","Session#","Mem Usage"
                parts = [p.strip().strip('"') for p in re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', out)]
                if parts:
                    name = parts[0]
                    return ProcessInfo(pid=pid, name=name)
            else:
                # Unix: use ps
                proc = subprocess.run(["ps", "-p", str(pid), "-o", "pid=,comm=,user=,args="], capture_output=True, text=True)
                out = proc.stdout.strip()
                if not out:
                    return None
                # Attempt parsing
                parts = re.split(r'\s+', out, maxsplit=2)
                if len(parts) >= 2:
                    name = parts[1]
                    user = parts[2].split()[0] if len(parts) >= 3 else None
                    return ProcessInfo(pid=pid, name=name, user=user)
        except Exception:
            return None
        return None

    def find_pids_by_name(self, name: str, exact: bool = False) -> List[int]:
        if self.system == "Windows":
            # tasklist with filter
            # tasklist /FI "IMAGENAME eq name*" may be used; use tasklist and filter in python for robustness
            proc = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True)
            out = proc.stdout or ""
            pids = []
            name_lower = name.lower()
            for line in out.splitlines():
                parts = [p.strip().strip('"') for p in re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', line)]
                if len(parts) >= 2:
                    pname = parts[0]
                    pid_s = parts[1]
                    try:
                        pid = int(pid_s)
                    except Exception:
                        continue
                    match = (pname.lower() == name_lower) if exact else (name_lower in pname.lower())
                    if match:
                        pids.append(pid)
            return sorted(pids)
        else:
            # use pgrep if available else ps/gawk
            if check_dependency("pgrep"):
                args = ["pgrep", "-f", name] if not exact else ["pgrep", "-x", name]
                proc = subprocess.run(args, capture_output=True, text=True)
                out = proc.stdout or ""
                pids = []
                for line in out.splitlines():
                    try:
                        pids.append(int(line.strip()))
                    except Exception:
                        continue
                return sorted(pids)
            else:
                # fallback to ps -ef
                proc = subprocess.run(["ps", "-ef"], capture_output=True, text=True)
                out = proc.stdout or ""
                pids = []
                for line in out.splitlines():
                    if name in line if exact else name.lower() in line.lower():
                        parts = re.split(r'\s+', line.strip())
                        if len(parts) >= 2:
                            try:
                                pids.append(int(parts[1]))
                            except Exception:
                                continue
                return sorted(set(pids))

    def find_ports_by_process_name(self, name: str, exact: bool = False) -> List[PortBinding]:
        results: List[PortBinding] = []
        # Use lsof to map processes to ports if available
        if check_dependency("lsof"):
            try:
                proc = subprocess.run(["lsof", "-i", "-P", "-n"], capture_output=True, text=True)
                out = proc.stdout or ""
                for line in out.splitlines():
                    if name.lower() not in line.lower() and (exact and name not in line):
                        continue
                    parts = re.split(r'\s+', line)
                    if len(parts) < 9:
                        continue
                    command = parts[0]
                    pid_s = parts[1]
                    try:
                        pid = int(pid_s)
                    except Exception:
                        pid = None
                    addr = parts[8]
                    # addr like *:8080
                    if ':' in addr:
                        try:
                            port = int(addr.rsplit(':', 1)[-1])
                        except Exception:
                            continue
                        results.append(PortBinding(port=port, family='IPv4', laddr=addr, pid=pid, process_name=command, state="LISTEN" if "LISTEN" in line else None))
            except Exception:
                pass
        else:
            # fallback: find pids then find their ports
            pids = self.find_pids_by_name(name, exact)
            for pid in pids:
                # try lsof -p <pid> -i
                if check_dependency("lsof"):
                    proc = subprocess.run(["lsof", "-a", "-p", str(pid), "-i", "-P", "-n"], capture_output=True, text=True)
                    out = proc.stdout or ""
                    for line in out.splitlines():
                        if "LISTEN" not in line and "TCP" not in line and "UDP" not in line:
                            continue
                        parts = re.split(r'\s+', line)
                        if len(parts) >= 9:
                            addr = parts[8]
                            try:
                                port = int(addr.rsplit(':', 1)[-1])
                            except Exception:
                                continue
                            results.append(PortBinding(port=port, family='IPv4', laddr=addr, pid=pid, process_name=parts[0], state="LISTEN"))
        return sorted(results, key=lambda b: (b.pid or 0, b.port))

    def kill_pid(self, pid: int, graceful_timeout: float = 3.0, force: bool = False, dry_run: bool = False) -> Tuple[bool, str]:
        if dry_run:
            return True, "Dry-run: would attempt terminate"
        try:
            if self.system == "Windows":
                # taskkill without /F is "gentle", with /F is forced
                try:
                    proc = subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True, text=True)
                    if proc.returncode == 0:
                        return True, "Terminated (taskkill)"
                except Exception:
                    pass
                if force:
                    try:
                        proc = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True)
                        return (proc.returncode == 0), proc.stdout + proc.stderr
                    except Exception as e:
                        return False, f"Error taskkill: {e}"
                return False, "Still running; taskkill gentle failed"
            else:
                # Unix: try SIGTERM then SIGKILL
                try:
                    os.kill(pid, signal.SIGTERM)
                except PermissionError:
                    return False, "Permission denied"
                except ProcessLookupError:
                    return False, "No such process"
                except Exception as e:
                    return False, f"Error sending SIGTERM: {e}"
                # wait short time
                waited = 0.0
                interval = 0.1
                while waited < graceful_timeout:
                    time.sleep(interval)
                    waited += interval
                    # check if process exists
                    try:
                        os.kill(pid, 0)
                        # still alive
                    except ProcessLookupError:
                        return True, "Terminated gracefully"
                    except PermissionError:
                        return False, "Permission denied"
                if not force:
                    return False, "Still alive after graceful timeout"
                # force kill
                try:
                    os.kill(pid, signal.SIGKILL)
                    return True, "Killed (SIGKILL)"
                except PermissionError:
                    return False, "Permission denied on SIGKILL"
                except ProcessLookupError:
                    return True, "Process disappeared after SIGKILL"
                except Exception as e:
                    return False, f"Error SIGKILL: {e}"
        except Exception as e:
            return False, f"Unexpected error: {e}"

# Factory
def get_inspector() -> BaseInspector:
    if USING_PSUTIL:
        return PsutilInspector()
    else:
        return FallbackInspector()

# CLI and orchestration
def print_table_listen(bindings: List[PortBinding]) -> None:
    if not bindings:
        print(colorize("No listening ports found.", Colors.YELLOW))
        return
    print(colorize(f"{'Port':<8} {'PID':<8} {'Process':<25} {'State':<12} {'Address':<25}", Colors.BOLD))
    print("─" * 80)
    for b in bindings:
        pid = str(b.pid) if b.pid is not None else "-"
        pname = b.process_name or "-"
        state = b.state or "-"
        print(f"{colorize(str(b.port), Colors.CYAN):<8} {pid:<8} {pname:<25} {state:<12} {b.laddr:<25}")

def jsonify_bindings(bindings: List[PortBinding]) -> str:
    return json.dumps([asdict(b) for b in bindings], indent=2)

def confirm_prompt(prompt: str, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    try:
        resp = input(colorize(prompt + " (y/N): ", Colors.MAGENTA))
        return resp.strip().lower() in ("y", "yes")
    except KeyboardInterrupt:
        print(colorize("\nOperation cancelled.", Colors.YELLOW))
        sys.exit(EXIT_GENERAL_ERROR)


def choose_docker_action(assume_yes: bool) -> Optional[str]:
    """Interactive docker action chooser. Returns action or None (cancel)."""
    if assume_yes:
        # safe default when user explicitly asked to skip prompts
        return "stop"
    print(colorize("\nChoose action:\n1) Stop container\n2) Restart container\n3) Remove container\n4) Cancel", Colors.CYAN))
    try:
        resp = input(colorize("Select (1-4): ", Colors.MAGENTA)).strip()
    except KeyboardInterrupt:
        print(colorize("\nOperation cancelled.", Colors.YELLOW))
        return None
    mapping = {"1": "stop", "2": "restart", "3": "rm", "4": None}
    return mapping.get(resp)


def print_table_docker(mappings: List[DockerPortMapping]) -> None:
    if not mappings:
        print(colorize("No Docker-published ports found.", Colors.YELLOW))
        return
    print(colorize(f"{'PORT':<8} {'CONTAINER':<20} {'IMAGE':<25} {'STATUS':<20}", Colors.BOLD))
    print("─" * 80)
    for m in mappings:
        print(f"{colorize(str(m.host_port), Colors.CYAN):<8} {m.container_name:<20} {m.image:<25} {m.status:<20}")


def print_table_list_product(local_bindings: List[PortBinding], docker_maps: List[DockerPortMapping]) -> None:
    """Product-style list output: PORT TYPE OWNER."""
    rows: Dict[int, Dict[str, Any]] = {}
    for b in local_bindings:
        rows.setdefault(b.port, {})
        rows[b.port]["local"] = b
    for d in docker_maps:
        rows.setdefault(d.host_port, {})
        rows[d.host_port]["docker"] = d

    if not rows:
        print(colorize("No active ports found.", Colors.YELLOW))
        return
    print(colorize(f"{'PORT':<8} {'TYPE':<10} {'OWNER':<25}", Colors.BOLD))
    print("─" * 55)
    for port in sorted(rows.keys()):
        if "docker" in rows[port] and "local" in rows[port]:
            owner = (rows[port]["docker"].container_name)
            print(f"{colorize(str(port), Colors.CYAN):<8} {'conflict':<10} {owner:<25}")
        elif "docker" in rows[port]:
            owner = rows[port]["docker"].container_name
            print(f"{colorize(str(port), Colors.CYAN):<8} {'docker':<10} {owner:<25}")
        else:
            b = rows[port]["local"]
            owner = b.process_name or "-"
            print(f"{colorize(str(port), Colors.CYAN):<8} {'local':<10} {owner:<25}")


def jsonify_docker(mappings: List[DockerPortMapping]) -> str:
    return json.dumps([asdict(m) for m in mappings], indent=2)


def handle_product_command(args: argparse.Namespace, inspector: BaseInspector) -> int:
    """Implements PRODUCT.md `kport <command>` interface."""
    debug = bool(getattr(args, "debug", False))

    if args.command == "docker":
        maps = list_docker_mappings(debug=debug)
        if args.json:
            print(jsonify_docker(maps))
        else:
            print_table_docker(maps)
        return EXIT_OK

    if args.command == "list":
        local = inspector.list_listening()
        docker_maps = list_docker_mappings(debug=debug)
        if args.json:
            # Provide both sources; consumer can merge.
            print(json.dumps({"local": [asdict(b) for b in local], "docker": [asdict(m) for m in docker_maps]}, indent=2))
        else:
            print_table_list_product(local, docker_maps)
        return EXIT_OK

    if args.command == "inspect":
        validate_port(args.port)
        local_bindings = [b for b in inspector.list_listening() if b.port == args.port]
        docker_hits = docker_mappings_for_host_port(args.port, debug=debug)
        pids = inspector.find_pids_on_port(args.port)

        if docker_hits:
            m = docker_hits[0]
            payload = {
                "port": args.port,
                "type": "docker",
                "container": m.container_name,
                "image": m.image,
                "host_port": m.host_port,
                "container_port": m.container_port,
                "status": m.status,
            }
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print(colorize(f"Port: {args.port}", Colors.CYAN + Colors.BOLD))
                print("Type: Docker Container")
                print(f"Container: {m.container_name}")
                print(f"Image: {m.image}")
                print(f"Host Port: {m.host_port}")
                print(f"Container Port: {m.container_port}")
                print(f"Status: {m.status}")
            return EXIT_PORT_DOCKER

        if not pids and not local_bindings:
            if args.json:
                print(json.dumps({"port": args.port, "type": "free"}, indent=2))
            else:
                print(colorize(f"Port {args.port} is free", Colors.GREEN))
            return EXIT_PORT_FREE

        if not pids and local_bindings:
            # Port is listening, but OS did not provide PID (often needs elevated privileges)
            msg = "Port is in use, but the owning PID is not visible (try running with sudo/admin)."
            if args.json:
                print(json.dumps({"port": args.port, "type": "local-unknown", "message": msg, "bindings": [asdict(b) for b in local_bindings]}, indent=2))
            else:
                print(colorize(f"Port: {args.port}", Colors.CYAN + Colors.BOLD))
                print("Type: Local Process")
                print(colorize(msg, Colors.YELLOW))
            return EXIT_OK

        # local process
        info_list = []
        for pid in pids:
            info = inspector.get_process_info(pid)
            info_list.append({"pid": pid, "process": asdict(info) if info else None})
        if args.json:
            print(json.dumps({"port": args.port, "type": "local", "pids": info_list}, indent=2))
        else:
            print(colorize(f"Port: {args.port}", Colors.CYAN + Colors.BOLD))
            print("Type: Local Process")
            for entry in info_list:
                pid = entry["pid"]
                proc = entry["process"]
                if proc:
                    print(f"PID: {pid}")
                    print(f"Process: {proc.get('name')}")
                    if proc.get("cmdline"):
                        print(f"Command: {' '.join(proc['cmdline'])}")
                else:
                    print(f"PID: {pid} (info unavailable)")
        return EXIT_OK

    if args.command == "explain":
        validate_port(args.port)
        local_bindings = [b for b in inspector.list_listening() if b.port == args.port]
        docker_hits = docker_mappings_for_host_port(args.port, debug=debug)
        if docker_hits:
            m = docker_hits[0]
            if args.json:
                print(
                    json.dumps(
                        {
                            "port": args.port,
                            "blocked": True,
                            "because": [
                                f"It is mapped to Docker container '{m.container_name}'",
                                f"Docker maps host port {m.host_port} → container port {m.container_port}",
                                "The process runs inside an isolated network namespace",
                            ],
                        },
                        indent=2,
                    )
                )
            else:
                print(colorize(f"Port {args.port} is unavailable because:", Colors.YELLOW + Colors.BOLD))
                print(f"- It is mapped to Docker container \"{m.container_name}\"")
                print(f"- Docker maps host port {m.host_port} → container port {m.container_port}")
                print("- The process runs inside an isolated network namespace")
            return EXIT_PORT_DOCKER

        pids = inspector.find_pids_on_port(args.port)
        if not pids and not local_bindings:
            if args.json:
                print(json.dumps({"port": args.port, "blocked": False}, indent=2))
            else:
                print(colorize(f"Port {args.port} is free", Colors.GREEN))
            return EXIT_PORT_FREE

        if not pids and local_bindings:
            if args.json:
                print(json.dumps({"port": args.port, "blocked": True, "type": "local-unknown", "message": "Owning PID not visible (try sudo/admin)", "bindings": [asdict(b) for b in local_bindings]}, indent=2))
            else:
                print(colorize(f"Port {args.port} is unavailable because:", Colors.YELLOW + Colors.BOLD))
                print("- A local process is listening, but the owning PID is not visible")
                print("- This is commonly due to missing privileges; try running with sudo")
            return EXIT_OK

        # local process explanation
        infos = []
        for pid in pids:
            info = inspector.get_process_info(pid)
            infos.append({"pid": pid, "process": asdict(info) if info else None})
        if args.json:
            print(json.dumps({"port": args.port, "blocked": True, "type": "local", "pids": infos}, indent=2))
        else:
            print(colorize(f"Port {args.port} is unavailable because:", Colors.YELLOW + Colors.BOLD))
            for entry in infos:
                proc = entry["process"]
                if proc:
                    print(f"- PID {entry['pid']} ({proc.get('name')}) is listening")
                else:
                    print(f"- PID {entry['pid']} is listening")
        return EXIT_OK

    if args.command == "kill":
        validate_port(args.port)
        debug = bool(getattr(args, "debug", False))
        local_bindings = [b for b in inspector.list_listening() if b.port == args.port]
        docker_hits = docker_mappings_for_host_port(args.port, debug=debug)
        if docker_hits:
            m = docker_hits[0]
            action = getattr(args, "docker_action", None)
            if not action and not args.json:
                print(colorize(f"Port {args.port} belongs to Docker container: {m.container_name}", Colors.YELLOW + Colors.BOLD))
                action = choose_docker_action(assume_yes=args.yes)
            if not action:
                if args.json:
                    print(
                        json.dumps(
                            {
                                "port": args.port,
                                "type": "docker",
                                "container": m.container_name,
                                "container_id": m.container_id,
                                "available_actions": ["stop", "restart", "rm"],
                                "performed": None,
                                "message": "No action selected",
                            },
                            indent=2,
                        )
                    )
                else:
                    print(colorize("Operation cancelled.", Colors.YELLOW))
                return EXIT_GENERAL_ERROR

            if args.json and not args.yes and not args.dry_run:
                print(
                    json.dumps(
                        {
                            "port": args.port,
                            "type": "docker",
                            "container": m.container_name,
                            "container_id": m.container_id,
                            "requested_action": action,
                            "performed": False,
                            "message": "Refusing to act without --yes in JSON mode",
                        },
                        indent=2,
                    )
                )
                return EXIT_GENERAL_ERROR

            ok, msg = docker_action_on_container(m.container_id, action=action, dry_run=args.dry_run, debug=debug)
            if args.json:
                print(
                    json.dumps(
                        {
                            "port": args.port,
                            "type": "docker",
                            "container": m.container_name,
                            "container_id": m.container_id,
                            "action": action,
                            "ok": ok,
                            "message": msg,
                        },
                        indent=2,
                    )
                )
            else:
                if ok:
                    print(colorize(f"✓ {msg}", Colors.GREEN))
                else:
                    print(colorize(f"✗ {msg}", Colors.RED))
            return EXIT_OK if ok else EXIT_GENERAL_ERROR

        # local process kill
        pids = inspector.find_pids_on_port(args.port)
        if not pids and not local_bindings:
            if args.json:
                print(json.dumps({"port": args.port, "killed": [], "failed": [], "message": "Port free"}, indent=2))
            else:
                print(colorize(f"Port {args.port} is free", Colors.GREEN))
            return EXIT_PORT_FREE

        if not pids and local_bindings:
            msg = "Port is in use but PID is not visible; cannot kill safely without PID. Try sudo/admin."
            if args.json:
                print(json.dumps({"port": args.port, "ok": False, "message": msg, "bindings": [asdict(b) for b in local_bindings]}, indent=2))
            else:
                print(colorize(msg, Colors.RED))
            return EXIT_PERMISSION

        if not args.json:
            print(colorize("Action plan:\n1. Send SIGTERM\n2. Wait\n3. Escalate if needed", Colors.CYAN))
            if not confirm_prompt("Proceed?", assume_yes=args.yes):
                print(colorize("Operation cancelled.", Colors.YELLOW))
                return EXIT_GENERAL_ERROR

        out_killed = []
        out_failed = []
        for pid in pids:
            ok, msg = inspector.kill_pid(pid, graceful_timeout=args.graceful_timeout, force=args.force, dry_run=args.dry_run)
            if ok:
                out_killed.append({"pid": pid, "msg": msg})
            else:
                out_failed.append({"pid": pid, "msg": msg})
        if args.json:
            print(json.dumps({"port": args.port, "killed": out_killed, "failed": out_failed}, indent=2))
        else:
            for k in out_killed:
                print(colorize(f"✓ Killed PID {k['pid']} ({k['msg']})", Colors.GREEN))
            for f in out_failed:
                print(colorize(f"✗ Failed PID {f['pid']} ({f['msg']})", Colors.RED))
        return EXIT_OK if not out_failed else EXIT_GENERAL_ERROR

    if args.command == "kill-process":
        pname = args.name
        pids = inspector.find_pids_by_name(pname, exact=args.exact)
        if not pids:
            if args.json:
                print(json.dumps({"name": pname, "pids": []}, indent=2))
            else:
                print(colorize(f"❌ No processes found matching '{pname}'", Colors.RED))
            return EXIT_OK
        if not args.json and not confirm_prompt(f"Proceed to terminate {len(pids)} process(es)?", assume_yes=args.yes):
            print(colorize("Operation cancelled.", Colors.YELLOW))
            return EXIT_GENERAL_ERROR
        killed = []
        failed = []
        for pid in pids:
            ok, msg = inspector.kill_pid(pid, graceful_timeout=args.graceful_timeout, force=args.force, dry_run=args.dry_run)
            if ok:
                killed.append({"pid": pid, "msg": msg})
            else:
                failed.append({"pid": pid, "msg": msg})
        if args.json:
            print(json.dumps({"killed": killed, "failed": failed}, indent=2))
        else:
            for k in killed:
                print(colorize(f"✓ Killed PID {k['pid']} ({k['msg']})", Colors.GREEN))
            for f in failed:
                print(colorize(f"✗ Failed PID {f['pid']} ({f['msg']})", Colors.RED))
        return EXIT_OK if not failed else EXIT_GENERAL_ERROR

    if args.command == "conflicts":
        docker_maps = list_docker_mappings(debug=debug)
        conflicts: List[Dict[str, Any]] = []
        for m in docker_maps:
            pids = inspector.find_pids_on_port(m.host_port)
            # Ignore the common docker-proxy holder; conflict means some *other* local process also binds.
            non_docker_pids = []
            for pid in pids:
                info = inspector.get_process_info(pid)
                pname = (info.name if info else "").lower()
                if "docker-proxy" in pname or pname.startswith("docker"):
                    continue
                non_docker_pids.append({"pid": pid, "process": asdict(info) if info else None})
            if non_docker_pids:
                conflicts.append(
                    {
                        "port": m.host_port,
                        "docker": asdict(m),
                        "local": non_docker_pids,
                    }
                )
        if args.json:
            print(json.dumps(conflicts, indent=2))
        else:
            if not conflicts:
                print(colorize("No port conflicts detected.", Colors.GREEN))
            else:
                print(colorize("WARNING: Port conflict detected", Colors.YELLOW + Colors.BOLD))
                for c in conflicts:
                    print(f"\nPort: {c['port']}")
                    print(f"- Docker container: {c['docker']['container_name']}")
                    for lp in c["local"]:
                        proc = lp.get("process") or {}
                        print(f"- Local process: {proc.get('name') or 'Unknown'}")
        return EXIT_OK

    return EXIT_INVALID_INPUT

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="kport - Cross-platform port inspector and killer (upgraded)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  kport.py -i 8080
  kport.py -im 3000 3001 3002
  kport.py -ir 3000-3010
  kport.py -ip node --exact
  kport.py -k 8080 --yes
  kport.py -kp node --dry-run --json
"""
    )

    # Global options (PRODUCT.md)
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without executing")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--debug", action="store_true", help="Verbose internal logs")
    parser.add_argument("--config", type=str, default=None, help="Path to JSON config file (default: .kport.json or ~/.config/kport/config.json)")

    # Legacy flags (backward compatible)
    parser.add_argument("-i", "--inspect", type=int, metavar="PORT", help="Inspect which process is using the specified port")
    parser.add_argument("-im", "--inspect-multiple", type=int, nargs="+", metavar="PORT", help="Inspect multiple ports")
    parser.add_argument("-ir", "--inspect-range", type=str, metavar="RANGE", help="Inspect port range (e.g., 3000-3010)")
    parser.add_argument("-ip", "--inspect-process", type=str, metavar="NAME", help="Inspect all processes matching the given name")
    parser.add_argument("-k", "--kill", type=int, metavar="PORT", help="Kill the process(es) using the specified port")
    parser.add_argument("-kp", "--kill-process", type=str, metavar="NAME", help="Kill all processes matching the given name")
    parser.add_argument("-ka", "--kill-all", type=int, nargs="+", metavar="PORT", help="Kill processes on multiple ports")
    parser.add_argument("-kr", "--kill-range", type=str, metavar="RANGE", help="Kill processes on port range (e.g., 3000-3010)")
    parser.add_argument("-l", "--list", action="store_true", help="List all listening ports and their processes")
    parser.add_argument("--exact", action="store_true", help="Use exact match for process name lookups")
    parser.add_argument("--force", action="store_true", help="Force kill immediately if needed (after graceful timeout)")
    parser.add_argument("--graceful-timeout", type=float, default=3.0, help="Seconds to wait for graceful termination before forcing (default 3.0)")
    parser.add_argument("-v", "--version", action="version", version="kport 3.1.0")

    # PRODUCT.md subcommands
    sub = parser.add_subparsers(dest="command")
    sp_inspect = sub.add_parser("inspect", help="Inspect a port (docker-aware)")
    sp_inspect.add_argument("port", type=int)
    sp_inspect.add_argument("--json", action="store_true")
    sp_inspect.add_argument("--debug", action="store_true")
    sp_inspect.add_argument("--config", type=str, default=None)

    sp_explain = sub.add_parser("explain", help="Explain why a port is blocked")
    sp_explain.add_argument("port", type=int)
    sp_explain.add_argument("--json", action="store_true")
    sp_explain.add_argument("--debug", action="store_true")
    sp_explain.add_argument("--config", type=str, default=None)

    sp_kill = sub.add_parser("kill", help="Safely free a port (docker-aware)")
    sp_kill.add_argument("port", type=int)
    sp_kill.add_argument("--docker-action", choices=["stop", "restart", "rm"], help="Action when port belongs to Docker")
    sp_kill.add_argument("--json", action="store_true")
    sp_kill.add_argument("--dry-run", action="store_true")
    sp_kill.add_argument("-y", "--yes", action="store_true")
    sp_kill.add_argument("--debug", action="store_true")
    sp_kill.add_argument("--force", action="store_true")
    sp_kill.add_argument("--graceful-timeout", type=float, default=3.0)
    sp_kill.add_argument("--config", type=str, default=None)

    sp_kp = sub.add_parser("kill-process", help="Kill processes by name")
    sp_kp.add_argument("name", type=str)
    sp_kp.add_argument("--exact", action="store_true")
    sp_kp.add_argument("--json", action="store_true")
    sp_kp.add_argument("--dry-run", action="store_true")
    sp_kp.add_argument("-y", "--yes", action="store_true")
    sp_kp.add_argument("--debug", action="store_true")
    sp_kp.add_argument("--force", action="store_true")
    sp_kp.add_argument("--graceful-timeout", type=float, default=3.0)
    sp_kp.add_argument("--config", type=str, default=None)

    sp_list = sub.add_parser("list", help="List active ports (local + docker)")
    sp_list.add_argument("--json", action="store_true")
    sp_list.add_argument("--debug", action="store_true")
    sp_list.add_argument("--config", type=str, default=None)

    sp_docker = sub.add_parser("docker", help="List Docker-published ports")
    sp_docker.add_argument("--json", action="store_true")
    sp_docker.add_argument("--debug", action="store_true")
    sp_docker.add_argument("--config", type=str, default=None)

    sp_conflicts = sub.add_parser("conflicts", help="Detect docker/local port conflicts")
    sp_conflicts.add_argument("--json", action="store_true")
    sp_conflicts.add_argument("--debug", action="store_true")
    sp_conflicts.add_argument("--config", type=str, default=None)

    args = parser.parse_args(argv)

    # Apply config defaults (if any)
    cfg = load_config(getattr(args, "config", None), debug=getattr(args, "debug", False))
    apply_config_defaults(args, cfg)

    inspector = get_inspector()

    # Convenience: if psutil not installed, show helpful hint once
    if not USING_PSUTIL:
        if not args.json:
            print(colorize("Notice: psutil not installed; falling back to system commands. Installing psutil improves reliability.", Colors.YELLOW))

    try:
        # PRODUCT.md command mode
        if getattr(args, "command", None):
            return handle_product_command(args, inspector)

        # No args => show help
        if not any([args.inspect, args.inspect_multiple, args.inspect_range, args.inspect_process, args.kill, args.list, args.kill_process, args.kill_all, args.kill_range]):
            parser.print_help()
            return EXIT_OK

        # List all listening ports
        if args.list:
            bindings = inspector.list_listening()
            if args.json:
                print(jsonify_bindings(bindings))
            else:
                print(colorize("\n📋 Listening ports\n", Colors.CYAN + Colors.BOLD))
                print_table_listen(bindings)

        # Inspect single port (legacy) - Docker-aware fallback
        if args.inspect:
            validate_port(args.inspect)
            local_bindings = [b for b in inspector.list_listening() if b.port == args.inspect]
            docker_hits = docker_mappings_for_host_port(args.inspect, debug=args.debug)
            pids = inspector.find_pids_on_port(args.inspect)
            if not pids:
                if docker_hits:
                    m = docker_hits[0]
                    if args.json:
                        print(
                            json.dumps(
                                {
                                    "port": args.inspect,
                                    "type": "docker",
                                    "container": m.container_name,
                                    "image": m.image,
                                    "host_port": m.host_port,
                                    "container_port": m.container_port,
                                    "status": m.status,
                                },
                                indent=2,
                            )
                        )
                    else:
                        print(colorize(f"\n🐳 Port {args.inspect} is mapped to Docker container: {m.container_name}\n", Colors.GREEN + Colors.BOLD))
                        print(f"Image: {m.image}")
                        print(f"Host Port: {m.host_port} → Container Port: {m.container_port}/{m.proto}")
                        print(f"Status: {m.status}")
                elif local_bindings:
                    msg = "Port is in use, but the owning PID is not visible (try running with sudo/admin)."
                    if args.json:
                        print(json.dumps({"port": args.inspect, "type": "local-unknown", "message": msg, "bindings": [asdict(b) for b in local_bindings]}, indent=2))
                    else:
                        print(colorize("⚠ " + msg, Colors.YELLOW))
                else:
                    msg = f"No processes found using port {args.inspect}"
                    if args.json:
                        print(json.dumps({"port": args.inspect, "pids": []}))
                    else:
                        print(colorize("❌ " + msg, Colors.RED))
            else:
                info_list = []
                for pid in pids:
                    info = inspector.get_process_info(pid)
                    info_list.append({"pid": pid, "process": asdict(info) if info else None})
                if args.json:
                    out: Dict[str, Any] = {"port": args.inspect, "pids": info_list}
                    if docker_hits:
                        out["docker"] = [asdict(m) for m in docker_hits]
                    print(json.dumps(out, indent=2))
                else:
                    print(colorize(f"\n🔍 Port {args.inspect} is used by PID(s): {', '.join(map(str,pids))}\n", Colors.GREEN + Colors.BOLD))
                    if docker_hits:
                        m = docker_hits[0]
                        print(colorize(f"🐳 Docker mapping: {m.container_name} ({m.image}) host {m.host_port} → {m.container_port}/{m.proto}", Colors.CYAN))
                    for entry in info_list:
                        pid = entry["pid"]
                        proc = entry["process"]
                        if proc:
                            print(colorize(f"PID {pid}: {proc['name']} (user={proc.get('user')})", Colors.WHITE))
                            if proc.get('cmdline'):
                                print(f"  cmd: {' '.join(proc['cmdline'])}")
                        else:
                            print(colorize(f"PID {pid}: info unavailable", Colors.YELLOW))

        # Inspect multiple ports
        if args.inspect_multiple:
            ports = args.inspect_multiple
            results = []
            for port in ports:
                validate_port(port)
                pids = inspector.find_pids_on_port(port)
                for pid in pids:
                    proc = inspector.get_process_info(pid)
                    results.append({"port": port, "pid": pid, "process": asdict(proc) if proc else None})
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                print(colorize(f"\n🔍 Inspecting {len(ports)} port(s)...\n", Colors.CYAN + Colors.BOLD))
                if not results:
                    print(colorize("❌ No processes found on any of the specified ports", Colors.RED))
                else:
                    print(colorize(f"{'Port':<8} {'PID':<8} {'Process':<30}", Colors.BOLD))
                    print("─" * 60)
                    for r in results:
                        pname = r['process']['name'] if r['process'] else "-"
                        print(f"{colorize(str(r['port']), Colors.CYAN):<8} {str(r['pid']):<8} {pname:<30}")
                    print(colorize(f"\n✓ Found processes on {len(results)} items", Colors.GREEN))

        # Inspect range
        if args.inspect_range:
            ports = parse_port_range(args.inspect_range)
            results = []
            for port in ports:
                pids = inspector.find_pids_on_port(port)
                for pid in pids:
                    proc = inspector.get_process_info(pid)
                    results.append({"port": port, "pid": pid, "process": asdict(proc) if proc else None})
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                print(colorize(f"\n🔍 Inspecting port range {args.inspect_range} ({len(ports)} ports)...\n", Colors.CYAN + Colors.BOLD))
                if not results:
                    print(colorize(f"❌ No processes found in port range {args.inspect_range}", Colors.RED))
                else:
                    print(colorize(f"{'Port':<8} {'PID':<8} {'Process':<30}", Colors.BOLD))
                    print("─" * 60)
                    for r in results:
                        pname = r['process']['name'] if r['process'] else "-"
                        print(f"{colorize(str(r['port']), Colors.CYAN):<8} {str(r['pid']):<8} {pname:<30}")
                    print(colorize(f"\n✓ Found processes on {len(results)} entries", Colors.GREEN))

        # Inspect by process name
        if args.inspect_process:
            pname = args.inspect_process
            bindings = inspector.find_ports_by_process_name(pname, exact=args.exact)
            if args.json:
                print(jsonify_bindings(bindings))
            else:
                print(colorize(f"\n🔍 Inspecting processes matching '{pname}'\n", Colors.CYAN + Colors.BOLD))
                if not bindings:
                    print(colorize(f"❌ No processes found matching '{pname}'", Colors.RED))
                else:
                    pid_groups: Dict[int, List[PortBinding]] = {}
                    for b in bindings:
                        pid_groups.setdefault(b.pid or 0, []).append(b)
                    print(colorize(f"{'PID':<8} {'Process':<25} {'Port':<8} {'State':<12}", Colors.BOLD))
                    print("─" * 70)
                    for pid, ports in pid_groups.items():
                        proc_name = ports[0].process_name or "-"
                        print(f"{colorize(str(pid), Colors.CYAN):<8} {proc_name:<25} {ports[0].port:<8} {ports[0].state or '-':<12}")
                        for p in ports[1:]:
                            print(f"{'':<8} {'':<25} {p.port:<8} {p.state or '-':<12}")
                    print(colorize(f"\n✓ Total processes found: {len(pid_groups)}", Colors.GREEN))
                    print(colorize(f"✓ Total connections: {len(bindings)}", Colors.GREEN))

        # Kill by process name
        if args.kill_process:
            pname = args.kill_process
            pids = inspector.find_pids_by_name(pname, exact=args.exact)
            if not pids:
                if args.json:
                    print(json.dumps({"name": pname, "pids": []}, indent=2))
                else:
                    print(colorize(f"❌ No processes found matching '{pname}'", Colors.RED))
            else:
                if args.json:
                    # In JSON mode, we won't prompt for confirmation; user should opt --yes if they want auto-approval in scripts.
                    out = []
                    for pid in pids:
                        info = inspector.get_process_info(pid)
                        out.append({"pid": pid, "process": asdict(info) if info else None})
                    print(json.dumps({"name": pname, "pids": out}, indent=2))
                    if not args.yes:
                        print(colorize("Note: JSON output provided. Use --yes to actually perform kills.", Colors.YELLOW))
                    else:
                        # proceed to kill
                        killed = []
                        failed = []
                        for pid in pids:
                            ok, msg = inspector.kill_pid(pid, graceful_timeout=args.graceful_timeout, force=args.force, dry_run=args.dry_run)
                            if ok:
                                killed.append({"pid": pid, "msg": msg})
                            else:
                                failed.append({"pid": pid, "msg": msg})
                        print(json.dumps({"killed": killed, "failed": failed}, indent=2))
                else:
                    print(colorize(f"Found {len(pids)} process(es) matching '{pname}':", Colors.YELLOW))
                    for pid in pids:
                        info = inspector.get_process_info(pid)
                        display = f"PID {pid}: {info.name if info else 'Unknown'}"
                        print(colorize("  " + display, Colors.WHITE))
                    if not confirm_prompt(f"\nAre you sure you want to kill {len(pids)} process(es)?", assume_yes=args.yes):
                        print(colorize("Operation cancelled.", Colors.YELLOW))
                    else:
                        killed_count = 0
                        for pid in pids:
                            ok, msg = inspector.kill_pid(pid, graceful_timeout=args.graceful_timeout, force=args.force, dry_run=args.dry_run)
                            if ok:
                                killed_count += 1
                                print(colorize(f"✓ Killed PID {pid} ({msg})", Colors.GREEN))
                            else:
                                print(colorize(f"✗ Failed to kill PID {pid} ({msg})", Colors.RED))
                        print(colorize(f"\n✓ Successfully killed {killed_count}/{len(pids)} process(es)", Colors.GREEN + Colors.BOLD))

        # Kill single port (legacy) - Docker-aware fallback
        if args.kill:
            validate_port(args.kill)
            local_bindings = [b for b in inspector.list_listening() if b.port == args.kill]
            docker_hits = docker_mappings_for_host_port(args.kill, debug=args.debug)
            pids = inspector.find_pids_on_port(args.kill)
            if not pids:
                if docker_hits:
                    m = docker_hits[0]
                    if args.json and not args.yes and not args.dry_run:
                        print(
                            json.dumps(
                                {
                                    "port": args.kill,
                                    "type": "docker",
                                    "container": m.container_name,
                                    "container_id": m.container_id,
                                    "message": "Refusing to act without --yes in JSON mode",
                                },
                                indent=2,
                            )
                        )
                    else:
                        if not args.json:
                            print(colorize(f"\n🐳 Port {args.kill} belongs to Docker container: {m.container_name}", Colors.YELLOW + Colors.BOLD))
                            action = choose_docker_action(assume_yes=args.yes)
                        else:
                            action = "stop"
                        if action:
                            ok, msg = docker_action_on_container(m.container_id, action=action, dry_run=args.dry_run, debug=args.debug)
                            if args.json:
                                print(json.dumps({"port": args.kill, "type": "docker", "action": action, "ok": ok, "message": msg}, indent=2))
                            else:
                                print(colorize(("✓ " if ok else "✗ ") + msg, Colors.GREEN if ok else Colors.RED))
                elif local_bindings:
                    msg = "Port is in use but PID is not visible; cannot kill safely. Try sudo/admin."
                    if args.json:
                        print(json.dumps({"port": args.kill, "ok": False, "message": msg, "bindings": [asdict(b) for b in local_bindings]}, indent=2))
                    else:
                        print(colorize(msg, Colors.RED))
                else:
                    if args.json:
                        print(json.dumps({"port": args.kill, "killed": [], "failed": []}, indent=2))
                    else:
                        print(colorize(f"❌ No process found using port {args.kill}", Colors.RED))
            else:
                if args.json:
                    out_killed = []
                    out_failed = []
                    for pid in pids:
                        ok, msg = inspector.kill_pid(pid, graceful_timeout=args.graceful_timeout, force=args.force, dry_run=args.dry_run)
                        if ok:
                            out_killed.append({"pid": pid, "msg": msg})
                        else:
                            out_failed.append({"pid": pid, "msg": msg})
                    out: Dict[str, Any] = {"port": args.kill, "killed": out_killed, "failed": out_failed}
                    if docker_hits:
                        out["docker"] = [asdict(m) for m in docker_hits]
                    print(json.dumps(out, indent=2))
                else:
                    print(colorize(f"Found PID(s) {', '.join(map(str,pids))} using port {args.kill}", Colors.YELLOW))
                    if docker_hits:
                        m = docker_hits[0]
                        print(colorize(f"🐳 Docker mapping: {m.container_name} ({m.image}) host {m.host_port} → {m.container_port}/{m.proto}", Colors.CYAN))
                    for pid in pids:
                        info = inspector.get_process_info(pid)
                        if info:
                            print(colorize(f"\nProcess to be terminated: PID {pid} - {info.name}", Colors.YELLOW))
                            if info.cmdline:
                                print("  cmd:", ' '.join(info.cmdline))
                    if not confirm_prompt("\nAre you sure you want to kill this process(es)?", assume_yes=args.yes):
                        print(colorize("Operation cancelled.", Colors.YELLOW))
                    else:
                        killed_count = 0
                        for pid in pids:
                            ok, msg = inspector.kill_pid(pid, graceful_timeout=args.graceful_timeout, force=args.force, dry_run=args.dry_run)
                            if ok:
                                killed_count += 1
                                print(colorize(f"✓ Killed PID {pid} ({msg})", Colors.GREEN))
                            else:
                                print(colorize(f"✗ Failed to kill PID {pid} ({msg})", Colors.RED))
                        print(colorize(f"\n✓ Successfully killed {killed_count}/{len(pids)} process(es)", Colors.GREEN + Colors.BOLD))

        # Kill multiple ports list
        if args.kill_all:
            for port in args.kill_all:
                validate_port(port)
            port_pid_map: Dict[int, List[int]] = {}
            for port in args.kill_all:
                pids = inspector.find_pids_on_port(port)
                if pids:
                    port_pid_map[port] = pids
            if not port_pid_map:
                print(colorize("❌ No processes found on any of the specified ports", Colors.RED))
            else:
                print(colorize("Found processes on the following ports:", Colors.YELLOW))
                for port, pids in port_pid_map.items():
                    names = [inspector.get_process_info(pid).name if inspector.get_process_info(pid) else "?" for pid in pids]
                    print(colorize(f"  Port {port}: PIDs {', '.join(map(str,pids))} ({', '.join(names)})", Colors.WHITE))
                if not confirm_prompt(f"\nAre you sure you want to kill {sum(len(ps) for ps in port_pid_map.values())} process(es)?", assume_yes=args.yes):
                    print(colorize("Operation cancelled.", Colors.YELLOW))
                else:
                    killed_count = 0
                    total = sum(len(ps) for ps in port_pid_map.values())
                    for port, pids in port_pid_map.items():
                        for pid in pids:
                            ok, msg = inspector.kill_pid(pid, graceful_timeout=args.graceful_timeout, force=args.force, dry_run=args.dry_run)
                            if ok:
                                killed_count += 1
                                print(colorize(f"✓ Killed PID {pid} (port {port})", Colors.GREEN))
                            else:
                                print(colorize(f"✗ Failed to kill PID {pid} (port {port}): {msg}", Colors.RED))
                    print(colorize(f"\n✓ Successfully killed {killed_count}/{total} process(es)", Colors.GREEN + Colors.BOLD))

        # Kill range
        if args.kill_range:
            ports = parse_port_range(args.kill_range)
            port_pid_map = {}
            for port in ports:
                pids = inspector.find_pids_on_port(port)
                if pids:
                    port_pid_map[port] = pids
            if not port_pid_map:
                print(colorize(f"❌ No processes found in port range {args.kill_range}", Colors.RED))
            else:
                print(colorize(f"Found processes on {len(port_pid_map)} port(s) in range:", Colors.YELLOW))
                for port, pids in port_pid_map.items():
                    print(colorize(f"  Port {port}: PIDs {', '.join(map(str,pids))}", Colors.WHITE))
                if not confirm_prompt(f"\nAre you sure you want to kill {sum(len(ps) for ps in port_pid_map.values())} process(es)?", assume_yes=args.yes):
                    print(colorize("Operation cancelled.", Colors.YELLOW))
                else:
                    killed_count = 0
                    total = sum(len(ps) for ps in port_pid_map.values())
                    for port, pids in port_pid_map.items():
                        for pid in pids:
                            ok, msg = inspector.kill_pid(pid, graceful_timeout=args.graceful_timeout, force=args.force, dry_run=args.dry_run)
                            if ok:
                                killed_count += 1
                                print(colorize(f"✓ Killed PID {pid} (port {port})", Colors.GREEN))
                            else:
                                print(colorize(f"✗ Failed to kill PID {pid} (port {port}): {msg}", Colors.RED))
                    print(colorize(f"\n✓ Successfully killed {killed_count}/{total} process(es)", Colors.GREEN + Colors.BOLD))

    except PermissionError:
        print(colorize("Permission denied. Try running with elevated privileges (sudo / admin).", Colors.RED), file=sys.stderr)
        return EXIT_PERMISSION
    except KeyboardInterrupt:
        print(colorize("\nOperation cancelled by user.", Colors.YELLOW))
        return EXIT_GENERAL_ERROR
    except Exception as e:
        print(colorize(f"Unexpected error: {e}", Colors.RED), file=sys.stderr)
        return EXIT_GENERAL_ERROR

    return EXIT_OK

if __name__ == "__main__":
    rc = main()
    sys.exit(rc)