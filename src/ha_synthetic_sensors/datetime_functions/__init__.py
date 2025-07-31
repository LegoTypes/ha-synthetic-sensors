"""DateTime functions module for synthetic sensors.

This module provides a modular, extensible system for datetime functions
that follows the established handler patterns in the synthetic sensors package.

The module is organized into:
- Protocol definitions for datetime function interfaces
- Base classes for common functionality
- Specific function implementations (timezone, date)
- Registry system for managing and routing function calls
- Handler integration with the evaluator system

Usage:
    # Get all datetime functions for registration with MathFunctions
    from ha_synthetic_sensors.datetime_functions import get_datetime_functions
    functions = get_datetime_functions()

    # Register custom datetime function handlers
    from ha_synthetic_sensors.datetime_functions import register_datetime_handler
    register_datetime_handler(MyCustomDateTimeHandler())

    # Use the datetime handler in the evaluator system
    from ha_synthetic_sensors.datetime_functions import DateTimeHandler
    handler = DateTimeHandler()
"""

from .datetime_handler import DateTimeHandler
from .function_registry import get_datetime_function_registry, get_datetime_functions, register_datetime_handler
from .protocol import DateTimeFunction, DateTimeFunctionProvider

__all__ = [
    "DateTimeFunction",
    "DateTimeFunctionProvider",
    "DateTimeHandler",
    "get_datetime_function_registry",
    "get_datetime_functions",
    "register_datetime_handler",
]
