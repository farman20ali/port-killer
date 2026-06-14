"""
Model Context Protocol (MCP) server implementation for kport.
Implements standard stdio-based tool calls with zero dependencies.
Incorporates a strict safety shield to prevent AI agents from killing critical system ports.
"""

import sys
import json
import traceback
from typing import Dict, Any, List
from .inspectors import get_inspector
from .docker_engine import list_docker_mappings, docker_mappings_for_host_port, docker_action_on_container
from . import __version__

# Security blocklist: ports that AI agents are prevented from killing by default.
PROTECTED_PORTS = {
    22,    # SSH
    53,    # DNS
    80,    # HTTP
    443,   # HTTPS
    5432,  # PostgreSQL
    3306,  # MySQL
    6379,  # Redis
    6443,  # Kubernetes API
}

# Critical system process names that should never be targeted
PROTECTED_PROCESS_NAMES = {
    "systemd", "init", "docker", "dockerd", "sshd", "explorer.exe", "lsass.exe", "services.exe"
}


import os

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
            except Exception:
                pass
    return {}


def log(msg: str) -> None:
    """Print debug output directly to stderr to avoid corrupting JSON-RPC on stdout."""
    print(f"[kport-mcp] {msg}", file=sys.stderr, flush=True)


TOOLS = [
    {
        "name": "list_ports",
        "description": "Lists all active listening ports on the host machine, including both local processes and Docker containers with their PIDs, names, and states.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
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
                    "description": "The port number to inspect."
                }
            },
            "required": ["port"]
        }
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
                    "description": "The port number to free up."
                },
                "force": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to force-kill (SIGKILL/fuser fallback) the process if graceful SIGTERM fails."
                },
                "docker_action": {
                    "type": "string",
                    "enum": ["stop", "restart", "rm"],
                    "default": "stop",
                    "description": "The action to perform if the port belongs to a Docker container (stop, restart, or remove container)."
                }
            },
            "required": ["port"]
        }
    }
]


def handle_list_ports() -> Dict[str, Any]:
    """Execute list_ports tool request."""
    inspector = get_inspector()
    local_bindings = inspector.list_listening()
    docker_maps = list_docker_mappings()

    local_list = []
    for b in local_bindings:
        local_list.append({
            "port": b.port,
            "pid": b.pid,
            "process_name": b.process_name,
            "state": b.state,
            "address": b.laddr
        })

    docker_list = []
    for d in docker_maps:
        docker_list.append({
            "port": d.host_port,
            "container_name": d.container_name,
            "image": d.image,
            "status": d.status,
            "container_port": d.container_port,
            "protocol": d.proto
        })

    return {
        "local_processes": local_list,
        "docker_containers": docker_list
    }


def handle_inspect_port(port: int) -> Dict[str, Any]:
    """Execute inspect_port tool request."""
    if not (1 <= port <= 65535):
        raise ValueError(f"Port {port} is out of bounds (1-65535)")

    inspector = get_inspector()
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
            response["message"] = "Port in use, but owning PID is not visible (needs administrative privileges)"
        else:
            response["type"] = "free"
    else:
        response["type"] = "local"
        proc_list = []
        for pid in pids:
            info = inspector.get_process_info(pid)
            if info:
                proc_list.append({
                    "pid": pid,
                    "name": info.name,
                    "exe": info.exe,
                    "cmdline": info.cmdline,
                    "user": info.user
                })
            else:
                proc_list.append({"pid": pid, "message": "process details unavailable"})
        response["processes"] = proc_list

    return response


def handle_kill_port(port: int, force: bool = True, docker_action: str = "stop") -> Dict[str, Any]:
    """Execute kill_port tool request under safety shield validations."""
    if not (1 <= port <= 65535):
        raise ValueError(f"Port {port} is out of bounds (1-65535)")

    # Load safety configurations dynamically
    cfg = load_mcp_config()
    
    # 1. Resolve active protected lists (merging defaults and config overrides)
    protected_ports = set(PROTECTED_PORTS)
    config_ports = cfg.get("protected_ports")
    if isinstance(config_ports, list):
        protected_ports = set(config_ports)
        
    protected_procs = set(PROTECTED_PROCESS_NAMES)
    config_procs = cfg.get("protected_processes")
    if isinstance(config_procs, list):
        protected_procs = {p.lower() for p in config_procs}

    # 2. Protected ports shield check
    if port in protected_ports:
        return {
            "success": False,
            "message": f"Security Shield Active: Port {port} is a critical system/database socket. AI is prevented from terminating it."
        }

    inspector = get_inspector()
    docker_hits = docker_mappings_for_host_port(port)
    pids = inspector.find_pids_on_port(port)

    # 3. Docker container path
    if docker_hits:
        m = docker_hits[0]
        ok, msg = docker_action_on_container(m.container_id, docker_action, dry_run=False)
        return {
            "success": ok,
            "type": "docker",
            "container_name": m.container_name,
            "action": docker_action,
            "message": msg
        }

    # 4. No PIDs path
    if not pids:
        local_bindings = inspector.find_bindings_on_port(port)
        if local_bindings:
            return {
                "success": False,
                "type": "local-unknown",
                "message": "Port is active but owning PID is not visible. Start the MCP server with elevated privileges (admin/sudo)."
            }
        return {
            "success": True,
            "message": f"Port {port} is already free."
        }

    # 5. Critical process name shield check
    for pid in pids:
        info = inspector.get_process_info(pid)
        if info and info.name.lower() in protected_procs:
            return {
                "success": False,
                "message": f"Security Shield Active: PID {pid} runs critical system process '{info.name}'. Termination aborted."
            }

    # 5. Local process escalated kill
    ok, msg = inspector.kill_port(port, graceful_timeout=3.0, force=force, dry_run=False, debug=True)
    return {
        "success": ok,
        "type": "local",
        "pids_targeted": pids,
        "message": msg
    }


def run_mcp_server() -> None:
    """Run standard stdio MCP JSON-RPC execution loop."""
    log("kport MCP Server successfully started.")

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
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "kport",
                            "version": __version__
                        }
                    }
                }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

            elif method == "tools/list":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": TOOLS
                    }
                }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                try:
                    if tool_name == "list_ports":
                        result_data = handle_list_ports()
                    elif tool_name == "inspect_port":
                        target_port = int(arguments.get("port"))
                        result_data = handle_inspect_port(target_port)
                    elif tool_name == "kill_port":
                        target_port = int(arguments.get("port"))
                        force_flag = bool(arguments.get("force", True))
                        docker_act = str(arguments.get("docker_action", "stop"))
                        result_data = handle_kill_port(target_port, force_flag, docker_act)
                    else:
                        raise ValueError(f"Unknown tool: {tool_name}")

                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(result_data, indent=2)
                                }
                            ],
                            "isError": not result_data.get("success", True) if "success" in result_data else False
                        }
                    }
                except Exception as ex:
                    log(f"Tool execution failed: {traceback.format_exc()}")
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Error executing tool '{tool_name}': {str(ex)}"
                                }
                            ],
                            "isError": True
                        }
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
                            "message": f"Method not found: {method}"
                        }
                    }
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()

        except Exception as e:
            log(f"RPC framing error: {traceback.format_exc()}")
