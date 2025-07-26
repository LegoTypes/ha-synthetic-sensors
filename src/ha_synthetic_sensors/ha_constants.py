"""Home Assistant constants loader for synthetic sensor package.

This module provides lazy loading of Home Assistant constants that users might
reference in their YAML configurations. This ensures that our package can
access any HA constant at runtime without having to predict what users will need.
"""

import importlib
import logging
from typing import Any

from .exceptions import IntegrationSetupError

_LOGGER = logging.getLogger(__name__)

# Cache for loaded constants to avoid repeated imports
_constant_cache: dict[str, Any] = {}

# Common HA modules that contain constants users might reference
_COMMON_HA_MODULES = [
    "homeassistant.const",
    "homeassistant.components.sensor",
    "homeassistant.components.binary_sensor",
    "homeassistant.components.alarm_control_panel",
    "homeassistant.components.lock",
    "homeassistant.components.binary_sensor.device_trigger",
    "homeassistant.components.sensor.const",
]


class HAConstantLoader:
    """Utility for lazy loading of Home Assistant constants."""

    @staticmethod
    def get_constant(constant_name: str, module_path: str | None = None) -> Any:
        """
        Get a Home Assistant constant by name, with optional specific module path.

        Args:
            constant_name: Name of the constant to retrieve
            module_path: Optional specific module path (e.g., 'homeassistant.const')
                        If not provided, will search common HA modules

        Returns:
            The constant value

        Raises:
            ValueError: If constant cannot be found in any module
        """
        cache_key = f"{module_path or 'auto'}:{constant_name}"

        # Check cache first
        if cache_key in _constant_cache:
            return _constant_cache[cache_key]

        if module_path:
            # Try specific module first
            try:
                value = HAConstantLoader._load_from_module(module_path, constant_name)
                _constant_cache[cache_key] = value
                return value
            except (ImportError, AttributeError) as e:
                raise ValueError(f"Cannot resolve {module_path}.{constant_name}: {e}") from e

        # Search common modules
        for module in _COMMON_HA_MODULES:
            try:
                value = HAConstantLoader._load_from_module(module, constant_name)
                _constant_cache[cache_key] = value
                _LOGGER.debug("Found constant %s in module %s", constant_name, module)
                return value
            except (ImportError, AttributeError):
                continue

        raise ValueError(f"Cannot find constant '{constant_name}' in any known HA module")

    @staticmethod
    def _load_from_module(module_path: str, constant_name: str) -> Any:
        """Load a constant from a specific module."""
        module = importlib.import_module(module_path)
        return getattr(module, constant_name)

    @staticmethod
    def preload_common_constants() -> None:
        """Pre-load commonly used constants for better performance."""
        common_constants = [
            # State constants
            ("homeassistant.const", "STATE_ON"),
            ("homeassistant.const", "STATE_OFF"),
            ("homeassistant.const", "STATE_UNKNOWN"),
            ("homeassistant.const", "STATE_UNAVAILABLE"),
            ("homeassistant.const", "STATE_OPEN"),
            ("homeassistant.const", "STATE_CLOSED"),
            ("homeassistant.const", "STATE_HOME"),
            ("homeassistant.const", "STATE_NOT_HOME"),
            # Device classes
            ("homeassistant.components.sensor", "SensorDeviceClass"),
            ("homeassistant.components.sensor", "SensorStateClass"),
            ("homeassistant.components.binary_sensor", "BinarySensorDeviceClass"),
            # Component states
            ("homeassistant.components.alarm_control_panel", "AlarmControlPanelState"),
            ("homeassistant.components.lock", "LockState"),
        ]

        for module_path, constant_name in common_constants:
            try:
                HAConstantLoader.get_constant(constant_name, module_path)
            except ValueError:
                # Some constants might not exist in all HA versions
                _LOGGER.debug("Could not preload constant %s from %s", constant_name, module_path)

    @staticmethod
    def clear_cache() -> None:
        """Clear the constant cache (useful for testing)."""
        _constant_cache.clear()


# Convenience function for direct access
def get_ha_constant(constant_name: str, module_path: str | None = None) -> Any:
    """
    Convenience function to get a Home Assistant constant.

    Args:
        constant_name: Name of the constant to retrieve
        module_path: Optional specific module path

    Returns:
        The constant value

    Example:
        >>> state_on = get_ha_constant("STATE_ON")
        >>> sensor_device_class = get_ha_constant("SensorDeviceClass", "homeassistant.components.sensor")
    """
    return HAConstantLoader.get_constant(constant_name, module_path)


# Pre-load common constants on module import
try:
    HAConstantLoader.preload_common_constants()
except Exception as e:
    raise IntegrationSetupError(f"Failed to preload some HA constants: {e}") from e

# Export the main interface
__all__ = [
    "HAConstantLoader",
    "get_ha_constant",
]
