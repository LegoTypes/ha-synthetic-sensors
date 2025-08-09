"""Factory for creating and managing variable resolvers."""

from collections.abc import Callable
import logging
from typing import Any

from ...type_definitions import DataProviderResult
from .attribute_reference_resolver import AttributeReferenceResolver
from .base_resolver import VariableResolver
from .config_variable_resolver import ConfigVariableResolver
from .cross_sensor_resolver import CrossSensorReferenceResolver
from .entity_attribute_resolver import EntityAttributeResolver
from .entity_reference_resolver import EntityReferenceResolver
from .self_reference_resolver import SelfReferenceResolver
from .state_attribute_resolver import StateAttributeResolver
from .state_resolver import StateResolver

_LOGGER = logging.getLogger(__name__)


class VariableResolverFactory:
    """Factory for creating and managing variable resolvers."""

    def __init__(
        self,
        sensor_to_backing_mapping: dict[str, str] | None = None,
        data_provider_callback: Callable[[str], DataProviderResult] | None = None,
        hass: Any = None,
    ) -> None:
        """Initialize the variable resolver factory with default resolvers."""
        self._resolvers: list[VariableResolver] = []
        self._cross_sensor_resolver: CrossSensorReferenceResolver | None = None
        self._self_reference_resolver: SelfReferenceResolver | None = None
        self._entity_attribute_resolver: EntityAttributeResolver | None = None
        self._sensor_to_backing_mapping = sensor_to_backing_mapping or {}
        self._data_provider_callback = data_provider_callback
        self._hass = hass
        self._state_resolver: StateResolver | None = None
        self._register_default_resolvers()

    @property
    def sensor_to_backing_mapping(self) -> dict[str, str]:
        """Get the sensor-to-backing mapping."""
        return self._sensor_to_backing_mapping

    @property
    def data_provider_callback(self) -> Callable[[str], DataProviderResult] | None:
        """Get the data provider callback."""
        return self._data_provider_callback

    def _register_default_resolvers(self) -> None:
        """Register the default set of resolvers in priority order."""
        # Register specific resolvers first (higher priority)
        self.register_resolver(StateAttributeResolver(self._sensor_to_backing_mapping, self._data_provider_callback))

        # Create and store state resolver with backing entity support and HA instance
        self._state_resolver = StateResolver(self._sensor_to_backing_mapping, self._data_provider_callback, self._hass)
        self.register_resolver(self._state_resolver)

        # Create and store self-reference resolver for entity ID self-references
        self._self_reference_resolver = SelfReferenceResolver()
        self._self_reference_resolver.set_sensor_to_backing_mapping(self._sensor_to_backing_mapping)
        self.register_resolver(self._self_reference_resolver)

        # Create and store entity attribute resolver for variable.attribute patterns
        self._entity_attribute_resolver = EntityAttributeResolver()
        self.register_resolver(self._entity_attribute_resolver)

        self.register_resolver(EntityReferenceResolver())

        # Register attribute reference resolver for attribute-to-attribute references
        self.register_resolver(AttributeReferenceResolver())

        # Create and store cross-sensor resolver for later configuration
        self._cross_sensor_resolver = CrossSensorReferenceResolver()
        self.register_resolver(self._cross_sensor_resolver)

        # Register ConfigVariableResolver last so it's checked as fallback
        self.register_resolver(ConfigVariableResolver())

    def set_sensor_registry_phase(self, sensor_registry_phase: Any) -> None:
        """Set the sensor registry phase for resolvers that need it."""
        if self._cross_sensor_resolver and hasattr(self._cross_sensor_resolver, "set_sensor_registry_phase"):
            self._cross_sensor_resolver.set_sensor_registry_phase(sensor_registry_phase)
            _LOGGER.debug("Updated cross-sensor resolver with sensor registry phase")

        if self._self_reference_resolver and hasattr(self._self_reference_resolver, "set_sensor_registry_phase"):
            self._self_reference_resolver.set_sensor_registry_phase(sensor_registry_phase)
            _LOGGER.debug("Updated self-reference resolver with sensor registry phase")

    def set_dependency_handler(self, dependency_handler: Any) -> None:
        """Set the dependency handler for entity resolution."""
        for resolver in self._resolvers:
            if hasattr(resolver, "set_dependency_handler"):
                resolver.set_dependency_handler(dependency_handler)
            if hasattr(resolver, "set_resolver_factory"):
                resolver.set_resolver_factory(self)
        _LOGGER.debug("Updated resolvers with dependency handler and resolver factory")

    def register_resolver(self, resolver: VariableResolver) -> None:
        """Register a resolver with the factory."""
        self._resolvers.append(resolver)
        _LOGGER.debug("Registered resolver: %s", resolver.get_resolver_name())

    def get_resolver_for_variable(self, variable_name: str, variable_value: str | Any) -> VariableResolver | None:
        """Get the appropriate resolver for a given variable."""
        for resolver in self._resolvers:
            if resolver.can_resolve(variable_name, variable_value):
                return resolver
        return None

    def resolve_variable(self, variable_name: str, variable_value: str | Any, context: dict[str, Any]) -> Any | None:
        """Resolve a variable using the appropriate resolver."""
        _LOGGER.debug("RESOLVER_FACTORY: Resolving variable %s with value %s", variable_name, variable_value)
        # Check if any resolver can handle this variable
        for resolver in self._resolvers:
            if resolver.can_resolve(variable_name, variable_value):
                result = resolver.resolve(variable_name, variable_value, context)
                return result
        # No resolver found
        _LOGGER.debug("RESOLVER_FACTORY: No resolver found for variable %s", variable_name)
        return None

    def get_all_resolvers(self) -> list[VariableResolver]:
        """Get all registered resolvers."""
        return self._resolvers.copy()

    def update_sensor_to_backing_mapping(
        self,
        sensor_to_backing_mapping: dict[str, str],
        data_provider_callback: Callable[[str], DataProviderResult] | None = None,
    ) -> None:
        """Update the sensor-to-backing mapping and data provider callback for all resolvers."""
        self._sensor_to_backing_mapping = sensor_to_backing_mapping
        if data_provider_callback:
            self._data_provider_callback = data_provider_callback

        # Update existing resolvers that need the mapping
        for resolver in self._resolvers:
            # Use public methods to avoid protected access warnings
            resolver.set_sensor_to_backing_mapping(self.sensor_to_backing_mapping)
            if data_provider_callback:
                resolver.set_data_provider_callback(self.data_provider_callback)

        _LOGGER.debug("Updated resolver factory with sensor-to-backing mapping: %d mappings", len(sensor_to_backing_mapping))

    def clear_resolvers(self) -> None:
        """Clear all registered resolvers."""
        self._resolvers.clear()
        self._register_default_resolvers()
