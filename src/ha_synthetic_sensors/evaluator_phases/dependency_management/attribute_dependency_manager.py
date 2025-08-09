"""Attribute dependency manager for handling attribute-to-attribute dependencies."""

import logging
import re
from typing import Any

from ...config_models import FormulaConfig, SensorConfig
from ...exceptions import CircularDependencyError
from ...reference_value_manager import ReferenceValueManager
from ...shared_constants import get_reserved_words

_LOGGER = logging.getLogger(__name__)


class AttributeDependencyManager:
    """
    Manages attribute dependencies and evaluation order.

    This class implements dependency analysis and topological sorting
    for attribute formulas, ensuring they are evaluated in the correct
    order when attributes reference other attributes.
    """

    def __init__(self) -> None:
        """Initialize the attribute dependency manager."""
        self._dependency_graph: dict[str, set[str]] = {}
        self._evaluation_order: list[str] = []

    def analyze_attribute_dependencies(self, sensor_config: SensorConfig) -> dict[str, set[str]]:
        """
        Analyze attribute dependencies in a sensor configuration.

        Args:
            sensor_config: The sensor configuration containing attribute formulas

        Returns:
            Dictionary mapping attribute names to their dependencies

        Raises:
            CircularDependencyError: If circular dependencies are detected
        """
        self._dependency_graph = {}

        # Get all attribute formulas (skip main formula at index 0)
        attribute_formulas = sensor_config.formulas[1:] if len(sensor_config.formulas) > 1 else []

        # Build dependency graph
        for formula in attribute_formulas:
            attr_name = self._extract_attribute_name(formula, sensor_config.unique_id)
            dependencies = self._extract_attribute_dependencies(formula.formula)
            self._dependency_graph[attr_name] = dependencies

            _LOGGER.debug("Attribute '%s' depends on: %s", attr_name, dependencies)

        # Check for circular dependencies
        self._check_circular_dependencies()

        return self._dependency_graph.copy()

    def get_evaluation_order(self, sensor_config: SensorConfig) -> list[str]:
        """
        Get the correct evaluation order for attributes using topological sort.

        Args:
            sensor_config: The sensor configuration containing attribute formulas

        Returns:
            List of attribute names in evaluation order

        Raises:
            CircularDependencyError: If circular dependencies are detected
        """
        # Analyze dependencies first
        self.analyze_attribute_dependencies(sensor_config)

        # Perform topological sort
        self._evaluation_order = self._topological_sort()

        _LOGGER.debug("Attribute evaluation order: %s", self._evaluation_order)

        return self._evaluation_order.copy()

    def build_evaluation_context(
        self, sensor_config: SensorConfig, main_sensor_value: Any, evaluator: Any, base_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Build evaluation context by evaluating attributes in dependency order.

        This is the core method that implements proper context building,
        similar to stack frame management in compilers.

        Args:
            sensor_config: The sensor configuration
            main_sensor_value: The main sensor's calculated value
            evaluator: The evaluator instance for formula evaluation
            base_context: Base context to start with

        Returns:
            Complete context with all attribute values calculated
        """
        # Start with base context
        context = base_context.copy() if base_context else {}
        # ARCHITECTURE FIX: Use ReferenceValueManager for state token
        entity_id = sensor_config.entity_id if sensor_config else "state"
        ReferenceValueManager.set_variable_with_reference_value(context, "state", entity_id, main_sensor_value)

        # Get evaluation order
        evaluation_order = self.get_evaluation_order(sensor_config)

        # Create attribute formula lookup
        attribute_formulas = {}
        for formula in sensor_config.formulas[1:]:  # Skip main formula
            attr_name = self._extract_attribute_name(formula, sensor_config.unique_id)
            attribute_formulas[attr_name] = formula

        # Evaluate attributes in dependency order, building context as we go
        for attr_name in evaluation_order:
            if attr_name in attribute_formulas:
                formula = attribute_formulas[attr_name]

                _LOGGER.debug("Evaluating attribute '%s' with context: %s", attr_name, list(context.keys()))

                # Evaluate the attribute formula with current context
                result = evaluator.evaluate_formula_with_sensor_config(formula, context, sensor_config)

                if result["success"] and result["value"] is not None:
                    # Add calculated value to context for subsequent attributes
                    context[attr_name] = result["value"]
                    _LOGGER.debug("Added attribute '%s' = %s to context", attr_name, result["value"])
                else:
                    _LOGGER.warning("Failed to evaluate attribute '%s': %s", attr_name, result)
                    # Don't add failed attributes to context

        return context

    def _extract_attribute_name(self, formula: FormulaConfig, sensor_unique_id: str) -> str:
        """Extract attribute name from formula ID."""
        if formula.id.startswith(f"{sensor_unique_id}_"):
            return formula.id[len(sensor_unique_id) + 1 :]
        # Fallback: use the full formula ID if it doesn't match expected pattern
        return formula.id

    def _extract_attribute_dependencies(self, formula: str) -> set[str]:
        """
        Extract attribute dependencies from a formula string.

        This method identifies attribute names that appear as standalone
        variables in the formula (not as part of other identifiers).
        """
        dependencies = set()

        # Pattern to match standalone attribute names (not part of other identifiers)
        pattern = r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b"

        # Reserved words that are not attribute dependencies

        for match in re.finditer(pattern, formula):
            identifier = match.group(1)

            # Skip reserved words
            if identifier in get_reserved_words():
                continue

            # Skip if it looks like an entity ID (contains dot)
            if "." in identifier:
                continue

            # This is likely an attribute dependency
            dependencies.add(identifier)

        return dependencies

    def _check_circular_dependencies(self) -> None:
        """Check for circular dependencies in the dependency graph."""

        def visit(node: str, visited: set[str], rec_stack: set[str], path: list[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for dependency in self._dependency_graph.get(node, set()):
                if dependency not in self._dependency_graph:
                    # Dependency doesn't exist as an attribute, skip
                    continue

                if dependency not in visited:
                    visit(dependency, visited, rec_stack, path)
                elif dependency in rec_stack:
                    # Found circular dependency
                    cycle_start = path.index(dependency)
                    cycle = [*path[cycle_start:], dependency]
                    raise CircularDependencyError(cycle)

            rec_stack.remove(node)
            path.pop()

        visited: set[str] = set()
        for node in self._dependency_graph:
            if node not in visited:
                visit(node, visited, set(), [])

    def _topological_sort(self) -> list[str]:
        """
        Perform topological sort on the dependency graph.

        Returns attributes in evaluation order (dependencies first).
        """
        # Calculate in-degrees
        in_degree = dict.fromkeys(self._dependency_graph, 0)

        for dependencies in self._dependency_graph.values():
            for dependency in dependencies:
                if dependency in in_degree:  # Only count dependencies that are actual attributes
                    in_degree[dependency] += 1

        # Initialize queue with nodes that have no dependencies
        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            # Remove node with no dependencies
            current = queue.pop(0)
            result.append(current)

            # Update in-degrees of dependent nodes
            for node, dependencies in self._dependency_graph.items():
                if current in dependencies:
                    in_degree[node] -= 1
                    if in_degree[node] == 0:
                        queue.append(node)

        # Check if all nodes were processed (no cycles)
        if len(result) != len(self._dependency_graph):
            remaining = list(set(self._dependency_graph.keys()) - set(result))
            raise CircularDependencyError(remaining)

        return result
