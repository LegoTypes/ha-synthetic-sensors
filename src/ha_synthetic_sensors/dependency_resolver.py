"""
Dependency resolution and management for synthetic sensors.

This module provides dependency tracking and circular dependency detection.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant


class DependencyResolver:
    """Tracks dependencies between synthetic sensors and provides update ordering."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the dependency resolver."""
        self._hass = hass
        self._dependencies: dict[str, set[str]] = {}  # sensor_name -> set of entity_ids
        self._dependents: dict[str, set[str]] = {}  # entity_id -> set of sensor_names that depend on it

    def add_sensor_dependencies(self, sensor_name: str, dependencies: set[str]) -> None:
        """Add dependencies for a sensor."""
        self._dependencies[sensor_name] = dependencies.copy()

        # Update reverse mapping
        for entity_id in dependencies:
            if entity_id not in self._dependents:
                self._dependents[entity_id] = set()
            self._dependents[entity_id].add(sensor_name)

    def get_dependencies(self, sensor_name: str) -> set[str]:
        """Get dependencies for a sensor."""
        return self._dependencies.get(sensor_name, set()).copy()

    def get_dependent_sensors(self, entity_id: str) -> set[str]:
        """Get sensors that depend on an entity."""
        return self._dependents.get(entity_id, set()).copy()

    def get_update_order(self, sensor_names: set[str]) -> list[str]:
        """Get the order in which sensors should be updated to respect dependencies."""
        visited = set()
        result = []

        def visit(sensor: str) -> None:
            if sensor in visited:
                return
            visited.add(sensor)

            # Visit dependencies first (only if they're also synthetic sensors)
            for dep in self._dependencies.get(sensor, set()):
                if dep in sensor_names:  # Only consider synthetic sensor dependencies
                    visit(dep)

            result.append(sensor)

        for sensor in sensor_names:
            visit(sensor)

        return result

    def detect_circular_dependencies(self) -> list[list[str]]:
        """Detect circular dependencies between synthetic sensors."""
        cycles = []
        visited = set()

        def dfs(sensor: str, path: list[str], in_path: set[str]) -> None:
            if sensor in in_path:
                # Found a cycle
                cycle_start = path.index(sensor)
                cycle = path[cycle_start:]
                # Normalize cycle to avoid duplicates (start with lexicographically smallest)
                min_idx = cycle.index(min(cycle))
                normalized_cycle = cycle[min_idx:] + cycle[:min_idx]
                if normalized_cycle not in cycles:
                    cycles.append(normalized_cycle)
                return

            if sensor in visited:
                return

            visited.add(sensor)
            path.append(sensor)
            in_path.add(sensor)

            # Only check synthetic sensor dependencies
            for dep in self._dependencies.get(sensor, set()):
                if dep in self._dependencies:  # Only synthetic sensors
                    dfs(dep, path.copy(), in_path.copy())

            in_path.remove(sensor)

        for sensor in self._dependencies:
            if sensor not in visited:
                dfs(sensor, [], set())

        return cycles

    def clear_dependencies(self, sensor_name: str) -> None:
        """Clear dependencies for a sensor."""
        if sensor_name in self._dependencies:
            # Remove from reverse mapping
            for entity_id in self._dependencies[sensor_name]:
                if entity_id in self._dependents:
                    self._dependents[entity_id].discard(sensor_name)
                    if not self._dependents[entity_id]:
                        del self._dependents[entity_id]

            del self._dependencies[sensor_name]
