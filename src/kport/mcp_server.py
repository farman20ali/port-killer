"""
Model Context Protocol (MCP) server implementation for kport.
Implements standard stdio-based tool calls with zero dependencies.
Incorporates a strict safety shield to prevent AI agents from killing critical system ports.
"""
from __future__ import annotations

import os
import sys
import json
import traceback
from typing import Dict, Any

from .inspectors import get_inspector
from .docker_engine import (
    list_docker_mappings,
    docker_mappings_for_host_port,
    docker_action_on_container,
)
from . import __version__
from .constants import PROTECTED_PORTS, PROTECTED_PROCESS_NAMES

# R10 fix: use shared constants from kport.constants (single source of truth).
# MCP and CLI now share identical default protection lists.
PROTECTED_PORTS = PROTECTED_PORTS  # re-export for backward compat
PROTECTED_PROCESS_NAMES = PROTECTED_PROCESS_NAMES  # re-export for backward compat


def load_mcp_config() -> dict:
    """Load configuration dictionary from default kport config locations."""
    home = os.path.expanduser("~")
    paths = [
        os.path.join(os.getcwd(), ".kport.json"),
        os.path.join(home, ".kport.json"),
        os.path.join(home, ".config", "kport", "config.json"),
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except (OSError, json.JSONDecodeError) as ex:
                # Non-fatal: config read/parse failed; continue with defaults.
                log(f"Failed to load MCP config from {p}: {ex!s}")
    return {}


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
                    "default": True,
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
]


def handle_list_ports(inspector) -> Dict[str, Any]:
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


def handle_inspect_port(inspector, port: int) -> Dict[str, Any]:
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
    inspector, port: int, force: bool = True, docker_action: str = "stop"
) -> Dict[str, Any]:
    """Execute kill_port tool request under safety shield validations."""
    if not (1 <= port <= 65535):
        raise ValueError(f"Port {port} is out of bounds (1-65535)")

    # Load safety configurations dynamically
    cfg = load_mcp_config()

    # 1. Resolve active protected lists — ADDITIVE, not replacement.
    #    A user config with protected_ports:[9999] should ADD to defaults,
    #    not silently unprotect SSH (22), Redis (6379), etc.
    protected_ports = set(PROTECTED_PORTS)
    config_ports = cfg.get("protected_ports")
    if isinstance(config_ports, list):
        protected_ports.update(config_ports)  # additive union

    protected_procs = set(PROTECTED_PROCESS_NAMES)
    config_procs = cfg.get("protected_processes")
    if isinstance(config_procs, list):
        protected_procs.update(p.lower() for p in config_procs)  # additive union

    # 2. Protected ports shield check
    if port in protected_ports:
        return {
            "success": False,
            "message": f"Security Shield Active: Port {port} is a critical system/database socket. AI is prevented from terminating it.",
        }

    inspector = get_inspector()
    docker_hits = docker_mappings_for_host_port(port)
    pids = inspector.find_pids_on_port(port)

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

    # 5. Critical process name shield check
    for pid in pids:
        info = inspector.get_process_info(pid)
        # R9 fix: was duplicate "# 5." label. Now correctly numbered as step 5.
        # Strip enrichment suffix (e.g. "sshd (...)" should still match "sshd")
        base_name = info.name.lower().split(" (")[0] if info else ""
        if base_name in protected_procs:
            return {
                "success": False,
                "message": f"Security Shield Active: PID {pid} runs critical system process '{info.name}'. Termination aborted.",
            }

    # 6. Local process escalated kill
    ok, msg = inspector.kill_port(
        port,
        graceful_timeout=3.0,
        force=force,
        dry_run=False,
        debug=True,
        assume_yes=True,
    )
    return {"success": ok, "type": "local", "pids_targeted": pids, "message": msg}


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
                        force_flag = bool(arguments.get("force", True))
                        docker_act = str(arguments.get("docker_action", "stop"))
                        result_data = handle_kill_port(
                            inspector, target_port, force_flag, docker_act
                        )
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
