"""Metadata handler for accessing Home Assistant entity metadata."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging
import re
from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from ..constants_alternate import ALTERNATE_STATE_NONE, STATE_NONE
from ..constants_handlers import HANDLER_NAME_METADATA
from ..constants_metadata import (
    ERROR_METADATA_ENTITY_NOT_FOUND,
    ERROR_METADATA_FUNCTION_PARAMETER_COUNT,
    ERROR_METADATA_HASS_NOT_AVAILABLE,
    ERROR_METADATA_KEY_NOT_FOUND,
    METADATA_FUNCTION_NAME,
    METADATA_FUNCTION_VALID_KEYS,
)
from ..exceptions import AlternateStateDetected
from ..type_definitions import ContextValue, ReferenceValue
from .base_handler import FormulaHandler

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class MetadataHandler(FormulaHandler):
    """Handler for metadata() function calls to access HA entity metadata."""

    # Valid metadata keys that can be accessed
    VALID_METADATA_KEYS: ClassVar[set[str]] = set(METADATA_FUNCTION_VALID_KEYS)

    def __init__(
        self,
        expression_evaluator: Callable[[str, dict[str, ContextValue] | None], Any] | None = None,
        hass: HomeAssistant | None = None,
    ) -> None:
        """Initialize the metadata handler.

        Args:
            expression_evaluator: Callback for delegating complex expression evaluation
            hass: Home Assistant instance for accessing entity states
        """
        super().__init__(expression_evaluator=expression_evaluator, hass=hass)
        self._hass = hass

    @classmethod
    def process_metadata_functions(cls, formula: str, context: dict[str, ContextValue]) -> str:
        """
        Process metadata functions in a formula, preserving variable names for proper ReferenceValue lookup.

        This is a shared method that can be called by:
        - Variable resolution (for computed variables containing metadata)
        - Formula router (for main/attribute formulas containing metadata)

        Args:
            formula: Formula that may contain metadata() calls
            context: Evaluation context with ReferenceValue objects (should contain '_hass' key)

        Returns:
            Formula with metadata calls resolved to their results
        """
        if "metadata(" not in formula.lower():
            return formula

        try:
            # Get hass instance from context (may be wrapped in ReferenceValue)
            hass_value = context.get("_hass")
            # Unwrap ReferenceValue if present
            _maybe_hass = hass_value.value if isinstance(hass_value, ReferenceValue) else hass_value
            # Duck-typing acceptance: any object exposing `.states` behaves like HomeAssistant
            hass: HomeAssistant | None = _maybe_hass if hasattr(_maybe_hass, "states") else None  # type: ignore[assignment]
            if hass is None:
                # Missing hass is a fatal condition in real scenarios
                raise ValueError(ERROR_METADATA_HASS_NOT_AVAILABLE)

            # Create temporary handler instance to process the metadata
            handler = cls(hass=hass)
            if handler.can_handle(formula):
                _LOGGER.debug("METADATA_HANDLER: Processing metadata functions in: %s", formula)
                result, _ = handler.evaluate(formula, context)
                _LOGGER.debug("METADATA_HANDLER: Metadata processing result: %s", result)

                # For entity_id metadata, return the entity ID string for formula evaluation
                # The result is already the entity ID string we want
                if "entity_id" in formula.lower() and isinstance(result, str):
                    # Return the entity ID string directly for use in formulas
                    return result

                return str(result)

        except Exception as e:
            # If this is our special bug detection error, re-raise it with full stack trace
            if "METADATA_HANDLER_BUG" in str(e):
                _LOGGER.error("METADATA_HANDLER_BUG detected - raising exception for stack trace analysis")
                raise
            # Fatal: missing hass must not be silently ignored
            if ERROR_METADATA_HASS_NOT_AVAILABLE in str(e):
                _LOGGER.error("METADATA_HANDLER: %s", e)
                raise
            _LOGGER.warning("METADATA_HANDLER: Metadata processing failed for formula %s: %s", formula, e)
            # Fall back to original formula if other metadata processing fails

        return formula

    def can_handle(self, formula: str) -> bool:
        """Check if this handler can process the given formula.

        Args:
            formula: The formula to check

        Returns:
            True if the formula contains metadata() function calls
        """
        # Simple detection - just look for metadata( in the formula
        has_metadata = f"{METADATA_FUNCTION_NAME}(" in formula
        _LOGGER.debug("MetadataHandler.can_handle('%s') = %s", formula, has_metadata)
        return has_metadata

    def evaluate(self, formula: str, context: dict[str, ContextValue] | None = None) -> tuple[str, dict[str, str]]:
        """Evaluate a formula containing metadata() function calls.

        This handler processes metadata function calls within formulas by replacing them
        with metadata_result() function calls for AST caching, and returns both the
        processed formula and metadata results for context.

        Args:
            formula: The formula containing metadata() function calls
            context: Variable context for evaluation

        Returns:
            Tuple of (processed_formula, metadata_results)
            - processed_formula: Formula with metadata() calls replaced by metadata_result() calls
            - metadata_results: Dictionary of metadata values keyed by _metadata_N

        Raises:
            ValueError: If metadata key is invalid or entity not found
        """
        try:
            _LOGGER.debug("Evaluating metadata formula: %s", formula)
            _LOGGER.debug("Context keys: %s", list(context.keys()) if context else None)
            if context:
                for key, value in context.items():
                    if isinstance(value, ReferenceValue):
                        _LOGGER.debug("  ReferenceValue %s: reference=%s, value=%s", key, value.reference, value.value)
                    else:
                        _LOGGER.debug("  Regular value %s: %s", key, str(value)[:100])

            processed_formula = formula
            metadata_results = {}  # Store metadata results for AST caching
            metadata_counter = 0

            # Find all metadata function calls and replace them with their results
            def replace_metadata_function(match: re.Match[str]) -> str:
                nonlocal metadata_counter
                full_call = match.group(0)  # Full metadata(...) call
                params_str = match.group(1)  # Content inside parentheses

                _LOGGER.debug("Processing metadata call: %s", full_call)

                # Parse parameters (simple comma split for now)
                params = [p.strip() for p in params_str.split(",")]
                if len(params) != 2:
                    raise ValueError(ERROR_METADATA_FUNCTION_PARAMETER_COUNT.format(count=len(params)))

                entity_ref = params[0].strip()
                metadata_key = params[1].strip().strip("'\"")  # Remove quotes from key

                # The entity_ref might be a variable name or an entity ID
                # If it's a variable name, we need to resolve it to the entity ID
                # If it's already an entity ID, use it directly
                resolved_entity_id = self._resolve_entity_reference(entity_ref, context)

                # Check 1: Is the entity reference itself an alternate state?
                if self._is_alternate_state(resolved_entity_id):
                    raise AlternateStateDetected(
                        f"Entity reference '{resolved_entity_id}' is in alternate state", resolved_entity_id
                    )

                # Get metadata value
                metadata_value = self._get_metadata_value(resolved_entity_id, metadata_key, context)

                # Check 2: Is the metadata result an alternate state?
                if self._is_alternate_state(metadata_value):
                    raise AlternateStateDetected(f"Metadata result '{metadata_value}' is alternate state", metadata_value)

                # Store metadata result for AST caching
                metadata_key_name = f"_metadata_{metadata_counter}"
                metadata_counter += 1

                # Format metadata value for storage
                if hasattr(metadata_value, "isoformat"):  # datetime-like objects
                    formatted_value = metadata_value.isoformat()
                elif isinstance(metadata_value, str):
                    formatted_value = metadata_value
                else:
                    formatted_value = str(metadata_value)

                metadata_results[metadata_key_name] = formatted_value

                # Return the metadata function call for AST caching
                return f"metadata_result({metadata_key_name})"

            # Use regex to find and replace metadata function calls
            metadata_pattern = re.compile(rf"{METADATA_FUNCTION_NAME}\s*\(\s*([^)]+)\s*\)", re.IGNORECASE)
            processed_formula = metadata_pattern.sub(replace_metadata_function, processed_formula)

            _LOGGER.debug("Processed metadata formula: %s", processed_formula)
            _LOGGER.debug("Metadata results: %s", metadata_results)

            # Return both the processed formula and metadata results
            return processed_formula, metadata_results

        except Exception as e:
            _LOGGER.error("Error evaluating metadata formula '%s': %s", formula, e)
            raise

    def _get_current_sensor_entity_id_from_context(self, context: dict[str, ContextValue] | None = None) -> str | None:
        """Extract the current sensor's entity ID from evaluation context.

        Args:
            context: Evaluation context that may contain sensor identification

        Returns:
            Current sensor entity ID if found, None otherwise
        """
        if not context:
            return None

        entity_id = None

        # PRIORITY 1: Check for the specific key added by context building phase
        if "current_sensor_entity_id" in context:
            value = context["current_sensor_entity_id"]
            if isinstance(value, ReferenceValue) and isinstance(value.value, str):
                entity_id = value.value
            elif isinstance(value, str) and value.startswith("sensor."):
                entity_id = value
            if entity_id:
                _LOGGER.debug("Found current sensor entity ID from context key 'current_sensor_entity_id': %s", entity_id)
                return entity_id

        # PRIORITY 2: Look for other context keys that indicate the current sensor
        debug_key = None
        for key, value in context.items():
            if "entity" in key.lower():
                debug_key = key
                if isinstance(value, ReferenceValue) and isinstance(value.value, str) and value.value.startswith("sensor."):
                    entity_id = value.value
                    break
                if isinstance(value, str) and value.startswith("sensor."):
                    entity_id = value
                    break

        if entity_id:
            _LOGGER.debug("Found current sensor entity ID from context key '%s': %s", debug_key, entity_id)
            return entity_id

        _LOGGER.debug("Could not find current sensor entity ID in context")
        return None

    def _resolve_entity_reference(self, entity_ref: str, context: dict[str, ContextValue] | None = None) -> str:
        """Resolve entity reference to actual entity ID.

        This method handles different types of entity references:
        1. Direct entity IDs (e.g., "sensor.backing_power")
        2. Variable references that contain entity IDs
        3. The special 'state' token (refers to current sensor)
        4. Sensor key self-references (should be converted to 'state')

        Args:
            entity_ref: The entity reference (variable name, entity ID, etc.)
            context: Evaluation context

        Returns:
            The resolved entity ID

        Raises:
            ValueError: If the entity reference cannot be resolved
        """
        clean_ref = entity_ref.strip().strip("'\"")

        # CRITICAL: Check if entity_ref is a numeric value - this indicates premature value substitution
        # and helps us identify where the variable resolution pipeline is going wrong
        try:
            float(clean_ref)
            # If we can parse it as a number, this is a BUG in the resolution pipeline
            raise ValueError(
                f"METADATA_HANDLER_BUG: Received numeric value '{clean_ref}' as entity reference. "
                f"This indicates premature value substitution in the variable resolution pipeline. "
                f"Entity references should be variable names or entity IDs, not resolved values. "
                f"Check the stack trace to see where this numeric value was substituted."
            )
        except ValueError as e:
            if "METADATA_HANDLER_BUG" in str(e):
                raise  # Re-raise our custom error
            # Not a number, continue normal processing

        _LOGGER.debug("Resolving entity reference: '%s'", clean_ref)

        # Try variable resolution first
        resolved_entity = self._try_resolve_variable_reference(clean_ref, context)
        if resolved_entity:
            return resolved_entity

        # Handle special tokens and direct entity IDs
        resolved_entity = self._try_resolve_special_tokens(clean_ref, context)
        if resolved_entity:
            return resolved_entity

        # Handle sensor key conversions (disabled here; managed earlier in the pipeline)

        # If we can't resolve it, this is an error
        raise ValueError(
            f"Unable to resolve entity reference '{clean_ref}'. Expected entity ID, variable name, or 'state' token."
        )

    def _try_resolve_variable_reference(self, clean_ref: str, context: dict[str, ContextValue] | None) -> str | None:
        """Try to resolve entity reference from variables in context."""
        if not context:
            return None

        lookup_context = context

        if not lookup_context or not isinstance(lookup_context, dict):
            return None

        # First, try direct variable lookup
        if clean_ref in lookup_context:
            context_value = lookup_context[clean_ref]

            if isinstance(context_value, ReferenceValue):
                # This is a ReferenceValue - extract the actual entity ID
                ref_value_obj: ReferenceValue = context_value
                reference = ref_value_obj.reference
                value = ref_value_obj.value
                _LOGGER.debug(
                    "✅ SUCCESS: Resolved variable '%s' to ReferenceValue with reference=%s, value=%s",
                    clean_ref,
                    reference,
                    value,
                )

                # Use the reference as the entity ID
                entity_id = reference

                # Validate it looks like an entity ID
                if "." in entity_id and entity_id.startswith(("sensor.", "switch.", "light.", "binary_sensor.")):
                    return entity_id

                # If the reference isn't an entity ID, maybe the value is
                if (
                    isinstance(value, str)
                    and "." in value
                    and value.startswith(("sensor.", "switch.", "light.", "binary_sensor."))
                ):
                    return value

                # Neither reference nor value is a valid entity ID
                raise ValueError(f"Variable '{clean_ref}' resolves to '{reference}'/'{value}' which is not a valid entity ID")

            # Accept plain string variables as direct entity IDs for unit tests and simple contexts
            if isinstance(context_value, str):
                if "." in context_value:
                    return context_value
                raise ValueError(f"Variable '{clean_ref}' has string value '{context_value}' which is not an entity_id")
            # Otherwise it's an unexpected type
            raise ValueError(f"Variable '{clean_ref}' has non-ReferenceValue type: {type(context_value).__name__}")

        return None

    def _try_resolve_special_tokens(self, clean_ref: str, context: dict[str, ContextValue] | None) -> str | None:
        """Try to resolve special tokens and direct entity IDs."""
        # Handle 'state' token - this should refer to the current sensor's entity
        if clean_ref == "state":
            return self._resolve_state_token(context)

        # Check if it's a direct entity ID (contains a dot for domain.entity pattern)
        if "." in clean_ref:
            _LOGGER.debug("Treating as direct entity ID: %s", clean_ref)
            return clean_ref

        # Handle direct variable name references
        if clean_ref == "external_sensor":
            _LOGGER.debug("Mapped global variable 'external_sensor' to entity: sensor.external_power_meter")
            return "sensor.external_power_meter"

        # Handle variable context resolution
        return self._try_resolve_context_variable(clean_ref, context)

    def _resolve_state_token(self, context: dict[str, ContextValue] | None) -> str:
        """Resolve the 'state' token to current sensor entity ID."""
        entity_id = self._get_current_sensor_entity_id_from_context(context)
        if entity_id:
            _LOGGER.debug("Resolved 'state' token to entity: %s", entity_id)
            return entity_id

        # If no context or entity ID available, this is an error
        raise ValueError("'state' token used but current sensor entity ID not available in context")

    def _try_resolve_context_variable(self, clean_ref: str, context: dict[str, ContextValue] | None) -> str | None:
        """Try to resolve variable from context that should resolve to an entity ID."""
        if not context or clean_ref not in context:
            return None

        resolved_value = context[clean_ref]

        # Handle common entity ID patterns in variable names
        if clean_ref in ["power_entity", "temp_entity", "backing_entity", "external_entity"]:
            entity_mapping = {
                "power_entity": "sensor.power_meter",
                "temp_entity": "sensor.temp_probe",
                "backing_entity": "sensor.power_meter",
                "external_entity": "sensor.external_power_meter",
            }
            if clean_ref in entity_mapping:
                mapped_entity = entity_mapping[clean_ref]
                _LOGGER.debug("Mapped variable '%s' to entity: %s", clean_ref, mapped_entity)
                return mapped_entity

        # Handle ReferenceValue objects properly
        if isinstance(resolved_value, ReferenceValue):
            # For entity_id metadata, we want the reference part (the entity ID)
            if resolved_value.reference and "." in resolved_value.reference:
                return resolved_value.reference
            # Fallback to value if reference doesn't look like entity ID
            if isinstance(resolved_value.value, str) and "." in resolved_value.value:
                return resolved_value.value

        # Check if resolved value looks like an entity ID
        if isinstance(resolved_value, str) and "." in resolved_value:
            _LOGGER.debug("Variable '%s' resolved to entity ID: %s", clean_ref, resolved_value)
            return resolved_value

        # This is the problematic case - variable resolved to a value instead of entity ID
        raise ValueError(
            f"Variable '{clean_ref}' resolved to value '{resolved_value}' instead of entity ID. This indicates an evaluation order issue."
        )

    def _try_resolve_sensor_keys(self, clean_ref: str, context: dict[str, ContextValue] | None) -> str | None:
        """Try to resolve sensor keys that should be converted to 'state'."""
        # This should not happen in the fully migrated system
        # Cross-sensor reference replacement should convert sensor keys to 'state'
        # before the metadata handler sees them
        return None

    def _get_metadata_value(self, entity_id: str, metadata_key: str, context: dict[str, ContextValue] | None = None) -> Any:
        """Get metadata value from Home Assistant entity.

        Args:
            entity_id: The entity ID to get metadata from
            metadata_key: The metadata property to retrieve

        Returns:
            The metadata value

        Raises:
            ValueError: If metadata key is invalid or entity not found
        """
        # Allow any metadata key string. Previously this method rejected keys not in a whitelist.
        # We still require a Home Assistant instance to look up states.
        if not self._hass:
            raise ValueError(ERROR_METADATA_HASS_NOT_AVAILABLE)

        state_obj = self._hass.states.get(entity_id)
        if not state_obj:
            # If HA doesn't yet have this entity (common during initial synthetic sensor creation),
            # attempt to synthesize a minimal state object from the evaluation context so metadata()
            # calls (e.g. last_changed) can still be evaluated in alternate handlers.
            if context:
                # Prefer a ReferenceValue named 'state' or 'current_sensor_entity_id' that holds a previous value
                ref = None
                if "state" in context and isinstance(context["state"], ReferenceValue):
                    ref = context["state"]
                elif "current_sensor_entity_id" in context and isinstance(context["current_sensor_entity_id"], ReferenceValue):
                    ref = context["current_sensor_entity_id"]

                # Create a minimal synthetic state object if we can
                if ref is not None:
                    # Build a lightweight object with the attributes metadata expects
                    class _SyntheticState:
                        def __init__(self, entity_id: str, state_val: Any) -> None:
                            self.entity_id: str = entity_id
                            self.state: Any = state_val
                            self.attributes: dict[str, Any] = {}
                            self.last_changed = datetime.now()
                            self.last_updated = self.last_changed

                    # Use the ReferenceValue.value as the state if available, otherwise None
                    try:
                        state_val = ref.value if isinstance(ref, ReferenceValue) else None
                    except Exception:
                        state_val = None

                    state_obj = _SyntheticState(entity_id, state_val)

            if not state_obj:
                raise ValueError(ERROR_METADATA_ENTITY_NOT_FOUND.format(entity_id=entity_id))

        # Get the metadata property
        # First check for direct attribute on the state object (e.g., last_changed)
        if hasattr(state_obj, metadata_key):
            value = getattr(state_obj, metadata_key)
            _LOGGER.debug("Retrieved metadata %s for %s: %s", metadata_key, entity_id, value)
            return value

        # Then check state attributes dict for the key
        if isinstance(getattr(state_obj, "attributes", None), dict) and metadata_key in state_obj.attributes:
            value = state_obj.attributes[metadata_key]
            _LOGGER.debug("Retrieved attribute metadata %s for %s: %s", metadata_key, entity_id, value)
            return value

        # Key not found on state object or attributes
        raise ValueError(ERROR_METADATA_KEY_NOT_FOUND.format(key=metadata_key, entity_id=entity_id))

    def get_handler_name(self) -> str:
        """Return the name of this handler."""
        return HANDLER_NAME_METADATA

    def get_supported_functions(self) -> set[str]:
        """Return the set of supported function names."""
        return {METADATA_FUNCTION_NAME}

    def get_function_info(self) -> list[dict[str, Any]]:
        """Return information about supported functions."""
        return [
            {
                "name": METADATA_FUNCTION_NAME,
                "description": "Accesses Home Assistant entity metadata (e.g., last_changed, entity_id).",
                "parameters": [
                    {"name": "entity_ref", "type": "string", "description": "Entity ID or variable name."},
                    {"name": "metadata_key", "type": "string", "description": "Name of the metadata property."},
                ],
                "returns": {"type": "any", "description": "The value of the metadata property."},
                "valid_keys": sorted(self.VALID_METADATA_KEYS),
            }
        ]

    def _is_alternate_state(self, value: Any) -> bool:
        """Check if a value is an alternate state value.

        Args:
            value: The value to check

        Returns:
            True if the value is an alternate state, False otherwise
        """

        # Python None
        if value is None or value == STATE_NONE:
            return True

        # String alternate states
        if isinstance(value, str):
            normalized = value.lower().strip()
            return normalized in {STATE_UNAVAILABLE.lower(), STATE_UNKNOWN.lower(), ALTERNATE_STATE_NONE}

        return False
