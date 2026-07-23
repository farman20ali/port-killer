# 🚀 kport v4.0.0 — Release Notes

**Release Date:** July 21, 2026  
**Tag:** `v4.0.0`  
**Previous Version:** [v3.2.6](./RELEASE_NOTES_3.2.6.md)

---

## Overview

kport 4.0.0 is a **major feature release** that introduces game-changing capabilities, cross-platform performance enhancements, and category-defining features for process and network port management.

This release represents a significant milestone, shipping an interactive TUI picker, process manager awareness, advanced watch capabilities, UDP protocol support, process tree termination, and a fully zero-dependency core engine.

---

## 🆕 What's New

### 🖥️ Interactive TUI Picker (`kport -I` / `kport interactive`)
You can now list, filter, select, and terminate processes using a visual text-user interface directly in your terminal:
- **Interactive TUI Mode**: Launch with `kport -I` or `kport interactive`.
- **Search-by-Default**: Start typing characters immediately to filter active ports (no prefix needed).
- **Navigation & Scrolling**: Use arrow keys to navigate the list, which dynamically scrolls viewports for lists longer than the terminal screen.
- **Multi-Select**: Press `[Space]` to check/uncheck multiple ports.
- **Dynamic Refresh**: Press `[Ctrl-r]` or type `/r` to reload active ports, preserving current selections and scrolling back to the top.
- **Safety Confirmation Prompt**: Hitting `[Enter]` exits curses and displays a clear target summary, requiring confirmation (`y/N`) before terminating processes. Bypassed via `-y`/`--yes`.
- **Fallback Mode**: Gracefully degrades to a clean, non-interactive numbered menu on non-TTY environments or terminals lacking curses support.
- **Quit Shortcuts**: Type `/q`, press `[Esc]` (clears search query first, then exits on next `[Esc]`), or use `[Ctrl-c]` to cancel and exit.

### ⚙️ Process Manager Awareness (`systemd`, `PM2`, `Supervisord`)
Tired of killing a port only to have the process instantly restart? `kport explain` is now smart enough to detect process managers:
- **Service Detection**: Automatically parses Linux cgroups to find systemd units (`systemd:nginx.service`), checks process environments and `pm2 jlist` for PM2 apps (`pm2:api-server`), and queries supervisord status.
- **Actionable Warnings**: Informs you why the port will restart and provides the exact command needed to stop the service (e.g., `systemctl stop nginx.service` or `pm2 stop api-server`).

### ⏱️ Watch Mode Enhancements (`--until` & `--timeout`)
`kport watch` is now a powerful scripting tool for CI/CD pipelines and deployment orchestration:
- **Block Until Free**: `kport watch 8080 --until free` blocks execution until the port is fully released (exits `0`).
- **Block Until Occupied**: `kport watch 8080 --until occupied` blocks execution until a process binds the port (exits `0`).
- **Timeouts**: Use `--timeout <seconds>` to limit the wait time. If the target state isn't reached before the timeout, it exits with a general error (`1`).

### 🌐 UDP Protocol Support (`--proto tcp|udp|both`)
Standard network inspection tools only check TCP. `kport` now fully supports UDP ports across all commands:
- **Inspection & Listing**: Filter bindings by protocol with `--proto tcp`, `--proto udp`, or `--proto both`.
- **Targeted Kill**: Terminate only UDP or TCP listeners bound to a specific port.

### 🌳 Recursive Process Tree Kill (`--kill-tree`)
Prevent orphaned worker processes by terminating entire process families recursively.
- When `--kill-tree` is used, `kport` queries child processes (via native `/proc` traversal on Unix, or `taskkill /T` on Windows) and terminates them in depth-first order (children first) before killing the parent process.

### ⏳ Wait for Exit (`--wait-for-exit <seconds>`)
Avoid race conditions in shell scripts and CI pipelines.
- Using `--wait-for-exit <seconds>` polls the target port every 200ms after sending kill signals, only exiting `0` when the socket is confirmed to be fully closed.

---

## ⚡ Zero Required Dependencies

To preserve the zero-required-dependency footprint, **psutil has been made completely optional** in the core package:
- Core `kport` installation (`pip install kport`) now requires **zero external dependencies**, relying entirely on native subprocesses and ctypes parsing (`/proc/net/*` on Linux, `iphlpapi.dll` on Windows).
- High-performance psutil inspection can be opted-in via the new `fast` extra:
  ```bash
  pip install kport[fast]
  ```

---

## ⚙️ Upgrading to v4.0.0

No breaking changes have been introduced to the stable `--json` envelope schema version 1. Custom JSON parser integrations will continue to work out-of-the-box.
