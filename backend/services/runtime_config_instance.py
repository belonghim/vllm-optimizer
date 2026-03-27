"""
RuntimeConfig singleton instance.

This module creates the RuntimeConfig singleton without multi_target_collector.
The collector is injected later by shared.py after both instances are created.

This breaks the circular import between shared.py and multi_target_collector.py.
"""

from services.runtime_config import RuntimeConfig

# Create instance without multi_target_collector initially (it will be injected by shared.py)
runtime_config = RuntimeConfig(None)

__all__ = ["runtime_config"]
