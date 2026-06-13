"""
Psutil-backed inspector implementation for kport.
Leverages psutil to get robust, cross-platform networking and process information.
"""

import os
import signal
from typing import List, Dict, Optional, Tuple, Any
from .base import BaseInspector, PortBinding, ProcessInfo

import psutil  # Safe to import because this implementation is dynamically loaded only when psutil is active.

class PsutilInspector(BaseInspector):
    def list_listening(self) -> List[PortBinding]:
        bindings: Dict[Tuple[int, str], PortBinding] = {}
        for conn in psutil.net_connections(kind='inet'):
            if not conn.laddr:
                continue
            laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if hasattr(conn.laddr, 'ip') else f"{conn.laddr[0]}:{conn.laddr[1]}"
            port = conn.laddr.port if hasattr(conn.laddr, 'port') else conn.laddr[1]
            family = 'IPv6' if conn.family.name == 'AF_INET6' else 'IPv4'
            state = conn.status
            
            # For listening tables, show LISTEN status bindings
            pid = conn.pid
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

    def find_bindings_on_port(self, port: int) -> List[PortBinding]:
        bindings: List[PortBinding] = []
        for conn in psutil.net_connections(kind='inet'):
            if not conn.laddr:
                continue
            try:
                conn_port = conn.laddr.port if hasattr(conn.laddr, 'port') else conn.laddr[1]
            except Exception:
                continue
            if conn_port != port:
                continue
            laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if hasattr(conn.laddr, 'ip') else f"{conn.laddr[0]}:{conn.laddr[1]}"
            family = 'IPv6' if conn.family.name == 'AF_INET6' else 'IPv4'
            pid = conn.pid
            proc_name = None
            if pid:
                try:
                    proc_name = psutil.Process(pid).name()
                except Exception:
                    proc_name = None
            bindings.append(PortBinding(
                port=conn_port,
                family=family,
                laddr=laddr,
                pid=pid,
                process_name=proc_name,
                state=conn.status,
            ))
        return sorted(bindings, key=lambda b: b.port)

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
                pname = p.info['name'] or ''
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

    def send_signal(self, pid: int, sig: int) -> bool:
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
        try:
            p = psutil.Process(pid)
            # Zombie processes are technically dead and ignore signals; treat them as dead
            return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False
        except Exception:
            try:
                # Fallback to checking via os.kill(pid, 0)
                os.kill(pid, 0)
                return True
            except (ProcessLookupError, PermissionError):
                return False
