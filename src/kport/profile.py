"""
profile.py -- Named port profile support for kport.

Allows users to define named groups of ports in their .kport.json config
so they can operate on a whole dev-stack in one command:

    kport kill --profile backend-dev
    kport inspect --profile backend-dev

Config schema (in .kport.json)::

    {
        "profiles": {
            "backend-dev": [8080, 5432, 6379],
            "frontend": [3000, 3001],
            "all-dev": [8080, 5432, 6379, 3000, 3001]
        }
    }
"""

from __future__ import annotations

from typing import Dict, List, Optional


def load_profiles(config: dict) -> Dict[str, List[int]]:
    """Parse the ``profiles`` key from a loaded kport config dict.

    Returns a dict mapping profile name -> list of port ints.
    Ignores entries that are not lists of integers, emitting no errors
    so a malformed config entry never crashes the CLI.
    """
    raw = config.get("profiles")
    if not isinstance(raw, dict):
        return {}

    profiles: Dict[str, List[int]] = {}
    for name, value in raw.items():
        if not isinstance(value, list):
            continue
        ports = []
        for item in value:
            try:
                port = int(item)
                if 1 <= port <= 65535:
                    ports.append(port)
            except (TypeError, ValueError):
                pass
        if ports:
            profiles[str(name)] = ports
    return profiles


def resolve_profile(name: str, profiles: Dict[str, List[int]]) -> Optional[List[int]]:
    """Return the port list for *name*, or None if the profile doesn't exist.

    Lookup is case-insensitive so ``backend-Dev`` matches ``backend-dev``.
    """
    # Exact match first
    if name in profiles:
        return profiles[name]
    # Case-insensitive fallback
    name_lower = name.lower()
    for key, ports in profiles.items():
        if key.lower() == name_lower:
            return ports
    return None
