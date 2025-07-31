"""DateTime functions module for synthetic sensors.

This module provides a modular, extensible system for datetime functions
that follows the established handler patterns in the synthetic sensors package.

The module is organized into:
- Protocol definitions for datetime function interfaces
- Base classes for common functionality
- Specific function implementations (timezone, date)
- Registry system for managing and routing function calls

Usage:
    # Get all datetime functions for registration with MathFunctions
    from ha_synthetic_sensors.datetime_functions import get_datetime_functions
    functions = get_datetime_functions()

    # Register custom datetime function handlers
    from ha_synthetic_sensors.datetime_functions import register_datetime_handler
    register_datetime_handler(MyCustomDateTimeHandler())

    # Use the datetime handler directly from its module
    from ha_synthetic_sensors.datetime_functions.datetime_handler import DateTimeHandler
    handler = DateTimeHandler()
"""

# Import only what's needed for math_functions integration
from .function_registry import get_datetime_function_registry, get_datetime_functions, register_datetime_handler
from .protocol import DateTimeFunction, DateTimeFunctionProvider

__all__ = [
    "DateTimeFunction",
    "DateTimeFunctionProvider",
    "get_datetime_function_registry",
    "get_datetime_functions",
    "register_datetime_handler",
]
