"""
Command-line interface (CLI) entry point and router for kport.
Parses options, handles configs, and delegates logic to backend components.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import asdict

from .exceptions import KPortError, InvalidPortError, PermissionDeniedError
from . import __version__
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


class _QuietParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(colorize(f"Error: {message}", Colors.RED), file=sys.stderr)
        print(f"Run 'kport --help' for usage.", file=sys.stderr)
        sys.exit(EXIT_INVALID_INPUT)


def _configure_stdio() -> None:
    """Use UTF-8 on Windows so emoji/symbols in CLI output do not crash."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


# Default safety policies (Phase 2 Pro features)
DEFAULT_PROTECTED_PORTS = {22, 53, 80, 443, 3306, 5432, 6379, 6443}
DEFAULT_PROTECTED_PROCESS_NAMES = {
    "systemd", "init", "docker", "dockerd", "sshd", "explorer.exe", "lsass.exe", "services.exe"
}


def check_safety_policy(port: Optional[int], pids: List[int], args: argparse.Namespace, inspector: BaseInspector) -> Tuple[bool, str]:
    """
    Check if a port or any associated PIDs are protected by safety policies.
    Returns (True, "") if safety policy permits, or (False, error_msg) if blocked.
    """
    bypass = getattr(args, "bypass_safety", False)

    # 1. Resolve active protected lists (merging defaults and config overrides)
    protected_ports = set(DEFAULT_PROTECTED_PORTS)
    config_ports = getattr(args, "protected_ports", None)
    if isinstance(config_ports, list):
        protected_ports = set(config_ports)

    protected_procs = set(DEFAULT_PROTECTED_PROCESS_NAMES)
    config_procs = getattr(args, "protected_processes", None)
    if isinstance(config_procs, list):
        protected_procs = {p.lower() for p in config_procs}

    # 2. Check Port protection
    if port is not None and port in protected_ports:
        if bypass:
            debug_log(getattr(args, "debug", False), f"Safety shield bypassed for protected port {port}")
        else:
            return False, f"Security Shield Active: Port {port} is a protected port. Action aborted. Use --bypass-safety to override."

    # 3. Check Process protection
    for pid in pids:
        try:
            info = inspector.get_process_info(pid)
            if info and info.name.lower() in protected_procs:
                if bypass:
                    debug_log(getattr(args, "debug", False), f"Safety shield bypassed for protected process '{info.name}' (PID {pid})")
                else:
                    return False, f"Security Shield Active: PID {pid} runs critical process '{info.name}' which is protected. Action aborted. Use --bypass-safety to override."
        except Exception:
            pass

    return True, ""


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
        # Only apply if the attribute exists AND is still at its default (False)
        if hasattr(args, name) and getattr(args, name) is False and isinstance(cfg.get(key), bool):
            setattr(args, name, cfg[key])

    def _set_num(name: str, key: str) -> None:
        # FIX: graceful_timeout default is now None; apply config only when not explicitly set
        if hasattr(args, name) and cfg.get(key) is not None:
            try:
                current = getattr(args, name)
                if name == "graceful_timeout" and current is None:
                    setattr(args, name, float(cfg[key]))
            except Exception:
                pass

    _set_bool("yes", "yes")
    _set_bool("dry_run", "dry_run")
    _set_bool("json", "json")
    _set_bool("debug", "debug")
    _set_bool("force", "force")
    _set_bool("bypass_safety", "bypass_safety")
    _set_num("graceful_timeout", "graceful_timeout")

    # Custom safety lists from config
    setattr(args, "protected_ports", cfg.get("protected_ports"))
    setattr(args, "protected_processes", cfg.get("protected_processes"))

    if hasattr(args, "docker_action") and getattr(args, "docker_action", None) is None:
        v = cfg.get("docker_action")
        if v in ("stop", "restart", "rm"):
            setattr(args, "docker_action", v)


def _resolve_timeout(args: argparse.Namespace) -> float:
    """Return graceful_timeout, falling back to 3.0 if not set."""
    t = getattr(args, "graceful_timeout", None)
    return float(t) if t is not None else 3.0


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
        extra = getattr(args, "extra", [])
        if extra:
            print(colorize(f"Note: 'kport docker' has no subcommands. Ignoring: {' '.join(extra)}", Colors.YELLOW), file=sys.stderr)
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
        local_bindings = inspector.find_bindings_on_port(args.port)
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
        local_bindings = inspector.find_bindings_on_port(args.port)
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
        pids = inspector.find_pids_on_port(args.port)

        # Check safety policy
        safe, safety_msg = check_safety_policy(args.port, pids, args, inspector)
        if not safe:
            if args.json:
                print(json.dumps({"port": args.port, "success": False, "message": safety_msg}, indent=2))
            else:
                print(colorize(safety_msg, Colors.RED), file=sys.stderr)
            return EXIT_PERMISSION

        local_bindings = inspector.find_bindings_on_port(args.port)
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

        ok, msg = inspector.kill_port(
            args.port,
            graceful_timeout=_resolve_timeout(args),  # FIX: use helper, never None
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

        # Check safety policy
        safe, safety_msg = check_safety_policy(None, pids, args, inspector)
        if not safe:
            if args.json:
                print(json.dumps({"name": pname, "success": False, "message": safety_msg}, indent=2))
            else:
                print(colorize(safety_msg, Colors.RED), file=sys.stderr)
            return EXIT_PERMISSION

        if not args.json and not confirm_prompt(f"Proceed to terminate {len(pids)} process(es)?", assume_yes=args.yes):
            print(colorize("Operation cancelled.", Colors.YELLOW))
            return EXIT_GENERAL_ERROR

        killed = []
        failed = []
        for pid in pids:
            ok, msg = inspector.kill_pid(pid, graceful_timeout=_resolve_timeout(args), force=args.force, dry_run=args.dry_run)
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

    if args.command == "watch":
        validate_port(args.port)
        interval = getattr(args, "interval", 1.0)

        import time
        from datetime import datetime

        def get_current_state() -> Dict[str, Any]:
            local_bindings = inspector.find_bindings_on_port(args.port)
            docker_hits = docker_mappings_for_host_port(args.port, debug=debug)
            pids = inspector.find_pids_on_port(args.port)

            if docker_hits:
                m = docker_hits[0]
                return {
                    "type": "docker",
                    "container": m.container_name,
                    "image": m.image,
                    "status": m.status,
                    "host_port": m.host_port,
                    "container_port": m.container_port,
                }
            elif pids:
                procs = []
                for pid in pids:
                    info = inspector.get_process_info(pid)
                    procs.append(info.name if info else "Unknown")
                return {
                    "type": "local",
                    "pids": pids,
                    "processes": procs,
                }
            elif local_bindings:
                return {
                    "type": "local-unknown",
                    "message": "Owning PID not visible"
                }
            else:
                return {"type": "free"}

        def describe_state(state: Dict[str, Any]) -> str:
            stype = state["type"]
            if stype == "free":
                return "FREE (no active connections)"
            elif stype == "docker":
                return f"DOCKER container '{state['container']}' ({state['image']}, status={state['status']})"
            elif stype == "local":
                procs_str = ", ".join(f"{name} (PID {pid})" for pid, name in zip(state["pids"], state["processes"]))
                return f"LOCAL process(es): {procs_str}"
            elif stype == "local-unknown":
                return "LOCAL (PID not visible/hidden)"
            return "UNKNOWN"

        last_state = None

        if args.json:
            initial = get_current_state()
            initial["timestamp"] = datetime.now().isoformat()
            print(json.dumps(initial))
            sys.stdout.flush()
            last_state = initial
        else:
            initial = get_current_state()
            print(colorize(f"👀 Watching port {args.port} (interval={interval}s). Press Ctrl+C to stop.", Colors.CYAN + Colors.BOLD))
            print(colorize(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Initial state: {describe_state(initial)}", Colors.WHITE))
            last_state = initial

        try:
            while True:
                time.sleep(interval)
                current = get_current_state()

                changed = False
                if current["type"] != last_state["type"]:
                    changed = True
                elif current["type"] == "docker":
                    if current["container"] != last_state.get("container") or current["status"] != last_state.get("status"):
                        changed = True
                elif current["type"] == "local":
                    if set(current["pids"]) != set(last_state.get("pids", [])):
                        changed = True

                if changed:
                    ts = datetime.now()
                    if args.json:
                        current["timestamp"] = ts.isoformat()
                        print(json.dumps(current))
                        sys.stdout.flush()
                    else:
                        desc = describe_state(current)
                        color = Colors.GREEN if current["type"] == "free" else Colors.YELLOW
                        print(colorize(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] 🔁 State changed: {desc}", color + Colors.BOLD))
                    last_state = current
        except KeyboardInterrupt:
            if not args.json:
                print(colorize("\nStopping watch mode.", Colors.CYAN))
        # FIX: return here, outside the except block, so watch always exits cleanly
        return EXIT_OK

    if args.command == "mcp":
        # Already correctly handled in original — kept as-is
        try:
            from .mcp_server import run_mcp_server
            run_mcp_server()
            return EXIT_OK
        except ImportError:
            print(colorize("Error: MCP server module not available. Install mcp extra: pip install kport[mcp]", Colors.RED), file=sys.stderr)
            return EXIT_GENERAL_ERROR
        except Exception as e:
            print(colorize(f"MCP server error: {e}", Colors.RED), file=sys.stderr)
            return EXIT_GENERAL_ERROR

    # Unrecognised subcommand — give a useful message instead of silent failure
    print(colorize(f"Error: unknown subcommand '{args.command}'", Colors.RED), file=sys.stderr)
    print("Run 'kport --help' for usage.", file=sys.stderr)
    return EXIT_INVALID_INPUT


def main(argv: Optional[List[str]] = None) -> int:
    _configure_stdio()
    parser = _QuietParser(
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
    parser.add_argument("--bypass-safety", action="store_true", help="Bypass safety shields on protected ports/processes")

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
    # FIX: default=None so config override only triggers when user didn't pass a value explicitly
    parser.add_argument("--graceful-timeout", type=float, default=None, help="Seconds to wait before force kill (default: 3.0)")
    parser.add_argument("-v", "--version", action="version", version=f"kport {__version__}")

    # FIX: pass parser_class=_QuietParser so ALL subparsers inherit quiet error formatting
    sub = parser.add_subparsers(dest="command", parser_class=_QuietParser)

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
    # FIX: default=None (consistent with top-level parser)
    sp_kill.add_argument("--graceful-timeout", type=float, default=None)
    sp_kill.add_argument("--config", type=str, default=None)
    sp_kill.add_argument("--bypass-safety", action="store_true", help="Bypass safety shields on protected ports/processes")

    sp_kp = sub.add_parser("kill-process", help="Kill processes by name")
    sp_kp.add_argument("name", type=str)
    sp_kp.add_argument("--exact", action="store_true")
    sp_kp.add_argument("--json", action="store_true")
    sp_kp.add_argument("--dry-run", action="store_true")
    sp_kp.add_argument("-y", "--yes", action="store_true")
    sp_kp.add_argument("--debug", action="store_true")
    sp_kp.add_argument("--force", action="store_true")
    # FIX: default=None (consistent with top-level parser)
    sp_kp.add_argument("--graceful-timeout", type=float, default=None)
    sp_kp.add_argument("--config", type=str, default=None)
    sp_kp.add_argument("--bypass-safety", action="store_true", help="Bypass safety shields on protected ports/processes")

    sp_list = sub.add_parser("list", help="List active ports (local + docker)")
    sp_list.add_argument("--json", action="store_true")
    sp_list.add_argument("--debug", action="store_true")
    sp_list.add_argument("--config", type=str, default=None)

    sp_docker = sub.add_parser("docker", help="List Docker-published ports")
    sp_docker.add_argument("--json", action="store_true")
    sp_docker.add_argument("--debug", action="store_true")
    sp_docker.add_argument("--config", type=str, default=None)
    sp_docker.add_argument("extra", nargs="*", help=argparse.SUPPRESS)  # absorb unknown args like 'list'

    sp_conflicts = sub.add_parser("conflicts", help="Detect docker/local port conflicts")
    sp_conflicts.add_argument("--json", action="store_true")
    sp_conflicts.add_argument("--debug", action="store_true")
    sp_conflicts.add_argument("--config", type=str, default=None)

    sp_watch = sub.add_parser("watch", help="Live monitoring of port ownership")
    sp_watch.add_argument("port", type=int)
    sp_watch.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds")
    sp_watch.add_argument("--json", action="store_true")
    sp_watch.add_argument("--debug", action="store_true")
    sp_watch.add_argument("--config", type=str, default=None)

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
            local_bindings = inspector.find_bindings_on_port(args.inspect)
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
                if not bindings:
                    pids = inspector.find_pids_by_name(pname, exact=args.exact)
                    if pids:
                        pids_str = ", ".join(map(str, pids))
                        import platform
                        is_windows = platform.system() == "Windows"
                        is_root = False
                        if not is_windows:
                            is_root = (os.geteuid() == 0) if hasattr(os, 'geteuid') else False
                        else:
                            import ctypes
                            try:
                                is_root = ctypes.windll.shell32.IsUserAnAdmin() != 0
                            except Exception:
                                pass
                        if not is_root:
                            print(colorize(f"Warning: No port bindings found matching '{pname}', but matching processes exist (PID(s): {pids_str}). Try running with sudo/admin privileges.", Colors.YELLOW), file=sys.stderr)
            else:
                print(colorize(f"\n🔍 Inspecting processes matching '{pname}'\n", Colors.CYAN + Colors.BOLD))
                if not bindings:
                    pids = inspector.find_pids_by_name(pname, exact=args.exact)
                    if pids:
                        pids_str = ", ".join(map(str, pids))
                        import platform
                        is_windows = platform.system() == "Windows"
                        is_root = False
                        if not is_windows:
                            is_root = (os.geteuid() == 0) if hasattr(os, 'geteuid') else False
                        else:
                            import ctypes
                            try:
                                is_root = ctypes.windll.shell32.IsUserAnAdmin() != 0
                            except Exception:
                                pass
                        
                        if not is_root:
                            msg = f"No port bindings found matching '{pname}', but matching processes exist (PID(s): {pids_str}). Try running with sudo/admin privileges."
                            print(colorize(f"⚠ {msg}", Colors.YELLOW))
                        else:
                            print(colorize(f"❌ Process(es) matching '{pname}' (PID(s): {pids_str}) found, but they are not listening on any ports.", Colors.RED))
                    else:
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
                # Check safety policy
                safe, safety_msg = check_safety_policy(None, pids, args, inspector)
                if not safe:
                    if args.json:
                        print(json.dumps({"name": pname, "success": False, "message": safety_msg}, indent=2))
                    else:
                        print(colorize(safety_msg, Colors.RED), file=sys.stderr)
                    return EXIT_PERMISSION
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
                            ok, msg = inspector.kill_pid(pid, graceful_timeout=_resolve_timeout(args), force=args.force, dry_run=args.dry_run)
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
                            ok, msg = inspector.kill_pid(pid, graceful_timeout=_resolve_timeout(args), force=args.force, dry_run=args.dry_run)
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

        # Kill single port (legacy)
        if args.kill:
            validate_port(args.kill)
            pids = inspector.find_pids_on_port(args.kill)

            # Check safety policy
            safe, safety_msg = check_safety_policy(args.kill, pids, args, inspector)
            if not safe:
                if args.json:
                    print(json.dumps({"port": args.kill, "success": False, "message": safety_msg}, indent=2))
                else:
                    print(colorize(safety_msg, Colors.RED), file=sys.stderr)
                return EXIT_PERMISSION

            local_bindings = inspector.find_bindings_on_port(args.kill)
            docker_hits = docker_mappings_for_host_port(args.kill, debug=args.debug)
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
                    ok, msg = inspector.kill_port(args.kill, graceful_timeout=_resolve_timeout(args), force=args.force, dry_run=args.dry_run, debug=args.debug)
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
                        ok, msg = inspector.kill_port(args.kill, graceful_timeout=_resolve_timeout(args), force=args.force, dry_run=args.dry_run, debug=args.debug)
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
            # Safety shield check
            for port in args.kill_all:
                pids = inspector.find_pids_on_port(port)
                safe, safety_msg = check_safety_policy(port, pids, args, inspector)
                if not safe:
                    print(colorize(f"Port {port} failed safety check: {safety_msg}", Colors.RED), file=sys.stderr)
                    return EXIT_PERMISSION
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
                        ok, msg = inspector.kill_port(port, graceful_timeout=_resolve_timeout(args), force=args.force, dry_run=args.dry_run, debug=args.debug)
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
            # Safety shield check
            for port in ports:
                pids = inspector.find_pids_on_port(port)
                safe, safety_msg = check_safety_policy(port, pids, args, inspector)
                if not safe:
                    print(colorize(f"Port {port} failed safety check: {safety_msg}", Colors.RED), file=sys.stderr)
                    return EXIT_PERMISSION
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
                        ok, msg = inspector.kill_port(port, graceful_timeout=_resolve_timeout(args), force=args.force, dry_run=args.dry_run, debug=args.debug)
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

    # Catch custom domain exceptions cleanly
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
        print("\nOperation cancelled by user.")
        return EXIT_GENERAL_ERROR
    except Exception as e:
        print(colorize(f"Unexpected error: {e}", Colors.RED), file=sys.stderr)
        return EXIT_GENERAL_ERROR

    return EXIT_OK


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)