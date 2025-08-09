"""Type-safe evaluation context that enforces ReferenceValue objects."""

import logging
from typing import Any

from .reference_value_manager import ReferenceValueManager
from .type_definitions import ContextValue, EvaluationContext, ReferenceValue

_LOGGER = logging.getLogger(__name__)


class TypeSafeEvaluationContext(dict[str, ContextValue]):
    """Type-safe evaluation context that automatically converts raw values to ReferenceValue objects.

    This context wrapper ensures that all variable assignments go through the ReferenceValueManager,
    preventing raw values from leaking into the evaluation context.
    """

    def __setitem__(self, key: str, value: ContextValue) -> None:
        """Override assignment to enforce ReferenceValue creation for variables."""
        # Allow special keys and already-converted ReferenceValue objects
        if key.startswith("_") or isinstance(value, ReferenceValue) or callable(value) or value is None:
            super().__setitem__(key, value)
            return

        # For raw values that should be variables, this is a type safety violation
        if isinstance(value, str | int | float | bool):
            _LOGGER.error("TYPE SAFETY VIOLATION: Attempt to set raw value for variable '%s': %s", key, value)
            _LOGGER.error("All variables must use ReferenceValueManager.set_variable_with_reference_value()")
            raise TypeError(f"Raw value assignment blocked for variable '{key}': {type(value).__name__}: {value}")

        # Allow other types (State, ConfigType, etc.)
        super().__setitem__(key, value)

    def set_variable_with_reference(self, var_name: str, var_value: Any, resolved_value: Any) -> None:
        """Type-safe method to set variables using ReferenceValueManager."""
        ReferenceValueManager.set_variable_with_reference_value(self, var_name, var_value, resolved_value)

    def to_evaluation_context(self) -> EvaluationContext:
        """Convert to type-safe EvaluationContext for handlers."""
        return ReferenceValueManager.convert_to_evaluation_context(self)
