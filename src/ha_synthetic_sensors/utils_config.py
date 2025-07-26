"""Configuration utilities for synthetic sensor package.

This module provides shared utilities for handling configuration variables
and other configuration-related operations to eliminate code duplication.
"""

import logging
from typing import Any, Callable

from .config_models import FormulaConfig
from .exceptions import MissingDependencyError
from .type_definitions import ContextValue

_LOGGER = logging.getLogger(__name__)


def resolve_config_variables(
    eval_context: dict[str, ContextValue],
    config: FormulaConfig | None,
    resolver_callback: Callable[[str, Any, dict[str, Any], Any | None], Any | None],
    sensor_config: Any = None,
) -> None:
    """Resolve config variables using the provided resolver callback.

    This is a shared utility to eliminate duplicate code between different
    phases that need to resolve configuration variables.

    Args:
        eval_context: The evaluation context to add resolved variables to
        config: The formula configuration containing variables
        resolver_callback: Callback function to resolve variables
        sensor_config: Optional sensor configuration for context
    """
    if not config:
        return

    for var_name, var_value in config.variables.items():
        # Skip if this variable is already set in context (context has higher priority)
        if var_name in eval_context:
            _LOGGER.debug("Skipping config variable %s (already set in context)", var_name)
            continue

        try:
            resolved_value = resolver_callback(var_name, var_value, eval_context, sensor_config)
            if resolved_value is not None:
                eval_context[var_name] = resolved_value
                _LOGGER.debug("Added config variable %s=%s", var_name, resolved_value)
            else:
                raise MissingDependencyError(
                    f"Config variable '{var_name}' in formula '{config.name or config.id}' resolved to None"
                )
        except Exception as err:
            raise MissingDependencyError(f"Error resolving config variable '{var_name}': {err}") from err
