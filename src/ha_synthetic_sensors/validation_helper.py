"""Validation helper for data provider results and entity states.

This module provides centralized validation logic for handling data provider callbacks
and entity states throughout the synthetic sensors package.
"""

from __future__ import annotations

import logging
from typing import Any

from .exceptions import MissingDependencyError, NonNumericStateError
from .type_definitions import DataProviderResult

_LOGGER = logging.getLogger(__name__)


class DataValidationError(Exception):
    """Raised when data provider returns invalid data structure."""


def validate_data_provider_result(result: Any, entity_id: str, context: str = "data provider") -> DataProviderResult:
    """Validate and normalize data provider callback result.

    Args:
        result: Raw result from data provider callback
        entity_id: Entity ID being resolved (for error messages)
        context: Context description for error messages

    Returns:
        Validated DataProviderResult

    Raises:
        DataValidationError: If result structure is invalid
        MissingDependencyError: If entity exists but has None value
    """
    # Check if callback returned None (implementation error)
    if result is None:
        raise DataValidationError(
            f"{context} callback returned None for entity '{entity_id}' - "
            "callback should return {{'value': <value>, 'exists': <bool>}}"
        )

    # Check if result is a dictionary with required keys
    if not isinstance(result, dict):
        raise DataValidationError(
            f"{context} callback returned {type(result).__name__} for entity '{entity_id}' - "
            "callback should return {{'value': <value>, 'exists': <bool>}}"
        )

    if "value" not in result or "exists" not in result:
        missing_keys = [key for key in ["value", "exists"] if key not in result]
        raise DataValidationError(
            f"{context} callback result missing required keys {missing_keys} for entity '{entity_id}' - "
            "callback should return {{'value': <value>, 'exists': <bool>}}"
        )

    # Extract values
    value = result["value"]
    exists = result["exists"]

    # Validate exists is boolean
    if not isinstance(exists, bool):
        raise DataValidationError(
            f"{context} callback returned non-boolean 'exists' ({type(exists).__name__}) "
            f"for entity '{entity_id}' - 'exists' should be True or False"
        )

    # Check for entity doesn't exist
    if not exists:
        raise MissingDependencyError(f"Entity '{entity_id}' not found by {context}")

    # Check for entity exists but has None value (unavailable)
    if value is None:
        raise MissingDependencyError(f"Entity '{entity_id}' exists but has None value - entity is unavailable")

    # Return validated result
    return {"value": value, "exists": exists}


def validate_entity_state(state: Any, entity_id: str, context: str = "entity state") -> Any:
    """Validate entity state value.

    Args:
        state: Entity state value
        entity_id: Entity ID (for error messages)
        context: Context description for error messages

    Returns:
        Validated state value

    Raises:
        MissingDependencyError: If state is None or invalid
    """
    if state is None:
        raise MissingDependencyError(f"Entity '{entity_id}' has None state - entity is unavailable")

    # Could add additional state validation here if needed
    # (e.g., check for "unknown", "unavailable" states)

    return state


def is_valid_numeric_state(state: Any) -> bool:
    """Check if a state value can be converted to a number.

    Args:
        state: State value to check

    Returns:
        True if state can be converted to float, False otherwise
    """
    if state is None:
        return False

    try:
        float(state)
        return True
    except (ValueError, TypeError):
        return False


def convert_to_numeric(state: Any, entity_id: str) -> float:
    """Convert state to numeric value.

    Args:
        state: State value to convert
        entity_id: Entity ID for error messages

    Returns:
        Numeric value

    Raises:
        NonNumericStateError: If state cannot be converted to number
    """
    if state is None:
        raise NonNumericStateError(entity_id, "None")

    try:
        return float(state)
    except (ValueError, TypeError) as e:
        raise NonNumericStateError(entity_id, str(state)) from e
