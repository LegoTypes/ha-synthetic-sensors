"""Shared resolver utilities for synthetic sensor package.

This module provides shared utilities for entity and attribute resolution
to eliminate code duplication between different resolver classes.
"""

import logging
from typing import Any

from .constants_boolean_states import FALSE_STATES, TRUE_STATES
from .constants_formula import is_ha_state_value, is_ha_unknown_equivalent, normalize_ha_state_value
from .data_validation import validate_data_provider_result
from .exceptions import DataValidationError, MissingDependencyError
from .utils_hass import check_data_provider_conditions, check_hass_lookup_conditions, get_data_provider_callback

_LOGGER = logging.getLogger(__name__)


def resolve_via_data_provider_entity(dependency_handler: Any, entity_id: str, original_reference: str) -> Any | None:
    """Resolve entity via data provider callback.

    This is a shared utility to eliminate duplicate code between entity resolvers.

    Args:
        dependency_handler: The dependency handler for entity resolution
        entity_id: The entity ID to resolve
        original_reference: The original reference for logging

    Returns:
        The resolved entity value or None if not found
    """
    if not check_data_provider_conditions(dependency_handler, entity_id):
        return None

    data_provider_callback = get_data_provider_callback(dependency_handler)
    if not data_provider_callback:
        return None

    try:
        result = data_provider_callback(entity_id)
        # Validate the data provider result according to the guide
        validated_result = validate_data_provider_result(result, f"data provider for '{entity_id}'")

        if validated_result.get("exists"):
            value = validated_result.get("value")
            if value is None:
                _LOGGER.debug(
                    "Entity resolver: entity '%s' exists but has None value, returning unknown state",
                    entity_id,
                )
                return "unknown"  # Use lowercase for HA state consistency

            # Handle special Home Assistant state values
            if isinstance(value, str) and (is_ha_state_value(value) or is_ha_unknown_equivalent(value)):
                _LOGGER.debug("Entity resolver: entity '%s' has %s state via data provider", entity_id, value)
                # Return the normalized HA state value so evaluator can handle it appropriately
                return normalize_ha_state_value(value)

            _LOGGER.debug("Entity resolver: resolved '%s' to %s", entity_id, value)
            return value
    except DataValidationError:
        # Re-raise fatal errors according to the guide
        raise
    except Exception as e:
        _LOGGER.warning("Error resolving entity reference '%s' via data provider: %s", entity_id, e)

    return None


def resolve_via_data_provider_attribute(
    dependency_handler: Any, entity_id: str, attribute_name: str, original_reference: str
) -> Any | None:
    """Resolve entity attribute via data provider callback.

    This is a shared utility to eliminate duplicate code between attribute resolvers.

    Args:
        dependency_handler: The dependency handler for entity resolution
        entity_id: The entity ID to resolve
        attribute_name: The attribute name to resolve
        original_reference: The original reference for logging

    Returns:
        The resolved attribute value or None if not found
    """
    if not check_data_provider_conditions(dependency_handler, entity_id):
        return None

    data_provider_callback = get_data_provider_callback(dependency_handler)
    if not data_provider_callback:
        return None

    try:
        result = data_provider_callback(entity_id)
        validated_result = validate_data_provider_result(result, f"data provider for '{entity_id}'")

        if validated_result.get("exists"):
            # Check if the result has attributes
            attributes = validated_result.get("attributes", {})
            if isinstance(attributes, dict) and attribute_name in attributes:
                attribute_value = attributes[attribute_name]

                # Handle special Home Assistant state values in attributes
                if isinstance(attribute_value, str) and (
                    is_ha_state_value(attribute_value) or is_ha_unknown_equivalent(attribute_value)
                ):
                    _LOGGER.debug(
                        "Attribute resolver: attribute '%s' of entity '%s' has %s state via data provider",
                        attribute_name,
                        entity_id,
                        attribute_value,
                    )
                    return normalize_ha_state_value(attribute_value)

                _LOGGER.debug(
                    "Attribute resolver: resolved '%s' to %s via data provider",
                    original_reference,
                    attribute_value,
                )
                return attribute_value
            _LOGGER.debug(
                "Attribute resolver: attribute '%s' not found in entity '%s' attributes",
                attribute_name,
                entity_id,
            )
            raise MissingDependencyError(f"Attribute '{attribute_name}' not found in entity '{entity_id}'")

        _LOGGER.debug("Attribute resolver: entity '%s' does not exist via data provider", entity_id)
        raise MissingDependencyError(f"Entity '{entity_id}' not found")
    except DataValidationError:
        raise
    except MissingDependencyError:
        raise
    except Exception as e:
        _LOGGER.warning("Error resolving entity attribute '%s' of '%s' via data provider: %s", attribute_name, entity_id, e)

    return None


def _convert_hass_state_value(state_value: str, entity_id: str, hass_state: Any = None) -> Any:
    """Convert HASS state value to appropriate type.

    Args:
        state_value: The raw state value from HASS
        entity_id: The entity ID for logging
        hass_state: The HASS state object for device class information

    Returns:
        The converted value
    """
    # Handle special Home Assistant state values
    if is_ha_state_value(state_value) or is_ha_unknown_equivalent(state_value):
        _LOGGER.debug("Entity resolver: entity '%s' has %s state via HASS", entity_id, state_value)
        return normalize_ha_state_value(state_value)

    # Try to convert to numeric value
    try:
        numeric_value = float(state_value) if "." in state_value else int(state_value)
        _LOGGER.debug("Entity resolver: resolved '%s' to %s via HASS", entity_id, numeric_value)
        return numeric_value
    except ValueError:
        # Handle boolean-like strings
        result = _convert_boolean_state(state_value, entity_id, hass_state)
        if result is not None:
            return result

        # Non-numeric, non-boolean state, return as string
        _LOGGER.debug(
            "Entity resolver: resolved '%s' to '%s' (non-numeric) via HASS",
            entity_id,
            state_value,
        )
        return state_value


def _convert_boolean_state(state_value: str, entity_id: str, hass_state: Any = None) -> float | None:
    """Convert boolean-like state to numeric value.

    Args:
        state_value: The raw state value
        entity_id: The entity ID for logging
        hass_state: The HASS state object for device class information

    Returns:
        Numeric value (1.0 or 0.0) or None if not convertible
    """
    state_str = str(state_value).lower()

    # Basic boolean states
    result = None
    if state_str in TRUE_STATES:
        result = 1.0
        _LOGGER.debug("Entity resolver: resolved '%s' to 1.0 (boolean true) via HASS", entity_id)
    elif state_str in FALSE_STATES:
        result = 0.0
        _LOGGER.debug("Entity resolver: resolved '%s' to 0.0 (boolean false) via HASS", entity_id)

    return result


def resolve_via_hass_entity(dependency_handler: Any, entity_id: str, original_reference: str) -> Any | None:
    """Resolve entity via HASS state lookup.

    This is a shared utility to eliminate duplicate code between entity resolvers.

    Args:
        dependency_handler: The dependency handler for entity resolution
        entity_id: The entity ID to resolve
        original_reference: The original reference for logging

    Returns:
        The resolved entity value or None if not found
    """
    if not check_hass_lookup_conditions(dependency_handler):
        return None

    try:
        hass = dependency_handler.hass
        if not (hass and hasattr(hass, "states")):
            return None

        hass_state = hass.states.get(entity_id)
        if hass_state is None:
            return None

        # Convert state value to appropriate type
        state_value = hass_state.state

        # Handle None state values (startup race condition)
        if state_value is None:
            _LOGGER.debug(
                "Entity resolver: entity '%s' has None state, returning unknown",
                entity_id,
            )
            return "unknown"  # Use lowercase for HA state consistency

        return _convert_hass_state_value(state_value, entity_id, hass_state)
    except Exception as e:
        _LOGGER.warning("Error resolving entity reference '%s' via HASS: %s", entity_id, e)

    return None


def resolve_via_hass_attribute(
    dependency_handler: Any, entity_id: str, attribute_name: str, original_reference: str
) -> Any | None:
    """Resolve entity attribute via HASS state lookup.

    This is a shared utility to eliminate duplicate code between attribute resolvers.

    Args:
        dependency_handler: The dependency handler for entity resolution
        entity_id: The entity ID to resolve
        attribute_name: The attribute name to resolve
        original_reference: The original reference for logging

    Returns:
        The resolved attribute value or None if not found
    """
    if not check_hass_lookup_conditions(dependency_handler):
        return None

    try:
        hass = dependency_handler.hass
        if not (hass and hasattr(hass, "states")):
            return None

        hass_state = hass.states.get(entity_id)
        if hass_state is None:
            _LOGGER.debug("Attribute resolver: entity '%s' not found via HASS", entity_id)
            raise MissingDependencyError(f"Entity '{entity_id}' not found")

        # Check if the attribute exists
        if hasattr(hass_state, "attributes") and attribute_name in hass_state.attributes:
            attribute_value = hass_state.attributes[attribute_name]

            # Handle special Home Assistant state values in attributes
            if isinstance(attribute_value, str) and (
                is_ha_state_value(attribute_value) or is_ha_unknown_equivalent(attribute_value)
            ):
                _LOGGER.debug(
                    "Attribute resolver: attribute '%s' of entity '%s' has %s state via HASS",
                    attribute_name,
                    entity_id,
                    attribute_value,
                )
                return normalize_ha_state_value(attribute_value)

            _LOGGER.debug("Attribute resolver: resolved '%s' to %s via HASS", original_reference, attribute_value)
            return attribute_value
        _LOGGER.debug(
            "Attribute resolver: attribute '%s' not found in entity '%s' via HASS",
            attribute_name,
            entity_id,
        )
        raise MissingDependencyError(f"Attribute '{attribute_name}' not found in entity '{entity_id}'")
    except Exception as e:
        _LOGGER.warning("Error resolving entity attribute '%s' of '%s' via HASS: %s", attribute_name, entity_id, e)

    return None
