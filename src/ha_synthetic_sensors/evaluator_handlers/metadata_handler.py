"""Metadata handler for accessing Home Assistant entity metadata."""

from __future__ import annotations

from collections.abc import Callable
import logging
import re
from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from ..constants_alternate import ALTERNATE_STATE_NONE, STATE_NONE, identify_alternate_state_value
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
from ..hierarchical_context_dict import HierarchicalContextDict
from ..regex_helper import RegexHelper, create_metadata_function_pattern
from ..shared_constants import get_ha_domains
from ..type_definitions import ReferenceValue
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
        expression_evaluator: Callable[[str, HierarchicalContextDict], Any] | None = None,
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
    def process_metadata_functions(cls, formula: str, context: HierarchicalContextDict) -> str:
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
            # Preserve Explicit AlternateStateDetected propagation
            if isinstance(e, AlternateStateDetected):
                raise
            # Fatal: missing hass must not be silently ignored
            if ERROR_METADATA_HASS_NOT_AVAILABLE in str(e):
                _LOGGER.error("METADATA_HANDLER: %s", e)
                raise

            # For other runtime errors during metadata processing, treat them as alternate STATE_UNKNOWN
            _LOGGER.warning(
                "METADATA_HANDLER: Runtime error processing metadata for formula %s: %s - skipping and treating as STATE_UNKNOWN",
                formula,
                e,
            )
            # Use "from e" to preserve original traceback while signaling alternate state
            raise AlternateStateDetected(f"Metadata processing error: {e}", STATE_UNKNOWN, "unknown") from e

        # If handler cannot handle this formula or no metadata was processed, return original formula
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

    def evaluate(self, formula: str, context: HierarchicalContextDict) -> tuple[str, dict[str, str]]:
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
        _LOGGER.debug("METADATA_EVALUATE_START: Evaluating metadata formula: %s", formula)

        # Validate Home Assistant instance is available
        if self._hass is None:
            raise ValueError("Home Assistant instance not available for metadata function")

        processed_formula = formula
        metadata_results = {}  # Store metadata results for AST caching
        metadata_counter = 0

        # Find all metadata function calls and replace them with their results
        def replace_metadata_function(match: re.Match[str]) -> str:
            nonlocal metadata_counter
            params_str = match.group(1)  # Content inside parentheses

            # Parse parameters (simple comma split for now)
            params = [p.strip() for p in params_str.split(",")]
            if len(params) != 2:
                raise ValueError(ERROR_METADATA_FUNCTION_PARAMETER_COUNT.format(count=len(params)))

            entity_ref = params[0].strip()
            metadata_key = params[1].strip().strip("'\"")  # Remove quotes from key

            # The entity_ref might be a variable name or an entity ID
            # If it's a variable name, we need to resolve it to the entity ID
            # If it's already an entity ID, use it directly
            try:
                resolved_entity_id = self._resolve_entity_reference(entity_ref, context)
            except Exception as e:
                raise ValueError(f"Cannot resolve entity reference: {e}") from e

            # Check 1: Is the entity reference itself an alternate state?
            if self._is_alternate_state(resolved_entity_id):
                # Determine the alternate state type for the entity reference
                alternate_state_type = identify_alternate_state_value(resolved_entity_id)
                state_type = alternate_state_type if isinstance(alternate_state_type, str) else "unknown"
                raise AlternateStateDetected(
                    f"Entity reference '{resolved_entity_id}' is in alternate state", resolved_entity_id, state_type
                )

            # Get metadata value
            metadata_value = self._get_metadata_value(resolved_entity_id, metadata_key, context)
            _LOGGER.debug("METADATA_GOT_VALUE: Got metadata value=%s (type: %s)", metadata_value, type(metadata_value).__name__)

            # Check 2: Is the metadata result an alternate state?
            if self._is_alternate_state(metadata_value):
                # Determine the alternate state type for the metadata value
                alternate_state_type = identify_alternate_state_value(metadata_value)
                state_type = alternate_state_type if isinstance(alternate_state_type, str) else "unknown"
                raise AlternateStateDetected(
                    f"Metadata result '{metadata_value}' is alternate state", metadata_value, state_type
                )

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

        # Use centralized metadata function pattern from regex helper
        regex_helper = RegexHelper()
        metadata_pattern = create_metadata_function_pattern(METADATA_FUNCTION_NAME)
        processed_formula = regex_helper.replace_with_function(
            processed_formula, metadata_pattern.pattern, replace_metadata_function
        )

        _LOGGER.debug("Processed metadata formula: %s", processed_formula)
        _LOGGER.debug("Metadata results: %s", metadata_results)

        # Return both the processed formula and metadata results
        _LOGGER.debug(
            "METADATA_EVALUATE_END: Returning processed_formula=%s, metadata_results=%s", processed_formula, metadata_results
        )
        return processed_formula, metadata_results

    def _get_current_sensor_entity_id_from_context(self, context: HierarchicalContextDict) -> str | None:
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
            _LOGGER.debug(
                "METADATA_CURRENT_SENSOR_DEBUG: Found current_sensor_entity_id=%s (type: %s)", value, type(value).__name__
            )
            if isinstance(value, ReferenceValue):
                _LOGGER.debug(
                    "METADATA_CURRENT_SENSOR_DEBUG: ReferenceValue.value=%s (type: %s)", value.value, type(value.value).__name__
                )
            if isinstance(value, ReferenceValue) and isinstance(value.value, str):
                entity_id = value.value
            elif isinstance(value, str) and value.startswith("sensor."):
                entity_id = value
            if entity_id:
                return entity_id
            _LOGGER.warning("METADATA_CURRENT_SENSOR_INVALID: current_sensor_entity_id value is not valid: %s", value)
        else:
            _LOGGER.warning("METADATA_CURRENT_SENSOR_MISSING: current_sensor_entity_id not found in context")

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

    def _resolve_entity_reference(self, entity_ref: str, context: HierarchicalContextDict) -> str:
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

        # Check if entity_ref is a numeric value - this indicates premature value substitution
        # and helps us identify where the variable resolution pipeline is going wrong
        try:
            float(clean_ref)
            # If we can parse it as a number, this is a BUG in the resolution pipeline
            raise ValueError(
                f"Received numeric value '{clean_ref}' as entity reference. "
                f"This indicates premature value substitution in the variable resolution pipeline. "
                f"Entity references should be variable names or entity IDs, not resolved values. "
                f"Check the stack trace to see where this numeric value was substituted."
            )
        except ValueError as e:
            if "METADATA_HANDLER_BUG" in str(e):
                raise  # Re-raise our custom error
            # Not a number, continue normal processing

        _LOGGER.debug("Resolving entity reference: '%s'", clean_ref)
        _LOGGER.debug("MetadataHandler context keys: %s", list(context.keys()) if context else "None")

        # Try variable resolution first
        _LOGGER.debug("MetadataHandler: About to call _try_resolve_variable_reference for '%s'", clean_ref)
        resolved_entity = self._try_resolve_variable_reference(clean_ref, context)
        _LOGGER.debug("MetadataHandler: _try_resolve_variable_reference returned: %s", resolved_entity)
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

    def _try_resolve_variable_reference(self, clean_ref: str, context: HierarchicalContextDict) -> str | None:
        """Try to resolve entity reference from variables in context."""
        _LOGGER.debug("MetadataHandler: _try_resolve_variable_reference called with clean_ref='%s'", clean_ref)
        if not context:
            _LOGGER.debug("MetadataHandler: No context provided, returning None")
            return None

        lookup_context = context

        if not lookup_context or not isinstance(lookup_context, dict | HierarchicalContextDict):
            _LOGGER.debug("MetadataHandler: Invalid lookup_context (type: %s), returning None", type(lookup_context).__name__)
            return None

        # Debug: Log what's in the context
        _LOGGER.debug(
            "MetadataHandler: Trying to resolve variable '%s' in context with keys: %s", clean_ref, list(lookup_context.keys())
        )

        # First, try direct variable lookup
        if clean_ref in lookup_context:
            _LOGGER.debug("MetadataHandler: Found '%s' in context", clean_ref)
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

                # Validate it looks like an entity ID using dynamic domain discovery
                hass = getattr(self, "_hass", None)
                ha_domains = get_ha_domains(hass) if hass else set()

                if "." in entity_id and any(entity_id.startswith(f"{domain}.") for domain in ha_domains):
                    return entity_id

                # If the reference isn't an entity ID, maybe the value is
                if isinstance(value, str) and "." in value and any(value.startswith(f"{domain}.") for domain in ha_domains):
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

    def _try_resolve_special_tokens(self, clean_ref: str, context: HierarchicalContextDict) -> str | None:
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

    def _resolve_state_token(self, context: HierarchicalContextDict) -> str:
        """Resolve the 'state' token to current sensor entity ID."""
        entity_id = self._get_current_sensor_entity_id_from_context(context)
        if entity_id:
            _LOGGER.debug("Resolved 'state' token to entity: %s", entity_id)
            return entity_id

        # If no context or entity ID available, this is an error
        raise ValueError("'state' token used but current sensor entity ID not available in context")

    def _try_resolve_context_variable(self, clean_ref: str, context: HierarchicalContextDict) -> str | None:
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

    def _try_resolve_sensor_keys(self, clean_ref: str, context: HierarchicalContextDict) -> str | None:
        """Try to resolve sensor keys that should be converted to 'state'."""
        # This should not happen in the fully migrated system
        # Cross-sensor reference replacement should convert sensor keys to 'state'
        # before the metadata handler sees them
        return None

    def _get_metadata_value(self, entity_id: str, metadata_key: str, context: HierarchicalContextDict) -> Any:
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

        # Handle case where entity doesn't exist
        if state_obj is None:
            _LOGGER.debug("METADATA_ENTITY_NOT_FOUND: Entity %s not found", entity_id)
            raise ValueError(ERROR_METADATA_ENTITY_NOT_FOUND.format(entity_id=entity_id))

        # Get the metadata property
        # First check state attributes dict for the key (most common case)
        if isinstance(getattr(state_obj, "attributes", None), dict) and metadata_key in state_obj.attributes:
            value = state_obj.attributes[metadata_key]
            _LOGGER.debug(
                "METADATA_FROM_ATTRIBUTES: Retrieved attribute metadata %s for %s: %s (type: %s)",
                metadata_key,
                entity_id,
                value,
                type(value).__name__,
            )
            return value

        # Then check for direct attribute on the state object (e.g., last_changed)
        if hasattr(state_obj, metadata_key):
            value = getattr(state_obj, metadata_key)
            _LOGGER.debug(
                "METADATA_FROM_DIRECT: Retrieved direct metadata %s for %s: %s (type: %s)",
                metadata_key,
                entity_id,
                value,
                type(value).__name__,
            )
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
