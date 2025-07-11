"""Device class constants for Home Assistant entity classification.

This module centralizes device class definitions from Home Assistant's official
device class enums, making them easier to maintain and update when HA adds new
device classes.
"""

import re
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# Non-numeric sensor device classes
# These sensor device classes represent non-numeric data
NON_NUMERIC_SENSOR_DEVICE_CLASSES = frozenset(
    {
        SensorDeviceClass.DATE,  # Date values (datetime.date objects)
        SensorDeviceClass.ENUM,  # Enumerated text values with limited options
        SensorDeviceClass.TIMESTAMP,  # Timestamp values (datetime.datetime objects)
    }
)

# Non-numeric binary sensor device classes
# Binary sensors represent on/off, true/false, open/closed states
# All binary sensor device classes are inherently non-numeric
NON_NUMERIC_BINARY_SENSOR_DEVICE_CLASSES = frozenset(
    {
        BinarySensorDeviceClass.BATTERY,
        BinarySensorDeviceClass.BATTERY_CHARGING,
        BinarySensorDeviceClass.CO,
        BinarySensorDeviceClass.COLD,
        BinarySensorDeviceClass.CONNECTIVITY,
        BinarySensorDeviceClass.DOOR,
        BinarySensorDeviceClass.GARAGE_DOOR,
        BinarySensorDeviceClass.GAS,
        BinarySensorDeviceClass.HEAT,
        BinarySensorDeviceClass.LIGHT,
        BinarySensorDeviceClass.LOCK,
        BinarySensorDeviceClass.MOISTURE,
        BinarySensorDeviceClass.MOTION,
        BinarySensorDeviceClass.MOVING,
        BinarySensorDeviceClass.OCCUPANCY,
        BinarySensorDeviceClass.OPENING,
        BinarySensorDeviceClass.PLUG,
        BinarySensorDeviceClass.POWER,
        BinarySensorDeviceClass.PRESENCE,
        BinarySensorDeviceClass.PROBLEM,
        BinarySensorDeviceClass.RUNNING,
        BinarySensorDeviceClass.SAFETY,
        BinarySensorDeviceClass.SMOKE,
        BinarySensorDeviceClass.SOUND,
        BinarySensorDeviceClass.TAMPER,
        BinarySensorDeviceClass.UPDATE,
        BinarySensorDeviceClass.VIBRATION,
        BinarySensorDeviceClass.WINDOW,
    }
)

# Combined set of all non-numeric device classes
ALL_NON_NUMERIC_DEVICE_CLASSES = NON_NUMERIC_SENSOR_DEVICE_CLASSES | NON_NUMERIC_BINARY_SENSOR_DEVICE_CLASSES


def get_domains_from_hass(hass: "HomeAssistant") -> set[str]:
    """Get all domains from the Home Assistant instance states.

    This function extracts domains from all entities in the current HA instance,
    similar to the template: {%- for d, es in states | groupby('domain') %}

    Args:
        hass: The Home Assistant instance

    Returns:
        set[str]: Set of all domain names found in the current HA instance
    """
    domains = set()
    try:
        states = hass.states.async_all()
        # Handle case where async_all() returns a Mock object (in tests)
        if hasattr(states, "__iter__"):
            for state in states:
                # Ensure state has entity_id attribute (not a Mock)
                if hasattr(state, "entity_id") and isinstance(state.entity_id, str):
                    domain = state.entity_id.split(".", 1)[0]
                    domains.add(domain)
    except (AttributeError, TypeError):
        # If we can't get states (mock objects, missing attributes, etc.),
        # return empty set so fallback validation is used
        pass

    return domains


def is_valid_ha_domain(domain: str, hass: "HomeAssistant | None" = None) -> bool:
    """Check if a domain is a valid Home Assistant domain.

    This function checks against domains from the actual Home Assistant instance
    if available, or falls back to format validation.

    Args:
        domain: The domain string to validate
        hass: Optional Home Assistant instance to check against

    Returns:
        bool: True if the domain is valid, False otherwise
    """
    if not domain:
        return False

    # If we have a Home Assistant instance, check against actual domains
    if hass is not None:
        available_domains = get_domains_from_hass(hass)

        # If the HA instance has states, use them for validation
        if available_domains:
            return domain in available_domains

        # If HA instance has no states (common in testing), fall back to format validation
        # This prevents rejecting all domains when testing with empty mock instances

    # Fallback to format validation when no HA instance is available
    # or when HA instance has no states
    # HA domains follow these conventions:
    # - Start with a lowercase letter
    # - Contain only lowercase letters, numbers, and underscores
    # - Be between 2-50 characters long
    pattern = r"^[a-z][a-z0-9_]{1,49}$"
    return bool(re.match(pattern, domain))
