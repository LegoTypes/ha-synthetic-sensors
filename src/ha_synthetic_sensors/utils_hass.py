"""Home Assistant utilities for synthetic sensor package.

This module provides shared utilities for handling Home Assistant
resolution logic to eliminate code duplication.
"""

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


def check_hass_lookup_conditions(dependency_handler: Any) -> bool:
    """Check if HASS lookup conditions are met.

    Args:
        dependency_handler: The dependency handler to check

    Returns:
        True if HASS lookups are allowed and available
    """
    return (
        dependency_handler
        and hasattr(dependency_handler, "hass")
        and hasattr(dependency_handler, "allow_ha_lookups")
        and dependency_handler.allow_ha_lookups
    )


def check_data_provider_conditions(dependency_handler: Any, entity_id: str) -> bool:
    """Check if data provider conditions are met.

    Args:
        dependency_handler: The dependency handler to check
        entity_id: The entity ID to check

    Returns:
        True if data provider should be used
    """
    return (
        dependency_handler
        and hasattr(dependency_handler, "should_use_data_provider")
        and dependency_handler.should_use_data_provider(entity_id)
    )


def get_data_provider_callback(dependency_handler: Any) -> Any | None:
    """Get the data provider callback from dependency handler.

    Args:
        dependency_handler: The dependency handler

    Returns:
        The data provider callback if available and callable, None otherwise
    """
    if not dependency_handler:
        return None

    data_provider_callback = dependency_handler.data_provider_callback
    if data_provider_callback and callable(data_provider_callback):
        return data_provider_callback

    return None
