"""Configuration utilities for synthetic sensor package.

This module provides shared utilities for handling configuration variables
and other configuration-related operations to eliminate code duplication.
"""

from collections.abc import Callable
import logging
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .alternate_state_eval import evaluate_computed_alternate
from .config_models import ComputedVariable, FormulaConfig
from .constants_evaluation_results import RESULT_KEY_ERROR, RESULT_KEY_SUCCESS, RESULT_KEY_VALUE
from .enhanced_formula_evaluation import EnhancedSimpleEvalHelper
from .evaluator_helpers import EvaluatorHelpers
from .exceptions import FatalEvaluationError, MissingDependencyError
from .formula_compilation_cache import FormulaCompilationCache
from .formula_evaluator_service import FormulaEvaluatorService
from .formula_parsing.variable_extractor import ExtractionContext, extract_variables
from .math_functions import MathFunctions
from .reference_value_manager import ReferenceValueManager
from .shared_constants import DATETIME_FUNCTIONS, DURATION_FUNCTIONS, METADATA_FUNCTIONS
from .type_definitions import ContextValue, ReferenceValue

_LOGGER = logging.getLogger(__name__)

# Global compilation cache for computed variable formulas
# Uses the same caching mechanism as main formulas for consistency
_COMPUTED_VARIABLE_COMPILATION_CACHE = FormulaCompilationCache()


# Enhanced SimpleEval helper for computed variables to use same functions as main formulas
class _EnhancedHelperSingleton:
    """Singleton for enhanced SimpleEval helper to avoid global statement."""

    _instance: EnhancedSimpleEvalHelper | None = None

    @classmethod
    def get_instance(cls) -> EnhancedSimpleEvalHelper:
        """Get or create the enhanced SimpleEval helper for computed variables."""
        if cls._instance is None:
            cls._instance = EnhancedSimpleEvalHelper()
            _LOGGER.debug("Created enhanced SimpleEval helper for computed variables")
        return cls._instance


def _get_enhanced_helper() -> EnhancedSimpleEvalHelper:
    """Get or create the enhanced SimpleEval helper for computed variables."""
    return _EnhancedHelperSingleton.get_instance()


def _extract_values_for_simpleeval(eval_context: dict[str, ContextValue]) -> dict[str, ContextValue]:
    """Extract values from ReferenceValue objects for SimpleEval evaluation.

    SimpleEval doesn't understand ReferenceValue objects, so we need to extract
    the actual values while preserving other context items.
    """
    simpleeval_context: dict[str, ContextValue] = {}

    for key, value in eval_context.items():
        if isinstance(value, ReferenceValue):
            # Extract the value from ReferenceValue for SimpleEval
            extracted_value = value.value
            # Apply priority analyzer (boolean-first, then numeric) for consistency
            if isinstance(extracted_value, str):
                extracted_value = EvaluatorHelpers.preprocess_value_for_enhanced_eval(extracted_value)
            simpleeval_context[key] = extracted_value
        else:
            # Keep other values as-is (functions, constants, etc.)
            simpleeval_context[key] = value

    return simpleeval_context


def _extract_variable_references(formula: str) -> list[str]:
    """Extract variable references from a formula, excluding string literals and keywords.

    Args:
        formula: The formula to analyze

    Returns:
        List of potential variable names found in the formula
    """
    return list(
        extract_variables(
            formula,
            context=ExtractionContext.CONFIG_VALIDATION,
            allow_dot_notation=True,  # utils_config allows dot notation
        )
    )


_COMPUTED_VARIABLE_COMPILATION_CACHE = FormulaCompilationCache(max_entries=500)


def clear_computed_variable_cache() -> None:
    """Clear the computed variable compilation cache. Useful for testing and memory management."""
    _COMPUTED_VARIABLE_COMPILATION_CACHE.clear()
    _LOGGER.debug("Cleared computed variable compilation cache")


def get_computed_variable_cache_stats() -> dict[str, Any]:
    """Get statistics about the computed variable compilation cache."""
    return _COMPUTED_VARIABLE_COMPILATION_CACHE.get_statistics()


def validate_computed_variable_references(
    variables: dict[str, Any], config_id: str | None = None, global_variables: dict[str, Any] | None = None
) -> list[str]:
    """Validate that computed variables don't reference undefined variables.

    Args:
        variables: Dictionary of variables including computed variables
        config_id: Optional config ID for error context
        global_variables: Dictionary of global variables that are available

    Returns:
        List of validation error messages
    """

    errors = []
    context_prefix = f"In {config_id}: " if config_id else ""

    # Get all available variable names (simple variables and computed variable names)
    available_vars = set(variables.keys())

    # Add global variables if provided
    if global_variables:
        available_vars.update(global_variables.keys())

    # Add common context variables that are always available
    always_available = {"state", "now", "today", "yesterday"}  # Common tokens
    always_available.update(METADATA_FUNCTIONS)  # Add metadata functions
    always_available.update(DURATION_FUNCTIONS)  # Add duration functions
    always_available.update(DATETIME_FUNCTIONS)  # Add datetime functions
    always_available.update(MathFunctions.get_all_functions().keys())  # Add enhanced math functions
    available_vars.update(always_available)

    # Check each computed variable for references to undefined variables
    for var_name, var_value in variables.items():
        if isinstance(var_value, ComputedVariable):
            formula = var_value.formula
            potential_refs = _extract_variable_references(formula)

            # Check for references to undefined variables
            # Entity IDs (sensor.*, binary_sensor.*, etc.) are always valid references
            undefined_refs = [ref for ref in potential_refs if ref not in available_vars and not _is_entity_id_reference(ref)]

            if undefined_refs:
                error_msg = (
                    f"{context_prefix}Computed variable '{var_name}' references "
                    f"undefined variables: {undefined_refs}. "
                    f"Available variables: {sorted(available_vars - always_available)}"
                )
                errors.append(error_msg)

            # Check for self-reference
            if var_name in potential_refs:
                errors.append(
                    f"{context_prefix}Computed variable '{var_name}' references itself, "
                    f"which may cause circular dependency issues"
                )

    return errors


def _is_entity_id_reference(reference: str) -> bool:
    """Check if a reference looks like a valid entity ID.

    Entity IDs typically follow the pattern: domain.object_id
    Common domains include: sensor, binary_sensor, switch, light, etc.

    Args:
        reference: The reference string to check

    Returns:
        True if the reference appears to be a valid entity ID
    """
    if not isinstance(reference, str) or "." not in reference:
        return False

    # Common Home Assistant entity domains
    from .constants_entities import COMMON_ENTITY_DOMAINS

    valid_domains = set(COMMON_ENTITY_DOMAINS) | {
        "cover",
        "fan",
        "lock",
        "media_player",
        "vacuum",
        "camera",
        "alarm_control_panel",
        "device_tracker",
        "person",
        "zone",
        "automation",
        "script",
        "scene",
        "input_boolean",
        "input_number",
        "input_select",
        "input_text",
        "input_datetime",
        "timer",
        "counter",
        "weather",
        "sun",
        "calendar",
        "water_heater",
        "humidifier",
        "air_quality",
        "button",
        "number",
        "select",
        "text",
    }

    parts = reference.split(".", 1)
    if len(parts) != 2:
        return False

    domain, object_id = parts
    return domain in valid_domains and len(object_id) > 0


# CLEAN SLATE: Removed exception handler fallback logic - deterministic system should not fallback to 0


def _analyze_computed_variable_error(
    var_name: str, formula: str, eval_context: dict[str, ContextValue], error: Exception
) -> dict[str, Any]:
    """Analyze a computed variable error and provide detailed diagnostic information.

    Args:
        var_name: Name of the computed variable that failed
        formula: The formula that failed to evaluate
        eval_context: Current evaluation context
        error: The exception that occurred

    Returns:
        Dictionary with error analysis details
    """

    # Extract potential variable references from formula (excluding string literals)
    potential_vars = _extract_variable_references(formula)

    # Check which variables are missing from context
    missing_vars = [var for var in potential_vars if var not in eval_context]
    available_vars = [var for var in potential_vars if var in eval_context]

    # Categorize the error type
    error_type = type(error).__name__
    error_message = str(error)

    # Determine likely cause - check specific error types first, then missing vars
    if "division by zero" in error_message.lower() or "zerodivision" in error_message.lower():
        likely_cause = "division_by_zero"
        suggestion = "Check for division by zero in formula - add conditional checks"
    elif "name" in error_message.lower() and "not defined" in error_message.lower():
        if missing_vars:
            likely_cause = "missing_dependencies"
            suggestion = f"Ensure variables {missing_vars} are defined or resolved first"
        else:
            likely_cause = "undefined_variable"
            suggestion = "Check variable names in formula for typos"
    elif "unsupported operand" in error_message.lower():
        likely_cause = "type_mismatch"
        suggestion = "Check that all variables are numeric values"
    elif "invalid syntax" in error_message.lower():
        likely_cause = "syntax_error"
        suggestion = "Check formula syntax for mathematical expressions"
    elif missing_vars:
        likely_cause = "missing_dependencies"
        suggestion = f"Ensure variables {missing_vars} are defined or resolved first"
    else:
        likely_cause = "unknown"
        suggestion = "Check formula logic and variable values"

    return {
        "variable_name": var_name,
        "formula": formula,
        "error_type": error_type,
        "error_message": error_message,
        "likely_cause": likely_cause,
        "missing_variables": missing_vars,
        "available_variables": available_vars,
        "context_values": {var: eval_context[var] for var in available_vars},
        "suggestion": suggestion,
        "summary": f"{error_type} in '{var_name}': {suggestion}",
    }


def resolve_config_variables(
    eval_context: dict[str, ContextValue],
    config: FormulaConfig | None,
    resolver_callback: Callable[[str, Any, dict[str, Any], Any | None], Any | None],
    sensor_config: Any = None,
) -> None:
    """Resolve config variables using the provided resolver callback.

    This is a shared utility to eliminate duplicate code between different
    phases that need to resolve configuration variables. Handles dependency
    ordering and error handling consistently.

    Args:
        eval_context: Context dictionary to populate with resolved values
        config: FormulaConfig containing variables to resolve
        resolver_callback: Callback function to resolve individual variables
        sensor_config: Optional sensor configuration for context
    """
    if not config or not config.variables:
        return

    # Separate simple variables from computed variables
    simple_variables: dict[str, Any] = {}
    computed_variables: dict[str, ComputedVariable] = {}

    for var_name, var_value in config.variables.items():
        if isinstance(var_value, ComputedVariable):
            computed_variables[var_name] = var_value
        else:
            simple_variables[var_name] = var_value

    # Resolve simple variables first (they may be dependencies for computed variables)
    if simple_variables:
        _resolve_simple_variables(eval_context, simple_variables, resolver_callback, sensor_config, config)

    # Resolve computed variables in dependency order
    if computed_variables:
        _resolve_computed_variables(eval_context, computed_variables, config)


def _resolve_simple_variables(
    eval_context: dict[str, ContextValue],
    simple_variables: dict[str, Any],
    resolver_callback: Callable[[str, Any, dict[str, Any], Any | None], Any | None],
    sensor_config: Any,
    config: FormulaConfig,
) -> None:
    """Resolve simple variables using the provided resolver callback.

    Args:
        eval_context: Context dictionary to populate
        simple_variables: Dictionary of simple variables to resolve
        resolver_callback: Callback function to resolve individual variables
        sensor_config: Sensor configuration for context
        config: FormulaConfig for context
    """
    # Entity-centric ReferenceValue registry: one ReferenceValue per unique entity_id
    entity_registry_key = "_entity_reference_registry"
    if entity_registry_key not in eval_context:
        eval_context[entity_registry_key] = {}

    for var_name, var_value in simple_variables.items():
        # Skip if this variable is already set in context (context has higher priority)
        if var_name in eval_context and var_name != entity_registry_key:
            _LOGGER.debug("Skipping config variable %s (already set in context)", var_name)
            continue

        _LOGGER.debug("UTILS_CONFIG_DEBUG: Calling resolver_callback for '%s' = '%s'", var_name, var_value)
        resolved_value = resolver_callback(var_name, var_value, eval_context, sensor_config)
        _LOGGER.debug("UTILS_CONFIG_DEBUG: resolver_callback returned %s for '%s'", resolved_value, var_name)

        # Always set the variable in context - resolver should always return ReferenceValue
        if isinstance(resolved_value, ReferenceValue):
            # Resolver already created ReferenceValue - use it directly
            eval_context[var_name] = resolved_value
            # Update the registry if needed
            entity_registry_key = "_entity_reference_registry"
            if entity_registry_key not in eval_context:
                eval_context[entity_registry_key] = {}
            entity_registry = eval_context[entity_registry_key]
            if isinstance(entity_registry, dict):
                entity_registry[resolved_value.reference] = resolved_value
        elif resolved_value is not None:
            # Resolver returned raw value - wrap in ReferenceValue
            ReferenceValueManager.set_variable_with_reference_value(eval_context, var_name, var_value, resolved_value)
        else:
            # Resolver returned None - this is a missing dependency (fatal error)
            raise MissingDependencyError(f"Variable '{var_name}' could not be resolved")


def _resolve_computed_variables(
    eval_context: dict[str, ContextValue],
    computed_variables: dict[str, ComputedVariable],
    config: FormulaConfig,
) -> None:
    """Resolve computed variables using simpleeval in dependency order."""
    _LOGGER.debug("Resolving %d computed variables", len(computed_variables))

    # Simple dependency ordering: resolve variables that don't depend on other computed variables first
    resolved_vars: set[str] = set()
    remaining_vars = computed_variables.copy()
    max_iterations = len(computed_variables) + 1  # Prevent infinite loops
    iteration = 0
    error_details_map: dict[str, dict[str, Any]] = {}

    while remaining_vars and iteration < max_iterations:
        iteration += 1
        made_progress = _process_computed_variables_iteration(
            remaining_vars, resolved_vars, eval_context, error_details_map, config
        )

        if not made_progress:
            _handle_no_progress_error(remaining_vars, error_details_map, eval_context)

    if remaining_vars:
        _handle_max_iterations_error(remaining_vars, max_iterations)


def _process_computed_variables_iteration(
    remaining_vars: dict[str, ComputedVariable],
    resolved_vars: set[str],
    eval_context: dict[str, ContextValue],
    error_details_map: dict[str, dict[str, Any]],
    parent_config: FormulaConfig | None,
) -> bool:
    """Process one iteration of computed variable resolution.

    Returns:
        True if progress was made, False otherwise
    """
    made_progress = False

    for var_name in list(remaining_vars.keys()):
        computed_var = remaining_vars[var_name]

        # Skip if already resolved
        if var_name in eval_context:
            del remaining_vars[var_name]
            resolved_vars.add(var_name)
            made_progress = True
            continue

        # Try to evaluate the computed variable formula with current context
        try:
            success = _try_resolve_computed_variable(var_name, computed_var, eval_context, parent_config)
            if success:
                del remaining_vars[var_name]
                resolved_vars.add(var_name)
                made_progress = True
        except FatalEvaluationError:
            # FATAL ERRORS: Programming errors should bubble up immediately
            raise
        except Exception as err:
            # Check if this is a real evaluation error vs entity unavailable/unknown
            error_str = str(err).lower()
            if STATE_UNKNOWN in error_str:
                # Entity state issues - use YAML exception handlers
                handled = _try_handle_computed_variable_error(var_name, computed_var, eval_context, error_details_map, err)
                if handled:
                    del remaining_vars[var_name]
                    resolved_vars.add(var_name)
                    made_progress = True
            else:
                # Programming/formula errors - should not fallback to 0
                # For now, still try alternate state handler but log as suspicious
                handled = _try_handle_computed_variable_error(var_name, computed_var, eval_context, error_details_map, err)
                if handled:
                    _LOGGER.warning(
                        "SUSPICIOUS: Used alternate state handler for programming error in %s - this may mask a real bug",
                        var_name,
                    )
                    del remaining_vars[var_name]
                    resolved_vars.add(var_name)
                    made_progress = True
                else:
                    # If alternate state handler also fails, bubble up the original error
                    raise err

    return made_progress


def _try_resolve_computed_variable(
    var_name: str,
    computed_var: ComputedVariable,
    eval_context: dict[str, ContextValue],
    parent_config: FormulaConfig | None,
) -> bool:
    """Try to resolve a single computed variable.

    This function delegates to the main evaluation system for proper formula evaluation.
    Computed variables should use the same evaluation pipeline as main formulas.

    For computed variables containing metadata functions, we use lazy ReferenceValue resolution
    to preserve the original references for metadata processing.

    Returns:
        True if successfully resolved, False otherwise
    """
    _LOGGER.debug("Resolving computed variable %s with formula: %s", var_name, computed_var.formula)

    try:
        if _metadata_function_present(computed_var.formula):
            return _resolve_metadata_computed_variable(var_name, computed_var, eval_context, parent_config)

        return _resolve_non_metadata_computed_variable(var_name, computed_var, eval_context, parent_config)

    except Exception as err:
        _LOGGER.debug("Computed variable %s failed to resolve: %s", var_name, err)
        return False


def _resolve_entity_references_in_computed_variable(formula: str, eval_context: dict[str, ContextValue]) -> str:
    """Deprecated: computed variables use unified evaluator pipeline; keep for compatibility."""
    return formula


def _metadata_function_present(formula: str) -> bool:
    import re  # pylint: disable=import-outside-toplevel

    metadata_pattern = re.compile(r"\bmetadata\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)")
    return metadata_pattern.search(formula) is not None


def _build_simple_variables_view(parent_config: FormulaConfig | None) -> dict[str, Any] | None:
    if not parent_config or not parent_config.variables:
        return None
    variables_view: dict[str, Any] = {}
    for key, value in parent_config.variables.items():
        if isinstance(value, ComputedVariable):
            continue
        variables_view[key] = value
    return variables_view


def _entity_available_in_hass(eval_context: dict[str, ContextValue]) -> bool:
    hass_val = eval_context.get("_hass")
    hass = hass_val.value if isinstance(hass_val, ReferenceValue) else hass_val
    current_sensor_val = eval_context.get("current_sensor_entity_id")
    current_entity_id = current_sensor_val.value if isinstance(current_sensor_val, ReferenceValue) else current_sensor_val
    if not (getattr(hass, "states", None) and isinstance(current_entity_id, str)):
        return False
    try:
        return hass.states.get(current_entity_id) is not None  # type: ignore[union-attr]
    except Exception:
        return False


def _evaluate_cv_via_pipeline(
    formula: str,
    eval_context: dict[str, ContextValue],
    parent_config: FormulaConfig | None,
    allow_unresolved_states: bool = False,
) -> dict[str, Any]:
    variables_view = _build_simple_variables_view(parent_config)
    return FormulaEvaluatorService.evaluate_formula_via_pipeline(
        formula,
        eval_context,
        variables=variables_view,
        bypass_dependency_management=False,
        allow_unresolved_states=allow_unresolved_states,
    )


def _set_reference_value(eval_context: dict[str, ContextValue], var_name: str, formula: str, value: Any) -> None:
    ReferenceValueManager.set_variable_with_reference_value(eval_context, var_name, formula, value)


def _set_lazy_reference(eval_context: dict[str, ContextValue], var_name: str, formula: str) -> None:
    lazy_reference = ReferenceValue(reference=formula, value=None)
    ReferenceValueManager.set_variable_with_reference_value(eval_context, var_name, formula, lazy_reference)


def _resolve_metadata_computed_variable(
    var_name: str,
    computed_var: ComputedVariable,
    eval_context: dict[str, ContextValue],
    parent_config: FormulaConfig | None,
) -> bool:
    _LOGGER.debug(
        "Computed variable %s contains metadata functions - attempting gated evaluation via pipeline",
        var_name,
    )

    if not _entity_available_in_hass(eval_context):
        _set_lazy_reference(eval_context, var_name, computed_var.formula)
        _LOGGER.debug("Computed variable %s stored as lazy ReferenceValue (awaiting HA readiness)", var_name)
        return True

    eval_result = _evaluate_cv_via_pipeline(
        computed_var.formula, eval_context, parent_config, computed_var.allow_unresolved_states
    )
    if eval_result.get(RESULT_KEY_SUCCESS):
        result = eval_result[RESULT_KEY_VALUE]
        _set_reference_value(eval_context, var_name, computed_var.formula, result)
        _LOGGER.debug("Computed variable %s resolved via pipeline to: %s", var_name, result)
        return True

    _LOGGER.debug(
        "Computed variable %s pipeline evaluation failed or returned error: %s; will keep lazy",
        var_name,
        eval_result.get(RESULT_KEY_ERROR),
    )
    _set_lazy_reference(eval_context, var_name, computed_var.formula)
    return True


def _resolve_non_metadata_computed_variable(
    var_name: str,
    computed_var: ComputedVariable,
    eval_context: dict[str, ContextValue],
    parent_config: FormulaConfig | None,
) -> bool:
    eval_result = _evaluate_cv_via_pipeline(
        computed_var.formula, eval_context, parent_config, computed_var.allow_unresolved_states
    )
    if eval_result.get(RESULT_KEY_SUCCESS):
        result = eval_result[RESULT_KEY_VALUE]
        _LOGGER.debug("Computed variable %s resolved via pipeline to: %s", var_name, result)
        _set_reference_value(eval_context, var_name, computed_var.formula, result)
        return True

    error_msg = str(eval_result.get(RESULT_KEY_ERROR))
    _LOGGER.debug("Computed variable %s failed via pipeline: %s", var_name, error_msg)
    return False


def _try_handle_computed_variable_error(
    var_name: str,
    computed_var: ComputedVariable,
    eval_context: dict[str, ContextValue],
    error_details_map: dict[str, dict[str, Any]],
    err: Exception,
) -> bool:
    """Try to handle a computed variable error using alternate state handler.

    Returns:
        True if error was handled successfully, False otherwise
    """
    # Try alternate state handler before giving up
    alternate_state_result = _try_alternate_state_handler(var_name, computed_var, eval_context, err)

    if alternate_state_result is not None:
        # Alternate state handler succeeded - use its result
        ReferenceValueManager.set_variable_with_reference_value(
            eval_context, var_name, computed_var.formula, alternate_state_result
        )
        _LOGGER.debug("Resolved computed variable %s using alternate state handler = %s", var_name, alternate_state_result)
        return True

    # Alternate state handler failed or not available - provide detailed error context
    error_details = _analyze_computed_variable_error(var_name, computed_var.formula, eval_context, err)
    _LOGGER.debug("Could not resolve computed variable %s: %s", var_name, error_details["summary"])

    # Store error details for final error reporting
    error_details_map[var_name] = error_details
    return False


def _try_alternate_state_handler(
    var_name: str, computed_var: ComputedVariable, eval_context: dict[str, ContextValue], error: Exception
) -> bool | str | float | int | None:
    """Try to resolve a computed variable using its alternate state handler.

    Args:
        var_name: Name of the computed variable that failed
        computed_var: The ComputedVariable object with potential alternate state handler
        eval_context: Current evaluation context
        error: The exception that occurred during main formula evaluation

    Returns:
        Resolved value from alternate state handler, or None if no handler or handler failed
    """
    if not computed_var.alternate_state_handler:
        return None

    # Determine which alternate state handler to use based on error type
    handler_formula: Any | None = None

    # FATAL ERRORS: These should NEVER be masked by UNAVAILABLE fallbacks
    fatal_error_patterns = [
        "syntax",
        "invalid formula",
        "no handler",
        "routing",
        "received non-date formula",
        "received non-numeric formula",
        "received non-string formula",
        "division by zero",
        "invalid duration",
    ]

    error_str = str(error).lower()
    is_fatal_error = any(pattern in error_str for pattern in fatal_error_patterns)

    if is_fatal_error:
        # Fatal errors should propagate, not be masked by fallbacks
        _LOGGER.error(
            "FATAL ERROR in computed variable '%s': %s - This should NOT be masked by UNAVAILABLE fallbacks", var_name, error
        )
        return None  # Let the error propagate as fatal

    # NON-FATAL ERRORS: Legitimate cases for UNAVAILABLE/UNKNOWN/NONE fallbacks
    handler_formula = None

    # Try specific handlers first
    if STATE_UNAVAILABLE in error_str:
        handler_formula = computed_var.alternate_state_handler.unavailable
    elif STATE_UNKNOWN in error_str:
        handler_formula = computed_var.alternate_state_handler.unknown
    elif "none" in error_str:
        handler_formula = computed_var.alternate_state_handler.none

    # If no specific handler found, try fallback handler
    if handler_formula is None:
        handler_formula = computed_var.alternate_state_handler.fallback

    # Final fallback: try specific handlers in priority order
    if handler_formula is None:
        handler_formula = (
            computed_var.alternate_state_handler.none
            or computed_var.alternate_state_handler.unavailable
            or computed_var.alternate_state_handler.unknown
        )

    if not handler_formula:
        return None

    try:
        result = evaluate_computed_alternate(
            handler_formula,
            eval_context,
            _get_enhanced_helper,
            _extract_values_for_simpleeval,
        )
        if result is None:
            _LOGGER.debug("Alternate state handler evaluation failed for variable %s", var_name)
            return None
        return result

    except Exception as handler_err:
        _LOGGER.debug("Alternate state handler for variable %s also failed: %s", var_name, handler_err)
        return None


def _handle_no_progress_error(
    remaining_vars: dict[str, ComputedVariable],
    error_details_map: dict[str, dict[str, Any]],
    eval_context: dict[str, ContextValue],
) -> None:
    """Handle the case where no progress was made in computed variable resolution."""
    # No progress made - provide detailed error analysis for each failed variable
    failed_var_details: list[dict[str, Any]] = []

    for var_name, computed_var in remaining_vars.items():
        stored_error_details: dict[str, Any] | None = error_details_map.get(var_name)
        if stored_error_details is not None:
            failed_var_details.append(stored_error_details)
        else:
            # Basic error info if detailed analysis wasn't captured
            failed_var_details.append(
                {
                    "variable_name": var_name,
                    "formula": computed_var.formula,
                    "likely_cause": "circular_dependency_or_missing_deps",
                    "suggestion": "Check for circular references or missing variable definitions",
                }
            )

    # Create comprehensive error message
    error_messages: list[str] = []
    for details in failed_var_details:
        error_messages.append(f"• {details['variable_name']}: {details['suggestion']}")

    # Include specific undefined variables that were referenced in formulas
    undefined_vars_raw = eval_context.get("_undefined_variables")
    undefined_vars: set[str] = set()
    if undefined_vars_raw and isinstance(undefined_vars_raw, str) and undefined_vars_raw.startswith("SET:"):
        vars_str = undefined_vars_raw[4:]
        if vars_str:
            undefined_vars = set(vars_str.split(","))

    if undefined_vars:
        undefined_list = sorted(undefined_vars)
        error_msg = (
            f"Could not resolve computed variables {list(remaining_vars.keys())}: Missing variables: {undefined_list}.\n"
            + "\n".join(error_messages)
        )
    else:
        error_msg = (
            f"Could not resolve computed variables {list(remaining_vars.keys())}: Missing variables: {list(remaining_vars)}.\n"
            + "\n".join(error_messages)
        )

    raise MissingDependencyError(error_msg)


def _handle_max_iterations_error(remaining_vars: dict[str, ComputedVariable], max_iterations: int) -> None:
    """Handle the case where max iterations were exceeded in computed variable resolution."""
    # Max iterations exceeded - likely circular dependencies
    remaining_var_names = list(remaining_vars.keys())
    formulas_info = [f"{name}: '{remaining_vars[name].formula}'" for name in remaining_var_names]

    raise MissingDependencyError(
        f"Could not resolve computed variables {remaining_var_names} within {max_iterations} iterations. "
        f"This likely indicates circular dependencies between variables:\n" + "\n".join(f"• {info}" for info in formulas_info)
    )
