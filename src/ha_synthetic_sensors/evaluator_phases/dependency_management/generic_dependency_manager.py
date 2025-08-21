"""Generic dependency manager for all formula types in the synthetic sensor system."""

from enum import Enum
import logging
import re
from typing import Any

from ...config_models import FormulaConfig, SensorConfig
from ...constants_evaluation_results import RESULT_KEY_SUCCESS, RESULT_KEY_VALUE
from ...exceptions import CircularDependencyError, FormulaEvaluationError
from ...reference_value_manager import ReferenceValueManager
from ...shared_constants import get_reserved_words
from ...type_definitions import ReferenceValue

_LOGGER = logging.getLogger(__name__)


class DependencyType(Enum):
    """Types of dependencies that can be tracked."""

    ATTRIBUTE = "attribute"  # Attribute-to-attribute references
    ENTITY = "entity"  # Entity references (sensor.temperature)
    CROSS_SENSOR = "cross_sensor"  # Cross-sensor references (other_sensor)
    VARIABLE = "variable"  # Config variables
    STATE = "state"  # State token references
    COLLECTION = "collection"  # Collection functions


class DependencyNode:
    """Represents a node in the dependency graph."""

    def __init__(self, node_id: str, formula: str, node_type: str = "formula") -> None:
        """Initialize a dependency node."""
        self.node_id = node_id
        self.formula = formula
        self.node_type = node_type  # "main", "attribute", "cross_sensor"
        self.dependencies: set[tuple[str, DependencyType]] = set()
        self.dependents: set[str] = set()


class GenericDependencyManager:
    """
    Universal dependency manager for all formula types.

    This class implements comprehensive dependency analysis and topological sorting
    for all types of formulas in the synthetic sensor system, following compiler
    design principles for dependency resolution.
    """

    def __init__(self) -> None:
        """Initialize the generic dependency manager."""
        self._dependency_graph: dict[str, DependencyNode] = {}
        self._evaluation_order: list[str] = []
        self._sensor_registry_phase = None

    def set_sensor_registry_phase(self, sensor_registry_phase: Any) -> None:
        """Set the sensor registry phase for cross-sensor dependency resolution."""
        self._sensor_registry_phase = sensor_registry_phase

    def analyze_all_dependencies(self, sensor_config: SensorConfig) -> dict[str, DependencyNode]:
        """
        Analyze all dependencies in a sensor configuration.

        This method performs comprehensive dependency analysis for:
        1. Main sensor formula dependencies
        2. Attribute-to-attribute dependencies
        3. Cross-sensor dependencies
        4. Entity dependencies
        5. Variable dependencies

        Args:
            sensor_config: The sensor configuration containing all formulas

        Returns:
            Dictionary mapping node IDs to their dependency information

        Raises:
            CircularDependencyError: If circular dependencies are detected
        """
        self._dependency_graph = {}

        # Analyze main formula dependencies
        if sensor_config.formulas:
            main_formula = sensor_config.formulas[0]
            main_node_id = f"{sensor_config.unique_id}_main"
            main_node = DependencyNode(main_node_id, main_formula.formula, "main")
            main_node.dependencies = self._extract_all_dependencies(main_formula.formula)
            self._dependency_graph[main_node_id] = main_node

            _LOGGER.debug("Main formula '%s' depends on: %s", main_node_id, main_node.dependencies)

        # Analyze attribute formula dependencies
        attribute_formulas = sensor_config.formulas[1:] if len(sensor_config.formulas) > 1 else []
        for formula in attribute_formulas:
            attr_name = self._extract_attribute_name(formula, sensor_config.unique_id)
            attr_node_id = f"{sensor_config.unique_id}_{attr_name}"
            attr_node = DependencyNode(attr_node_id, formula.formula, "attribute")
            attr_node.dependencies = self._extract_all_dependencies(formula.formula)
            self._dependency_graph[attr_node_id] = attr_node

            _LOGGER.debug("Attribute '%s' depends on: %s", attr_name, attr_node.dependencies)

        # Build reverse dependency graph (dependents)
        self._build_dependent_relationships()

        # Check for circular dependencies
        self._check_circular_dependencies()

        return self._dependency_graph.copy()

    def get_evaluation_order(self, sensor_config: SensorConfig) -> list[str]:
        """
        Get the correct evaluation order for all formulas using topological sort.

        This ensures that dependencies are evaluated before dependents,
        following proper compiler dependency resolution order.

        Args:
            sensor_config: The sensor configuration containing all formulas

        Returns:
            List of node IDs in evaluation order

        Raises:
            CircularDependencyError: If circular dependencies are detected
        """
        # Analyze dependencies first
        self.analyze_all_dependencies(sensor_config)

        # Perform topological sort
        self._evaluation_order = self._topological_sort()

        _LOGGER.debug("Formula evaluation order: %s", self._evaluation_order)

        return self._evaluation_order.copy()

    def build_evaluation_context(
        self, sensor_config: SensorConfig, evaluator: Any, base_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Build evaluation context by evaluating formulas in dependency order.

        This is the core method that implements proper context building,
        similar to stack frame management in compilers, but generic for all formula types.

        Args:
            sensor_config: The sensor configuration
            evaluator: The evaluator instance for formula evaluation
            base_context: Base context to start with

        Returns:
            Complete context with all formula values calculated
        """
        # Start with base context
        context = base_context.copy() if base_context else {}

        # Get evaluation order
        evaluation_order = self.get_evaluation_order(sensor_config)

        # Create formula lookup
        formula_lookup = {}

        # Add main formula
        if sensor_config.formulas:
            main_formula = sensor_config.formulas[0]
            main_node_id = f"{sensor_config.unique_id}_main"
            formula_lookup[main_node_id] = main_formula

        # Add attribute formulas
        for formula in sensor_config.formulas[1:]:
            attr_name = self._extract_attribute_name(formula, sensor_config.unique_id)
            attr_node_id = f"{sensor_config.unique_id}_{attr_name}"
            formula_lookup[attr_node_id] = formula

        # Evaluate formulas in dependency order, building context as we go
        main_sensor_value = None

        for node_id in evaluation_order:
            if node_id in formula_lookup:
                formula = formula_lookup[node_id]
                node = self._dependency_graph[node_id]

                _LOGGER.debug("Evaluating %s '%s' with context: %s", node.node_type, node_id, list(context.keys()))

                # Evaluate the formula with current context
                if node.node_type == "main":
                    # Main sensor evaluation - use direct evaluation to avoid recursion
                    eval_result = self._evaluate_formula_directly(formula, context, evaluator, sensor_config)
                    # Accept successful result even when the value is None (state reflection)
                    if eval_result and eval_result.get(RESULT_KEY_SUCCESS):
                        main_sensor_value = eval_result.get(RESULT_KEY_VALUE)
                        # ARCHITECTURE FIX: Use ReferenceValueManager for state token
                        entity_id = sensor_config.entity_id if sensor_config else "state"
                        ReferenceValueManager.set_variable_with_reference_value(context, "state", entity_id, main_sensor_value)
                        _LOGGER.debug("Main sensor value: %s", main_sensor_value)
                    else:
                        raise FormulaEvaluationError(f"Failed to evaluate main sensor for {sensor_config.unique_id}")

                elif node.node_type == "attribute":
                    # Attribute evaluation
                    # Ensure state is in context for attribute formulas
                    if main_sensor_value is not None and "state" not in context:
                        # ARCHITECTURE FIX: Use ReferenceValueManager for state token in attributes
                        entity_id = sensor_config.entity_id if sensor_config else "state"
                        ReferenceValueManager.set_variable_with_reference_value(context, "state", entity_id, main_sensor_value)

                    eval_result = self._evaluate_formula_directly(formula, context, evaluator, sensor_config)
                    if eval_result and eval_result.get(RESULT_KEY_SUCCESS):
                        attr_name = self._extract_attribute_name(formula, sensor_config.unique_id)
                        # Use ReferenceValueManager to preserve reference metadata for attributes
                        ReferenceValueManager.set_variable_with_reference_value(
                            context, attr_name, f"{sensor_config.unique_id}_{attr_name}", eval_result.get(RESULT_KEY_VALUE)
                        )
                        _LOGGER.debug("Added attribute '%s' = %s to context", attr_name, eval_result.get(RESULT_KEY_VALUE))
                    else:
                        raise FormulaEvaluationError(f"Failed to evaluate attribute '{node_id}' for {sensor_config.unique_id}")

        return context

    def _evaluate_formula_directly(
        self, formula: FormulaConfig, context: dict[str, Any], evaluator: Any, sensor_config: SensorConfig
    ) -> Any:
        """
        Evaluate a formula directly using the evaluator's fallback method.

        This bypasses the dependency management to prevent infinite recursion
        when the dependency manager needs to evaluate individual formulas.
        """
        try:
            # Enhance context with cross-sensor registry values for cross-sensor reference resolution
            enhanced_context = context.copy()
            if self._sensor_registry_phase:
                # Add all registered sensor values to the context
                registry_values = self._sensor_registry_phase.get_all_sensor_values()
                for sensor_name, sensor_value in registry_values.items():
                    if sensor_value is not None:
                        # ARCHITECTURE FIX: Wrap sensor values in ReferenceValue objects
                        # This ensures cross-sensor context uses ReferenceValue objects
                        if isinstance(sensor_value, ReferenceValue):
                            enhanced_context[sensor_name] = sensor_value
                        else:
                            # Wrap raw sensor values in ReferenceValue objects
                            _LOGGER.debug(
                                "DEPENDENCY_MANAGER_DEBUG: Setting %s = %s (type: %s)",
                                sensor_name,
                                sensor_value,
                                type(sensor_value).__name__,
                            )
                            ReferenceValueManager.set_variable_with_reference_value(
                                enhanced_context, sensor_name, sensor_name, sensor_value
                            )
                        _LOGGER.debug("Added cross-sensor value '%s' = %s to evaluation context", sensor_name, sensor_value)

            # Use the evaluator's fallback method with enhanced context
            result = evaluator.fallback_to_normal_evaluation(formula, enhanced_context, sensor_config)

            # Diagnostic: log when direct evaluation returns success with None value
            try:
                if result and result.get(RESULT_KEY_SUCCESS) and result.get(RESULT_KEY_VALUE) is None:
                    _LOGGER.debug(
                        "DIRECT_EVAL_DEBUG: direct evaluation for '%s' returned success with None (state=%s)",
                        getattr(formula, "id", formula.formula),
                        result.get("state"),
                    )
            except Exception:
                pass

            # Return the full result dict for caller to inspect success/state/value
            return result

        except Exception as e:
            _LOGGER.error("Direct formula evaluation failed for '%s': %s", formula.formula, e)
            return None

    def _extract_attribute_name(self, formula: FormulaConfig, sensor_unique_id: str) -> str:
        """Extract attribute name from formula ID."""
        if formula.id.startswith(f"{sensor_unique_id}_"):
            return formula.id[len(sensor_unique_id) + 1 :]
        # Fallback: use the full formula ID if it doesn't match expected pattern
        return formula.id

    def _extract_all_dependencies(self, formula: str) -> set[tuple[str, DependencyType]]:
        """
        Extract all types of dependencies from a formula string.

        This method identifies:
        1. Attribute references (level1, hourly_cost, etc.)
        2. Entity references (sensor.temperature, etc.)
        3. Cross-sensor references (other_sensor, etc.)
        4. State references (state, state.voltage, etc.)
        5. Collection functions (sum("device_class:power"), etc.)
        6. Variable references (config variables)
        """
        dependencies = set()

        # Pattern to match all identifiers
        pattern = r"\b([a-zA-Z_][a-zA-Z0-9_.]*)\b"

        # Reserved words that are not dependencies

        for match in re.finditer(pattern, formula):
            identifier = match.group(1)

            # Skip reserved words
            if identifier in get_reserved_words():
                continue

            # Classify the dependency type
            dep_type = self._classify_dependency(identifier, formula)
            if dep_type:
                dependencies.add((identifier, dep_type))

        # Extract collection function dependencies
        collection_deps = self._extract_collection_dependencies(formula)
        dependencies.update(collection_deps)

        return dependencies

    def _classify_dependency(self, identifier: str, formula: str) -> DependencyType | None:
        """Classify what type of dependency an identifier represents."""

        # Entity references (contain dots and start with known prefixes)
        if "." in identifier:
            entity_prefixes = ["sensor", "binary_sensor", "switch", "light", "climate", "input_number", "input_text", "span"]
            if identifier.split(".")[0] in entity_prefixes:
                return DependencyType.ENTITY

        # State references
        if identifier == "state" or identifier.startswith("state."):
            return DependencyType.STATE

        # Cross-sensor references (would need additional context to determine)
        # For now, treat simple identifiers as potential attributes or variables
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier):
            # Could be attribute, variable, or cross-sensor - context dependent
            # Default to attribute for now (this could be enhanced with more context)
            return DependencyType.ATTRIBUTE

        return None

    def _extract_collection_dependencies(self, formula: str) -> set[tuple[str, DependencyType]]:
        """Extract collection function dependencies."""
        dependencies = set()

        # Pattern for collection functions: function_name("pattern")
        collection_pattern = r'\b(sum|avg|max|min|count)\s*\(\s*["\']([^"\']+)["\']\s*\)'

        for match in re.finditer(collection_pattern, formula):
            func_name = match.group(1)
            pattern = match.group(2)
            # Collection functions are their own dependency type
            dependencies.add((f"{func_name}({pattern})", DependencyType.COLLECTION))

        return dependencies

    def _build_dependent_relationships(self) -> None:
        """Build reverse dependency relationships (who depends on whom)."""
        for node_id, node in self._dependency_graph.items():
            for dep_id, dep_type in node.dependencies:
                # Find the node that this dependency refers to
                for target_node_id, target_node in self._dependency_graph.items():
                    if self._dependency_matches_node(dep_id, dep_type, target_node_id, target_node):
                        target_node.dependents.add(node_id)

    def _dependency_matches_node(
        self, dep_id: str, dep_type: DependencyType, target_node_id: str, target_node: DependencyNode
    ) -> bool:
        """Check if a dependency matches a target node."""
        if dep_type == DependencyType.ATTRIBUTE and target_node.node_type == "attribute":
            # For attributes, match the attribute name part
            target_attr_name = target_node_id.split("_")[-1]  # Last part after underscore
            return dep_id == target_attr_name

        # Add more matching logic for other dependency types as needed
        return False

    def _check_circular_dependencies(self) -> None:
        """Check for circular dependencies in the dependency graph."""

        def visit(node_id: str, visited: set[str], rec_stack: set[str], path: list[str]) -> None:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            node = self._dependency_graph.get(node_id)
            if not node:
                return

            for dep_id, dep_type in node.dependencies:
                # Find target nodes for this dependency
                target_nodes = []
                for target_node_id, target_node in self._dependency_graph.items():
                    if self._dependency_matches_node(dep_id, dep_type, target_node_id, target_node):
                        target_nodes.append(target_node_id)

                for target_node_id in target_nodes:
                    if target_node_id not in visited:
                        visit(target_node_id, visited, rec_stack, path)
                    elif target_node_id in rec_stack:
                        # Found circular dependency
                        cycle_start = path.index(target_node_id)
                        cycle = [*path[cycle_start:], target_node_id]
                        raise CircularDependencyError(cycle)

            rec_stack.remove(node_id)
            path.pop()

        visited: set[str] = set()
        for node_id in self._dependency_graph:
            if node_id not in visited:
                visit(node_id, visited, set(), [])

    def _topological_sort(self) -> list[str]:
        """
        Perform topological sort on the dependency graph.

        Returns nodes in evaluation order (dependencies first).
        """
        # Calculate in-degrees (how many dependencies each node has)
        in_degree = dict.fromkeys(self._dependency_graph, 0)

        for node_id, node in self._dependency_graph.items():
            for dep_id, dep_type in node.dependencies:
                # Find target nodes for this dependency
                for target_node_id, target_node in self._dependency_graph.items():
                    if self._dependency_matches_node(dep_id, dep_type, target_node_id, target_node):
                        in_degree[node_id] += 1

        # Initialize queue with nodes that have no dependencies
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            # Process node with no remaining dependencies
            current = queue.pop(0)
            result.append(current)

            # Update in-degrees of dependent nodes
            current_node = self._dependency_graph[current]
            for dependent_id in current_node.dependents:
                if dependent_id in in_degree:
                    in_degree[dependent_id] -= 1
                    if in_degree[dependent_id] == 0:
                        queue.append(dependent_id)

        # Check if all nodes were processed (no cycles)
        if len(result) != len(self._dependency_graph):
            remaining = list(set(self._dependency_graph.keys()) - set(result))
            raise CircularDependencyError(remaining)

        return result
