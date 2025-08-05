"""Constants for formula evaluation handlers.

CLEAN SLATE: Only handlers that are actually used after enhanced SimpleEval implementation.
"""

# Handler names (only used handlers)
HANDLER_NAME_METADATA = "metadata"
HANDLER_NAME_NUMERIC = "numeric"

# Handler type registration names (only used handlers)
HANDLER_TYPE_METADATA = "metadata"
HANDLER_TYPE_NUMERIC = "numeric"

# Handler factory error messages
ERROR_NO_HANDLER_FOR_FORMULA = "No handler can handle formula: '{formula}'. This indicates a routing configuration issue."

# Handler registration debug messages
DEBUG_REGISTERED_HANDLER = "Registered handler '{name}': {handler_name}"
DEBUG_REGISTERED_HANDLER_TYPE = "Registered handler type '{name}': {handler_type_name}"

# Note: Boolean constants removed since BooleanHandler was eliminated
# Enhanced SimpleEval handles all boolean operations natively
