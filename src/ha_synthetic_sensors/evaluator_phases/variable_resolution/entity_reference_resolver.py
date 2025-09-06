"""Entity reference resolver for synthetic sensor package."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...hierarchical_context_dict import HierarchicalContextDict

from ...constants_entities import is_valid_entity_id
from ...exceptions import MissingDependencyError
from ...type_definitions import ContextValue
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
            # Check if it looks like an entity ID (basic format check)
            # This allows both HA entities and integration entities to be tried
            if "." in variable_value and variable_value.split(".")[0].isalpha():
                return True

            # Also check HA registry if available for additional validation
            hass = getattr(self._dependency_handler, "hass", None) if self._dependency_handler else None
            if hass is not None:
                return is_valid_entity_id(variable_value, hass)
        return False

    def resolve(self, variable_name: str, variable_value: str | Any, context: "HierarchicalContextDict") -> ContextValue:
        """Resolve an entity reference."""

        if not isinstance(variable_value, str):
            _LOGGER.debug("ENTITY_RESOLVER_DEBUG: variable_value is not string, returning None")
            return None

        # Check if the entity is available in the context (already resolved)
        context_result = self._check_context_resolution(variable_value, context)
        if context_result is not None:
            return context_result

        # Try data provider resolution first
        _LOGGER.debug("ENTITY_RESOLVER_DEBUG: Trying data provider resolution for '%s'", variable_value)
        data_provider_result = resolve_via_data_provider_entity(self._dependency_handler, variable_value, variable_value)
        if data_provider_result is not None:
            _LOGGER.debug("ENTITY_RESOLVER_DEBUG: Data provider resolved '%s' to %s", variable_value, data_provider_result)
            return data_provider_result  # type: ignore[no-any-return]
        _LOGGER.debug("ENTITY_RESOLVER_DEBUG: Data provider could not resolve '%s'", variable_value)

        # Try HASS state lookup
        hass_result = resolve_via_hass_entity(self._dependency_handler, variable_value, variable_value)
        if hass_result is not None:
            return hass_result  # type: ignore[no-any-return]

        # Try direct resolution
        direct_result = self._resolve_via_direct_lookup(variable_value)
        if direct_result is not None:
            return direct_result  # type: ignore[no-any-return]

        # Entity cannot be resolved - this is a missing dependency (fatal error)
        # Missing entities should raise MissingDependencyError, not be converted to STATE_NONE
        _LOGGER.debug("Entity reference resolver: could not resolve '%s', raising MissingDependencyError", variable_value)
        raise MissingDependencyError(f"Entity '{variable_value}' not found")

    def _check_context_resolution(self, variable_value: str, context: "HierarchicalContextDict") -> ContextValue:
        """Check if the entity is already resolved in the context."""
        if variable_value in context:
            context_value = context[variable_value]
            # If there's a ReferenceValue in context, return it (it's already resolved)
            from ...type_definitions import ReferenceValue

            if isinstance(context_value, ReferenceValue):
                return context_value
            # For other context values (callable, dict, None), return them as-is
            if context_value is not None:
                return context_value
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
