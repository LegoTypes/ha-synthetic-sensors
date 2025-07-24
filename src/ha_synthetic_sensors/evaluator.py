"""Enhanced formula evaluation for YAML-based synthetic sensors."""

from __future__ import annotations

from abc import ABC, abstractmethod
import ast
import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant

from .cache import CacheConfig, FormulaCache
from .collection_resolver import CollectionResolver
from .config_models import FormulaConfig, SensorConfig
from .constants_formula import is_reserved_word
from .dependency_parser import DependencyParser
from .evaluator_cache import EvaluatorCache
from .evaluator_config import CircuitBreakerConfig, RetryConfig
from .evaluator_dependency import EvaluatorDependency
from .evaluator_error_handler import EvaluatorErrorHandler
from .evaluator_handlers import HandlerFactory
from .evaluator_phases.context_building import ContextBuildingPhase
from .evaluator_phases.dependency_management import DependencyManagementPhase
from .evaluator_phases.dependency_management.generic_dependency_manager import GenericDependencyManager
from .evaluator_phases.pre_evaluation import PreEvaluationPhase
from .evaluator_phases.sensor_registry import SensorRegistryPhase
from .evaluator_phases.variable_resolution import VariableResolutionPhase
from .evaluator_results import EvaluatorResults
from .exceptions import (
    BackingEntityResolutionError,
    CircularDependencyError,
    DataValidationError,
    MissingDependencyError,
    SensorMappingError,
)
from .formula_preprocessor import FormulaPreprocessor
from .type_definitions import CacheStats, ContextValue, DataProviderCallback, DependencyValidation, EvaluationResult

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
        allow_ha_lookups: bool = False,
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
            allow_ha_lookups: Whether to allow fallback to HA state lookups for backing entities
        """
        self._hass = hass

        # Initialize components
        self._cache = FormulaCache(cache_config)
        self._dependency_parser = DependencyParser(hass)
        self._collection_resolver = CollectionResolver(hass)

        # Initialize configuration objects
        self._circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        self._retry_config = retry_config or RetryConfig()

        # Initialize handler modules
        self._dependency_handler = EvaluatorDependency(hass, data_provider_callback, allow_ha_lookups)
        self._cache_handler = EvaluatorCache(cache_config)
        self._error_handler = EvaluatorErrorHandler(self._circuit_breaker_config, self._retry_config)
        self._formula_preprocessor = FormulaPreprocessor(self._collection_resolver)

        # Initialize handler factory for formula evaluation
        self._handler_factory = HandlerFactory()

        # Initialize sensor-to-backing mapping
        self._sensor_to_backing_mapping: dict[str, str] = {}

        # Initialize phase modules for compiler-like evaluation
        self._variable_resolution_phase = VariableResolutionPhase(self._sensor_to_backing_mapping, data_provider_callback)
        self._dependency_management_phase = DependencyManagementPhase()
        self._context_building_phase = ContextBuildingPhase()
        self._pre_evaluation_phase = PreEvaluationPhase()
        self._sensor_registry_phase = SensorRegistryPhase()

        # Initialize generic dependency manager for universal dependency tracking
        self._generic_dependency_manager = GenericDependencyManager()
        self._generic_dependency_manager.set_sensor_registry_phase(self._sensor_registry_phase)

        # Support for push-based entity registration (new pattern)
        self._registered_integration_entities: set[str] | None = None

        # Store data provider callback for backward compatibility
        self._data_provider_callback = data_provider_callback

        # Store allow_ha_lookups setting
        self._allow_ha_lookups = allow_ha_lookups

        # Set dependencies for context building phase (after all attributes are initialized)
        self._context_building_phase.set_evaluator_dependencies(
            hass, data_provider_callback, self._dependency_handler, self._sensor_to_backing_mapping
        )

        # Set dependencies for pre-evaluation phase
        self._pre_evaluation_phase.set_evaluator_dependencies(
            hass,
            data_provider_callback,
            self._dependency_handler,
            self._cache_handler,
            self._error_handler,
            self._sensor_to_backing_mapping,
            self._allow_ha_lookups,
            self._variable_resolution_phase,
            self._dependency_management_phase,
            self._context_building_phase,
        )

        # Set sensor registry phase for variable resolution
        self._variable_resolution_phase.set_sensor_registry_phase(self._sensor_registry_phase)

        # Set dependency handler for variable resolution
        self._variable_resolution_phase.set_dependency_handler(self._dependency_handler)

        # Set formula preprocessor for collection function resolution
        self._variable_resolution_phase.set_formula_preprocessor(self._formula_preprocessor)

        # Set dependencies for dependency management phase
        self._dependency_management_phase.set_evaluator_dependencies(
            self._dependency_handler,
            self._sensor_to_backing_mapping,
        )

        # Set sensor registry phase for cross-sensor dependency management
        self._dependency_management_phase.set_sensor_registry_phase(self._sensor_registry_phase)

        # CROSS-SENSOR REFERENCE SUPPORT
        # Registry of all sensors and their current values for cross-sensor references
        # This enables sensors to reference other sensors by name (e.g., base_power_sensor)
        # Future: This registry can be extended to support different data types (strings, dates, etc.)
        # Now managed by the SensorRegistryPhase

    @property
    def data_provider_callback(self) -> DataProviderCallback | None:
        """Get the current data provider callback."""
        return self._data_provider_callback

    @data_provider_callback.setter
    def data_provider_callback(self, value: DataProviderCallback | None) -> None:
        """Set the data provider callback and update all dependent components."""
        self._data_provider_callback = value
        self._dependency_handler.data_provider_callback = value

        # Update Variable Resolution Phase (Phase 1) with new data provider for state resolution
        self._variable_resolution_phase.update_data_provider_callback(value)

        # Update context building phase with new callback
        self._context_building_phase.set_evaluator_dependencies(
            self._hass, value, self._dependency_handler, self._sensor_to_backing_mapping
        )

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
        return self.evaluate_formula_with_sensor_config(config, context, None)

    def _perform_pre_evaluation_checks(
        self,
        config: FormulaConfig,
        context: dict[str, ContextValue] | None,
        sensor_config: SensorConfig | None,
        formula_name: str,
    ) -> tuple[EvaluationResult | None, dict[str, ContextValue] | None]:
        """Perform all pre-evaluation checks and return error result if any fail."""
        return self._pre_evaluation_phase.perform_pre_evaluation_checks(config, context, sensor_config, formula_name)

    def evaluate_formula_with_sensor_config(
        self,
        config: FormulaConfig,
        context: dict[str, ContextValue] | None = None,
        sensor_config: SensorConfig | None = None,
        bypass_dependency_management: bool = False,
    ) -> EvaluationResult:
        """Evaluate a formula configuration with enhanced error handling and sensor context."""
        formula_name = config.name or config.id

        try:
            return self._evaluate_formula_core(config, context, sensor_config, bypass_dependency_management, formula_name)
        except ValueError as e:
            return self._handle_value_error(e, formula_name)
        except BackingEntityResolutionError as e:
            return self._handle_backing_entity_error(e, formula_name)
        except (DataValidationError, MissingDependencyError, SensorMappingError, CircularDependencyError):
            # Let these specialized exceptions propagate - they should be raised, not converted to error results
            raise
        except Exception as err:
            return self._error_handler.handle_evaluation_error(err, formula_name)

    def _evaluate_formula_core(
        self,
        config: FormulaConfig,
        context: dict[str, ContextValue] | None,
        sensor_config: SensorConfig | None,
        bypass_dependency_management: bool,
        formula_name: str,
    ) -> EvaluationResult:
        """Core formula evaluation logic without exception handling."""
        # Perform all pre-evaluation checks
        check_result, eval_context = self._perform_pre_evaluation_checks(config, context, sensor_config, formula_name)
        if check_result:
            return check_result

        # Ensure eval_context is not None (should be guaranteed by the helper method)
        if eval_context is None:
            return EvaluatorResults.create_error_result("Failed to build evaluation context", state="unavailable")

        # Use enhanced variable resolution with HA state detection
        resolution_result = self._variable_resolution_phase.resolve_all_references_with_ha_detection(
            config.formula, sensor_config, eval_context, config
        )
        _LOGGER.debug(
            "Evaluator: formula '%s' resolved to '%s' with context: %s",
            config.formula,
            resolution_result.resolved_formula,
            eval_context,
        )

        # Check if HA state was detected during variable resolution
        if resolution_result.has_ha_state and resolution_result.ha_state_value:
            return self._handle_ha_state_detection(resolution_result, formula_name)

        # Check if we need dependency-aware evaluation
        if self._should_use_dependency_management(sensor_config, context, bypass_dependency_management, config):
            # At this point, we know context and sensor_config are not None due to the check above
            # Type checking: these should never be None here due to the guard condition
            if context is None or sensor_config is None:
                return EvaluatorResults.create_error_result("Context or sensor config is None", state="unavailable")
            return self._evaluate_with_dependency_management(config, context, sensor_config)

        # Evaluate the formula normally
        return self._evaluate_formula_normally(config, eval_context, context, sensor_config, formula_name)

    def _handle_ha_state_detection(self, resolution_result: Any, formula_name: str) -> EvaluationResult:
        """Handle HA state detection during variable resolution."""
        _LOGGER.debug(
            "Formula '%s' resolved to HA state '%s' during variable resolution, returning corresponding sensor state",
            formula_name,
            resolution_result.ha_state_value,
        )
        self._error_handler.handle_successful_evaluation(formula_name)
        return EvaluatorResults.create_success_result_with_state(
            resolution_result.ha_state_value,
            value=None,
            unavailable_dependencies=resolution_result.unavailable_dependencies or [],
        )

    def _should_use_dependency_management(
        self,
        sensor_config: SensorConfig | None,
        context: dict[str, ContextValue] | None,
        bypass_dependency_management: bool,
        config: FormulaConfig,
    ) -> bool:
        """Determine if dependency management should be used."""
        if not sensor_config or not context or bypass_dependency_management:
            return False
        return self._needs_dependency_resolution(config, sensor_config)

    def _evaluate_formula_normally(
        self,
        config: FormulaConfig,
        eval_context: dict[str, ContextValue],
        context: dict[str, ContextValue] | None,
        sensor_config: SensorConfig | None,
        formula_name: str,
    ) -> EvaluationResult:
        """Evaluate formula using normal evaluation path."""
        result = self._execute_formula_evaluation(config, eval_context, context, config.id, sensor_config)
        self._error_handler.handle_successful_evaluation(formula_name)
        return self._create_success_result(result)

    def _handle_value_error(self, error: ValueError, formula_name: str) -> EvaluationResult:
        """Handle ValueError exceptions during formula evaluation."""
        # Handle formula evaluation failures due to None values
        if "Formula evaluation failed due to None values" in str(error):
            _LOGGER.warning("Formula '%s': %s", formula_name, str(error))
            self._error_handler.increment_error_count(formula_name)
            return EvaluatorResults.create_success_result_with_state("unknown", value="unknown")
        # Re-raise other ValueError exceptions
        raise error

    def _handle_backing_entity_error(self, error: BackingEntityResolutionError, formula_name: str) -> EvaluationResult:
        """Handle BackingEntityResolutionError exceptions."""
        self._error_handler.increment_error_count(formula_name)
        return EvaluatorResults.create_error_result(str(error), state="unavailable")

    def _create_success_result(self, result: float | str | bool) -> EvaluationResult:
        """Create appropriate success result based on result type."""
        if isinstance(result, (int, float)):
            return EvaluatorResults.create_success_result(float(result))
        # For string/boolean results, use the generic success result
        return EvaluatorResults.create_success_result_with_state("ok", value=result)

    def _extract_and_prepare_dependencies(
        self, config: FormulaConfig, context: dict[str, ContextValue] | None, sensor_config: SensorConfig | None = None
    ) -> tuple[set[str], set[str]]:
        """Extract dependencies and prepare them for evaluation."""
        return self._dependency_management_phase.extract_and_prepare_dependencies(config, context, sensor_config)

    def _handle_dependency_issues(
        self, missing_deps: set[str], unavailable_deps: set[str], unknown_deps: set[str], formula_name: str
    ) -> EvaluationResult | None:
        """Handle missing, unavailable, and unknown dependencies with state reflection."""
        result = self._dependency_management_phase.handle_dependency_issues(
            missing_deps, unavailable_deps, unknown_deps, formula_name
        )

        if result is None:
            return None

        # Convert the phase result to an EvaluationResult
        return self._convert_dependency_result_to_evaluation_result(result)

    def _convert_dependency_result_to_evaluation_result(self, result: dict[str, Any]) -> EvaluationResult:
        """Convert dependency management phase result to EvaluationResult."""
        if "error" in result:
            return EvaluatorResults.create_error_result(
                result["error"], state=result["state"], missing_dependencies=result.get("missing_dependencies")
            )
        return EvaluatorResults.create_success_result_with_state(
            result["state"], unavailable_dependencies=result.get("unavailable_dependencies")
        )

    def _validate_evaluation_context(self, eval_context: dict[str, ContextValue], formula_name: str) -> EvaluationResult | None:
        """Validate that evaluation context has all required variables."""
        result = self._dependency_management_phase.validate_evaluation_context(eval_context, formula_name)

        if result is None:
            return None

        # Convert the phase result to an EvaluationResult and handle error counting
        if "error" in result:
            self._error_handler.increment_error_count(formula_name)
            return EvaluatorResults.create_error_result(result["error"], state=result["state"])
        return EvaluatorResults.create_success_result_with_state(
            result["state"], unavailable_dependencies=result.get("unavailable_dependencies")
        )

    def _needs_dependency_resolution(self, config: FormulaConfig, sensor_config: SensorConfig) -> bool:
        """
        Check if a formula needs dependency-aware evaluation.

        This method determines if the formula contains attribute references that might
        need dependency resolution from other attributes in the same sensor.
        """
        # Check if the formula contains potential attribute references
        # Look for simple identifiers that could be attribute names
        pattern = r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b"

        for match in re.finditer(pattern, config.formula):
            identifier = match.group(1)

            # Skip reserved words
            if is_reserved_word(identifier):
                continue

            # Skip if it looks like an entity ID (contains dot)
            if "." in identifier:
                continue

            # Check if this identifier could be an attribute in the sensor
            # If the sensor has multiple formulas (main + attributes), this could be an attribute reference
            if len(sensor_config.formulas) > 1:
                return True

        return False

    def _evaluate_with_dependency_management(
        self, config: FormulaConfig, context: dict[str, ContextValue], sensor_config: SensorConfig
    ) -> EvaluationResult:
        """
        Evaluate a formula with automatic dependency management.

        This method uses the generic dependency manager to ensure that any attribute
        dependencies are properly resolved before evaluating the current formula.
        """
        try:
            # Build complete evaluation context using dependency manager
            complete_context = self._generic_dependency_manager.build_evaluation_context(
                sensor_config=sensor_config, evaluator=self, base_context=context
            )

            # Now evaluate the formula with the complete context
            formula_name = config.name or config.id

            # Perform pre-evaluation checks with the complete context
            check_result, eval_context = self._perform_pre_evaluation_checks(
                config, complete_context, sensor_config, formula_name
            )
            if check_result:
                return check_result

            # Ensure eval_context is not None
            if eval_context is None:
                return EvaluatorResults.create_error_result("Failed to build evaluation context", state="unavailable")

            # Evaluate the formula with dependency-resolved context
            result = self._execute_formula_evaluation(config, eval_context, complete_context, config.id, sensor_config)

            # Handle success
            self._error_handler.handle_successful_evaluation(formula_name)

            # Convert result to proper EvaluationResult
            if isinstance(result, (int, float)):
                return EvaluatorResults.create_success_result(float(result))
            return EvaluatorResults.create_success_result_with_state("ok", value=result)

        except Exception as e:
            _LOGGER.error("Error in dependency-aware evaluation for formula '%s': %s", config.formula, e)
            # Re-raise MissingDependencyError and other fatal errors
            if isinstance(e, (MissingDependencyError, DataValidationError, SensorMappingError)):
                raise
            # Fall back to normal evaluation for other errors
            return self._fallback_to_normal_evaluation(config, context, sensor_config)

    def fallback_to_normal_evaluation(
        self, config: FormulaConfig, context: dict[str, ContextValue] | None, sensor_config: SensorConfig | None
    ) -> EvaluationResult:
        """Public method to fallback to normal evaluation if dependency management fails."""
        return self._fallback_to_normal_evaluation(config, context, sensor_config)

    def _fallback_to_normal_evaluation(
        self, config: FormulaConfig, context: dict[str, ContextValue] | None, sensor_config: SensorConfig | None
    ) -> EvaluationResult:
        """Fallback to normal evaluation if dependency management fails."""
        formula_name = config.name or config.id

        # Perform all pre-evaluation checks
        check_result, eval_context = self._perform_pre_evaluation_checks(config, context, sensor_config, formula_name)
        if check_result:
            return check_result

        # Ensure eval_context is not None
        if eval_context is None:
            return EvaluatorResults.create_error_result("Failed to build evaluation context", state="unavailable")

        # Evaluate the formula
        result = self._execute_formula_evaluation(config, eval_context, context, config.id, sensor_config)

        # Convert result to proper EvaluationResult
        if isinstance(result, (int, float)):
            return EvaluatorResults.create_success_result(float(result))
        return EvaluatorResults.create_success_result_with_state("ok", value=result)

    def _execute_formula_evaluation(
        self,
        config: FormulaConfig,
        eval_context: dict[str, ContextValue],
        context: dict[str, ContextValue] | None,
        cache_key_id: str,
        sensor_config: SensorConfig | None = None,
    ) -> float | str | bool:
        """Execute the actual formula evaluation with proper multi-phase resolution."""
        # PHASE 1: Clean formula resolution - resolve ALL references to actual values
        resolved_formula = self._resolve_all_references_in_formula(config.formula, sensor_config, eval_context, config)

        # PHASE 2: Determine formula type and delegate to appropriate handler
        # This architecture separates numeric computation from string processing,
        # allowing for future expansion of string manipulation capabilities

        try:
            # Use handler factory to route formula to appropriate handler
            handler = self._handler_factory.get_handler_for_formula(resolved_formula)
            if handler:
                result = handler.evaluate(resolved_formula, eval_context)
            else:
                # Fallback to numeric handler if no specific handler found
                numeric_handler = self._handler_factory.get_handler("numeric")
                if numeric_handler:
                    result = numeric_handler.evaluate(resolved_formula, eval_context)
                else:
                    raise ValueError("No handler available for formula evaluation")

            # Validate result type based on formula context
            is_main_formula = sensor_config and config.id == sensor_config.unique_id
            if is_main_formula and not isinstance(result, (int, float)):
                raise ValueError(f"Main formula result must be numeric, got {type(result).__name__}: {result}")

            # Cache the result (cache handler supports multiple types for future expansion)
            if isinstance(result, (int, float)):
                self._cache_handler.cache_result(config, context, cache_key_id, float(result))

            # Ensure proper type annotation for return
            final_result: float | str | bool = float(result) if isinstance(result, (int, float)) else result

            return final_result

        except (TypeError, ValueError) as e:
            # Handle errors caused by None values or invalid operations
            error_msg = str(e)
            if "None" in error_msg or "unsupported operand" in error_msg:
                # Check if any values in the context are None or "None"
                none_values = [k for k, v in eval_context.items() if v is None or v == "None"]
                if none_values:
                    _LOGGER.warning(
                        "Formula evaluation failed due to None values: %s. Context variables with None: %s", e, none_values
                    )
                    # For main formulas, this should be a fatal error
                    if sensor_config and config.id == sensor_config.unique_id:
                        raise ValueError(
                            f"Main formula evaluation failed: variables {none_values} could not be resolved"
                        ) from e
                    # For attribute formulas, return a failure result
                    return "unknown"

                # Check if the resolved formula contains "None" strings
                if "None" in resolved_formula:
                    _LOGGER.warning("Formula contains unresolved variables: %s", resolved_formula)
                    if sensor_config and config.id == sensor_config.unique_id:
                        raise ValueError(f"Main formula contains unresolved variables: {resolved_formula}") from e
                    return "unknown"

            # Re-raise other errors
            raise

    def _build_evaluation_context(
        self,
        dependencies: set[str],
        context: dict[str, ContextValue] | None = None,
        config: FormulaConfig | None = None,
        sensor_config: SensorConfig | None = None,
        allow_ha_lookups: bool = False,
    ) -> dict[str, ContextValue]:
        """Build evaluation context from dependencies and configuration."""
        return self._context_building_phase.build_evaluation_context(
            dependencies, context, config, sensor_config, allow_ha_lookups
        )

    def _resolve_all_references_in_formula(
        self,
        formula: str,
        sensor_config: SensorConfig | None,
        eval_context: dict[str, ContextValue],
        formula_config: FormulaConfig | None = None,
    ) -> str:
        """
        COMPILER-LIKE APPROACH: Resolve ALL references in formula to actual values.

        This method delegates to the Variable Resolution Phase for complete resolution.
        """
        return self._variable_resolution_phase.resolve_all_references_in_formula(
            formula, sensor_config, eval_context, formula_config
        )

    # Public interface methods
    def get_formula_dependencies(self, formula: str) -> set[str]:
        """Get dependencies for a formula."""
        return self._dependency_handler.get_formula_dependencies(formula)

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
                if not dep.replace(".", "_").replace("-", "_").replace(":", "_").isidentifier():
                    errors.append(f"Invalid variable name: {dep}")

            # Note: We don't require formulas to reference entities - they can use literal values in variables

        except Exception as err:
            errors.append(f"Validation error: {err}")

        return errors

    def validate_dependencies(self, dependencies: set[str]) -> DependencyValidation:
        """Validate dependencies and return validation result."""
        return self._dependency_handler.validate_dependencies(dependencies)

    def get_evaluation_context(
        self, formula_config: FormulaConfig, sensor_config: SensorConfig | None = None
    ) -> dict[str, ContextValue]:
        """Get the evaluation context for a formula configuration."""
        dependencies, _ = self._extract_and_prepare_dependencies(formula_config, None, sensor_config)
        return self._build_evaluation_context(
            dependencies, None, formula_config, sensor_config, allow_ha_lookups=self._allow_ha_lookups
        )

    # Delegate cache operations to handler
    def clear_cache(self, formula_name: str | None = None) -> None:
        """Clear cache for specific formula or all formulas."""
        self._cache_handler.clear_cache(formula_name)

    def get_cache_stats(self) -> CacheStats:
        """Get cache statistics."""
        cache_stats = self._cache_handler.get_cache_stats()
        # Add error counts from the error handler
        cache_stats["error_counts"] = self._error_handler.get_error_counts()
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

    @property
    def allow_ha_lookups(self) -> bool:
        """Get the allow_ha_lookups setting."""
        return self._allow_ha_lookups

    @property
    def dependency_management_phase(self) -> Any:
        """Get the dependency management phase."""
        return self._dependency_management_phase

    def update_allow_ha_lookups(self, allow_ha_lookups: bool) -> None:
        """Update the allow_ha_lookups setting."""
        self._allow_ha_lookups = allow_ha_lookups
        _LOGGER.debug("Updated allow_ha_lookups setting: %s", allow_ha_lookups)

    def update_sensor_to_backing_mapping(self, sensor_to_backing_mapping: dict[str, str]) -> None:
        """Update the sensor-to-backing entity mapping for state token resolution."""
        self._sensor_to_backing_mapping = sensor_to_backing_mapping.copy()

        # Update the Variable Resolution Phase (Phase 1) - this is where state token resolution happens
        self._variable_resolution_phase.update_sensor_to_backing_mapping(
            self._sensor_to_backing_mapping, self._data_provider_callback
        )

        # Update all other phases that depend on this mapping
        self._pre_evaluation_phase.set_evaluator_dependencies(
            self._hass,
            self._data_provider_callback,
            self._dependency_handler,
            self._cache_handler,
            self._error_handler,
            self._sensor_to_backing_mapping,
            self._allow_ha_lookups,
            self._variable_resolution_phase,
            self._dependency_management_phase,
            self._context_building_phase,
        )

        self._context_building_phase.set_evaluator_dependencies(
            self._hass, self._data_provider_callback, self._dependency_handler, self._sensor_to_backing_mapping
        )

        self._dependency_management_phase.set_evaluator_dependencies(
            self._dependency_handler,
            self._sensor_to_backing_mapping,
        )

        _LOGGER.debug("Updated sensor-to-backing mapping: %d mappings", len(sensor_to_backing_mapping))

    # CROSS-SENSOR REFERENCE MANAGEMENT
    def register_sensor(self, sensor_name: str, entity_id: str, initial_value: float | str | bool = 0.0) -> None:
        """
        Register a sensor in the cross-sensor reference registry.

        This method enables cross-sensor references by tracking all sensors and their values.
        Sensors can then reference each other by name (e.g., base_power_sensor).

        Args:
            sensor_name: The unique name of the sensor (e.g., "base_power_sensor")
            entity_id: The Home Assistant entity ID (e.g., "sensor.base_power_sensor")
            initial_value: The initial value for the sensor
        """
        self._sensor_registry_phase.register_sensor(sensor_name, entity_id, initial_value)

    def update_sensor_value(self, sensor_name: str, value: float | str | bool) -> None:
        """
        Update a sensor's value in the cross-sensor reference registry.

        This method is called when a sensor's value changes, enabling other sensors
        to reference the updated value in their formulas.

        Args:
            sensor_name: The unique name of the sensor
            value: The new value for the sensor
        """
        self._sensor_registry_phase.update_sensor_value(sensor_name, value)

    def get_sensor_value(self, sensor_name: str) -> float | str | bool | None:
        """
        Get a sensor's current value from the cross-sensor reference registry.

        This method is used during formula evaluation to resolve cross-sensor references.

        Args:
            sensor_name: The unique name of the sensor

        Returns:
            The current value of the sensor, or None if not found
        """
        return self._sensor_registry_phase.get_sensor_value(sensor_name)

    def unregister_sensor(self, sensor_name: str) -> None:
        """
        Unregister a sensor from the cross-sensor reference registry.

        Args:
            sensor_name: The unique name of the sensor to unregister
        """
        self._sensor_registry_phase.unregister_sensor(sensor_name)

    def get_registered_sensors(self) -> set[str]:
        """
        Get all registered sensor names.

        Returns:
            Set of all registered sensor names
        """
        return self._sensor_registry_phase.get_registered_sensors()
