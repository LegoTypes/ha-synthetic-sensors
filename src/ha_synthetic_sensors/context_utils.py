"""Utility functions for safe context operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .type_definitions import ContextValue, ReferenceValue

if TYPE_CHECKING:
    from .hierarchical_context_dict import HierarchicalContextDict


def get_context_value(context: dict[str, ContextValue], key: str) -> ContextValue | None:
    """Get a value from context with proper type handling.

    This function enforces the ReferenceValue architecture by ensuring that only
    properly wrapped values are returned from context.

    Args:
        context: The context dictionary (must not be None)
        key: The key to retrieve

    Returns:
        ReferenceValue object or None if key not found

    Raises:
        ValueError: If context contains raw values (architecture violation)
    """
    value = context.get(key)
    if value is None:
        return None

    # If we got a raw value from context, this violates the architecture
    if not isinstance(value, ReferenceValue):
        raise ValueError(
            f"Context contains raw value '{value}' (type: {type(value).__name__}) "
            f"for key '{key}'. All variables must be ReferenceValue objects. "
            f"This indicates a critical bug where raw values bypassed "
            f"all validation layers. Check the variable resolution system and "
            f"ensure all context modifications go through safe_context_set() "
            f"or the unified setter."
        )

    return value


def set_context_value(context: dict[str, ContextValue], key: str, value: ContextValue) -> None:
    """Set a value in context, enforcing ReferenceValue architecture.

    This function enforces the ReferenceValue architecture by preventing raw values
    from being stored in context. All variables must be ReferenceValue objects.

    Args:
        context: The context dictionary
        key: The key to set
        value: The value to set (must be ReferenceValue or allowed type)

    Raises:
        ValueError: If attempting to store raw values in context
    """
    # CRITICAL: Enforce ReferenceValue architecture
    if not isinstance(value, ReferenceValue):
        # This is a raw value being stored in context - this violates the architecture
        raise ValueError(
            f"Attempted to store raw value '{value}' (type: {type(value).__name__}) "
            f"for key '{key}' in context. All variables must be ReferenceValue objects. "
            f"This indicates a bug in the variable resolution system where raw values "
            f"are reaching the context instead of being properly wrapped in ReferenceValue objects."
        )

    context[key] = value


def has_context_key(context: dict[str, ContextValue] | None, key: str) -> bool:
    """Check if context has a key.

    Args:
        context: The context dictionary (may be None)
        key: The key to check

    Returns:
        True if key exists
    """
    if context is None:
        return False
    return key in context


def extract_numeric_values(context: dict[str, ContextValue]) -> dict[str, float | int]:
    """Extract numeric values from context for formula evaluation, enforcing ReferenceValue architecture.

    This function only accepts ReferenceValue objects and extracts their numeric values.
    Raw numeric values are not allowed as they violate the architecture.

    Args:
        context: The context dictionary containing ReferenceValue objects

    Returns:
        Dictionary mapping keys to numeric values extracted from ReferenceValue objects

    Raises:
        ValueError: If context contains raw numeric values (architecture violation)
    """
    numeric_context: dict[str, float | int] = {}
    for key, value in context.items():
        if isinstance(value, int | float):
            # CRITICAL: Raw numeric values in context violate the ReferenceValue architecture
            raise ValueError(
                f"Context contains raw numeric value '{value}' (type: {type(value).__name__}) "
                f"for key '{key}'. All variables must be ReferenceValue objects. "
                f"Use ReferenceValueManager to wrap values."
            )
        if isinstance(value, ReferenceValue) and isinstance(value.value, int | float):
            # Handle ReferenceValue objects - extract the numeric value
            numeric_context[key] = value.value
        elif isinstance(value, ReferenceValue) and value.value is not None:
            # Try to convert non-numeric values to numbers if possible
            try:
                numeric_value = float(value.value)
                numeric_context[key] = numeric_value
            except (ValueError, TypeError):
                # Skip values that can't be converted to numbers
                continue
        else:
            # Skip None values or ReferenceValue objects with None values
            continue

    return numeric_context


def extract_string_values(context: dict[str, ContextValue]) -> dict[str, str]:
    """Extract string values from context, enforcing ReferenceValue architecture.

    This function only accepts ReferenceValue objects and extracts their string values.
    Raw string values are not allowed as they violate the architecture.

    Args:
        context: The context dictionary containing ReferenceValue objects

    Returns:
        Dictionary mapping keys to string values extracted from ReferenceValue objects

    Raises:
        ValueError: If context contains raw string values (architecture violation)
    """
    string_context: dict[str, str] = {}
    for key, value in context.items():
        if isinstance(value, str):
            # CRITICAL: Raw strings in context violate the ReferenceValue architecture
            raise ValueError(
                f"Context contains raw string '{value}' for key '{key}'. "
                f"All variables must be ReferenceValue objects. "
                f"Use ReferenceValueManager to wrap values."
            )
        if isinstance(value, ReferenceValue) and isinstance(value.value, str):
            # Handle ReferenceValue objects - extract the string value
            string_context[key] = value.value
        elif isinstance(value, ReferenceValue) and value.value is not None:
            # Handle ReferenceValue objects with non-string values - convert to string
            string_context[key] = str(value.value)
        else:
            # Skip None values or ReferenceValue objects with None values
            continue

    return string_context


def get_reference_value(context: dict[str, ContextValue], key: str) -> ContextValue | None:
    """Get a ReferenceValue from context, handling both direct values and ReferenceValue objects.

    This function enforces the ReferenceValue architecture by ensuring that only
    properly wrapped values are returned from context.

    Args:
        context: The context dictionary
        key: The key to retrieve

    Returns:
        ReferenceValue object or None if not found

    Raises:
        ValueError: If context contains raw values (architecture violation)
    """
    value = context.get(key)
    if value is None:
        return None

    # If it's already a ReferenceValue-like object with .value and .reference, return as-is
    if isinstance(value, ReferenceValue):
        return value

    # CRITICAL: This should never happen in the new architecture
    # If we find raw values in context, it means the setter validation failed
    # or there's a bug in the variable resolution system
    raise ValueError(
        f"Context contains raw value '{value}' (type: {type(value).__name__}) "
        f"for key '{key}'. This indicates a critical bug where raw values bypassed "
        f"the setter validation. All variables must be ReferenceValue objects. "
        f"Check the variable resolution system and ensure all context modifications "
        f"go through safe_context_set() or the unified setter."
    )


# Legacy functions for backward compatibility
def safe_context_set(context: HierarchicalContextDict, key: str, value: ContextValue) -> None:
    """Safely set a value in context, using unified setter if available.

    This function enforces the ReferenceValue architecture by preventing raw values
    from being stored in context. All variables must be ReferenceValue objects.

    Args:
        context: The context dictionary (may be HierarchicalContextDict)
        key: The key to set
        value: The value to set (must be ReferenceValue or allowed type)

    Raises:
        ValueError: If attempting to store raw values in context
    """
    # CRITICAL: Enforce ReferenceValue architecture
    if not isinstance(value, ReferenceValue):
        # This is a raw value being stored in context - this violates the architecture
        raise ValueError(
            f"Attempted to store raw value '{value}' (type: {type(value).__name__}) "
            f"for key '{key}' in context. All variables must be ReferenceValue objects. "
            f"This indicates a bug in the variable resolution system where raw values "
            f"are reaching the context instead of being properly wrapped in ReferenceValue objects."
        )

    if hasattr(context, "_hierarchical_context"):
        # This is our HierarchicalContextDict - use unified setter
        context._hierarchical_context.set(key, value)  # pylint: disable=protected-access
    else:
        # Regular dict - use direct assignment
        context[key] = value


def safe_context_get(context: HierarchicalContextDict, key: str) -> ContextValue:
    """Safely get a value from context, enforcing ReferenceValue architecture.

    This function enforces the ReferenceValue architecture by ensuring that only
    properly wrapped values are returned from context.

    Args:
        context: The context dictionary (may be HierarchicalContextDict)
        key: The key to retrieve

    Returns:
        ReferenceValue object

    Raises:
        KeyError: If key not found in context
        ValueError: If context contains raw values (architecture violation)

    Raises:
        ValueError: If context contains raw values (architecture violation)
    """
    value = context._hierarchical_context.get(key) if hasattr(context, "_hierarchical_context") else context.get(key)  # pylint: disable=protected-access

    # If we got a raw value from context, this violates the architecture
    if not isinstance(value, ReferenceValue):
        raise ValueError(
            f"Context contains raw value '{value}' (type: {type(value).__name__}) "
            f"for key '{key}'. All variables must be ReferenceValue objects. "
            f"This indicates a critical bug where raw values bypassed "
            f"all validation layers. Check the variable resolution system and "
            f"ensure all context modifications go through safe_context_set() "
            f"or the unified setter."
        )

    return value


def safe_context_contains(context: HierarchicalContextDict, key: str) -> bool:
    """Safely check if key exists in context.

    Args:
        context: The context dictionary (may be HierarchicalContextDict)
        key: The key to check

    Returns:
        True if key exists
    """
    if hasattr(context, "_hierarchical_context"):
        # This is our HierarchicalContextDict - use hierarchical contains
        hierarchical_context = context._hierarchical_context  # pylint: disable=protected-access
        return bool(hierarchical_context.has(key))
    # Regular dict - use normal contains
    return key in context
