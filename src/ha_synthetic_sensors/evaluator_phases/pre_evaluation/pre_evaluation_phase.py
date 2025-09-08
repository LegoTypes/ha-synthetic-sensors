"""Pre-Evaluation Processing Phase for synthetic sensor formula evaluation."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from ...alternate_state_processor import alternate_state_processor
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
from ...hierarchical_context_dict import HierarchicalContextDict
from ...type_definitions import DataProviderCallback, EvaluationResult
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
        context: HierarchicalContextDict,
        sensor_config: SensorConfig | None,
        formula_name: str,
        bypass_dependency_management: bool = False,
        alternate_state_processor_instance: Any = None,
    ) -> tuple[EvaluationResult | None, HierarchicalContextDict]:
        """Perform all pre-evaluation checks and return error result if any fail.

        Args:
            config: Formula configuration to evaluate
            context: Optional context variables
            sensor_config: Optional sensor configuration
            formula_name: Name of the formula for error reporting
            bypass_dependency_management: Whether to skip dependency management

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
                context,
            )

        # Step 2: Check cache
        if self._cache_handler:
            cache_result = self._cache_handler.check_cache(config, context, config.id)
            if cache_result:
                return cache_result, context

        # Step 3: State token validation removed - StateResolver already handles proper state setup

        # Step 4: Process dependencies and build context (unless bypassed)
        if bypass_dependency_management:
            _LOGGER.debug("BYPASS_DEPENDENCY_MANAGEMENT: Skipping dependency management for formula '%s'", formula_name)
            return None, context
        return self._process_dependencies_and_build_context(
            config, context, sensor_config, formula_name, alternate_state_processor_instance
        )

    def _process_dependencies_and_build_context(
        self,
        config: FormulaConfig,
        context: HierarchicalContextDict,
        sensor_config: SensorConfig | None,
        formula_name: str,
        alternate_state_processor_instance: Any = None,
    ) -> tuple[EvaluationResult | None, HierarchicalContextDict]:
        """Process dependencies and build evaluation context."""

        # PHASE 1: Variable Resolution - Resolve config variables BEFORE checking dependencies
        # This ensures that variables like 'internal_sensor_a' are resolved to their actual entity IDs
        # before the dependency checker looks for them
        if self._variable_resolution_phase:
            # Create a copy of the context for variable resolution
            resolved_context = context
            self._variable_resolution_phase.resolve_config_variables(resolved_context, config, sensor_config)

            # Resolve collection functions BEFORE dependency extraction
            # Collection functions like sum("device_class:power") must be resolved to actual entity references
            # before the dependency parser processes the formula, otherwise the parser treats the collection
            # pattern as missing dependencies (e.g., "device_class", "power")
            if hasattr(self._variable_resolution_phase, "_resolve_collection_functions"):
                # Resolve collection functions in the formula to prevent dependency parser confusion
                original_formula = config.formula
                resolved_formula = self._variable_resolution_phase._resolve_collection_functions(
                    config.formula, sensor_config, resolved_context, config
                )
                if resolved_formula != original_formula:
                    # Store original formula for restoration after dependency extraction
                    config._original_formula = original_formula  # type: ignore[attr-defined]
                    # Temporarily update the config formula for dependency extraction
                    # This ensures dependency extraction works on the resolved formula
                    config.formula = resolved_formula
                    _LOGGER.debug(
                        "Pre-evaluation collection function resolution: '%s' -> '%s'", original_formula, resolved_formula
                    )

                # Also resolve collection functions in computed variables to prevent dependency parser confusion
                if config.variables:
                    original_variables = {}
                    modified_variables = {}
                    for var_name, var_value in config.variables.items():
                        if hasattr(var_value, "formula"):
                            # This is a ComputedVariable with a formula
                            original_var_formula = var_value.formula
                            resolved_var_formula = self._variable_resolution_phase._resolve_collection_functions(
                                var_value.formula, sensor_config, resolved_context, config
                            )
                            if resolved_var_formula != original_var_formula:
                                # Store original for restoration
                                original_variables[var_name] = original_var_formula
                                # Create a copy of the computed variable with resolved formula
                                from ...config_models import ComputedVariable

                                resolved_var = ComputedVariable(
                                    formula=resolved_var_formula,
                                    dependencies=getattr(var_value, "dependencies", set()),
                                    alternate_state_handler=getattr(var_value, "alternate_state_handler", None),
                                    allow_unresolved_states=getattr(var_value, "allow_unresolved_states", False),
                                )
                                modified_variables[var_name] = resolved_var
                                _LOGGER.debug(
                                    "Pre-evaluation computed variable collection function resolution: '%s' -> '%s'",
                                    original_var_formula,
                                    resolved_var_formula,
                                )
                    # Store original variables for restoration and update config
                    if original_variables:
                        config._original_variables = original_variables  # type: ignore[attr-defined]
                        # Update the variables in config for dependency extraction
                        for var_name, resolved_var in modified_variables.items():
                            config.variables[var_name] = resolved_var
        else:
            resolved_context = context

        # PHASE 1: Single Value Check - Check for single alternate states before dependency management
        try:
            # May raise AlternateStateDetected for single state formulas
            # Use provided alternate state processor instance or fall back to global
            processor = (
                alternate_state_processor_instance
                if alternate_state_processor_instance is not None
                else alternate_state_processor
            )
            processor.check_pre_evaluation_states(resolved_context, config, sensor_config)
        except Exception as e:
            # If AlternateStateDetected is raised, let it propagate up to be handled by the main evaluator
            # Other exceptions should also propagate up
            raise e

        # Extract and validate dependencies
        if not (self._dependency_management_phase and self._dependency_handler):
            return None, resolved_context

        # Store original formula to restore after dependency extraction
        original_formula = getattr(config, "_original_formula", None) or config.formula

        dependencies, collection_pattern_entities = self._dependency_management_phase.extract_and_prepare_dependencies(
            config, resolved_context, sensor_config
        )
        missing_deps, unavailable_deps, unknown_deps = self._dependency_handler.check_dependencies(
            dependencies, resolved_context, collection_pattern_entities
        )

        # Restore original formula after dependency extraction if it was modified
        if original_formula is not None:
            config.formula = original_formula
            # Only delete the attribute if it was actually set
            if hasattr(config, "_original_formula"):
                delattr(config, "_original_formula")

        # Restore original computed variables after dependency extraction if they were modified
        if hasattr(config, "_original_variables"):
            original_variables = config._original_variables
            for var_name, original_formula in original_variables.items():
                if var_name in config.variables and hasattr(config.variables[var_name], "formula"):
                    # Restore the original formula in the computed variable
                    from ...config_models import ComputedVariable

                    current_var = config.variables[var_name]
                    original_var = ComputedVariable(
                        formula=original_formula,
                        dependencies=getattr(current_var, "dependencies", set()),
                        alternate_state_handler=getattr(current_var, "alternate_state_handler", None),
                        allow_unresolved_states=getattr(current_var, "allow_unresolved_states", False),
                    )
                    config.variables[var_name] = original_var
            # Clean up the temporary attribute
            delattr(config, "_original_variables")

        # Handle dependency issues
        dependency_result = self._handle_dependency_issues(missing_deps, unavailable_deps, unknown_deps, formula_name)
        if dependency_result:
            return dependency_result, resolved_context

        # PHASE 3: Context Building - Build evaluation context with resolved variables
        if not self._context_building_phase:
            return None, resolved_context

        final_context = self._context_building_phase.build_evaluation_context(
            dependencies, resolved_context, config, sensor_config
        )

        context_result = self._validate_evaluation_context(final_context, formula_name)
        if context_result:
            return context_result, resolved_context

        # Return the built evaluation context with resolved variables
        return None, final_context

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

    def _validate_evaluation_context(self, eval_context: HierarchicalContextDict, formula_name: str) -> EvaluationResult | None:
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
