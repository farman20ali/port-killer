"""
Inspectors initialization package for kport.
Dynamically resolves and exposes the target inspector based on dependency availability.
"""

from .base import BaseInspector, PortBinding, ProcessInfo

USING_PSUTIL = False
try:
    import psutil
    USING_PSUTIL = True
except ImportError:
    pass


def get_inspector() -> BaseInspector:
    """Resolve and return the appropriate inspector instance for the host system."""
    if USING_PSUTIL:
        from .psutil_impl import PsutilInspector
        return PsutilInspector()
    else:
        from .system_impl import FallbackInspector
        return FallbackInspector()
