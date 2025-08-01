"""Configuration utilities for synthetic sensor package.

This module provides shared utilities for handling configuration variables
and other configuration-related operations to eliminate code duplication.
"""

from collections.abc import Callable
import logging
import re
from typing import Any

from .config_models import ComputedVariable, FormulaConfig
from .exceptions import MissingDependencyError
from .formula_compilation_cache import FormulaCompilationCache
from .type_definitions import ContextValue

_LOGGER = logging.getLogger(__name__)

# Global compilation cache for computed variable formulas
# Uses the same caching mechanism as main formulas for consistency


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

    # First, remove string literals to avoid matching words inside quotes
    # Handle both single and double quoted strings
    formula_without_strings = re.sub(r"""(?:"[^"]*"|'[^']*')""", "", formula)

    # Extract potential variable references from formula (without strings)
    tokens = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_.]*\b", formula_without_strings)

    # Filter out Python keywords and built-in functions
    excluded_tokens = {
        "if",
        "else",
        "elif",
        "and",
        "or",
        "not",
        "True",
        "False",
        "None",
        "abs",
        "round",
        "max",
        "min",
        "sum",
        "len",
        "int",
        "float",
        "str",
        "conditional",
        "iff",
        "f",
        "fstring",  # f is often used in f-strings
    }

    return [token for token in tokens if token not in excluded_tokens]


_COMPUTED_VARIABLE_COMPILATION_CACHE = FormulaCompilationCache(max_entries=500)


def clear_computed_variable_cache() -> None:
    """Clear the computed variable compilation cache. Useful for testing and memory management."""
    _COMPUTED_VARIABLE_COMPILATION_CACHE.clear()
    _LOGGER.debug("Cleared computed variable compilation cache")


def get_computed_variable_cache_stats() -> dict[str, Any]:
    """Get statistics about the computed variable compilation cache."""
    return _COMPUTED_VARIABLE_COMPILATION_CACHE.get_statistics()


def validate_computed_variable_references(variables: dict[str, Any], config_id: str | None = None) -> list[str]:
    """Validate that computed variables don't reference undefined variables.

    Args:
        variables: Dictionary of variables including computed variables
        config_id: Optional config ID for error context

    Returns:
        List of validation error messages
    """

    errors = []
    context_prefix = f"In {config_id}: " if config_id else ""

    # Get all available variable names (simple variables and computed variable names)
    available_vars = set(variables.keys())

    # Add common context variables that are always available
    always_available = {"state", "now", "today", "yesterday"}  # Common tokens
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
    if "unavailable" in str(error).lower() or "not defined" in str(error).lower():
        handler_formula = computed_var.exception_handler.unavailable
    elif "unknown" in str(error).lower():
        handler_formula = computed_var.exception_handler.unknown
    else:
        # For general errors, try unavailable handler first, then unknown
        handler_formula = computed_var.exception_handler.unavailable or computed_var.exception_handler.unknown

    if not handler_formula:
        return None

    try:
        # Use the same compilation cache for exception handler formulas
        compiled_handler = _COMPUTED_VARIABLE_COMPILATION_CACHE.get_compiled_formula(handler_formula)
        result = compiled_handler.evaluate(eval_context, numeric_only=False)
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
    for var_name, var_value in simple_variables.items():
        # Skip if this variable is already set in context (context has higher priority)
        if var_name in eval_context:
            _LOGGER.debug("Skipping config variable %s (already set in context)", var_name)
            continue

        resolved_value = resolver_callback(var_name, var_value, eval_context, sensor_config)
        if resolved_value is not None:
            eval_context[var_name] = resolved_value
            _LOGGER.debug("Resolved simple variable %s = %s", var_name, resolved_value)


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

    # Store error details separately to avoid modifying ComputedVariable objects
    error_details_map: dict[str, dict[str, Any]] = {}

    while remaining_vars and iteration < max_iterations:
        iteration += 1
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
                # Use the same compilation cache approach as main formulas
                compiled_formula = _COMPUTED_VARIABLE_COMPILATION_CACHE.get_compiled_formula(computed_var.formula)
                result = compiled_formula.evaluate(eval_context, numeric_only=False)

                eval_context[var_name] = result
                _LOGGER.debug("Resolved computed variable %s = %s", var_name, result)
                del remaining_vars[var_name]
                resolved_vars.add(var_name)
                made_progress = True

            except Exception as err:
                # Try exception handler before giving up
                exception_result = _try_exception_handler(var_name, computed_var, eval_context, err)

                if exception_result is not None:
                    # Exception handler succeeded - use its result
                    eval_context[var_name] = exception_result
                    _LOGGER.debug("Resolved computed variable %s using exception handler = %s", var_name, exception_result)
                    del remaining_vars[var_name]
                    resolved_vars.add(var_name)
                    made_progress = True
                    continue

                # Exception handler failed or not available - provide detailed error context
                error_details = _analyze_computed_variable_error(var_name, computed_var.formula, eval_context, err)
                _LOGGER.debug("Could not resolve computed variable %s: %s", var_name, error_details["summary"])

                # Store error details for final error reporting
                error_details_map[var_name] = error_details

                # Continue to next variable - maybe dependencies aren't ready yet
                continue

        if not made_progress:
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

    if remaining_vars:
        # Max iterations exceeded - likely circular dependencies
        remaining_var_names = list(remaining_vars.keys())
        formulas_info = [f"{name}: '{remaining_vars[name].formula}'" for name in remaining_var_names]

        raise MissingDependencyError(
            f"Could not resolve computed variables {remaining_var_names} within {max_iterations} iterations. "
            f"This likely indicates circular dependencies between variables:\n"
            + "\n".join(f"• {info}" for info in formulas_info)
        )
