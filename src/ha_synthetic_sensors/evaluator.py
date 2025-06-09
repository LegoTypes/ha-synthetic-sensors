"""Enhanced formula evaluation for YAML-based synthetic sensors."""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Callable, NotRequired, TypedDict, Union

from homeassistant.core import HomeAssistant
from simpleeval import SimpleEval

from .cache import CacheConfig, FormulaCache
from .config_manager import FormulaConfig
from .dependency_parser import DependencyParser
from .math_functions import MathFunctions

_LOGGER = logging.getLogger(__name__)

# Type alias for evaluation context values
ContextValue = Union[str, float, int, bool, Callable[..., Any]]

# Type alias for formula evaluation results
FormulaResult = Union[float, int, str, bool, None]


# TypedDicts for evaluator results
class EvaluationResult(TypedDict):
    """Result of formula evaluation."""

    success: bool
    value: FormulaResult
    error: NotRequired[str]
    cached: NotRequired[bool]


class CacheStats(TypedDict):
    """Cache statistics for monitoring."""

    total_cached_formulas: int
    total_cached_evaluations: int
    valid_cached_evaluations: int
    error_counts: dict[str, int]
    cache_ttl_seconds: float


class DependencyValidation(TypedDict):
    """Result of dependency validation."""

    is_valid: bool
    issues: dict[str, str]
    missing_entities: list[str]
    unavailable_entities: list[str]


class EvaluationContext(TypedDict, total=False):
    """Context for formula evaluation with entity states and functions.

    Using total=False since the actual keys depend on the formula being evaluated.
    """


class FormulaEvaluator(ABC):
    """Abstract base class for formula evaluators."""

    @abstractmethod
    def evaluate_formula(
        self, config: FormulaConfig, context: dict[str, ContextValue] | None = None
    ) -> EvaluationResult:
        """Evaluate a formula configuration."""

    @abstractmethod
    def get_formula_dependencies(self, formula: str) -> set[str]:
        """Get dependencies for a formula."""

    @abstractmethod
    def validate_formula_syntax(self, formula: str) -> list[str]:
        """Validate formula syntax."""


class Evaluator(FormulaEvaluator):
    """Enhanced formula evaluator with dependency tracking and optimized caching."""

    def __init__(self, hass: HomeAssistant, cache_config: CacheConfig | None = None):
        """Initialize the enhanced formula evaluator.

        Args:
            hass: Home Assistant instance
            cache_config: Optional cache configuration

        """
        self._hass = hass

        # Initialize optimized components
        self._cache = FormulaCache(cache_config)
        self._dependency_parser = DependencyParser()
        self._math_functions = MathFunctions.get_builtin_functions()

        # Error tracking for circuit breaker pattern
        self._error_count: dict[str, int] = {}
        self._max_errors = 5

    def evaluate_formula(
        self, config: FormulaConfig, context: dict[str, ContextValue] | None = None
    ) -> EvaluationResult:
        """Evaluate a formula configuration with enhanced error handling."""
        # Use either name or id as formula identifier
        formula_name = config.name or config.id

        try:
            # Check if we should skip due to too many errors
            if self._should_skip_evaluation(formula_name):
                return {
                    "success": False,
                    "error": (
                        f"Skipping formula '{formula_name}' due to repeated errors"
                    ),
                    "value": None,
                }

            # Check cache first
            filtered_context = self._filter_context_for_cache(context)
            cached_result = self._cache.get_result(
                config.formula, filtered_context, formula_name
            )
            if cached_result is not None:
                return {"success": True, "value": cached_result, "cached": True}

            # Extract dependencies using optimized parser
            dependencies = self.get_formula_dependencies(config.formula)

            # Validate dependencies are available
            missing_deps = self._check_dependencies(dependencies, context)
            if missing_deps:
                return {
                    "success": False,
                    "error": f"Missing dependencies: {missing_deps}",
                    "value": None,
                }

            # Build evaluation context
            eval_context = self._build_evaluation_context(dependencies, context)

            # Create evaluator with mathematical functions
            evaluator = SimpleEval()
            evaluator.names = eval_context
            evaluator.functions = self._math_functions.copy()

            # Evaluate the formula
            result = evaluator.eval(config.formula)

            # Cache the result
            self._cache.store_result(
                config.formula, result, filtered_context, formula_name
            )

            # Reset error count on success
            self._error_count.pop(formula_name, None)

            return {"success": True, "value": result, "cached": False}

        except Exception as err:
            self._increment_error_count(formula_name)
            return {
                "success": False,
                "error": f"Formula evaluation failed for '{formula_name}': {err}",
                "value": None,
            }

    def _check_dependencies(
        self, dependencies: set[str], context: dict[str, ContextValue] | None = None
    ) -> set[str]:
        """Check which dependencies are missing or unavailable.

        Args:
            dependencies: Set of dependency names to check
            context: Optional context dictionary with variable values

        Returns:
            Set of missing dependency names
        """
        missing = set()
        context = context or {}
        for entity_id in dependencies:
            # First check if provided in context
            if entity_id in context:
                continue
            # Then check if it's a Home Assistant entity
            state = self._hass.states.get(entity_id)
            if state is None:
                missing.add(entity_id)
        return missing

    def get_formula_dependencies(self, formula: str) -> set[str]:
        """Extract and return all entity dependencies from a formula."""
        # Check cache first
        cached_deps = self._cache.get_dependencies(formula)
        if cached_deps is not None:
            return cached_deps

        # Use optimized dependency parser
        dependencies = self._dependency_parser.extract_dependencies(formula)

        # Cache the result
        self._cache.store_dependencies(formula, dependencies)
        return dependencies

    def validate_formula_syntax(self, formula: str) -> list[str]:
        """Validate formula syntax and return list of errors."""
        errors = []

        try:
            # Basic syntax validation using simpleeval
            evaluator = SimpleEval()

            # Add dummy functions for validation
            evaluator.functions.update(
                {
                    "entity": lambda x: 0,
                    "state": lambda x: 0,
                    "float": float,
                    "int": int,
                    "abs": abs,
                    "min": min,
                    "max": max,
                    "round": round,
                    "sum": sum,
                }
            )

            # Try to parse the expression (simpleeval doesn't have compile method)
            evaluator.parse(formula)

        except Exception as err:
            errors.append(f"Syntax error: {err}")

        # Check for common issues
        if (
            "entity(" not in formula
            and "state(" not in formula
            and "states." not in formula
        ):
            errors.append("Formula does not reference any entities")

        # Check for balanced parentheses
        if formula.count("(") != formula.count(")"):
            errors.append("Unbalanced parentheses")

        return errors

    def validate_dependencies(self, dependencies: set[str]) -> DependencyValidation:
        """Validate that all dependencies exist and return any issues."""
        issues = {}
        missing_entities = []
        unavailable_entities = []

        for entity_id in dependencies:
            state = self._hass.states.get(entity_id)
            if state is None:
                issues[entity_id] = "Entity does not exist"
                missing_entities.append(entity_id)
            elif state.state in ("unavailable", "unknown"):
                issues[entity_id] = f"Entity state is {state.state}"
                unavailable_entities.append(entity_id)

        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "missing_entities": missing_entities,
            "unavailable_entities": unavailable_entities,
        }

    def get_evaluation_context(self, formula_config: FormulaConfig) -> dict[str, Any]:
        """Build evaluation context with entity states and helper functions."""
        context = {}

        # Add entity-specific context
        for entity_id in formula_config.dependencies:
            state = self._hass.states.get(entity_id)
            if state:
                # Add direct entity access
                context[f"entity_{entity_id.replace('.', '_')}"] = (
                    self._get_numeric_state(state)
                )

                # Add attribute access
                for attr_name, attr_value in state.attributes.items():
                    safe_attr_name = (
                        f"{entity_id.replace('.', '_')}_{attr_name.replace('.', '_')}"
                    )
                    context[safe_attr_name] = attr_value

        return context

    def clear_cache(self, formula_name: str | None = None) -> None:
        """Clear evaluation cache for specific formula or all formulas."""
        if formula_name:
            # For specific formula, we could implement formula-specific clearing
            # For now, clear all as a simple implementation
            self._cache.clear_all()
        else:
            self._cache.clear_all()

    def get_cache_stats(self) -> CacheStats:
        """Get cache statistics for monitoring."""
        stats = self._cache.get_statistics()
        return {
            "total_cached_formulas": stats["dependency_entries"],
            "total_cached_evaluations": stats["total_entries"],
            "valid_cached_evaluations": stats["valid_entries"],
            "error_counts": dict(self._error_count),
            "cache_ttl_seconds": stats["ttl_seconds"],
        }

    def _build_evaluation_context(
        self, dependencies: set[str], context: dict[str, ContextValue] | None = None
    ) -> dict[str, Any]:
        """Build context for formula evaluation."""
        eval_context = {}
        context = context or {}
        for var in dependencies:
            if var in context:
                eval_context[var] = context[var]
            else:
                # Try to resolve as Home Assistant entity_id
                state = self._hass.states.get(var)
                if state:
                    try:
                        eval_context[var] = float(state.state)
                    except (ValueError, TypeError):
                        eval_context[var] = 0.0
        # Add common functions
        eval_context.update(
            {
                "abs": abs,
                "min": min,
                "max": max,
                "round": round,
                "sum": sum,
                "float": float,
                "int": int,
            }
        )
        return eval_context

    def _should_skip_evaluation(self, formula_name: str) -> bool:
        """Check if formula should be skipped due to repeated errors."""
        return self._error_count.get(formula_name, 0) >= self._max_errors

    def _increment_error_count(self, formula_name: str) -> None:
        """Increment error count for a formula."""
        self._error_count[formula_name] = self._error_count.get(formula_name, 0) + 1

    def _get_numeric_state(self, state) -> float:
        """Get numeric value from entity state, with fallback handling."""
        try:
            return float(state.state)
        except (ValueError, TypeError):
            # Try to extract numeric value from common patterns
            if isinstance(state.state, str):
                # Remove common units and try again
                cleaned = re.sub(r"[^\d.-]", "", state.state)
                if cleaned:
                    try:
                        return float(cleaned)
                    except ValueError:
                        pass

            # Return 0 as fallback for non-numeric states
            return 0.0

    def _filter_context_for_cache(
        self, context: dict[str, ContextValue] | None
    ) -> dict[str, str | float | int | bool] | None:
        """Filter context to only include types that can be cached.

        Args:
            context: Original context which may include callables

        Returns:
            Filtered context with only cacheable types
        """
        if context is None:
            return None

        return {
            key: value
            for key, value in context.items()
            if isinstance(value, (str, float, int, bool))
        }


class DependencyResolver:
    """Resolves and tracks dependencies between synthetic sensors."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the dependency resolver.

        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        self._dependency_graph: dict[str, set[str]] = {}
        self._reverse_dependencies: dict[str, set[str]] = {}
        self._logger = _LOGGER.getChild(self.__class__.__name__)

    def add_sensor_dependencies(self, sensor_name: str, dependencies: set[str]) -> None:
        """Add dependencies for a sensor."""
        self._dependency_graph[sensor_name] = dependencies

        # Update reverse dependencies
        for dep in dependencies:
            if dep not in self._reverse_dependencies:
                self._reverse_dependencies[dep] = set()
            self._reverse_dependencies[dep].add(sensor_name)

    def get_dependencies(self, sensor_name: str) -> set[str]:
        """Get direct dependencies for a sensor."""
        return self._dependency_graph.get(sensor_name, set())

    def get_dependent_sensors(self, entity_id: str) -> set[str]:
        """Get all sensors that depend on a given entity."""
        return self._reverse_dependencies.get(entity_id, set())

    def get_update_order(self, sensor_names: set[str]) -> list[str]:
        """Get the order in which sensors should be updated based on dependencies."""
        # Topological sort to handle dependencies
        visited = set()
        temp_visited = set()
        result = []

        def visit(sensor: str):
            if sensor in temp_visited:
                # Circular dependency detected
                return

            if sensor in visited:
                return

            temp_visited.add(sensor)

            # Visit dependencies first (only synthetic sensors)
            deps = self.get_dependencies(sensor)
            for dep in deps:
                if dep in sensor_names:  # Only consider synthetic sensor dependencies
                    visit(dep)

            temp_visited.remove(sensor)
            visited.add(sensor)
            result.append(sensor)

        for sensor in sensor_names:
            if sensor not in visited:
                visit(sensor)

        return result

    def detect_circular_dependencies(self) -> list[list[str]]:
        """Detect circular dependencies in the sensor graph."""
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(sensor: str, path: list[str]):
            if sensor in rec_stack:
                # Found a cycle
                cycle_start = path.index(sensor)
                cycles.append(path[cycle_start:] + [sensor])
                return

            if sensor in visited:
                return

            visited.add(sensor)
            rec_stack.add(sensor)

            deps = self.get_dependencies(sensor)
            for dep in deps:
                if dep in self._dependency_graph:  # Only follow synthetic sensor deps
                    dfs(dep, path + [sensor])

            rec_stack.remove(sensor)

        for sensor in self._dependency_graph:
            if sensor not in visited:
                dfs(sensor, [])

        return cycles

    def clear_dependencies(self, sensor_name: str) -> None:
        """Clear dependencies for a sensor."""
        if sensor_name in self._dependency_graph:
            old_deps = self._dependency_graph[sensor_name]

            # Remove from reverse dependencies
            for dep in old_deps:
                if dep in self._reverse_dependencies:
                    self._reverse_dependencies[dep].discard(sensor_name)
                    if not self._reverse_dependencies[dep]:
                        del self._reverse_dependencies[dep]

            del self._dependency_graph[sensor_name]

    def evaluate(
        self, formula: str, context: dict[str, float | int | str] | None = None
    ) -> float:
        """Evaluate a formula with the given context.

        Args:
            formula: Formula to evaluate
            context: Additional context variables

        Returns:
            float: Evaluation result
        """
        try:
            evaluator = SimpleEval()
            if context:
                evaluator.names.update(context)
            result = evaluator.eval(formula)
            return float(result)
        except Exception as exc:
            self._logger.error("Formula evaluation failed: %s", exc)
            return 0.0

    def extract_variables(self, formula: str) -> set[str]:
        """Extract variable names from a formula.

        Args:
            formula: Formula to analyze

        Returns:
            set: Set of variable names used in formula
        """
        # Simple regex-based extraction - in real implementation would be more
        # sophisticated
        import re

        # Find potential variable names (alphanumeric + underscore, not starting
        # with digit
        variables = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", formula))

        # Remove known built-in functions and operators
        builtins = {"abs", "max", "min", "round", "int", "float", "str", "len", "sum"}
        return variables - builtins
