"""
Shared safety constants for kport.
Single source-of-truth for protected ports and process names,
used by both CLI and MCP server to keep policies in sync.
"""
from __future__ import annotations

# Ports that must never be killed by default.
# These are critical infrastructure sockets (SSH, DNS, HTTP, HTTPS, databases, k8s).
PROTECTED_PORTS: frozenset[int] = frozenset(
    {
        22,  # SSH
        53,  # DNS
        80,  # HTTP
        443,  # HTTPS
        3306,  # MySQL / MariaDB
        5432,  # PostgreSQL
        6379,  # Redis
        6443,  # Kubernetes API server
        2375,  # Docker daemon (unencrypted)
        2376,  # Docker daemon (TLS)
        27017,  # MongoDB
    }
)

# Critical system process names that must never be targeted.
# Comparison is always case-insensitive.
PROTECTED_PROCESS_NAMES: frozenset[str] = frozenset(
    {
        "systemd",
        "init",
        "docker",
        "dockerd",
        "containerd",
        "sshd",
        "cron",
        "rsyslogd",
        "dbus-daemon",
        "explorer.exe",
        "lsass.exe",
        "services.exe",
        "wininit.exe",
        "winlogon.exe",
        "csrss.exe",
        "smss.exe",
    }
)

# Generic runtime process names whose display can be enriched
# by looking up their first meaningful CLI argument (script/jar/module name).
RUNTIME_ENRICHMENT_NAMES: frozenset[str] = frozenset(
    {
        "node",
        "nodejs",
        "node.exe",
        "python",
        "python3",
        "python2",
        "python.exe",
        "python3.exe",
        "java",
        "java.exe",
        "ruby",
        "ruby.exe",
        "php",
        "php-fpm",
        "php.exe",
        "bun",
        "bun.exe",
        "deno",
        "deno.exe",
        "perl",
        "perl.exe",
        "go",
        "go.exe",
        "cargo",
        "dotnet",
        "dotnet.exe",
        "tsx",
        "ts-node",
    }
)
