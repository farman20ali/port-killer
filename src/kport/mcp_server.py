"""
Model Context Protocol (MCP) server implementation for kport.
Implements standard stdio-based tool calls with zero dependencies.
Incorporates a strict safety shield to prevent AI agents from killing critical system ports.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Any

from . import __version__
from .constants import (
    PROTECTED_PORTS,
    PROTECTED_PROCESS_NAMES,
)
from .docker_engine import (
    docker_action_on_container,
    docker_mappings_for_host_port,
    list_docker_mappings,
)
from .inspectors import get_inspector
from .safety import check_safety_policy, load_kport_config
from .diagnostics import (
    diagnose_port as _diagnose_port_data,
    detect_conflicts as _detect_conflicts_data,
    run_doctor as _run_doctor_data,
)

# R10 fix: use shared constants from kport.constants (single source of truth).
# MCP and CLI now share identical default protection lists.


def load_mcp_config() -> dict:
    """Load configuration dictionary from default kport config locations."""
    return load_kport_config()


def log(msg: str) -> None:
    """Print debug output directly to stderr to avoid corrupting JSON-RPC on stdout."""
    print(f"[kport-mcp] {msg}", file=sys.stderr, flush=True)


TOOLS = [
    {
        "name": "list_ports",
        "description": "Lists all active listening ports on the host machine, including both local processes and Docker containers with their PIDs, names, and states.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "inspect_port",
        "description": "Returns detailed information about the local process or Docker container holding a specific port.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 65535,
                    "description": "The port number to inspect.",
                }
            },
            "required": ["port"],
        },
    },
    {
        "name": "kill_port",
        "description": "Frees up a port by terminating the local process or executing a Docker container action if the port is owned by Docker.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 65535,
                    "description": "The port number to free up.",
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to force-kill (SIGKILL/fuser fallback) the process if graceful SIGTERM fails.",
                },
                "docker_action": {
                    "type": "string",
                    "enum": ["stop", "restart", "rm"],
                    "default": "stop",
                    "description": "The action to perform if the port belongs to a Docker container (stop, restart, or remove container).",
                },
            },
            "required": ["port"],
        },
    },
    {
        "name": "diagnose_port",
        "description": "Runs a detailed semantic diagnostic analysis on a specific port, providing structured observations, inferred service relationships/manager context, process risks, and remediation recommendations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 65535,
                    "description": "The port number to diagnose.",
                },
                "proto": {
                    "type": "string",
                    "enum": ["tcp", "udp", "both"],
                    "default": "tcp",
                    "description": "The protocol type to scan.",
                }
            },
            "required": ["port"],
        },
    },
    {
        "name": "conflicts",
        "description": "Runs conflict detection on the host machine to identify ports mapped to Docker containers that are also bound/occupied by native host processes.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "doctor",
        "description": "Runs an environment-wide diagnostic check, summarizing platform/capabilities, active listening sockets, connection counts, process/service context, and high-level configuration/risk findings.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def handle_list_ports(inspector) -> dict[str, Any]:
    """Execute list_ports tool request."""
    local_bindings = inspector.list_listening()
    docker_maps = list_docker_mappings()

    local_list = []
    for b in local_bindings:
        local_list.append(
            {
                "port": b.port,
                "pid": b.pid,
                "process_name": b.process_name,
                "state": b.state,
                "address": b.laddr,
            }
        )

    docker_list = []
    for d in docker_maps:
        docker_list.append(
            {
                "port": d.host_port,
                "container_name": d.container_name,
                "image": d.image,
                "status": d.status,
                "container_port": d.container_port,
                "protocol": d.proto,
            }
        )

    return {"local_processes": local_list, "docker_containers": docker_list}


def handle_inspect_port(inspector, port: int) -> dict[str, Any]:
    """Execute inspect_port tool request."""
    if not (1 <= port <= 65535):
        raise ValueError(f"Port {port} is out of bounds (1-65535)")

    local_bindings = inspector.find_bindings_on_port(port)
    docker_hits = docker_mappings_for_host_port(port)
    pids = inspector.find_pids_on_port(port)

    response = {"port": port}

    if docker_hits:
        m = docker_hits[0]
        response["type"] = "docker"
        response["container_name"] = m.container_name
        response["container_id"] = m.container_id
        response["image"] = m.image
        response["status"] = m.status
        response["container_port"] = m.container_port
        response["protocol"] = m.proto
        return response

    if not pids:
        if local_bindings:
            response["type"] = "local-unknown"
            response["message"] = (
                "Port in use, but owning PID is not visible (needs administrative privileges)"
            )
        else:
            response["type"] = "free"
    else:
        response["type"] = "local"
        proc_list = []
        for pid in pids:
            info = inspector.get_process_info(pid)
            if info:
                proc_list.append(
                    {
                        "pid": pid,
                        "name": info.name,
                        "exe": info.exe,
                        "cmdline": info.cmdline,
                        "user": info.user,
                    }
                )
            else:
                proc_list.append({"pid": pid, "message": "process details unavailable"})
        response["processes"] = proc_list

    return response


def handle_kill_port(
    inspector, port: int, force: bool = False, docker_action: str = "stop"
) -> dict[str, Any]:
    """Execute kill_port tool request under safety shield validations."""
    if not (1 <= port <= 65535):
        raise ValueError(f"Port {port} is out of bounds (1-65535)")

    # 1. Load configuration and retrieve target pids
    cfg = load_mcp_config()
    inspector = get_inspector()
    pids = inspector.find_pids_on_port(port)

    # 2. Unified safety policy check
    # MCP server NEVER bypasses safety (so bypass_safety=False).
    allowed, reason = check_safety_policy(
        port=port,
        pids=pids,
        inspector=inspector,
        bypass_safety=False,
        config=cfg if cfg else None,
    )
    if not allowed:
        return {
            "success": False,
            "message": reason,
        }

    docker_hits = docker_mappings_for_host_port(port)

    # 3. Docker container path
    if docker_hits:
        m = docker_hits[0]
        if docker_action == "rm" and not force:
            return {
                "success": False,
                "type": "docker",
                "container_name": m.container_name,
                "action": docker_action,
                "message": "Removing a Docker container is irreversible and requires force parameter to be explicitly set to True.",
            }
        ok, msg = docker_action_on_container(
            m.container_id, docker_action, dry_run=False
        )
        return {
            "success": ok,
            "type": "docker",
            "container_name": m.container_name,
            "action": docker_action,
            "message": msg,
        }

    # 4. No PIDs path
    if not pids:
        local_bindings = inspector.find_bindings_on_port(port)
        if local_bindings:
            return {
                "success": False,
                "type": "local-unknown",
                "message": "Port is active but owning PID is not visible. Start the MCP server with elevated privileges (admin/sudo).",
            }
        return {"success": True, "message": f"Port {port} is already free."}

    # 5. Local process escalated kill
    ok, msg = inspector.kill_port(
        port,
        graceful_timeout=3.0,
        force=force,
        dry_run=False,
        debug=True,
        assume_yes=True,
    )
    return {"success": ok, "type": "local", "pids_targeted": pids, "message": msg}


def handle_diagnose_port(inspector, port: int, proto: str = "tcp") -> dict[str, Any]:
    """Execute diagnose_port tool request."""
    if not (1 <= port <= 65535):
        raise ValueError(f"Port {port} is out of bounds (1-65535)")
    cfg = load_mcp_config()
    return _diagnose_port_data(port, inspector, proto=proto, config=cfg)


def handle_conflicts(inspector) -> list[dict[str, Any]]:
    """Execute conflicts tool request."""
    return _detect_conflicts_data(inspector)


def handle_doctor(inspector) -> dict[str, Any]:
    """Execute doctor tool request."""
    return _run_doctor_data(inspector)


def run_mcp_server() -> None:
    """Run standard stdio MCP JSON-RPC execution loop."""
    log("kport MCP Server successfully started.")

    # P3 fix: create ONE inspector for the entire server lifetime.
    # Creating a new instance per-call was wasteful; more importantly,
    # a single instance will correctly clear its own per-query cache
    # (via _clear_cache()) on each call rather than allocating fresh objects.
    inspector = get_inspector()

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if method == "initialize":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "kport", "version": __version__},
                    },
                }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

            elif method == "tools/list":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                try:
                    if tool_name == "list_ports":
                        result_data = handle_list_ports(inspector)
                    elif tool_name == "inspect_port":
                        target_port = int(arguments.get("port"))
                        result_data = handle_inspect_port(inspector, target_port)
                    elif tool_name == "kill_port":
                        target_port = int(arguments.get("port"))
                        force_flag = bool(arguments.get("force", False))
                        docker_act = str(arguments.get("docker_action", "stop"))
                        result_data = handle_kill_port(
                            inspector, target_port, force_flag, docker_act
                        )
                    elif tool_name == "diagnose_port":
                        target_port = int(arguments.get("port"))
                        proto_val = str(arguments.get("proto", "tcp"))
                        result_data = handle_diagnose_port(inspector, target_port, proto_val)
                    elif tool_name == "conflicts":
                        result_data = handle_conflicts(inspector)
                    elif tool_name == "doctor":
                        result_data = handle_doctor(inspector)
                    else:
                        raise ValueError(f"Unknown tool: {tool_name}")

                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(result_data, indent=2),
                                }
                            ],
                            "isError": not result_data.get("success", True)
                            if "success" in result_data
                            else False,
                        },
                    }
                except Exception as ex:  # noqa: BLE001 - top-level tool execution handler (intentional)
                    log(f"Tool execution failed: {traceback.format_exc()}")
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Error executing tool '{tool_name}': {ex!s}",
                                }
                            ],
                            "isError": True,
                        },
                    }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

            elif method == "notifications/initialized":
                # Standard client initialized notification
                pass

            else:
                if req_id is not None:
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method not found: {method}",
                        },
                    }
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()

        except Exception:  # noqa: BLE001 - top-level RPC framing (must not crash the server)
            log(f"RPC framing error: {traceback.format_exc()}")
