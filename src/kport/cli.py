"""
Command-line interface (CLI) entry point and router for kport.
Parses options, handles configs, and delegates logic to backend components.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Dict, Optional, Any
from dataclasses import asdict

from .exceptions import KPortError, InvalidPortError, PermissionDeniedError
from .inspectors import get_inspector, BaseInspector, PortBinding
from .docker_engine import (
    list_docker_mappings,
    docker_mappings_for_host_port,
    docker_action_on_container
)
from .formatter import (
    Colors,
    colorize,
    print_table_listen,
    jsonify_bindings,
    confirm_prompt,
    choose_docker_action,
    print_table_docker,
    print_table_list_product,
    jsonify_docker
)

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
    """Load optional JSON configuration defaults."""
    candidate_paths = [config_path] if config_path else _default_config_paths()

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
    """Apply configuration options as fallback defaults to argparse Namespace."""
    def _set_bool(name: str, key: str) -> None:
        if hasattr(args, name) and getattr(args, name) is False and isinstance(cfg.get(key), bool):
            setattr(args, name, cfg[key])

    def _set_num(name: str, key: str) -> None:
        if hasattr(args, name) and cfg.get(key) is not None:
            try:
                current = getattr(args, name)
                # Only apply if still at default
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


def validate_port(port: int) -> None:
    """Validate port constraints, raising InvalidPortError on failure."""
    if not (1 <= port <= 65535):
        raise InvalidPortError(f"Port {port} is not valid. Must be 1-65535.")


def parse_port_range(port_range: str, max_ports: int = 1000) -> List[int]:
    """Parse port range strings (e.g. 8080 or 3000-3010)."""
    try:
        if '-' in port_range:
            start_s, end_s = port_range.split('-', 1)
            start = int(start_s.strip())
            end = int(end_s.strip())
            if start > end:
                raise InvalidPortError(f"Invalid range {port_range}: start > end")
            total = end - start + 1
            if total > max_ports:
                raise InvalidPortError(f"Range too large ({total} ports). Maximum {max_ports} allowed.")
            for p in (start, end):
                validate_port(p)
            return list(range(start, end + 1))
        else:
            port = int(port_range.strip())
            validate_port(port)
            return [port]
    except ValueError:
        raise InvalidPortError(f"Invalid port or range format: {port_range}")


def handle_product_command(args: argparse.Namespace, inspector: BaseInspector) -> int:
    """Implement subcommands defined in the product specification."""
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
            msg = "Port is in use, but the owning PID is not visible (try running with sudo/admin)."
            if args.json:
                print(json.dumps({"port": args.port, "type": "local-unknown", "message": msg, "bindings": [asdict(b) for b in local_bindings]}, indent=2))
            else:
                print(colorize(f"Port: {args.port}", Colors.CYAN + Colors.BOLD))
                print("Type: Local Process")
                print(colorize(msg, Colors.YELLOW))
            return EXIT_OK

        # Local process
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
                print(json.dumps({
                    "port": args.port,
                    "blocked": True,
                    "because": [
                        f"It is mapped to Docker container '{m.container_name}'",
                        f"Docker maps host port {m.host_port} → container port {m.container_port}",
                        "The process runs inside an isolated network namespace",
                    ],
                }, indent=2))
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

        # Local process explanation
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
                    print(json.dumps({
                        "port": args.port,
                        "type": "docker",
                        "container": m.container_name,
                        "container_id": m.container_id,
                        "available_actions": ["stop", "restart", "rm"],
                        "performed": None,
                        "message": "No action selected",
                    }, indent=2))
                else:
                    print(colorize("Operation cancelled.", Colors.YELLOW))
                return EXIT_GENERAL_ERROR

            if args.json and not args.yes and not args.dry_run:
                print(json.dumps({
                    "port": args.port,
                    "type": "docker",
                    "container": m.container_name,
                    "container_id": m.container_id,
                    "requested_action": action,
                    "performed": False,
                    "message": "Refusing to act without --yes in JSON mode",
                }, indent=2))
                return EXIT_GENERAL_ERROR

            ok, msg = docker_action_on_container(m.container_id, action=action, dry_run=args.dry_run, debug=debug)
            if args.json:
                print(json.dumps({
                    "port": args.port,
                    "type": "docker",
                    "container": m.container_name,
                    "container_id": m.container_id,
                    "action": action,
                    "ok": ok,
                    "message": msg,
                }, indent=2))
            else:
                if ok:
                    print(colorize(f"✓ {msg}", Colors.GREEN))
                else:
                    print(colorize(f"✗ {msg}", Colors.RED))
            return EXIT_OK if ok else EXIT_GENERAL_ERROR

        # Local process kill
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

        # Unified escalated kill execution (Fixes Bug 1 & Bug 2)
        ok, msg = inspector.kill_port(
            args.port, 
            graceful_timeout=args.graceful_timeout, 
            force=args.force, 
            dry_run=args.dry_run,
            debug=debug
        )

        if args.json:
            print(json.dumps({
                "port": args.port,
                "success": ok,
                "message": msg,
                "pids_targeted": pids
            }, indent=2))
        else:
            if ok:
                print(colorize(f"✓ {msg}", Colors.GREEN))
            else:
                print(colorize(f"✗ {msg}", Colors.RED))
        
        return EXIT_OK if ok else EXIT_GENERAL_ERROR

    if args.command == "kill-process":
        pname = args.name
        pids = inspector.find_pids_by_name(pname, exact=args.exact)
        if not pids:
            if args.json:
                print(json.dumps({"name": pname, "pids": []}, indent=2))
            else:
                print(colorize(f"✗ No processes found matching '{pname}'", Colors.RED))
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
        conflicts = []
        for m in docker_maps:
            pids = inspector.find_pids_on_port(m.host_port)
            non_docker_pids = []
            for pid in pids:
                info = inspector.get_process_info(pid)
                pname = (info.name if info else "").lower()
                if "docker-proxy" in pname or pname.startswith("docker"):
                    continue
                non_docker_pids.append({"pid": pid, "process": asdict(info) if info else None})
            if non_docker_pids:
                conflicts.append({
                    "port": m.host_port,
                    "docker": asdict(m),
                    "local": non_docker_pids,
                })
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

    if args.command == "mcp":
        from .mcp_server import run_mcp_server
        run_mcp_server()
        return EXIT_OK

    return EXIT_INVALID_INPUT


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="kport - Cross-platform port inspector and killer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  kport -i 8080
  kport -im 3000 3001 3002
  kport -ir 3000-3010
  kport -k 8080 --yes
  kport inspect 8080
  kport kill 8080 --force
  kport mcp
"""
    )

    # Global options
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without executing")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--debug", action="store_true", help="Verbose internal logs")
    parser.add_argument("--config", type=str, default=None, help="Path to JSON config file")

    # Legacy flags
    parser.add_argument("-i", "--inspect", type=int, metavar="PORT", help="Inspect specified port")
    parser.add_argument("-im", "--inspect-multiple", type=int, nargs="+", metavar="PORT", help="Inspect multiple ports")
    parser.add_argument("-ir", "--inspect-range", type=str, metavar="RANGE", help="Inspect port range")
    parser.add_argument("-ip", "--inspect-process", type=str, metavar="NAME", help="Inspect processes by name")
    parser.add_argument("-k", "--kill", type=int, metavar="PORT", help="Kill processes using port")
    parser.add_argument("-kp", "--kill-process", type=str, metavar="NAME", help="Kill processes by name")
    parser.add_argument("-ka", "--kill-all", type=int, nargs="+", metavar="PORT", help="Kill multiple ports")
    parser.add_argument("-kr", "--kill-range", type=str, metavar="RANGE", help="Kill processes on range")
    parser.add_argument("-l", "--list", action="store_true", help="List all listening ports")
    parser.add_argument("--exact", action="store_true", help="Exact process name matching")
    parser.add_argument("--force", action="store_true", help="Force kill stubborn processes (SIGKILL / fuser)")
    parser.add_argument("--graceful-timeout", type=float, default=3.0, help="Seconds to wait before force kill")
    parser.add_argument("-v", "--version", action="version", version="kport 3.1.2")

    # Subcommands
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

    sp_mcp = sub.add_parser("mcp", help="Start the stdio Model Context Protocol (MCP) server")

    args = parser.parse_args(argv)

    # Load configuration
    cfg = load_config(getattr(args, "config", None), debug=getattr(args, "debug", False))
    apply_config_defaults(args, cfg)

    inspector = get_inspector()

    try:
        # 1. Product subcommands routing
        if getattr(args, "command", None):
            return handle_product_command(args, inspector)

        # Show help if no action requested
        if not any([args.inspect, args.inspect_multiple, args.inspect_range, args.inspect_process, args.kill, args.list, args.kill_process, args.kill_all, args.kill_range]):
            parser.print_help()
            return EXIT_OK

        # 2. Legacy flag parsing and execution

        # List ports
        if args.list:
            bindings = inspector.list_listening()
            if args.json:
                print(jsonify_bindings(bindings))
            else:
                print(colorize("\n📋 Listening ports\n", Colors.CYAN + Colors.BOLD))
                print_table_listen(bindings)

        # Inspect port
        if args.inspect:
            validate_port(args.inspect)
            local_bindings = [b for b in inspector.list_listening() if b.port == args.inspect]
            docker_hits = docker_mappings_for_host_port(args.inspect, debug=args.debug)
            pids = inspector.find_pids_on_port(args.inspect)
            if not pids:
                if docker_hits:
                    m = docker_hits[0]
                    if args.json:
                        print(json.dumps({
                            "port": args.inspect,
                            "type": "docker",
                            "container": m.container_name,
                            "image": m.image,
                            "host_port": m.host_port,
                            "container_port": m.container_port,
                            "status": m.status,
                        }, indent=2))
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
                    out = {"port": args.inspect, "pids": info_list}
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
                    pid_groups = {}
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

        # Kill by process name (legacy)
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
                    out = []
                    for pid in pids:
                        info = inspector.get_process_info(pid)
                        out.append({"pid": pid, "process": asdict(info) if info else None})
                    print(json.dumps({"name": pname, "pids": out}, indent=2))
                    if not args.yes:
                        print(colorize("Note: JSON output provided. Use --yes to actually perform kills.", Colors.YELLOW))
                    else:
                        killed = []
                        failed = []
                        for pid in pids:
                            ok, msg = inspector.kill_pid(pid, graceful_timeout=args.graceful_timeout, force=args.force, dry_run=args.dry_run)
                            if ok:
                                killed.append({"pid": pid, "msg": msg})
                            else:
                                failed.append({"pid": pid, "msg": msg})
                        print(json.dumps({"killed": killed, "failed": failed}, indent=2))
                        if failed:
                            return EXIT_GENERAL_ERROR
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
                        failed_count = 0
                        for pid in pids:
                            ok, msg = inspector.kill_pid(pid, graceful_timeout=args.graceful_timeout, force=args.force, dry_run=args.dry_run)
                            if ok:
                                killed_count += 1
                                print(colorize(f"✓ Killed PID {pid} ({msg})", Colors.GREEN))
                            else:
                                failed_count += 1
                                print(colorize(f"✗ Failed to kill PID {pid} ({msg})", Colors.RED))
                        
                        if failed_count > 0:
                            print(colorize(f"\n✗ Failed to kill {failed_count}/{len(pids)} process(es)", Colors.RED + Colors.BOLD))
                            return EXIT_GENERAL_ERROR
                        else:
                            print(colorize(f"\n✓ Successfully killed {killed_count}/{len(pids)} process(es)", Colors.GREEN + Colors.BOLD))

        # Kill single port (legacy) - escalated & verified (Fixes Bug 1 & Bug 2)
        if args.kill:
            validate_port(args.kill)
            local_bindings = [b for b in inspector.list_listening() if b.port == args.kill]
            docker_hits = docker_mappings_for_host_port(args.kill, debug=args.debug)
            pids = inspector.find_pids_on_port(args.kill)
            if not pids:
                if docker_hits:
                    m = docker_hits[0]
                    if args.json and not args.yes and not args.dry_run:
                        print(json.dumps({
                            "port": args.kill,
                            "type": "docker",
                            "container": m.container_name,
                            "container_id": m.container_id,
                            "message": "Refusing to act without --yes in JSON mode",
                        }, indent=2))
                    else:
                        action = "stop" if args.json else None
                        if not args.json:
                            print(colorize(f"\n🐳 Port {args.kill} belongs to Docker container: {m.container_name}", Colors.YELLOW + Colors.BOLD))
                            action = choose_docker_action(assume_yes=args.yes)
                        if action:
                            ok, msg = docker_action_on_container(m.container_id, action=action, dry_run=args.dry_run, debug=args.debug)
                            if args.json:
                                print(json.dumps({"port": args.kill, "type": "docker", "action": action, "ok": ok, "message": msg}, indent=2))
                            else:
                                print(colorize(("✓ " if ok else "✗ ") + msg, Colors.GREEN if ok else Colors.RED))
                            if not ok:
                                return EXIT_GENERAL_ERROR
                elif local_bindings:
                    msg = "Port is in use but PID is not visible; cannot kill safely. Try sudo/admin."
                    if args.json:
                        print(json.dumps({"port": args.kill, "ok": False, "message": msg, "bindings": [asdict(b) for b in local_bindings]}, indent=2))
                    else:
                        print(colorize(msg, Colors.RED))
                    return EXIT_PERMISSION
                else:
                    if args.json:
                        print(json.dumps({"port": args.kill, "killed": [], "failed": []}, indent=2))
                    else:
                        print(colorize(f"❌ No process found using port {args.kill}", Colors.RED))
            else:
                if args.json:
                    ok, msg = inspector.kill_port(args.kill, graceful_timeout=args.graceful_timeout, force=args.force, dry_run=args.dry_run, debug=args.debug)
                    out = {"port": args.kill, "success": ok, "message": msg, "pids_targeted": pids}
                    if docker_hits:
                        out["docker"] = [asdict(m) for m in docker_hits]
                    print(json.dumps(out, indent=2))
                    return EXIT_OK if ok else EXIT_GENERAL_ERROR
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
                        return EXIT_GENERAL_ERROR
                    else:
                        # Escalated verified kill call
                        ok, msg = inspector.kill_port(args.kill, graceful_timeout=args.graceful_timeout, force=args.force, dry_run=args.dry_run, debug=args.debug)
                        if ok:
                            print(colorize(f"\n✓ Port {args.kill} successfully freed ({msg})", Colors.GREEN + Colors.BOLD))
                            return EXIT_OK
                        else:
                            print(colorize(f"\n✗ Failed to free port {args.kill}: {msg}", Colors.RED + Colors.BOLD))
                            return EXIT_GENERAL_ERROR

        # Kill multiple ports (legacy)
        if args.kill_all:
            for port in args.kill_all:
                validate_port(port)
            port_pid_map = {}
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
                    return EXIT_GENERAL_ERROR
                else:
                    failed_ports = 0
                    total_ports = len(port_pid_map)
                    for port in port_pid_map.keys():
                        ok, msg = inspector.kill_port(port, graceful_timeout=args.graceful_timeout, force=args.force, dry_run=args.dry_run, debug=args.debug)
                        if ok:
                            print(colorize(f"✓ Freed port {port} ({msg})", Colors.GREEN))
                        else:
                            print(colorize(f"✗ Failed to free port {port}: {msg}", Colors.RED))
                            failed_ports += 1
                    
                    if failed_ports > 0:
                        print(colorize(f"\n✗ Failed to free {failed_ports}/{total_ports} port(s)", Colors.RED + Colors.BOLD))
                        return EXIT_GENERAL_ERROR
                    else:
                        print(colorize(f"\n✓ Successfully freed all {total_ports} port(s)", Colors.GREEN + Colors.BOLD))

        # Kill range (legacy)
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
                    return EXIT_GENERAL_ERROR
                else:
                    failed_ports = 0
                    total_ports = len(port_pid_map)
                    for port in port_pid_map.keys():
                        ok, msg = inspector.kill_port(port, graceful_timeout=args.graceful_timeout, force=args.force, dry_run=args.dry_run, debug=args.debug)
                        if ok:
                            print(colorize(f"✓ Freed port {port} ({msg})", Colors.GREEN))
                        else:
                            print(colorize(f"✗ Failed to free port {port}: {msg}", Colors.RED))
                            failed_ports += 1

                    if failed_ports > 0:
                        print(colorize(f"\n✗ Failed to free {failed_ports}/{total_ports} port(s) in range", Colors.RED + Colors.BOLD))
                        return EXIT_GENERAL_ERROR
                    else:
                        print(colorize(f"\n✓ Successfully freed all {total_ports} port(s) in range", Colors.GREEN + Colors.BOLD))

    # Catch custom domain exceptions cleanly (fixes hard exits inside functions)
    except InvalidPortError as e:
        print(colorize(f"Error: {e}", Colors.RED), file=sys.stderr)
        return EXIT_INVALID_INPUT
    except PermissionDeniedError as e:
        print(colorize(f"Permission denied: {e}. Try running with administrative privileges (sudo/admin).", Colors.RED), file=sys.stderr)
        return EXIT_PERMISSION
    except KPortError as e:
        print(colorize(f"kport error: {e}", Colors.RED), file=sys.stderr)
        return EXIT_GENERAL_ERROR
    except PermissionError:
        print(colorize("Permission denied. Try running with elevated privileges (sudo/admin).", Colors.RED), file=sys.stderr)
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