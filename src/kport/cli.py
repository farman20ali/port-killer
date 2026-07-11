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
from .inspectors import get_inspector, BaseInspector
from .constants import PROTECTED_PORTS, PROTECTED_PROCESS_NAMES
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
    print_table_list_product
)
from .profile import load_profiles, resolve_profile
from .notify import notify as _desktop_notify
from . import audit

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
        print("Run 'kport --help' for usage.", file=sys.stderr)
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


# Default safety policies — imported from constants to share with MCP server.
# These are used as the starting baseline; config can only ADD to these, never replace.
DEFAULT_PROTECTED_PORTS = PROTECTED_PORTS
DEFAULT_PROTECTED_PROCESS_NAMES = PROTECTED_PROCESS_NAMES


def check_safety_policy(port: Optional[int], pids: List[int], args: argparse.Namespace, inspector: BaseInspector) -> Tuple[bool, str]:
    """
    Check if a port or any associated PIDs are protected by safety policies.
    Returns (True, "") if safety policy permits, or (False, error_msg) if blocked.
    """
    bypass = getattr(args, "bypass_safety", False)

    # R16 fix: config overrides are ADDITIVE, not replacements.
    # A user setting protected_ports:[8080] should ADD to the defaults,
    # not silently unprotect SSH (22), Redis (6379), etc.
    protected_ports = set(DEFAULT_PROTECTED_PORTS)
    config_ports = getattr(args, "protected_ports", None)
    if isinstance(config_ports, list):
        protected_ports.update(config_ports)  # additive

    protected_procs = set(DEFAULT_PROTECTED_PROCESS_NAMES)
    config_procs = getattr(args, "protected_processes", None)
    if isinstance(config_procs, list):
        protected_procs.update(p.lower() for p in config_procs)  # additive

    # Check Port protection
    if port is not None and port in protected_ports:
        if bypass:
            debug_log(getattr(args, "debug", False), f"Safety shield bypassed for protected port {port}")
        else:
            return False, f"Security Shield Active: Port {port} is a protected port. Action aborted. Use --bypass-safety to override."

    # Check Process protection
    for pid in pids:
        try:
            info = inspector.get_process_info(pid)
            if info and info.name.lower().split(" (")[0] in protected_procs:
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


def confirm_docker_rm(container_name: str, container_id: str, assume_yes: bool, force: bool) -> bool:
    """
    Hard confirmation gate for docker rm.
    Returns True if confirmed/allowed, False otherwise.
    """
    if assume_yes:
        if force:
            return True
        print(colorize("Error: Removing a Docker container is irreversible. Use --force in addition to --yes to bypass interactive confirmation.", Colors.RED), file=sys.stderr)
        return False

    print(colorize(f"\n⚠️  WARNING: You are about to permanently destroy container '{container_name}' ({container_id[:12]}).", Colors.YELLOW + Colors.BOLD))
    print(colorize("This action is irreversible and any non-persistent data will be lost.", Colors.YELLOW))
    try:
        expected = container_name
        user_input = input(colorize(f"To confirm, type the container name '{expected}': ", Colors.MAGENTA)).strip()
        if user_input == expected or user_input == container_id or user_input == container_id[:12]:
            return True
        print(colorize("Aborted: Confirmation input did not match.", Colors.RED))
        return False
    except KeyboardInterrupt:
        print()
        raise


def _is_elevated() -> bool:
    """P1 fix: detect if the current process is running with root/admin privileges."""
    if sys.platform == "win32":
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    return (os.geteuid() == 0) if hasattr(os, 'geteuid') else False


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


JSON_SCHEMA_VERSION = 1


def _json_out(command: str, data: dict) -> str:
    """Return a stable, versioned JSON envelope for --json output.

    Schema:  {"schema_version": 1, "command": "<subcommand>", "data": {...}}
    All --json outputs pass through here so downstream scripts can key on
    schema_version to detect breaking changes.
    """
    return json.dumps({"schema_version": JSON_SCHEMA_VERSION, "command": command, "data": data}, indent=2)


def _resolve_ports_for_args(args: argparse.Namespace) -> List[int]:
    """Helper to resolve a list of ports for the command, supporting --profile."""
    profile_name = getattr(args, "profile", None)
    if profile_name:
        cfg = load_config(getattr(args, "config", None), debug=getattr(args, "debug", False))
        profiles = load_profiles(cfg)
        resolved = resolve_profile(profile_name, profiles)
        if resolved is None:
            raise KPortError(f"Profile '{profile_name}' not found in configuration")
        return resolved

    port = getattr(args, "port", None)
    if port is not None:
        return [port]
    return []


def handle_product_command(args: argparse.Namespace, inspector: BaseInspector) -> int:
    """Implement subcommands defined in the product specification."""
    debug = bool(getattr(args, "debug", False))

    if args.command == "docker":
        extra = getattr(args, "extra", [])
        if extra:
            print(colorize(f"Note: 'kport docker' has no subcommands. Ignoring: {' '.join(extra)}", Colors.YELLOW), file=sys.stderr)
        maps = list_docker_mappings(debug=debug)
        if args.json:
            print(_json_out("docker", [asdict(m) for m in maps]))
        else:
            print_table_docker(maps)
        return EXIT_OK

    if args.command == "list":
        local = inspector.list_listening()
        docker_maps = list_docker_mappings(debug=debug)
        if args.json:
            print(_json_out("list", {"local": [asdict(b) for b in local], "docker": [asdict(m) for m in docker_maps]}))
        else:
            print_table_list_product(local, docker_maps)
        return EXIT_OK

    if args.command == "inspect":
        ports = _resolve_ports_for_args(args)
        if not ports:
            print(colorize("Error: inspect requires a port or a --profile", Colors.RED), file=sys.stderr)
            return EXIT_INVALID_INPUT

        results = []
        exit_code = EXIT_PORT_FREE
        for port in ports:
            validate_port(port)
            local_bindings = inspector.find_bindings_on_port(port)
            docker_hits = docker_mappings_for_host_port(port, debug=debug)
            pids = inspector.find_pids_on_port(port)

            if docker_hits:
                m = docker_hits[0]
                payload = {
                    "port": port,
                    "type": "docker",
                    "container": m.container_name,
                    "image": m.image,
                    "host_port": m.host_port,
                    "container_port": m.container_port,
                    "status": m.status,
                }
                results.append(payload)
                if not args.json:
                    print(colorize(f"Port: {port}", Colors.CYAN + Colors.BOLD))
                    print("Type: Docker Container")
                    print(f"Container: {m.container_name}")
                    print(f"Image: {m.image}")
                    print(f"Host Port: {m.host_port}")
                    print(f"Container Port: {m.container_port}")
                    print(f"Status: {m.status}")
                    print()
                exit_code = EXIT_PORT_DOCKER
            elif not pids and not local_bindings:
                payload = {"port": port, "type": "free"}
                results.append(payload)
                if not args.json:
                    print(colorize(f"Port {port} is free", Colors.GREEN))
                    print()
            elif not pids and local_bindings:
                msg = "Port is in use, but the owning PID is not visible (try running with sudo/admin)."
                payload = {"port": port, "type": "local-unknown", "message": msg, "bindings": [asdict(b) for b in local_bindings]}
                results.append(payload)
                if not args.json:
                    print(colorize(f"Port: {port}", Colors.CYAN + Colors.BOLD))
                    print("Type: Local Process")
                    print(colorize(msg, Colors.YELLOW))
                    print()
                if exit_code not in (EXIT_PORT_DOCKER, EXIT_OK):
                    exit_code = EXIT_OK
            else:
                info_list = []
                for pid in pids:
                    info = inspector.get_process_info(pid)
                    info_list.append({"pid": pid, "process": asdict(info) if info else None})
                payload = {"port": port, "type": "local", "pids": info_list}
                results.append(payload)
                if not args.json:
                    print(colorize(f"Port: {port}", Colors.CYAN + Colors.BOLD))
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
                    print()
                if exit_code != EXIT_PORT_DOCKER:
                    exit_code = EXIT_OK

        if args.json:
            if len(ports) == 1:
                print(_json_out("inspect", results[0]))
            else:
                print(_json_out("inspect", {"ports": results}))
        return exit_code

    if args.command == "explain":
        validate_port(args.port)
        local_bindings = inspector.find_bindings_on_port(args.port)
        docker_hits = docker_mappings_for_host_port(args.port, debug=debug)
        if docker_hits:
            m = docker_hits[0]
            if args.json:
                print(_json_out("explain", {
                    "port": args.port,
                    "blocked": True,
                    "because": [
                        f"It is mapped to Docker container '{m.container_name}'",
                        f"Docker maps host port {m.host_port} \u2192 container port {m.container_port}",
                        "The process runs inside an isolated network namespace",
                    ],
                    "suggested_actions": [
                        {"action": "docker_stop", "port": args.port,
                         "container": m.container_name,
                         "requires_confirmation": True, "safe": True,
                         "command": f"kport kill {args.port} --docker-action stop --yes"},
                        {"action": "docker_restart", "port": args.port,
                         "container": m.container_name,
                         "requires_confirmation": True, "safe": True,
                         "command": f"kport kill {args.port} --docker-action restart --yes"},
                    ],
                }))
            else:
                print(colorize(f"Port {args.port} is unavailable because:", Colors.YELLOW + Colors.BOLD))
                print(f"- It is mapped to Docker container \"{m.container_name}\"")
                print(f"- Docker maps host port {m.host_port} → container port {m.container_port}")
                print("- The process runs inside an isolated network namespace")
            return EXIT_PORT_DOCKER

        pids = inspector.find_pids_on_port(args.port)
        if not pids and not local_bindings:
            if args.json:
                print(_json_out("explain", {
                    "port": args.port,
                    "blocked": False,
                    "suggested_actions": [
                        {"action": "bind", "port": args.port,
                         "requires_confirmation": False, "safe": True,
                         "note": "Port is free — safe to bind"},
                    ],
                }))
            else:
                print(colorize(f"Port {args.port} is free", Colors.GREEN))
            return EXIT_PORT_FREE

        if not pids and local_bindings:
            if args.json:
                print(_json_out("explain", {
                    "port": args.port,
                    "blocked": True,
                    "type": "local-unknown",
                    "message": "Owning PID not visible (try sudo/admin)",
                    "bindings": [asdict(b) for b in local_bindings],
                    "suggested_actions": [
                        {"action": "rerun_as_admin", "port": args.port,
                         "requires_confirmation": False, "safe": True,
                         "note": "Re-run kport with administrator/sudo privileges to see the owning PID"},
                    ],
                }))
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

        # Build safe suggested_actions (protected-port-aware)
        safe_kill = not any(
            p in DEFAULT_PROTECTED_PORTS for p in [args.port]
        ) and not any(
            (inspector.get_process_info(p) and
             inspector.get_process_info(p).name.lower().split(" (")[0] in DEFAULT_PROTECTED_PROCESS_NAMES)
            for p in pids
        )
        if args.json:
            print(_json_out("explain", {
                "port": args.port,
                "blocked": True,
                "type": "local",
                "pids": infos,
                "suggested_actions": [
                    {
                        "action": "kill",
                        "port": args.port,
                        "requires_confirmation": True,
                        "safe": safe_kill,
                        "command": f"kport kill {args.port} --yes",
                        "note": None if safe_kill else "Port or process is protected — pass --bypass-safety to override",
                    },
                    {
                        "action": "dry_run",
                        "port": args.port,
                        "requires_confirmation": False,
                        "safe": True,
                        "command": f"kport kill {args.port} --dry-run --json",
                        "note": "Preview what would happen without executing",
                    },
                ],
            }))
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
        ports = _resolve_ports_for_args(args)
        if not ports:
            print(colorize("Error: kill requires a port or a --profile", Colors.RED), file=sys.stderr)
            return EXIT_INVALID_INPUT

        # For text output, confirm once if not yes
        if not args.json and not args.yes:
            # We want to confirm proceeding with the action plan for all ports.
            pids_to_kill_all = []
            docker_hits_all = []
            for port in ports:
                pids = inspector.find_pids_on_port(port)
                pids_to_kill_all.extend(pids)
                dh = docker_mappings_for_host_port(port, debug=debug)
                if dh:
                    docker_hits_all.append(dh[0])
            
            # Print Action Plan
            print(colorize("Action plan:", Colors.CYAN))
            if pids_to_kill_all:
                print(colorize(f"1. Terminate local PIDs: {', '.join(map(str, set(pids_to_kill_all)))}", Colors.CYAN))
            if docker_hits_all:
                action = getattr(args, "docker_action", None) or "stop"
                containers_str = ", ".join(m.container_name for m in docker_hits_all)
                print(colorize(f"2. Perform Docker action '{action}' on containers: {containers_str}", Colors.CYAN))
            
            if not confirm_prompt("Proceed?", assume_yes=args.yes):
                print(colorize("Operation cancelled.", Colors.YELLOW))
                return EXIT_GENERAL_ERROR

        results = []
        overall_ok = True
        exit_codes = []
        for port in ports:
            validate_port(port)
            pids = inspector.find_pids_on_port(port)

            # Check safety policy
            safe, safety_msg = check_safety_policy(port, pids, args, inspector)
            if not safe:
                if args.json:
                    results.append({"port": port, "success": False, "message": safety_msg})
                else:
                    print(colorize(f"Port {port}: {safety_msg}", Colors.RED), file=sys.stderr)
                overall_ok = False
                exit_codes.append(EXIT_PERMISSION)
                continue

            local_bindings = inspector.find_bindings_on_port(port)
            docker_hits = docker_mappings_for_host_port(port, debug=debug)
            if docker_hits:
                m = docker_hits[0]
                action = getattr(args, "docker_action", None)
                if not action and not args.json:
                    print(colorize(f"Port {port} belongs to Docker container: {m.container_name}", Colors.YELLOW + Colors.BOLD))
                    action = choose_docker_action(assume_yes=args.yes)
                if not action:
                    if args.json:
                        results.append({
                            "port": port,
                            "type": "docker",
                            "container": m.container_name,
                            "container_id": m.container_id,
                            "available_actions": ["stop", "restart", "rm"],
                            "performed": None,
                            "message": "No action selected",
                        })
                    else:
                        print(colorize("Operation cancelled.", Colors.YELLOW))
                    overall_ok = False
                    exit_codes.append(EXIT_GENERAL_ERROR)
                    continue

                if args.json and not args.yes and not args.dry_run:
                    results.append({
                        "port": port,
                        "type": "docker",
                        "container": m.container_name,
                        "container_id": m.container_id,
                        "requested_action": action,
                        "performed": False,
                        "message": "Refusing to act without --yes in JSON mode",
                    })
                    overall_ok = False
                    exit_codes.append(EXIT_GENERAL_ERROR)
                    continue

                if action == "rm" and not args.dry_run:
                    if not confirm_docker_rm(m.container_name, m.container_id, assume_yes=args.yes, force=args.force):
                        if args.json:
                            results.append({
                                "port": port,
                                "type": "docker",
                                "container": m.container_name,
                                "container_id": m.container_id,
                                "action": "rm",
                                "ok": False,
                                "message": "Removing a Docker container is irreversible. Use --force in addition to --yes to bypass interactive confirmation."
                            })
                        overall_ok = False
                        exit_codes.append(EXIT_PERMISSION)
                        continue

                ok, msg = docker_action_on_container(m.container_id, action=action, dry_run=args.dry_run, debug=debug)
                # Audit log for docker action
                audit.log_docker_action(
                    m.container_id, m.container_name, action,
                    dry_run=args.dry_run, success=ok, message=msg
                )
                if args.json:
                    results.append({
                        "port": port,
                        "type": "docker",
                        "container": m.container_name,
                        "container_id": m.container_id,
                        "action": action,
                        "ok": ok,
                        "message": msg,
                    })
                else:
                    if ok:
                        print(colorize(f"✓ Port {port}: {msg}", Colors.GREEN))
                    else:
                        print(colorize(f"✗ Port {port}: {msg}", Colors.RED))
                if not ok:
                    overall_ok = False
                exit_codes.append(EXIT_OK if ok else EXIT_GENERAL_ERROR)
                continue

            # Local process kill
            if not pids and not local_bindings:
                if args.json:
                    results.append({"port": port, "killed": [], "failed": [], "message": "Port free"})
                else:
                    print(colorize(f"Port {port} is free", Colors.GREEN))
                exit_codes.append(EXIT_PORT_FREE)
                continue

            if not pids and local_bindings:
                msg = "Port is in use but PID is not visible; cannot kill safely without PID. Try sudo/admin."
                if args.json:
                    results.append({"port": port, "ok": False, "message": msg, "bindings": [asdict(b) for b in local_bindings]})
                else:
                    print(colorize(f"Port {port}: {msg}", Colors.RED))
                overall_ok = False
                exit_codes.append(EXIT_PERMISSION)
                continue

            ok, msg = inspector.kill_port(
                port,
                graceful_timeout=_resolve_timeout(args),
                force=args.force,
                dry_run=args.dry_run,
                debug=debug,
                assume_yes=args.yes
            )

            # Audit log
            audit.log_kill_port(
                port, pids,
                dry_run=args.dry_run, success=ok, message=msg
            )

            if args.json:
                results.append({
                    "port": port,
                    "success": ok,
                    "message": msg,
                    "pids_targeted": pids,
                    "dry_run": args.dry_run,
                })
            else:
                if ok:
                    print(colorize(f"✓ Port {port}: {msg}", Colors.GREEN))
                else:
                    print(colorize(f"✗ Port {port}: {msg}", Colors.RED))
            if not ok:
                overall_ok = False
            exit_codes.append(EXIT_OK if ok else EXIT_GENERAL_ERROR)

        if args.json:
            if len(ports) == 1:
                print(_json_out("kill", results[0]))
            else:
                print(_json_out("kill", {"ports": results}))

        if len(ports) == 1:
            return exit_codes[0]
        return EXIT_OK if overall_ok else EXIT_GENERAL_ERROR

    if args.command == "kill-process":
        pname = args.name
        pids = inspector.find_pids_by_name(pname, exact=args.exact)
        if not pids:
            if args.json:
                print(_json_out("kill-process", {"name": pname, "pids": []}))
            else:
                print(colorize(f"✗ No processes found matching '{pname}'", Colors.RED))
            return EXIT_OK

        # Check safety policy
        safe, safety_msg = check_safety_policy(None, pids, args, inspector)
        if not safe:
            if args.json:
                print(_json_out("kill-process", {"name": pname, "success": False, "message": safety_msg}))
            else:
                print(colorize(safety_msg, Colors.RED), file=sys.stderr)
            return EXIT_PERMISSION

        if not args.json and not confirm_prompt(f"Proceed to terminate {len(pids)} process(es)?", assume_yes=args.yes):
            print(colorize("Operation cancelled.", Colors.YELLOW))
            return EXIT_GENERAL_ERROR

        killed = []
        failed = []
        for pid in pids:
            ok, msg = inspector.kill_pid(pid, graceful_timeout=_resolve_timeout(args), force=args.force, dry_run=args.dry_run, assume_yes=args.yes)
            
            # Audit log
            audit.log_kill_pid(
                pid, pname,
                dry_run=args.dry_run, success=ok, message=msg
            )
            
            if ok:
                killed.append({"pid": pid, "msg": msg})
            else:
                failed.append({"pid": pid, "msg": msg})

        if args.json:
            print(_json_out("kill-process", {"killed": killed, "failed": failed}))
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
            print(_json_out("conflicts", conflicts))
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
        ports_to_watch: List[int] = []
        # Support both single port (positional) and --ports / --range
        single = getattr(args, "port", None)
        multi  = getattr(args, "ports", None)
        rng    = getattr(args, "range", None)
        if multi:
            for p in multi:
                validate_port(p)
                ports_to_watch.append(p)
        elif rng:
            ports_to_watch = parse_port_range(rng)
        elif single is not None:
            validate_port(single)
            ports_to_watch = [single]
        else:
            print(colorize("Error: watch requires a port, --ports, or --range", Colors.RED), file=sys.stderr)
            return EXIT_INVALID_INPUT

        interval    = getattr(args, "interval", 1.0)
        do_notify   = getattr(args, "notify", False)

        import time
        from datetime import datetime

        # Per-port state tracking
        states: Dict[int, Dict[str, Any]] = {}

        def get_port_state(port: int) -> Dict[str, Any]:
            local_bindings = inspector.find_bindings_on_port(port)
            docker_hits = docker_mappings_for_host_port(port, debug=debug)
            pids = inspector.find_pids_on_port(port)

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
                return {"type": "local", "pids": pids, "processes": procs}
            elif local_bindings:
                return {"type": "local-unknown", "message": "Owning PID not visible"}
            else:
                return {"type": "free"}

        def describe_state(port: int, state: Dict[str, Any]) -> str:
            stype = state["type"]
            if stype == "free":
                return f"port {port}: FREE"
            elif stype == "docker":
                return (f"port {port}: DOCKER '{state['container']}' "
                        f"({state['image']}, status={state['status']})")
            elif stype == "local":
                procs_str = ", ".join(
                    f"{name} (PID {pid})"
                    for pid, name in zip(state["pids"], state["processes"])
                )
                return f"port {port}: LOCAL {procs_str}"
            elif stype == "local-unknown":
                return f"port {port}: LOCAL (PID hidden)"
            return f"port {port}: UNKNOWN"

        def _states_differ(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
            """P6 fix: compare full state including process names, not just PIDs."""
            if a["type"] != b["type"]:
                return True
            if a["type"] == "docker":
                return (
                    a["container"] != b.get("container")
                    or a["status"] != b.get("status")
                )
            if a["type"] == "local":
                return (
                    set(a["pids"]) != set(b.get("pids", []))
                    or sorted(a["processes"]) != sorted(b.get("processes", []))
                )
            return False

        # Initialise state for each watched port
        for port in ports_to_watch:
            st = get_port_state(port)
            states[port] = st
            if args.json:
                st_out = dict(st)
                st_out["port"] = port
                st_out["timestamp"] = datetime.now().isoformat()
                print(json.dumps(st_out))
                sys.stdout.flush()
            else:
                desc = describe_state(port, st)
                print(colorize(
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Initial: {desc}",
                    Colors.WHITE
                ))

        if not args.json:
            ports_str = ", ".join(str(p) for p in ports_to_watch)
            print(colorize(
                f"\n\U0001f440 Watching port(s) {ports_str} (interval={interval}s). "
                "Press Ctrl+C to stop.",
                Colors.CYAN + Colors.BOLD
            ))

        try:
            while True:
                time.sleep(interval)
                for port in ports_to_watch:
                    current = get_port_state(port)
                    last = states[port]

                    if _states_differ(current, last):
                        ts = datetime.now()
                        states[port] = current
                        desc = describe_state(port, current)

                        if args.json:
                            out = dict(current)
                            out["port"] = port
                            out["timestamp"] = ts.isoformat()
                            print(json.dumps(out))
                            sys.stdout.flush()
                        else:
                            color = Colors.GREEN if current["type"] == "free" else Colors.YELLOW
                            print(colorize(
                                f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] \U0001f501 {desc}",
                                color + Colors.BOLD
                            ))

                        if do_notify:
                            _desktop_notify(
                                "kport — port state change",
                                desc,
                            )
        except KeyboardInterrupt:
            if not args.json:
                print(colorize("\nStopping watch mode.", Colors.CYAN))
        return EXIT_OK

    if args.command == "mcp":
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

    if args.command == "completion":
        shell = getattr(args, "shell", None) or "bash"
        _print_completion(shell)
        return EXIT_OK

    # Unrecognised subcommand — give a useful message instead of silent failure
    print(colorize(f"Error: unknown subcommand '{args.command}'", Colors.RED), file=sys.stderr)
    print("Run 'kport --help' for usage.", file=sys.stderr)
    return EXIT_INVALID_INPUT


def _print_completion(shell: str) -> None:
    if shell == "bash":
        print("""# bash completion for kport
_kport_completion() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    opts="inspect explain kill kill-process list docker conflicts watch mcp completion --json --dry-run --yes --debug --config --bypass-safety --version"
    case "${prev}" in
        inspect|explain|watch|kill)
            return 0
            ;;
        kill-process|--inspect-process|-ip|-kp)
            return 0
            ;;
        *)
            ;;
    esac
    COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    return 0
}
complete -F _kport_completion kport
""")
    elif shell == "zsh":
        print("""# zsh completion for kport
#compdef kport

_kport() {
    local line
    _arguments -C \\
        '--json[Output machine-readable JSON]' \\
        '--dry-run[Show actions without executing]' \\
        '(-y --yes)'{-y,--yes}'[Skip confirmation prompts]' \\
        '--debug[Verbose internal logs]' \\
        '--config[Path to JSON config file]' \\
        '--bypass-safety[Bypass safety shields on protected ports/processes]' \\
        '(-v --version)'{-v,--version}'[Show version]' \\
        '1: :->cmds' \\
        '*:: :->args'

    case $state in
        cmds)
            _values "subcommand" \\
                'inspect[Inspect a port (docker-aware)]' \\
                'explain[Explain why a port is blocked]' \\
                'kill[Safely free a port (docker-aware)]' \\
                'kill-process[Kill processes by name]' \\
                'list[List active ports (local + docker)]' \\
                'docker[List Docker-published ports]' \\
                'conflicts[Detect docker/local port conflicts]' \\
                'watch[Live monitoring of port ownership]' \\
                'mcp[Start the stdio Model Context Protocol (MCP) server]' \\
                'completion[Generate shell autocompletion]'
            ;;
    esac
}
""")
    elif shell == "fish":
        print("""# fish completion for kport
complete -c kport -f
complete -c kport -a "inspect explain kill kill-process list docker conflicts watch mcp completion"
complete -c kport -s y -l yes -d "Skip confirmation prompts"
complete -c kport -l json -d "Output machine-readable JSON"
complete -c kport -l dry-run -d "Show actions without executing"
complete -c kport -l debug -d "Verbose internal logs"
complete -c kport -l config -d "Path to JSON config file"
complete -c kport -l bypass-safety -d "Bypass safety shields on protected ports/processes"
complete -c kport -s v -l version -d "Show version"
""")
    elif shell == "powershell":
        print("""# powershell completion for kport
Register-ArgumentCompleter -Native -CommandName kport -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    $opts = @('inspect', 'explain', 'kill', 'kill-process', 'list', 'docker', 'conflicts', 'watch', 'mcp', 'completion', '--json', '--dry-run', '--yes', '--debug', '--config', '--bypass-safety', '--version')
    $opts | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
        [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
    }
}
""")
    else:
        print(f"Error: unsupported shell '{shell}'", file=sys.stderr)


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
    parser.add_argument("--mcp", action="store_true",
                        help="Start the MCP JSON-RPC server on stdio (alias for 'kport mcp')")

    # FIX: pass parser_class=_QuietParser so ALL subparsers inherit quiet error formatting
    sub = parser.add_subparsers(dest="command", parser_class=_QuietParser)

    # Common arguments parser to share among all subparsers
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parent_parser.add_argument("--dry-run", action="store_true", help="Show actions without executing")
    parent_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompts")
    parent_parser.add_argument("--debug", action="store_true", help="Verbose internal logs")
    parent_parser.add_argument("--config", type=str, default=None, help="Path to JSON config file")
    parent_parser.add_argument("--bypass-safety", action="store_true", help="Bypass safety shields on protected ports/processes")

    sp_inspect = sub.add_parser("inspect", parents=[parent_parser], help="Inspect a port (docker-aware)")
    sp_inspect.add_argument("port", type=int, nargs="?")
    sp_inspect.add_argument("--profile", type=str, help="Named port profile from config")

    sp_explain = sub.add_parser("explain", parents=[parent_parser], help="Explain why a port is blocked")
    sp_explain.add_argument("port", type=int)

    sp_kill = sub.add_parser("kill", parents=[parent_parser], help="Safely free a port (docker-aware)")
    sp_kill.add_argument("port", type=int, nargs="?")
    sp_kill.add_argument("--profile", type=str, help="Named port profile from config")
    sp_kill.add_argument("--docker-action", choices=["stop", "restart", "rm"], help="Action when port belongs to Docker")
    sp_kill.add_argument("--force", action="store_true")
    # FIX: default=None (consistent with top-level parser)
    sp_kill.add_argument("--graceful-timeout", type=float, default=None)

    sp_kp = sub.add_parser("kill-process", parents=[parent_parser], help="Kill processes by name")
    sp_kp.add_argument("name", type=str)
    sp_kp.add_argument("--exact", action="store_true")
    sp_kp.add_argument("--force", action="store_true")
    # FIX: default=None (consistent with top-level parser)
    sp_kp.add_argument("--graceful-timeout", type=float, default=None)

    _sp_list = sub.add_parser("list", parents=[parent_parser], help="List active ports (local + docker)")

    sp_docker = sub.add_parser("docker", parents=[parent_parser], help="List Docker-published ports")
    sp_docker.add_argument("extra", nargs="*", help=argparse.SUPPRESS)  # absorb unknown args like 'list'

    _sp_conflicts = sub.add_parser("conflicts", parents=[parent_parser], help="Detect docker/local port conflicts")

    sp_watch = sub.add_parser("watch", parents=[parent_parser], help="Live monitoring of port ownership")
    sp_watch.add_argument("port", type=int, nargs="?")
    sp_watch.add_argument("--ports", type=int, nargs="+", help="Multiple ports to watch")
    sp_watch.add_argument("--range", type=str, help="Range of ports to watch (e.g. 3000-3010)")
    sp_watch.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds")
    sp_watch.add_argument("--notify", action="store_true", help="Send OS desktop notification on state change")

    sub.add_parser("mcp", parents=[parent_parser], help="Start the stdio Model Context Protocol (MCP) server")
    
    sp_completion = sub.add_parser("completion", parents=[parent_parser], help="Generate shell autocompletion scripts")
    sp_completion.add_argument("shell", choices=["bash", "zsh", "fish", "powershell"], help="Target shell")

    args = parser.parse_args(argv)

    if getattr(args, "mcp", False):
        try:
            from .mcp_server import run_mcp_server
            run_mcp_server()
            return EXIT_OK
        except ImportError:
            print(colorize("Error: MCP server module not available.", Colors.RED), file=sys.stderr)
            return EXIT_GENERAL_ERROR
        except Exception as e:
            print(colorize(f"MCP server error: {e}", Colors.RED), file=sys.stderr)
            return EXIT_GENERAL_ERROR

    # Load configuration
    cfg = load_config(getattr(args, "config", None), debug=getattr(args, "debug", False))
    apply_config_defaults(args, cfg)

    inspector = get_inspector()

    try:
        # 1. Product subcommands routing
        if getattr(args, "command", None):
            return handle_product_command(args, inspector)

        # Show help if no action requested
        if not any([
            args.inspect is not None, args.inspect_multiple, args.inspect_range,
            args.inspect_process, args.kill is not None, args.list,
            args.kill_process, args.kill_all, args.kill_range,
        ]):
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
        if args.inspect is not None:  # C6: use is not None, not truthiness
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
                        if not _is_elevated():  # P1: use shared helper
                            print(colorize(f"Warning: No port bindings found matching '{pname}', but matching processes exist (PID(s): {pids_str}). Try running with sudo/admin privileges.", Colors.YELLOW), file=sys.stderr)
            else:
                print(colorize(f"\n🔍 Inspecting processes matching '{pname}'\n", Colors.CYAN + Colors.BOLD))
                if not bindings:
                    pids = inspector.find_pids_by_name(pname, exact=args.exact)
                    if pids:
                        pids_str = ", ".join(map(str, pids))
                        if not _is_elevated():  # P1: use shared helper
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
                            print(f"{'':8} {'':25} {p.port:<8} {p.state or '-':<12}")
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
                    if not args.yes:
                        out = []
                        for pid in pids:
                            info = inspector.get_process_info(pid)
                            out.append({"pid": pid, "process": asdict(info) if info else None})
                        print(json.dumps({
                            "name": pname,
                            "pids": out,
                            "message": "Note: Use --yes to actually perform kills."
                        }, indent=2))
                    else:
                        killed = []
                        failed = []
                        for pid in pids:
                            ok, msg = inspector.kill_pid(pid, graceful_timeout=_resolve_timeout(args), force=args.force, dry_run=args.dry_run, assume_yes=args.yes)
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
                            ok, msg = inspector.kill_pid(pid, graceful_timeout=_resolve_timeout(args), force=args.force, dry_run=args.dry_run, assume_yes=args.yes)
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
        if args.kill is not None:  # C6: use is not None, not truthiness
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
                        if action == "rm" and not args.dry_run:
                            if not confirm_docker_rm(m.container_name, m.container_id, assume_yes=args.yes, force=args.force):
                                if args.json:
                                    print(json.dumps({
                                        "port": args.kill,
                                        "type": "docker",
                                        "container": m.container_name,
                                        "container_id": m.container_id,
                                        "action": "rm",
                                        "ok": False,
                                        "message": "Removing a Docker container is irreversible. Use --force in addition to --yes to bypass interactive confirmation."
                                    }, indent=2))
                                return EXIT_PERMISSION

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
                    ok, msg = inspector.kill_port(args.kill, graceful_timeout=_resolve_timeout(args), force=args.force, dry_run=args.dry_run, debug=args.debug, assume_yes=args.yes)
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
                        ok, msg = inspector.kill_port(args.kill, graceful_timeout=_resolve_timeout(args), force=args.force, dry_run=args.dry_run, debug=args.debug, assume_yes=args.yes)
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
                        ok, msg = inspector.kill_port(port, graceful_timeout=_resolve_timeout(args), force=args.force, dry_run=args.dry_run, debug=args.debug, assume_yes=args.yes)
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
                        ok, msg = inspector.kill_port(port, graceful_timeout=_resolve_timeout(args), force=args.force, dry_run=args.dry_run, debug=args.debug, assume_yes=args.yes)
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