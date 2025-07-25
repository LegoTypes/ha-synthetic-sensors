"""Home Assistant constants available for use in sensor formulas.

This module provides lazy access to all Home Assistant constants that users might
reference in their sensor formulas. This ensures that formulas can use any
valid HA constant without import issues, and constants are only loaded when needed.
"""

from typing import Any

from .ha_constants import HAConstantLoader


# Create a module-level function to get constants lazily
def __getattr__(name: str) -> Any:
    """Lazy loading of HA constants when accessed."""
    # Validate input - empty strings are not valid attribute names
    if not name:
        raise AttributeError(f"Module '{__name__}' has no attribute '{name}'")

    try:
        return HAConstantLoader.get_constant(name)
    except ValueError as e:
        raise AttributeError(f"Module '{__name__}' has no attribute '{name}'") from e
