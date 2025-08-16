"""Evaluation result constants for synthetic sensor package.

This module centralizes constants used in evaluation results including
result keys, state values, and other shared constants used across the
evaluation system.
"""

# Evaluation result dictionary keys
RESULT_KEY_SUCCESS = "success"
RESULT_KEY_VALUE = "value"
RESULT_KEY_ERROR = "error"
RESULT_KEY_STATE = "state"
RESULT_KEY_CACHED = "cached"
RESULT_KEY_UNAVAILABLE_DEPENDENCIES = "unavailable_dependencies"
RESULT_KEY_MISSING_DEPENDENCIES = "missing_dependencies"

# Evaluation state values
STATE_OK = "ok"
STATE_UNAVAILABLE = "unavailable"
STATE_UNKNOWN = "unknown"

# Error message keywords for error classification
ERROR_KEYWORD_UNDEFINED = "undefined"
ERROR_KEYWORD_NOT_DEFINED = "not defined"
ERROR_KEYWORD_NAME = "name"
ERROR_KEYWORD_VARIABLE = "variable"
ERROR_KEYWORD_DIVISION_BY_ZERO = "division by zero"

# Valid result keys for different result types
SUCCESS_RESULT_KEYS = frozenset(
    {
        RESULT_KEY_UNAVAILABLE_DEPENDENCIES,
        RESULT_KEY_MISSING_DEPENDENCIES,
        RESULT_KEY_VALUE,
    }
)

ERROR_RESULT_KEYS = frozenset(
    {
        RESULT_KEY_CACHED,
        RESULT_KEY_UNAVAILABLE_DEPENDENCIES,
        RESULT_KEY_MISSING_DEPENDENCIES,
    }
)

# All valid evaluation result keys
VALID_RESULT_KEYS = frozenset(
    {
        RESULT_KEY_SUCCESS,
        RESULT_KEY_VALUE,
        RESULT_KEY_ERROR,
        RESULT_KEY_STATE,
        RESULT_KEY_CACHED,
        RESULT_KEY_UNAVAILABLE_DEPENDENCIES,
        RESULT_KEY_MISSING_DEPENDENCIES,
    }
)
