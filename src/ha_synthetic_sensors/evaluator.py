"""Enhanced formula evaluation for YAML-based synthetic sensors."""

from __future__ import annotations

from abc import ABC, abstractmethod
import ast
import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant
from simpleeval import SimpleEval

from .cache import CacheConfig, FormulaCache
from .collection_resolver import CollectionResolver
from .config_models import FormulaConfig
from .dependency_parser import DependencyParser
from .evaluator_cache import EvaluatorCache
from .evaluator_config import CircuitBreakerConfig, RetryConfig
from .evaluator_dependency import EvaluatorDependency
from .exceptions import DataValidationError, is_fatal_error, is_retriable_error
from .math_functions import MathFunctions
from .type_definitions import CacheStats, ContextValue, DataProviderCallback, DependencyValidation, EvaluationResult
from .variable_resolver import (
    ContextResolutionStrategy,
    HomeAssistantResolutionStrategy,
    IntegrationResolutionStrategy,
    VariableResolutionStrategy,
    VariableResolver,
)

_LOGGER = logging.getLogger(__name__)


class FormulaEvaluator(ABC):
    """Abstract base class for formula evaluators."""

    @abstractmethod
    def evaluate_formula(self, config: FormulaConfig, context: dict[str, ContextValue] | None = None) -> EvaluationResult:
        """Evaluate a formula configuration."""

    @abstractmethod
    def get_formula_dependencies(self, formula: str) -> set[str]:
        """Get dependencies for a formula."""

    @abstractmethod
    def validate_formula_syntax(self, formula: str) -> list[str]:
        """Validate formula syntax."""


class Evaluator(FormulaEvaluator):
    """Enhanced formula evaluator with dependency tracking and optimized caching.

    TWO-TIER CIRCUIT BREAKER PATTERN:
    ============================================

    This evaluator implements an error handling system that distinguishes
    between different types of errors and handles them appropriately:

    TIER 1 - FATAL ERROR CIRCUIT BREAKER:
    - Tracks permanent configuration issues (syntax errors, missing entities)
    - Uses traditional circuit breaker pattern with configurable threshold (default: 5)
    - When threshold is reached, evaluation attempts are completely skipped
    - Designed to prevent resource waste on permanently broken formulas

    TIER 2 - TRANSITORY ERROR RESILIENCE:
    - Tracks temporary issues (unavailable entities, network problems)
    - Does NOT trigger circuit breaker - allows continued evaluation attempts
    - Propagates "unknown" state to synthetic sensors
    - Recovers when underlying issues resolve

    STATE PROPAGATION STRATEGY:
    - Missing entities → "unavailable" state (fatal error)
    - Unavailable entities → "unknown" state (transitory error)
    - Successful evaluation → "ok" state (resets all error counters)

    """

    def __init__(
        self,
        hass: HomeAssistant,
        cache_config: CacheConfig | None = None,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        retry_config: RetryConfig | None = None,
        data_provider_callback: DataProviderCallback | None = None,
    ):
        """Initialize the enhanced formula evaluator.

        Args:
            hass: Home Assistant instance
            cache_config: Optional cache configuration
            circuit_breaker_config: Optional circuit breaker configuration
            retry_config: Optional retry configuration for transitory errors
            data_provider_callback: Optional callback for getting data directly from integrations
                                  without requiring actual HA entities. Should return (value, exists)
                                  where exists=True if data is available, False if not found.
        """
        self._hass = hass

        # Initialize components
        self._cache = FormulaCache(cache_config)
        self._dependency_parser = DependencyParser()
        self._collection_resolver = CollectionResolver(hass)
        self._math_functions = MathFunctions.get_builtin_functions()

        # Initialize configuration objects
        self._circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        self._retry_config = retry_config or RetryConfig()

        # Initialize handler modules
        self._dependency_handler = EvaluatorDependency(hass, data_provider_callback)
        self._cache_handler = EvaluatorCache(cache_config)

        # TIER 1: Fatal Error Circuit Breaker (Traditional Pattern)
        # Tracks configuration errors, syntax errors, missing entities, etc.
        self._error_count: dict[str, int] = {}

        # TIER 2: Transitory Error Tracking (Intelligent Resilience)
        # Tracks temporary issues like unknown/unavailable entity states.
        self._transitory_error_count: dict[str, int] = {}

        # Support for push-based entity registration (new pattern)
        self._registered_integration_entities: set[str] | None = None

        # Store data provider callback for backward compatibility
        self._data_provider_callback = data_provider_callback

    @property
    def data_provider_callback(self) -> DataProviderCallback | None:
        """Get the current data provider callback."""
        return self._data_provider_callback

    @property
    def _data_provider_callback(self) -> DataProviderCallback | None:
        """Get the data provider callback for backward compatibility."""
        return getattr(self._dependency_handler, "_data_provider_callback", None)

    @_data_provider_callback.setter
    def _data_provider_callback(self, value: DataProviderCallback | None) -> None:
        """Set the data provider callback for backward compatibility."""
        self._dependency_handler.data_provider_callback = value

    def update_integration_entities(self, entity_ids: set[str]) -> None:
        """Update the set of entities that the integration can provide (new push-based pattern)."""
        self._registered_integration_entities = entity_ids.copy()
        self._dependency_handler.update_integration_entities(entity_ids)
        _LOGGER.debug("Updated integration entities: %d entities", len(entity_ids))

    def get_integration_entities(self) -> set[str]:
        """Get the current set of integration entities using the push-based pattern."""
        return self._dependency_handler.get_integration_entities()

    def evaluate_formula(self, config: FormulaConfig, context: dict[str, ContextValue] | None = None) -> EvaluationResult:
        """Evaluate a formula configuration with enhanced error handling."""
        formula_name = config.name or config.id
        cache_key_id = config.id

        try:
            # Check circuit breaker
            if self._should_skip_evaluation(formula_name):
                return self._create_error_result(f"Skipping formula '{formula_name}' due to repeated errors")

            # Check cache
            cache_result = self._cache_handler.check_cache(config, context, cache_key_id)
            if cache_result:
                return cache_result

            # Extract and validate dependencies
            dependencies, collection_pattern_entities = self._extract_and_prepare_dependencies(config, context)
            missing_deps, unavailable_deps, unknown_deps = self._dependency_handler.check_dependencies(
                dependencies, context, collection_pattern_entities
            )

            # Handle dependency issues
            dependency_result = self._handle_dependency_issues(missing_deps, unavailable_deps, unknown_deps, formula_name)
            if dependency_result:
                return dependency_result

            # Build and validate evaluation context
            eval_context = self._build_evaluation_context(dependencies, context, config)
            context_result = self._validate_evaluation_context(eval_context, formula_name)
            if context_result:
                return context_result

            # Evaluate the formula
            result = self._execute_formula_evaluation(config, eval_context, context, cache_key_id)

            # Handle success
            self._handle_successful_evaluation(formula_name)
            return self._create_success_result(result)

        except DataValidationError:
            raise
        except Exception as err:
            return self._handle_evaluation_error(err, formula_name)

    def _extract_and_prepare_dependencies(
        self, config: FormulaConfig, context: dict[str, ContextValue] | None
    ) -> tuple[set[str], set[str]]:
        """Extract dependencies and prepare collection pattern entities."""
        return self._dependency_handler.extract_and_prepare_dependencies(config, context)

    def _handle_dependency_issues(
        self, missing_deps: set[str], unavailable_deps: set[str], unknown_deps: set[str], formula_name: str
    ) -> EvaluationResult | None:
        """Handle missing, unavailable, and unknown dependencies with state reflection."""
        # Only missing dependencies are truly fatal
        if missing_deps:
            return self._handle_missing_dependencies(missing_deps, formula_name)

        # Handle non-fatal dependencies with state reflection
        # Priority: unavailable > unknown (unavailable is worse)
        if unavailable_deps or unknown_deps:
            all_problematic_deps = list(unavailable_deps) + list(unknown_deps)

            if unavailable_deps:
                # If any dependencies are unavailable, reflect unavailable state
                return self._create_success_result_with_state("unavailable", unavailable_dependencies=all_problematic_deps)

            # Only unknown dependencies
            return self._create_success_result_with_state("unknown", unavailable_dependencies=all_problematic_deps)

        return None

    def _handle_missing_dependencies(self, missing_deps: set[str], formula_name: str) -> EvaluationResult:
        """Handle missing dependencies (fatal error)."""
        error_msg = f"Missing dependencies: {', '.join(sorted(missing_deps))}"
        _LOGGER.warning("Formula '%s': %s", formula_name, error_msg)
        self._increment_error_count(formula_name)
        return self._create_error_result(error_msg, state="unavailable", missing_dependencies=list(missing_deps))

    def _validate_evaluation_context(self, eval_context: dict[str, ContextValue], formula_name: str) -> EvaluationResult | None:
        """Validate that evaluation context has all required variables."""
        try:
            # Check for any None values in the context that would break evaluation
            none_variables = [var for var, value in eval_context.items() if value is None]
            if none_variables:
                error_msg = f"Variables with None values: {', '.join(none_variables)}"
                _LOGGER.warning("Formula '%s': %s", formula_name, error_msg)
                self._increment_error_count(formula_name)
                return self._create_error_result(error_msg, state="unavailable")
            return None
        except Exception as err:
            _LOGGER.error("Formula '%s': Context validation error: %s", formula_name, err)
            self._increment_error_count(formula_name)
            return self._create_error_result(f"Context validation error: {err}", state="unavailable")

    def _execute_formula_evaluation(
        self,
        config: FormulaConfig,
        eval_context: dict[str, ContextValue],
        context: dict[str, ContextValue] | None,
        cache_key_id: str,
    ) -> float:
        """Execute the actual formula evaluation."""
        # Preprocess formula for evaluation
        processed_formula = self._preprocess_formula_for_evaluation(config.formula, eval_context)

        # Create evaluator with math functions and context
        evaluator = SimpleEval(functions=self._math_functions)
        evaluator.names = eval_context

        # Evaluate the formula
        result = evaluator.eval(processed_formula)

        # Validate result
        if not isinstance(result, (int, float)):
            raise ValueError(f"Formula result must be numeric, got {type(result).__name__}: {result}")

        # Cache the result using the cache handler
        self._cache_handler.cache_result(config, context, cache_key_id, float(result))

        return float(result)

    def _handle_successful_evaluation(self, formula_name: str) -> None:
        """Reset error counters on successful evaluation."""
        self._error_count.pop(formula_name, None)
        self._transitory_error_count.pop(formula_name, None)

    def _create_success_result(self, result: float) -> EvaluationResult:
        """Create a successful evaluation result."""
        return {
            "success": True,
            "value": result,
            "state": "ok",
        }

    def _create_success_result_with_state(self, state: str, **kwargs: Any) -> EvaluationResult:
        """Create a successful result with specific state (for dependency state reflection)."""
        result: EvaluationResult = {
            "success": True,
            "value": None,
            "state": state,
        }
        # Add any additional fields from kwargs
        for key, value in kwargs.items():
            if key in ["unavailable_dependencies", "missing_dependencies"]:
                result[key] = value  # type: ignore[literal-required]
        return result

    def _create_error_result(self, error_message: str, state: str = "unavailable", **kwargs: Any) -> EvaluationResult:
        """Create an error evaluation result."""
        result: EvaluationResult = {
            "success": False,
            "error": error_message,
            "value": None,
            "state": state,
        }
        # Add any additional fields from kwargs that are valid for EvaluationResult
        for key, value in kwargs.items():
            if key in ["cached", "unavailable_dependencies", "missing_dependencies"]:
                result[key] = value  # type: ignore[literal-required]
        return result

    def _handle_evaluation_error(self, err: Exception, formula_name: str) -> EvaluationResult:
        """Handle evaluation errors with appropriate error classification."""
        if is_fatal_error(err):
            return self._handle_fatal_error(err, formula_name)
        if is_retriable_error(err):
            return self._handle_retriable_error(err, formula_name)
        return self._handle_unknown_error(err, formula_name)

    def _handle_fatal_error(self, err: Exception, formula_name: str) -> EvaluationResult:
        """Handle fatal errors that should trigger circuit breaker."""
        _LOGGER.error("Formula '%s': Fatal error: %s", formula_name, err)
        self._increment_error_count(formula_name)
        return self._create_error_result(str(err), state="unavailable")

    def _handle_retriable_error(self, err: Exception, formula_name: str) -> EvaluationResult:
        """Handle retriable errors that should not trigger circuit breaker."""
        _LOGGER.debug("Formula '%s': Retriable error: %s", formula_name, err)
        self._increment_transitory_error_count(formula_name)
        return self._create_error_result(str(err), state="unknown")

    def _handle_unknown_error(self, err: Exception, formula_name: str) -> EvaluationResult:
        """Handle unknown errors with conservative approach."""
        _LOGGER.warning(
            "Formula '%s': Unknown error type, treating as fatal: %s (%s)",
            formula_name,
            err,
            type(err).__name__,
        )
        self._increment_error_count(formula_name)
        return self._create_error_result(str(err), state="unavailable")

    # Delegate dependency checking to handler
    def _check_dependencies(
        self,
        dependencies: set[str],
        context: dict[str, ContextValue] | None = None,
        collection_pattern_entities: set[str] | None = None,
    ) -> tuple[set[str], set[str], set[str]]:
        """Check dependencies and return missing, unavailable, and unknown sets."""
        return self._dependency_handler.check_dependencies(dependencies, context, collection_pattern_entities)

    def get_formula_dependencies(self, formula: str) -> set[str]:
        """Get dependencies for a formula."""
        return self._dependency_handler.get_formula_dependencies(formula)

    def _extract_formula_dependencies(self, config: FormulaConfig, context: dict[str, ContextValue] | None = None) -> set[str]:
        """Extract dependencies from formula config, handling entity references in collection patterns."""
        # Use dependency handler for consistent extraction logic
        return self._dependency_handler.extract_formula_dependencies(config, context)

    def validate_formula_syntax(self, formula: str) -> list[str]:
        """Validate formula syntax and return list of errors."""
        errors = []

        try:
            # Basic syntax validation using AST
            ast.parse(formula, mode="eval")
        except SyntaxError as err:
            errors.append(f"Syntax error: {err.msg} at position {err.offset}")
            return errors

        try:
            # Check for valid variable names and function calls
            dependencies = self.get_formula_dependencies(formula)

            # Validate each dependency
            for dep in dependencies:
                if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$", dep):
                    errors.append(f"Invalid variable name: {dep}")

            # Note: We don't require formulas to reference entities - they can use literal values in variables

        except Exception as err:
            errors.append(f"Validation error: {err}")

        return errors

    def validate_dependencies(self, dependencies: set[str]) -> DependencyValidation:
        """Validate dependencies and return validation result."""
        return self._dependency_handler.validate_dependencies(dependencies)

    def get_evaluation_context(self, formula_config: FormulaConfig) -> dict[str, ContextValue]:
        """Get the evaluation context for a formula configuration."""
        dependencies = self._extract_formula_dependencies(formula_config)
        return self._build_evaluation_context(dependencies, None, formula_config)

    # Delegate cache operations to handler
    def clear_cache(self, formula_name: str | None = None) -> None:
        """Clear cache for specific formula or all formulas."""
        self._cache_handler.clear_cache(formula_name)

    def get_cache_stats(self) -> CacheStats:
        """Get cache statistics."""
        cache_stats = self._cache_handler.get_cache_stats()
        # Add error counts from the evaluator's circuit breaker tracking
        cache_stats["error_counts"] = self._error_count.copy()
        return cache_stats

    # Configuration methods
    def get_circuit_breaker_config(self) -> CircuitBreakerConfig:
        """Get current circuit breaker configuration."""
        return self._circuit_breaker_config

    def get_retry_config(self) -> RetryConfig:
        """Get current retry configuration."""
        return self._retry_config

    def update_circuit_breaker_config(self, config: CircuitBreakerConfig) -> None:
        """Update circuit breaker configuration."""
        self._circuit_breaker_config = config
        _LOGGER.debug("Updated circuit breaker config: threshold=%d", config.max_fatal_errors)

    def update_retry_config(self, config: RetryConfig) -> None:
        """Update retry configuration."""
        self._retry_config = config
        _LOGGER.debug("Updated retry config: max_attempts=%d, backoff=%f", config.max_attempts, config.backoff_seconds)

    def _build_evaluation_context(
        self,
        dependencies: set[str],
        context: dict[str, ContextValue] | None = None,
        config: FormulaConfig | None = None,
    ) -> dict[str, ContextValue]:
        """Build evaluation context from dependencies and configuration."""
        eval_context: dict[str, ContextValue] = {}

        # Create variable resolver
        resolver = self._create_variable_resolver(context)

        # Add context variables first (highest priority)
        self._add_context_variables(eval_context, context)

        # Resolve entity dependencies
        self._resolve_entity_dependencies(eval_context, dependencies, resolver)

        # Resolve config variables (can override entity values)
        self._resolve_config_variables(eval_context, config, resolver)

        return eval_context

    def _create_variable_resolver(self, context: dict[str, ContextValue] | None) -> VariableResolver:
        """Create variable resolver with appropriate strategies."""
        strategies: list[VariableResolutionStrategy] = []

        # Context resolution (highest priority)
        if context:
            strategies.append(ContextResolutionStrategy(context))

        # Integration resolution (for data provider callback)
        if self._dependency_handler.data_provider_callback:
            strategies.append(IntegrationResolutionStrategy(self._dependency_handler.data_provider_callback, self))

        # Home Assistant resolution (lowest priority)
        strategies.append(HomeAssistantResolutionStrategy(self._hass))

        return VariableResolver(strategies)

    def _add_context_variables(self, eval_context: dict[str, ContextValue], context: dict[str, ContextValue] | None) -> None:
        """Add context variables to evaluation context."""
        if context:
            for key, value in context.items():
                if not key.startswith("entity_"):  # Skip entity references
                    eval_context[key] = value

    def _resolve_entity_dependencies(
        self, eval_context: dict[str, ContextValue], dependencies: set[str], resolver: VariableResolver
    ) -> None:
        """Resolve entity dependencies using variable resolver."""
        for entity_id in dependencies:
            try:
                value, exists, source = resolver.resolve_variable(entity_id)
                if exists and value is not None:
                    self._add_entity_to_context(eval_context, entity_id, value, source)
                else:
                    _LOGGER.debug("Could not resolve entity: %s", entity_id)
            except Exception as err:
                _LOGGER.warning("Error resolving entity %s: %s", entity_id, err)

    def _add_entity_to_context(
        self, eval_context: dict[str, ContextValue], entity_id: str, value: ContextValue, source: str
    ) -> None:
        """Add entity value to evaluation context with proper variable name."""
        # Convert entity_id to valid variable name
        var_name = entity_id.replace(".", "_").replace("-", "_")
        eval_context[var_name] = value

        # Also add with original entity_id for backward compatibility
        eval_context[entity_id] = value

        _LOGGER.debug("Added %s=%s to context (source: %s)", var_name, value, source)

    def _resolve_config_variables(
        self, eval_context: dict[str, ContextValue], config: FormulaConfig | None, resolver: VariableResolver
    ) -> None:
        """Resolve config variables using variable resolver."""
        if not config:
            return

        for var_name, var_value in config.variables.items():
            # Skip if this variable is already set in context (context has higher priority)
            if var_name in eval_context:
                _LOGGER.debug("Skipping config variable %s (already set in context)", var_name)
                continue

            try:
                if isinstance(var_value, str) and "." in var_value:
                    # Variable references an entity
                    value, exists, source = resolver.resolve_variable(var_name, var_value)
                    if exists and value is not None:
                        eval_context[var_name] = value
                        _LOGGER.debug(
                            "Added config variable %s=%s (entity: %s, source: %s)", var_name, value, var_value, source
                        )
                    else:
                        self._handle_config_variable_none_value(var_name, config)
                else:
                    # Variable has a direct value
                    eval_context[var_name] = var_value
                    _LOGGER.debug("Added config variable %s=%s (direct value)", var_name, var_value)
            except Exception as err:
                _LOGGER.warning("Error resolving config variable %s: %s", var_name, err)

    def _handle_config_variable_none_value(self, var_name: str, config: FormulaConfig) -> None:
        """Handle config variable with None value."""
        _LOGGER.warning("Config variable '%s' in formula '%s' resolved to None", var_name, config.name or config.id)

    def _handle_config_variable_not_found(self, var_name: str, config: FormulaConfig) -> None:
        """Handle config variable that could not be found."""
        _LOGGER.warning("Config variable '%s' in formula '%s' has no entity_id or value", var_name, config.name or config.id)

    def _preprocess_formula_for_evaluation(self, formula: str, eval_context: dict[str, ContextValue] | None = None) -> str:
        """Preprocess formula for evaluation by resolving collection functions and normalizing entity IDs.

        Processing order:
        1. Resolve collection functions (replace with computed values)
        2. Normalize entity IDs for simpleeval compatibility

        Args:
            formula: Original formula string
            eval_context: Evaluation context (optional, not used in basic implementation)

        Returns:
            Formula with collection functions resolved and entity IDs normalized to valid variable names
        """
        processed_formula = formula

        # Step 1: Resolve collection functions
        processed_formula = self._resolve_collection_functions(processed_formula)

        # Step 2: Extract entity references and normalize them
        entity_refs = self._dependency_parser.extract_dependencies(processed_formula)

        # Replace each entity_id with normalized version
        for entity_id in entity_refs:
            if "." in entity_id:
                normalized_name = entity_id.replace(".", "_").replace("-", "_")
                # Use word boundaries to ensure we only replace complete entity_ids
                pattern = r"\b" + re.escape(entity_id) + r"\b"
                processed_formula = re.sub(pattern, normalized_name, processed_formula)

        return processed_formula

    def _resolve_collection_functions(self, formula: str) -> str:
        """Resolve collection functions by replacing them with actual computed values.

        Collection patterns like sum("device_class:power") are resolved fresh on each
        evaluation to actual values: sum(150.5, 225.3, 89.2) becomes the computed result.
        This eliminates cache staleness issues when entities are added/removed and ensures
        dynamic discovery works correctly.

        Args:
            formula: Formula containing collection functions

        Returns:
            Formula with collection functions replaced by computed values
        """
        try:
            # Extract dynamic queries from the formula
            parsed_deps = self._dependency_parser.parse_formula_dependencies(formula, {})

            if not parsed_deps.dynamic_queries:
                return formula  # No collection functions to resolve

            resolved_formula = formula

            for query in parsed_deps.dynamic_queries:
                resolved_formula = self._resolve_single_collection_query(resolved_formula, query)

            return resolved_formula

        except Exception as e:
            _LOGGER.error("Error resolving collection functions in formula '%s': %s", formula, e)
            return formula  # Return original formula if resolution fails

    def _resolve_single_collection_query(self, formula: str, query: Any) -> str:
        """Resolve a single collection query in the formula.

        Args:
            formula: Current formula string
            query: DynamicQuery object to resolve

        Returns:
            Formula with this query resolved
        """
        # Resolve collection to get matching entity IDs
        entity_ids = self._collection_resolver.resolve_collection(query)

        if not entity_ids:
            return self._replace_with_default_value(formula, query, "no entities matched")

        # Get numeric values for the entities
        values = self._collection_resolver.get_entity_values(entity_ids)

        if not values:
            return self._replace_with_default_value(formula, query, "no numeric values found")

        # Calculate the result based on the function
        result = self._calculate_collection_result(query.function, values)

        # Replace the pattern in the formula
        return self._replace_collection_pattern(formula, query, str(result))

    def _replace_with_default_value(self, formula: str, query: Any, reason: str) -> str:
        """Replace collection query with default value when no data is available.

        Args:
            formula: Current formula string
            query: DynamicQuery object
            reason: Reason for using default value (for logging)

        Returns:
            Formula with query replaced by default value
        """
        _LOGGER.warning("Collection query %s:%s %s", query.query_type, query.pattern, reason)
        default_value = "0"  # All functions return 0 for empty collections per README
        return self._replace_collection_pattern(formula, query, default_value)

    def _calculate_collection_result(self, function: str, values: list[float]) -> float | int:
        """Calculate the result for a collection function.

        Args:
            function: Function name (sum, avg, count, etc.)
            values: List of numeric values

        Returns:
            Calculated result
        """
        # Try basic arithmetic functions first
        basic_result = self._try_basic_arithmetic(function, values)
        if basic_result is not None:
            return basic_result

        # Try statistical functions
        statistical_result = self._try_statistical_functions(function, values)
        if statistical_result is not None:
            return statistical_result

        # Unknown function fallback
        _LOGGER.warning("Unknown collection function: %s", function)
        return 0

    def _try_basic_arithmetic(self, function: str, values: list[float]) -> float | int | None:
        """Try to calculate basic arithmetic functions.

        Args:
            function: Function name
            values: List of numeric values

        Returns:
            Calculated result or None if function not handled
        """
        if function == "sum":
            return sum(values)
        if function == "count":
            return len(values)
        if function == "max":
            return max(values) if values else 0
        if function == "min":
            return min(values) if values else 0
        if function in ("avg", "average", "mean"):
            return sum(values) / len(values) if values else 0

        return None

    def _try_statistical_functions(self, function: str, values: list[float]) -> float | None:
        """Try to calculate statistical functions.

        Args:
            function: Function name
            values: List of numeric values

        Returns:
            Calculated result or None if function not handled
        """
        if function in ("std", "var"):
            return self._calculate_statistical_function(function, values)

        return None

    def _calculate_statistical_function(self, function: str, values: list[float]) -> float:
        """Calculate statistical functions (std, var).

        Args:
            function: Statistical function name
            values: List of numeric values

        Returns:
            Calculated statistical result
        """
        if len(values) <= 1:
            return 0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)

        if function == "var":
            return float(variance)
        if function == "std":
            return float(variance**0.5)

        return 0  # Fallback

    def _replace_collection_pattern(self, formula: str, query: Any, replacement: str) -> str:
        """Replace collection pattern in formula with replacement value.

        Args:
            formula: Current formula string
            query: DynamicQuery object
            replacement: Value to replace the pattern with

        Returns:
            Formula with pattern replaced
        """
        # Handle both space formats that users might input in YAML
        pattern_with_space = f'{query.function}("{query.query_type}: {query.pattern}")'
        pattern_without_space = f'{query.function}("{query.query_type}:{query.pattern}")'

        # Replace whichever pattern exists in the formula
        if pattern_with_space in formula:
            return formula.replace(pattern_with_space, replacement)
        if pattern_without_space in formula:
            return formula.replace(pattern_without_space, replacement)

        _LOGGER.warning("Could not find pattern to replace for %s:%s", query.query_type, query.pattern)
        return formula

    def _increment_transitory_error_count(self, formula_name: str) -> None:
        """Increment transitory error count for a formula."""
        current_count = self._transitory_error_count.get(formula_name, 0)
        new_count = current_count + 1
        self._transitory_error_count[formula_name] = new_count

        _LOGGER.debug(
            "Formula '%s': Transitory error count: %d/%d (threshold: %d)",
            formula_name,
            new_count,
            self._retry_config.max_attempts,
            self._retry_config.max_attempts,
        )

        # Log warning if approaching retry limit but don't trigger circuit breaker
        if new_count >= self._retry_config.max_attempts:
            _LOGGER.warning(
                "Formula '%s': Reached transitory error limit (%d), but continuing evaluation attempts",
                formula_name,
                self._retry_config.max_attempts,
            )

    def _should_skip_evaluation(self, formula_name: str) -> bool:
        """Check if evaluation should be skipped due to circuit breaker."""
        error_count = self._error_count.get(formula_name, 0)
        should_skip = error_count >= self._circuit_breaker_config.max_fatal_errors

        if should_skip:
            _LOGGER.debug(
                "Formula '%s': Skipping evaluation due to circuit breaker (errors: %d/%d)",
                formula_name,
                error_count,
                self._circuit_breaker_config.max_fatal_errors,
            )

        return should_skip

    def _increment_error_count(self, formula_name: str) -> None:
        """Increment error count for a formula."""
        current_count = self._error_count.get(formula_name, 0)
        new_count = current_count + 1
        self._error_count[formula_name] = new_count

        _LOGGER.debug(
            "Formula '%s': Error count: %d/%d (threshold: %d)",
            formula_name,
            new_count,
            self._circuit_breaker_config.max_fatal_errors,
            self._circuit_breaker_config.max_fatal_errors,
        )

        if new_count >= self._circuit_breaker_config.max_fatal_errors:
            _LOGGER.warning(
                "Formula '%s': Circuit breaker triggered after %d errors",
                formula_name,
                new_count,
            )
