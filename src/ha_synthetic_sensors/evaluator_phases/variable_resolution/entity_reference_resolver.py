"""Entity reference resolver for synthetic sensor package."""

import logging
from typing import Any

from ...constants_entities import is_valid_entity_id
from ...exceptions import MissingDependencyError
from ...utils_resolvers import resolve_via_data_provider_entity, resolve_via_hass_entity
from .base_resolver import VariableResolver

_LOGGER = logging.getLogger(__name__)


class EntityReferenceResolver(VariableResolver):
    """Resolver for entity references like 'sensor.temperature'."""

    def __init__(self) -> None:
        """Initialize the entity reference resolver."""
        self._dependency_handler: Any = None

    def set_dependency_handler(self, dependency_handler: Any) -> None:
        """Set the dependency handler for entity resolution."""
        self._dependency_handler = dependency_handler

    def can_resolve(self, variable_name: str, variable_value: str | Any) -> bool:
        """Determine if this resolver can handle entity references."""
        if isinstance(variable_value, str):
            # Check if it looks like an entity ID using centralized validation
            # Get hass from dependency handler if available
            hass = getattr(self._dependency_handler, "hass", None) if self._dependency_handler else None
            if hass is None:
                # If no hass available, just check basic format
                return "." in variable_value and variable_value.split(".")[0].isalpha()
            return is_valid_entity_id(variable_value, hass)
        return False

    def resolve(self, variable_name: str, variable_value: str | Any, context: dict[str, Any]) -> Any | None:
        """Resolve an entity reference."""
        if not isinstance(variable_value, str):
            return None

        # Check if the entity is available in the context (already resolved)
        context_result = self._check_context_resolution(variable_value, context)
        if context_result is not None:
            return context_result

        # Try data provider resolution first
        data_provider_result = resolve_via_data_provider_entity(self._dependency_handler, variable_value, variable_value)
        if data_provider_result is not None:
            return data_provider_result

        # Try HASS state lookup
        hass_result = resolve_via_hass_entity(self._dependency_handler, variable_value, variable_value)
        if hass_result is not None:
            return hass_result

        # Try direct resolution
        direct_result = self._resolve_via_direct_lookup(variable_value)
        if direct_result is not None:
            return direct_result

        # Entity cannot be resolved - raise MissingDependencyError according to the reference guide
        _LOGGER.debug("Entity reference resolver: could not resolve '%s'", variable_value)
        raise MissingDependencyError(variable_value)

    def _check_context_resolution(self, variable_value: str, context: dict[str, Any]) -> Any | None:
        """Check if the entity is already resolved in the context."""
        if variable_value in context:
            context_value = context[variable_value]
            # Only return the context value if it's already resolved (not a raw entity ID)
            if context_value != variable_value:
                return context_value
            # If the context value is the same as variable_value (raw entity ID), continue to resolve it
        return None

    def _resolve_via_direct_lookup(self, variable_value: str) -> Any | None:
        """Resolve entity via direct lookup."""
        if not (self._dependency_handler and hasattr(self._dependency_handler, "get_entity_state")):
            return None

        value = self._dependency_handler.get_entity_state(variable_value)
        if value is not None:
            _LOGGER.debug("Entity reference resolver: resolved '%s' to %s via direct lookup", variable_value, value)
            return value
        return None
