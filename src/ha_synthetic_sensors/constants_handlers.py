"""Constants for formula evaluation handlers."""

# Handler names
HANDLER_NAME_METADATA = "metadata"
HANDLER_NAME_STRING = "string"
HANDLER_NAME_NUMERIC = "numeric"
HANDLER_NAME_BOOLEAN = "boolean"
HANDLER_NAME_DATE = "date"

# Handler type registration names
HANDLER_TYPE_METADATA = "metadata"
HANDLER_TYPE_STRING = "string"
HANDLER_TYPE_NUMERIC = "numeric"
HANDLER_TYPE_BOOLEAN = "boolean"
HANDLER_TYPE_DATE = "date"

# Handler factory error messages
ERROR_NO_HANDLER_FOR_FORMULA = "No handler can handle formula: '{formula}'. This indicates a routing configuration issue."

# Handler registration debug messages
DEBUG_REGISTERED_HANDLER = "Registered handler '{name}': {handler_name}"
DEBUG_REGISTERED_HANDLER_TYPE = "Registered handler type '{name}': {handler_type_name}"

# Boolean handler constants
BOOLEAN_OPERATORS = frozenset({"and", "or", "not"})
BOOLEAN_COMPARISON_OPERATORS = frozenset({"<", ">", "<=", ">=", "==", "!=", "="})
BOOLEAN_LITERAL_VALUES = frozenset({"True", "False"})
BOOLEAN_STATE_FUNCTIONS = frozenset({"is_on", "is_off", "is_home", "is_away"})

# Boolean handler error messages
ERROR_BOOLEAN_RESULT_TYPE = "Boolean formula result must be boolean, got {type_name}: {result}"
