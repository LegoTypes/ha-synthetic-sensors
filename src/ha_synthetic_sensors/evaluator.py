"""Enhanced formula evaluation for YAML-based synthetic sensors."""

from __future__ import annotations

from abc import ABC, abstractmethod
import ast
from dataclasses import dataclass
import logging
import re
from typing import Any, Callable, NotRequired, TypedDict

from homeassistant.core import HomeAssistant
from simpleeval import SimpleEval

from .cache import CacheConfig, FormulaCache
from .collection_resolver import CollectionResolver
from .config_manager import FormulaConfig
from .dependency_parser import DependencyParser
from .exceptions import (
    FormulaSyntaxError,
    MissingDependencyError,
    NonNumericStateError,
    is_fatal_error,
    is_retriable_error,
)
from .math_functions import MathFunctions

_LOGGER = logging.getLogger(__name__)


# NonNumericStateError is now imported from exceptions module


# Type alias for evaluation context values
ContextValue = str | float | int | bool | Callable[..., Any]

# Type alias for formula evaluation results
FormulaResult = float | int | str | bool | None


# TypedDicts for evaluator results
class EvaluationResult(TypedDict):
    """Result of formula evaluation."""

    success: bool
    value: FormulaResult
    error: NotRequired[str]
    cached: NotRequired[bool]
    state: NotRequired[str]  # "ok", "unknown", "unavailable"
    unavailable_dependencies: NotRequired[list[str]]
    missing_dependencies: NotRequired[list[str]]


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
    ):
        """Initialize the enhanced formula evaluator.

        Args:
            hass: Home Assistant instance
            cache_config: Optional cache configuration
            circuit_breaker_config: Optional circuit breaker configuration
            retry_config: Optional retry configuration for transitory errors

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

        # TIER 1: Fatal Error Circuit Breaker (Traditional Pattern)
        # Tracks configuration errors, syntax errors, missing entities, etc.
        self._error_count: dict[str, int] = {}

        # TIER 2: Transitory Error Tracking (Intelligent Resilience)
        # Tracks temporary issues like unknown/unavailable entity states.
        self._transitory_error_count: dict[str, int] = {}

    def evaluate_formula(self, config: FormulaConfig, context: dict[str, ContextValue] | None = None) -> EvaluationResult:
        """Evaluate a formula configuration with enhanced error handling."""
        # Use either name or id as formula identifier for display/logging
        formula_name = config.name or config.id
        # Use config.id for cache key generation to ensure uniqueness
        # config.name is just for display and is not guaranteed to be unique
        cache_key_id = config.id

        try:
            # Check if we should bail due to too many attempts
            if self._should_skip_evaluation(formula_name):
                return {
                    "success": False,
                    "error": (f"Skipping formula '{formula_name}' due to repeated errors"),
                    "value": None,
                }

            # Check cache first
            filtered_context = self._filter_context_for_cache(context)
            cached_result = self._cache.get_result(config.formula, filtered_context, cache_key_id)
            if cached_result is not None:
                return {
                    "success": True,
                    "value": cached_result,
                    "cached": True,
                    "state": "ok",
                }

            # Extract dependencies using enhanced method that handles variables and collection functions
            dependencies = self._extract_formula_dependencies(config, context)

            # Identify collection pattern entities that don't need numeric validation
            parsed_deps = self._dependency_parser.parse_formula_dependencies(config.formula, {})
            collection_pattern_entities = set()
            for query in parsed_deps.dynamic_queries:
                entity_refs = self._collection_resolver._entity_reference_pattern.findall(query.pattern)
                collection_pattern_entities.update(entity_refs)

            # Validate dependencies are available
            missing_deps, unavailable_deps = self._check_dependencies(dependencies, context, collection_pattern_entities)

            # Handle missing entities (fatal error)
            if missing_deps:
                # TIER 1 FATAL ERROR: Increment fatal error counter
                # Missing entities indicate permanent configuration issues
                error = MissingDependencyError(", ".join(missing_deps), formula_name)
                self._increment_error_count(formula_name)
                _LOGGER.error("Missing dependencies in formula '%s': %s", formula_name, missing_deps)
                return {
                    "success": False,
                    "error": str(error),
                    "value": None,
                    "state": "unavailable",
                    "missing_dependencies": list(missing_deps),
                }

            # Handle unavailable entities (propagate unknown state)
            if unavailable_deps:
                # TIER 2 TRANSITORY HANDLING: Don't increment fatal error count
                # Instead, track as transitory and propagate unknown state upward
                # Allows the synthetic sensor to indicate temporary unavailability
                if self._circuit_breaker_config.track_transitory_errors:
                    self._increment_transitory_error_count(formula_name)
                _LOGGER.info(
                    "Formula '%s' has unavailable dependencies: %s. " "Setting synthetic sensor to unknown state.",
                    formula_name,
                    unavailable_deps,
                )
                return {
                    "success": True,  # Not an error, but dependency unavailable
                    "value": None,
                    "state": "unknown",
                    "unavailable_dependencies": list(unavailable_deps),
                }

            # Build evaluation context
            eval_context = self._build_evaluation_context(dependencies, context)

            # Additional safety check: if any values in the context are unavailable/unknown,
            # return early to prevent simpleeval errors
            for var_name, var_value in eval_context.items():
                if isinstance(var_value, str) and var_value in ("unavailable", "unknown"):
                    _LOGGER.debug("Formula '%s' has variable '%s' with unavailable value '%s'. " "Setting synthetic sensor to unknown state.", formula_name, var_name, var_value)
                    return {
                        "success": True,  # Not an error, but dependency unavailable
                        "value": None,
                        "state": "unknown",
                        "unavailable_dependencies": [var_name],
                    }

            # Create evaluator with proper separation of names and functions
            evaluator = SimpleEval()
            evaluator.names = eval_context
            evaluator.functions = self._math_functions.copy()

            # Preprocess formula: resolve variables first, then collection functions, then normalize entity_ids
            processed_formula = self._preprocess_formula_for_evaluation(config.formula, eval_context)

            # Optimization: If the formula has been completely resolved to a literal,
            # we can evaluate it directly without needing the complex evaluation context
            try:
                # Check if the processed formula is a simple numeric literal
                result = float(processed_formula)
                # If we get here, it's a pure number - no need for complex evaluation

            except ValueError:
                # Not a literal - proceed with normal evaluation
                result = evaluator.eval(processed_formula)

            # Cache the result
            self._cache.store_result(config.formula, result, filtered_context, cache_key_id)

            # Reset error count on success
            # CIRCUIT BREAKER RESET: When a formula evaluates successfully,
            # we reset BOTH error counters to allow recovery from previous issues
            if self._circuit_breaker_config.reset_on_success:
                self._error_count.pop(formula_name, None)
                self._transitory_error_count.pop(formula_name, None)

            return {
                "success": True,
                "value": result,
                "cached": False,
                "state": "ok",
            }

        except Exception as err:
            # TWO-TIER ERROR CLASSIFICATION following HA coordinator patterns:
            # We analyze the exception to determine whether it represents a fatal
            # error (configuration/syntax issues) or a transitory error (temporary
            # runtime issues that might resolve themselves).

            if is_fatal_error(err):
                # TIER 1: Fatal errors - permanent configuration issues
                self._increment_error_count(formula_name)
                _LOGGER.error("Fatal error in formula '%s': %s", formula_name, err)

                # For fatal errors, we could raise UpdateFailed to trigger coordinator retry logic
                # but for now we return error state to allow graceful degradation
                return {
                    "success": False,
                    "error": f"Fatal error in formula '{formula_name}': {err}",
                    "value": None,
                    "state": "unavailable",
                }
            elif is_retriable_error(err):
                # TIER 2: Transitory errors - temporary issues that might resolve
                if self._circuit_breaker_config.track_transitory_errors:
                    self._increment_transitory_error_count(formula_name)
                _LOGGER.warning("Transitory error in formula '%s': %s", formula_name, err)

                return {
                    "success": True,  # Not a failure, just temporarily unavailable
                    "value": None,
                    "state": "unknown",
                    "error": f"Transitory error: {err}",
                }
            else:
                # Unknown error type - treat as fatal for safety
                error_message = str(err)
                is_syntax_error = "not defined" in error_message.lower() or "syntax" in error_message.lower()

                if is_syntax_error:
                    # Wrap in our exception type for better error handling
                    syntax_error = FormulaSyntaxError(config.formula, str(err))
                    self._increment_error_count(formula_name)
                    _LOGGER.error("Syntax error in formula '%s': %s", formula_name, syntax_error)

                    return {
                        "success": False,
                        "error": str(syntax_error),
                        "value": None,
                        "state": "unavailable",
                    }
                else:
                    # Unknown error - treat as transitory for graceful degradation
                    if self._circuit_breaker_config.track_transitory_errors:
                        self._increment_transitory_error_count(formula_name)
                    _LOGGER.warning("Unknown error in formula '%s': %s", formula_name, err)

                    return {
                        "success": False,
                        "error": f"Unknown error in formula '{formula_name}': {err}",
                        "value": None,
                        "state": "unknown",
                    }

    def _check_dependencies(self, dependencies: set[str], context: dict[str, ContextValue] | None = None, collection_pattern_entities: set[str] | None = None) -> tuple[set[str], set[str]]:
        """Check which dependencies are missing or unavailable.

        This method is a critical part of the two-tier circuit breaker system.
        It distinguishes between two types of dependency issues:

        1. MISSING ENTITIES: Entities that don't exist in Home Assistant
           - These are FATAL errors (Tier 1)
           - Usually indicate configuration mistakes or typos
           - Will cause the formula to fail and increment fatal error count

        2. UNAVAILABLE ENTITIES: Entities that exist but are unavailable/unknown/
           non-numeric
           - These are TRANSITORY errors (Tier 2)
           - Usually indicate temporary issues (network, device offline, etc.)
           - Formula evaluation continues but propagates unknown state upward

        Args:
            dependencies: Set of dependency names to check
            context: Optional context dictionary with variable values

        Returns:
            Tuple of (missing_entities, unavailable_entities)
        """
        missing = set()
        unavailable = set()
        context = context or {}
        collection_pattern_entities = collection_pattern_entities or set()

        for entity_id in dependencies:
            # First check if provided in context
            if entity_id in context:
                continue
            # Then check if it's a Home Assistant entity
            state = self._hass.states.get(entity_id)
            if state is None:
                # FATAL ERROR: Entity doesn't exist in Home Assistant
                missing.add(entity_id)
            elif state.state in ("unavailable", "unknown"):
                # TRANSITORY ERROR: Entity exists but currently unavailable
                unavailable.add(entity_id)
            else:
                # Special handling for collection pattern entities - they don't need numeric validation
                if entity_id in collection_pattern_entities:
                    # Collection pattern entities can have any state value (they're used as pattern sources)
                    continue

                # Check if the state can be converted to numeric (for mathematical operations)
                try:
                    self._convert_to_numeric(state.state, entity_id)
                except NonNumericStateError:
                    # Determine if this is a FATAL or TRANSITORY error based on
                    # entity type
                    if self._is_entity_supposed_to_be_numeric(state):
                        # TRANSITORY ERROR: Entity should be numeric but currently isn't
                        # (e.g., sensor.temperature returning "starting_up")
                        unavailable.add(entity_id)
                    else:
                        # FATAL ERROR: Entity is fundamentally non-numeric
                        # (e.g., binary_sensor.door, weather.current_condition)
                        missing.add(entity_id)

        return missing, unavailable

    def get_formula_dependencies(self, formula: str) -> set[str]:
        """Extract and return all entity dependencies from a formula."""
        # Check cache first
        cached_deps = self._cache.get_dependencies(formula)
        if cached_deps is not None:
            return cached_deps

        # Use dependency parser
        dependencies = self._dependency_parser.extract_dependencies(formula)

        # Cache the result
        self._cache.store_dependencies(formula, dependencies)
        return dependencies

    def _extract_formula_dependencies(self, config: FormulaConfig, context: dict[str, ContextValue] | None = None) -> set[str]:
        """Extract dependencies from formula config, handling entity references in collection patterns.

        This method extracts dependencies for the new design where entity references
        can appear directly within collection patterns like sum("device_class: input_select.device_type").

        Args:
            config: Formula configuration with variables
            context: Optional evaluation context

        Returns:
            Set of actual entity dependencies needed for evaluation
        """
        dependencies = set()

        # Add variable entity references as dependencies (for backward compatibility)
        if hasattr(config, "variables") and config.variables:
            for _var_name, entity_id in config.variables.items():
                dependencies.add(entity_id)

        # Extract entity references from collection patterns
        parsed_deps = self._dependency_parser.parse_formula_dependencies(config.formula, {})

        for query in parsed_deps.dynamic_queries:
            # Look for entity references within the pattern using collection resolver's pattern
            entity_refs = self._collection_resolver._entity_reference_pattern.findall(query.pattern)
            dependencies.update(entity_refs)

        # Extract regular dependencies (non-collection function entities)
        static_deps = self._dependency_parser.extract_entity_references(config.formula)
        dependencies.update(static_deps)

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
        if "entity(" not in formula and "state(" not in formula and "states." not in formula:
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
                context[f"entity_{entity_id.replace('.', '_')}"] = self._get_numeric_state(state)

                # Add attribute access
                for attr_name, attr_value in state.attributes.items():
                    safe_attr_name = f"{entity_id.replace('.', '_')}_{attr_name.replace('.', '_')}"
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
        """Get cache statistics for monitoring.

        Returns statistics that include both cache performance metrics and
        error tracking information from the two-tier circuit breaker system.
        This allows monitoring of both successful operations and error patterns.
        """
        stats = self._cache.get_statistics()
        return {
            "total_cached_formulas": stats["dependency_entries"],
            "total_cached_evaluations": stats["total_entries"],
            "valid_cached_evaluations": stats["valid_entries"],
            "error_counts": dict(self._error_count),  # Fatal errors only
            "cache_ttl_seconds": stats["ttl_seconds"],
            # Note: transitory_error_count is tracked but not exposed in stats
            # as these are temporary issues that don't indicate system problems
        }

    def get_circuit_breaker_config(self) -> CircuitBreakerConfig:
        """Get the current circuit breaker configuration."""
        return self._circuit_breaker_config

    def get_retry_config(self) -> RetryConfig:
        """Get the current retry configuration."""
        return self._retry_config

    def update_circuit_breaker_config(self, config: CircuitBreakerConfig) -> None:
        """Update the circuit breaker configuration.

        Args:
            config: New circuit breaker configuration
        """
        self._circuit_breaker_config = config

    def update_retry_config(self, config: RetryConfig) -> None:
        """Update the retry configuration.

        Args:
            config: New retry configuration
        """
        self._retry_config = config

    def _build_evaluation_context(self, dependencies: set[str], context: dict[str, ContextValue] | None = None) -> dict[str, Any]:
        """Build the evaluation context with entity states and dynamic query resolution."""
        eval_context = {}

        # Add provided context (this includes variables resolved by formula config)
        if context:
            eval_context.update(context)

        # Resolve dependencies that are entity_ids (not already in context)
        for entity_id in dependencies:
            # Skip if already provided in context (variable resolution)
            if entity_id in eval_context:
                continue

            state = self._hass.states.get(entity_id)
            if state is not None:
                try:
                    # Try to get numeric state value
                    numeric_value = self._get_numeric_state(state)

                    # For entity_ids with dots, add both original and normalized forms to support
                    # both "sensor.entity_name" and "sensor_entity_name" variable access
                    eval_context[entity_id] = numeric_value
                    if "." in entity_id:
                        normalized_name = entity_id.replace(".", "_")
                        eval_context[normalized_name] = numeric_value

                    # Add state object for attribute access
                    eval_context[f"{entity_id}_state"] = state

                except (ValueError, TypeError, NonNumericStateError):
                    # For non-numeric states, keep as string
                    eval_context[entity_id] = state.state
                    if "." in entity_id:
                        normalized_name = entity_id.replace(".", "_")
                        eval_context[normalized_name] = state.state
                    eval_context[f"{entity_id}_state"] = state

        return eval_context

    def _increment_transitory_error_count(self, formula_name: str) -> None:
        """Increment transitory error count for a formula.

        TIER 2 ERROR TRACKING: Transitory errors are tracked separately from
        fatal errors. They represent temporary issues that might resolve on their
        own (e.g., network connectivity, device availability). Unlike fatal errors,
        these don't trigger the circuit breaker and don't prevent continued
        evaluation attempts.

        Examples of transitory errors:
        - Entity states showing "unknown" or "unavailable"
        - Temporary network connectivity issues
        - Devices that are temporarily offline but will come back

        Args:
            formula_name: Name/ID of the formula that encountered the error
        """
        current = self._transitory_error_count.get(formula_name, 0)
        self._transitory_error_count[formula_name] = current + 1

    def _should_skip_evaluation(self, formula_name: str) -> bool:
        """Check if formula should be skipped due to repeated errors.

        CIRCUIT BREAKER LOGIC: This method implements the traditional circuit
        breaker pattern but ONLY for fatal errors (Tier 1). Transitory errors
        (Tier 2) are tracked separately and do NOT trigger the circuit breaker.

        This intelligent approach allows the system to:
        1. Stop wasting resources on permanently broken formulas (fatal errors)
        2. Continue attempting evaluation for temporarily unavailable dependencies
        3. Gracefully handle mixed scenarios where some dependencies are missing
           and others are just temporarily unavailable

        Args:
            formula_name: Name/ID of the formula to check

        Returns:
            True if evaluation should be skipped due to too many FATAL errors
        """
        fatal_errors = self._error_count.get(formula_name, 0)
        return fatal_errors >= self._circuit_breaker_config.max_fatal_errors

    def _increment_error_count(self, formula_name: str) -> None:
        """Increment fatal error count for a formula.

        TIER 1 ERROR TRACKING: Fatal errors represent permanent issues that
        require manual intervention to resolve. These errors trigger the
        traditional circuit breaker pattern to prevent wasting system resources.

        Examples of fatal errors:
        - Syntax errors in formula expressions
        - References to non-existent entities (typos in entity_ids)
        - Invalid mathematical operations or function calls
        - Configuration errors that won't resolve automatically

        When the fatal error count reaches the configured maximum (default: 5), the
        circuit breaker opens and evaluation attempts are skipped entirely.

        Args:
            formula_name: Name/ID of the formula that encountered the error
        """
        self._error_count[formula_name] = self._error_count.get(formula_name, 0) + 1

    def _get_numeric_state(self, state: Any) -> float:
        """Get numeric value from entity state, with error handling.

        This method now properly raises exceptions for non-numeric states
        instead of silently returning 0, which could mask configuration issues.
        """
        try:
            return self._convert_to_numeric(state.state, getattr(state, "entity_id", "unknown"))
        except NonNumericStateError:
            # For backward compatibility in contexts where we need a fallback,
            # log the issue but still return 0. The caller should handle this properly.
            _LOGGER.warning(
                "Entity '%s' has non-numeric state '%s', using 0 as fallback",
                getattr(state, "entity_id", "unknown"),
                state.state,
            )
            return 0.0

    def _convert_to_numeric(self, state_value: Any, entity_id: str) -> float:
        """Convert a state value to numeric, raising exception if not possible.

        Args:
            state_value: The state value to convert
            entity_id: Entity ID for error reporting

        Returns:
            float: Numeric value

        Raises:
            NonNumericStateError: If the state cannot be converted to numeric
        """
        try:
            return float(state_value)
        except (ValueError, TypeError) as err:
            # Try to extract numeric value from common patterns (e.g., "25.5°C")
            if isinstance(state_value, str):
                # Remove common units and try again
                cleaned = re.sub(r"[^\d.-]", "", state_value)
                if cleaned:
                    try:
                        return float(cleaned)
                    except ValueError:
                        pass

            # If we can't convert, raise an exception instead of returning 0
            raise NonNumericStateError(entity_id, str(state_value)) from err

    def _filter_context_for_cache(self, context: dict[str, ContextValue] | None) -> dict[str, str | float | int | bool] | None:
        """Filter context to only include types that can be cached.

        Args:
            context: Original context which may include callables

        Returns:
            Filtered context with only cacheable types
        """
        if context is None:
            return None

        return {key: value for key, value in context.items() if isinstance(value, (str, float, int, bool))}

    def _is_entity_supposed_to_be_numeric(self, state: Any) -> bool:
        """Determine if entity should be numeric based on domain and device_class.

        This method implements smart error classification by analyzing entity
        metadata to distinguish between:

        NUMERIC entities (TRANSITORY when non-numeric):
        - sensor.* with numeric device classes (power, energy, temperature, etc.)
        - input_number.*
        - counter.*
        - number.*

        NON-NUMERIC entities (FATAL when referenced in formulas):
        - binary_sensor.* (returns "on"/"off")
        - switch.* (returns "on"/"off")
        - device_tracker.* (returns location names)
        - sensor.* with non-numeric device classes (timestamp, date, etc.)

        Args:
            state: Home Assistant state object

        Returns:
            bool: True if entity should contain numeric values
        """
        entity_id = getattr(state, "entity_id", "")
        domain = entity_id.split(".")[0] if "." in entity_id else ""
        device_class = getattr(state, "attributes", {}).get("device_class")

        # Domains that are always numeric
        numeric_domains = {"input_number", "counter", "number"}

        # Domains that are never numeric
        non_numeric_domains = {
            "binary_sensor",
            "switch",
            "input_boolean",
            "device_tracker",
            "weather",
            "climate",
            "media_player",
            "light",
            "fan",
            "cover",
            "alarm_control_panel",
            "lock",
            "vacuum",
        }

        # Check obvious cases first
        if domain in numeric_domains:
            return True
        if domain in non_numeric_domains:
            return False

        # For sensors, analyze device_class
        if domain == "sensor":
            # Non-numeric sensor device classes
            non_numeric_device_classes = {
                "timestamp",
                "date",
                "enum",
                "connectivity",
                "moving",
                "opening",
                "presence",
                "problem",
                "safety",
                "tamper",
                "update",
            }

            if device_class in non_numeric_device_classes:
                return False

            # If no device_class, try to infer from state value patterns
            if device_class is None:
                # Check if current state looks numeric
                try:
                    float(state.state)
                    # Current state is numeric, likely a numeric sensor
                    return True
                except (ValueError, TypeError):
                    # Non-numeric state - could be temporary or permanent
                    # Use heuristics based on common patterns
                    state_value = str(state.state).lower()

                    # Temporary states that indicate a normally numeric sensor
                    temporary_states = {
                        "unknown",
                        "unavailable",
                        "starting",
                        "initializing",
                        "calibrating",
                        "loading",
                        "connecting",
                        "offline",
                        "error",
                    }

                    if state_value in temporary_states:
                        return True

                    # Check for numeric patterns with units (e.g., "25.5°C")
                    # Non-numeric descriptive states suggest non-numeric sensor
                    return bool(re.search(r"\d+\.?\d*", state_value))

            # If we have a device_class but it's not in our non-numeric list,
            # assume it's numeric (most sensor device_classes are numeric)
            return True

        # For other domains, default to assuming non-numeric
        return False

    def _preprocess_formula_for_evaluation(self, formula: str, eval_context: dict[str, Any] | None = None) -> str:
        """Preprocess formula: resolve variables first, then collection functions, then normalize entity IDs.

        This method now implements variable-first processing to enable dynamic collection patterns.
        Processing order:
        1. Resolve variables and string operations (enables dynamic pattern construction)
        2. Resolve collection functions (with potentially variable-based patterns)
        3. Normalize entity IDs for simpleeval compatibility

        Args:
            formula: Original formula string
            eval_context: Evaluation context with variable values (optional)

        Returns:
            Preprocessed formula with variables resolved, collection functions resolved, and normalized entity_id variable names
        """
        processed_formula = formula

        # Step 1: Resolve variables and string operations to enable dynamic collection patterns
        if eval_context:
            processed_formula = self._resolve_variables_and_strings(processed_formula, eval_context)

        # Step 2: Resolve collection functions (now with potentially dynamic patterns)
        processed_formula = self._resolve_collection_functions(processed_formula)

        # Step 3: Find all entity references using dependency parser and normalize
        entity_refs = self._dependency_parser.extract_entity_references(processed_formula)

        # Replace each entity_id with normalized version
        for entity_id in entity_refs:
            if "." in entity_id:
                normalized_name = entity_id.replace(".", "_")
                # Use word boundaries to ensure we only replace complete entity_ids
                pattern = r"\b" + re.escape(entity_id) + r"\b"
                processed_formula = re.sub(pattern, normalized_name, processed_formula)

        return processed_formula

    def _resolve_variables_and_strings(self, formula: str, eval_context: dict[str, Any]) -> str:
        """Resolve variables and string operations in formula for dynamic pattern construction.

        This method performs a limited evaluation that only resolves:
        - Variable substitution
        - String concatenation operations
        - Basic string operations needed for collection pattern construction

        It does NOT evaluate:
        - Mathematical operations
        - Collection functions (those are resolved later)
        - Complex expressions

        Args:
            formula: Formula with potential variable references and string operations
            eval_context: Context containing variable values

        Returns:
            Formula with variables and string operations resolved
        """
        try:
            # Create a limited evaluator for string operations only
            string_evaluator = SimpleEval()
            string_evaluator.names = eval_context.copy()

            # Only allow string operations and basic functions needed for pattern construction
            string_evaluator.functions = {
                "str": str,
                "float": float,
                "int": int,
                # Note: We don't include mathematical functions here to avoid premature evaluation
            }

            # We need to be careful here - we want to resolve string concatenation
            # but not evaluate collection functions or mathematical expressions yet.
            #
            # Strategy: Look for string concatenation patterns and resolve those,
            # but leave everything else untouched.

            # For now, implement a simple approach: try to evaluate string expressions only
            # This is a starting implementation that can be enhanced later

            # Look for quoted string concatenation patterns like "device_class:" + variable
            # Parse the formula to find string concatenation
            try:
                tree = ast.parse(formula, mode="eval")
                resolved_formula = self._resolve_string_concatenations(tree, eval_context)
                return resolved_formula
            except (SyntaxError, ValueError):
                # If we can't parse it, return the original formula
                _LOGGER.debug("Could not parse formula for string resolution: %s", formula)
                return formula

        except Exception as e:
            _LOGGER.warning("Error resolving variables and strings in formula '%s': %s", formula, e)
            return formula

    def _resolve_string_concatenations(self, node: ast.AST, eval_context: dict[str, Any]) -> str:
        """Recursively resolve string concatenation operations in AST.

        Args:
            node: AST node to process
            eval_context: Variable values

        Returns:
            String representation with concatenations resolved
        """
        if isinstance(node, ast.Expression):
            return self._resolve_string_concatenations(node.body, eval_context)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            # Handle string concatenation
            left = self._resolve_string_concatenations(node.left, eval_context)
            right = self._resolve_string_concatenations(node.right, eval_context)

            # If both sides are strings (quoted), concatenate them
            if left.startswith('"') and left.endswith('"') and right.startswith('"') and right.endswith('"'):
                return f'"{left[1:-1]}{right[1:-1]}"'
            # If left is string and right is a resolved variable value
            elif left.startswith('"') and left.endswith('"'):
                return f'"{left[1:-1]}{right}"'
            # If right is string and left is a resolved variable value
            elif right.startswith('"') and right.endswith('"'):
                return f'"{left}{right[1:-1]}"'
            else:
                # Return as concatenation expression if not both strings
                return f"{left} + {right}"
        elif isinstance(node, ast.Constant):
            # String literal
            if isinstance(node.value, str):
                return f'"{node.value}"'
            else:
                return str(node.value)
        elif isinstance(node, ast.Name):
            # Variable reference
            var_name = node.id
            if var_name in eval_context:
                value = eval_context[var_name]
                if isinstance(value, str):
                    return value  # Don't quote it since it's a resolved variable value
                else:
                    return str(value)
            else:
                return var_name
        elif isinstance(node, ast.Call):
            # Function call - don't resolve these yet, leave as-is
            func_name = ast.unparse(node)
            return func_name
        else:
            # For other node types, return the unparsed version
            return ast.unparse(node)

    def _resolve_collection_functions(self, formula: str) -> str:
        r"""Resolve collection functions by replacing them with actual entity values.

        Collections, unlike single entities use literal value replacement, not runtime variables.
        Collection patterns like sum("regex:sensor\.circuit_.*") are resolved fresh on each
        evaluation to actual values: sum(150.5, 225.3, 89.2). This eliminates cache staleness
        issues when entities are added/removed and ensures dynamic discovery works correctly.

        Args:
            formula: Formula containing collection functions

        Returns:
            Formula with collection functions replaced by actual values
        """
        try:
            # Extract dynamic queries from the formula
            parsed_deps = self._dependency_parser.parse_formula_dependencies(formula, {})

            if not parsed_deps.dynamic_queries:
                return formula  # No collection functions to resolve

            resolved_formula = formula

            for query in parsed_deps.dynamic_queries:
                # Resolve collection to get matching entity IDs
                entity_ids = self._collection_resolver.resolve_collection(query)

                if not entity_ids:
                    _LOGGER.warning("Collection query %s:%s matched no entities", query.query_type, query.pattern)

                    # Return appropriate default values for different functions
                    if query.function == "sum":
                        default_value = "0"
                    elif query.function == "max" or query.function == "min":
                        default_value = "0"  # or could be None/error
                    elif query.function in ("avg", "average") or query.function == "count":
                        default_value = "0"
                    else:
                        default_value = "0"  # Default fallback

                    # Handle both space formats for replacement
                    pattern_with_space = f'{query.function}("{query.query_type}: {query.pattern}")'
                    pattern_without_space = f'{query.function}("{query.query_type}:{query.pattern}")'

                    if pattern_with_space in resolved_formula:
                        resolved_formula = resolved_formula.replace(pattern_with_space, default_value)
                    elif pattern_without_space in resolved_formula:
                        resolved_formula = resolved_formula.replace(pattern_without_space, default_value)
                    continue

                # Get numeric values for the entities
                values = self._collection_resolver.get_entity_values(entity_ids)

                if not values:
                    _LOGGER.warning("No numeric values found for collection query %s:%s", query.query_type, query.pattern)

                    # Return appropriate default values for different functions
                    if query.function == "sum":
                        default_value = "0"
                    elif query.function == "max" or query.function == "min":
                        default_value = "0"  # or could be None/error
                    elif query.function in ("avg", "average") or query.function == "count":
                        default_value = "0"
                    else:
                        default_value = "0"  # Default fallback

                    # Handle both space formats for replacement
                    pattern_with_space = f'{query.function}("{query.query_type}: {query.pattern}")'
                    pattern_without_space = f'{query.function}("{query.query_type}:{query.pattern}")'

                    if pattern_with_space in resolved_formula:
                        resolved_formula = resolved_formula.replace(pattern_with_space, default_value)
                    elif pattern_without_space in resolved_formula:
                        resolved_formula = resolved_formula.replace(pattern_without_space, default_value)
                    continue

                # Replace the collection function with the resolved values
                # Calculate the result directly instead of generating list literals
                values_str = ", ".join(str(v) for v in values)  # For logging and fallback

                result: float | int | str
                if query.function == "sum":
                    result = sum(values)
                elif query.function == "max":
                    result = max(values)
                elif query.function == "min":
                    result = min(values)
                elif query.function == "avg" or query.function == "average":
                    result = sum(values) / len(values) if values else 0
                elif query.function == "count":
                    result = len(values)
                else:
                    # For unknown functions, fall back to comma-separated values
                    result = f"{query.function}({values_str})"

                # Handle both space formats that users might input in YAML
                # Try both "device_class: power" and "device_class:power" patterns
                pattern_with_space = f'{query.function}("{query.query_type}: {query.pattern}")'
                pattern_without_space = f'{query.function}("{query.query_type}:{query.pattern}")'

                # Replace whichever pattern exists in the formula
                if pattern_with_space in resolved_formula:
                    resolved_formula = resolved_formula.replace(pattern_with_space, str(result))
                elif pattern_without_space in resolved_formula:
                    resolved_formula = resolved_formula.replace(pattern_without_space, str(result))
                else:
                    _LOGGER.warning("Could not find pattern to replace for %s:%s", query.query_type, query.pattern)

                _LOGGER.debug("Resolved collection %s:%s to %d values: [%s]", query.query_type, query.pattern, len(values), values_str[:100])

            return resolved_formula

        except Exception as e:
            _LOGGER.error("Error resolving collection functions in formula '%s': %s", formula, e)
            return formula  # Return original formula if resolution fails


@dataclass
class CircuitBreakerConfig:
    """Configuration for the two-tier circuit breaker pattern."""

    # TIER 1: Fatal Error Circuit Breaker
    max_fatal_errors: int = 5  # Stop trying after this many fatal errors

    # TIER 2: Transitory Error Handling
    max_transitory_errors: int = 20  # Track but don't stop on transitory errors
    track_transitory_errors: bool = True  # Whether to track transitory errors

    # Error Reset Behavior
    reset_on_success: bool = True  # Reset counters on successful evaluation


@dataclass
class RetryConfig:
    """Configuration for handling unavailable dependencies and retry logic."""

    enabled: bool = True
    max_attempts: int = 3
    backoff_seconds: float = 5.0
    exponential_backoff: bool = True
    retry_on_unknown: bool = True
    retry_on_unavailable: bool = True


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

        def visit(sensor: str) -> None:
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

        def dfs(sensor: str, path: list[str]) -> None:
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
                    dfs(dep, [*path, sensor])

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

    def evaluate(self, formula: str, context: dict[str, float | int | str] | None = None) -> float:
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
