"""Cross-sensor dependency manager for handling cross-sensor dependencies."""

import logging
import re
from typing import Any

from ...config_models import SensorConfig
from .base_manager import DependencyManager

_LOGGER = logging.getLogger(__name__)


class CrossSensorDependencyManager(DependencyManager):
    """Manages evaluation order for cross-sensor dependencies.

    This manager handles:
    - Analysis of cross-sensor dependencies from formulas
    - Calculation of evaluation order using topological sort
    - Detection of circular dependencies between sensors
    - Validation of cross-sensor dependency graphs
    """

    def __init__(self) -> None:
        """Initialize the cross-sensor dependency manager."""
        self._sensor_registry_phase = None

    def can_manage(self, manager_type: str, context: dict[str, Any] | None = None) -> bool:
        """Determine if this manager can handle cross-sensor dependency management."""
        return manager_type in {
            "cross_sensor_analysis",
            "evaluation_order",
            "cross_sensor_circular_detection",
            "validate_cross_sensor_deps",
        }

    def manage(self, manager_type: str, context: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Manage cross-sensor dependencies based on the manager type."""
        if context is None:
            context = {}

        if manager_type == "cross_sensor_analysis":
            return self._analyze_cross_sensor_dependencies(context.get("sensors", []), context.get("sensor_registry", {}))
        if manager_type == "evaluation_order":
            return self._get_evaluation_order(context.get("sensor_dependencies", {}), context.get("sensor_registry", {}))
        if manager_type == "cross_sensor_circular_detection":
            return self._detect_cross_sensor_circular_references(
                context.get("sensor_dependencies", {}), context.get("sensor_registry", {})
            )
        if manager_type == "validate_cross_sensor_deps":
            return self._validate_cross_sensor_dependencies(
                context.get("sensor_dependencies", {}), context.get("sensor_registry", {})
            )

        return None

    def set_sensor_registry_phase(self, sensor_registry_phase: Any) -> None:
        """Set the sensor registry phase for cross-sensor dependency resolution."""
        self._sensor_registry_phase = sensor_registry_phase

    def _analyze_cross_sensor_dependencies(
        self, sensors: list[SensorConfig], sensor_registry: dict[str, Any]
    ) -> dict[str, set[str]]:
        """Analyze which sensors depend on other sensors.

        Args:
            sensors: List of sensor configurations to analyze
            sensor_registry: Current sensor registry for cross-sensor references

        Returns:
            Dictionary mapping sensor names to sets of their dependencies
        """
        dependencies: dict[str, set[str]] = {}

        for sensor in sensors:
            sensor_deps: set[str] = set()

            # Analyze each formula in the sensor
            for formula in sensor.formulas:
                formula_deps = self._extract_cross_sensor_dependencies_from_formula(formula.formula, sensor_registry)
                sensor_deps.update(formula_deps)

            dependencies[sensor.unique_id] = sensor_deps

        _LOGGER.debug("Cross-sensor dependency analysis: %s", dependencies)
        return dependencies

    def _extract_cross_sensor_dependencies_from_formula(self, formula: str, sensor_registry: dict[str, Any]) -> set[str]:
        """Extract cross-sensor dependencies from a formula.

        Args:
            formula: The formula to analyze
            sensor_registry: Current sensor registry

        Returns:
            Set of sensor names that this formula depends on
        """
        dependencies: set[str] = set()

        if not self._sensor_registry_phase:
            return dependencies

        # Get all registered sensor names
        registered_sensors = self._sensor_registry_phase.get_registered_sensors()

        # Simple token-based analysis - look for sensor names in the formula
        # This is a basic implementation; a more sophisticated parser could be used
        for sensor_name in registered_sensors:
            if sensor_name in formula and self._is_valid_cross_sensor_reference(formula, sensor_name):
                dependencies.add(sensor_name)

        return dependencies

    def _is_valid_cross_sensor_reference(self, formula: str, sensor_name: str) -> bool:
        """Check if a sensor name in a formula is a valid cross-sensor reference.

        Args:
            formula: The formula to check
            sensor_name: The sensor name to look for

        Returns:
            True if the sensor name is a valid cross-sensor reference
        """
        # This is a simplified implementation
        # In practice, we'd use proper parsing to distinguish between:
        # - Variable names that happen to contain sensor names
        # - Actual cross-sensor references
        # - String literals containing sensor names

        # For now, we'll do a basic check that the sensor name is not part of a larger word
        # Look for the sensor name as a whole word or variable
        pattern = r"\b" + re.escape(sensor_name) + r"\b"
        return bool(re.search(pattern, formula))

    def _get_evaluation_order(self, sensor_dependencies: dict[str, set[str]], sensor_registry: dict[str, Any]) -> list[str]:
        """Return sensors in dependency order using topological sort.

        Args:
            sensor_dependencies: Dictionary mapping sensor names to their dependencies
            sensor_registry: Current sensor registry

        Returns:
            List of sensor names in evaluation order
        """
        # Create a copy of dependencies for processing
        deps = {sensor: deps.copy() for sensor, deps in sensor_dependencies.items()}

        # Find all sensors (both in dependencies and as dependencies)
        all_sensors = set(deps.keys())
        for sensor_deps in deps.values():
            all_sensors.update(sensor_deps)

        # Initialize result and in-degree count
        result: list[str] = []
        in_degree = dict.fromkeys(all_sensors, 0)

        # Calculate in-degrees
        for _sensor, sensor_deps in deps.items():
            for dep in sensor_deps:
                if dep in in_degree:
                    in_degree[dep] += 1

        # Find sensors with no dependencies (in-degree = 0)
        queue = [sensor for sensor, degree in in_degree.items() if degree == 0]

        # Process queue
        while queue:
            current = queue.pop(0)
            result.append(current)

            # Reduce in-degree for all sensors that depend on current
            for sensor, sensor_deps in deps.items():
                if current in sensor_deps:
                    in_degree[sensor] -= 1
                    if in_degree[sensor] == 0:
                        queue.append(sensor)

        # Check for circular dependencies
        if len(result) != len(all_sensors):
            remaining = [sensor for sensor in all_sensors if sensor not in result]
            _LOGGER.warning("Circular dependency detected. Sensors not in evaluation order: %s", remaining)

            # Add remaining sensors at the end (they have circular dependencies)
            result.extend(remaining)

        _LOGGER.debug("Cross-sensor evaluation order: %s", result)
        return result

    def _detect_cross_sensor_circular_references(
        self, sensor_dependencies: dict[str, set[str]], sensor_registry: dict[str, Any]
    ) -> list[str]:
        """Detect circular dependencies between sensors.

        Args:
            sensor_dependencies: Dictionary mapping sensor names to their dependencies
            sensor_registry: Current sensor registry

        Returns:
            List of sensor names involved in circular references
        """
        circular_refs: list[str] = []

        # Use depth-first search to detect cycles
        visited = set()
        rec_stack = set()

        def has_cycle(sensor: str) -> bool:
            """Check if there's a cycle starting from this sensor."""
            if sensor in rec_stack:
                return True
            if sensor in visited:
                return False

            visited.add(sensor)
            rec_stack.add(sensor)

            for dep in sensor_dependencies.get(sensor, set()):
                if has_cycle(dep):
                    if dep not in circular_refs:
                        circular_refs.append(dep)
                    return True

            rec_stack.remove(sensor)
            return False

        # Check for cycles starting from each sensor
        for sensor in sensor_dependencies:
            if sensor not in visited and has_cycle(sensor) and sensor not in circular_refs:
                circular_refs.append(sensor)

        if circular_refs:
            _LOGGER.warning("Cross-sensor circular references detected: %s", circular_refs)

        return circular_refs

    def _validate_cross_sensor_dependencies(
        self, sensor_dependencies: dict[str, set[str]], sensor_registry: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate cross-sensor dependencies.

        Args:
            sensor_dependencies: Dictionary mapping sensor names to their dependencies
            sensor_registry: Current sensor registry

        Returns:
            Validation result with status and any issues found
        """
        issues: list[str] = []

        # Check for circular dependencies
        circular_refs = self._detect_cross_sensor_circular_references(sensor_dependencies, sensor_registry)
        if circular_refs:
            issues.append(f"Circular dependencies detected: {', '.join(circular_refs)}")

        # Check for missing sensor references
        if self._sensor_registry_phase:
            registered_sensors = self._sensor_registry_phase.get_registered_sensors()

            for sensor, deps in sensor_dependencies.items():
                for dep in deps:
                    if dep not in registered_sensors:
                        issues.append(f"Sensor '{sensor}' references unregistered sensor '{dep}'")

        # Check evaluation order
        try:
            evaluation_order = self._get_evaluation_order(sensor_dependencies, sensor_registry)
            if len(evaluation_order) != len(set(evaluation_order)):
                issues.append("Duplicate sensors in evaluation order")
        except Exception as e:
            issues.append(f"Error calculating evaluation order: {e}")

        is_valid = len(issues) == 0

        result = {
            "valid": is_valid,
            "issues": issues,
            "evaluation_order": self._get_evaluation_order(sensor_dependencies, sensor_registry) if is_valid else [],
            "circular_references": circular_refs,
        }

        _LOGGER.debug("Cross-sensor dependency validation: %s", result)
        return result

    def get_manager_name(self) -> str:
        """Get the name of this manager for logging and debugging."""
        return "CrossSensorDependencyManager"
