"""Data validation utilities for consistent error handling."""

from __future__ import annotations

from typing import Any

from .exceptions import DataValidationError
from .type_definitions import DataProviderResult


def validate_data_provider_result(result: Any, context: str = "data provider") -> DataProviderResult:
    """Validate data provider callback result and raise fatal error for bad data.

    Args:
        result: Result from data provider callback
        context: Context string for error messages

    Returns:
        Valid DataProviderResult

    Raises:
        DataValidationError: If result is invalid (fatal error)
    """
    if result is None:
        raise DataValidationError(
            f"Data provider callback returned None - this is a fatal implementation error. Context: {context}"
        )

    if not isinstance(result, dict):
        raise DataValidationError(
            f"Data provider callback returned invalid type {type(result).__name__}, expected dict. Context: {context}"
        )

    if "value" not in result:
        raise DataValidationError(f"Data provider callback result missing required 'value' key. Context: {context}")

    if "exists" not in result:
        raise DataValidationError(f"Data provider callback result missing required 'exists' key. Context: {context}")

    if not isinstance(result["exists"], bool):
        raise DataValidationError(
            f"Data provider callback 'exists' value must be boolean, got {type(result['exists']).__name__}. Context: {context}"
        )

    return result  # type: ignore[return-value]


def validate_entity_state_value(value: Any, entity_id: str) -> None:
    """Validate entity state value and raise fatal error for None values.

    Args:
        value: Entity state value
        entity_id: Entity ID for error context

    Raises:
        DataValidationError: If value is None (fatal error)
    """
    if value is None:
        raise DataValidationError(
            f"Entity '{entity_id}' has None state value - this indicates the entity is unavailable "
            f"or has invalid data. This is a fatal error."
        )
