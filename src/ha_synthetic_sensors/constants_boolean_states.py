"""Boolean state constants for synthetic sensor package.

This module provides centralized boolean state mappings to eliminate
duplicate code between different resolver classes.

All constants are sourced from Home Assistant's device trigger mappings
using lazy loading, eliminating the need to maintain hardcoded lists.
"""

from typing import Any

from .ha_constants import HAConstantLoader


def _get_constant(name: str, module: str | None = None) -> Any:
    """Helper to get a constant with fallback."""
    try:
        return HAConstantLoader.get_constant(name, module)
    except ValueError:
        # Return the string name as fallback if constant doesn't exist
        return name


def get_true_states() -> set[Any]:
    """Get the set of states that should be considered True (1.0).

    Uses HA's own device trigger TURNED_ON mappings which contain all
    the semantic state mappings HA recognizes as "true".
    """
    # Get HA's official "turned on" states - this is the ground truth
    ha_turned_on = set(_get_constant("TURNED_ON", "homeassistant.components.binary_sensor.device_trigger"))

    # Add HA's fundamental boolean states
    ha_basic_states = {
        _get_constant("STATE_ON"),
    }

    # Only add truly generic boolean representations not covered by HA
    package_semantics = {"true", "yes", "1"}

    return ha_turned_on | ha_basic_states | package_semantics


def get_false_states() -> set[Any]:
    """Get the set of states that should be considered False (0.0).

    Uses HA's own device trigger TURNED_OFF mappings which contain all
    the semantic state mappings HA recognizes as "false".
    """
    # Get HA's official "turned off" states - this is the ground truth
    ha_turned_off = set(_get_constant("TURNED_OFF", "homeassistant.components.binary_sensor.device_trigger"))

    # Add HA's fundamental boolean states
    ha_basic_states = {
        _get_constant("STATE_OFF"),
    }

    # Only add truly generic boolean representations not covered by HA
    package_semantics = {"false", "no", "0"}

    return ha_turned_off | ha_basic_states | package_semantics


def get_current_true_states() -> set[Any]:
    """Get current true states - always fresh."""
    return get_true_states()


def get_current_false_states() -> set[Any]:
    """Get current false states - always fresh."""
    return get_false_states()


# Backwards compatibility - provide constants that are computed fresh each time
TRUE_STATES = get_true_states()
FALSE_STATES = get_false_states()
