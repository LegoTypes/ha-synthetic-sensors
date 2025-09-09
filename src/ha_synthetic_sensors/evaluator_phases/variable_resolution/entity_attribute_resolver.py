"""Entity attribute resolver for synthetic sensor package."""

import logging
from typing import TYPE_CHECKING, Any

from ...exceptions import MissingDependencyError
from ...shared_constants import get_ha_domains
from ...type_definitions import ContextValue
from ...utils_resolvers import resolve_via_data_provider_attribute, resolve_via_hass_attribute
from .base_resolver import VariableResolver

if TYPE_CHECKING:
    from ...hierarchical_context_dict import HierarchicalContextDict

_LOGGER = logging.getLogger(__name__)


class EntityAttributeResolver(VariableResolver):
    """Resolver for entity attribute references like 'device.battery_level' where device is a variable."""

    def __init__(self) -> None:
        """Initialize the entity attribute resolver."""
        self._dependency_handler: Any = None

    def set_dependency_handler(self, dependency_handler: Any) -> None:
        """Set the dependency handler for entity resolution."""
        self._dependency_handler = dependency_handler

    def can_resolve(self, variable_name: str, variable_value: str | Any) -> bool:
        """Determine if this resolver can handle entity attribute references."""
        if not isinstance(variable_value, str):
            return False

        # Check if it looks like an entity attribute reference (contains a dot)
        # and it's not a state.attribute or entity ID pattern
        # Use dynamic domain discovery instead of hardcoded list
        hass = getattr(self._dependency_handler, "hass", None) if self._dependency_handler else None
        ha_domains = get_ha_domains(hass) if hass else set()

        if "." in variable_value and not variable_value.startswith("state."):
            # Check if it's an entity ID using dynamic domain discovery
            if any(variable_value.startswith(f"{domain}.") for domain in ha_domains):
                return False
            # Simple heuristic: if it contains exactly one dot and doesn't look like an entity ID
            parts = variable_value.split(".")
            # Get hass from dependency handler if available
            hass = getattr(self._dependency_handler, "hass", None) if self._dependency_handler else None
            if len(parts) == 2 and parts[0] not in get_ha_domains(hass):
                return True

        return False

    def resolve(self, variable_name: str, variable_value: str | Any, context: "HierarchicalContextDict") -> ContextValue:
        """Resolve an entity attribute reference."""
        if not isinstance(variable_value, str):
            return None

        # Parse the attribute reference
        parsed = self._parse_attribute_reference(variable_value)
        if not parsed:
            return None

        entity_variable, attribute_name = parsed

        # Get the entity ID from context or formula config
        entity_id = self._get_entity_id_from_context(entity_variable, context)
        if not entity_id:
            return None

        _LOGGER.debug(
            "Entity attribute resolver: resolving attribute '%s' of entity '%s' (via variable '%s')",
            attribute_name,
            entity_id,
            entity_variable,
        )

        # Resolve the entity attribute using the same logic as EntityReferenceResolver
        return self._resolve_entity_attribute(entity_id, attribute_name, variable_value)  # type: ignore[no-any-return]

    def _resolve_entity_attribute(self, entity_id: str, attribute_name: str, original_reference: str) -> Any:
        """Resolve the entity attribute value using data provider or HA lookups."""
        # Try data provider resolution first
        data_provider_result = resolve_via_data_provider_attribute(
            self._dependency_handler, entity_id, attribute_name, original_reference
        )
        if data_provider_result is not None:
            return data_provider_result

        # Try HASS state lookup
        hass_result = resolve_via_hass_attribute(self._dependency_handler, entity_id, attribute_name, original_reference)
        if hass_result is not None:
            return hass_result

        # Could not resolve entity attribute
        _LOGGER.debug("Entity attribute resolver: could not resolve attribute '%s' of entity '%s'", attribute_name, entity_id)
        raise MissingDependencyError(f"Could not resolve attribute '{attribute_name}' of entity '{entity_id}'")

    def _parse_attribute_reference(self, variable_value: str) -> tuple[str, ...] | None:
        """Parse an attribute reference into entity variable and attribute name."""
        if "." not in variable_value:
            return None

        parts = variable_value.split(".", 1)
        if len(parts) != 2:
            return None

        return tuple(parts)

    def _get_entity_id_from_context(self, entity_variable: str, context: "HierarchicalContextDict") -> str | None:
        """Get the entity ID from context or formula config."""
        # Get formula_config from context to access original variable definitions
        formula_config = context.get("formula_config")
        if formula_config and hasattr(formula_config, "variables") and formula_config.variables:
            # Look up the original entity ID from the formula config
            entity_id = formula_config.variables.get(entity_variable)
            if not entity_id:
                _LOGGER.debug("Entity attribute resolver: variable '%s' not found in formula config", entity_variable)
                return None
        else:
            # Fallback: look up the entity variable in the context to get the entity ID
            if entity_variable not in context:
                _LOGGER.debug("Entity attribute resolver: variable '%s' not found in context", entity_variable)
                return None

            entity_id = context[entity_variable]

        if not isinstance(entity_id, str):
            _LOGGER.debug("Entity attribute resolver: variable '%s' is not a string: %s", entity_variable, entity_id)
            return None

        return entity_id
