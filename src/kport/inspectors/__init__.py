"""
Inspectors initialization package for kport.
Dynamically resolves and exposes the target inspector based on dependency availability.
"""

from .base import BaseInspector, PortBinding, ProcessInfo

__all__ = [
    "get_inspector",
    "BaseInspector",
    "PortBinding",
    "ProcessInfo",
]

USING_PSUTIL = False
try:
    import psutil
    USING_PSUTIL = True
except ImportError:
    pass


def _psutil_accessible() -> bool:
    """
    Return True only if psutil can actually enumerate network connections on
    this host.  On Linux, psutil.net_connections() requires access to
    /proc/net/tcp* and per-process /proc/<pid>/fd/ entries.  Inside a
    strictly-confined snap whose network-observe / system-observe plugs are
    not yet connected, this raises PermissionError (raw) or
    psutil.AccessDenied — even when the caller is root, because AppArmor
    applies regardless of UID in strict-confinement mode.
    """
    if not USING_PSUTIL:
        return False
    try:
        import psutil as _p
        _p.net_connections(kind="inet")
        return True
    except PermissionError:
        return False
    except Exception as exc:
        # psutil.AccessDenied is NOT a subclass of PermissionError; catch it too.
        try:
            import psutil as _p2
            if isinstance(exc, _p2.AccessDenied):
                return False
        except Exception:
            pass
        # Any other unexpected psutil failure → be safe and fall back.
        return False


def get_inspector() -> BaseInspector:
    """Resolve and return the appropriate inspector instance for the host system."""
    if _psutil_accessible():
        from .psutil_impl import PsutilInspector
        return PsutilInspector()
    from .system_impl import FallbackInspector
    return FallbackInspector()
