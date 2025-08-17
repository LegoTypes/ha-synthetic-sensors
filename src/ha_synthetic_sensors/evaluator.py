"""Enhanced formula evaluation for YAML-based synthetic sensors."""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
import re
from typing import Any, cast

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import StateType

from .alternate_state_eval import evaluate_formula_alternate
from .cache import CacheConfig
from .collection_resolver import CollectionResolver
from .config_models import FormulaConfig, SensorConfig
from .constants_evaluation_results import (
    RESULT_KEY_ERROR,
    RESULT_KEY_STATE,
    RESULT_KEY_SUCCESS,
    RESULT_KEY_UNAVAILABLE_DEPENDENCIES,
    RESULT_KEY_VALUE,
)
from .constants_formula import is_reserved_word
from .dependency_parser import DependencyParser
from .enhanced_formula_evaluation import EnhancedSimpleEvalHelper
from .evaluation_error_handlers import (
    handle_backing_entity_error as _handle_backing_entity_error_helper,
    handle_value_error as _handle_value_error_helper,
)
from .evaluator_cache import EvaluatorCache
from .evaluator_config import CircuitBreakerConfig, RetryConfig
from .evaluator_dependency import EvaluatorDependency
from .evaluator_error_handler import EvaluatorErrorHandler
from .evaluator_execution import FormulaExecutionEngine
from .evaluator_formula_processor import FormulaProcessor
from .evaluator_handlers import HandlerFactory
from .evaluator_helpers import EvaluatorHelpers
from .evaluator_phases.context_building import ContextBuildingPhase
from .evaluator_phases.dependency_management import DependencyManagementPhase
from .evaluator_phases.dependency_management.generic_dependency_manager import GenericDependencyManager
from .evaluator_phases.pre_evaluation import PreEvaluationPhase
from .evaluator_phases.sensor_registry import SensorRegistryPhase
from .evaluator_phases.variable_resolution import VariableResolutionPhase
from .evaluator_phases.variable_resolution.resolution_types import VariableResolutionResult
from .evaluator_results import EvaluatorResults
from .evaluator_sensor_registry import EvaluatorSensorRegistry
from .evaluator_stats import (
    build_compilation_cache_stats as _build_compilation_cache_stats,
    get_enhanced_evaluation_stats as _get_enhanced_evaluation_stats,
)
from .exceptions import (
    BackingEntityResolutionError,
    CircularDependencyError,
    DataValidationError,
    MissingDependencyError,
    SensorMappingError,
)
from .formula_evaluator_service import FormulaEvaluatorService
from .formula_preprocessor import FormulaPreprocessor
from .reference_value_manager import ReferenceValueManager
from .type_definitions import (
    CacheStats,
    ContextValue,
    DataProviderCallback,
    DependencyValidation,
    EvaluationResult,
    ReferenceValue,
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
                                   Variables automatically try backing entities first, then HA fallback.
        """
        if hass is None:
            raise ValueError("Evaluator requires a valid Home Assistant instance, got None")
        self._hass = hass

        # Initialize components
        self._dependency_parser = DependencyParser(hass)
        self._collection_resolver = CollectionResolver(hass)

        # Initialize configuration objects
        self._circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        self._retry_config = retry_config or RetryConfig()

        # Initialize handler modules
        self._dependency_handler = EvaluatorDependency(hass, data_provider_callback)
        self._cache_handler = EvaluatorCache(cache_config)
        self._error_handler = EvaluatorErrorHandler(self._circuit_breaker_config, self._retry_config)
        self._formula_preprocessor = FormulaPreprocessor(self._collection_resolver, hass)

        # Initialize handler factory for formula evaluation with expression evaluator callback
        self._handler_factory = HandlerFactory(expression_evaluator=self._evaluate_expression_callback, hass=hass)

        # Initialize enhanced routing (clean slate design - always enabled)
        self._enhanced_helper = EnhancedSimpleEvalHelper()

        self._execution_engine = FormulaExecutionEngine(
            self._handler_factory,
            self._error_handler,
            self._enhanced_helper,
        )

        # Initialize the shared formula evaluation service
        FormulaEvaluatorService.initialize(self._execution_engine._core_evaluator)
        FormulaEvaluatorService.set_evaluator(self)
        self._sensor_registry = EvaluatorSensorRegistry()

        # Initialize formula processor
        # Note: This will be properly initialized after variable resolution phase is created
        self._formula_processor: FormulaProcessor | None = None

        # Initialize sensor-to-backing mapping
        self._sensor_to_backing_mapping: dict[str, str] = {}

        # Initialize phase modules for compiler-like evaluation
        self._variable_resolution_phase = VariableResolutionPhase(self._sensor_to_backing_mapping, data_provider_callback, hass)
        self._dependency_management_phase = DependencyManagementPhase()
        self._context_building_phase = ContextBuildingPhase()
        self._pre_evaluation_phase = PreEvaluationPhase()
        self._sensor_registry_phase = SensorRegistryPhase()

        # Initialize formula processor now that variable resolution phase is available
        self._formula_processor = FormulaProcessor(self._variable_resolution_phase)

        # Initialize generic dependency manager for universal dependency tracking
        self._generic_dependency_manager = GenericDependencyManager()
        self._generic_dependency_manager.set_sensor_registry_phase(self._sensor_registry_phase)

        # Support for push-based entity registration (new pattern)
        self._registered_integration_entities: set[str] | None = None

        # Store data provider callback for backward compatibility
        self._data_provider_callback = data_provider_callback

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
        # Convert raw context values to ReferenceValue objects for API convenience
        normalized_context = self._normalize_context_values(context)
        return self.evaluate_formula_with_sensor_config(config, normalized_context, None)

    def _normalize_context_values(self, context: dict[str, ContextValue] | None) -> dict[str, ContextValue] | None:
        """Convert raw context values to ReferenceValue objects for API convenience.

        This allows the evaluator API to accept raw Python values while ensuring that
        the internal processing pipeline only deals with ReferenceValue objects.
        """
        if context is None:
            return None

        normalized_context: dict[str, ContextValue] = {}

        for key, value in context.items():
            if isinstance(value, ReferenceValue):
                # Already a ReferenceValue - use directly
                normalized_context[key] = value
            else:
                # Convert raw value to ReferenceValue for internal consistency
                ReferenceValueManager.set_variable_with_reference_value(normalized_context, key, key, value)

        return normalized_context

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

        result: EvaluationResult
        try:
            result = self._evaluate_formula_core(config, context, sensor_config, bypass_dependency_management, formula_name)
        except (
            ValueError,
            BackingEntityResolutionError,
            DataValidationError,
            MissingDependencyError,
            SensorMappingError,
            CircularDependencyError,
        ) as known_err:
            result = self._handle_known_errors(known_err, formula_name)
        except Exception as err_unknown:
            result = self._error_handler.handle_evaluation_error(err_unknown, formula_name)
        return result

    def _handle_known_errors(self, err: Exception, formula_name: str) -> EvaluationResult:
        """Map known exceptions to standardized evaluation results."""
        if isinstance(err, ValueError):
            return _handle_value_error_helper(err, formula_name, self._error_handler)
        if isinstance(err, BackingEntityResolutionError):
            return _handle_backing_entity_error_helper(err, formula_name, self._error_handler)
        if isinstance(err, DataValidationError | MissingDependencyError | SensorMappingError | CircularDependencyError):
            self._error_handler.increment_error_count(formula_name)
            raise err
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
        if check_result is not None:
            return check_result

        # Ensure eval_context is not None (should be guaranteed by the helper method)
        if eval_context is None:
            return EvaluatorResults.create_error_result("Failed to build evaluation context", state="unknown")

        # Use enhanced variable resolution with HA state detection
        resolution_result = self._variable_resolution_phase.resolve_all_references_with_ha_detection(
            config.formula, sensor_config, eval_context, config
        )

        # Check if HA state was detected during variable resolution
        ha_state = resolution_result.ha_state_value if resolution_result.has_ha_state else None
        if ha_state is not None:
            if config.alternate_state_handler:
                fake_err = ValueError(str(ha_state))
                alt_value = self._try_formula_alternate_state_handler(config, eval_context, sensor_config, fake_err)
                if alt_value is not None:
                    normalized = EvaluatorHelpers.process_evaluation_result(alt_value)
                    return EvaluatorResults.create_success_result_with_state("ok", value=normalized)
            return self._handle_ha_state_detection(resolution_result, formula_name)

        # Check if we need dependency-aware evaluation
        if self._should_use_dependency_management(sensor_config, context, bypass_dependency_management, config):
            # At this point, we know context and sensor_config are not None due to the check above
            # Type checking: these should never be None here due to the guard condition
            # Create a new config with the resolved formula to avoid double resolution
            resolved_config = FormulaConfig(
                id=config.id,
                name=config.name,
                formula=resolution_result.resolved_formula,
                variables=config.variables,
                metadata=config.metadata,
                attributes=config.attributes,
                dependencies=config.dependencies,
                alternate_state_handler=config.alternate_state_handler,
            )
            # Mypy narrowing: guarded by _should_use_dependency_management, so both are non-None here
            narrowed_context = cast(dict[str, ContextValue], context)
            narrowed_sensor_config = cast(SensorConfig, sensor_config)
            return self._evaluate_with_dependency_management(resolved_config, narrowed_context, narrowed_sensor_config)

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
        return EvaluatorResults.create_success_from_ha_state(
            resolution_result.ha_state_value, resolution_result.unavailable_dependencies or []
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
        result_value = self._execute_formula_evaluation(config, eval_context, context, config.id, sensor_config)
        self._error_handler.handle_successful_evaluation(formula_name)

        # Cache the successful result
        if isinstance(result_value, float | int):
            self._cache_handler.cache_result(config, eval_context, config.id, float(result_value))

        return EvaluatorResults.create_success_from_result(result_value)

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
        return EvaluatorResults.from_dependency_phase_result(result)

    def _validate_evaluation_context(self, eval_context: dict[str, ContextValue], formula_name: str) -> EvaluationResult | None:
        """Validate that evaluation context has all required variables."""
        result = self._dependency_management_phase.validate_evaluation_context(eval_context, formula_name)

        if result is None:
            return None

        # Convert the phase result to an EvaluationResult and handle error counting
        if RESULT_KEY_ERROR in result:
            self._error_handler.increment_error_count(formula_name)
            return EvaluatorResults.create_error_result(result[RESULT_KEY_ERROR], state=result[RESULT_KEY_STATE])
        return EvaluatorResults.create_success_result_with_state(
            result[RESULT_KEY_STATE], unavailable_dependencies=result.get(RESULT_KEY_UNAVAILABLE_DEPENDENCIES)
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
                return EvaluatorResults.create_error_result("Failed to build evaluation context", state="unknown")

            # Evaluate the formula with dependency-resolved context
            result = self._execute_formula_evaluation(config, eval_context, complete_context, config.id, sensor_config)

            # Handle success
            self._error_handler.handle_successful_evaluation(formula_name)

            # Convert result to proper EvaluationResult
            if isinstance(result, int | float):
                return EvaluatorResults.create_success_result(float(result))
            return EvaluatorResults.create_success_result_with_state("ok", value=result)

        except Exception as e:
            _LOGGER.error("Error in dependency-aware evaluation for formula '%s': %s", config.formula, e)
            # Re-raise MissingDependencyError and other fatal errors
            if isinstance(e, MissingDependencyError | DataValidationError | SensorMappingError):
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
            return EvaluatorResults.create_error_result("Failed to build evaluation context", state="unknown")

        # Evaluate the formula
        result = self._execute_formula_evaluation(config, eval_context, context, config.id, sensor_config)

        # Convert result to proper EvaluationResult
        if isinstance(result, int | float):
            return EvaluatorResults.create_success_result(float(result))
        return EvaluatorResults.create_success_result_with_state("ok", value=result)

    def _try_formula_alternate_state_handler(
        self,
        config: FormulaConfig,
        eval_context: dict[str, ContextValue],
        sensor_config: SensorConfig | None,
        error: Exception,
    ) -> bool | str | float | int | None:
        """Try to resolve a formula using its alternate state handler.

        Args:
            config: Formula configuration with potential alternate state handler
            eval_context: Current evaluation context
            sensor_config: Optional sensor configuration for context
            error: The exception that occurred during main formula evaluation

        Returns:
            Resolved value from exception handler, or None if no handler or handler failed
        """
        if not config.alternate_state_handler:
            return None

        # Determine which exception handler(s) to try. Prefer type-specific, then fallback to both.
        error_str = str(error).lower()
        candidates: list[Any] = []
        if "unavailable" in error_str and config.alternate_state_handler.unavailable is not None:
            candidates.append(config.alternate_state_handler.unavailable)
        if "unknown" in error_str and config.alternate_state_handler.unknown is not None:
            candidates.append(config.alternate_state_handler.unknown)
        # Fallback ordering if error type not identifiable
        if not candidates:
            if config.alternate_state_handler.unavailable is not None:
                candidates.append(config.alternate_state_handler.unavailable)
            if config.alternate_state_handler.unknown is not None:
                candidates.append(config.alternate_state_handler.unknown)
        if not candidates:
            return None

        try:
            for handler_formula in candidates:
                result = evaluate_formula_alternate(
                    handler_formula,
                    eval_context,
                    sensor_config,
                    config,
                    self._execution_engine.core_evaluator,
                    self._resolve_all_references_in_formula,
                )
                if result is not None:
                    _LOGGER.debug("Resolved formula %s using exception handler: %s", config.id, result)
                    return self._convert_handler_result(result)
            return None

        except Exception as handler_err:
            _LOGGER.debug("Exception handler for formula %s also failed: %s", config.id, handler_err)
            return None

    def _convert_handler_result(self, result: Any) -> bool | str | float | int | None:
        """Convert exception handler result to appropriate type."""
        return EvaluatorHelpers.process_evaluation_result(result)

    def _execute_formula_evaluation(
        self,
        config: FormulaConfig,
        eval_context: dict[str, ContextValue],
        context: dict[str, ContextValue] | None,
        cache_key_id: str,
        sensor_config: SensorConfig | None = None,
    ) -> float | str | bool | None:
        """Execute the actual formula evaluation with proper multi-phase resolution and exception handling."""
        # PHASE 1: Variable resolution
        resolution_result, resolved_formula = self._resolve_formula_variables(config, sensor_config, eval_context)

        # PHASE 2: Prepare handler context
        handler_context = self._prepare_handler_context(eval_context, resolution_result)

        # PHASE 3: Execute formula with appropriate handler
        result = self._execute_with_handler(config, resolved_formula, handler_context, eval_context, sensor_config)

        # PHASE 4: Validate and finalize result
        return self._finalize_result(result, config, context, cache_key_id, sensor_config)

    def _resolve_formula_variables(
        self, config: FormulaConfig, sensor_config: SensorConfig | None, eval_context: dict[str, ContextValue]
    ) -> tuple[VariableResolutionResult, str]:
        """Resolve formula variables and return resolution result and resolved formula."""
        if self._formula_processor is None:
            raise RuntimeError("Formula processor not initialized")
        return self._formula_processor.resolve_formula_variables(config, sensor_config, eval_context)

    def _prepare_handler_context(
        self, eval_context: dict[str, ContextValue], resolution_result: VariableResolutionResult
    ) -> dict[str, ContextValue]:
        """Prepare context for formula handlers."""
        if self._formula_processor is None:
            raise RuntimeError("Formula processor not initialized")
        return self._formula_processor.prepare_handler_context(eval_context, resolution_result)

    def _extract_values_for_enhanced_evaluation(self, context: dict[str, ContextValue]) -> dict[str, Any]:
        """Extract values from ReferenceValue objects for enhanced SimpleEval evaluation."""
        # Use public interface via temporary execution (avoid protected access)
        enhanced_context: dict[str, Any] = {}
        for key, value in context.items():
            if isinstance(value, ReferenceValue):
                enhanced_context[key] = EvaluatorHelpers.process_evaluation_result(value.value)
            else:
                enhanced_context[key] = value
        return enhanced_context

    def _execute_with_handler(
        self,
        config: FormulaConfig,
        resolved_formula: str,
        handler_context: dict[str, ContextValue],
        eval_context: dict[str, ContextValue],
        sensor_config: SensorConfig | None,
    ) -> float | str | bool | None:
        """Execute formula using the shared formula evaluation service."""
        try:
            # Use the shared formula evaluation service
            result = FormulaEvaluatorService.evaluate_formula(resolved_formula, config.formula, handler_context)

            # Check if we need to use alternate state handler
            # CRITICAL FIX: Check for None in addition to STATE_UNKNOWN and STATE_UNAVAILABLE
            # This ensures that None values (which indicate missing/unavailable data) properly trigger
            # alternate state handlers, preventing ValueError for numeric sensors that expect None or numeric values.
            if (result is None or result in (STATE_UNKNOWN, STATE_UNAVAILABLE)) and config.alternate_state_handler:
                # Create a fake error to trigger alternate handlers for the specific state
                # CRITICAL FIX: Handle None results gracefully in error creation
                # This prevents errors when creating fake errors for None values that trigger alternate handlers.
                fake_err = ValueError(str(result) if result is not None else "None")
                exception_result = self._try_formula_alternate_state_handler(config, eval_context, sensor_config, fake_err)

                if exception_result is not None:
                    _LOGGER.debug(
                        "Formula %s resolved using alternate handler for %s = %s", config.id, result, exception_result
                    )
                    return exception_result

            return result
        except Exception as err:
            # Exception handler for compatibility (but clean slate should not need this)
            exception_result = self._try_formula_alternate_state_handler(config, eval_context, sensor_config, err)

            if exception_result is not None:
                _LOGGER.debug("Formula %s resolved using exception handler = %s", config.id, exception_result)
                return exception_result
            # Re-raise original error - clean slate should be deterministic
            raise err

    def _finalize_result(
        self,
        result: float | str | bool | None,
        config: FormulaConfig,
        context: dict[str, ContextValue] | None,
        cache_key_id: str,
        sensor_config: SensorConfig | None,
    ) -> float | str | bool | None:
        """Validate result type and cache if appropriate."""
        if self._formula_processor is None:
            raise RuntimeError("Formula processor not initialized")
        return self._formula_processor.finalize_result(result, config, context, cache_key_id, sensor_config)

    def _build_evaluation_context(
        self,
        dependencies: set[str],
        context: dict[str, ContextValue] | None = None,
        config: FormulaConfig | None = None,
        sensor_config: SensorConfig | None = None,
    ) -> dict[str, ContextValue]:
        """Build evaluation context from dependencies and configuration."""
        return self._context_building_phase.build_evaluation_context(dependencies, context, config, sensor_config)

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
        return EvaluatorHelpers.validate_formula_syntax(formula, self._dependency_handler)

    def validate_dependencies(self, dependencies: set[str]) -> DependencyValidation:
        """Validate dependencies and return validation result."""
        return self._dependency_handler.validate_dependencies(dependencies)

    def get_evaluation_context(
        self, formula_config: FormulaConfig, sensor_config: SensorConfig | None = None
    ) -> dict[str, ContextValue]:
        """Get the evaluation context for a formula configuration."""
        dependencies, _ = self._extract_and_prepare_dependencies(formula_config, None, sensor_config)
        return self._build_evaluation_context(dependencies, None, formula_config, sensor_config)

    # Delegate cache operations to handler
    def clear_cache(self, formula_name: str | None = None) -> None:
        """Clear cache for specific formula or all formulas."""
        self._cache_handler.clear_cache(formula_name)

    def start_update_cycle(self) -> None:
        """Start a new evaluation update cycle."""
        self._cache_handler.start_update_cycle()

    def end_update_cycle(self) -> None:
        """End current evaluation update cycle."""
        self._cache_handler.end_update_cycle()

    def get_cache_stats(self) -> CacheStats:
        """Get cache statistics."""
        cache_stats = self._cache_handler.get_cache_stats()
        # Add error counts from the error handler
        cache_stats["error_counts"] = self._error_handler.get_error_counts()
        return cache_stats

    def clear_compiled_formulas(self) -> None:
        """Clear all compiled formulas from the formula compilation cache.

        This should be called when formulas change or during configuration reload
        to ensure that formula modifications take effect.
        """
        # Clear compiled formulas in enhanced helper (99% of formulas)
        if hasattr(self._enhanced_helper, "clear_compiled_formulas"):
            self._enhanced_helper.clear_compiled_formulas()

        # Clear compiled formulas in numeric handler (specialized cases)
        numeric_handler = self._handler_factory.get_handler("numeric")
        if numeric_handler is not None and hasattr(numeric_handler, "clear_compiled_formulas"):
            numeric_handler.clear_compiled_formulas()

    def get_compilation_cache_stats(self) -> dict[str, Any]:
        """Get formula compilation cache statistics.

        Returns:
            Dictionary with compilation cache statistics from enhanced helper and specialized handlers
        """
        numeric_handler = self._handler_factory.get_handler("numeric")
        return _build_compilation_cache_stats(self._enhanced_helper, numeric_handler)

    def get_enhanced_evaluation_stats(self) -> dict[str, Any]:
        """Get enhanced evaluation usage statistics.

        Returns:
            Dictionary with enhanced evaluation usage and cache statistics
        """
        return _get_enhanced_evaluation_stats(self._enhanced_helper)

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
    def dependency_management_phase(self) -> Any:
        """Get the dependency management phase."""
        return self._dependency_management_phase

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
        """Register a sensor in the cross-sensor reference registry."""
        self._sensor_registry.register_sensor(sensor_name, entity_id, initial_value)
        self._sensor_registry_phase.register_sensor(sensor_name, entity_id, initial_value)

    def update_sensor_value(self, sensor_name: str, value: float | str | bool) -> None:
        """Update a sensor's value in the cross-sensor reference registry."""
        self._sensor_registry.update_sensor_value(sensor_name, value)
        self._sensor_registry_phase.update_sensor_value(sensor_name, value)

    def get_sensor_value(self, sensor_name: str) -> float | str | bool | None:
        """Get a sensor's current value from the cross-sensor reference registry."""
        return self._sensor_registry.get_sensor_value(sensor_name)

    def unregister_sensor(self, sensor_name: str) -> None:
        """Unregister a sensor from the cross-sensor reference registry."""
        self._sensor_registry.unregister_sensor(sensor_name)
        self._sensor_registry_phase.unregister_sensor(sensor_name)

    def get_registered_sensors(self) -> set[str]:
        """Get all registered sensor names."""
        return self._sensor_registry.get_registered_sensors()

    def _evaluate_expression_callback(self, expression: str, context: dict[str, ContextValue] | None = None) -> ContextValue:
        """
        Expression evaluator callback for handlers that need to delegate complex expressions.

        This allows handlers like DateHandler to delegate complex expression evaluation
        back to the main evaluator while maintaining separation of concerns.

        Args:
            expression: The expression to evaluate
            context: Variable context for evaluation

        Returns:
            The evaluated result
        """
        # Create a temporary FormulaConfig for the expression
        temp_config = FormulaConfig(id=f"temp_expression_{hash(expression)}", name="Temporary Expression", formula=expression)

        # Evaluate the expression using the main evaluation pipeline
        result = self.evaluate_formula(temp_config, context)

        result_dict = cast(dict[str, Any], result)
        if result_dict[RESULT_KEY_SUCCESS]:
            return cast(StateType, result_dict[RESULT_KEY_VALUE])
        raise ValueError(f"Failed to evaluate expression '{expression}': {result.get('error', 'Unknown error')}")
