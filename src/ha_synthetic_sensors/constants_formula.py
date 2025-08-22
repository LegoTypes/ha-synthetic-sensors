"""Formula evaluation constants for synthetic sensor package.

This module centralizes formula-related constants including reserved words,
HA state values, and other shared constants used across the evaluation system.
"""

from .constants_alternate import identify_alternate_state_value
from .math_functions import MathFunctions
from .shared_constants import BOOLEAN_LITERALS, MATH_FUNCTIONS, PYTHON_KEYWORDS, STRING_FUNCTIONS

# Define categorization mapping for string functions
_MULTI_PARAM_FUNCTION_NAMES = frozenset(
    {"contains", "startswith", "endswith", "replace", "replace_all", "split", "join", "pad_left", "pad_right", "center"}
)

# Derive string function categories from shared constants to avoid duplication
MULTI_PARAM_STRING_FUNCTIONS: frozenset[str] = STRING_FUNCTIONS & _MULTI_PARAM_FUNCTION_NAMES
BASIC_STRING_FUNCTIONS: frozenset[str] = STRING_FUNCTIONS - MULTI_PARAM_STRING_FUNCTIONS - {"str"}


# Validate that our categorization matches the shared constants at module load time
def _validate_string_function_categorization() -> None:
    """Validate that string function categories are consistent with shared constants."""
    categorized_functions = BASIC_STRING_FUNCTIONS | MULTI_PARAM_STRING_FUNCTIONS | {"str"}
    if categorized_functions != STRING_FUNCTIONS:
        missing_in_categorized = STRING_FUNCTIONS - categorized_functions
        missing_in_shared = categorized_functions - STRING_FUNCTIONS
        error_msg = "String function categorization mismatch. "
        if missing_in_categorized:
            error_msg += f"Missing in categorized: {sorted(missing_in_categorized)}. "
        if missing_in_shared:
            error_msg += f"Missing in shared: {sorted(missing_in_shared)}. "
        raise ValueError(error_msg)


# Perform validation at module import time
_validate_string_function_categorization()

# Get enhanced functions dynamically to include all available functions
_ENHANCED_FUNCTIONS = set(MathFunctions.get_all_functions().keys())

# Reserved words that should not be treated as variables in formulas
# These are Python keywords, boolean literals, and function names
FORMULA_RESERVED_WORDS: frozenset[str] = frozenset(
    PYTHON_KEYWORDS
    | BOOLEAN_LITERALS
    | MATH_FUNCTIONS
    | _ENHANCED_FUNCTIONS  # Include all enhanced math functions like minutes_between
    | {
        "len",
        "abs",
        "round",
        # Mathematical functions
        "sin",
        "cos",
        "tan",
        "sqrt",
        "pow",
        "exp",
        "log",
        "log10",
        # Special formula tokens
        "state",
        # Type conversion functions
        "date",  # Date conversion function: date('2025-01-01')
        # String manipulation functions (imported from STRING_FUNCTIONS)
        *STRING_FUNCTIONS,
    }
)

# Home Assistant state values that represent entity status
# These are semantic states, not string literals for formula evaluation
HA_STATE_VALUES: frozenset[str] = frozenset(
    {
        "unknown",  # Entity exists but has no current value
        "unavailable",  # Entity exists but is temporarily unavailable
        "none",  # String representation of None (converted to "unknown")
    }
)

# HA state values that should be converted to "unknown"
# These are alternative representations of the unknown state
HA_UNKNOWN_EQUIVALENTS: frozenset[str] = frozenset(
    {
        "None",  # String "None" should be converted to "unknown"
        "none",  # Lowercase "none" should be converted to "unknown"
    }
)

# Collection function names supported by the formula evaluator
COLLECTION_FUNCTIONS: frozenset[str] = MATH_FUNCTIONS

# Additional mathematical functions beyond the basic collection functions
ADDITIONAL_MATH_FUNCTIONS: frozenset[str] = frozenset(
    {
        "sqrt",  # Square root
        "pow",  # Power function
        "exp",  # Exponential
        "log",  # Natural logarithm
        "log10",  # Base-10 logarithm
        "sin",  # Sine
        "cos",  # Cosine
        "tan",  # Tangent
    }
)

# String function constants for error messages and defaults
DEFAULT_PADDING_CHAR: str = " "
COMMA_SEPARATOR: str = ","
STRING_TRUE: str = "true"
STRING_FALSE: str = "false"

# Error message templates for string functions
ERROR_MSG_PARAMETER_COUNT_EXACT: str = "{function}() requires exactly {expected} parameters, got {actual}"
ERROR_MSG_PARAMETER_COUNT_RANGE: str = "{function}() requires {min_params} or {max_params} parameters, got {actual}"
ERROR_MSG_FILL_CHAR_LENGTH: str = "{function}() fill character must be exactly 1 character"

# Pattern constants for tests to match error messages
ERROR_PATTERN_PARAMETER_COUNT_EXACT = r".*{function}\(\) requires exactly \d+ parameters, got \d+"
ERROR_PATTERN_PARAMETER_COUNT_RANGE = r".*{function}\(\) requires \d+ or \d+ parameters, got \d+"
ERROR_PATTERN_FILL_CHAR_LENGTH = r".*fill character must be exactly 1 character"

# All supported functions (collection + additional math)
SUPPORTED_FUNCTIONS: frozenset[str] = frozenset(COLLECTION_FUNCTIONS | ADDITIONAL_MATH_FUNCTIONS)

# Dependency status values
DEPENDENCY_STATUS_VALUES: frozenset[str] = frozenset(
    {
        "ok",  # Dependency is available and has a valid value
        "missing",  # Dependency cannot be resolved (fatal error)
        "unavailable",  # Dependency exists but is temporarily unavailable
        "unknown",  # Dependency exists but has no current value
    }
)

# Error types for dependency resolution
DEPENDENCY_ERROR_TYPES: frozenset[str] = frozenset(
    {
        "BackingEntityResolutionError",  # Backing entity cannot be resolved
        "MissingDependencyError",  # Required dependency is missing
        "DataValidationError",  # Data provider returned invalid data
        "CircularDependencyError",  # Circular dependency detected
    }
)


def is_reserved_word(word: str) -> bool:
    """Check if a word is a reserved word in formulas.

    Args:
        word: The word to check

    Returns:
        True if the word is reserved and should not be treated as a variable
    """
    return word in FORMULA_RESERVED_WORDS


def is_ha_unknown_equivalent(value: str) -> bool:
    """Check if a value should be converted to "unknown".

    Args:
        value: The value to check

    Returns:
        True if the value should be converted to "unknown"
    """
    return value in HA_UNKNOWN_EQUIVALENTS


def normalize_ha_state_value(value: str) -> str:
    """Normalize HA state values to consistent casing.

    Args:
        value: The state value to normalize

    Returns:
        Normalized state value (lowercase for HA states)
    """
    if is_ha_unknown_equivalent(value):
        return "unknown"
    # Use modern alternate state detection
    alt_state = identify_alternate_state_value(value.lower())
    return value.lower() if isinstance(alt_state, str) else value


def is_collection_function(function_name: str) -> bool:
    """Check if a function name is a collection function.

    Args:
        function_name: The function name to check

    Returns:
        True if the function is a collection function (sum, avg, max, min, count)
    """
    return function_name in COLLECTION_FUNCTIONS


def is_math_function(function_name: str) -> bool:
    """Check if a function name is a mathematical function.

    Args:
        function_name: The function name to check

    Returns:
        True if the function is a mathematical function
    """
    return function_name in MATH_FUNCTIONS or function_name in ADDITIONAL_MATH_FUNCTIONS


def is_supported_function(function_name: str) -> bool:
    """Check if a function name is supported by the formula evaluator.

    Args:
        function_name: The function name to check

    Returns:
        True if the function is supported
    """
    return function_name in SUPPORTED_FUNCTIONS


def is_dependency_status(status: str) -> bool:
    """Check if a value is a valid dependency status.

    Args:
        status: The status value to check

    Returns:
        True if the status is valid
    """
    return status in DEPENDENCY_STATUS_VALUES


def is_dependency_error_type(error_type: str) -> bool:
    """Check if an error type is a dependency-related error.

    Args:
        error_type: The error type to check

    Returns:
        True if the error type is dependency-related
    """
    return error_type in DEPENDENCY_ERROR_TYPES


def is_string_function(function_name: str) -> bool:
    """Check if a function name is a string manipulation function.

    Args:
        function_name: The function name to check

    Returns:
        True if the function is a string manipulation function
    """
    return function_name in STRING_FUNCTIONS


def is_basic_string_function(function_name: str) -> bool:
    """Check if a function name is a basic single-parameter string function.

    Args:
        function_name: The function name to check

    Returns:
        True if the function is a basic string function (single parameter)
    """
    return function_name in BASIC_STRING_FUNCTIONS


def is_multi_param_string_function(function_name: str) -> bool:
    """Check if a function name is an advanced multi-parameter string function.

    Args:
        function_name: The function name to check

    Returns:
        True if the function is a multi-parameter string function
    """
    return function_name in MULTI_PARAM_STRING_FUNCTIONS
