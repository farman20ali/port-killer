"""
cli_utils.py — CLI-specific shared utilities for kport.

Contains helpers used by both cli.py and cli_commands.py.

Architectural constraints:
  - cli_utils.py may import from domain modules.
  - Domain modules MUST NOT import from cli_utils.py, cli_commands.py,
    or cli.py.
  - cli_commands.py MAY import from cli_utils.py.
  - cli.py MAY import from cli_utils.py.
  - cli_utils.py MUST NOT import from cli_commands.py or cli.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from .exceptions import InvalidPortError, KPortError
from .formatter import Colors, colorize
from .inspectors import BaseInspector
from .profile import load_profiles, resolve_profile
from .safety import (
    SafetyDecision,
)
from .safety import (
    check_safety_policy as _core_check_safety_policy,
)

# ---------------------------------------------------------------------------
# Exit codes — defined here so cli_commands.py can import them without
# creating a circular dependency on cli.py.
# cli.py re-exports these symbols so that `from kport.cli import EXIT_OK`
# continues to work for existing consumers and tests.
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_GENERAL_ERROR = 1
EXIT_INVALID_INPUT = 2
EXIT_PERMISSION = 3
EXIT_PORT_DOCKER = 4
EXIT_PORT_FREE = 5

# JSON schema version for --json output envelope
JSON_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _json_out(command: str, data: dict) -> str:
    """Return a stable, versioned JSON envelope for --json output.

    Schema:  {"schema_version": 1, "command": "<subcommand>", "data": {...}}
    All --json outputs pass through here so downstream scripts can key on
    schema_version to detect breaking changes.
    """
    return json.dumps(
        {"schema_version": JSON_SCHEMA_VERSION, "command": command, "data": data},
        indent=2,
    )


def debug_log(enabled: bool, msg: str) -> None:
    if enabled:
        print(colorize(f"[debug] {msg}", Colors.BLUE), file=sys.stderr)


# ---------------------------------------------------------------------------
# Privilege detection
# ---------------------------------------------------------------------------


def _is_elevated() -> bool:
    """P1 fix: detect if the current process is running with root/admin privileges."""
    if sys.platform == "win32":
        try:
            import ctypes

            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except (AttributeError, OSError):
            return False
    return (os.geteuid() == 0) if hasattr(os, "geteuid") else False


# ---------------------------------------------------------------------------
# Port validation and range parsing
# ---------------------------------------------------------------------------


def validate_port(port: int) -> None:
    """Validate port constraints, raising InvalidPortError on failure."""
    if not (1 <= port <= 65535):
        raise InvalidPortError(f"Port {port} is not valid. Must be 1-65535.")


def parse_port_range(port_range: str, max_ports: int = 1000) -> list[int]:
    """Parse port range strings (e.g. 8080 or 3000-3010)."""
    try:
        if "-" in port_range:
            start_s, end_s = port_range.split("-", 1)
            start = int(start_s.strip())
            end = int(end_s.strip())
            if start > end:
                raise InvalidPortError(f"Invalid range {port_range}: start > end")
            total = end - start + 1
            if total > max_ports:
                raise InvalidPortError(
                    f"Range too large ({total} ports). Maximum {max_ports} allowed."
                )
            for p in (start, end):
                validate_port(p)
            return list(range(start, end + 1))
        else:
            port = int(port_range.strip())
            validate_port(port)
            return [port]
    except ValueError:
        raise InvalidPortError(f"Invalid port or range format: {port_range}")


# ---------------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------------


def _default_config_paths() -> list[str]:
    home = os.path.expanduser("~")
    return [
        os.path.join(os.getcwd(), ".kport.json"),
        os.path.join(home, ".kport.json"),
        os.path.join(home, ".config", "kport", "config.json"),
    ]


def load_config(config_path: str | None, debug: bool = False) -> dict[str, Any]:
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
            print(
                colorize(f"Error: invalid JSON in config file {path}: {e}", Colors.RED),
                file=sys.stderr,
            )
            sys.exit(EXIT_INVALID_INPUT)
        except OSError as e:
            print(
                colorize(f"Error: failed to read config file {path}: {e}", Colors.RED),
                file=sys.stderr,
            )
            sys.exit(EXIT_INVALID_INPUT)
    return {}


def apply_config_defaults(args: argparse.Namespace, cfg: dict[str, Any]) -> None:
    """Apply configuration options as fallback defaults to argparse Namespace."""

    def _set_bool(name: str, key: str) -> None:
        # Only apply if the attribute exists AND is still at its default (False)
        if (
            hasattr(args, name)
            and getattr(args, name) is False
            and isinstance(cfg.get(key), bool)
        ):
            setattr(args, name, cfg[key])

    def _set_num(name: str, key: str) -> None:
        # FIX: graceful_timeout default is now None; apply config only when not explicitly set
        if hasattr(args, name) and cfg.get(key) is not None:
            try:
                current = getattr(args, name)
                if name == "graceful_timeout" and current is None:
                    setattr(args, name, float(cfg[key]))
            except (ValueError, TypeError):
                pass

    _set_bool("yes", "yes")
    _set_bool("dry_run", "dry_run")
    _set_bool("json", "json")
    _set_bool("debug", "debug")
    _set_bool("force", "force")
    _set_bool("bypass_safety", "bypass_safety")
    _set_num("graceful_timeout", "graceful_timeout")

    # Custom safety lists from config
    args.protected_ports = cfg.get("protected_ports")
    args.protected_processes = cfg.get("protected_processes")

    if hasattr(args, "docker_action") and getattr(args, "docker_action", None) is None:
        v = cfg.get("docker_action")
        if v in ("stop", "restart", "rm"):
            args.docker_action = v


def _resolve_timeout(args: argparse.Namespace) -> float:
    """Return graceful_timeout, falling back to 3.0 if not set."""
    t = getattr(args, "graceful_timeout", None)
    return float(t) if t is not None else 3.0


# ---------------------------------------------------------------------------
# Safety policy CLI wrapper
# ---------------------------------------------------------------------------


def check_safety_policy(
    port: int | None,
    pids: list[int],
    args: argparse.Namespace,
    inspector: BaseInspector,
) -> SafetyDecision:
    """
    Check if a port or any associated PIDs are protected by safety policies.

    Delegates to the centralized safety module (safety.py).  Reads
    bypass_safety, protected_ports, and protected_processes from *args* so
    that CLI configuration continues to work as before.

    Returns a SafetyDecision that supports (bool, str) tuple-unpacking for
    backward compatibility.
    """
    bypass = getattr(args, "bypass_safety", False)

    # Build a config-like dict from CLI args so the shared policy function
    # can apply the same additive override logic.
    config: dict = {}
    config_ports = getattr(args, "protected_ports", None)
    if isinstance(config_ports, list):
        config["protected_ports"] = config_ports
    config_procs = getattr(args, "protected_processes", None)
    if isinstance(config_procs, list):
        config["protected_processes"] = config_procs

    decision = _core_check_safety_policy(
        port=port,
        pids=pids,
        inspector=inspector,
        bypass_safety=bypass,
        config=config if config else None,
    )

    if bypass and not decision.allowed:
        # Should not normally happen, but guard anyway.
        pass
    elif bypass and decision.allowed and decision.policy_source == "bypass":
        debug_log(
            getattr(args, "debug", False),
            f"Safety shield bypassed (port={port}, pids={pids})",
        )

    return decision


# ---------------------------------------------------------------------------
# Docker confirmation gate
# ---------------------------------------------------------------------------


def confirm_docker_rm(
    container_name: str,
    container_id: str,
    assume_yes: bool,
    force: bool,
    image: str = "",
    host_port: int | None = None,
    container_port: int | None = None,
) -> bool:
    """
    Confirmation gate for docker rm.

    Shows a rich context card with container name, image, port mapping, and
    short ID, then asks a simple [y/N] prompt.  The user never has to type
    a container name — just 'y' to confirm.

    --yes --force together skips the prompt entirely (non-interactive mode).
    --yes alone still shows the prompt because rm is irreversible.
    """
    if assume_yes and force:
        return True
    if assume_yes and not force:
        print(
            colorize(
                "Error: Removing a Docker container is irreversible. "
                "Use --force in addition to --yes to bypass interactive confirmation.",
                Colors.RED,
            ),
            file=sys.stderr,
        )
        return False

    short_id = container_id[:12] if container_id else "unknown"
    port_info = (
        f"{host_port} → {container_port}"
        if host_port and container_port
        else str(host_port or "?")
    )

    print()
    print(
        colorize(
            "  ⚠️  DESTRUCTIVE ACTION — This cannot be undone",
            Colors.YELLOW + Colors.BOLD,
        )
    )
    print(colorize("  " + "─" * 46, Colors.YELLOW))
    print(colorize(f"  Container   : {container_name}", Colors.WHITE))
    if image:
        print(colorize(f"  Image       : {image}", Colors.WHITE))
    print(colorize(f"  Port        : {port_info}", Colors.WHITE))
    print(colorize(f"  Container ID: {short_id}", Colors.WHITE))
    print(colorize("  " + "─" * 46, Colors.YELLOW))
    print()
    try:
        user_input = (
            input(colorize("  Remove this container? [y/N]: ", Colors.MAGENTA))
            .strip()
            .lower()
        )
        if user_input in ("y", "yes"):
            return True
        print(colorize("Aborted.", Colors.YELLOW))
        return False
    except KeyboardInterrupt:
        print()
        raise


# ---------------------------------------------------------------------------
# Port polling
# ---------------------------------------------------------------------------


def _poll_until_free(
    port: int, timeout: float, inspector: BaseInspector, interval: float = 0.2
) -> bool:
    """Compatibility alias — delegates to :func:`kport.port_utils.poll_until_free`.

    The polling implementation has been relocated to ``port_utils`` so that it
    can be consumed by any layer (CLI, MCP, domain) without a presentation-layer
    dependency.  This alias preserves backward compatibility for code that still
    imports ``_poll_until_free`` from ``cli_utils``.

    .. deprecated::
        Import :func:`~kport.port_utils.poll_until_free` from
        ``kport.port_utils`` directly.
    """
    from .port_utils import poll_until_free

    return poll_until_free(port, timeout, inspector, interval)


# ---------------------------------------------------------------------------
# Profile-based port resolution
# ---------------------------------------------------------------------------


def _resolve_ports_for_args(args: argparse.Namespace) -> list[int]:
    """Helper to resolve a list of ports for the command, supporting --profile."""
    profile_name = getattr(args, "profile", None)
    if profile_name:
        cfg = load_config(
            getattr(args, "config", None), debug=getattr(args, "debug", False)
        )
        profiles = load_profiles(cfg)
        resolved = resolve_profile(profile_name, profiles)
        if resolved is None:
            raise KPortError(f"Profile '{profile_name}' not found in configuration")
        return resolved

    port = getattr(args, "port", None)
    if port is not None:
        return [port]
    return []
