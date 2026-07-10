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
import socket
import struct
from typing import List, Dict, Optional, Tuple, Any
from .base import BaseInspector, PortBinding, ProcessInfo

# --- Linux-native /proc parsing helpers ---

def parse_ipv4(hex_str: str) -> str:
    """Parse little-endian hex IPv4 string from /proc/net/tcp."""
    b = bytes.fromhex(hex_str)
    return socket.inet_ntop(socket.AF_INET, b[::-1])

def parse_ipv6(hex_str: str) -> str:
    """Parse hex IPv6 representation from /proc/net/tcp6."""
    b = bytes.fromhex(hex_str)
    unpacked = struct.unpack('<IIII', b)
    packed = struct.pack('>IIII', *unpacked)
    return socket.inet_ntop(socket.AF_INET6, packed)

def _parse_proc_net_file(filename: str, family: str) -> List[Tuple[str, int, int]]:
    """Parse socket information from /proc/net/tcp* or /proc/net/udp*."""
    sockets = []
    if not os.path.exists(filename):
        return sockets
    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
        if len(lines) <= 1:
            return sockets
        for line in lines[1:]:
            parts = line.strip().split()
            if len(parts) < 10:
                continue
            local_addr = parts[1]
            state = parts[3]
            
            if "tcp" in filename and state != "0A":
                continue
                
            inode = int(parts[9])
            if inode == 0:
                continue
                
            try:
                ip_hex, port_hex = local_addr.split(':')
                port = int(port_hex, 16)
                if family == 'IPv4':
                    ip = parse_ipv4(ip_hex)
                else:
                    ip = parse_ipv6(ip_hex)
                sockets.append((ip, port, inode))
            except Exception:
                continue
    except Exception:
        pass
    return sockets

def _get_linux_inode_to_pid_map() -> Dict[int, int]:
    """Map socket inodes to owning process PIDs on Linux."""
    inode_to_pid = {}
    try:
        for pid_str in os.listdir('/proc'):
            if not pid_str.isdigit():
                continue
            pid = int(pid_str)
            fd_dir = f'/proc/{pid}/fd'
            try:
                for fd in os.listdir(fd_dir):
                    try:
                        link = os.readlink(f'{fd_dir}/{fd}')
                        if link.startswith('socket:['):
                            inode = int(link[8:-1])
                            inode_to_pid[inode] = pid
                    except (OSError, ValueError):
                        continue
            except OSError:
                continue
    except Exception:
        pass
    return inode_to_pid

def _get_linux_process_info(pid: int) -> Optional[ProcessInfo]:
    """Retrieve process information natively on Linux from /proc."""
    try:
        stat_info = os.stat(f'/proc/{pid}')
        uid = stat_info.st_uid
        try:
            import pwd
            user = pwd.getpwuid(uid).pw_name
        except Exception:
            user = str(uid)

        try:
            with open(f'/proc/{pid}/comm', 'r', errors='ignore') as f:
                name = f.read().strip()
        except Exception:
            name = ""

        cmdline = None
        try:
            with open(f'/proc/{pid}/cmdline', 'r', errors='ignore') as f:
                content = f.read()
                if content:
                    cmdline = [arg for arg in content.split('\x00') if arg]
        except Exception:
            pass

        if not name and cmdline:
            name = os.path.basename(cmdline[0])

        return ProcessInfo(pid=pid, name=name, cmdline=cmdline, user=user)
    except Exception:
        return None

def _list_listening_linux_native() -> Optional[List[PortBinding]]:
    """Get active listening sockets natively on Linux via /proc/net."""
    if platform.system() != "Linux":
        return None

    inode_to_pid = _get_linux_inode_to_pid_map()

    # C3 fix: build a pid→info map once instead of calling _get_linux_process_info
    # once per socket (which would be 4× redundant for each PID binding on TCP4/6 + UDP4/6).
    unique_pids = {pid for pid in inode_to_pid.values() if pid}
    pid_to_info: Dict[int, Optional[ProcessInfo]] = {
        pid: _get_linux_process_info(pid) for pid in unique_pids
    }

    def _make_binding(ip: str, port: int, inode: int, family: str, state: str) -> PortBinding:
        pid = inode_to_pid.get(inode)
        info = pid_to_info.get(pid) if pid else None
        pname = info.name if info else None
        laddr = f"[{ip}]:{port}" if family == 'IPv6' else f"{ip}:{port}"
        return PortBinding(port=port, family=family, laddr=laddr, pid=pid, process_name=pname, state=state)

    bindings = []
    for ip, port, inode in _parse_proc_net_file('/proc/net/tcp', 'IPv4'):
        bindings.append(_make_binding(ip, port, inode, 'IPv4', 'LISTEN'))
    for ip, port, inode in _parse_proc_net_file('/proc/net/tcp6', 'IPv6'):
        bindings.append(_make_binding(ip, port, inode, 'IPv6', 'LISTEN'))
    # UDP has no state — entries are active bindings, not connections.
    for ip, port, inode in _parse_proc_net_file('/proc/net/udp', 'IPv4'):
        bindings.append(_make_binding(ip, port, inode, 'IPv4', 'UDP'))
    for ip, port, inode in _parse_proc_net_file('/proc/net/udp6', 'IPv6'):
        bindings.append(_make_binding(ip, port, inode, 'IPv6', 'UDP'))

    return bindings


# --- Windows-native ctypes parsing helpers ---

# Only define Windows API structs and ctypes setup if on Windows
if platform.system() == "Windows":
    import ctypes
    from ctypes import wintypes

    AF_INET = 2
    AF_INET6 = 23
    TCP_TABLE_OWNER_PID_ALL = 5
    UDP_TABLE_OWNER_PID = 1

    class MIB_TCPROW_OWNER_PID(ctypes.Structure):
        _fields_ = [
            ("dwState", wintypes.DWORD),
            ("dwLocalAddr", wintypes.DWORD),
            ("dwLocalPort", wintypes.DWORD),
            ("dwRemoteAddr", wintypes.DWORD),
            ("dwRemotePort", wintypes.DWORD),
            ("dwOwningPid", wintypes.DWORD),
        ]

    class MIB_TCP6ROW_OWNER_PID(ctypes.Structure):
        _fields_ = [
            ("ucLocalAddr", ctypes.c_byte * 16),
            ("dwLocalScopeId", wintypes.DWORD),
            ("dwLocalPort", wintypes.DWORD),
            ("ucRemoteAddr", ctypes.c_byte * 16),
            ("dwRemoteScopeId", wintypes.DWORD),
            ("dwRemotePort", wintypes.DWORD),
            ("dwState", wintypes.DWORD),
            ("dwOwningPid", wintypes.DWORD),
        ]

    class MIB_UDPROW_OWNER_PID(ctypes.Structure):
        _fields_ = [
            ("dwLocalAddr", wintypes.DWORD),
            ("dwLocalPort", wintypes.DWORD),
            ("dwOwningPid", wintypes.DWORD),
        ]

    class MIB_UDP6ROW_OWNER_PID(ctypes.Structure):
        _fields_ = [
            ("ucLocalAddr", ctypes.c_byte * 16),
            ("dwLocalScopeId", wintypes.DWORD),
            ("dwLocalPort", wintypes.DWORD),
            ("dwOwningPid", wintypes.DWORD),
        ]

def _get_extended_tcp_table_ipv4() -> List[PortBinding]:
    bindings = []
    if platform.system() != "Windows":
        return bindings
    
    iphlpapi = ctypes.windll.iphlpapi
    size = wintypes.DWORD(0)
    res = iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), True, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
    
    buf = ctypes.create_string_buffer(size.value)
    res = iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), True, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
    if res != 0:
        return []
        
    num_entries = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD)).contents.value
    entry_size = ctypes.sizeof(MIB_TCPROW_OWNER_PID)
    offset = ctypes.sizeof(wintypes.DWORD)
    
    for i in range(num_entries):
        entry_ptr = ctypes.cast(ctypes.byref(buf, offset + i * entry_size), ctypes.POINTER(MIB_TCPROW_OWNER_PID))
        row = entry_ptr.contents
        
        state_map = {
            1: "CLOSED", 2: "LISTEN", 3: "SYN_SENT", 4: "SYN_RECV",
            5: "ESTABLISHED", 6: "FIN_WAIT1", 7: "FIN_WAIT2",
            8: "CLOSE_WAIT", 9: "CLOSING", 10: "LAST_ACK",
            11: "TIME_WAIT", 12: "DELETE_TCB"
        }
        state = state_map.get(row.dwState, f"STATE_{row.dwState}")
        
        if state != "LISTEN":
            continue
            
        ip_bytes = struct.pack('<I', row.dwLocalAddr)
        ip = socket.inet_ntop(socket.AF_INET, ip_bytes)
        port = socket.ntohs(row.dwLocalPort & 0xFFFF)
        pid = int(row.dwOwningPid)
        bindings.append(PortBinding(port=port, family='IPv4', laddr=f"{ip}:{port}", pid=pid, process_name=None, state=state))
        
    return bindings

def _get_extended_tcp_table_ipv6() -> List[PortBinding]:
    bindings = []
    if platform.system() != "Windows":
        return bindings
    
    iphlpapi = ctypes.windll.iphlpapi
    size = wintypes.DWORD(0)
    res = iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), True, AF_INET6, TCP_TABLE_OWNER_PID_ALL, 0)
    
    buf = ctypes.create_string_buffer(size.value)
    res = iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), True, AF_INET6, TCP_TABLE_OWNER_PID_ALL, 0)
    if res != 0:
        return []
        
    num_entries = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD)).contents.value
    entry_size = ctypes.sizeof(MIB_TCP6ROW_OWNER_PID)
    offset = ctypes.sizeof(wintypes.DWORD)
    
    for i in range(num_entries):
        entry_ptr = ctypes.cast(ctypes.byref(buf, offset + i * entry_size), ctypes.POINTER(MIB_TCP6ROW_OWNER_PID))
        row = entry_ptr.contents
        
        state_map = {
            1: "CLOSED", 2: "LISTEN", 3: "SYN_SENT", 4: "SYN_RECV",
            5: "ESTABLISHED", 6: "FIN_WAIT1", 7: "FIN_WAIT2",
            8: "CLOSE_WAIT", 9: "CLOSING", 10: "LAST_ACK",
            11: "TIME_WAIT", 12: "DELETE_TCB"
        }
        state = state_map.get(row.dwState, f"STATE_{row.dwState}")
        
        if state != "LISTEN":
            continue
            
        ip_bytes = bytes(row.ucLocalAddr)
        ip = socket.inet_ntop(socket.AF_INET6, ip_bytes)
        port = socket.ntohs(row.dwLocalPort & 0xFFFF)
        pid = int(row.dwOwningPid)
        bindings.append(PortBinding(port=port, family='IPv6', laddr=f"[{ip}]:{port}", pid=pid, process_name=None, state=state))
        
    return bindings

def _get_extended_udp_table_ipv4() -> List[PortBinding]:
    bindings = []
    if platform.system() != "Windows":
        return bindings
    
    iphlpapi = ctypes.windll.iphlpapi
    size = wintypes.DWORD(0)
    res = iphlpapi.GetExtendedUdpTable(None, ctypes.byref(size), True, AF_INET, UDP_TABLE_OWNER_PID, 0)
    
    buf = ctypes.create_string_buffer(size.value)
    res = iphlpapi.GetExtendedUdpTable(buf, ctypes.byref(size), True, AF_INET, UDP_TABLE_OWNER_PID, 0)
    if res != 0:
        return []
        
    num_entries = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD)).contents.value
    entry_size = ctypes.sizeof(MIB_UDPROW_OWNER_PID)
    offset = ctypes.sizeof(wintypes.DWORD)
    
    for i in range(num_entries):
        entry_ptr = ctypes.cast(ctypes.byref(buf, offset + i * entry_size), ctypes.POINTER(MIB_UDPROW_OWNER_PID))
        row = entry_ptr.contents
        
        ip_bytes = struct.pack('<I', row.dwLocalAddr)
        ip = socket.inet_ntop(socket.AF_INET, ip_bytes)
        port = socket.ntohs(row.dwLocalPort & 0xFFFF)
        pid = int(row.dwOwningPid)
        bindings.append(PortBinding(port=port, family='IPv4', laddr=f"{ip}:{port}", pid=pid, process_name=None, state="UDP"))
        
    return bindings

def _get_extended_udp_table_ipv6() -> List[PortBinding]:
    bindings = []
    if platform.system() != "Windows":
        return bindings
    
    iphlpapi = ctypes.windll.iphlpapi
    size = wintypes.DWORD(0)
    res = iphlpapi.GetExtendedUdpTable(None, ctypes.byref(size), True, AF_INET6, UDP_TABLE_OWNER_PID, 0)
    
    buf = ctypes.create_string_buffer(size.value)
    res = iphlpapi.GetExtendedUdpTable(buf, ctypes.byref(size), True, AF_INET6, UDP_TABLE_OWNER_PID, 0)
    if res != 0:
        return []
        
    num_entries = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD)).contents.value
    entry_size = ctypes.sizeof(MIB_UDP6ROW_OWNER_PID)
    offset = ctypes.sizeof(wintypes.DWORD)
    
    for i in range(num_entries):
        entry_ptr = ctypes.cast(ctypes.byref(buf, offset + i * entry_size), ctypes.POINTER(MIB_UDP6ROW_OWNER_PID))
        row = entry_ptr.contents
        
        ip_bytes = bytes(row.ucLocalAddr)
        ip = socket.inet_ntop(socket.AF_INET6, ip_bytes)
        port = socket.ntohs(row.dwLocalPort & 0xFFFF)
        pid = int(row.dwOwningPid)
        bindings.append(PortBinding(port=port, family='IPv6', laddr=f"[{ip}]:{port}", pid=pid, process_name=None, state="UDP"))
        
    return bindings

def _windows_listening_native() -> List[PortBinding]:
    """Retrieve all Windows listening sockets natively using ctypes."""
    bindings = []
    try:
        bindings.extend(_get_extended_tcp_table_ipv4())
    except Exception:
        pass
    try:
        bindings.extend(_get_extended_tcp_table_ipv6())
    except Exception:
        pass
    try:
        bindings.extend(_get_extended_udp_table_ipv4())
    except Exception:
        pass
    try:
        bindings.extend(_get_extended_udp_table_ipv6())
    except Exception:
        pass
    
    for b in bindings:
        if b.pid:
            info = _get_windows_process_info_native(b.pid)
            if info:
                b.process_name = info.name
    return bindings

def _get_windows_process_info_native(pid: int) -> Optional[ProcessInfo]:
    """Retrieve process name/executable path natively on Windows using ctypes."""
    if platform.system() != "Windows":
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        h_proc = kernel32.OpenProcess(0x1000, False, pid)
        if not h_proc:
            return None
        try:
            size = wintypes.DWORD(260)
            buf = ctypes.create_unicode_buffer(260)
            if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                exe_path = buf.value
                name = os.path.basename(exe_path)
                return ProcessInfo(pid=pid, name=name, exe=exe_path)
        finally:
            kernel32.CloseHandle(h_proc)
    except Exception:
        pass
    return None


_SUBPROCESS_TIMEOUT = 15


class FallbackInspector(BaseInspector):
    def __init__(self):
        self.system = platform.system()
        self._ps_exe = None
        self._process_info_cache: Dict[int, Optional[ProcessInfo]] = {}
        self._tasklist_cache: Optional[Dict[int, str]] = None
        if self.system == "Windows":
            self._ps_exe = shutil.which("powershell") or shutil.which("pwsh")

    def _clear_cache(self) -> None:
        """C1: Clear all per-PID caches before each public query.

        In long-running modes (Watch Mode, MCP server) the OS reuses PIDs.
        Stale cache entries would return the old dead process name for a new
        process that happened to acquire the same PID. Clearing on every
        public entry point ensures each query sees a fresh snapshot.
        """
        self._process_info_cache.clear()
        self._tasklist_cache = None  # Force tasklist re-query on Windows

    def _powershell(self) -> Optional[str]:
        return self._ps_exe

    def _run_subprocess(self, cmd: List[str], timeout: int = _SUBPROCESS_TIMEOUT) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def _run_powershell_json(self, script: str, timeout: int = _SUBPROCESS_TIMEOUT) -> Optional[Any]:
        ps = self._powershell()
        if not ps:
            return None
        try:
            cmd = [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script]
            proc = self._run_subprocess(cmd, timeout=timeout)
            if proc.returncode != 0:
                return None
            out = (proc.stdout or "").strip()
            if not out:
                return None
            return json.loads(out)
        except (subprocess.TimeoutExpired, Exception):
            return None

    def _parse_tasklist_csv(self, out: str) -> Dict[int, str]:
        names: Dict[int, str] = {}
        for line in out.splitlines():
            parts = [p.strip().strip('"') for p in re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', line)]
            if len(parts) >= 2:
                try:
                    names[int(parts[1])] = parts[0]
                except ValueError:
                    continue
        return names

    def _ensure_tasklist_cache(self) -> Dict[int, str]:
        if self._tasklist_cache is not None:
            return self._tasklist_cache
        self._tasklist_cache = {}
        try:
            proc = self._run_subprocess(["tasklist", "/FO", "CSV", "/NH"])
            self._tasklist_cache = self._parse_tasklist_csv(proc.stdout or "")
        except Exception:
            pass
        return self._tasklist_cache

    def _process_name_for_pid(self, pid: int) -> Optional[str]:
        return self._ensure_tasklist_cache().get(pid)

    def _binding_from_windows_conn(self, item: Dict[str, Any]) -> Optional[PortBinding]:
        try:
            port = int(item.get("LocalPort"))
        except Exception:
            return None
        pid = None
        try:
            pid = int(item.get("OwningProcess"))
        except Exception:
            pid = None
        laddr = f"{item.get('LocalAddress')}:{port}"
        state = item.get("State")
        pname = self._process_name_for_pid(pid) if pid else None
        return PortBinding(port=port, family='IPv4', laddr=laddr, pid=pid, process_name=pname, state=state)

    def list_listening(self) -> List[PortBinding]:
        self._clear_cache()  # C1: always fresh snapshot
        if self.system == "Windows":
            bindings: List[PortBinding] = []
            try:
                bindings = _windows_listening_native()
            except Exception:
                pass
            if not bindings:
                bindings = self._windows_listening()
            return bindings
        else:
            bindings = []
            try:
                bindings = _list_listening_linux_native() or []
            except Exception:
                bindings = []
            if not bindings:
                bindings = self._unix_listening()
            return bindings

    def find_bindings_on_port(self, port: int) -> List[PortBinding]:
        self._clear_cache()  # C1
        if self.system == "Windows":
            try:
                bindings = _windows_listening_native()
                if bindings:
                    return [b for b in bindings if b.port == port]
            except Exception:
                pass
            return self._windows_bindings_on_port(port)
        else:
            try:
                bindings = _list_listening_linux_native() or []
                if bindings:
                    return [b for b in bindings if b.port == port]
            except Exception:
                pass
            return [b for b in self._unix_listening() if b.port == port]

    def _windows_bindings_on_port(self, port: int) -> List[PortBinding]:
        bindings: List[PortBinding] = []
        self._ensure_tasklist_cache()
        ps_data = self._run_powershell_json(
            f"Get-NetTCPConnection -State Listen -LocalPort {port} | "
            "Select-Object LocalAddress,LocalPort,OwningProcess,State | ConvertTo-Json -Depth 3"
        )
        if ps_data is not None:
            items = ps_data if isinstance(ps_data, list) else [ps_data]
            for it in items:
                binding = self._binding_from_windows_conn(it)
                if binding:
                    bindings.append(binding)
            return sorted(bindings, key=lambda b: b.port)

        if not shutil.which("netstat"):
            return bindings
        try:
            proc = self._run_subprocess(["netstat", "-ano"])
            for line in proc.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = re.split(r'\s+', line)
                if len(parts) >= 5 and parts[0].upper() in ("TCP", "UDP"):
                    local_addr = parts[1]
                    if ':' not in local_addr:
                        continue
                    port_str = local_addr.rsplit(':', 1)[-1]
                    try:
                        if int(port_str) != port:
                            continue
                    except ValueError:
                        continue
                    state = parts[3] if len(parts) >= 5 else ""
                    pid = None
                    try:
                        pid = int(parts[-1])
                    except Exception:
                        pid = None
                    pname = self._process_name_for_pid(pid) if pid else None
                    bindings.append(PortBinding(
                        port=port, family='IPv4', laddr=local_addr, pid=pid,
                        process_name=pname, state=state,
                    ))
        except Exception:
            pass
        return sorted(bindings, key=lambda b: b.port)

    def _windows_listening(self) -> List[PortBinding]:
        bindings: List[PortBinding] = []
        self._ensure_tasklist_cache()
        ps_data = self._run_powershell_json(
            "Get-NetTCPConnection -State Listen | "
            "Select-Object LocalAddress,LocalPort,OwningProcess,State | ConvertTo-Json -Depth 3"
        )
        if ps_data is not None:
            items = ps_data if isinstance(ps_data, list) else [ps_data]
            for it in items:
                binding = self._binding_from_windows_conn(it)
                if binding:
                    bindings.append(binding)
            return sorted(bindings, key=lambda b: b.port)

        if not shutil.which("netstat"):
            return bindings
        try:
            proc = self._run_subprocess(["netstat", "-ano"])
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
                        pname = self._process_name_for_pid(pid) if pid else None
                        bindings.append(PortBinding(
                            port=port, family='IPv4', laddr=local_addr, pid=pid,
                            process_name=pname, state=state,
                        ))
        except Exception:
            pass
        return sorted(bindings, key=lambda b: b.port)

    def _unix_listening(self) -> List[PortBinding]:
        bindings: List[PortBinding] = []
        if shutil.which("lsof"):
            try:
                proc = self._run_subprocess(["lsof", "-i", "-P", "-n"])
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
                    proc = self._run_subprocess(["ss", "-ltnp"])
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
        self._clear_cache()  # C1
        if self.system == "Windows":
            try:
                bindings = _windows_listening_native()
                if bindings:
                    return sorted({b.pid for b in bindings if b.port == port and b.pid})
            except Exception:
                pass
            return self._windows_pids_on_port(port)
        else:
            try:
                bindings = _list_listening_linux_native() or []
                if bindings:
                    return sorted({b.pid for b in bindings if b.port == port and b.pid})
            except Exception:
                pass
            return self._unix_pids_on_port(port)

    def _windows_pids_on_port(self, port: int) -> List[int]:
        pids = set()
        ps_data = self._run_powershell_json(
            f"Get-NetTCPConnection -State Listen -LocalPort {port} | "
            "Select-Object -ExpandProperty OwningProcess | ConvertTo-Json -Depth 2"
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
        proc = self._run_subprocess(["netstat", "-ano"])
        # R3: check returncode before parsing output
        if proc.returncode != 0:
            return []
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
            proc = self._run_subprocess(["lsof", "-t", "-i", f":{port}"])
            for line in proc.stdout.splitlines():
                try:
                    pids.add(int(line.strip()))
                except Exception:
                    continue
        else:
            if shutil.which("ss"):
                proc = self._run_subprocess(["ss", "-ltnp"])
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
        if pid in self._process_info_cache:
            return self._process_info_cache[pid]
        info = self._fetch_process_info(pid)
        self._process_info_cache[pid] = info
        return info

    def _fetch_process_info(self, pid: int) -> Optional[ProcessInfo]:
        try:
            if self.system == "Windows":
                try:
                    info = _get_windows_process_info_native(pid)
                    if info:
                        return info
                except Exception:
                    pass
                name = self._process_name_for_pid(pid)
                if name:
                    return ProcessInfo(pid=pid, name=name)

                proc = self._run_subprocess(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    timeout=5,
                )
                out = proc.stdout.strip()
                if out and "No tasks are running" not in out:
                    parts = [p.strip().strip('"') for p in re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', out)]
                    if parts:
                        return ProcessInfo(pid=pid, name=parts[0])
            else:
                try:
                    info = _get_linux_process_info(pid)
                    if info:
                        return info
                except Exception:
                    pass
                proc = self._run_subprocess(["ps", "-p", str(pid), "-o", "pid=,comm=,user=,args="])
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
        self._clear_cache()  # C1
        self_pid = os.getpid()  # R5: never return kport's own PID
        if self.system == "Windows":
            proc = self._run_subprocess(["tasklist", "/FO", "CSV", "/NH"])
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
                    if pid == self_pid:
                        continue  # R5: skip self
                    match = (pname.lower() == name_lower) if exact else (name_lower in pname.lower())
                    if match:
                        pids.append(pid)
            return sorted(pids)
        else:
            if shutil.which("pgrep"):
                # pgrep -f matches the full command line including kport itself.
                # Filter self-PID from results (R5).
                args = ["pgrep", "-f", name] if not exact else ["pgrep", "-x", name]
                proc = self._run_subprocess(args)
                out = proc.stdout or ""
                pids = []
                for line in out.splitlines():
                    try:
                        pid = int(line.strip())
                        if pid != self_pid:
                            pids.append(pid)
                    except Exception:
                        continue
                return sorted(pids)
            else:
                proc = self._run_subprocess(["ps", "-ef"])
                out = proc.stdout or ""
                pids = []
                for line in out.splitlines():
                    if name in line if exact else name.lower() in line.lower():
                        parts = re.split(r'\s+', line.strip())
                        if len(parts) >= 2:
                            try:
                                pid = int(parts[1])
                                if pid != self_pid:
                                    pids.append(pid)
                            except Exception:
                                continue
                return sorted(set(pids))

    def find_ports_by_process_name(self, name: str, exact: bool = False) -> List[PortBinding]:
        self._clear_cache()  # C1
        results: List[PortBinding] = []
        name_lower = name.lower()

        if shutil.which("lsof"):
            try:
                proc = self._run_subprocess(["lsof", "-i", "-P", "-n"])
                out = proc.stdout or ""
                for line in out.splitlines():
                    # C2 fix: correct filter logic.
                    # In fuzzy mode: keep lines where name appears anywhere.
                    # In exact mode: keep lines where the command field matches exactly.
                    parts = re.split(r'\s+', line)
                    if len(parts) < 9:
                        continue
                    command = parts[0]
                    if exact:
                        if command.lower() != name_lower:
                            continue
                    else:
                        if name_lower not in line.lower():
                            continue
                    pid_s = parts[1]
                    try:
                        pid = int(pid_s)
                    except Exception:
                        pid = None
                    addr = parts[8]
                    if ':' not in addr:
                        continue
                    try:
                        port = int(addr.rsplit(':', 1)[-1])
                    except Exception:
                        continue
                    results.append(PortBinding(
                        port=port, family='IPv4', laddr=addr, pid=pid,
                        process_name=command,
                        state="LISTEN" if "LISTEN" in line else None,
                    ))
            except Exception:
                pass
        else:
            # C7 fix: removed dead inner `if shutil.which("lsof")` that could never
            # execute (we're already in the `else` branch meaning lsof is absent).
            # Fall back to pids-first, then use /proc or ps to find their sockets.
            pids = self.find_pids_by_name(name, exact)
            for pid in pids:
                # Try native /proc on Linux
                try:
                    bindings = _list_listening_linux_native() or []
                    for b in bindings:
                        if b.pid == pid:
                            results.append(b)
                except Exception:
                    pass
        return sorted(results, key=lambda b: (b.pid or 0, b.port))

    def send_signal(self, pid: int, sig: int) -> bool:
        if self.system == "Windows":
            import signal as signal_module
            if sig == signal_module.SIGTERM:
                proc = self._run_subprocess(["taskkill", "/PID", str(pid)])
                if proc.returncode == 0:
                    return True
                raise RuntimeError(f"taskkill gentle failed: {proc.stderr.strip()}")
            else:
                proc = self._run_subprocess(["taskkill", "/PID", str(pid), "/F"])
                if proc.returncode == 0:
                    return True
                raise RuntimeError(f"taskkill forced failed: {proc.stderr.strip()}")
        else:
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
            proc = self._run_subprocess(["tasklist", "/FI", f"PID eq {pid}", "/NH"], timeout=5)
            return f" {pid} " in f" {proc.stdout} " or f"\"{pid}\"" in proc.stdout
        else:
            try:
                os.kill(pid, 0)
                return True
            except (ProcessLookupError, PermissionError) as e:
                return isinstance(e, PermissionError)
