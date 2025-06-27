"""Variable resolution strategies for flexible data access in synthetic sensors.

This module provides a pluggable resolution system that allows synthetic sensors
to get data from different sources (HA state, integration callbacks, or context)
in a consistent and predictable way.

Variable Types Supported:
1. Entity aliases: variable maps to an entity ID (e.g., power: "sensor.power_meter")
2. Numeric literals: variable contains a direct numeric value (e.g., offset: 5, rate: 1.5)

Note: String literals and string operations are not currently supported since
the evaluation engine (simpleeval) is focused on mathematical operations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Any, cast

from homeassistant.core import HomeAssistant, State

from .exceptions import NonNumericStateError
from .types import ContextValue, DataProviderCallback, EntityListCallback

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
        return isinstance(value, (int, float))

    def resolve_variable(self, variable_name: str, entity_id: str | None = None) -> tuple[Any, bool, str]:
        """Resolve variable from context."""
        if variable_name in self._context:
            value = self._context[variable_name]
            # Validate that the value is numeric
            if isinstance(value, (int, float)):
                return value, True, "context"
            else:
                _LOGGER.warning("Context variable '%s' has non-numeric value '%s', skipping", variable_name, value)
                return None, False, "context"
        return None, False, "context"


class IntegrationResolutionStrategy(VariableResolutionStrategy):
    """Resolution strategy that uses integration data provider callbacks.

    This strategy resolves variables by calling back into the integration
    that registered the synthetic sensor. The integration can provide
    data without requiring actual HA entities.
    """

    def __init__(self, data_provider_callback: DataProviderCallback, entity_list_callback: EntityListCallback | None = None, evaluator: Any = None):
        """Initialize with integration callbacks and optional evaluator for new pattern."""
        self._data_provider_callback = data_provider_callback
        self._entity_list_callback = entity_list_callback
        self._evaluator = evaluator  # For accessing new get_integration_entities method
        self._integration_entities: set[str] | None = None

    def _get_integration_entities(self) -> set[str]:
        """Get the set of entities that the integration can provide."""
        # Try new pattern first (via evaluator)
        if self._evaluator and hasattr(self._evaluator, "get_integration_entities"):
            entities = self._evaluator.get_integration_entities()
            return cast(set[str], entities)

        # Fall back to old callback pattern for backward compatibility
        if self._integration_entities is None:
            if self._entity_list_callback:
                try:
                    self._integration_entities = self._entity_list_callback()
                except Exception as e:
                    _LOGGER.warning("Error calling entity list callback: %s", e)
                    self._integration_entities = set()
            else:
                # If no entity list callback, assume integration can provide any entity
                self._integration_entities = set()
        return self._integration_entities

    def can_resolve(self, variable_name: str, entity_id: str | None = None) -> bool:
        """Check if integration can resolve this variable."""
        integration_entities = self._get_integration_entities()
        target_entity = entity_id or variable_name

        # If we have registered entities (from new pattern or old callback), check if entity is in the list
        if integration_entities:
            return target_entity in integration_entities

        # If no registered entities and no callback, can't resolve anything
        if not self._entity_list_callback:
            return False

        # If we have a callback but no entities yet, assume we can try to resolve any entity ID
        return entity_id is not None or "." in variable_name

    def resolve_variable(self, variable_name: str, entity_id: str | None = None) -> tuple[Any, bool, str]:
        """Resolve variable using integration callback."""
        target_entity = entity_id or variable_name

        try:
            result = self._data_provider_callback(target_entity)
            return result["value"], result["exists"], "integration"
        except Exception as e:
            _LOGGER.warning("Error calling data provider callback for '%s': %s", target_entity, e)
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

        # Only resolve if it looks like an entity ID
        if "." not in target_entity:
            return False

        state = self._hass.states.get(target_entity)
        return state is not None

    def resolve_variable(self, variable_name: str, entity_id: str | None = None) -> tuple[Any, bool, str]:
        """Resolve variable using HA state."""
        target_entity = entity_id or variable_name

        state = self._hass.states.get(target_entity)
        if state is None:
            return None, False, "ha"

        try:
            # Try to get numeric state value
            numeric_value = self._get_numeric_state(state)
            return numeric_value, True, "ha"
        except (ValueError, TypeError, NonNumericStateError):
            # For non-numeric states, keep as string
            return state.state, True, "ha"

    def _get_numeric_state(self, state: State) -> float:
        """Extract numeric value from state object."""
        try:
            return float(state.state)
        except (ValueError, TypeError):
            # Check for common non-numeric states that should be converted
            state_str = str(state.state).lower()
            if state_str in ("on", "true", "open", "home"):
                return 1.0
            elif state_str in ("off", "false", "closed", "away"):
                return 0.0
            else:
                raise NonNumericStateError(state.state, f"Cannot convert state '{state.state}' to numeric value") from None


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
            if isinstance(var_value, (int, float)):
                results[var_name] = (var_value, True, "literal")
            else:
                # Handle entity ID resolution (string or None)
                results[var_name] = self.resolve_variable(var_name, var_value)
        return results
