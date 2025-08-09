"""Home Assistant Synthetic Sensors Package.

A reusable package for creating and managing synthetic sensors in Home Assistant
integrations using formula-based calculations and YAML configuration.
"""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

# Public API - Core classes needed by integrations
from .config_models import FormulaConfig, SensorConfig

# Public API - Utility classes
from .device_association import DeviceAssociationHelper
from .entity_factory import EntityDescription, EntityFactory

# Public API - Exceptions
from .exceptions import SyntheticSensorsConfigError

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
from .sensor_manager import SensorManager
from .sensor_set import SensorSet
from .storage_manager import StorageManager

# Public API - Type definitions
from .type_definitions import DataProviderCallback, DataProviderChangeNotifier, DataProviderResult


def _register_backing_entities_and_mappings(
    sensor_manager: SensorManager,
    backing_entity_ids: set[str] | None,
    sensor_to_backing_mapping: dict[str, str] | None,
    change_notifier: DataProviderChangeNotifier | None,
    logger: logging.Logger,
) -> None:
    """Register backing entities and mappings with the sensor manager."""
    # Register explicit backing entities if provided directly
    if backing_entity_ids is not None:
        if backing_entity_ids:  # Non-empty set
            logger.info("Registering explicit backing entities with sensor manager...")
            sensor_manager.register_data_provider_entities(backing_entity_ids, change_notifier)
            logger.info("Explicit backing entities registered successfully")

            # Also register sensor-to-backing mapping if provided for state token resolution
            if sensor_to_backing_mapping:
                sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)
                logger.info("Sensor-to-backing mapping registered for state token resolution")
        else:
            # Empty set provided explicitly - this is an error
            raise SyntheticSensorsConfigError(
                "Empty backing entity set provided explicitly. Use None for HA-only mode, or provide actual backing entities."
            )
    # Register explicit backing entities if provided via mapping
    elif sensor_to_backing_mapping is not None:
        logger.info("Registering sensor-to-backing mapping with sensor manager...")
        # Extract backing entity IDs from the mapping
        backing_entity_ids = set(sensor_to_backing_mapping.values())
        if backing_entity_ids:  # Only register if we have actual entities
            sensor_manager.register_data_provider_entities(backing_entity_ids, change_notifier)
            # Register the mapping for state token resolution
            sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)
            logger.info("Sensor-to-backing mapping registered successfully")
        else:
            logger.info("Empty sensor-to-backing mapping provided - variables will use HA entity references")
    else:
        # No backing entities provided - sensors will use HA entity references or direct values
        logger.debug("No backing entities provided - sensors will use HA entity references or direct values")


def rebind_backing_entities(
    sensor_manager: SensorManager,
    backing_entity_ids: set[str],
    change_notifier: DataProviderChangeNotifier | None,
    *,
    trigger_initial_update: bool = True,
    logger: logging.Logger | None = None,
) -> None:
    """Rebind data-provider entities and optionally trigger a coarse update.

    Common helper for integrations to call after initial setup or CRUD operations
    (e.g., adding solar or named circuits) so newly added sensors evaluate immediately.
    """
    log = logger or logging.getLogger(__name__)
    if not backing_entity_ids:
        return

    try:
        sensor_manager.register_data_provider_entities(backing_entity_ids, change_notifier)
    except Exception as err:
        log.warning("Failed to register backing entities with notifier: %s", err)
        return

    if trigger_initial_update and change_notifier is not None:
        try:
            change_notifier(backing_entity_ids)
        except Exception as err:
            log.warning("Failed to trigger initial update after rebind: %s", err)


def _log_configuration_details(config: Any, device_identifier: str) -> None:
    """Log detailed configuration information."""
    if not config or not config.sensors:
        logging.getLogger(__name__).error("No sensors found in configuration - this is a fatal error")
        raise ValueError(f"No sensors found in configuration for device {device_identifier}")

    logging.getLogger(__name__).info("Configuration contains %d sensors:", len(config.sensors))
    for sensor in config.sensors:
        logging.getLogger(__name__).info("  Sensor: %s", sensor.unique_id)
        logging.getLogger(__name__).info("    Entity ID: %s", sensor.entity_id or "None")
        logging.getLogger(__name__).info("    Name: %s", sensor.name)
        if sensor.formulas:
            for formula in sensor.formulas:
                logging.getLogger(__name__).info("    Formula '%s': %s", formula.id, formula.formula)
                if formula.variables:
                    logging.getLogger(__name__).info("      Variables:")
                    for var_name, var_value in formula.variables.items():
                        logging.getLogger(__name__).info("        %s: %s", var_name, var_value)


async def async_setup_synthetic_sensors(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    storage_manager: StorageManager,
    device_identifier: str,
    data_provider_callback: DataProviderCallback | None = None,
    change_notifier: DataProviderChangeNotifier | None = None,
    sensor_to_backing_mapping: dict[str, str] | None = None,
) -> SensorManager:
    """Set up synthetic sensors with storage-based configuration.

    This is the recommended pattern for most integrations. It uses storage-based
    configuration and provides a clean interface for synthetic sensor management.

    Args:
        hass: Home Assistant instance
        config_entry: Integration's ConfigEntry
        async_add_entities: AddEntitiesCallback from sensor platform
        storage_manager: Pre-configured StorageManager instance
        device_identifier: Device identifier for entity IDs and sensor set ID
        data_provider_callback: Optional callback for live data
        change_notifier: Optional callback for change notifications
        sensor_to_backing_mapping: Optional mapping from sensor unique IDs to backing entity IDs

    Returns:
        Configured SensorManager instance

    Example:
        ```python
        # In your sensor.py platform
        from ha_synthetic_sensors import async_setup_synthetic_sensors

        async def async_setup_entry(hass, config_entry, async_add_entities):
            # Create your native sensors first
            native_entities = create_native_sensors(coordinator)
            async_add_entities(native_entities)

            # Set up synthetic sensors with one call
            sensor_manager = await async_setup_synthetic_sensors(
                hass=hass,
                config_entry=config_entry,
                async_add_entities=async_add_entities,
                storage_manager=storage_manager,
                device_identifier=coordinator.device_id,
                data_provider_callback=create_data_provider_callback(coordinator),
                change_notifier=create_change_notifier_callback(sensor_manager),
                # Variables automatically try backing entities first, then HA fallback
            )
        ```
    """
    logger = logging.getLogger(__name__)
    logger.info("=== SYNTHETIC SENSORS SETUP DEBUG ===")
    logger.info("Setting up synthetic sensors for device: %s", device_identifier)

    # Get device info if available (integration-specific)
    device_info = None
    if hasattr(config_entry, "data"):
        integration_data = hass.data.get(config_entry.domain, {}).get(config_entry.entry_id, {})
        device_info = integration_data.get("device_info")

    # Create sensor manager
    sensor_manager = await async_create_sensor_manager(
        hass=hass,
        integration_domain=config_entry.domain,
        add_entities_callback=async_add_entities,
        device_info=device_info,
        data_provider_callback=data_provider_callback,
        device_identifier=device_identifier,
    )

    # Register backing entities if provided and non-empty
    backing_entity_ids: set[str] | None = None
    if sensor_to_backing_mapping:
        backing_entity_ids = set(sensor_to_backing_mapping.values())
        if backing_entity_ids:  # Only register if we have actual entities
            sensor_manager.register_data_provider_entities(backing_entity_ids, change_notifier)
            sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)
            logger.info("Sensor-to-backing mapping registered successfully")
        else:
            logger.info("Empty sensor-to-backing mapping provided - variables will use HA entity references")
    else:
        logger.debug("No sensor-to-backing mapping provided - sensors will use HA entity references or direct values")

    # CRITICAL: Register sensor manager with storage manager for entity change notifications
    # This must happen before loading configuration to ensure proper dependency tracking
    sensor_manager.register_with_storage_manager(storage_manager)

    # Load configuration from storage
    config = storage_manager.to_config(device_identifier=device_identifier)
    logger.info("Loading configuration for device: %s", device_identifier)

    # Log the configuration details
    _log_configuration_details(config, device_identifier)

    await sensor_manager.load_configuration(config)
    logger.info("Configuration loaded successfully")

    # Trigger an initial coarse update if backing entities were provided
    initial_backing_ids: set[str] = set()
    if backing_entity_ids is not None:
        initial_backing_ids = backing_entity_ids
    elif sensor_to_backing_mapping is not None:
        initial_backing_ids = set(sensor_to_backing_mapping.values())

    if change_notifier and initial_backing_ids:
        logger.debug(
            "Triggering initial coarse update for %d backing entities",
            len(initial_backing_ids),
        )
        try:
            change_notifier(initial_backing_ids)
        except Exception as err:
            logger.warning("Initial coarse update failed: %s", err)

    logger.info("=== END SYNTHETIC SENSORS SETUP DEBUG ===")

    return sensor_manager


async def async_setup_synthetic_sensors_with_entities(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    storage_manager: StorageManager,
    device_identifier: str,
    data_provider_callback: DataProviderCallback | None = None,
    change_notifier: DataProviderChangeNotifier | None = None,
    backing_entity_ids: set[str] | None = None,
    sensor_to_backing_mapping: dict[str, str] | None = None,
) -> SensorManager:
    """Simplified setup pattern for synthetic sensors with explicit backing entities.

    This function allows direct specification of backing entity IDs for integrations
    that manage virtual entities separately from sensor-to-backing mapping.

    Args:
        hass: Home Assistant instance
        config_entry: Integration's ConfigEntry
        async_add_entities: Callback to add entities to HA
        storage_manager: Storage manager for sensor configuration
        device_identifier: Device identifier for sensor grouping
        data_provider_callback: Optional callback for providing entity data
        change_notifier: Optional callback for real-time change notifications
        backing_entity_ids: Set of backing entity IDs to register (or None for HA-only mode)
        sensor_to_backing_mapping: Optional mapping for state token resolution

    Returns:
        SensorManager: Configured sensor manager
    """

    logger = logging.getLogger(__name__)

    # Log the setup parameters
    logger.info("=== SYNTHETIC SENSORS SETUP DEBUG ===")
    logger.info("Setting up synthetic sensors with entities:")
    logger.info("  Device identifier: %s", device_identifier)

    logger.info("  Data provider callback: %s", "Provided" if data_provider_callback else "None")
    logger.info("  Change notifier: %s", "Provided" if change_notifier else "None")

    if sensor_to_backing_mapping:
        logger.info("  Sensor-to-backing mapping provided (%d mappings):", len(sensor_to_backing_mapping))
        for sensor_key, backing_entity_id in sorted(sensor_to_backing_mapping.items()):
            logger.info("    %s -> %s", sensor_key, backing_entity_id)
    else:
        logger.info("  No sensor-to-backing mapping provided")

    # Get device info if available (integration-specific)
    device_info = None
    if hasattr(config_entry, "data"):
        # Let the integration provide device_info if needed
        integration_data = hass.data.get(config_entry.domain, {}).get(config_entry.entry_id, {})
        device_info = integration_data.get("device_info")

    # CRITICAL: Validate domain consistency to prevent entity registration conflicts
    # Tests may pass a MagicMock for config_entry.domain; only validate when domain is a real string
    logger.info("=== DOMAIN VALIDATION ===")
    logger.info("Config entry domain: %s", getattr(config_entry, "domain", None))
    logger.info("Storage manager integration domain: %s", storage_manager.integration_domain)

    integration_domain_obj = getattr(config_entry, "domain", None)
    integration_domain = (
        integration_domain_obj if isinstance(integration_domain_obj, str) else storage_manager.integration_domain
    )

    if isinstance(integration_domain_obj, str) and storage_manager.integration_domain != integration_domain:
        logger.error(
            "DOMAIN MISMATCH: StorageManager integration_domain '%s' != ConfigEntry domain '%s'",
            storage_manager.integration_domain,
            integration_domain,
        )
        raise ValueError(
            f"Domain mismatch: StorageManager expects '{storage_manager.integration_domain}' "
            f"but ConfigEntry has '{integration_domain}'. This will cause entity registration conflicts."
        )

    logger.info("Using integration domain: %s", integration_domain)

    # Create sensor manager using the simple helper
    sensor_manager = await async_create_sensor_manager(
        hass=hass,
        integration_domain=integration_domain,
        add_entities_callback=async_add_entities,
        device_info=device_info,
        data_provider_callback=data_provider_callback,
        device_identifier=device_identifier,
    )

    # Register backing entities and mappings
    _register_backing_entities_and_mappings(
        sensor_manager, backing_entity_ids, sensor_to_backing_mapping, change_notifier, logger
    )

    # CRITICAL: Register sensor manager with storage manager for entity change notifications
    # This must happen before loading configuration to ensure proper dependency tracking
    sensor_manager.register_with_storage_manager(storage_manager)

    # Load configuration from storage
    config = storage_manager.to_config(device_identifier=device_identifier)
    logger.info("Loading configuration for device: %s", device_identifier)

    # Log the configuration details
    _log_configuration_details(config, device_identifier)

    await sensor_manager.load_configuration(config)
    logger.info("Configuration loaded successfully")
    logger.info("=== END SYNTHETIC SENSORS SETUP DEBUG ===")

    return sensor_manager


async def async_setup_synthetic_integration(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    integration_domain: str,
    device_identifier: str,
    sensor_configs: list[SensorConfig],
    sensor_to_backing_mapping: dict[str, str] | None = None,
    data_provider_callback: DataProviderCallback | None = None,
    sensor_set_name: str | None = None,
    change_notifier: DataProviderChangeNotifier | None = None,
) -> tuple[StorageManager, SensorManager]:
    """Complete setup pattern for synthetic sensors following logical flow.

    This function follows the logical sequence:
    1. Setup StorageManager
    2. Get/Create SensorSet from StorageManager
    3. Define YAML configuration + backing entities (provided by caller)
    4. Load everything in one atomic operation with change detection

    Args:
        hass: Home Assistant instance
        config_entry: Integration's ConfigEntry
        async_add_entities: AddEntitiesCallback from sensor platform
        integration_domain: Domain name for the integration
        device_identifier: Device identifier for entity IDs and sensor set ID
        sensor_configs: List of SensorConfig objects defining the sensors
        sensor_to_backing_mapping: Optional mapping from sensor unique IDs to backing entity IDs
        data_provider_callback: Optional callback for live data
        sensor_set_name: Optional name for the sensor set (defaults to device-based name)
        allow_ha_lookups: If True, backing entities can fall back to HA state lookups
                        when not found in data provider. If False (default), backing
                        entities are always virtual and only use data provider callback.
        change_notifier: Optional callback that the integration can call when backing
                       entity data changes to trigger selective sensor updates.

    Returns:
        Tuple of (StorageManager, SensorManager): Both configured and ready

    Example:
        ```python
        # In your sensor.py platform
        from ha_synthetic_sensors import async_setup_synthetic_integration, SensorConfig, FormulaConfig

        async def async_setup_entry(hass, config_entry, async_add_entities):
            # Your native sensors first
            async_add_entities(native_sensors)

            # Define your synthetic sensor configurations
            sensor_configs = [
                SensorConfig(
                    unique_id="main_power",
                    name="Main Power",
                    entity_id="sensor.span_main_power",
                    device_identifier=device_id,
                    formulas=[FormulaConfig(
                        id="main",
                        formula="source_value",
                        variables={"source_value": "sensor.span_backing_main_power"}
                    )]
                )
            ]

            backing_entities = {"sensor.span_backing_main_power"}

            # One call sets up everything
            storage_manager, sensor_manager = await async_setup_synthetic_integration(
                hass=hass,
                config_entry=config_entry,
                async_add_entities=async_add_entities,
                integration_domain=DOMAIN,
                device_identifier=coordinator.device_id,
                sensor_configs=sensor_configs,
                sensor_to_backing_mapping=backing_entities, # Pass the mapping
                data_provider_callback=create_data_provider(coordinator),
            )
        ```
    """

    # Setup StorageManager
    storage_manager = StorageManager(hass, f"{integration_domain}_synthetic", integration_domain=integration_domain)
    await storage_manager.async_load()

    # Get/Create SensorSet from StorageManager
    sensor_set_id = f"{device_identifier}_sensors"
    sensor_set_display_name = sensor_set_name or f"{integration_domain.title()} {device_identifier} Sensors"

    if storage_manager.sensor_set_exists(sensor_set_id):
        sensor_set = storage_manager.get_sensor_set(sensor_set_id)

        # Existing storage - preserve user customizations
        # Only add new sensors that don't exist
        existing_sensor_ids = {s.unique_id for s in sensor_set.list_sensors()}
        new_sensors = [s for s in sensor_configs if s.unique_id not in existing_sensor_ids]

        if new_sensors:
            for sensor_config in new_sensors:
                await sensor_set.async_add_sensor(sensor_config)
    else:
        # Fresh install - create sensor set with provided configurations
        await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier=device_identifier,
            name=sensor_set_display_name,
        )
        sensor_set = storage_manager.get_sensor_set(sensor_set_id)
        await sensor_set.async_replace_sensors(sensor_configs)

    # Configuration is already defined (provided by caller as sensor_configs)

    # Load everything in one atomic operation with change detection

    # Get device info if available (integration-specific)
    device_info = None
    if hasattr(config_entry, "data"):
        integration_data = hass.data.get(integration_domain, {}).get(config_entry.entry_id, {})
        device_info = integration_data.get("device_info")

    # Create sensor manager
    sensor_manager = await async_create_sensor_manager(
        hass=hass,
        integration_domain=integration_domain,
        add_entities_callback=async_add_entities,
        device_info=device_info,
        data_provider_callback=data_provider_callback,
    )

    # Register backing entities if provided and non-empty
    if sensor_to_backing_mapping:
        backing_entity_ids = set(sensor_to_backing_mapping.values())
        if backing_entity_ids:  # Only register if we have actual entities
            sensor_manager.register_data_provider_entities(backing_entity_ids, change_notifier)
            sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

    # Register with storage manager for entity change notifications
    sensor_manager.register_with_storage_manager(storage_manager)

    # Load configuration from storage (this triggers sensor creation)
    config = storage_manager.to_config(device_identifier=device_identifier)
    await sensor_manager.load_configuration(config)

    return storage_manager, sensor_manager


async def async_setup_synthetic_integration_with_auto_backing(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    integration_domain: str,
    device_identifier: str,
    sensor_configs: list[SensorConfig],
    data_provider_callback: DataProviderCallback | None = None,
    sensor_set_name: str | None = None,
) -> tuple[StorageManager, SensorManager]:
    """Complete setup with automatic backing entity management.

    This is the most advanced interface that automatically extracts and manages
    backing entities from sensor configurations, making them completely invisible
    to the caller. Perfect for integrations that want zero backing entity management.

    Args:
        hass: Home Assistant instance
        config_entry: Integration's ConfigEntry
        async_add_entities: AddEntitiesCallback from sensor platform
        integration_domain: Domain name for the integration
        device_identifier: Device identifier for entity IDs and sensor set ID
        sensor_configs: List of SensorConfig objects defining the sensors
        data_provider_callback: Optional callback for live data
        sensor_set_name: Optional name for the sensor set (defaults to device-based name)
        allow_ha_lookups: If True, backing entities can fall back to HA state lookups
                        when not found in data provider. If False (default), backing
                        entities are always virtual and only use data provider callback.

    Returns:
        Tuple of (StorageManager, SensorManager): Both configured and ready
    """

    # Setup StorageManager
    storage_manager = StorageManager(hass, f"{integration_domain}_synthetic", integration_domain=integration_domain)
    await storage_manager.async_load()

    # Get/Create SensorSet from StorageManager
    sensor_set_id = f"{device_identifier}_sensors"
    sensor_set_display_name = sensor_set_name or f"{integration_domain.title()} {device_identifier} Sensors"

    if storage_manager.sensor_set_exists(sensor_set_id):
        sensor_set = storage_manager.get_sensor_set(sensor_set_id)

        # Existing storage - preserve user customizations
        # Only add new sensors that don't exist
        existing_sensor_ids = {s.unique_id for s in sensor_set.list_sensors()}
        new_sensors = [s for s in sensor_configs if s.unique_id not in existing_sensor_ids]

        if new_sensors:
            for sensor_config in new_sensors:
                await sensor_set.async_add_sensor(sensor_config)
    else:
        # Fresh install - create sensor set with provided configurations
        await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier=device_identifier,
            name=sensor_set_display_name,
        )
        sensor_set = storage_manager.get_sensor_set(sensor_set_id)
        await sensor_set.async_replace_sensors(sensor_configs)

    # Extract backing entities automatically from sensor configurations
    all_backing_entities: set[str] = set()
    for sensor_config in sensor_configs:
        for formula in sensor_config.formulas:
            if formula.variables:
                for _var_name, var_value in formula.variables.items():
                    # Check if this looks like an entity ID that would use integration data provider
                    if isinstance(var_value, str) and var_value.startswith("sensor."):
                        all_backing_entities.add(var_value)

    # Load everything in one atomic operation with automatic backing entity management

    # Get device info if available (integration-specific)
    device_info = None
    if hasattr(config_entry, "data"):
        integration_data = hass.data.get(integration_domain, {}).get(config_entry.entry_id, {})
        device_info = integration_data.get("device_info")

    # Create sensor manager
    sensor_manager = await async_create_sensor_manager(
        hass=hass,
        integration_domain=integration_domain,
        add_entities_callback=async_add_entities,
        device_info=device_info,
        data_provider_callback=data_provider_callback,
    )

    # Register backing entities automatically (invisible to caller)
    if all_backing_entities:
        sensor_manager.register_data_provider_entities(all_backing_entities)

    # Register with storage manager for entity change notifications
    sensor_manager.register_with_storage_manager(storage_manager)

    # Load configuration from storage (this triggers sensor creation with automatic backing entity management)
    config = storage_manager.to_config(device_identifier=device_identifier)
    await sensor_manager.load_configuration(config)

    return storage_manager, sensor_manager


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


try:
    from importlib.metadata import version

    __version__ = version("ha-synthetic-sensors")
except ImportError:
    # Fallback for development/editable installs
    __version__ = "unknown"
__all__ = [
    "DataProviderCallback",
    "DataProviderChangeNotifier",
    "DataProviderResult",
    "DeviceAssociationHelper",
    "EntityDescription",
    "EntityFactory",
    "FormulaConfig",
    "SensorConfig",
    "SensorManager",
    "SensorSet",
    "StorageManager",
    "SyntheticSensorsIntegration",
    "async_create_sensor_manager",
    "async_reload_integration",
    "async_setup_integration",
    "async_setup_synthetic_integration",
    "async_setup_synthetic_integration_with_auto_backing",
    "async_setup_synthetic_sensors",
    "async_setup_synthetic_sensors_with_entities",
    "async_unload_integration",
    "configure_logging",
    "get_example_config",
    "get_integration",
    "get_logging_info",
    "test_logging",
    "validate_yaml_content",
]
