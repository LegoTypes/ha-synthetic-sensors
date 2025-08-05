"""Configuration utilities for synthetic sensor package.

This module provides shared utilities for handling configuration variables
and other configuration-related operations to eliminate code duplication.
"""

from collections.abc import Callable
import logging
from typing import Any

from .config_models import ComputedVariable, FormulaConfig
from .exceptions import EmptyEvaluationContextError, FatalEvaluationError, MissingDependencyError
from .formula_router import FormulaRouter
from .evaluator_handlers.handler_factory import HandlerFactory
from .formula_compilation_cache import FormulaCompilationCache
from .formula_parsing.variable_extractor import ExtractionContext, extract_variables
from .reference_value_manager import ReferenceValueManager
from .shared_constants import DATETIME_FUNCTIONS, DURATION_FUNCTIONS, METADATA_FUNCTIONS
from .type_definitions import ContextValue, ReferenceValue

_LOGGER = logging.getLogger(__name__)

# Global compilation cache for computed variable formulas
# Uses the same caching mechanism as main formulas for consistency
_COMPUTED_VARIABLE_COMPILATION_CACHE = FormulaCompilationCache()


def _extract_values_for_simpleeval(eval_context: dict[str, ContextValue]) -> dict[str, ContextValue]:
    """Extract values from ReferenceValue objects for SimpleEval evaluation.

    SimpleEval doesn't understand ReferenceValue objects, so we need to extract
    the actual values while preserving other context items.
    """
    simpleeval_context: dict[str, ContextValue] = {}

    for key, value in eval_context.items():
        if isinstance(value, ReferenceValue):
            # Extract the value from ReferenceValue for SimpleEval
            simpleeval_context[key] = value.value
        else:
            # Keep other values as-is (functions, constants, etc.)
            simpleeval_context[key] = value

    return simpleeval_context


def convert_string_to_number_if_possible(result: str) -> str | int | float:
    """Convert a string result to a number if possible, otherwise return as string.

    This is a shared utility to eliminate duplicate code across multiple handlers.

    Args:
        result: String result to potentially convert

    Returns:
        Converted number (int or float) if possible, otherwise the original string
    """
    try:
        # Try to convert string to number for main formulas
        if "." in result:
            return float(result)
        return int(result)
    except ValueError:
        # If conversion fails, return as string
        return result


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
    available_vars.update(always_available)

    # Check each computed variable for references to undefined variables
    for var_name, var_value in variables.items():
        if isinstance(var_value, ComputedVariable):
            formula = var_value.formula
            potential_refs = _extract_variable_references(formula)

            # Check for references to undefined variables
            undefined_refs = [ref for ref in potential_refs if ref not in available_vars]

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


def _try_exception_handler(
    var_name: str, computed_var: ComputedVariable, eval_context: dict[str, ContextValue], error: Exception
) -> bool | str | float | int | None:
    """Try to resolve a computed variable using its exception handler.

    Args:
        var_name: Name of the computed variable that failed
        computed_var: The ComputedVariable object with potential exception handler
        eval_context: Current evaluation context
        error: The exception that occurred during main formula evaluation

    Returns:
        Resolved value from exception handler, or None if no handler or handler failed
    """
    if not computed_var.exception_handler:
        return None

    # Determine which exception handler to use based on error type
    handler_formula = None
    
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
        _LOGGER.error("FATAL ERROR in computed variable '%s': %s - This should NOT be masked by UNAVAILABLE fallbacks", var_name, error)
        return None  # Let the error propagate as fatal
    
    # NON-FATAL ERRORS: Legitimate cases for UNAVAILABLE/UNKNOWN fallbacks
    if "unavailable" in error_str or "not defined" in error_str:
        handler_formula = computed_var.exception_handler.unavailable
    elif "unknown" in error_str:
        handler_formula = computed_var.exception_handler.unknown
    else:
        # For other non-fatal errors, try unavailable handler first, then unknown
        handler_formula = computed_var.exception_handler.unavailable or computed_var.exception_handler.unknown

    if not handler_formula:
        return None

    try:
        # Use the same compilation cache for exception handler formulas
        compiled_handler = _COMPUTED_VARIABLE_COMPILATION_CACHE.get_compiled_formula(handler_formula)

        # Extract values from ReferenceValue objects for SimpleEval evaluation
        simpleeval_context = _extract_values_for_simpleeval(eval_context)
        result = compiled_handler.evaluate(simpleeval_context, numeric_only=False)
        _LOGGER.debug("Resolved computed variable %s using exception handler: %s", var_name, result)

        # Convert numeric strings to numbers for consistency
        if isinstance(result, str):
            return convert_string_to_number_if_possible(result)

        return result
    except Exception as handler_err:
        _LOGGER.debug("Exception handler for variable %s also failed: %s", var_name, handler_err)
        return None


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
    _LOGGER.error("UTILS_CONFIG: resolve_config_variables called with resolver_callback: %s", resolver_callback)
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

        resolved_value = resolver_callback(var_name, var_value, eval_context, sensor_config)
        if resolved_value is not None:
            # Check if resolver already returned a ReferenceValue object
            if isinstance(resolved_value, ReferenceValue):
                # Resolver already created ReferenceValue - use it directly
                _LOGGER.error("UTILS_CONFIG: %s already ReferenceValue, setting directly: %s", var_name, resolved_value)
                eval_context[var_name] = resolved_value
                # Update the registry if needed
                entity_registry_key = "_entity_reference_registry"
                if entity_registry_key not in eval_context:
                    eval_context[entity_registry_key] = {}
                entity_registry = eval_context[entity_registry_key]
                if isinstance(entity_registry, dict):
                    entity_registry[resolved_value.reference] = resolved_value
            else:
                # Resolver returned raw value - wrap in ReferenceValue
                _LOGGER.error(
                    "UTILS_CONFIG: %s raw value, wrapping: %s (type: %s)",
                    var_name,
                    resolved_value,
                    type(resolved_value).__name__,
                )
                ReferenceValueManager.set_variable_with_reference_value(eval_context, var_name, var_value, resolved_value)


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
        made_progress = _process_computed_variables_iteration(remaining_vars, resolved_vars, eval_context, error_details_map)

        if not made_progress:
            _handle_no_progress_error(remaining_vars, error_details_map)

    if remaining_vars:
        _handle_max_iterations_error(remaining_vars, max_iterations)


def _process_computed_variables_iteration(
    remaining_vars: dict[str, ComputedVariable],
    resolved_vars: set[str],
    eval_context: dict[str, ContextValue],
    error_details_map: dict[str, dict[str, Any]],
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
            success = _try_resolve_computed_variable(var_name, computed_var, eval_context)
            if success:
                del remaining_vars[var_name]
                resolved_vars.add(var_name)
                made_progress = True
        except FatalEvaluationError:
            # FATAL ERRORS: Let these bubble up immediately - they indicate critical system failures
            # EmptyEvaluationContextError, MissingDependencyError should NEVER be masked by UNAVAILABLE fallbacks
            raise
        except Exception as err:
            # NON-FATAL ERRORS: Try to handle with UNAVAILABLE fallbacks
            handled = _try_handle_computed_variable_error(var_name, computed_var, eval_context, error_details_map, err)
            if handled:
                del remaining_vars[var_name]
                resolved_vars.add(var_name)
                made_progress = True

    return made_progress


def _try_resolve_computed_variable(
    var_name: str, computed_var: ComputedVariable, eval_context: dict[str, ContextValue]
) -> bool:
    """Try to resolve a single computed variable using the proper FormulaRouter and handler system.

    This ensures computed variables go through the same evaluation pathway as main formulas,
    including proper type conversion via the type analyzer system.

    Returns:
        True if successfully resolved, False otherwise
    """
    # FATAL ERROR CHECK: Empty context during computed variable evaluation is a critical system error
    if not eval_context:
        raise EmptyEvaluationContextError(computed_var.formula, "computed variable")
    
    _LOGGER.error(
        "COMPUTED_VAR_DEBUG: Evaluating %s formula '%s' with context: %s",
        var_name,
        computed_var.formula,
        eval_context,
    )
    
    # Use FormulaRouter to determine the appropriate handler (same as main formulas)
    formula_router = FormulaRouter()
    routing_result = formula_router.route_formula(computed_var.formula)
    
    # Create handler factory and get the appropriate handler
    # Note: We'll pass None for hass since computed variables don't need HA integration
    handler_factory = HandlerFactory(expression_evaluator=None, hass=None)
    
    # Get handler based on routing result
    if routing_result.evaluator_type.value == "numeric":
        handler = handler_factory.get_handler("numeric")
    elif routing_result.evaluator_type.value == "string":
        handler = handler_factory.get_handler("string")
    elif routing_result.evaluator_type.value == "date":
        handler = handler_factory.get_handler("date")
    elif routing_result.evaluator_type.value == "boolean":
        handler = handler_factory.get_handler("boolean")
    elif routing_result.evaluator_type.value == "duration":
        handler = handler_factory.get_handler("duration")
    else:
        # Fallback to numeric handler
        handler = handler_factory.get_handler("numeric")
    
    if not handler:
        raise ValueError(f"No handler available for computed variable formula: {computed_var.formula}")
    
    # Evaluate using the proper handler (which includes type analyzer integration)
    result = handler.evaluate(computed_var.formula, eval_context)
    _LOGGER.error("COMPUTED_VAR_DEBUG: Result for %s: %s (type: %s)", var_name, result, type(result).__name__)

    # For computed variables, the formula itself is the "reference"
    ReferenceValueManager.set_variable_with_reference_value(eval_context, var_name, computed_var.formula, result)
    _LOGGER.debug("Resolved computed variable %s = %s", var_name, result)
    return True


def _try_handle_computed_variable_error(
    var_name: str,
    computed_var: ComputedVariable,
    eval_context: dict[str, ContextValue],
    error_details_map: dict[str, dict[str, Any]],
    err: Exception,
) -> bool:
    """Try to handle a computed variable error using exception handler.

    Returns:
        True if error was handled successfully, False otherwise
    """
    # Try exception handler before giving up
    exception_result = _try_exception_handler(var_name, computed_var, eval_context, err)

    if exception_result is not None:
        # Exception handler succeeded - use its result
        ReferenceValueManager.set_variable_with_reference_value(eval_context, var_name, computed_var.formula, exception_result)
        _LOGGER.debug("Resolved computed variable %s using exception handler = %s", var_name, exception_result)
        return True

    # Exception handler failed or not available - provide detailed error context
    error_details = _analyze_computed_variable_error(var_name, computed_var.formula, eval_context, err)
    _LOGGER.debug("Could not resolve computed variable %s: %s", var_name, error_details["summary"])

    # Store error details for final error reporting
    error_details_map[var_name] = error_details
    return False


def _handle_no_progress_error(
    remaining_vars: dict[str, ComputedVariable], error_details_map: dict[str, dict[str, Any]]
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

    raise MissingDependencyError(
        f"Could not resolve computed variables {list(remaining_vars.keys())}:\n" + "\n".join(error_messages)
    )


def _handle_max_iterations_error(remaining_vars: dict[str, ComputedVariable], max_iterations: int) -> None:
    """Handle the case where max iterations were exceeded in computed variable resolution."""
    # Max iterations exceeded - likely circular dependencies
    remaining_var_names = list(remaining_vars.keys())
    formulas_info = [f"{name}: '{remaining_vars[name].formula}'" for name in remaining_var_names]

    raise MissingDependencyError(
        f"Could not resolve computed variables {remaining_var_names} within {max_iterations} iterations. "
        f"This likely indicates circular dependencies between variables:\n" + "\n".join(f"• {info}" for info in formulas_info)
    )
