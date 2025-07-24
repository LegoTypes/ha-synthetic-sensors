"""Formula evaluation constants for synthetic sensor package.

This module centralizes formula-related constants including reserved words,
HA state values, and other shared constants used across the evaluation system.
"""

from .shared_constants import BOOLEAN_LITERALS, MATH_FUNCTIONS, PYTHON_KEYWORDS

# Reserved words that should not be treated as variables in formulas
# These are Python keywords, boolean literals, and function names
FORMULA_RESERVED_WORDS: frozenset[str] = frozenset(
    PYTHON_KEYWORDS
    | BOOLEAN_LITERALS
    | MATH_FUNCTIONS
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


def is_ha_state_value(value: str) -> bool:
    """Check if a value is a Home Assistant state value.

    Args:
        value: The value to check

    Returns:
        True if the value represents an HA state (unknown, unavailable, etc.)
    """
    return value in HA_STATE_VALUES


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
    return value.lower() if is_ha_state_value(value.lower()) else value


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
