"""Circular reference detector for detecting circular dependencies."""

import logging
from typing import Any

from ...exceptions import CircularDependencyError
from .base_manager import DependencyManager

_LOGGER = logging.getLogger(__name__)


class CircularReferenceDetector(DependencyManager):
    """Detector for circular dependencies."""

    def can_manage(self, manager_type: str, context: dict[str, Any] | None = None) -> bool:
        """Determine if this manager can handle circular reference detection."""
        return manager_type == "circular_detection"

    def manage(self, manager_type: str, context: dict[str, Any] | None = None, **kwargs: Any) -> set[str]:
        """Detect circular references in dependencies."""
        if manager_type != "circular_detection" or context is None:
            return set()

        dependencies = context.get("dependencies", set())
        sensor_name = context.get("sensor_name", "")
        sensor_registry = context.get("sensor_registry", {})

        circular_refs = self._detect_circular_references(dependencies, sensor_name, sensor_registry)

        if circular_refs:
            raise CircularDependencyError(list(circular_refs))

        return circular_refs

    def _detect_circular_references(
        self, dependencies: set[str], sensor_name: str, sensor_registry: dict[str, Any]
    ) -> set[str]:
        """Detect circular references in the dependency graph."""
        circular_refs: set[str] = set()

        # Check for self-references
        if sensor_name in dependencies:
            circular_refs.add(sensor_name)
            _LOGGER.debug("Circular reference detector: found self-reference to '%s'", sensor_name)

        # Check for cross-sensor circular references
        for dep in dependencies:
            if dep in sensor_registry and self._would_create_circle(dep, sensor_name, sensor_registry):
                # This dependency is a registered sensor - check if it references back
                # For now, we'll do a simple check. In a full implementation, we'd traverse the dependency graph
                circular_refs.add(dep)
                _LOGGER.debug("Circular reference detector: found circular reference through '%s'", dep)

        return circular_refs

    def _would_create_circle(self, dep: str, sensor_name: str, sensor_registry: dict[str, Any]) -> bool:
        """Check if adding a dependency would create a circular reference."""
        # This is a simplified implementation
        # In a full implementation, we'd traverse the dependency graph to detect cycles
        # For now, we'll just check for direct self-references
        return dep == sensor_name
