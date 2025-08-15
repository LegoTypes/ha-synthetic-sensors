"""Cross-sensor dependency manager for handling cross-sensor dependencies."""

import logging
import re
from typing import Any

from ...config_models import SensorConfig
from ...dependency_parser import DependencyParser
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

            # Analyze each formula in the sensor, passing current sensor for auto self-exclusion
            for formula in sensor.formulas:
                formula_deps = self._extract_cross_sensor_dependencies_from_formula(
                    formula.formula, sensor_registry, current_sensor=sensor
                )
                sensor_deps.update(formula_deps)
                _LOGGER.debug("Sensor '%s' formula '%s' dependencies: %s", sensor.unique_id, formula.formula, formula_deps)

            dependencies[sensor.unique_id] = sensor_deps
            _LOGGER.debug("Sensor '%s' total dependencies: %s", sensor.unique_id, sensor_deps)

        _LOGGER.debug("Cross-sensor dependency analysis: %s", dependencies)
        return dependencies

    def _extract_cross_sensor_dependencies_from_formula(
        self, formula: str, sensor_registry: dict[str, Any], current_sensor: Any = None
    ) -> set[str]:
        """Extract cross-sensor dependencies from a formula.

        Args:
            formula: The formula to analyze
            sensor_registry: Current sensor registry
            current_sensor: The sensor that owns this formula (for auto self-exclusion)

        Returns:
            Set of sensor names that this formula depends on
        """
        dependencies: set[str] = set()

        if not self._sensor_registry_phase:
            return dependencies

        # Get all registered sensor names
        registered_sensors = self._sensor_registry_phase.get_registered_sensors()

        # 1. Handle collection functions with auto self-exclusion
        collection_deps = self._extract_collection_function_dependencies(formula, sensor_registry, current_sensor)
        dependencies.update(collection_deps)

        # 2. Handle direct cross-sensor references (existing logic)
        for sensor_name in registered_sensors:
            if sensor_name in formula and self._is_valid_cross_sensor_reference(formula, sensor_name):
                dependencies.add(sensor_name)

        return dependencies

    def _extract_collection_function_dependencies(
        self, formula: str, sensor_registry: dict[str, Any], current_sensor: Any = None
    ) -> set[str]:
        """Extract dependencies from collection functions, applying auto self-exclusion.

        This method detects collection functions like sum('device_class:power') and determines
        which sensors they would include, automatically excluding the current sensor if it
        would be included in the collection to prevent circular dependencies.

        Args:
            formula: The formula to analyze
            sensor_registry: Current sensor registry
            current_sensor: The sensor that owns this formula (for auto self-exclusion)

        Returns:
            Set of sensor names that collection functions depend on (excluding self)
        """
        dependencies: set[str] = set()

        try:
            # Use the dependency parser to extract dynamic queries (collection functions)
            parser = DependencyParser()
            dynamic_queries = parser.extract_dynamic_queries(formula)

            if not dynamic_queries:
                return dependencies

            # For each collection function, determine what sensors it would include
            for query in dynamic_queries:
                collection_sensors = self._resolve_collection_dependencies(query, sensor_registry)

                # AUTO SELF-EXCLUSION: Remove current sensor if it would be included
                if current_sensor and hasattr(current_sensor, "unique_id") and current_sensor.unique_id in collection_sensors:
                    collection_sensors.discard(current_sensor.unique_id)
                    _LOGGER.debug(
                        "Auto-excluded sensor '%s' from collection function dependencies to prevent circular dependency",
                        current_sensor.unique_id,
                    )

                dependencies.update(collection_sensors)

        except Exception as e:
            _LOGGER.warning("Error analyzing collection functions in formula '%s': %s", formula, e)

        return dependencies

    def _resolve_collection_dependencies(self, query: Any, sensor_registry: dict[str, Any]) -> set[str]:
        """Resolve which sensors a collection function would depend on.

        This performs a static analysis of what sensors would be included in a collection
        function, applying the same filtering logic as the runtime collection resolver
        but without needing actual entity registry data.

        Args:
            query: Dynamic query object from dependency parser
            sensor_registry: Current sensor registry

        Returns:
            Set of sensor names the collection would depend on
        """
        dependencies: set[str] = set()

        # Handle device_class pattern specifically (most common case)
        if query.query_type == "device_class":
            # Find all sensors in registry with matching device_class
            target_device_class = query.pattern.lower()

            for sensor_name, sensor_data in sensor_registry.items():
                if isinstance(sensor_data, dict):
                    # Extract device_class from sensor metadata
                    metadata = sensor_data.get("metadata", {})
                    if isinstance(metadata, dict):
                        sensor_device_class = metadata.get("device_class", "").lower()
                        if sensor_device_class == target_device_class:
                            dependencies.add(sensor_name)

        # Add support for other collection patterns as needed (regex, area, etc.)
        # For now, focus on device_class which is the most common cause of circular deps

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

        # Initialize result and out-degree count for evaluation order
        result: list[str] = []
        out_degree = {sensor: len(deps.get(sensor, set())) for sensor in all_sensors}

        _LOGGER.debug("Dependency graph: %s", deps)
        _LOGGER.debug("Out-degree calculation: %s", out_degree)

        # Find sensors with no outgoing dependencies (don't depend on others) - these can be evaluated first
        queue = [sensor for sensor, degree in out_degree.items() if degree == 0]
        _LOGGER.debug("Initial queue (sensors with no outgoing dependencies): %s", queue)

        # Process queue - remove dependencies from remaining sensors
        processed = set()
        while queue:
            current = queue.pop(0)
            result.append(current)
            processed.add(current)

            # For each remaining sensor, check if its dependencies are now satisfied
            for sensor in all_sensors:
                if sensor not in processed and sensor not in queue:
                    remaining_deps = deps.get(sensor, set()) - processed
                    if len(remaining_deps) == 0:
                        queue.append(sensor)

        # Check for circular dependencies
        if len(result) != len(all_sensors):
            # POLICY: Cross-sensor cycles are non-fatal; do not log to avoid noise.
            # Return partial order; runtime will use last-known values.
            pass

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

        # POLICY: Cross-sensor cycles are allowed; emit a warning and return the list without raising.
        if circular_refs:
            # WFF Valid warning for HA states, typical in HA integrations
            _LOGGER.warning("Circular cross-sensor dependency detected among: %s", sorted(set(circular_refs)))
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

        # Check for circular dependencies (non-fatal)
        circular_refs = self._detect_cross_sensor_circular_references(sensor_dependencies, sensor_registry)
        if circular_refs:
            # POLICY: Do not include non-fatal cycles in issues to avoid noise.
            pass

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

        return result

    def get_manager_name(self) -> str:
        """Get the name of this manager for logging and debugging."""
        return "CrossSensorDependencyManager"
