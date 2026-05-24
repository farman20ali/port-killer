import sys
import os
import types
import importlib
import inspect

# Ensure src is on sys.path so `kport` package can be imported
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# Minimal replacement for pytest.raises
class _Raises:
    def __init__(self, exc):
        if isinstance(exc, tuple):
            self.exc = exc
        else:
            self.exc = (exc,)
    def __enter__(self):
        return None
    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError(f"Expected exception {self.exc} but none was raised")
        return issubclass(exc_type, self.exc)

fake_pytest = types.SimpleNamespace(raises=lambda exc: _Raises(exc))
import builtins
sys.modules['pytest'] = fake_pytest

# Import the tests module and run functions starting with test_
mod = importlib.import_module('tests.test_cli')
failed = 0
for name, fn in inspect.getmembers(mod, inspect.isfunction):
    if name.startswith('test_'):
        try:
            print('RUN', name)
            fn()
        except Exception as e:
            failed += 1
            print('FAIL', name, '-', type(e).__name__ + ':', e)

if failed:
    print(f"{failed} tests failed")
    sys.exit(1)
else:
    print('All tests passed')
    sys.exit(0)
