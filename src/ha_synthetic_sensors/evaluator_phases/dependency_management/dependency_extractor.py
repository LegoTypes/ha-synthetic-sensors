"""Dependency extractor for extracting dependencies from formulas."""

import logging
import re
from typing import Any

from ...config_models import ComputedVariable, FormulaConfig
from .base_manager import DependencyManager

_LOGGER = logging.getLogger(__name__)


class DependencyExtractor(DependencyManager):
    """Extractor for dependencies from formulas."""

    def can_manage(self, manager_type: str, context: dict[str, Any] | None = None) -> bool:
        """Determine if this manager can handle dependency extraction."""
        return manager_type == "extract"

    def manage(self, manager_type: str, context: dict[str, Any] | None = None, **kwargs: Any) -> set[str]:
        """Extract dependencies from a formula configuration."""
        if manager_type != "extract" or context is None:
            return set()

        config = context.get("config")
        if not config or not isinstance(config, FormulaConfig):
            return set()

        # Extract dependencies from the formula
        dependencies = self._extract_dependencies_from_formula(config.formula)

        # Add dependencies from config variables
        if config.variables:
            dependencies.update(self._collect_deps_from_variables(config.variables))

        # Add dependencies from attribute formulas and their variables
        if config.attributes:
            dependencies.update(self._collect_deps_from_attributes(config.attributes))

        _LOGGER.debug("Dependency extractor: extracted dependencies: %s", dependencies)
        return dependencies

    def _collect_deps_from_variables(self, variables: dict[str, Any]) -> set[str]:
        """Collect dependencies from a variables mapping."""
        deps: set[str] = set()
        for _var_name, var_value in variables.items():
            if isinstance(var_value, str) and "." in var_value:
                deps.add(var_value)
            elif isinstance(var_value, ComputedVariable):
                deps.update(self._extract_dependencies_from_formula(var_value.formula))
        return deps

    def _collect_deps_from_attributes(self, attributes: dict[str, Any]) -> set[str]:
        """Collect dependencies from attribute definitions (formula and variables)."""
        deps: set[str] = set()
        for _attr_name, attr_value in attributes.items():
            if not isinstance(attr_value, dict):
                continue
            attr_formula = attr_value.get("formula")
            if isinstance(attr_formula, str) and attr_formula:
                deps.update(self._extract_dependencies_from_formula(attr_formula))
            attr_variables = attr_value.get("variables")
            if isinstance(attr_variables, dict) and attr_variables:
                deps.update(self._collect_deps_from_variables(attr_variables))
        return deps

    def _extract_dependencies_from_formula(self, formula: str) -> set[str]:
        """Extract entity dependencies from a formula string."""
        dependencies: set[str] = set()

        # Pattern to match entity references (e.g., sensor.temperature, binary_sensor.motion)
        entity_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z0-9_.]+)\b")

        # Find all entity references in the formula
        for match in entity_pattern.finditer(formula):
            entity_id = match.group(1)
            dependencies.add(entity_id)

        # Pattern to match state token references
        if "state" in formula:
            dependencies.add("state")

        _LOGGER.debug("Dependency extractor: extracted from formula '%s': %s", formula, dependencies)
        return dependencies
