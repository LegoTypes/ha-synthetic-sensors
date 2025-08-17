"""Pre-Evaluation Processing Phase for synthetic sensor formula evaluation."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from ...config_models import FormulaConfig, SensorConfig
from ...constants_evaluation_results import (
    RESULT_KEY_ERROR,
    RESULT_KEY_MISSING_DEPENDENCIES,
    RESULT_KEY_STATE,
    RESULT_KEY_UNAVAILABLE_DEPENDENCIES,
)
from ...evaluator_cache import EvaluatorCache
from ...evaluator_dependency import EvaluatorDependency
from ...evaluator_error_handler import EvaluatorErrorHandler
from ...evaluator_phases.context_building import ContextBuildingPhase
from ...evaluator_phases.dependency_management import DependencyManagementPhase
from ...evaluator_phases.variable_resolution import VariableResolutionPhase
from ...evaluator_results import EvaluatorResults
from ...type_definitions import ContextValue, DataProviderCallback, EvaluationResult
from .circular_reference_validator import CircularReferenceValidator

_LOGGER = logging.getLogger(__name__)


class PreEvaluationPhase:
    """Pre-Evaluation Processing Phase for synthetic sensor formula evaluation.

    This phase handles all pre-evaluation checks and validation before formula execution,
    including circuit breaker management, cache validation, state token resolution,
    and dependency validation.

    The phase implements the new backing entity behavior rules:
    - Fatal errors: No mapping exists for backing entity
    - Transient conditions: Mapping exists but value is None (treated as Unknown)
    """

    def __init__(self) -> None:
        """Initialize the pre-evaluation phase."""
        # Dependencies will be set by the evaluator
        self._hass: HomeAssistant | None = None
        self._data_provider_callback: DataProviderCallback | None = None
        self._dependency_handler: EvaluatorDependency | None = None
        self._cache_handler: EvaluatorCache | None = None
        self._error_handler: EvaluatorErrorHandler | None = None
        self._sensor_to_backing_mapping: dict[str, str] | None = None

        # Phase dependencies
        self._variable_resolution_phase: VariableResolutionPhase | None = None
        self._dependency_management_phase: DependencyManagementPhase | None = None
        self._context_building_phase: ContextBuildingPhase | None = None

        # Validation components
        self._circular_reference_validator = CircularReferenceValidator()

    def set_evaluator_dependencies(
        self,
        hass: HomeAssistant,
        data_provider_callback: DataProviderCallback | None,
        dependency_handler: EvaluatorDependency,
        cache_handler: EvaluatorCache,
        error_handler: EvaluatorErrorHandler,
        sensor_to_backing_mapping: dict[str, str],
        variable_resolution_phase: VariableResolutionPhase,
        dependency_management_phase: DependencyManagementPhase,
        context_building_phase: ContextBuildingPhase,
    ) -> None:
        """Set evaluator dependencies for pre-evaluation processing."""
        self._hass = hass
        self._data_provider_callback = data_provider_callback
        self._dependency_handler = dependency_handler
        self._cache_handler = cache_handler
        self._error_handler = error_handler
        self._sensor_to_backing_mapping = sensor_to_backing_mapping
        self._variable_resolution_phase = variable_resolution_phase
        self._dependency_management_phase = dependency_management_phase
        self._context_building_phase = context_building_phase

    def perform_pre_evaluation_checks(
        self,
        config: FormulaConfig,
        context: dict[str, ContextValue] | None,
        sensor_config: SensorConfig | None,
        formula_name: str,
    ) -> tuple[EvaluationResult | None, dict[str, ContextValue] | None]:
        """Perform all pre-evaluation checks and return error result if any fail.

        Args:
            config: Formula configuration to evaluate
            context: Optional context variables
            sensor_config: Optional sensor configuration
            formula_name: Name of the formula for error reporting

        Returns:
            Tuple of (error_result, eval_context) where error_result is None if checks pass
        """
        if not all([self._error_handler, self._cache_handler, self._dependency_handler]):
            raise RuntimeError("Pre-evaluation phase dependencies not set")

        # Step 0: Validate for circular references (must be first - before any resolution attempts)
        # Note: CircularDependencyError will propagate up as a fatal error
        self._circular_reference_validator.validate_formula_config(config, sensor_config)

        # Step 1: Check circuit breaker
        if self._error_handler and self._error_handler.should_skip_evaluation(formula_name):
            return (
                EvaluatorResults.create_error_result(f"Skipping formula '{formula_name}' due to repeated errors"),
                None,
            )

        # Step 2: Check cache
        if self._cache_handler:
            cache_result = self._cache_handler.check_cache(config, context, config.id)
            if cache_result:
                return cache_result, None

        # Step 3: Validate state token resolution (if formula contains 'state')
        if "state" in config.formula and sensor_config:
            state_token_result = self._validate_state_token_resolution(sensor_config, config)
            if state_token_result:
                return state_token_result, None

        # Step 4: Process dependencies and build context
        return self._process_dependencies_and_build_context(config, context, sensor_config, formula_name)

    def _process_dependencies_and_build_context(
        self,
        config: FormulaConfig,
        context: dict[str, ContextValue] | None,
        sensor_config: SensorConfig | None,
        formula_name: str,
    ) -> tuple[EvaluationResult | None, dict[str, ContextValue] | None]:
        """Process dependencies and build evaluation context."""
        # Extract and validate dependencies
        if not (self._dependency_management_phase and self._dependency_handler):
            return None, {}

        dependencies, collection_pattern_entities = self._dependency_management_phase.extract_and_prepare_dependencies(
            config, context, sensor_config
        )
        missing_deps, unavailable_deps, unknown_deps = self._dependency_handler.check_dependencies(
            dependencies, context, collection_pattern_entities
        )

        # Handle dependency issues
        dependency_result = self._handle_dependency_issues(missing_deps, unavailable_deps, unknown_deps, formula_name)
        if dependency_result:
            return dependency_result, None

        # PHASE 1: Variable Resolution - Config variables will be resolved in context building phase
        # with correct priority order (context > config variables)

        # PHASE 3: Context Building - Build evaluation context with resolved variables
        if not self._context_building_phase:
            return None, {}

        final_context = self._context_building_phase.build_evaluation_context(dependencies, context, config, sensor_config)

        context_result = self._validate_evaluation_context(final_context, formula_name)
        if context_result:
            return context_result, None

        # Return the built evaluation context with resolved variables
        return None, final_context

    def _validate_state_token_resolution(self, sensor_config: SensorConfig, config: FormulaConfig) -> EvaluationResult | None:
        """Validate that state token can be resolved for the given sensor configuration.

        Implements the new backing entity behavior rules:
        - Fatal errors: No mapping exists for backing entity and previous state cannot be resolved in HA
        - Transient conditions: Mapping exists but value is None (treated as Unknown)
        """
        if not sensor_config:
            return EvaluatorResults.create_error_result("State token requires sensor configuration", state="unavailable")

        # Check if this is an attribute formula (has underscore in ID and not the main formula)
        is_attribute_formula = "_" in config.id and config.id != sensor_config.unique_id

        # Only validate backing entity for main formulas, not attributes
        # Attributes get their state token from context (main sensor result)
        if not is_attribute_formula:
            # For main formulas, state token resolution follows this priority:
            # 1. Explicit backing entity mapping (if exists)
            # 2. Sensor's own HA state (if sensor has entity_id)
            # 3. Previous calculated value (for recursive calculations)
            backing_entity_id = None
            if self._sensor_to_backing_mapping is not None:
                backing_entity_id = self._sensor_to_backing_mapping.get(sensor_config.unique_id)

            if backing_entity_id:
                # This sensor has explicit backing entity mapping - validate it's registered
                if self._dependency_handler and hasattr(self._dependency_handler, "get_integration_entities"):
                    integration_entities = self._dependency_handler.get_integration_entities()
                    if integration_entities and backing_entity_id not in integration_entities:
                        return EvaluatorResults.create_error_result(
                            f"Backing entity '{backing_entity_id}' for sensor '{sensor_config.unique_id}' is not registered with integration",
                            state="unavailable",
                        )
                return None
            if sensor_config.entity_id:
                # No explicit backing entity mapping, but sensor has entity_id
                # State token will fall back to sensor's own HA state - this is valid
                return None
            # No backing entity mapping and no entity_id - this is self-reference/recursive calculation
            # The state token will resolve to the sensor's previous calculated value
            return None

        return None

    def _handle_dependency_issues(
        self, missing_deps: set[str], unavailable_deps: set[str], unknown_deps: set[str], formula_name: str
    ) -> EvaluationResult | None:
        """Handle missing, unavailable, and unknown dependencies with state reflection."""
        if not self._dependency_management_phase:
            return None

        result = self._dependency_management_phase.handle_dependency_issues(
            missing_deps, unavailable_deps, unknown_deps, formula_name
        )

        if result is None:
            return None

        # Convert the phase result to an EvaluationResult
        return self._convert_dependency_result_to_evaluation_result(result, formula_name)

    def _convert_dependency_result_to_evaluation_result(self, result: dict[str, Any], formula_name: str) -> EvaluationResult:
        """Convert dependency management phase result to EvaluationResult."""
        if RESULT_KEY_ERROR in result:
            # Missing dependencies are fatal errors - increment error count for circuit breaker
            if self._error_handler and result.get(RESULT_KEY_MISSING_DEPENDENCIES):
                self._error_handler.increment_error_count(formula_name)
            return EvaluatorResults.create_error_result(
                result[RESULT_KEY_ERROR],
                state=result[RESULT_KEY_STATE],
                missing_dependencies=result.get(RESULT_KEY_MISSING_DEPENDENCIES),
            )
        return EvaluatorResults.create_success_result_with_state(
            result[RESULT_KEY_STATE],
            unavailable_dependencies=result.get(RESULT_KEY_UNAVAILABLE_DEPENDENCIES),
        )

    def _validate_evaluation_context(self, eval_context: dict[str, ContextValue], formula_name: str) -> EvaluationResult | None:
        """Validate that evaluation context has all required variables."""
        if not self._dependency_management_phase:
            return None

        result = self._dependency_management_phase.validate_evaluation_context(eval_context, formula_name)

        if result is None:
            return None
        # Convert the phase result to an EvaluationResult and handle error counting
        if RESULT_KEY_ERROR in result:
            if self._error_handler:
                self._error_handler.increment_error_count(formula_name)
            return EvaluatorResults.create_error_result(result[RESULT_KEY_ERROR], state=result[RESULT_KEY_STATE])
        return EvaluatorResults.create_success_result_with_state(
            result[RESULT_KEY_STATE],
            unavailable_dependencies=result.get(RESULT_KEY_UNAVAILABLE_DEPENDENCIES),
        )
