"""Variable resolution strategies for synthetic sensor package."""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import TYPE_CHECKING, Any, cast

from homeassistant.core import HomeAssistant, State

from .constants_boolean_states import FALSE_STATES, TRUE_STATES
from .data_validation import validate_data_provider_result, validate_entity_state_value
from .exceptions import MissingDependencyError, NonNumericStateError
from .type_definitions import ContextValue, DataProviderCallback
from .utils import denormalize_entity_id

if TYPE_CHECKING:
    pass  # No additional imports needed for type checking

_LOGGER = logging.getLogger(__name__)


class VariableResolutionStrategy(ABC):
    """Abstract base class for variable resolution strategies.

    This defines how variables/entities are resolved during formula evaluation.
    Different strategies can handle HA state, integration callbacks, or hybrid approaches.
    """

    @abstractmethod
    def resolve_variable(self, variable_name: str, entity_id: str | None = None) -> tuple[Any, bool, str]:
        """Resolve a variable to its value.

        Args:
            variable_name: The variable name to resolve
            entity_id: Optional entity ID if this variable maps to an entity

        Returns:
            Tuple of (value, exists, source) where:
            - value: The resolved value
            - exists: Whether the variable exists/is available
            - source: Description of the data source ("ha", "integration", "context", etc.)
        """

    @abstractmethod
    def can_resolve(self, variable_name: str, entity_id: str | None = None) -> bool:
        """Check if this strategy can resolve the given variable.

        Args:
            variable_name: The variable name to check
            entity_id: Optional entity ID if this variable maps to an entity

        Returns:
            True if this strategy should be used for this variable
        """


class ContextResolutionStrategy(VariableResolutionStrategy):
    """Resolution strategy that uses provided context values.

    This strategy resolves variables from the provided evaluation context.
    It has the highest priority since context values are explicitly provided.

    Context values should be numeric (int, float) for mathematical operations.
    """

    def __init__(self, context: dict[str, ContextValue]):
        """Initialize with context dictionary."""
        self._context = context or {}

    def can_resolve(self, variable_name: str, entity_id: str | None = None) -> bool:
        """Check if variable exists in context and is numeric."""
        if variable_name not in self._context:
            return False

        # Ensure the context value is numeric for mathematical operations
        value = self._context[variable_name]
        return isinstance(value, int | float)

    def resolve_variable(self, variable_name: str, entity_id: str | None = None) -> tuple[Any, bool, str]:
        """Resolve variable from context."""
        if variable_name in self._context:
            value = self._context[variable_name]
            # Validate that the value is numeric
            if isinstance(value, int | float):
                return value, True, "context"
            raise MissingDependencyError(
                f"Context variable '{variable_name}' has non-numeric value '{value}' - "
                "all context variables must be numeric for use in formulas"
            )
        return None, False, "context"


class IntegrationResolutionStrategy(VariableResolutionStrategy):
    """Resolution strategy that uses integration data provider callbacks.

    This strategy resolves variables by calling back into the integration
    that registered the synthetic sensor. The integration can provide
    data without requiring actual HA entities.
    """

    def __init__(self, data_provider_callback: DataProviderCallback, dependency_handler: Any = None):
        """Initialize with integration callback and dependency handler for push-based pattern."""
        self._data_provider_callback = data_provider_callback
        self._dependency_handler = dependency_handler  # For accessing get_integration_entities method

    def _get_integration_entities(self) -> set[str]:
        """Get the set of entities that the integration can provide using push-based pattern."""
        # Use dependency handler pattern
        if self._dependency_handler and hasattr(self._dependency_handler, "get_integration_entities"):
            entities = self._dependency_handler.get_integration_entities()
            return cast(set[str], entities)

        # If no dependency handler provided, return empty set (no integration entities available)
        return set()

    def can_resolve(self, variable_name: str, entity_id: str | None = None) -> bool:
        """Check if integration data provider can resolve this variable.

        Uses registration filtering to only resolve registered entities,
        implementing the user's architecture to prevent hiding configuration errors.
        """
        target_entity = entity_id or variable_name

        # Handle normalized entity IDs (with underscores instead of dots)
        if "." not in target_entity and "_" in target_entity:
            original_entity_id = denormalize_entity_id(target_entity)
            if original_entity_id:
                # Check registration first, then existence
                return self._is_entity_registered(original_entity_id) and self._check_entity_exists(original_entity_id)

        # Only resolve if it looks like an entity ID
        if "." not in target_entity:
            return False

        # Check registration first, then existence
        return self._is_entity_registered(target_entity) and self._check_entity_exists(target_entity)

    def _is_entity_registered(self, entity_id: str) -> bool:
        """Check if an entity is registered with the integration.

        Implements proper registration filtering according to the architecture.
        """
        integration_entities = self._get_integration_entities()

        # If no entities are registered, allow any entity (flexible data provider usage)
        if not integration_entities:
            return True

        # Only allow registered entities (strict registration validation)
        return entity_id in integration_entities

    def _check_entity_exists(self, entity_id: str) -> bool:
        """Check if an entity exists in the integration data provider."""
        if self._data_provider_callback is None:
            return False

        # Only call data provider for registered entities
        if not self._is_entity_registered(entity_id):
            return False

        result = self._data_provider_callback(entity_id)
        return result is not None and result.get("exists", False)

    def resolve_variable(self, variable_name: str, entity_id: str | None = None) -> tuple[Any, bool, str]:
        """Resolve variable using integration data provider."""
        target_entity = entity_id or variable_name

        # Check if this is an attribute reference (e.g., "state.voltage")
        if "." in variable_name and entity_id is None:
            return self._resolve_attribute_reference(variable_name)

        # Regular entity resolution - only call data provider for registered entities
        if not self._is_entity_registered(target_entity):
            return None, False, "integration"

        result = self._data_provider_callback(target_entity)
        validated_result = validate_data_provider_result(result, f"integration data provider for '{target_entity}'")

        # If entity exists, validate and sanitize the state value
        if validated_result["exists"]:
            sanitized_value = validate_entity_state_value(validated_result["value"], target_entity)
            return sanitized_value, validated_result["exists"], "integration"

        return validated_result["value"], validated_result["exists"], "integration"

    def _resolve_attribute_reference(self, variable_name: str) -> tuple[Any, bool, str]:
        """Resolve an attribute reference like 'state.voltage' or 'sensor.temp.humidity'."""
        parts = variable_name.split(".", 1)
        base_entity = parts[0]
        attribute_name = parts[1]

        if base_entity == "state":
            return self._resolve_state_attribute_reference(attribute_name)

        return self._resolve_regular_attribute_reference(base_entity, attribute_name)

    def _resolve_state_attribute_reference(self, attribute_name: str) -> tuple[Any, bool, str]:
        """Resolve a state attribute reference like 'state.voltage'."""
        # Try to get backing entity from integration entities
        integration_entities = self._get_integration_entities()
        if integration_entities:
            backing_entity = next(iter(integration_entities))
            result = self._data_provider_callback(backing_entity)
            validated_result = validate_data_provider_result(result, f"integration data provider for '{backing_entity}'")

            if validated_result["exists"] and "attributes" in validated_result:
                attributes = validated_result["attributes"]
                if attribute_name in attributes:
                    attribute_value = attributes[attribute_name]
                    sanitized_value = validate_entity_state_value(attribute_value, f"{backing_entity}.{attribute_name}")
                    return sanitized_value, True, "integration"

        # Fallback: try to resolve "state" as a regular entity
        return self._resolve_regular_attribute_reference("state", attribute_name)

    def _resolve_regular_attribute_reference(self, base_entity: str, attribute_name: str) -> tuple[Any, bool, str]:
        """Resolve a regular attribute reference like 'sensor.temp.humidity'."""
        # Only call data provider for registered entities
        if not self._is_entity_registered(base_entity):
            return None, False, "integration"

        result = self._data_provider_callback(base_entity)
        validated_result = validate_data_provider_result(result, f"integration data provider for '{base_entity}'")

        if not validated_result["exists"]:
            return None, False, "integration"

        # Check if the result has attributes
        if "attributes" in validated_result and isinstance(validated_result["attributes"], dict):
            attributes = validated_result["attributes"]
            if attribute_name in attributes:
                attribute_value = attributes[attribute_name]
                sanitized_value = validate_entity_state_value(attribute_value, f"{base_entity}.{attribute_name}")
                return sanitized_value, True, "integration"

        # Attribute not found
        return None, False, "integration"


class HomeAssistantResolutionStrategy(VariableResolutionStrategy):
    """Resolution strategy that uses Home Assistant state.

    This strategy resolves variables by looking up entity states in HA.
    It serves as the fallback strategy when other strategies cannot resolve a variable.
    """

    def __init__(self, hass: HomeAssistant):
        """Initialize with Home Assistant instance."""
        self._hass = hass

    def can_resolve(self, variable_name: str, entity_id: str | None = None) -> bool:
        """Check if HA has state for this variable."""
        target_entity = entity_id or variable_name

        # Handle normalized entity IDs (with underscores instead of dots)
        if "." not in target_entity and "_" in target_entity:
            # Try to convert normalized entity ID back to original format
            # This handles cases where entity IDs were normalized for simpleeval compatibility
            original_entity_id = denormalize_entity_id(target_entity)
            if original_entity_id:
                state = self._hass.states.get(original_entity_id)
                result = state is not None
                return result

        # Only resolve if it looks like an entity ID
        if "." not in target_entity:
            return False

        state = self._hass.states.get(target_entity)
        result = state is not None
        return result

    def resolve_variable(self, variable_name: str, entity_id: str | None = None) -> tuple[Any, bool, str]:
        """Resolve variable using HA state."""
        target_entity = entity_id or variable_name

        # Check if this is an attribute reference (e.g., "state.voltage")
        if "." in variable_name and entity_id is None:
            return self._resolve_attribute_reference(variable_name)

        # Handle normalized entity IDs (with underscores instead of dots)
        if "." not in target_entity and "_" in target_entity:
            original_entity_id = denormalize_entity_id(target_entity)
            if original_entity_id:
                state = self._hass.states.get(original_entity_id)
                if state is not None:
                    return self._process_state(state, "ha")

        state = self._hass.states.get(target_entity)
        if state is None:
            return None, False, "ha"

        return self._process_state(state, "ha")

    def _resolve_attribute_reference(self, variable_name: str) -> tuple[Any, bool, str]:
        """Resolve an attribute reference like 'state.voltage'."""
        parts = variable_name.split(".", 1)
        base_entity = parts[0]
        attribute_name = parts[1]

        # Resolve the base entity first
        state = self._hass.states.get(base_entity)
        if state is None:
            return None, False, "ha"

        # Check if the state has the requested attribute
        if hasattr(state, "attributes") and attribute_name in state.attributes:
            attribute_value = state.attributes[attribute_name]
            # Try to convert to numeric if possible
            try:
                numeric_value = float(attribute_value)
                return numeric_value, True, "ha"
            except (ValueError, TypeError):
                # Return as string if not numeric
                return str(attribute_value), True, "ha"

        # Attribute not found
        return None, False, "ha"

    def _process_state(self, state: State, source: str) -> tuple[Any, bool, str]:
        """Process state and return numeric value."""
        # Handle startup race conditions where state exists but state.state is None
        if state.state is None:
            return None, False, source

        # Handle clearly unavailable states
        if str(state.state).lower() in ("unavailable", "unknown"):
            return None, False, source

        try:
            # Try to get numeric state value
            numeric_value = self._get_numeric_state(state)
            return numeric_value, True, source
        except (ValueError, TypeError, NonNumericStateError):
            # For truly non-numeric states that can't be converted, treat as unavailable
            return None, False, source

    def get_numeric_state(self, state: State) -> float:
        """Public method to get numeric state value.

        Args:
            state: Home Assistant state object

        Returns:
            Numeric value of the state

        Raises:
            NonNumericStateError: If state cannot be converted to numeric
        """
        return self._get_numeric_state(state)

    def convert_boolean_state_to_numeric(self, state: State) -> float | None:
        """Public method to convert boolean-like state to numeric value.

        Args:
            state: Home Assistant state object

        Returns:
            Numeric value (1.0 or 0.0) or None if not convertible
        """
        return self._convert_boolean_state_to_numeric(state)

    def _get_numeric_state(self, state: State) -> float:
        """Extract numeric value from state object.

        Converts boolean-like states to numeric values following HA conventions:
        - Binary states: on/off, true/false, open/closed, etc. → 1.0/0.0
        - Device presence: home/away, detected/clear → 1.0/0.0
        - Lock states: locked/unlocked → 1.0/0.0
        - Other boolean-like states based on device type
        """
        try:
            return float(state.state)
        except (ValueError, TypeError):
            # Convert boolean-like states to numeric values
            numeric_value = self.convert_boolean_state_to_numeric(state)
            if numeric_value is not None:
                return numeric_value

            # If we can't convert the state, raise an error
            raise NonNumericStateError(
                state.entity_id,
                f"Cannot convert state '{state.state}' to numeric value",
            ) from None

    def _convert_boolean_state_to_numeric(self, state: State) -> float | None:
        """Convert boolean-like state to numeric value.

        Args:
            state: Home Assistant state object

        Returns:
            Numeric value (1.0 or 0.0) or None if not convertible
        """
        state_str = str(state.state).lower()

        # Standard boolean states (True = 1.0)
        if state_str in TRUE_STATES:
            return 1.0

        # Standard boolean states (False = 0.0)
        if state_str in FALSE_STATES:
            return 0.0

        # Device-specific boolean states based on device class
        device_class = state.attributes.get("device_class")
        if device_class:
            device_class = device_class.lower()

            # Device-specific true states
            device_true_states = {
                "moisture": {"moist", "wet"},
                "door": {"open"},
                "window": {"open"},
                "motion": {"motion", "detected"},
                "presence": {"home", "detected"},
                "lock": {"locked"},
                "battery": {"low"},
                "problem": {"problem"},
            }

            # Device-specific false states
            device_false_states = {
                "moisture": {"not_moist", "dry"},
                "door": {"closed"},
                "window": {"closed"},
                "motion": {"clear", "no_motion"},
                "presence": {"away", "not_home"},
                "lock": {"unlocked"},
                "battery": {"normal"},
                "problem": {"ok", "normal"},
            }

            if device_class in device_true_states and state_str in device_true_states[device_class]:
                return 1.0
            if device_class in device_false_states and state_str in device_false_states[device_class]:
                return 0.0

        return None  # Cannot convert


class VariableResolver:
    """Orchestrates variable resolution using multiple strategies.

    This class manages the resolution process by trying different strategies
    in priority order until a variable is resolved or all strategies are exhausted.
    """

    def __init__(self, strategies: list[VariableResolutionStrategy]):
        """Initialize with ordered list of resolution strategies."""
        self._strategies = strategies

    def resolve_variable(self, variable_name: str, entity_id: str | None = None) -> tuple[Any, bool, str]:
        """Resolve a variable using the first capable strategy.

        Args:
            variable_name: The variable name to resolve
            entity_id: Optional entity ID if this variable maps to an entity

        Returns:
            Tuple of (value, exists, source) where source indicates which strategy succeeded
        """
        for strategy in self._strategies:
            if strategy.can_resolve(variable_name, entity_id):
                return strategy.resolve_variable(variable_name, entity_id)

        # No strategy could resolve the variable
        return None, False, "none"

    def resolve_variables(self, variables: dict[str, str | int | float | None]) -> dict[str, tuple[Any, bool, str]]:
        """Resolve multiple variables efficiently.

        Args:
            variables: Dict mapping variable names to optional entity IDs or numeric literals

        Returns:
            Dict mapping variable names to (value, exists, source) tuples
        """
        results: dict[str, tuple[Any, bool, str]] = {}
        for var_name, var_value in variables.items():
            # Handle numeric literals directly without entity resolution
            if isinstance(var_value, int | float):
                results[var_name] = (var_value, True, "literal")
            else:
                # Handle entity ID resolution (string or None)
                results[var_name] = self.resolve_variable(var_name, var_value)
        return results
