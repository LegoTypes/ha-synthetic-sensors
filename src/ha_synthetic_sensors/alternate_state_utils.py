"""Utility functions for alternate state detection."""

from .constants_alternate import identify_alternate_state_value


def detect_alternate_state_value(result: object) -> tuple[bool, str | bool]:
    """Detect if a result is an alternate HA state value.

    Args:
        result: The value to check

    Returns:
        Tuple of (is_alternate_state, alternate_state_or_false)
        - If alternate state: (True, state_string)
        - If not alternate state: (False, False)
    """
    try:
        alt = identify_alternate_state_value(result)
    except Exception:
        alt = False

    if isinstance(alt, str):
        return True, alt
    return False, alt
