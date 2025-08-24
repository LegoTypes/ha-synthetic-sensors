"""Alternate state handler related constants.

These constants centralize YAML key names used for alternate state handlers.
"""

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN  # local import

UNAVAILABLE_KEY = "UNAVAILABLE"
UNKNOWN_KEY = "UNKNOWN"
NONE_KEY = "NONE"
FALLBACK_KEY = "FALLBACK"

# Special YAML constants that get converted to Python values
STATE_NONE_YAML = "STATE_NONE"  # Gets converted to Python None

# Internal state constants for alternate state handler processing
STATE_NONE = None  # Internal representation of None state (Python None)

# Alternate state type identifiers (used for handler selection)
ALTERNATE_STATE_NONE = "none"
ALTERNATE_STATE_UNKNOWN = "unknown"
ALTERNATE_STATE_UNAVAILABLE = "unavailable"


def identify_alternate_state_value(value: object) -> str | bool:
    """Return 'none'|'unknown'|'unavailable' for HA special state values, else None.

    This helper centralizes alternate-state identification so other modules can
    consistently map Python/HA values to the alternate-state identifiers used by
    the pipeline.
    """
    try:
        # None -> STATE_NONE
        if value is None:
            return ALTERNATE_STATE_NONE

        # Handle direct Home Assistant consts or string equivalents
        if value == STATE_UNKNOWN or (isinstance(value, str) and value.lower().strip() == STATE_UNKNOWN.lower()):
            return ALTERNATE_STATE_UNKNOWN

        if value == STATE_UNAVAILABLE or (isinstance(value, str) and value.lower().strip() == STATE_UNAVAILABLE.lower()):
            return ALTERNATE_STATE_UNAVAILABLE

        # Handle special case for 'none' string
        if isinstance(value, str) and value.lower().strip() == ALTERNATE_STATE_NONE:
            return ALTERNATE_STATE_NONE
    except (AttributeError, TypeError):
        # Be tolerant of unexpected inputs - signal no alternate state found
        pass

    # No alternate state detected
    return False
