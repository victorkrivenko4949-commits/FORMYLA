"""
Mass Task Generation System
Generators package for FORMYLA platform.
"""

from .safe_writer import SafeJSONWriter
from .base_generator import TaskGenerator

__all__ = ['SafeJSONWriter', 'TaskGenerator']
