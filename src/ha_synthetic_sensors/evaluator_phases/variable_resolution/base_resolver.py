"""Base interface for variable resolvers in the compiler-like evaluation system."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...hierarchical_context_dict import HierarchicalContextDict

from ...type_definitions import ContextValue


class VariableResolver:
    """Base interface for variable resolvers in the compiler-like evaluation system."""

    def can_resolve(self, variable_name: str, variable_value: str | Any) -> bool:
        """Determine if this resolver can handle the variable."""
        return False

    def resolve(self, variable_name: str, variable_value: str | Any, context: "HierarchicalContextDict") -> ContextValue:
        """Resolve a variable."""
        return None

    def get_resolver_name(self) -> str:
        """Get the name of this resolver for logging and debugging."""
        return self.__class__.__name__

    def set_sensor_to_backing_mapping(self, mapping: dict[str, str]) -> None:
        """Set the sensor-to-backing mapping for this resolver."""
        if hasattr(self, "_sensor_to_backing_mapping"):
            self._sensor_to_backing_mapping = mapping

    def set_data_provider_callback(self, callback: Any) -> None:
        """Set the data provider callback for this resolver."""
        if hasattr(self, "_data_provider_callback"):
            self._data_provider_callback = callback
