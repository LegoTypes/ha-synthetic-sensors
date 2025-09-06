"""Cross-sensor reference resolver for handling cross-sensor references."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...hierarchical_context_dict import HierarchicalContextDict

from ...exceptions import CrossSensorResolutionError, DependencyValidationError, MissingDependencyError
from ...type_definitions import ContextValue
from .base_resolver import VariableResolver

_LOGGER = logging.getLogger(__name__)


class CrossSensorReferenceResolver(VariableResolver):
    """Resolver for cross-sensor references like 'base_power_sensor'."""

    def __init__(self, sensor_registry_phase: Any = None) -> None:
        """Initialize the cross-sensor reference resolver."""
        self._sensor_registry_phase = sensor_registry_phase
        self._dependency_usage_tracker: dict[str, int] = {}

    def can_resolve(self, variable_name: str, variable_value: str | Any) -> bool:
        """Determine if this resolver can handle cross-sensor references."""
        # For cross-sensor references, the variable name and value are the same (the sensor name)
        if isinstance(variable_value, str) and variable_name == variable_value:
            # Check if it's a registered sensor name
            if self._sensor_registry_phase:
                return bool(self._sensor_registry_phase.is_sensor_registered(variable_value))
            return False
        return False

    def resolve(self, variable_name: str, variable_value: str | Any, context: "HierarchicalContextDict") -> ContextValue:
        """Enhanced cross-sensor reference resolution with dependency tracking."""
        if not isinstance(variable_value, str):
            return None

        # Enhanced error handling with specific error types
        if not self._sensor_registry_phase:
            raise MissingDependencyError(
                f"Cross-sensor reference '{variable_value}' cannot be resolved: registry not available"
            )

        # Track dependency usage for debugging
        self._track_dependency_usage(variable_name, variable_value)

        # Validate dependency availability before resolution
        if not self._validate_dependency_availability(variable_value):
            raise CrossSensorResolutionError(variable_value, "dependency validation failed")

        # Get the sensor value from the registry phase
        sensor_value = self._sensor_registry_phase.get_sensor_value(variable_value)

        if sensor_value is not None:
            _LOGGER.debug("Cross-sensor resolver: resolved '%s' to value '%s'", variable_value, sensor_value)
            # Cast to ContextValue since sensor registry returns Any but we know it's a valid context value
            return sensor_value  # type: ignore[no-any-return]

        # Enhanced error handling for missing sensor values
        if self._sensor_registry_phase.is_sensor_registered(variable_value):
            raise DependencyValidationError(variable_value, "sensor registered but value not yet evaluated")
        raise MissingDependencyError(f"Cross-sensor reference '{variable_value}' not found in registry")

    def _track_dependency_usage(self, variable_name: str, variable_value: str) -> None:
        """Track dependency usage for debugging and validation."""
        usage_key = f"{variable_name}:{variable_value}"
        self._dependency_usage_tracker[usage_key] = self._dependency_usage_tracker.get(usage_key, 0) + 1
        _LOGGER.debug(
            "Cross-sensor dependency usage tracked: %s (count: %d)", usage_key, self._dependency_usage_tracker[usage_key]
        )

    def _validate_dependency_availability(self, variable_value: str) -> bool:
        """Validate that a dependency is available before resolution."""
        if not self._sensor_registry_phase:
            return False

        # Check if sensor is registered
        if not self._sensor_registry_phase.is_sensor_registered(variable_value):
            _LOGGER.debug("Cross-sensor dependency validation failed: sensor '%s' not registered", variable_value)
            return False

        # Check if sensor has a value (not None)
        sensor_value = self._sensor_registry_phase.get_sensor_value(variable_value)
        if sensor_value is None:
            _LOGGER.debug("Cross-sensor dependency validation failed: sensor '%s' has no value", variable_value)
            return False

        return True

    def get_dependency_usage_stats(self) -> dict[str, int]:
        """Get dependency usage statistics for debugging."""
        return self._dependency_usage_tracker.copy()

    def clear_dependency_usage_tracker(self) -> None:
        """Clear the dependency usage tracker."""
        self._dependency_usage_tracker.clear()

    def set_sensor_registry_phase(self, sensor_registry_phase: Any) -> None:
        """Set the sensor registry phase for cross-sensor reference resolution."""
        self._sensor_registry_phase = sensor_registry_phase
