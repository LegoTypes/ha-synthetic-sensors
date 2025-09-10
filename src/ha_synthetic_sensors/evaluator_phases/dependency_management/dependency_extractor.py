"""Dependency extractor for extracting dependencies from formulas."""

import logging
from typing import TYPE_CHECKING, Any

from ...config_models import ComputedVariable, FormulaConfig
from ...formula_ast_analysis_service import FormulaASTAnalysisService
from .base_manager import DependencyManager

if TYPE_CHECKING:
    from ...hierarchical_context_dict import HierarchicalContextDict


_LOGGER = logging.getLogger(__name__)


class DependencyExtractor(DependencyManager):
    """Extractor for dependencies from formulas."""

    _hass: Any = None
    _ast_service: FormulaASTAnalysisService | None = None

    @property
    def hass(self) -> Any:
        """Get the Home Assistant instance."""
        return self._hass

    @hass.setter
    def hass(self, value: Any) -> None:
        """Set the Home Assistant instance."""
        self._hass = value

    def set_ast_service(self, ast_service: FormulaASTAnalysisService) -> None:
        """Set the AST analysis service for parse-once optimization."""
        self._ast_service = ast_service

    def can_manage(self, manager_type: str, context: "HierarchicalContextDict") -> bool:
        """Determine if this manager can handle dependency extraction."""
        return manager_type == "extract"

    def manage(self, manager_type: str, context: "HierarchicalContextDict", **kwargs: Any) -> set[str]:
        """Extract dependencies from a formula configuration."""
        if manager_type != "extract":
            return set()

        # Get data from kwargs instead of context for dependency management
        config = kwargs.get("config")
        if not config or not isinstance(config, FormulaConfig):
            return set()

        # Extract dependencies from the formula using our fixed parser
        dependencies = self._extract_dependencies_from_formula(config.formula)

        # Add dependencies from config variables
        # IMPORTANT: Do NOT add variable dependencies to formulas that are just "state"
        # The "state" token is a special resolver that should not inherit dependencies
        # from ComputedVariable formulas in the variables section
        if config.variables and config.formula != "state":
            var_deps = self._collect_deps_from_variables(config.variables)
            dependencies.update(var_deps)
        elif config.formula == "state" and config.variables:
            # Log for debugging but don't add dependencies
            var_deps = self._collect_deps_from_variables(config.variables)
            if var_deps:
                _LOGGER.debug(
                    "Ignoring variable dependencies for 'state' formula: %s from variables: %s",
                    var_deps,
                    list(config.variables.keys()),
                )

        # NOTE: Do NOT include dependencies from attribute formulas here!
        # Attributes should be evaluated separately after the main formula.
        # Including attribute dependencies breaks the evaluation sequencing.

        _LOGGER.debug("Dependency extractor: extracted dependencies for '%s': %s", config.name or config.id, dependencies)
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
        """Extract entity dependencies from a formula string using AST analysis."""
        # Use AST service if available for parse-once optimization
        if self._ast_service:
            dependencies = self._ast_service.extract_dependencies(formula)
            _LOGGER.debug("Dependency extractor (AST): extracted from formula '%s': %s", formula, dependencies)
            return dependencies

        # Initialize AST service if not already done
        if not self._ast_service:
            self._ast_service = FormulaASTAnalysisService()

        dependencies = self._ast_service.extract_dependencies(formula)
        _LOGGER.debug("Dependency extractor (AST): extracted from formula '%s': %s", formula, dependencies)
        return dependencies
