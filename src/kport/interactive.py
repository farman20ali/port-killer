"""
Interactive TUI picker module for kport.

Provides a terminal user interface (curses-based with fallback) for listing active ports,
filtering, multi-selecting, and terminating processes.
"""

import sys
import os
from dataclasses import asdict
from typing import List, Dict, Any, Optional

from .inspectors import BaseInspector
from .docker_engine import list_docker_mappings, docker_action_on_container
from .process_manager import detect_process_manager
from .formatter import Colors, colorize, confirm_prompt

def _fetch_interactive_rows(inspector: BaseInspector) -> List[Dict[str, Any]]:
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
        
        rows.append({
            "type": "local",
            "port": port,
            "pid": pid,
            "process": proc_name,
            "proto": proto,
            "state": state,
            "managed_by": managed_by,
            "selected": False,
        })
        
    # 2. Docker port mappings
    docker_hits = list_docker_mappings()
    for m in docker_hits:
        rows.append({
            "type": "docker",
            "port": m.host_port,
            "pid": m.container_id[:12],
            "process": m.container_name,
            "proto": m.proto,
            "state": f"Docker ({m.container_port})",
            "managed_by": f"docker:{m.image}",
            "selected": False,
        })
        
    return sorted(rows, key=lambda r: (r["port"], r["type"]))


def _fallback_numbered_menu(inspector: BaseInspector, args: Any) -> int:
    """Simple text fallback menu when curses UI is unavailable."""
    rows = _fetch_interactive_rows(inspector)
    if not rows:
        print(colorize("No active listening ports found.", Colors.GREEN))
        return 0
        
    print(colorize("\nActive Listening Ports:", Colors.CYAN + Colors.BOLD))
    print(f"{'#':<4} {'Port':<8} {'PID/ID':<12} {'Process':<20} {'Proto':<6} {'Managed By / State'}")
    print("-" * 75)
    
    for idx, r in enumerate(rows, 1):
        pid_str = str(r['pid']) if r['pid'] else "hidden"
        mb_str = r['managed_by'] or r['state']
        print(f"[{idx:<2}] {r['port']:<8} {pid_str:<12} {r['process']:<20} {r['proto']:<6} {mb_str}")
        
    try:
        inp = input(colorize("\nEnter number(s) to kill (comma separated, e.g. 1, 3) or 'q' to quit: ", Colors.YELLOW)).strip()
        if not inp or inp.lower() == 'q':
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


def _execute_kills(inspector: BaseInspector, selected_rows: List[Dict[str, Any]], args: Any) -> int:
    """Execute kill action on all user-selected items."""
    if not selected_rows:
        return 0
        
    print(colorize(f"\nProceeding to terminate {len(selected_rows)} selected target(s)...", Colors.CYAN))
    
    errors = 0
    for r in selected_rows:
        if r["type"] == "docker":
            action = getattr(args, "docker_action", None) or "stop"
            ok, msg = docker_action_on_container(r["pid"], action, dry_run=getattr(args, "dry_run", False))
            if ok:
                print(colorize(f"✓ Port {r['port']} ({r['process']}): {msg}", Colors.GREEN))
            else:
                print(colorize(f"✗ Port {r['port']}: {msg}", Colors.RED))
                errors += 1
        else:
            kill_tree = getattr(args, "kill_tree", False)
            ok, msg = inspector.kill_port(
                r["port"],
                force=getattr(args, "force", False),
                dry_run=getattr(args, "dry_run", False),
                assume_yes=True,
                kill_tree=kill_tree,
                proto=r.get("proto", "tcp"),
            )
            if ok:
                print(colorize(f"✓ Port {r['port']} ({r['process']}): {msg}", Colors.GREEN))
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
        except Exception:
            pass
            
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Highlight bar
        curses.init_pair(2, curses.COLOR_GREEN, -1)                  # Free/Success
        curses.init_pair(3, curses.COLOR_YELLOW, -1)                 # Warning/Managed

        rows = _fetch_interactive_rows(inspector)
        if not rows:
            return None
            
        current_idx = 0
        search_query = ""

        while True:
            # Filter rows by search_query
            filtered_rows = [
                r for r in rows
                if not search_query or search_query.lower() in f"{r['port']} {r['process']} {r['managed_by']} {r['pid']}".lower()
            ]
            
            if current_idx >= len(filtered_rows):
                current_idx = max(0, len(filtered_rows) - 1)
                
            stdscr.clear()
            max_y, max_x = stdscr.getmaxyx()

            # Header
            header = " kport Interactive Picker | [/] Filter  [Space] Select  [Enter] Confirm Kill  [Esc/q] Quit"
            stdscr.addstr(0, 0, header[:max_x-1], curses.A_BOLD | curses.color_pair(1))

            filter_line = f" Filter: {search_query}_" if search_query else " (Type to filter ports/processes)"
            stdscr.addstr(1, 0, filter_line[:max_x-1])

            col_header = f" {'Sel':<4} {'Port':<7} {'PID/ID':<12} {'Process':<18} {'Proto':<6} {'Managed By / State'}"
            stdscr.addstr(2, 0, col_header[:max_x-1], curses.A_UNDERLINE)

            # Draw rows
            visible_count = max_y - 4
            for i in range(min(visible_count, len(filtered_rows))):
                r = filtered_rows[i]
                sel_char = "[x]" if r["selected"] else "[ ]"
                pid_str = str(r["pid"]) if r["pid"] else "hidden"
                mb_str = r["managed_by"] or r["state"]

                line = f" {sel_char:<4} {r['port']:<7} {pid_str:<12} {r['process']:<18} {r['proto']:<6} {mb_str}"
                line = line[:max_x-1]

                if i == current_idx:
                    stdscr.addstr(3 + i, 0, line, curses.A_REVERSE)
                else:
                    stdscr.addstr(3 + i, 0, line)

            stdscr.refresh()

            try:
                ch = stdscr.getch()
            except KeyboardInterrupt:
                return None

            if ch in (27, ord('q'), ord('Q')):  # Esc or Q
                return None
            elif ch in (curses.KEY_UP, ord('k')):
                current_idx = max(0, current_idx - 1)
            elif ch in (curses.KEY_DOWN, ord('j')):
                current_idx = min(len(filtered_rows) - 1, current_idx + 1) if filtered_rows else 0
            elif ch == ord(' '):  # Space toggle select
                if filtered_rows and current_idx < len(filtered_rows):
                    filtered_rows[current_idx]["selected"] = not filtered_rows[current_idx]["selected"]
            elif ch in (10, 13):  # Enter key
                # Collect selected items (or item under cursor if none selected)
                selected = [r for r in rows if r["selected"]]
                if not selected and filtered_rows:
                    selected = [filtered_rows[current_idx]]
                return selected
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if search_query:
                    search_query = search_query[:-1]
            elif 32 <= ch <= 126 and chr(ch) != ' ':  # Printable chars for filter search
                search_query += chr(ch)

    try:
        selected_targets = curses.wrapper(_curses_main)
        if selected_targets is None:
            print("Cancelled.")
            return 0
        return _execute_kills(inspector, selected_targets, args)
    except Exception:
        # If curses initialization fails (e.g. TERM missing or unsupported terminal)
        return _fallback_numbered_menu(inspector, args)
