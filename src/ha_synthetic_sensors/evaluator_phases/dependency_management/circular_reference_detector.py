"""Circular reference detector for detecting circular dependencies."""

import logging
from typing import TYPE_CHECKING, Any

from ...exceptions import CircularDependencyError
from .base_manager import DependencyManager

if TYPE_CHECKING:
    from ...hierarchical_context_dict import HierarchicalContextDict


_LOGGER = logging.getLogger(__name__)


class CircularReferenceDetector(DependencyManager):
    """Detector for circular dependencies."""

    def can_manage(self, manager_type: str, context: "HierarchicalContextDict") -> bool:
        """Determine if this manager can handle circular reference detection."""
        return manager_type == "circular_detection"

    def manage(self, manager_type: str, context: "HierarchicalContextDict", **kwargs: Any) -> set[str]:
        """Detect circular references in dependencies."""
        if manager_type != "circular_detection":
            return set()

        # Get data from context first, then fall back to kwargs for backward compatibility
        dependencies = context.get("dependencies", kwargs.get("dependencies", set()))
        sensor_name = context.get("sensor_name", kwargs.get("sensor_name", ""))
        sensor_registry = context.get("sensor_registry", kwargs.get("sensor_registry", {}))
        sensor_dependencies = context.get("sensor_dependencies", kwargs.get("sensor_dependencies"))

        # If a full graph is provided, detect cycles strictly and raise when present
        if isinstance(sensor_dependencies, dict) and sensor_dependencies:
            cycle_path = self._detect_cycle_with_graph(sensor_dependencies, str(sensor_name))
            if cycle_path:
                raise CircularDependencyError(cycle_path)
            return set()

        # Ensure we have the right types
        deps_set: set[str] = set(dependencies) if isinstance(dependencies, set | list | tuple) else set()
        registry_dict: dict[str, Any] = dict(sensor_registry) if isinstance(sensor_registry, dict) else {}
        circular_refs = self._detect_circular_references(deps_set, str(sensor_name), registry_dict)

        if circular_refs:
            raise CircularDependencyError(list(circular_refs))

        return circular_refs

    def _detect_circular_references(
        self, dependencies: set[str], sensor_name: str, sensor_registry: dict[str, Any]
    ) -> set[str]:
        """Detect circular references in the dependency graph."""
        circular_refs: set[str] = set()

        # Attribute formulas can reference 'state' of the main sensor; this is evaluated first
        # and is not a recursive dependency. Explicitly ignore 'state'.
        if "state" in dependencies:
            dependencies = dependencies - {"state"}

        # Check for self-references
        if sensor_name in dependencies:
            circular_refs.add(sensor_name)
            _LOGGER.debug("Circular reference detector: found self-reference to '%s'", sensor_name)

        # Cross-sensor circular references are not considered fatal; do not flag them here.
        for dep in dependencies:
            # Without a global graph, we cannot reliably detect indirect cycles here.
            # Leave this as a no-op beyond self-reference to avoid false positives.
            # Cross-sensor cycles should be detected via 'sensor_dependencies' graph path.
            _ = dep  # preserve variable for readability, no action

        return circular_refs

    def _detect_cycle_with_graph(self, graph: dict[str, set[str]], sensor_name: str) -> list[str]:
        """Detect a cycle using a dependency graph. If sensor_name is provided, prefer cycles involving it.

        Returns a list representing the cycle path (e.g., [A, B, C, A]) or an empty list if no cycle.
        """

        def find_cycle_from(start: str) -> list[str]:
            visited: set[str] = set()
            stack: list[str] = []
            in_stack: set[str] = set()

            def dfs(node: str) -> list[str]:
                visited.add(node)
                stack.append(node)
                in_stack.add(node)

                for neighbor in graph.get(node, set()):
                    if neighbor not in visited:
                        cycle_path = dfs(neighbor)
                        if cycle_path:
                            return cycle_path
                    elif neighbor in in_stack:
                        # Found a cycle; slice stack from first occurrence of neighbor and append neighbor to close the loop
                        try:
                            idx = stack.index(neighbor)
                            return [*stack[idx:], neighbor]
                        except ValueError:
                            # Should not happen, but return a minimal cycle
                            return [neighbor, node, neighbor]

                stack.pop()
                in_stack.remove(node)
                return []

            return dfs(start)

        # Prefer checking cycles starting from sensor_name if provided
        if sensor_name and sensor_name in graph:
            cycle = find_cycle_from(sensor_name)
            if cycle:
                _LOGGER.debug("Circular reference detector: cycle involving '%s': %s", sensor_name, cycle)
                return cycle

        # Otherwise, check for any cycle in the graph
        seen: set[str] = set()
        for node in graph:
            if node in seen:
                continue
            cycle = find_cycle_from(node)
            seen.add(node)
            if cycle:
                _LOGGER.debug("Circular reference detector: detected cycle: %s", cycle)
                return cycle

        return []
