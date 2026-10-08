"""Compatibility alias: one module object, including private helpers and cache."""
import sys
from teacher import groups as _impl
sys.modules[__name__] = _impl
