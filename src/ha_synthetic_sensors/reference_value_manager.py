"""Centralized manager for ReferenceValue objects to ensure type safety."""

from collections.abc import Callable
import logging
from typing import TYPE_CHECKING, Any, ClassVar, cast

from homeassistant.core import State
from homeassistant.helpers.typing import ConfigType

from .context_utils import safe_context_set
from .type_definitions import ContextValue, EvaluationContext, ReferenceValue

if TYPE_CHECKING:
    from .hierarchical_context_dict import HierarchicalContextDict

_LOGGER = logging.getLogger(__name__)


class ReferenceValueManager:
    """Centralized manager for ReferenceValue objects ensuring type safety."""

    # Internal cache for entity deduplication - completely hidden from user context
    _entity_cache: ClassVar[dict[str, ReferenceValue]] = {}

    @staticmethod
    def set_variable_with_reference_value(
        eval_context: "HierarchicalContextDict", var_name: str, var_value: Any, resolved_value: Any, force_update: bool = False
    ) -> None:
        """Set a variable in evaluation context using entity-centric ReferenceValue approach.

        This is the ONLY way variables should be set in eval_context to ensure type safety.

        Args:
            eval_context: The evaluation context to modify
            var_name: The variable name
            var_value: The original variable value (entity ID or reference)
            resolved_value: The resolved state value
            force_update: If True, force creation of new ReferenceValue even if entity is cached
        """
        # Debug: Check what type of context we received
        _LOGGER.debug(
            "REF_VALUE_MGR_CONTEXT_TYPE: Received context type %s for variable %s", type(eval_context).__name__, var_name
        )

        # Use internal cache for entity deduplication (hidden from user context)
        entity_reference = var_value if isinstance(var_value, str) else str(var_value)

        # Check internal cache for existing ReferenceValue
        if entity_reference in ReferenceValueManager._entity_cache and not force_update:
            # Reuse existing ReferenceValue for this entity (deduplication)
            existing_ref_value = ReferenceValueManager._entity_cache[entity_reference]
            safe_context_set(eval_context, var_name, existing_ref_value)

            # WFF FIX: Also store varaible name under entity ID for dependency resolution
            # This ensures that future references to the same entity ID can find the resolved value
            if isinstance(var_value, str) and var_value != var_name and "." in var_value:
                safe_context_set(eval_context, var_value, existing_ref_value)

            _LOGGER.debug(
                "ReferenceValueManager: %s reusing existing ReferenceValue for entity %s: value=%s",
                var_name,
                entity_reference,
                getattr(existing_ref_value, "value", existing_ref_value),
            )
        else:
            # Create new ReferenceValue for this entity
            # Prevent double wrapping of ReferenceValue objects
            if isinstance(resolved_value, ReferenceValue):
                # If resolved_value is already a ReferenceValue, use it directly
                ref_value = resolved_value
            else:
                # Create new ReferenceValue for raw values
                ref_value = ReferenceValue(reference=entity_reference, value=resolved_value)

            # Cache internally for future deduplication
            ReferenceValueManager._entity_cache[entity_reference] = ref_value

            # Set in user context under variable name
            safe_context_set(eval_context, var_name, ref_value)

            # : Also store under entity ID for dependency resolution
            # This ensures that dependency checking can find already-resolved entities
            if isinstance(var_value, str) and var_value != var_name and "." in var_value:
                safe_context_set(eval_context, var_value, ref_value)
                _LOGGER.debug(
                    "ReferenceValueManager: %s also stored under entity ID %s for dependency resolution",
                    var_name,
                    var_value,
                )

            # Debug logging for grace period and False values
            action = (
                "force updated" if force_update and entity_reference in ReferenceValueManager._entity_cache else "created new"
            )
            _LOGGER.debug(
                "ReferenceValueManager: %s %s ReferenceValue for entity %s: value=%s",
                var_name,
                action,
                entity_reference,
                resolved_value,
            )

    @staticmethod
    def clear_cache() -> None:
        """Clear the internal entity cache. Used for testing and cleanup."""
        ReferenceValueManager._entity_cache.clear()

    @staticmethod
    def invalidate_entities(entity_ids: set[str]) -> None:
        """Invalidate cached ReferenceValues for specific entities.

        This forces fresh resolution of the specified entities on next access.

        Args:
            entity_ids: Set of entity IDs to invalidate from cache
        """
        invalidated_count = 0
        for entity_id in entity_ids:
            if entity_id in ReferenceValueManager._entity_cache:
                del ReferenceValueManager._entity_cache[entity_id]
                invalidated_count += 1

        if invalidated_count > 0:
            _LOGGER.debug("ReferenceValueManager: Invalidated %d cached entities: %s", invalidated_count, list(entity_ids))

    @staticmethod
    def get_cache_stats() -> dict[str, Any]:
        """Get statistics about the internal cache. Used for debugging."""
        return {
            "cached_entities": len(ReferenceValueManager._entity_cache),
            "entities": list(ReferenceValueManager._entity_cache.keys()),
        }

    @staticmethod
    def is_entity_cached(entity_reference: str) -> bool:
        """Check if an entity is already cached."""
        return entity_reference in ReferenceValueManager._entity_cache

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
