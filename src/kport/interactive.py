"""
Interactive TUI picker module for kport.

Provides a terminal user interface (curses-based with fallback) for listing active ports,
filtering, multi-selecting, and terminating processes.
"""

from __future__ import annotations

import sys
from typing import Any

from . import audit
from .docker_engine import docker_action_on_container, list_docker_mappings
from .formatter import Colors, colorize, confirm_prompt
from .inspectors import BaseInspector
from .process_manager import detect_process_manager
from .safety import check_safety_policy, load_kport_config


def _fetch_interactive_rows(inspector: BaseInspector) -> list[dict[str, Any]]:
    """Gather all local and docker port entries for the picker."""
    rows = []

    # 1. Local listening bindings
    local_bindings = inspector.list_listening(proto="both")
    seen_local_ports = set()
    for b in local_bindings:
        port = b.port
        seen_local_ports.add(port)
        pid = b.pid
        proc_name = b.process_name or "Unknown"
        state = b.state or "LISTEN"
        proto = b.proto

        pm_info = detect_process_manager(pid) if pid else None
        managed_by = pm_info["managed_by"] if pm_info else ""

        rows.append(
            {
                "type": "local",
                "port": port,
                "pid": pid,
                "process": proc_name,
                "proto": proto,
                "state": state,
                "managed_by": managed_by,
                "selected": False,
            }
        )

    # 2. Docker port mappings
    docker_hits = list_docker_mappings()
    for m in docker_hits:
        rows.append(
            {
                "type": "docker",
                "port": m.host_port,
                "pid": m.container_id[:12],
                "process": m.container_name,
                "proto": m.proto,
                "state": f"Docker ({m.container_port})",
                "managed_by": f"docker:{m.image}",
                "selected": False,
            }
        )

    return sorted(rows, key=lambda r: (r["port"], r["type"]))


def _fallback_numbered_menu(inspector: BaseInspector, args: Any) -> int:
    """Simple text fallback menu when curses UI is unavailable."""
    rows = _fetch_interactive_rows(inspector)
    if not rows:
        print(colorize("No active listening ports found.", Colors.GREEN))
        return 0

    print(colorize("\nActive Listening Ports:", Colors.CYAN + Colors.BOLD))
    print(
        f"{'#':<4} {'Port':<8} {'PID/ID':<12} {'Process':<20} {'Proto':<6} {'Managed By / State'}"
    )
    print("-" * 75)

    for idx, r in enumerate(rows, 1):
        pid_str = str(r["pid"]) if r["pid"] else "hidden"
        mb_str = r["managed_by"] or r["state"]
        print(
            f"[{idx:<2}] {r['port']:<8} {pid_str:<12} {r['process']:<20} {r['proto']:<6} {mb_str}"
        )

    try:
        inp = input(
            colorize(
                "\nEnter number(s) to kill (comma separated, e.g. 1, 3) or 'q' to quit: ",
                Colors.YELLOW,
            )
        ).strip()
        if not inp or inp.lower() == "q":
            print("Cancelled.")
            return 0

        selected_indices = []
        for token in inp.split(","):
            token = token.strip()
            if token.isdigit():
                val = int(token)
                if 1 <= val <= len(rows):
                    selected_indices.append(val - 1)

        if not selected_indices:
            print("No valid selection.")
            return 0

        selected_rows = [rows[i] for i in selected_indices]
        return _execute_kills(inspector, selected_rows, args)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return 0


def _execute_kills(
    inspector: BaseInspector, selected_rows: list[dict[str, Any]], args: Any
) -> int:
    """Execute kill action on all user-selected items."""
    if not selected_rows:
        return 0

    # Safety check before confirmation or execution
    cfg = load_kport_config()
    bypass = getattr(args, "bypass_safety", False)
    config = {}
    config_ports = getattr(args, "protected_ports", None)
    if isinstance(config_ports, list):
        config["protected_ports"] = config_ports
    config_procs = getattr(args, "protected_processes", None)
    if isinstance(config_procs, list):
        config["protected_processes"] = config_procs
    if not config and cfg:
        config = cfg

    for r in selected_rows:
        if r["type"] != "docker":
            pids = inspector.find_pids_on_port(r["port"], proto=r.get("proto", "tcp"))
            allowed, reason = check_safety_policy(
                port=r["port"],
                pids=pids,
                inspector=inspector,
                bypass_safety=bypass,
                config=config if config else None,
            )
            if not allowed:
                print(colorize(f"\n✗ {reason}", Colors.RED))
                return 1

    # Confirmation gate unless yes/assume_yes is specified
    assume_yes = getattr(args, "yes", False)
    if not assume_yes:
        print(colorize("\nWarning: You are about to terminate the following active port(s)/process(es):", Colors.YELLOW + Colors.BOLD))
        print(colorize(f"{'Type':<10} {'Port':<8} {'PID/ID':<12} {'Process/Container':<25} {'Managed By / State'}", Colors.BOLD))
        print("-" * 75)
        for r in selected_rows:
            pid_str = str(r["pid"]) if r["pid"] else "hidden"
            mb_str = r["managed_by"] or r["state"]
            type_str = r["type"].capitalize()
            proc_str = r["process"]
            if len(proc_str) > 24:
                proc_str = proc_str[:21] + "..."
            print(f"{type_str:<10} {r['port']:<8} {pid_str:<12} {proc_str:<25} {mb_str}")
        
        try:
            if not confirm_prompt("\nAre you sure you want to proceed with terminating these target(s)?", assume_yes=False):
                print(colorize("Cancelled.", Colors.RED))
                return 0
        except (KeyboardInterrupt, EOFError):
            print(colorize("\nCancelled.", Colors.RED))
            return 0

    print(
        colorize(
            f"\nProceeding to terminate {len(selected_rows)} selected target(s)...",
            Colors.CYAN,
        )
    )

    errors = 0
    for r in selected_rows:
        if r["type"] == "docker":
            action = getattr(args, "docker_action", None) or "stop"
            ok, msg = docker_action_on_container(
                r["pid"], action, dry_run=getattr(args, "dry_run", False)
            )
            if ok:
                print(
                    colorize(
                        f"✓ Port {r['port']} ({r['process']}): {msg}", Colors.GREEN
                    )
                )
            else:
                print(colorize(f"✗ Port {r['port']}: {msg}", Colors.RED))
                errors += 1
        else:
            kill_tree = getattr(args, "kill_tree", False)
            dry_run = getattr(args, "dry_run", False)
            ok, msg = inspector.kill_port(
                r["port"],
                force=getattr(args, "force", False),
                dry_run=dry_run,
                assume_yes=True,
                kill_tree=kill_tree,
                proto=r.get("proto", "tcp"),
            )
            # Emit audit record for every local kill attempt (success or failure).
            # r["pid"] is the integer PID displayed in the TUI row for local entries.
            tui_pids = [r["pid"]] if isinstance(r.get("pid"), int) else []
            audit.log_kill_port(
                port=r["port"],
                pids=tui_pids,
                dry_run=dry_run,
                success=ok,
                message=msg,
            )
            if ok:
                print(
                    colorize(
                        f"✓ Port {r['port']} ({r['process']}): {msg}", Colors.GREEN
                    )
                )
            else:
                print(colorize(f"✗ Port {r['port']}: {msg}", Colors.RED))
                errors += 1

    return 0 if errors == 0 else 1


def run_interactive_picker(inspector: BaseInspector, args: Any) -> int:
    """
    Run interactive TUI picker.
    Tries stdlib curses first, falls back to text menu if TTY / curses unavailable.
    """
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return _fallback_numbered_menu(inspector, args)

    try:
        import curses
    except ImportError:
        return _fallback_numbered_menu(inspector, args)

    def _curses_main(stdscr):
        try:
            curses.curs_set(0)
        except curses.error:
            pass

        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Highlight bar
        curses.init_pair(2, curses.COLOR_GREEN, -1)  # Free/Success
        curses.init_pair(3, curses.COLOR_YELLOW, -1)  # Warning/Managed

        rows = _fetch_interactive_rows(inspector)
        if not rows:
            return None
        current_idx = 0
        start_idx = 0
        search_query = ""

        while True:
            # Filter rows by search_query
            filtered_rows = [
                r
                for r in rows
                if not search_query
                or search_query.lower()
                in f"{r['port']} {r['process']} {r['managed_by']} {r['pid']}".lower()
            ]

            if current_idx >= len(filtered_rows):
                current_idx = max(0, len(filtered_rows) - 1)

            stdscr.clear()
            max_y, max_x = stdscr.getmaxyx()

            visible_count = max_y - 4

            # Maintain scrolling window offset
            if current_idx < start_idx:
                start_idx = current_idx
            elif current_idx >= start_idx + visible_count:
                start_idx = current_idx - visible_count + 1

            if start_idx >= len(filtered_rows):
                start_idx = max(0, len(filtered_rows) - visible_count)

            # Curses search is active by default; show cursor
            try:
                curses.curs_set(1)
            except curses.error:
                pass

            # Header
            header = " kport Interactive Picker | Type to filter  [Space] Select  [Ctrl-r] Refresh  [Enter] Kill  [Esc] Quit"
            stdscr.addstr(
                0, 0, header[: max_x - 1], curses.A_BOLD | curses.color_pair(1)
            )

            filter_line = f" Filter: {search_query}_"
            stdscr.addstr(1, 0, filter_line[: max_x - 1])

            col_header = f" {'Sel':<4} {'Port':<7} {'PID/ID':<12} {'Process':<18} {'Proto':<6} {'Managed By / State'}"
            stdscr.addstr(2, 0, col_header[: max_x - 1], curses.A_UNDERLINE)

            # Draw rows
            for i in range(min(visible_count, len(filtered_rows) - start_idx)):
                r = filtered_rows[start_idx + i]
                sel_char = "[x]" if r["selected"] else "[ ]"
                pid_str = str(r["pid"]) if r["pid"] else "hidden"
                mb_str = r["managed_by"] or r["state"]

                line = f" {sel_char:<4} {r['port']:<7} {pid_str:<12} {r['process']:<18} {r['proto']:<6} {mb_str}"
                line = line[: max_x - 1]

                if (start_idx + i) == current_idx:
                    stdscr.addstr(3 + i, 0, line, curses.A_REVERSE)
                else:
                    stdscr.addstr(3 + i, 0, line)

            stdscr.refresh()

            try:
                ch = stdscr.getch()
            except KeyboardInterrupt:
                return None

            # Handle navigation keys
            if ch in (curses.KEY_UP,):
                current_idx = max(0, current_idx - 1)
            elif ch in (curses.KEY_DOWN,):
                current_idx = (
                    min(len(filtered_rows) - 1, current_idx + 1) if filtered_rows else 0
                )
            
            # Handle selection toggle
            elif ch == ord(" "):
                if filtered_rows and current_idx < len(filtered_rows):
                    filtered_rows[current_idx]["selected"] = not filtered_rows[
                        current_idx
                    ]["selected"]

            # Handle reload/refresh hotkey (Ctrl-r is code 18)
            elif ch == 18:
                selected_keys = {(r["type"], r["port"], r["pid"]) for r in rows if r["selected"]}
                rows = _fetch_interactive_rows(inspector)
                for r in rows:
                    if (r["type"], r["port"], r["pid"]) in selected_keys:
                        r["selected"] = True
                current_idx = 0
                start_idx = 0

            # Handle backspace
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if search_query:
                    search_query = search_query[:-1]

            # Handle exit / escape
            elif ch == 27:
                if search_query:
                    search_query = ""
                else:
                    return None

            # Handle execution / Enter key
            elif ch in (10, 13):
                selected = [r for r in rows if r["selected"]]
                if not selected and filtered_rows:
                    selected = [filtered_rows[current_idx]]
                return selected

            # Handle other printable keys for default search
            elif 32 < ch <= 126:
                search_query += chr(ch)
                # Check for /q (quit)
                if search_query.endswith("/q"):
                    return None
                # Check for /r (refresh)
                elif search_query.endswith("/r"):
                    # Strip /r
                    search_query = search_query[:-2]
                    # Refresh selection & rows
                    selected_keys = {(r["type"], r["port"], r["pid"]) for r in rows if r["selected"]}
                    rows = _fetch_interactive_rows(inspector)
                    for r in rows:
                        if (r["type"], r["port"], r["pid"]) in selected_keys:
                            r["selected"] = True
                    current_idx = 0
                    start_idx = 0

    try:
        selected_targets = curses.wrapper(_curses_main)
        if selected_targets is None:
            print("Cancelled.")
            return 0
        return _execute_kills(inspector, selected_targets, args)
    except Exception:  # noqa: BLE001 - fallback to text menu on any curses exception
        # If curses initialization fails (e.g. TERM missing or unsupported terminal)
        return _fallback_numbered_menu(inspector, args)
