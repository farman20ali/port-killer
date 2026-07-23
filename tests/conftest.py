"""
conftest.py – shared pytest fixtures and session-level setup.

psutil stub
-----------
kport ships psutil as an *optional* extra.  The CI test job installs only
``.[dev]`` (no psutil), so importing ``kport.inspectors.psutil_impl`` would
raise ``ModuleNotFoundError: No module named 'psutil'``.

We solve this by registering a lightweight stub in ``sys.modules`` *before*
any test module is collected.  Tests that exercise psutil-dependent behaviour
patch the individual attributes they need (e.g. ``psutil.Process``,
``psutil.net_connections``) on top of this stub, which works because
``patch()`` writes into the same module object.
"""

import sys
import types
from unittest.mock import MagicMock


def _make_psutil_stub() -> types.ModuleType:
    """Return a minimal fake psutil module that satisfies psutil_impl imports."""
    stub = types.ModuleType("psutil")

    # Constants referenced by psutil_impl
    stub.CONN_LISTEN = "LISTEN"
    stub.STATUS_ZOMBIE = "zombie"

    # Exception types referenced by psutil_impl
    stub.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    stub.AccessDenied = type("AccessDenied", (Exception,), {})
    stub.ZombieProcess = type("ZombieProcess", (Exception,), {})

    # Callable stubs – individual tests override these via patch()
    stub.net_connections = MagicMock(return_value=[])
    stub.Process = MagicMock()
    stub.process_iter = MagicMock(return_value=iter([]))

    return stub


# Register the stub only when the real psutil is not installed.
if "psutil" not in sys.modules:
    try:
        import psutil as _real_psutil  # noqa: F401  (present in some envs)
    except ImportError:
        sys.modules["psutil"] = _make_psutil_stub()
