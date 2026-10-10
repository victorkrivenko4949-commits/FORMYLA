"""Compatibility alias: one module object, including private helpers and cache."""
import sys
from bank import repository as _impl
sys.modules[__name__] = _impl
