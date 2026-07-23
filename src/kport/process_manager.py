"""
Process Manager Detection Module for kport.

Detects if a process (by PID) is managed by systemd, pm2, or supervisor.
Returns structured info to explain why processes may automatically restart if killed.
"""

import os
import re
import shutil
import subprocess
from typing import Dict, Optional, Any


def _get_cgroup_systemd_unit(pid: int) -> Optional[str]:
    """Extract systemd service unit name from /proc/<pid>/cgroup on Linux."""
    cgroup_path = f"/proc/{pid}/cgroup"
    if not os.path.exists(cgroup_path):
        return None
    try:
        with open(cgroup_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # Example lines:
                # 0::/system.slice/nginx.service
                # 1:name=systemd:/system.slice/system-mydaemon.slice/mydaemon.service
                # 0::/user.slice/user-1000.slice/user@1000.service/app.slice/pm2-alien.service
                parts = line.split(":")
                path = parts[-1]
                for segment in path.split("/"):
                    if segment.endswith(".service"):
                        # Skip generic user@1000.service container
                        if segment.startswith("user@"):
                            continue
                        return segment
    except Exception:
        pass
    return None


def _get_proc_environ(pid: int) -> Dict[str, str]:
    """Read environment variables for PID on Linux from /proc/<pid>/environ."""
    env_path = f"/proc/{pid}/environ"
    env_dict = {}
    if not os.path.exists(env_path):
        return env_dict
    try:
        with open(env_path, "rb") as f:
            content = f.read()
        for item in content.split(b"\x00"):
            if b"=" in item:
                k, v = item.split(b"=", 1)
                env_dict[k.decode("utf-8", errors="ignore")] = v.decode(
                    "utf-8", errors="ignore"
                )
    except Exception:
        pass
    return env_dict


def _detect_pm2_app(pid: int, env: Dict[str, str]) -> Optional[str]:
    """Detect if PID is managed by PM2."""
    # 1. Check env vars set by PM2 worker processes
    if "pm_id" in env or "PM2_HOME" in env or "pm2_home" in env:
        name = env.get("name") or env.get("PM2_APP_NAME") or env.get("APP_NAME")
        if name:
            return name
        return f"app#{env.get('pm_id', 'unknown')}"

    # 2. Try pm2 jlist if pm2 binary exists on PATH
    if shutil.which("pm2"):
        try:
            res = subprocess.run(
                ["pm2", "jlist"], capture_output=True, text=True, timeout=3
            )
            if res.returncode == 0 and res.stdout:
                import json

                data = json.loads(res.stdout)
                if isinstance(data, list):
                    for app in data:
                        if isinstance(app, dict):
                            app_pid = app.get("pid")
                            pm2_env = app.get("pm2_env", {})
                            if app_pid == pid:
                                return app.get("name") or f"app#{app.get('pm_id')}"
                            if (
                                isinstance(pm2_env, dict)
                                and pm2_env.get("pm_id") is not None
                            ):
                                if app.get("pid") == pid:
                                    return app.get("name")
        except Exception:
            pass

    return None


def _detect_supervisor_app(pid: int) -> Optional[str]:
    """Detect if PID is managed by supervisord."""
    if shutil.which("supervisorctl"):
        try:
            res = subprocess.run(
                ["supervisorctl", "status"], capture_output=True, text=True, timeout=3
            )
            if res.returncode == 0 and res.stdout:
                for line in res.stdout.splitlines():
                    # Format: myprog:myprog_01  RUNNING  pid 1234, uptime 0:01:00
                    m = re.search(r"^(\S+)\s+\S+\s+pid\s+(\d+)", line.strip())
                    if m and int(m.group(2)) == pid:
                        return m.group(1)
        except Exception:
            pass
    return None


def detect_process_manager(
    pid: int, process_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Detect if PID is managed by a process manager (systemd, pm2, supervisord).
    Returns dict:
      {
        "manager": "systemd" | "pm2" | "supervisor",
        "name": str,
        "managed_by": str,  e.g. "systemd:nginx.service", "pm2:my-app", "supervisor:my-worker"
        "warning": str
      }
    Or None if process is not managed by a known process manager.
    """
    if not pid or pid <= 0:
        return None

    # Check systemd cgroup first
    unit = _get_cgroup_systemd_unit(pid)
    if unit:
        # Check if this systemd unit is actually pm2 service
        if "pm2" in unit.lower():
            env = _get_proc_environ(pid)
            pm2_name = _detect_pm2_app(pid, env)
            if pm2_name:
                return {
                    "manager": "pm2",
                    "name": pm2_name,
                    "managed_by": f"pm2:{pm2_name}",
                    "warning": f"Managed by PM2 '{pm2_name}'. Killing PID triggers auto-restart. Stop via 'pm2 stop {pm2_name}'.",
                }
        return {
            "manager": "systemd",
            "name": unit,
            "managed_by": f"systemd:{unit}",
            "warning": f"Managed by systemd service '{unit}'. Killing PID triggers auto-restart. Stop via 'systemctl stop {unit}'.",
        }

    # Check PM2 environment
    env = _get_proc_environ(pid)
    pm2_name = _detect_pm2_app(pid, env)
    if pm2_name:
        return {
            "manager": "pm2",
            "name": pm2_name,
            "managed_by": f"pm2:{pm2_name}",
            "warning": f"Managed by PM2 '{pm2_name}'. Killing PID triggers auto-restart. Stop via 'pm2 stop {pm2_name}'.",
        }

    # Check supervisord
    sup_name = _detect_supervisor_app(pid)
    if sup_name:
        return {
            "manager": "supervisor",
            "name": sup_name,
            "managed_by": f"supervisor:{sup_name}",
            "warning": f"Managed by supervisord '{sup_name}'. Killing PID triggers auto-restart. Stop via 'supervisorctl stop {sup_name}'.",
        }

    return None
