"""Home Assistant Synthetic Sensors Package.

A reusable package for creating and managing synthetic sensors in Home Assistant
integrations using formula-based calculations and YAML configuration.
"""

import logging

from .config_manager import ConfigManager
from .evaluator import Evaluator
from .integration import (
    SyntheticSensorsIntegration,
    async_reload_integration,
    async_setup_integration,
    async_unload_integration,
    get_example_config,
    get_integration,
    validate_yaml_content,
)
from .name_resolver import NameResolver
from .sensor_manager import SensorManager
from .service_layer import ServiceLayer


def configure_logging(level: int = logging.DEBUG) -> None:
    """Configure logging level for the ha_synthetic_sensors package.

    This function ensures that all synthetic sensors logging will be visible
    by properly configuring the logger hierarchy and ensuring handlers are set up.

    Args:
        level: Logging level (default: logging.DEBUG)

    Example:
        import ha_synthetic_sensors
        ha_synthetic_sensors.configure_logging(logging.DEBUG)
    """
    # Get the root package logger
    package_logger = logging.getLogger("ha_synthetic_sensors")
    package_logger.setLevel(level)

    # Configure all child module loggers explicitly
    module_loggers = [
        "ha_synthetic_sensors.evaluator",
        "ha_synthetic_sensors.service_layer",
        "ha_synthetic_sensors.collection_resolver",
        "ha_synthetic_sensors.variable_resolver",
        "ha_synthetic_sensors.config_manager",
        "ha_synthetic_sensors.sensor_manager",
        "ha_synthetic_sensors.name_resolver",
        "ha_synthetic_sensors.dependency_parser",
        "ha_synthetic_sensors.integration",
        "ha_synthetic_sensors.entity_factory",
    ]

    for logger_name in module_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        # Ensure the logger propagates to its parent (which should have handlers)
        logger.propagate = True

    # Also set the main package logger to propagate to root loggers
    package_logger.propagate = True

    # Add a test log message to verify configuration worked
    package_logger.info("Synthetic sensors logging configured at level: %s", logging.getLevelName(level))


def get_logging_info() -> dict[str, str]:
    """Get current logging configuration for debugging.

    Returns:
        Dictionary with logger names, their effective levels, and handler info
    """
    package_logger = logging.getLogger("ha_synthetic_sensors")

    loggers_info = {
        "ha_synthetic_sensors": f"{logging.getLevelName(package_logger.getEffectiveLevel())} (handlers: {len(package_logger.handlers)}, propagate: {package_logger.propagate})",
        "ha_synthetic_sensors.evaluator": f"{logging.getLevelName(logging.getLogger('ha_synthetic_sensors.evaluator').getEffectiveLevel())}",
        "ha_synthetic_sensors.service_layer": f"{logging.getLevelName(logging.getLogger('ha_synthetic_sensors.service_layer').getEffectiveLevel())}",
        "ha_synthetic_sensors.collection_resolver": f"{logging.getLevelName(logging.getLogger('ha_synthetic_sensors.collection_resolver').getEffectiveLevel())}",
        "ha_synthetic_sensors.config_manager": f"{logging.getLevelName(logging.getLogger('ha_synthetic_sensors.config_manager').getEffectiveLevel())}",
    }

    return loggers_info


def test_logging() -> None:
    """Test function to verify logging is working across all modules.

    Call this after configure_logging() to verify that log messages
    from the synthetic sensors package are being output correctly.
    """
    # Test logging from various modules
    logging.getLogger("ha_synthetic_sensors").info("TEST: Main package logger")
    logging.getLogger("ha_synthetic_sensors.evaluator").debug("TEST: Evaluator debug message")
    logging.getLogger("ha_synthetic_sensors.service_layer").debug("TEST: Service layer debug message")
    logging.getLogger("ha_synthetic_sensors.config_manager").debug("TEST: Config manager debug message")


__version__ = "0.1.0"
__all__ = [
    "ConfigManager",
    "Evaluator",
    "NameResolver",
    "SensorManager",
    "ServiceLayer",
    "SyntheticSensorsIntegration",
    "async_reload_integration",
    "async_setup_integration",
    "async_unload_integration",
    "configure_logging",
    "get_example_config",
    "get_integration",
    "get_logging_info",
    "test_logging",
    "validate_yaml_content",
]
