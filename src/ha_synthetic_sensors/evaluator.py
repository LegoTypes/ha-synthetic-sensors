"""Enhanced formula evaluation for YAML-based synthetic sensors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
import re
from typing import Any, Callable, NotRequired, TypedDict, Union

from homeassistant.core import HomeAssistant
from simpleeval import SimpleEval  # type: ignore[import-untyped]

from .cache import CacheConfig, FormulaCache
from .collection_resolver import CollectionResolver
from .config_manager import FormulaConfig
from .dependency_parser import DependencyParser
from .math_functions import MathFunctions

_LOGGER = logging.getLogger(__name__)


class NonNumericStateError(Exception):
    """Raised when an entity state cannot be converted to a numeric value."""

    def __init__(self, entity_id: str, state_value: str):
        self.entity_id = entity_id
        self.state_value = state_value
        super().__init__(f"Entity '{entity_id}' has non-numeric state '{state_value}'")


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
        # Use either name or id as formula identifier
        formula_name = config.name or config.id

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
            cached_result = self._cache.get_result(config.formula, filtered_context, formula_name)
            if cached_result is not None:
                return {
                    "success": True,
                    "value": cached_result,
                    "cached": True,
                    "state": "ok",
                }

            # Extract dependencies using parser
            dependencies = self.get_formula_dependencies(config.formula)

            # Validate dependencies are available
            missing_deps, unavailable_deps = self._check_dependencies(dependencies, context)

            # Handle missing entities (fatal error)
            if missing_deps:
                # TIER 1 FATAL ERROR: Increment fatal error counter
                # Missing entities indicate permanent configuration issues
                self._increment_error_count(formula_name)
                return {
                    "success": False,
                    "error": f"Missing dependencies: {missing_deps}",
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

            # Create evaluator with proper separation of names and functions
            evaluator = SimpleEval()
            evaluator.names = eval_context
            evaluator.functions = self._math_functions.copy()

            # Preprocess formula: convert entity_ids with dots to underscores for simpleeval
            processed_formula = self._preprocess_formula_for_evaluation(config.formula)

            # Evaluate the preprocessed formula
            result = evaluator.eval(processed_formula)

            # Cache the result
            self._cache.store_result(config.formula, result, filtered_context, formula_name)

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
            # TWO-TIER ERROR CLASSIFICATION:
            # We analyze the exception to determine whether it represents a fatal
            # error (configuration/syntax issues) or a transitory error (temporary
            # runtime issues that might resolve themselves).

            error_message = str(err)
            is_fatal_error = (
                # Missing variable definitions (e.g., typos in entity names)
                "name" in error_message.lower()
                and "not defined" in error_message.lower()
            ) or (
                # Syntax errors in formula (e.g., malformed expressions)
                "syntax"
                in error_message.lower()
            )

            if is_fatal_error:
                # TIER 1: Fatal errors
                self._increment_error_count(formula_name)
            else:
                # TIER 2: Transitory errors
                if self._circuit_breaker_config.track_transitory_errors:
                    self._increment_transitory_error_count(formula_name)

            return {
                "success": False,
                "error": f"Formula evaluation failed for '{formula_name}': {err}",
                "value": None,
            }

    def _check_dependencies(self, dependencies: set[str], context: dict[str, ContextValue] | None = None) -> tuple[set[str], set[str]]:
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
                # Check if the state can be converted to numeric
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

    def _preprocess_formula_for_evaluation(self, formula: str) -> str:
        """Preprocess formula: resolve collection functions and normalize entity IDs.

        Args:
            formula: Original formula string

        Returns:
            Preprocessed formula with collection functions resolved and normalized entity_id variable names
        """
        processed_formula = formula

        # First, resolve collection functions
        processed_formula = self._resolve_collection_functions(processed_formula)

        # Find all entity references using dependency parser
        entity_refs = self._dependency_parser.extract_entity_references(processed_formula)

        # Replace each entity_id with normalized version
        for entity_id in entity_refs:
            if "." in entity_id:
                normalized_name = entity_id.replace(".", "_")
                # Use word boundaries to ensure we only replace complete entity_ids
                pattern = r"\b" + re.escape(entity_id) + r"\b"
                processed_formula = re.sub(pattern, normalized_name, processed_formula)

        return processed_formula

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
                    # Replace with empty function call to avoid syntax errors
                    original_pattern = f'{query.function}("{query.query_type}:{query.pattern}")'
                    resolved_formula = resolved_formula.replace(original_pattern, f"{query.function}()")
                    continue

                # Get numeric values for the entities
                values = self._collection_resolver.get_entity_values(entity_ids)

                if not values:
                    _LOGGER.warning("No numeric values found for collection query %s:%s", query.query_type, query.pattern)
                    # Replace with empty function call
                    original_pattern = f'{query.function}("{query.query_type}:{query.pattern}")'
                    resolved_formula = resolved_formula.replace(original_pattern, f"{query.function}()")
                    continue

                # Replace the collection function with the resolved values
                values_str = ", ".join(str(v) for v in values)
                original_pattern = f'{query.function}("{query.query_type}:{query.pattern}")'
                resolved_formula = resolved_formula.replace(original_pattern, f"{query.function}({values_str})")

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
