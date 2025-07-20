"""Entity reference resolver for handling entity references."""

import logging
from typing import Any

from ...type_definitions import ContextValue
from .base_resolver import VariableResolver

_LOGGER = logging.getLogger(__name__)


class EntityReferenceResolver(VariableResolver):
    """Resolver for entity references like 'sensor.temperature'."""

    def __init__(self) -> None:
        """Initialize the entity reference resolver."""
        self._dependency_handler = None

    def set_dependency_handler(self, dependency_handler: Any) -> None:
        """Set the dependency handler for entity resolution."""
        self._dependency_handler = dependency_handler

    def can_resolve(self, variable_name: str, variable_value: str | Any) -> bool:
        """Determine if this resolver can handle entity references."""
        if isinstance(variable_value, str):
            # Check if it looks like an entity ID (contains a dot and starts with a valid entity type)
            return "." in variable_value and variable_value.split(".")[0] in [
                "sensor",
                "binary_sensor",
                "switch",
                "light",
                "climate",
                "input_number",
                "input_text",
                "span",  # Add span for integration entities
            ]
        return False

    def resolve(self, variable_name: str, variable_value: str | Any, context: dict[str, ContextValue]) -> Any | None:
        """Resolve an entity reference."""
        if not isinstance(variable_value, str):
            return None

        # Check if the entity is available in the context (already resolved)
        if variable_value in context:
            return context[variable_value]

        # Try to use the dependency handler's data provider callback first
        if self._dependency_handler and hasattr(self._dependency_handler, "data_provider_callback"):
            data_provider_callback = self._dependency_handler.data_provider_callback
            if data_provider_callback and callable(data_provider_callback):
                try:
                    result = data_provider_callback(variable_value)
                    if result and result.get("exists"):
                        value = result.get("value")
                        if value is not None:
                            _LOGGER.debug("Entity reference resolver: resolved '%s' to %s", variable_value, value)
                            return value
                except Exception as e:
                    _LOGGER.warning("Error resolving entity reference '%s' via data provider: %s", variable_value, e)

        # If we have a dependency handler with HASS access, try direct state lookup
        if self._dependency_handler and hasattr(self._dependency_handler, "_hass"):
            try:
                hass = self._dependency_handler._hass
                if hass and hasattr(hass, "states"):
                    state = hass.states.get(variable_value)
                    if state is not None:
                        # Convert state value to appropriate type
                        state_value = state.state
                        if state_value in ("unavailable", "unknown", "None"):
                            _LOGGER.debug("Entity reference resolver: entity '%s' has unavailable state", variable_value)
                            return None
                        
                        # Try to convert to numeric value
                        try:
                            if "." in state_value:
                                numeric_value = float(state_value)
                            else:
                                numeric_value = int(state_value)
                            _LOGGER.debug("Entity reference resolver: resolved '%s' to %s via HASS", variable_value, numeric_value)
                            return numeric_value
                        except ValueError:
                            # Handle boolean-like strings
                            if state_value.lower() in ("on", "true", "yes", "1"):
                                _LOGGER.debug("Entity reference resolver: resolved '%s' to 1.0 (boolean true) via HASS", variable_value)
                                return 1.0
                            elif state_value.lower() in ("off", "false", "no", "0"):
                                _LOGGER.debug("Entity reference resolver: resolved '%s' to 0.0 (boolean false) via HASS", variable_value)
                                return 0.0
                            else:
                                # Non-numeric, non-boolean state, return as string
                                _LOGGER.debug("Entity reference resolver: resolved '%s' to '%s' (non-numeric) via HASS", variable_value, state_value)
                                return state_value
            except Exception as e:
                _LOGGER.warning("Error resolving entity reference '%s' via HASS: %s", variable_value, e)

        # If we have a dependency handler but no data provider callback or HASS, try direct resolution
        if self._dependency_handler and hasattr(self._dependency_handler, "get_entity_state"):
            try:
                value = self._dependency_handler.get_entity_state(variable_value)
                if value is not None:
                    _LOGGER.debug("Entity reference resolver: resolved '%s' to %s via direct lookup", variable_value, value)
                    return value
            except Exception as e:
                _LOGGER.warning("Error resolving entity reference '%s' via direct lookup: %s", variable_value, e)

        _LOGGER.debug("Entity reference resolver: could not resolve '%s'", variable_value)
        return None
