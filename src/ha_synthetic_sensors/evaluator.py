"""Enhanced formula evaluation for YAML-based synthetic sensors."""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
import traceback
from typing import Any, cast
import uuid

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import STATE_UNKNOWN, HomeAssistant
from homeassistant.helpers.typing import StateType

from .alternate_state_eval import evaluate_formula_alternate
from .alternate_state_processor import AlternateStateProcessor
from .cache import CacheConfig
from .collection_resolver import CollectionResolver
from .config_models import FormulaConfig, SensorConfig
from .constants_alternate import STATE_NONE, STATE_NONE_YAML, identify_alternate_state_value
from .constants_evaluation_results import RESULT_KEY_ERROR, RESULT_KEY_STATE, RESULT_KEY_UNAVAILABLE_DEPENDENCIES
from .constants_formula import is_reserved_word
from .dependency_parser import DependencyParser
from .enhanced_formula_evaluation import EnhancedSimpleEvalHelper
from .evaluation_common import (
    check_dependency_management_conditions,
    handle_evaluation_exception,
    process_alternate_state_result,
)
from .evaluation_context import HierarchicalEvaluationContext
from .evaluation_error_handlers import (
    handle_backing_entity_error as _handle_backing_entity_error_helper,
    handle_value_error as _handle_value_error_helper,
)
from .evaluator_cache import EvaluatorCache
from .evaluator_config import CircuitBreakerConfig, RetryConfig
from .evaluator_config_utils import EvaluatorConfigUtils
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
from .evaluator_utilities import EvaluatorUtilities
from .exceptions import (
    AlternateStateDetected,
    BackingEntityResolutionError,
    CircularDependencyError,
    DataValidationError,
    MissingDependencyError,
    SensorMappingError,
)
from .formula_evaluator_service import FormulaEvaluatorService
from .formula_preprocessor import FormulaPreprocessor
from .hierarchical_context_dict import HierarchicalContextDict
from .type_definitions import CacheStats, DataProviderCallback, DependencyValidation, EvaluationResult, ReferenceValue

_LOGGER = logging.getLogger(__name__)


class FormulaEvaluator(ABC):
    """Abstract base class for formula evaluators."""

    @abstractmethod
    def evaluate_formula(self, config: FormulaConfig, context: HierarchicalContextDict) -> EvaluationResult:
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
        self._dependency_management_phase = DependencyManagementPhase(hass)
        self._context_building_phase = ContextBuildingPhase()
        self._pre_evaluation_phase = PreEvaluationPhase()
        self._sensor_registry_phase = SensorRegistryPhase()

        # Initialize formula processor now that variable resolution phase is available
        self._formula_processor = FormulaProcessor(self._variable_resolution_phase)

        # Initialize generic dependency manager for universal dependency tracking
        self._generic_dependency_manager = GenericDependencyManager()
        self._generic_dependency_manager.set_sensor_registry_phase(self._sensor_registry_phase)

        # Initialize alternate state processor with evaluator injection for proper pipeline processing
        self._alternate_state_processor = AlternateStateProcessor(evaluator=self)

        # Support for push-based entity registration (new pattern)
        self._registered_integration_entities: set[str] | None = None

        # Store data provider callback for backward compatibility
        self._data_provider_callback = data_provider_callback

        # Store the last accumulated evaluation context
        self._last_accumulated_context: HierarchicalContextDict | None = None

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

        # Initialize utilities
        self._utilities = EvaluatorUtilities(hass)
        self._config_utils = EvaluatorConfigUtils(circuit_breaker_config, retry_config)

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

    @property
    def execution_engine(self) -> Any:
        """Get the execution engine."""
        return self._execution_engine

    @property
    def needs_dependency_resolution(self) -> Any:
        """Get the needs dependency resolution method."""
        return self._needs_dependency_resolution

    @property
    def execute_formula_evaluation(self) -> Any:
        """Get the execute formula evaluation method."""
        return self._execute_formula_evaluation

    @property
    def error_handler(self) -> Any:
        """Get the error handler."""
        return self._error_handler

    @property
    def cache_handler(self) -> Any:
        """Get the cache handler."""
        return self._cache_handler

    @property
    def generic_dependency_manager(self) -> Any:
        """Get the generic dependency manager."""
        return self._generic_dependency_manager

    @property
    def perform_pre_evaluation_checks(self) -> Any:
        """Get the perform pre evaluation checks method."""
        return self._perform_pre_evaluation_checks

    def update_integration_entities(self, entity_ids: set[str]) -> None:
        """Update the set of entities that the integration can provide (new push-based pattern)."""
        self._registered_integration_entities = entity_ids.copy()
        self._dependency_handler.update_integration_entities(entity_ids)
        _LOGGER.debug("Updated integration entities: %d entities", len(entity_ids))

    def get_integration_entities(self) -> set[str]:
        """Get the current set of integration entities using the push-based pattern."""
        return self._dependency_handler.get_integration_entities()

    def evaluate_formula(
        self, config: FormulaConfig, context: HierarchicalContextDict | dict[str, Any] | None
    ) -> EvaluationResult:
        """Evaluate a formula configuration with enhanced error handling."""
        # ARCHITECTURE FIX: Ensure proper context is always provided
        if context is None:
            raise ValueError(
                "No evaluation context provided. The evaluator requires a proper HierarchicalContextDict "
                "from the sensor manager to prevent context pollution across evaluations. "
                "This indicates a bug in the evaluation flow where context creation is bypassed."
            )
        elif isinstance(context, dict) and not isinstance(context, HierarchicalContextDict):
            # Create unique context name to prevent pollution across evaluations
            unique_context_name = f"sensor_dict_conversion_{uuid.uuid4().hex[:8]}"
            hierarchical_context = HierarchicalEvaluationContext(unique_context_name)
            hierarchical_dict = HierarchicalContextDict(hierarchical_context)
            for key, value in context.items():
                # Ensure all values are wrapped in ReferenceValue objects per architecture
                if not isinstance(value, ReferenceValue):
                    value = ReferenceValue(reference=key, value=value)
                hierarchical_context.set(key, value)
            context = hierarchical_dict

        # Convert raw context values to ReferenceValue objects for API convenience
        normalized_context = self._normalize_context_values(context)
        return self.evaluate_formula_with_sensor_config(config, normalized_context, None)

    def _normalize_context_values(self, context: HierarchicalContextDict) -> HierarchicalContextDict:
        """Convert raw context values to ReferenceValue objects for API convenience.

        This allows the evaluator API to accept raw Python values while ensuring that
        the internal processing pipeline only deals with ReferenceValue objects.
        """
        # Context should already be hierarchical and properly structured
        # The HierarchicalContextDict enforces ReferenceValue architecture at assignment time
        return context

    def _perform_pre_evaluation_checks(
        self,
        config: FormulaConfig,
        context: HierarchicalContextDict,
        sensor_config: SensorConfig | None,
        formula_name: str,
    ) -> tuple[EvaluationResult | None, HierarchicalContextDict]:
        """Perform all pre-evaluation checks and return error result if any fail."""
        return self._pre_evaluation_phase.perform_pre_evaluation_checks(
            config, context, sensor_config, formula_name, alternate_state_processor_instance=self._alternate_state_processor
        )

    def evaluate_formula_with_sensor_config(
        self,
        config: FormulaConfig,
        context: HierarchicalContextDict | dict[str, Any] | None,
        sensor_config: SensorConfig | None = None,
        bypass_dependency_management: bool = False,
    ) -> EvaluationResult:
        """Evaluate a formula configuration with enhanced error handling and sensor context."""
        # ARCHITECTURE FIX: Ensure proper context is always provided
        if context is None:
            raise ValueError(
                "No evaluation context provided. The evaluator requires a proper HierarchicalContextDict "
                "from the sensor manager to prevent context pollution across evaluations. "
                "This indicates a bug in the evaluation flow where context creation is bypassed."
            )
        elif isinstance(context, dict) and not isinstance(context, HierarchicalContextDict):
            # Create unique context name to prevent pollution across evaluations
            unique_context_name = f"sensor_dict_conversion_{uuid.uuid4().hex[:8]}"
            hierarchical_context = HierarchicalEvaluationContext(unique_context_name)
            hierarchical_dict = HierarchicalContextDict(hierarchical_context)
            for key, value in context.items():
                # Ensure all values are wrapped in ReferenceValue objects per architecture
                if not isinstance(value, ReferenceValue):
                    value = ReferenceValue(reference=key, value=value)
                hierarchical_context.set(key, value)
            context = hierarchical_dict

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
        except AlternateStateDetected as alt_state_err:
            # Process AlternateStateDetected through the alternate state handler (Phase 4)
            # This follows the pipeline flow where alternate states are handled centrally
            raw_result = self._alternate_state_processor.process_evaluation_result(
                alt_state_err.alternate_state_value,  # The alternate state value
                alt_state_err,  # The exception object
                context,
                config,
                sensor_config,
                self._execution_engine.core_evaluator,
                self._variable_resolution_phase.resolve_all_references_in_formula,
            )
            result = EvaluatorResults.create_success_from_result(raw_result)
            return result
        except Exception as err_unknown:
            # Log full exception with traceback to aid debugging of integration tests
            _LOGGER.exception("Unhandled exception during evaluation of formula '%s': %s", formula_name, err_unknown)
            # Also print the traceback to stdout for tests running with -s
            traceback.print_exc()
            result = self._error_handler.handle_evaluation_error(err_unknown, formula_name)
        _LOGGER.debug("evaluate_formula_with_sensor_config result for %s: %s", formula_name, result)
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
        context: HierarchicalContextDict,
        sensor_config: SensorConfig | None,
        bypass_dependency_management: bool,
        formula_name: str,
    ) -> EvaluationResult:
        """Core formula evaluation logic."""
        # Perform all pre-evaluation checks
        check_result, eval_context = self._perform_pre_evaluation_checks(config, context, sensor_config, formula_name)
        if check_result is not None:
            return check_result

        # eval_context is now guaranteed to be non-None since context is required

        # Perform variable resolution
        resolution_result = self._perform_variable_resolution(config, sensor_config, eval_context)

        # Handle HA state detection results
        ha_state_result = self._handle_ha_state_detection(resolution_result, config, eval_context, sensor_config)
        if ha_state_result is not None:
            return ha_state_result

        # Handle early results
        if resolution_result.early_result is not None:
            _LOGGER.debug("Early result detected in variable resolution: %s", resolution_result.early_result)
            return self._process_early_result(resolution_result.early_result, config, eval_context, sensor_config)

        # Choose evaluation strategy based on dependency management needs
        return self._choose_evaluation_strategy(
            config, context, sensor_config, bypass_dependency_management, resolution_result, eval_context, formula_name
        )

    def _perform_variable_resolution(
        self, config: FormulaConfig, sensor_config: SensorConfig | None, eval_context: HierarchicalContextDict
    ) -> Any:
        """Perform variable resolution with HA state detection."""
        try:
            resolution_result = self._variable_resolution_phase.resolve_all_references_with_ha_detection(
                config.formula, sensor_config, eval_context, config
            )
            return resolution_result
        except Exception as e:
            _LOGGER.exception("Exception during variable resolution for formula %s: %s", config.id, e)
            traceback.print_exc()
            raise

    def _handle_ha_state_detection(
        self,
        resolution_result: Any,
        config: FormulaConfig,
        eval_context: HierarchicalContextDict,
        sensor_config: SensorConfig | None,
    ) -> EvaluationResult | None:
        """Handle HA state detection results from variable resolution."""
        if not getattr(resolution_result, "has_ha_state", False):
            return None

        # If an early_result exists, send it to the alternate-state processor
        if getattr(resolution_result, "early_result", None) is not None:
            return self._process_early_result(resolution_result.early_result, config, eval_context, sensor_config)

        # No early_result to process: return a HA-state-preserving result
        ha_state_value = getattr(resolution_result, "ha_state_value", None)
        if ha_state_value is not None:
            return EvaluatorResults.create_success_from_ha_state(
                ha_state_value,
                getattr(resolution_result, "unavailable_dependencies", None),
            )

        # If ha_state_value is None, preserve None for proper alternate state classification
        return EvaluatorResults.create_success_result_with_state(
            STATE_NONE_YAML,  # Use STATE_NONE_YAML instead of STATE_UNKNOWN to preserve None value
            unavailable_dependencies=getattr(resolution_result, "unavailable_dependencies", None),
        )

    def _choose_evaluation_strategy(
        self,
        config: FormulaConfig,
        context: HierarchicalContextDict,
        sensor_config: SensorConfig | None,
        bypass_dependency_management: bool,
        resolution_result: Any,
        eval_context: HierarchicalContextDict,
        formula_name: str,
    ) -> EvaluationResult:
        """Choose between dependency-aware and normal evaluation."""
        if self._should_use_dependency_management(sensor_config, context, bypass_dependency_management, config):
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
            narrowed_sensor_config = cast(SensorConfig, sensor_config)
            return self._evaluate_with_dependency_management(resolved_config, context, narrowed_sensor_config)

        # Evaluate the formula normally
        return self._evaluate_formula_normally(config, eval_context, context, sensor_config, formula_name)

    def _process_early_result(
        self,
        early_result: Any,
        config: FormulaConfig,
        eval_context: HierarchicalContextDict,
        sensor_config: SensorConfig | None,
    ) -> EvaluationResult:
        """Convert early results to EvaluationResult format with potential alternate state handling."""

        # Use the alternate state processor to handle the early result
        # This consolidates all alternate state processing in Phase 4
        # When alternate state processor returns None (no handler found),
        # preserve the None instead of falling back to early_result
        return process_alternate_state_result(
            result=early_result,
            config=config,
            eval_context=eval_context,
            sensor_config=sensor_config,
            core_evaluator=self._execution_engine.core_evaluator,
            alternate_state_processor_instance=self._alternate_state_processor,
            resolve_all_references_in_formula=self._variable_resolution_phase.resolve_all_references_in_formula,
            pre_eval=True,
        )

    def _should_use_dependency_management(
        self,
        sensor_config: SensorConfig | None,
        context: HierarchicalContextDict,
        bypass_dependency_management: bool,
        config: FormulaConfig,
    ) -> bool:
        """Determine if dependency management should be used."""
        if not check_dependency_management_conditions(sensor_config, context, bypass_dependency_management):
            return False
        if sensor_config is None:
            return False
        return self._needs_dependency_resolution(config, sensor_config)

    def _evaluate_formula_normally(
        self,
        config: FormulaConfig,
        eval_context: HierarchicalContextDict,
        context: HierarchicalContextDict,
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
        self, config: FormulaConfig, context: HierarchicalContextDict, sensor_config: SensorConfig | None = None
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

    def _validate_evaluation_context(self, eval_context: HierarchicalContextDict, formula_name: str) -> EvaluationResult | None:
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
        # Use centralized identifier pattern from regex helper
        from .regex_helper import create_identifier_pattern

        pattern = create_identifier_pattern()

        for match in pattern.finditer(config.formula):
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
        self, config: FormulaConfig, context: HierarchicalContextDict, sensor_config: SensorConfig
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
            # Preserve None results as STATE_UNKNOWN via create_success_from_result
            # Convert using the central helper so alternate states and None are handled consistently
            return EvaluatorResults.create_success_from_result(result)

        except Exception as e:
            handle_evaluation_exception(e, config, config.name or config.id)
            # Fall back to normal evaluation for other errors
            return self._fallback_to_normal_evaluation(config, context, sensor_config)

    def fallback_to_normal_evaluation(
        self, config: FormulaConfig, context: HierarchicalContextDict, sensor_config: SensorConfig | None
    ) -> EvaluationResult:
        """Public method to fallback to normal evaluation if dependency management fails."""
        return self._fallback_to_normal_evaluation(config, context, sensor_config)

    def _fallback_to_normal_evaluation(
        self, config: FormulaConfig, context: HierarchicalContextDict, sensor_config: SensorConfig | None
    ) -> EvaluationResult:
        """Fallback to normal evaluation if dependency management fails."""
        formula_name = config.name or config.id

        # Perform all pre-evaluation checks
        check_result, eval_context = self._perform_pre_evaluation_checks(config, context, sensor_config, formula_name)
        if check_result:
            return check_result

        # eval_context is now guaranteed to be non-None since context is required

        # Evaluate the formula
        result = self._execute_formula_evaluation(config, eval_context, context, config.id, sensor_config)

        # Convert result to proper EvaluationResult
        # Normalize all results through shared helper to ensure consistent STATE_OK / STATE_UNKNOWN behavior
        return EvaluatorResults.create_success_from_result(result)

    def _evaluate_alternate_state_handler(
        self,
        alternate_state_value: str,
        config: FormulaConfig,
        context: HierarchicalContextDict,
        sensor_config: SensorConfig | None,
    ) -> Any:
        """Evaluate alternate state handler using the same pipeline as attributes.

        Alternate state handlers are treated exactly like attributes - they inherit the same context
        and go through the standard evaluation pipeline with no special handling. They can have
        their own alternate state handlers, creating recursive evaluation chains.

        The evaluation uses the standard pipeline, but the result value is extracted for compatibility
        with the main evaluation pipeline's _finalize_result method.

        Args:
            alternate_state_value: The alternate state that triggered the handler (e.g., 'unavailable')
            config: Original formula configuration with alternate_state_handler
            context: Current evaluation context (inherited from main evaluation)
            sensor_config: Optional sensor configuration

        Returns:
            Extracted value from evaluation result (for pipeline compatibility)
        """
        if not config.alternate_state_handler:
            return None

        # Get the handler value for this alternate state
        handler_value = None
        if alternate_state_value == STATE_UNAVAILABLE:
            handler_value = config.alternate_state_handler.unavailable
            if handler_value is None:
                handler_value = config.alternate_state_handler.fallback
        elif alternate_state_value == STATE_UNKNOWN:
            handler_value = config.alternate_state_handler.unknown
            if handler_value is None:
                handler_value = config.alternate_state_handler.fallback
        elif alternate_state_value is None or alternate_state_value == STATE_NONE:
            handler_value = config.alternate_state_handler.none
            if handler_value is None:
                handler_value = config.alternate_state_handler.fallback
        else:
            # Try fallback handler
            handler_value = config.alternate_state_handler.fallback

        _LOGGER.debug("Alternate state handler: state=%s, handler_value=%s", alternate_state_value, handler_value)

        if handler_value is None:
            _LOGGER.debug("No handler found for alternate state: %s", alternate_state_value)
            return None

        # Handle literal values (str, int, float, bool)
        if isinstance(handler_value, str | int | float | bool):
            # For string literals, check if they look like formulas
            if isinstance(handler_value, str) and self._looks_like_formula(handler_value):
                # Treat as formula
                alternate_config = FormulaConfig(
                    id=f"{config.id}_alternate_{alternate_state_value}",
                    formula=handler_value,
                    variables={},  # No additional variables for simple formula strings
                )
            else:
                # Return literal value directly
                return handler_value
        else:
            # Handle formula objects {formula: str, variables: dict}
            alternate_config = FormulaConfig(
                id=f"{config.id}_alternate_{alternate_state_value}",
                formula=handler_value["formula"],
                variables=handler_value.get("variables", {}),  # Use get() to handle missing variables key
            )

        # Evaluate using the standard pipeline - exactly like attributes
        # The context is inherited and the evaluator handles everything normally
        result = self.evaluate_formula(alternate_config, context)

        # Extract the value from the evaluation result for compatibility with _finalize_result
        # This is different from attributes which use the full result, but alternate state handlers
        # need to return the actual value to be processed by the main evaluation pipeline
        if isinstance(result, dict) and "value" in result:
            return result["value"]
        return result

    def _looks_like_formula(self, s: str) -> bool:
        """Check if a string looks like a formula expression."""
        from .constants_formula import ALL_OPERATORS

        return any(op in s for op in ALL_OPERATORS)

    def _try_formula_alternate_state_handler(
        self,
        config: FormulaConfig,
        eval_context: HierarchicalContextDict,
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

        candidates = self._get_handler_candidates(config.alternate_state_handler, error)
        if not candidates:
            return None

        return self._execute_handler_candidates(candidates, config, eval_context, sensor_config)

    def _get_handler_candidates(self, handler: Any, error: Exception) -> list[Any]:
        """Get list of handler candidates based on error type and available handlers."""
        error_str = str(error).lower()
        candidates: list[Any] = []

        # Try specific handlers first based on error type
        specific_handler = self._get_specific_handler_for_error(handler, error_str)
        if specific_handler is not None:
            candidates.append(specific_handler)

        # If no specific handler found, try fallback handler
        if not candidates and handler.fallback is not None:
            candidates.append(handler.fallback)

        # Final fallback: try all available handlers in priority order
        if not candidates:
            candidates.extend(self._get_all_available_handlers(handler))

        return candidates

    def _get_specific_handler_for_error(self, handler: Any, error_str: str) -> Any:
        """Get the specific handler that matches the error type."""
        if STATE_UNAVAILABLE in error_str and handler.unavailable is not None:
            return handler.unavailable
        if STATE_UNKNOWN in error_str and handler.unknown is not None:
            return handler.unknown
        if "none" in error_str and handler.none is not None:
            return handler.none
        return None

    def _get_all_available_handlers(self, handler: Any) -> list[Any]:
        """Get all available handlers in priority order."""
        handlers = []
        if handler.none is not None:
            handlers.append(handler.none)
        if handler.unavailable is not None:
            handlers.append(handler.unavailable)
        if handler.unknown is not None:
            handlers.append(handler.unknown)
        return handlers

    def _execute_handler_candidates(
        self,
        candidates: list[Any],
        config: FormulaConfig,
        eval_context: HierarchicalContextDict,
        sensor_config: SensorConfig | None,
    ) -> bool | str | float | int | None:
        """Execute handler candidates until one succeeds."""
        try:
            for handler_formula in candidates:
                result = evaluate_formula_alternate(
                    handler_formula,
                    eval_context,
                    sensor_config,
                    config,
                    self._execution_engine.core_evaluator,
                    self._variable_resolution_phase.resolve_all_references_in_formula,
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
        eval_context: HierarchicalContextDict,
        context: HierarchicalContextDict,
        cache_key_id: str,
        sensor_config: SensorConfig | None = None,
    ) -> float | str | bool | None:
        """Execute the actual formula evaluation with multi-phase resolution and exception handling.

        This method orchestrates the complete evaluation pipeline for a formula, including:
        - Variable resolution and dependency management
        - Context preparation and optimization
        - Formula execution via CoreFormulaEvaluator
        - Alternate state handling and result finalization

        RELATIONSHIP: This method delegates the actual formula evaluation to CoreFormulaEvaluator
        via _execute_with_handler -> FormulaEvaluatorService -> CoreFormulaEvaluator.evaluate_formula
        """

        # PHASE 1: Variable resolution
        resolution_result, resolved_formula = self._resolve_formula_variables(config, sensor_config, eval_context)

        # PHASE 2: Prepare handler context
        handler_context = self._prepare_handler_context(eval_context, resolution_result)

        # PHASE 3: Execute formula with appropriate handler
        try:
            # Note: Metadata function processing is handled in CoreFormulaEvaluator
            # No need to duplicate it here since _execute_with_handler calls CoreFormulaEvaluator

            # Evaluation with raise conditions for alternate states and exception handling
            result = self._execute_with_handler(config, resolved_formula, handler_context, eval_context, sensor_config)

            # Check if evaluation result is an alternate state
            alternate_state = identify_alternate_state_value(result)
            if isinstance(alternate_state, str):
                raise AlternateStateDetected(f"Evaluation returned alternate state: {result}", result, alternate_state)

        except AlternateStateDetected as e:
            # Handle alternate state detection using recursive evaluation
            _LOGGER.debug("AlternateStateDetected for formula %s: %s", config.id, e.alternate_state_value)
            if config.alternate_state_handler:
                result = self._evaluate_alternate_state_handler(e.alternate_state_value, config, handler_context, sensor_config)
                _LOGGER.debug("Formula %s resolved using alternate state handler = %s", config.id, result)
            else:
                # No alternate state handler configured, return the alternate state value
                result = e.alternate_state_value

        # PHASE 4: Validate and finalize result
        final_result = self._finalize_result(result, config, context, cache_key_id, sensor_config)

        # Store the accumulated context for later retrieval
        # CRITICAL FIX: Store reference to original context, not a copy
        # This ensures that modifications during variable resolution are preserved
        return final_result

    def _resolve_formula_variables(
        self, config: FormulaConfig, sensor_config: SensorConfig | None, eval_context: HierarchicalContextDict
    ) -> tuple[VariableResolutionResult, str]:
        """Resolve formula variables and return resolution result and resolved formula."""

        if self._formula_processor is None:
            raise RuntimeError("Formula processor not initialized")
        return self._formula_processor.resolve_formula_variables(config, sensor_config, eval_context)

    def _prepare_handler_context(
        self, eval_context: HierarchicalContextDict, resolution_result: VariableResolutionResult
    ) -> HierarchicalContextDict:
        """Prepare context for formula handlers."""
        if self._formula_processor is None:
            raise RuntimeError("Formula processor not initialized")
        return self._formula_processor.prepare_handler_context(eval_context, resolution_result)

    def _extract_values_for_enhanced_evaluation(self, context: HierarchicalContextDict) -> dict[str, Any]:
        """Extract values from ReferenceValue objects for enhanced SimpleEval evaluation."""
        enhanced_context: dict[str, Any] = {}

        for key, value in context.items():
            if isinstance(value, ReferenceValue):
                raw = value.value
                # Detect HA alternate states using shared helper
                # identify_alternate_state_value() returns a string for matches
                # and False when no alternate state is detected. Respect that
                # contract by checking for a string result rather than None.
                alt = identify_alternate_state_value(raw)
                enhanced_context[key] = alt if isinstance(alt, str) else raw
            else:
                enhanced_context[key] = value

        return enhanced_context

    def _execute_with_handler(
        self,
        config: FormulaConfig,
        resolved_formula: str,
        handler_context: HierarchicalContextDict,
        eval_context: HierarchicalContextDict,
        sensor_config: SensorConfig | None,
    ) -> float | str | bool | None:
        """Execute formula using the shared formula evaluation service.

        This method delegates formula evaluation to the shared FormulaEvaluatorService,
        which in turn uses CoreFormulaEvaluator for the actual evaluation logic.

        RELATIONSHIP: This is the bridge between the pipeline orchestrator (_execute_formula_evaluation)
        and the pure evaluation engine (CoreFormulaEvaluator via FormulaEvaluatorService)
        """
        # Use the shared formula evaluation service
        # Correct argument type in evaluate_formula call
        result = FormulaEvaluatorService.evaluate_formula(
            resolved_formula, config.formula, handler_context, allow_unresolved_states=config.allow_unresolved_states
        )
        return result

    def _finalize_result(
        self,
        result: float | str | bool | None,
        config: FormulaConfig,
        context: HierarchicalContextDict,
        cache_key_id: str,
        sensor_config: SensorConfig | None,
    ) -> float | str | bool | None:
        """Validate result type and cache if appropriate."""
        # Direct return - no post-processing needed
        # None values are preserved through the evaluation pipeline
        return result

    def _build_evaluation_context(
        self,
        dependencies: set[str],
        context: HierarchicalContextDict,
        config: FormulaConfig | None = None,
        sensor_config: SensorConfig | None = None,
    ) -> HierarchicalContextDict:
        """Build evaluation context from dependencies and configuration."""
        return self._context_building_phase.build_evaluation_context(dependencies, context, config, sensor_config)

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
    ) -> HierarchicalContextDict:
        """Get the evaluation context for a formula configuration."""
        # Return the accumulated context from the last evaluation
        if self._last_accumulated_context:
            _LOGGER.info("CONTEXT_RETRIEVED: Returning accumulated context with %d items", len(self._last_accumulated_context))
            return self._last_accumulated_context  # No .copy() - return reference

        # ARCHITECTURE VIOLATION: Should never rebuild context from scratch
        raise RuntimeError(
            "EVALUATOR_VIOLATION: get_evaluation_context called without accumulated context!\n"
            "This violates the 'build context, not start with empty' architecture.\n"
            "Evaluator should always have accumulated context from previous phases."
        )

    # Delegate cache operations to handler
    def clear_cache(self, formula_name: str | None = None) -> None:
        """Clear cache for specific formula or all formulas."""
        self._config_utils.clear_cache(self._cache_handler, formula_name)

    def start_update_cycle(self) -> None:
        """Start a new evaluation update cycle."""
        self._config_utils.start_update_cycle(self._cache_handler)

    def get_last_discovered_entities(self) -> set[str]:
        """Get entities discovered during the last evaluation."""
        return self._variable_resolution_phase.last_discovered_entities

    def end_update_cycle(self) -> None:
        """End current evaluation update cycle."""
        self._config_utils.end_update_cycle(self._cache_handler)

    def get_cache_stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._config_utils.get_cache_stats(self._cache_handler, self._error_handler)

    def clear_compiled_formulas(self) -> None:
        """Clear all compiled formulas from cache."""
        self._config_utils.clear_compiled_formulas(self._enhanced_helper)

    def get_compilation_cache_stats(self) -> dict[str, Any]:
        """Get formula compilation cache statistics."""
        return self._config_utils.get_compilation_cache_stats(_build_compilation_cache_stats, self._enhanced_helper)

    def get_enhanced_evaluation_stats(self) -> dict[str, Any]:
        """Get enhanced evaluation usage statistics."""
        return self._config_utils.get_enhanced_evaluation_stats(_get_enhanced_evaluation_stats, self._enhanced_helper)

    # Configuration methods
    def get_circuit_breaker_config(self) -> CircuitBreakerConfig:
        """Get current circuit breaker configuration."""
        return self._config_utils.get_circuit_breaker_config()

    def get_retry_config(self) -> RetryConfig:
        """Get current retry configuration."""
        return self._config_utils.get_retry_config()

    def update_circuit_breaker_config(self, config: CircuitBreakerConfig) -> None:
        """Update circuit breaker configuration."""
        self._config_utils.update_circuit_breaker_config(config)

    def update_retry_config(self, config: RetryConfig) -> None:
        """Update retry configuration."""
        self._config_utils.update_retry_config(config)

    @property
    def dependency_management_phase(self) -> Any:
        """Get the dependency management phase."""
        return self._dependency_management_phase

    def update_sensor_to_backing_mapping(self, sensor_to_backing_mapping: dict[str, str]) -> None:
        """Update the sensor-to-backing entity mapping for state token resolution."""
        self._sensor_to_backing_mapping = sensor_to_backing_mapping.copy()
        self._utilities.update_sensor_to_backing_mapping(
            sensor_to_backing_mapping,
            self._variable_resolution_phase,
            self._pre_evaluation_phase,
            self._context_building_phase,
            self._dependency_management_phase,
            self._data_provider_callback,
            self._dependency_handler,
            self._cache_handler,
            self._error_handler,
        )

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

    def _evaluate_expression_callback(self, expression: str, context: HierarchicalContextDict) -> StateType:
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
        return self._utilities.evaluate_expression_callback(expression, context, self.evaluate_formula)
