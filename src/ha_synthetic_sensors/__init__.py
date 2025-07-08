"""Home Assistant Synthetic Sensors Package.

A reusable package for creating and managing synthetic sensors in Home Assistant
integrations using formula-based calculations and YAML configuration.
"""

import logging
from typing import Any

# Public API - Core classes needed by integrations
from .config_manager import FormulaConfig, SensorConfig

# Public API - Utility classes
from .device_association import DeviceAssociationHelper
from .entity_factory import EntityDescription, EntityFactory

# Public API - Integration helpers
from .integration import (
    SyntheticSensorsIntegration,
    async_create_sensor_manager,
    async_reload_integration,
    async_setup_integration,
    async_unload_integration,
    get_example_config,
    get_integration,
    validate_yaml_content,
)
from .sensor_set import SensorSet
from .storage_manager import StorageManager

# Public API - Type definitions
from .types import DataProviderCallback, DataProviderResult


async def async_setup_synthetic_sensors(
    hass: Any,
    config_entry: Any,
    async_add_entities: Any,
    storage_manager: Any,
    device_identifier: str,
    data_provider_callback: DataProviderCallback | None = None,
) -> Any:
    """Recommended setup pattern for synthetic sensors in HA integrations.

    This is the simplified, recommended way to integrate synthetic sensors
    into your Home Assistant custom integration.

    Args:
        hass: Home Assistant instance
        config_entry: Integration's ConfigEntry
        async_add_entities: AddEntitiesCallback from sensor platform
        storage_manager: StorageManager with sensor configurations
        device_identifier: Device identifier for entity IDs
        data_provider_callback: Optional callback for live data

    Returns:
        SensorManager: Configured sensor manager

    Example:
        ```python
        # In your sensor.py platform
        from ha_synthetic_sensors import async_setup_synthetic_sensors

        async def async_setup_entry(hass, config_entry, async_add_entities):
            # Your native sensors first
            async_add_entities(native_sensors)

            # Then synthetic sensors
            storage_manager = hass.data[DOMAIN][config_entry.entry_id]["storage_manager"]
            sensor_manager = await async_setup_synthetic_sensors(
                hass=hass,
                config_entry=config_entry,
                async_add_entities=async_add_entities,
                storage_manager=storage_manager,
                device_identifier=coordinator.device_id,
                data_provider_callback=create_data_provider(coordinator),
            )
        ```
    """
    from .integration import async_create_sensor_manager

    # Get device info if available (integration-specific)
    device_info = None
    if hasattr(config_entry, "data"):
        # Let the integration provide device_info if needed
        integration_data = hass.data.get(config_entry.domain, {}).get(config_entry.entry_id, {})
        device_info = integration_data.get("device_info")

    # Create sensor manager using the simple helper
    sensor_manager = await async_create_sensor_manager(
        hass=hass,
        integration_domain=config_entry.domain,
        add_entities_callback=async_add_entities,
        device_info=device_info,
        data_provider_callback=data_provider_callback,
    )

    # Register backing entities if available
    if hasattr(storage_manager, "get_registered_entities"):
        backing_entities = storage_manager.get_registered_entities()
        sensor_manager.register_data_provider_entities(backing_entities)

    # Load configuration from storage
    config = storage_manager.to_config(device_identifier=device_identifier)
    await sensor_manager.load_configuration(config)

    return sensor_manager


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
    "DataProviderCallback",
    "DataProviderResult",
    "DeviceAssociationHelper",
    "EntityDescription",
    "EntityFactory",
    "FormulaConfig",
    "SensorConfig",
    "SensorSet",
    "StorageManager",
    "SyntheticSensorsIntegration",
    "async_create_sensor_manager",
    "async_reload_integration",
    "async_setup_integration",
    "async_setup_synthetic_sensors",
    "async_unload_integration",
    "configure_logging",
    "get_example_config",
    "get_integration",
    "get_logging_info",
    "test_logging",
    "validate_yaml_content",
]
