"""Centralized manager for ReferenceValue objects to ensure type safety."""

from collections.abc import Callable
import logging
from typing import Any, cast

from homeassistant.core import State
from homeassistant.helpers.typing import ConfigType

from .type_definitions import ContextValue, EvaluationContext, ReferenceValue

_LOGGER = logging.getLogger(__name__)


class ReferenceValueManager:
    """Centralized manager for ReferenceValue objects ensuring type safety."""

    @staticmethod
    def set_variable_with_reference_value(
        eval_context: dict[str, ContextValue], var_name: str, var_value: Any, resolved_value: Any
    ) -> None:
        """Set a variable in evaluation context using entity-centric ReferenceValue approach.

        This is the ONLY way variables should be set in eval_context to ensure type safety.

        Args:
            eval_context: The evaluation context to modify
            var_name: The variable name
            var_value: The original variable value (entity ID or reference)
            resolved_value: The resolved state value
        """
        # Entity-centric ReferenceValue registry: one ReferenceValue per unique entity_id
        entity_registry_key = "_entity_reference_registry"
        if entity_registry_key not in eval_context:
            eval_context[entity_registry_key] = {}
        entity_registry: dict[str, ReferenceValue] = eval_context[entity_registry_key]  # type: ignore

        # Determine the canonical entity reference (the final entity_id)
        entity_reference = var_value if isinstance(var_value, str) else str(var_value)

        # Check if we already have a ReferenceValue for this entity
        if entity_reference in entity_registry:
            # Reuse existing ReferenceValue for this entity
            existing_ref_value = entity_registry[entity_reference]
            eval_context[var_name] = existing_ref_value
            _LOGGER.debug(
                "ReferenceValueManager: %s reusing existing ReferenceValue for entity %s: value=%s",
                var_name,
                entity_reference,
                existing_ref_value.value,
            )
        else:
            # Create new ReferenceValue for this entity
            # Prevent double wrapping of ReferenceValue objects
            if isinstance(resolved_value, ReferenceValue):
                # If resolved_value is already a ReferenceValue, use it directly
                ref_value = resolved_value
                # Update the registry with the existing ReferenceValue
                entity_registry[entity_reference] = ref_value
                eval_context[var_name] = ref_value
            else:
                # Create new ReferenceValue for raw values
                ref_value = ReferenceValue(reference=entity_reference, value=resolved_value)
                entity_registry[entity_reference] = ref_value
                eval_context[var_name] = ref_value
            _LOGGER.debug(
                "ReferenceValueManager: %s created new ReferenceValue for entity %s: value=%s",
                var_name,
                entity_reference,
                resolved_value,
            )

    @staticmethod
    def convert_to_evaluation_context(context: dict[str, ContextValue]) -> EvaluationContext:
        """Convert a context with possible raw values to a type-safe EvaluationContext.

        This enforces that only ReferenceValue objects and other allowed types are in the result.

        Args:
            context: Context that may contain raw values

        Returns:
            Type-safe EvaluationContext with only ReferenceValue objects for variables

        Raises:
            TypeError: If context contains raw values that can't be converted
        """
        evaluation_context: EvaluationContext = {}

        for key, value in context.items():
            if isinstance(value, ReferenceValue | type(None)) or callable(value) or key.startswith("_"):
                # These are allowed in EvaluationContext
                evaluation_context[key] = cast(ReferenceValue | Callable[..., Any] | State | ConfigType | None, value)
            elif isinstance(value, State):
                # State objects are allowed in EvaluationContext
                evaluation_context[key] = cast(ReferenceValue | Callable[..., Any] | State | ConfigType | None, value)
            elif isinstance(value, dict):
                # ConfigType (dict) is allowed in EvaluationContext
                evaluation_context[key] = cast(ReferenceValue | Callable[..., Any] | State | ConfigType | None, value)
            elif isinstance(value, str | int | float | bool):
                # Raw values are NOT allowed - this is a type safety violation
                _LOGGER.error(
                    "TYPE SAFETY VIOLATION: Variable '%s' has raw value '%s' instead of ReferenceValue",
                    key,
                    value,
                )
                raise TypeError(
                    f"Context contains raw value for variable '{key}': {type(value).__name__}: {value}. All variables must be ReferenceValue objects."
                )
            else:
                # Other types might be allowed, log for investigation
                _LOGGER.debug("Converting context: allowing type %s for key '%s'", type(value).__name__, key)
                evaluation_context[key] = cast(ReferenceValue | Callable[..., Any] | State | ConfigType | None, value)

        return evaluation_context
