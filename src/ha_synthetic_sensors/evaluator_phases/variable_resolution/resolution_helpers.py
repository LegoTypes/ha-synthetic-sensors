"""Helper functions for variable resolution to avoid code duplication."""

import logging
from typing import Any

from ha_synthetic_sensors.reference_value_manager import ReferenceValueManager
from ha_synthetic_sensors.type_definitions import ContextValue

_LOGGER = logging.getLogger(__name__)


class ResolutionHelpers:
    """Helper functions for variable resolution operations."""

    @staticmethod
    def log_and_set_resolved_variable(
        eval_context: dict[str, ContextValue],
        var_name: str,
        var_value: Any,
        resolved_value: Any,
        context_name: str = "RESOLUTION",
    ) -> None:
        """Log variable resolution and set it using ReferenceValueManager.

        Args:
            eval_context: The evaluation context to update
            var_name: The variable name
            var_value: The original variable value
            resolved_value: The resolved value
            context_name: Context name for logging (e.g., "VARIABLE_INHERITANCE", "VARIABLE_RESOLUTION")
        """
        _LOGGER.debug(
            "%s_DEBUG: %s -> %s returned %s (type: %s)",
            context_name,
            var_name,
            var_value,
            resolved_value,
            type(resolved_value).__name__,
        )
        ReferenceValueManager.set_variable_with_reference_value(eval_context, var_name, var_value, resolved_value)
