"""
Terminal formatting and output representation module for kport.
Decouples UI and CLI layout generation from networking core logic.
"""

import json
import platform
import os
import sys
from typing import List, Dict, Any, Optional
from dataclasses import asdict

class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def colorize(text: str, color: str) -> str:
    """Colorize text for terminal output, handling Windows console compatibility."""
    if platform.system() == "Windows":
        try:
            os.system("")  # Enable ANSI escape processing in modern Windows terminals
        except Exception:
            pass
    return f"{color}{text}{Colors.RESET}"


def print_table_listen(bindings: List[Any]) -> None:
    """Print standard tabular listing of local listening ports."""
    if not bindings:
        print(colorize("No listening ports found.", Colors.YELLOW))
        return
    print(colorize(f"{'Port':<8} {'PID':<8} {'Process':<25} {'State':<12} {'Address':<25}", Colors.BOLD))
    print("─" * 80)
    for b in bindings:
        pid = str(b.pid) if b.pid is not None else "-"
        pname = b.process_name or "-"
        state = b.state or "-"
        print(f"{colorize(str(b.port), Colors.CYAN):<8} {pid:<8} {pname:<25} {state:<12} {b.laddr:<25}")


def jsonify_bindings(bindings: List[Any]) -> str:
    """Render list of PortBindings as JSON string."""
    return json.dumps([asdict(b) for b in bindings], indent=2)


def confirm_prompt(prompt: str, assume_yes: bool = False) -> bool:
    """Show an interactive yes/no confirmation prompt to the user."""
    if assume_yes:
        return True
    try:
        resp = input(colorize(prompt + " (y/N): ", Colors.MAGENTA))
        return resp.strip().lower() in ("y", "yes")
    except KeyboardInterrupt:
        print(colorize("\nOperation cancelled.", Colors.YELLOW))
        sys.exit(1)


def choose_docker_action(assume_yes: bool) -> Optional[str]:
    """Interactive Docker action selector."""
    if assume_yes:
        return "stop"
    print(colorize("\nChoose action:\n1) Stop container\n2) Restart container\n3) Remove container\n4) Cancel", Colors.CYAN))
    try:
        resp = input(colorize("Select (1-4): ", Colors.MAGENTA)).strip()
    except KeyboardInterrupt:
        print(colorize("\nOperation cancelled.", Colors.YELLOW))
        return None
    mapping = {"1": "stop", "2": "restart", "3": "rm", "4": None}
    return mapping.get(resp)


def print_table_docker(mappings: List[Any]) -> None:
    """Print tabular details of Docker mapped ports."""
    if not mappings:
        print(colorize("No Docker-published ports found.", Colors.YELLOW))
        return
    print(colorize(f"{'PORT':<8} {'CONTAINER':<20} {'IMAGE':<25} {'STATUS':<20}", Colors.BOLD))
    print("─" * 80)
    for m in mappings:
        print(f"{colorize(str(m.host_port), Colors.CYAN):<8} {m.container_name:<20} {m.image:<25} {m.status:<20}")


def print_table_list_product(local_bindings: List[Any], docker_maps: List[Any]) -> None:
    """Print unified list output representing PORT, TYPE, and OWNER."""
    rows: Dict[int, Dict[str, Any]] = {}
    for b in local_bindings:
        rows.setdefault(b.port, {})
        rows[b.port]["local"] = b
    for d in docker_maps:
        rows.setdefault(d.host_port, {})
        rows[d.host_port]["docker"] = d

    if not rows:
        print(colorize("No active ports found.", Colors.YELLOW))
        return
    print(colorize(f"{'PORT':<8} {'TYPE':<10} {'OWNER':<25}", Colors.BOLD))
    print("─" * 55)
    for port in sorted(rows.keys()):
        if "docker" in rows[port] and "local" in rows[port]:
            owner = rows[port]["docker"].container_name
            print(f"{colorize(str(port), Colors.CYAN):<8} {'conflict':<10} {owner:<25}")
        elif "docker" in rows[port]:
            owner = rows[port]["docker"].container_name
            print(f"{colorize(str(port), Colors.CYAN):<8} {'docker':<10} {owner:<25}")
        else:
            b = rows[port]["local"]
            owner = b.process_name or "-"
            print(f"{colorize(str(port), Colors.CYAN):<8} {'local':<10} {owner:<25}")


def jsonify_docker(mappings: List[Any]) -> str:
    """Render list of Docker mappings as JSON string."""
    return json.dumps([asdict(m) for m in mappings], indent=2)
