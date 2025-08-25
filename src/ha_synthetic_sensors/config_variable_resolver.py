"""Config variable resolution utilities.

This module provides shared utilities for resolving configuration variables
without creating circular dependencies between modules.
"""

from .utils_config import resolve_config_variables

# Re-export the function to maintain backward compatibility
__all__ = ["resolve_config_variables"]
