"""Generic dependency manager for all formula types in the synthetic sensor system."""

from enum import Enum
import logging
from typing import TYPE_CHECKING, Any

from ...config_models import FormulaConfig, SensorConfig
from ...constants_entities import COMMON_ENTITY_DOMAINS
from ...constants_evaluation_results import RESULT_KEY_SUCCESS, RESULT_KEY_VALUE
from ...exceptions import CircularDependencyError, FormulaEvaluationError
from ...formula_ast_analysis_service import FormulaASTAnalysisService
from ...formula_utils import extract_attribute_name, extract_formula_dependencies
from ...reference_value_manager import ReferenceValueManager
from ...regex_helper import (
    create_collection_function_extraction_pattern,
    extract_entity_references_from_metadata,
    find_all_match_objects,
    regex_helper,
)
from ...type_definitions import ReferenceValue

if TYPE_CHECKING:
    from ...hierarchical_context_dict import HierarchicalContextDict


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

    def __init__(self, ast_service: Any = None) -> None:
        """Initialize the generic dependency manager."""
        self._dependency_graph: dict[str, DependencyNode] = {}
        self._evaluation_order: list[str] = []
        self._sensor_registry_phase = None

        self._ast_service = ast_service or FormulaASTAnalysisService()

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

    def _create_formula_lookup(self, sensor_config: SensorConfig) -> dict[str, FormulaConfig]:
        """Create lookup table mapping node IDs to formula configurations."""
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

        return formula_lookup

    def _extract_main_sensor_value(self, context: "HierarchicalContextDict", sensor_config: SensorConfig) -> Any:
        """Extract main sensor value from context."""
        if "state" not in context:
            raise FormulaEvaluationError(f"Main sensor result not found in context for {sensor_config.unique_id}")

        state_ref = context["state"]
        if isinstance(state_ref, ReferenceValue):
            main_sensor_value = state_ref.value
            return main_sensor_value

        # Handle non-ReferenceValue state_ref - should be a simple value
        # Cast to ensure type compatibility
        main_sensor_value = state_ref if isinstance(state_ref, str | int | float | type(None)) else None
        return main_sensor_value

    def _process_attribute_node(
        self,
        node_id: str,
        formula: FormulaConfig,
        context: "HierarchicalContextDict",
        evaluator: Any,
        sensor_config: SensorConfig,
        main_sensor_value: Any,
    ) -> None:
        """Process an attribute node during evaluation."""
        # Ensure state is in context for attribute formulas
        if main_sensor_value is not None and "state" not in context:
            # Use ReferenceValueManager for state token in attributes
            entity_id = sensor_config.entity_id if sensor_config else "state"
            ReferenceValueManager.set_variable_with_reference_value(context, "state", entity_id, main_sensor_value)

        eval_result = self._evaluate_formula_directly(formula, context, evaluator, sensor_config)
        if eval_result and eval_result.get(RESULT_KEY_SUCCESS):
            attr_name = self._extract_attribute_name(formula, sensor_config.unique_id)
            # Use ReferenceValueManager to preserve reference metadata for attributes
            ReferenceValueManager.set_variable_with_reference_value(
                context, attr_name, f"{sensor_config.unique_id}_{attr_name}", eval_result.get(RESULT_KEY_VALUE)
            )
        else:
            raise FormulaEvaluationError(f"Failed to evaluate attribute '{node_id}' for {sensor_config.unique_id}")

    def build_evaluation_context(
        self, sensor_config: SensorConfig, evaluator: Any, base_context: "HierarchicalContextDict"
    ) -> "HierarchicalContextDict":
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
        # Context is now required parameter - no None checks needed
        # Don't copy the context since HierarchicalContextDict is a singleton
        context = base_context

        # Get evaluation order and create formula lookup
        evaluation_order = self.get_evaluation_order(sensor_config)
        formula_lookup = self._create_formula_lookup(sensor_config)

        # Evaluate formulas in dependency order, building context as we go
        main_sensor_value = None

        for node_id in evaluation_order:
            if node_id not in formula_lookup:
                continue

            formula = formula_lookup[node_id]
            node = self._dependency_graph[node_id]

            # Use existing main sensor result from context instead of re-evaluating
            if node.node_type == "main":
                main_sensor_value = self._extract_main_sensor_value(context, sensor_config)
            elif node.node_type == "attribute":
                self._process_attribute_node(node_id, formula, context, evaluator, sensor_config, main_sensor_value)

        return context

    def _evaluate_formula_directly(
        self, formula: FormulaConfig, context: "HierarchicalContextDict", evaluator: Any, sensor_config: SensorConfig
    ) -> Any:
        """
        Evaluate a formula directly using the evaluator's fallback method.

        This bypasses the dependency management to prevent infinite recursion
        when the dependency manager needs to evaluate individual formulas.
        """
        try:
            # Enhance context with cross-sensor registry values for cross-sensor reference resolution
            # Don't copy the context since HierarchicalContextDict is a singleton
            enhanced_context = context
            if self._sensor_registry_phase:
                # Add all registered sensor values to the context
                registry_values = self._sensor_registry_phase.get_all_sensor_values()
                for sensor_name, sensor_value in registry_values.items():
                    if sensor_value is not None:
                        # Wrap sensor values in ReferenceValue objects
                        # This ensures cross-sensor context uses ReferenceValue objects
                        if isinstance(sensor_value, ReferenceValue):
                            enhanced_context[sensor_name] = sensor_value
                        else:
                            # Wrap raw sensor values in ReferenceValue objects
                            ReferenceValueManager.set_variable_with_reference_value(
                                enhanced_context, sensor_name, sensor_name, sensor_value
                            )

            # Use the evaluator's fallback method with enhanced context
            result = evaluator.fallback_to_normal_evaluation(formula, enhanced_context, sensor_config)

            # Return the full result dict for caller to inspect success/state/value
            return result

        except Exception as e:
            _LOGGER.error("Direct formula evaluation failed for '%s': %s", formula.formula, e)
            return None

    def _extract_attribute_name(self, formula: FormulaConfig, sensor_unique_id: str) -> str:
        """Extract attribute name from formula ID."""
        return extract_attribute_name(formula, sensor_unique_id)

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

        # Use centralized dependency extraction utility
        identifiers = extract_formula_dependencies(formula)

        for identifier in identifiers:
            # Classify the dependency type
            dep_type = self._classify_dependency(identifier, formula)
            if dep_type:
                dependencies.add((identifier, dep_type))

        # Extract collection function dependencies
        collection_deps = self._extract_collection_dependencies(formula)
        dependencies.update(collection_deps)

        # Extract entity dependencies from metadata function calls
        metadata_entities = extract_entity_references_from_metadata(formula)
        for entity_id in metadata_entities:
            dependencies.add((entity_id, DependencyType.ENTITY))

        return dependencies

    def extract_cross_sensor_dependencies_with_context(self, formula: str, current_sensor: Any = None) -> set[str]:
        """Extract cross-sensor dependencies from a formula with sensor context.

        This method enhances the standard dependency extraction by resolving
        variables in metadata() calls to cross-sensor dependencies.

        Args:
            formula: The formula to analyze
            current_sensor: The sensor that owns this formula (for variable resolution)

        Returns:
            Set of sensor unique IDs that this formula depends on
        """
        if not current_sensor:
            return set()

        # Use AST service for parse-once optimization
        metadata_calls = self._ast_service.extract_metadata_calls(formula)
        metadata_variables = {entity for entity, _ in metadata_calls}

        cross_sensor_deps = set()
        for variable in metadata_variables:
            sensor_id = self._resolve_variable_to_sensor_id(variable, current_sensor)
            if sensor_id:
                cross_sensor_deps.add(sensor_id)

        return cross_sensor_deps

    def _resolve_variable_to_sensor_id(self, variable: str, current_sensor: Any) -> str | None:
        """Resolve a variable to a sensor unique ID if it maps to a registered sensor.

        Args:
            variable: Variable name to resolve
            current_sensor: The sensor containing the variable definition

        Returns:
            Sensor unique ID if variable maps to a registered sensor, None otherwise
        """
        # Find the variable value in the sensor's formula configurations
        var_value = self._find_variable_value(variable, current_sensor)
        if not var_value:
            return None

        # Check if variable maps to a sensor entity ID
        if not (isinstance(var_value, str) and var_value.startswith("sensor.")):
            return None

        potential_unique_id = var_value[7:]  # Remove "sensor." prefix

        # Verify this corresponds to a registered sensor
        if self._is_registered_sensor(potential_unique_id):
            return potential_unique_id

        return None

    def _find_variable_value(self, variable: str, current_sensor: Any) -> str | None:
        """Find the value of a variable in the sensor's formula configurations."""
        for formula_config in current_sensor.formulas:
            if hasattr(formula_config, "variables") and formula_config.variables and variable in formula_config.variables:
                value = formula_config.variables[variable]
                # Convert to string if it's a numeric literal or ComputedVariable
                if isinstance(value, str):
                    return value
                # For numeric literals and ComputedVariable, convert to string representation
                return str(value)
        return None

    def _is_registered_sensor(self, sensor_unique_id: str) -> bool:
        """Check if a sensor unique ID is registered."""
        if not (hasattr(self, "_sensor_registry_phase") and self._sensor_registry_phase):
            return False
        registered_sensors = self._sensor_registry_phase.get_registered_sensors()
        return sensor_unique_id in registered_sensors

    def _classify_dependency(self, identifier: str, formula: str) -> DependencyType | None:
        """Classify what type of dependency an identifier represents."""

        # Entity references (contain dots and start with known prefixes)
        if "." in identifier:
            entity_prefixes = [
                *COMMON_ENTITY_DOMAINS,
                "input_number",
                "input_text",
                "span",
                "device_tracker",
                "cover",
            ]
            if identifier.split(".")[0] in entity_prefixes:
                return DependencyType.ENTITY

        # State references
        if identifier == "state" or identifier.startswith("state."):
            return DependencyType.STATE

        # Cross-sensor references (would need additional context to determine)
        # For now, treat simple identifiers as potential attributes or variables
        # Use centralized regex helper for validation
        if regex_helper.is_valid_identifier(identifier):
            # Could be attribute, variable, or cross-sensor - context dependent
            # Default to attribute for now (this could be enhanced with more context)
            return DependencyType.ATTRIBUTE

        return None

    def _extract_collection_dependencies(self, formula: str) -> set[tuple[str, DependencyType]]:
        """Extract collection function dependencies."""
        dependencies = set()

        # Pattern for collection functions: function_name("pattern")
        # Use centralized collection function extraction pattern from regex helper
        collection_pattern = create_collection_function_extraction_pattern()

        for match in find_all_match_objects(formula, collection_pattern):
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
