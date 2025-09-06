"""Circular Reference Validator for formula evaluation.

This validator performs early detection of circular references and self-referencing
attributes before any dependency resolution is attempted. This prevents the system
from attempting to resolve entities that can never exist due to circular dependencies.
"""

import logging
from typing import TYPE_CHECKING

from ha_synthetic_sensors.config_models import SensorConfig
from ha_synthetic_sensors.exceptions import CircularDependencyError

if TYPE_CHECKING:
    from ha_synthetic_sensors.config_models import FormulaConfig

_LOGGER = logging.getLogger(__name__)


class CircularReferenceValidator:
    """Validates formulas for circular references before evaluation."""

    def __init__(self) -> None:
        """Initialize the circular reference validator."""
        # Use centralized identifier pattern from regex helper
        from ...regex_helper import create_identifier_pattern

        self._variable_pattern = create_identifier_pattern()

    def validate_formula_config(self, config: "FormulaConfig", sensor_config: SensorConfig | None = None) -> None:
        """Validate a formula configuration for circular references.

        Args:
            config: Formula configuration to validate
            sensor_config: Optional sensor configuration for attribute validation

        Raises:
            CircularDependencyError: If a circular reference is detected
        """
        _LOGGER.debug(
            "Validating formula config: %s with sensor config: %s",
            config.name,
            sensor_config.unique_id if sensor_config else None,
        )
        _LOGGER.debug("Formula content: %s", config.formula)

        # Check if this individual formula is a self-reference (for attribute formulas)
        if config.name:
            # Extract attribute name from composite formula name (e.g., "sensor_name - attr_name" -> "attr_name")
            attribute_name = self._extract_attribute_name(config.name)
            if attribute_name and self._formula_references_itself(config.formula, attribute_name):
                _LOGGER.debug("Detected self-reference in attribute '%s': %s", attribute_name, config.formula)
                raise CircularDependencyError([attribute_name, attribute_name])

        # Check all attribute formulas in sensor config for self-references
        if sensor_config and sensor_config.formulas:
            self._validate_sensor_formulas(sensor_config)

    def _validate_sensor_formulas(self, sensor_config: SensorConfig) -> None:
        """Validate all formulas in a sensor configuration for circular references.

        Args:
            sensor_config: Sensor configuration to validate

        Raises:
            CircularDependencyError: If a circular reference is detected
        """
        if not sensor_config.formulas:
            return

        # Build attribute formula map (skip the first formula which is the main sensor formula)
        attribute_formulas: dict[str, str] = {}
        for formula_config in sensor_config.formulas[1:]:  # Skip main formula
            if formula_config.name:
                attribute_formulas[formula_config.name] = formula_config.formula

        if not attribute_formulas:
            return

        # Check each attribute for self-reference
        for attr_name, attr_formula in attribute_formulas.items():
            if self._formula_references_itself(attr_formula, attr_name):
                raise CircularDependencyError([attr_name, attr_name])

        # Check for circular dependencies between attributes
        self._detect_attribute_circular_dependencies(attribute_formulas)

    def _extract_attribute_name(self, formula_name: str) -> str | None:
        """Extract attribute name from composite formula name.

        For attribute formulas, the name is typically "sensor_name - attribute_name".
        This method extracts just the attribute name part.

        Args:
            formula_name: The composite formula name

        Returns:
            The attribute name, or None if pattern doesn't match
        """
        if " - " in formula_name:
            # Split on " - " and take the last part as the attribute name
            parts = formula_name.split(" - ")
            if len(parts) >= 2:
                return parts[-1]
        return None

    def _formula_references_itself(self, formula: str, name: str) -> bool:
        """Check if a formula references its own name.

        Args:
            formula: The formula to check
            name: The name to look for in the formula

        Returns:
            True if the formula contains a self-reference
        """
        # Use the fixed dependency parser to extract variables correctly
        # This handles string literals properly and won't extract 'domain' from metadata() calls
        from ...dependency_parser import DependencyParser

        parser = DependencyParser(hass=None)
        variables = parser.extract_variables(formula)

        # Check if the name appears as a standalone variable reference
        # This catches direct references like "device_info" or "my_attribute"
        if name in variables:
            # But we need to be careful about nested attribute references
            # Check if this is actually a nested reference like "state.device_info.manufacturer"
            # In that case, "device_info" is part of a nested path, not a direct reference

            # Look for patterns like "state.name" or "name.something" which would be nested references
            # A direct reference would be just "name" as a standalone variable

            # Pattern to match standalone variable references (not part of nested paths)
            # Use centralized standalone reference pattern from regex helper
            from ...regex_helper import create_standalone_reference_pattern

            standalone_pattern = create_standalone_reference_pattern(name)

            # Check if there are any standalone references to this name
            if standalone_pattern.search(formula):
                return True

        return False

    def _detect_attribute_circular_dependencies(self, attributes: dict[str, str]) -> None:
        """Detect circular dependencies between attributes.

        Args:
            attributes: Dictionary of attribute names to formulas

        Raises:
            CircularDependencyError: If a circular dependency is detected
        """
        # Build dependency graph
        dependencies: dict[str, set[str]] = {}

        for attr_name, attr_formula in attributes.items():
            # Find all attribute references in this formula using fixed dependency parser
            referenced_attrs = set()
            from ...dependency_parser import DependencyParser

            parser = DependencyParser(hass=None)
            variables = parser.extract_variables(attr_formula)

            for var in variables:
                if var in attributes:  # This variable is another attribute
                    referenced_attrs.add(var)

            dependencies[attr_name] = referenced_attrs

        # Detect cycles using DFS
        self._detect_cycles_in_dependency_graph(dependencies)

    def _detect_cycles_in_dependency_graph(self, dependencies: dict[str, set[str]]) -> None:
        """Detect cycles in a dependency graph using DFS.

        Args:
            dependencies: Graph where keys depend on values in their sets

        Raises:
            CircularDependencyError: If a cycle is detected
        """
        # Track visit states: 0=unvisited, 1=visiting, 2=visited
        states = dict.fromkeys(dependencies, 0)
        path: list[str] = []

        def dfs_visit(attr: str) -> None:
            if states[attr] == 1:  # Currently visiting - cycle detected
                cycle_start = path.index(attr)
                cycle = [*path[cycle_start:], attr]
                raise CircularDependencyError(cycle)

            if states[attr] == 2:  # Already fully visited
                return

            states[attr] = 1  # Mark as visiting
            path.append(attr)

            # Visit all dependencies
            for dep in dependencies.get(attr, set()):
                if dep in dependencies:  # Only check attributes, not external references
                    dfs_visit(dep)

            states[attr] = 2  # Mark as fully visited
            path.pop()

        # Check each unvisited attribute
        for attr in dependencies:
            if states[attr] == 0:
                dfs_visit(attr)
