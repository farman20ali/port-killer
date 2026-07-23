"""
Custom exception definitions for kport.
Enables clean error propagation without hard process exits inside library code.
"""


class KPortError(Exception):
    """Base exception for all kport errors."""

    exit_code = 1


class InvalidPortError(KPortError):
    """Raised when a port number or port range is invalid."""

    exit_code = 2


class PermissionDeniedError(KPortError):
    """Raised when executing a command lacks sufficient privileges."""

    exit_code = 3


class DockerError(KPortError):
    """Raised when a Docker execution fails or returns an error."""

    exit_code = 1


class PortBlockedError(KPortError):
    """Raised when a port cannot be freed or verified."""

    exit_code = 1


class ProcessNotFoundError(KPortError):
    """Raised when an expected process no longer exists (PID vanished)."""

    exit_code = 1
