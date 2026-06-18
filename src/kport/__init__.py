"""
kport: Cross-platform port inspector and killer package.
"""

__version__ = "3.2.4"

from .inspectors import get_inspector, BaseInspector, PortBinding, ProcessInfo
from .exceptions import KPortError, InvalidPortError, PermissionDeniedError, DockerError, PortBlockedError
