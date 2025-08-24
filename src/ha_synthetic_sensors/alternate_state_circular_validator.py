"""Circular dependency detection for alternate state handlers.

This module validates that alternate state handlers don't create circular references
that would cause infinite loops during evaluation.
"""

from __future__ import annotations

from typing import Any

from .config_models import AlternateStateHandler
from .constants_alternate import STATE_NONE_YAML


class CircularDependencyError(ValueError):
    """Raised when circular dependencies are detected in alternate state handlers."""


def validate_alternate_state_handler_circular_deps(handler: AlternateStateHandler) -> None:
    """Validate that alternate state handlers don't have circular dependencies.

    Args:
        handler: The alternate state handler to validate

    Raises:
        CircularDependencyError: If circular dependencies are detected
    """
    if not handler:
        return

    # Map of handler types to their values
    handlers = {
        "unavailable": handler.unavailable,
        "unknown": handler.unknown,
        "none": handler.none,
        "fallback": handler.fallback,
    }

    # Check each handler for circular references
    for handler_type, handler_value in handlers.items():
        if handler_value is not None:
            _check_handler_for_circular_deps(handler_type, handler_value, handlers, set())


def _check_handler_for_circular_deps(
    current_handler: str, handler_value: Any, all_handlers: dict[str, Any], visited: set[str]
) -> None:
    """Recursively check a handler for circular dependencies.

    Args:
        current_handler: The current handler type being checked
        handler_value: The value of the current handler
        all_handlers: All handlers in the alternate state handler
        visited: Set of already visited handlers (for cycle detection)

    Raises:
        CircularDependencyError: If a circular dependency is detected
    """
    if current_handler in visited:
        cycle_path = " -> ".join(visited) + f" -> {current_handler}"
        raise CircularDependencyError(f"Circular dependency detected in alternate state handlers: {cycle_path}")

    visited.add(current_handler)

    # Check if this handler references another state that would trigger another handler
    referenced_states = _extract_state_references(handler_value)

    for state in referenced_states:
        # Map state references to handler types
        state_to_handler = {"STATE_NONE": "none", "STATE_UNKNOWN": "unknown", "STATE_UNAVAILABLE": "unavailable"}

        if state in state_to_handler:
            referenced_handler = state_to_handler[state]
            if referenced_handler in all_handlers and all_handlers[referenced_handler] is not None:
                # Recursively check the referenced handler
                _check_handler_for_circular_deps(
                    referenced_handler,
                    all_handlers[referenced_handler],
                    all_handlers,
                    visited.copy(),  # Use copy to allow multiple paths
                )

    visited.remove(current_handler)


def _extract_state_references(handler_value: Any) -> set[str]:
    """Extract state references from a handler value.

    Args:
        handler_value: The handler value to check for state references

    Returns:
        Set of state references found in the handler value
    """
    references = set()

    if isinstance(handler_value, str):
        # Check for direct state references
        if handler_value == STATE_NONE_YAML:
            references.add("STATE_NONE")
        elif handler_value == "STATE_UNKNOWN":
            references.add("STATE_UNKNOWN")
        elif handler_value == "STATE_UNAVAILABLE":
            references.add("STATE_UNAVAILABLE")
        # Check for state references in formula strings
        elif "STATE_NONE" in handler_value:
            references.add("STATE_NONE")
        elif "STATE_UNKNOWN" in handler_value:
            references.add("STATE_UNKNOWN")
        elif "STATE_UNAVAILABLE" in handler_value:
            references.add("STATE_UNAVAILABLE")

    elif isinstance(handler_value, dict) and "formula" in handler_value:
        # Check object form handlers
        formula = str(handler_value["formula"])
        if "STATE_NONE" in formula:
            references.add("STATE_NONE")
        if "STATE_UNKNOWN" in formula:
            references.add("STATE_UNKNOWN")
        if "STATE_UNAVAILABLE" in formula:
            references.add("STATE_UNAVAILABLE")

    return references
