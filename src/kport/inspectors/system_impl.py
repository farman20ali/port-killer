"""
OS system commands fallback inspector implementation for kport.
Leverages platform binaries (lsof, ss, netstat, tasklist, powershell) to inspect states.
"""

import platform
import subprocess
import shutil
import re
import json
import os
import signal
from typing import List, Dict, Optional, Tuple, Any
from .base import BaseInspector, PortBinding, ProcessInfo

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

        if not shutil.which("netstat"):
            return bindings
        try:
            proc = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            lines = proc.stdout.splitlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                parts = re.split(r'\s+', line)
                if len(parts) >= 5 and parts[0].upper() in ("TCP", "UDP"):
                    local_addr = parts[1]
                    state = parts[3] if len(parts) >= 5 else ""
                    pid = None
                    try:
                        pid = int(parts[-1])
                    except Exception:
                        pid = None
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
        if shutil.which("lsof"):
            try:
                proc = subprocess.run(["lsof", "-i", "-P", "-n"], capture_output=True, text=True)
                lines = proc.stdout.splitlines()
                for line in lines:
                    if "LISTEN" not in line and "LISTENING" not in line:
                        continue
                    parts = re.split(r'\s+', line)
                    if len(parts) < 9:
                        continue
                    command = parts[0]
                    pid = None
                    try:
                        pid = int(parts[1])
                    except Exception:
                        pid = None
                    name_field = parts[8]
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
            if shutil.which("ss"):
                try:
                    proc = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True)
                    lines = proc.stdout.splitlines()
                    for line in lines:
                        if "LISTEN" not in line:
                            continue
                        parts = re.split(r'\s+', line)
                        for token in parts:
                            if ':' in token and re.search(r':\d+$', token):
                                try:
                                    port = int(token.rsplit(':', 1)[-1])
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
        if not shutil.which("netstat"):
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
        if shutil.which("lsof"):
            proc = subprocess.run(["lsof", "-t", "-i", f":{port}"], capture_output=True, text=True)
            for line in proc.stdout.splitlines():
                try:
                    pids.add(int(line.strip()))
                except Exception:
                    continue
        else:
            if shutil.which("ss"):
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
                ps_data = self._run_powershell_json(
                    f"Get-Process -Id {pid} | Select-Object Id,ProcessName,Path | ConvertTo-Json -Depth 3"
                )
                if isinstance(ps_data, dict):
                    name = ps_data.get("ProcessName")
                    exe = ps_data.get("Path")
                    if name:
                        return ProcessInfo(pid=pid, name=str(name), exe=str(exe) if exe else None)

                # Fallback: tasklist
                proc = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True)
                out = proc.stdout.strip()
                if not out:
                    return None
                parts = [p.strip().strip('"') for p in re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', out)]
                if parts:
                    name = parts[0]
                    return ProcessInfo(pid=pid, name=name)
            else:
                # Unix
                proc = subprocess.run(["ps", "-p", str(pid), "-o", "pid=,comm=,user=,args="], capture_output=True, text=True)
                out = proc.stdout.strip()
                if not out:
                    return None
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
            if shutil.which("pgrep"):
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
        if shutil.which("lsof"):
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
                    if ':' in addr:
                        try:
                            port = int(addr.rsplit(':', 1)[-1])
                        except Exception:
                            continue
                        results.append(PortBinding(port=port, family='IPv4', laddr=addr, pid=pid, process_name=command, state="LISTEN" if "LISTEN" in line else None))
            except Exception:
                pass
        else:
            pids = self.find_pids_by_name(name, exact)
            for pid in pids:
                if shutil.which("lsof"):
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

    def send_signal(self, pid: int, sig: int) -> bool:
        if self.system == "Windows":
            # For Windows taskkill fallback
            import signal as signal_module
            if sig == signal_module.SIGTERM:
                proc = subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True, text=True)
                if proc.returncode == 0:
                    return True
                raise RuntimeError(f"taskkill gentle failed: {proc.stderr.strip()}")
            else:
                proc = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True)
                if proc.returncode == 0:
                    return True
                raise RuntimeError(f"taskkill forced failed: {proc.stderr.strip()}")
        else:
            # Unix-like signal sending
            try:
                os.kill(pid, sig)
                return True
            except ProcessLookupError:
                raise ProcessLookupError()
            except PermissionError:
                raise PermissionError()
            except Exception as e:
                raise RuntimeError(str(e))

    def is_process_alive(self, pid: int) -> bool:
        if self.system == "Windows":
            # Verify via tasklist matching
            proc = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
            return f" {pid} " in f" {proc.stdout} " or f"\"{pid}\"" in proc.stdout
        else:
            try:
                os.kill(pid, 0)
                return True
            except (ProcessLookupError, PermissionError) as e:
                # PermissionError means process exists but we lack authorization
                return isinstance(e, PermissionError)
