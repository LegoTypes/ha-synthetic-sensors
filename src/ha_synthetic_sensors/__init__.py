"""Home Assistant Synthetic Sensors Package.

A reusable package for creating and managing synthetic sensors in Home Assistant
integrations using formula-based calculations and YAML configuration.

Usage:
    # Lightweight imports - only import what you need
    import ha_synthetic_sensors
    from ha_synthetic_sensors import config_manager
    from ha_synthetic_sensors import sensor_manager

    # Or import specific classes when you need them
    from ha_synthetic_sensors.config_manager import ConfigManager
    from ha_synthetic_sensors.sensor_manager import SensorManager
"""

import logging


def configure_logging(level: int = logging.DEBUG) -> None:
    """Configure logging level for the ha_synthetic_sensors package.

    Call this function from your integration's setup to enable debug logging
    for the synthetic sensors package.

    Args:
        level: Logging level (default: logging.DEBUG)

    Example:
        import ha_synthetic_sensors
        ha_synthetic_sensors.configure_logging(logging.DEBUG)
    """
    logger = logging.getLogger(__name__)
    logger.setLevel(level)

    # Also configure specific module loggers that do heavy logging
    heavy_loggers = [
        "ha_synthetic_sensors.evaluator",
        "ha_synthetic_sensors.service_layer",
        "ha_synthetic_sensors.collection_resolver",
        "ha_synthetic_sensors.variable_resolver",
    ]

    for logger_name in heavy_loggers:
        logging.getLogger(logger_name).setLevel(level)


def get_logging_info() -> dict[str, str]:
    """Get current logging configuration for debugging.

    Returns:
        Dictionary with logger names and their effective levels
    """
    package_logger = logging.getLogger(__name__)

    loggers_info = {
        "ha_synthetic_sensors": logging.getLevelName(package_logger.getEffectiveLevel()),
        "ha_synthetic_sensors.evaluator": logging.getLevelName(
            logging.getLogger("ha_synthetic_sensors.evaluator").getEffectiveLevel()
        ),
        "ha_synthetic_sensors.service_layer": logging.getLevelName(
            logging.getLogger("ha_synthetic_sensors.service_layer").getEffectiveLevel()
        ),
        "ha_synthetic_sensors.collection_resolver": logging.getLevelName(
            logging.getLogger("ha_synthetic_sensors.collection_resolver").getEffectiveLevel()
        ),
    }

    return loggers_info


__version__ = "0.1.0"
__all__ = [
    "configure_logging",
    "get_logging_info",
]
