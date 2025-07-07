# Synthetic Sensors Integration Guide

This guide demonstrates how to integrate the `ha-synthetic-sensors` library into your Home Assistant custom integration to
create dynamic, formula-based sensors.

## Overview

The `ha-synthetic-sensors` library provides a storage-based approach to creating synthetic sensors that can perform
calculations using data from your integration's native sensors. This is particularly useful for:

- Creating derived sensors (e.g., power calculations from voltage/current)
- Aggregating data across multiple devices
- Providing user-customizable sensor formulas
- Managing large numbers of dynamic sensors

## Key Concepts

### Storage-First Architecture

The library uses Home Assistant's storage system to persist sensor configurations:

- **StorageManager**: Manages persistent storage and sensor set operations
- **SensorSet**: Handle for a group of related sensors with CRUD operations
- **SensorManager**: Creates and manages actual Home Assistant sensor entities
- **Data Provider**: Supplies live data to synthetic sensors from your integration

### Integration Patterns

1. **Storage-Based**: Sensors are defined in HA storage, user-customizable (recommended)
2. **File-Based**: Sensors defined in YAML files, integration managed files
3. **Hybrid**: Mix of storage-based and file-based sensors

## Quick Start Integration Pattern

### 1. Basic Setup in `__init__.py`

```python
import ha_synthetic_sensors
from ha_synthetic_sensors.storage_manager import StorageManager

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Configure logging
    ha_synthetic_sensors.configure_logging(logging.DEBUG)

    # Create your coordinator
    coordinator = YourIntegrationCoordinator(...)
    await coordinator.async_config_entry_first_refresh()

    # Initialize storage manager
    storage_manager = StorageManager(hass, f"{DOMAIN}_synthetic")
    await storage_manager.async_load()

    # Generate synthetic sensor configurations
    await setup_synthetic_sensors(coordinator, storage_manager, entry)

    # Store for use in sensor platform
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "storage_manager": storage_manager,
    }

    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def setup_synthetic_sensors(
    coordinator: YourCoordinator,
    storage_manager: StorageManager,
    entry: ConfigEntry
) -> None:
    """Generate and store synthetic sensor configurations."""

    # Generate sensor configurations from your device data
    device_identifier = coordinator.device_id
    sensor_configs = generate_sensor_configs(coordinator.data, device_identifier)

    # Create or get sensor set
    sensor_set_id = f"{device_identifier}_sensors"
    if storage_manager.sensor_set_exists(sensor_set_id):
        sensor_set = storage_manager.get_sensor_set(sensor_set_id)
    else:
        sensor_set = await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier=device_identifier,
            name=f"{coordinator.device_name} Sensors",
        )

    # Check if this is a fresh install or existing storage
    if sensor_set.sensor_count == 0:
        # Fresh install - populate with defaults
        await sensor_set.async_replace_sensors(sensor_configs)
    else:
        # Existing storage - preserve user customizations
        # Only add new sensors, don't modify existing ones
        existing_sensor_ids = {s.unique_id for s in sensor_set.list_sensors()}
        new_sensors = [s for s in sensor_configs if s.unique_id not in existing_sensor_ids]
        if new_sensors:
            for sensor_config in new_sensors:
                await sensor_set.async_add_sensor(sensor_config)
```

### 2. Sensor Platform Setup in `sensor.py`

**CRITICAL**: The sensor platform must create the actual Home Assistant sensor entities using the stored configurations.

```python
from ha_synthetic_sensors.integration import SyntheticSensorsIntegration
from ha_synthetic_sensors.sensor_manager import SensorManagerConfig

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    storage_manager = data["storage_manager"]

    # Create any native (non-synthetic) sensors first
    native_entities = create_native_sensors(coordinator)
    async_add_entities(native_entities)

    # Create synthetic sensors from stored configurations
    await create_synthetic_sensor_entities(hass, entry, coordinator, storage_manager, async_add_entities)

async def create_synthetic_sensor_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: YourCoordinator,
    storage_manager: StorageManager,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create synthetic sensor entities from stored configurations."""

    # Create synthetic sensors integration
    synthetic_integration = SyntheticSensorsIntegration(hass, entry)

    # Configure sensor manager
    manager_config = SensorManagerConfig(
        integration_domain=DOMAIN,
        device_info=coordinator.device_info,
        lifecycle_managed_externally=True,
        data_provider_callback=create_data_provider_callback(coordinator),
    )

    # Create managed sensor manager
    sensor_manager = await synthetic_integration.create_managed_sensor_manager(
        add_entities_callback=async_add_entities,
        manager_config=manager_config
    )

    # Convert storage to config format and load
    device_identifier = coordinator.device_id
    config = storage_manager.to_config(device_identifier=device_identifier)

    # Register backing entities that provide data
    backing_entities = generate_backing_entity_ids(coordinator.data, device_identifier)
    sensor_manager.register_data_provider_entities(backing_entities)

    # Load configuration to create actual sensor entities
    await sensor_manager.load_configuration(config)
```

### 3. Data Provider Implementation

```python
def create_data_provider_callback(coordinator: YourCoordinator) -> DataProviderCallback:
    """Create data provider callback for synthetic sensors."""

    def data_provider_callback(entity_id: str) -> DataProviderResult:
        """Provide live data for synthetic sensors."""
        try:
            # Parse backing entity ID: "your_integration_backing.device_123_power"
            if not entity_id.startswith(f"{DOMAIN}_backing."):
                return {"value": None, "exists": False}

            # Extract device and sensor type
            parts = entity_id.split(".")
            if len(parts) != 2:
                return {"value": None, "exists": False}

            # Parse device_123_power -> device_id=123, sensor_type=power
            backing_part = parts[1]  # "device_123_power"
            device_id, sensor_type = parse_backing_entity(backing_part)

            # Get current data from coordinator
            device_data = coordinator.data.get_device(device_id)
            if not device_data:
                return {"value": None, "exists": False}

            # Return the requested sensor value
            value = getattr(device_data, sensor_type, None)
            return {"value": value, "exists": value is not None}

        except Exception as e:
            _LOGGER.error("Error in data provider callback: %s", e)
            return {"value": None, "exists": False}

    return data_provider_callback

def generate_backing_entity_ids(device_data: Any, device_identifier: str) -> set[str]:
    """Generate backing entity IDs that the data provider can supply."""
    backing_entities = set()

    # Add backing entities for each data point your integration provides
    backing_entities.add(f"{DOMAIN}_backing.{device_identifier}_power")
    backing_entities.add(f"{DOMAIN}_backing.{device_identifier}_energy")
    backing_entities.add(f"{DOMAIN}_backing.{device_identifier}_voltage")

    return backing_entities
```

### 4. Sensor Configuration Generation

```python
def generate_sensor_configs(device_data: Any, device_identifier: str) -> list[SensorConfig]:
    """Generate sensor configurations from your device data."""
    from ha_synthetic_sensors.config_manager import SensorConfig, FormulaConfig

    configs = []

    # Example: Power sensor
    power_config = SensorConfig(
        unique_id=f"{device_identifier}_power",
        name=f"{device_data.name} Power",
        entity_id=f"sensor.{device_identifier}_power",
        device_identifier=device_identifier,
        formulas=[
            FormulaConfig(
                id="main",
                formula="power_value",
                variables={"power_value": f"{DOMAIN}_backing.{device_identifier}_power"},
                unit_of_measurement="W",
                device_class="power",
                state_class="measurement",
            )
        ],
    )
    configs.append(power_config)

    # Example: Energy sensor with calculation
    energy_config = SensorConfig(
        unique_id=f"{device_identifier}_daily_energy",
        name=f"{device_data.name} Daily Energy",
        entity_id=f"sensor.{device_identifier}_daily_energy",
        device_identifier=device_identifier,
        formulas=[
            FormulaConfig(
                id="main",
                formula="power_value * hours_per_day / 1000",
                variables={
                    "power_value": f"{DOMAIN}_backing.{device_identifier}_power",
                    "hours_per_day": "24"
                },
                unit_of_measurement="kWh",
                device_class="energy",
                state_class="total_increasing",
            )
        ],
    )
    configs.append(energy_config)

    return configs
```

## Storage-Based Configuration Management

### Storage Concepts

1. **Sensor Sets**: Groups of sensors with integration-controlled identifiers
2. **Storage Persistence**: Configuration stored in HA's storage system
3. **SensorSet Interface**: Focused handle for individual sensor set operations

### StorageManager and SensorSet API

```python
# Initialize storage manager
storage_manager = StorageManager(hass, "your_integration_synthetic")
await storage_manager.async_load()

# Create sensor set and get handle in one step
sensor_set = await storage_manager.async_create_sensor_set(
    sensor_set_id=f"{device_identifier}_sensors",  # Integration controls format
    device_identifier="your_device_123",  # Optional - for entity ID generation
    name=f"Device {device_identifier} Sensors",
    description="Power monitoring sensors"
)

# Individual operations via SensorSet
sensor = sensor_set.get_sensor(unique_id)
await sensor_set.async_update_sensor(modified_sensor)
await sensor_set.async_remove_sensor(unique_id)

# Property access for debugging/logging
logger.debug(f"Sensor set {sensor_set.sensor_set_id} has {sensor_set.sensor_count} sensors")
```

### Accessing StorageManager from SensorSet

**IMPORTANT**: If you need to access the underlying `StorageManager` from a `SensorSet` (e.g., for conversion operations),
use the `storage_manager` property:

```python
# Get sensor set from storage manager
sensor_set = storage_manager.get_sensor_set(sensor_set_id)

# Access the underlying storage manager
underlying_storage = sensor_set.storage_manager

# Convert storage to config format
config = underlying_storage.to_config(device_identifier=device_identifier)

# Or use the storage manager directly if you have a reference
config = storage_manager.to_config(device_identifier=device_identifier)
```

### Storage-First vs Generate-and-Overwrite

**WRONG - Generate and Overwrite Approach:**

```python
# This destroys user customizations!
sensor_configs = generate_sensor_configs(device_data)
await sensor_set.async_replace_sensors(sensor_configs)  # Overwrites everything
```

**CORRECT - Storage-First Approach:**

```python
# Preserve user customizations
if sensor_set.sensor_count == 0:
    # Fresh install - populate with defaults
    await sensor_set.async_replace_sensors(default_configs)
else:
    # Existing storage - only add new sensors, preserve existing
    await add_missing_sensors_only(sensor_set, default_configs)

# WRONG: Always overwrite
await sensor_set.async_replace_sensors(default_configs)  # Destroys customizations
```

# Bulk setup or replacmemt operations on sensor set

sensor_configs = generate_sensor_configs(device_data)
await sensor_set.async_replace_sensors(sensor_configs)

# Individual sensor CRUD operations

await sensor_set.async_add_sensor(new_sensor_config)
await sensor_set.async_update_sensor(modified_sensor_config)
await sensor_set.async_remove_sensor("sensor_unique_id")

# Get individual sensor

sensor = sensor_set.get_sensor("sensor_unique_id")

# List all sensors in set

sensors = sensor_set.list_sensors()

# YAML operations

await sensor_set.async_import_yaml(yaml_content)
yaml_content = sensor_set.export_yaml()

# Sensor set management

sensor_count = sensor_set.sensor_count
metadata = sensor_set.metadata
exists = sensor_set.exists

# Delete entire sensor set

await sensor_set.async_delete()

# OR

await storage_manager.async_delete_sensor_set(f"{device_identifier}_sensors")

## Bulk Modification Operations

The `SensorSet.async_modify()` method provides powerful bulk modification capabilities for complex operations:

```python
from ha_synthetic_sensors.sensor_set import SensorSetModification

# Example: Bulk entity ID changes (e.g., when device entity IDs change)
entity_id_changes = {
    "sensor.old_power_meter": "sensor.new_power_meter",
    "sensor.old_energy_meter": "sensor.new_energy_meter",
    "sensor.old_temperature": "sensor.new_temperature"
}

modification = SensorSetModification(
    entity_id_changes=entity_id_changes,
    global_settings={"variables": {"efficiency_factor": 0.92}}  # Update global settings too
)

result = await sensor_set.async_modify(modification)
print(f"Changed {result['entity_ids_changed']} entity IDs")

# Example: Complex sensor set restructuring
modification = SensorSetModification(
    # Remove outdated sensors
    remove_sensors=["old_sensor_1", "old_sensor_2"],

    # Add new sensors
    add_sensors=[new_sensor_config_1, new_sensor_config_2],

    # Update existing sensors with new formulas
    update_sensors=[updated_sensor_config],

    # Change entity IDs and global settings
    entity_id_changes={"sensor.old_reference": "sensor.new_reference"},
    global_settings={"device_identifier": "new_device_id"}
)

result = await sensor_set.async_modify(modification)
print(f"Modifications: {result['sensors_added']} added, {result['sensors_removed']} removed, "
      f"{result['sensors_updated']} updated, {result['entity_ids_changed']} entity IDs changed")
```

**SensorSetModification Operations:**

- **`add_sensors`**: List of new SensorConfig objects to add
- **`remove_sensors`**: List of unique_ids to remove
- **`update_sensors`**: List of SensorConfig objects to update (must preserve unique_id)
- **`entity_id_changes`**: Dict mapping old entity IDs to new entity IDs
- **`global_settings`**: Dict of new global settings to apply

**Bulk Modification Benefits:**

- **Atomic Operations**: All changes succeed or fail together
- **Validation**: Comprehensive validation prevents conflicts
- **Efficiency**: Single operation handles complex changes
- **Entity ID Coordination**: Automatic Home Assistant entity registry updates
- **Cache Management**: Coordinated formula cache invalidation

### Working with Multiple Sensor Sets

```python
# Create multiple sensor sets for different purposes
config_set = await storage_manager.async_create_sensor_set(
    sensor_set_id=f"{device_identifier}_config_v1",  # Integration controls format
    device_identifier="device_123",
    name="Device Configuration"
)

monitoring_set = await storage_manager.async_create_sensor_set(
    sensor_set_id=f"{device_identifier}_monitoring_v1",  # Integration controls format
    device_identifier="device_123",
    name="Device Monitoring"
)

# Later, get handles for existing sensor sets - clean handle pattern
config_set = storage_manager.get_sensor_set(f"{device_identifier}_config_v1")
monitoring_set = storage_manager.get_sensor_set(f"{device_identifier}_monitoring_v1")

# Property access for debugging/logging
_LOGGER.debug(f"Config set {config_set.sensor_set_id} has {config_set.sensor_count} sensors")
_LOGGER.debug(f"Monitoring set {monitoring_set.sensor_set_id} has {monitoring_set.sensor_count} sensors")

# Query all sensor sets
all_sets = storage_manager.list_sensor_sets()
device_sets = storage_manager.list_sensor_sets(device_identifier="device_123")
```

### StorageManager Direct Access

```python
# Convert between formats
config = storage_manager.to_config(device_identifier="your_device_123")
await storage_manager.async_from_config(config, sensor_set_id, device_identifier)

# Query sensors across all sets
sensors = storage_manager.list_sensors(device_identifier="your_device_123")
specific_sensor = storage_manager.get_sensor("unique_id")

# Global settings
await storage_manager.async_set_global_setting("key", "value")
value = storage_manager.get_global_setting("key", default="default")
```

### Enhanced SensorSet Features

The SensorSet interface provides additional convenience methods for better integration experience:

```python
# SensorSet property getters
sensor_set = storage_manager.get_sensor_set(sensor_set_id)

# Access sensor set metadata
sensor_set_id = sensor_set.sensor_set_id
device_identifier = sensor_set.device_identifier
name = sensor_set.name
sensor_count = sensor_set.sensor_count

# Check sensor existence
if sensor_set.sensor_exists("unique_id"):
    sensor = sensor_set.get_sensor("unique_id")

# StorageManager convenience methods
if storage_manager.sensor_set_exists(sensor_set_id):
    sensor_set = storage_manager.get_sensor_set(sensor_set_id)

# List sensor sets with optional filtering
all_sets = await storage_manager.list_sensor_sets()
device_sets = await storage_manager.list_sensor_sets(device_identifier="device_123")
```

### Error Handling Improvements

The SensorSet architecture includes custom exceptions for better error handling:

```python
from ha_synthetic_sensors.exceptions import (
    SensorSetNotFoundError,
    SensorNotFoundError,
    DuplicateSensorError
)

try:
    sensor_set = storage_manager.get_sensor_set("nonexistent_set")
except SensorSetNotFoundError:
    _LOGGER.error("Sensor set not found")

try:
    await sensor_set.async_add_sensor(duplicate_config)
except DuplicateSensorError:
    _LOGGER.error("Sensor already exists in set")

try:
    sensor = sensor_set.get_sensor("nonexistent_sensor")
except SensorNotFoundError:
    _LOGGER.error("Sensor not found in set")
```

## Migration from File-Based Configuration

### For Existing Integrations

If you have existing YAML-based configurations, use the migration path:

```python
async def migrate_yaml_to_storage(
    storage_manager: StorageManager,
    yaml_file_path: str,
    sensor_set_id: str,
    device_identifier: str | None = None
) -> None:
    """Migrate YAML configuration to storage."""

    # Load YAML configuration
    with open(yaml_file_path, 'r') as f:
        yaml_content = f.read()

    # Create sensor set from YAML
    sensor_set = await storage_manager.async_create_sensor_set(
        sensor_set_id=sensor_set_id,
        device_identifier=device_identifier,
        name="Migrated Sensors"
    )

    # Import YAML content
    await sensor_set.async_import_yaml(yaml_content)

    # Optionally remove old YAML file
    # os.remove(yaml_file_path)
```

## Common Integration Patterns

### Pattern 1: Device-Based Sensor Sets

Each device gets its own sensor set:

```python
async def setup_device_sensors(device_id: str, device_data: Any) -> None:
    sensor_set_id = f"device_{device_id}_sensors"
    sensor_set = await storage_manager.async_create_sensor_set(
        sensor_set_id=sensor_set_id,
        device_identifier=device_id,
        name=f"Device {device_id} Sensors"
    )

    # Generate device-specific sensors
    sensor_configs = generate_device_sensors(device_data)
    await sensor_set.async_replace_sensors(sensor_configs)
```

### Pattern 2: Feature-Based Sensor Sets

Group sensors by functionality:

```python
async def setup_feature_sensors(device_id: str) -> None:
    # Power monitoring sensors
    power_set = await storage_manager.async_create_sensor_set(
        sensor_set_id=f"{device_id}_power_sensors",
        device_identifier=device_id,
        name="Power Monitoring"
    )

    # Environmental sensors
    env_set = await storage_manager.async_create_sensor_set(
        sensor_set_id=f"{device_id}_env_sensors",
        device_identifier=device_id,
        name="Environmental Monitoring"
    )
```

### Pattern 3: Configuration-Driven Sensors

Sensors based on user configuration:

```python
async def setup_configurable_sensors(entry: ConfigEntry) -> None:
    config = entry.data

    if config.get("enable_power_sensors", True):
        await setup_power_sensors(entry)

    if config.get("enable_environmental_sensors", False):
        await setup_environmental_sensors(entry)
```

## Best Practices

### 1. Storage-First Approach

Always treat storage as the source of truth:

```python
# CORRECT: Check storage first
if sensor_set.sensor_count == 0:
    # Fresh install - populate defaults
    await sensor_set.async_replace_sensors(default_configs)
else:
    # Existing storage - preserve user customizations
    await add_missing_sensors_only(sensor_set, default_configs)

# WRONG: Always overwrite
await sensor_set.async_replace_sensors(default_configs)  # Destroys customizations
```

### 2. Unique Sensor Keys

Use consistent, unique sensor keys:

```python
# CORRECT: Consistent format
sensor_key = f"{device_identifier}_{sensor_type}"

# WRONG: Inconsistent or non-unique
sensor_key = f"{sensor_type}"  # Not unique across devices
```

### 3. Error Handling

Always handle storage and sensor manager errors:

```python
try:
    await sensor_set.async_add_sensor(sensor_config)
except DuplicateSensorError:
    # Handle duplicate sensor
    await sensor_set.async_update_sensor(sensor_config)
except Exception as e:
    _LOGGER.error("Failed to add sensor: %s", e)
```

### 4. Performance Considerations

Use bulk operations when possible:

```python
# CORRECT: Bulk operation
await sensor_set.async_replace_sensors(sensor_configs)

# WRONG: Individual operations in loop
for config in sensor_configs:
    await sensor_set.async_add_sensor(config)
```

### 5. Data Provider Efficiency

Cache expensive operations in data providers:

```python
def create_data_provider_callback(coordinator: YourCoordinator) -> DataProviderCallback:
    def data_provider_callback(entity_id: str) -> DataProviderResult:
        # Use coordinator's cached data, don't make new API calls
        return coordinator.get_cached_value(entity_id)

    return data_provider_callback
```

## Troubleshooting

### Common Issues

1. **Sensors not appearing**: Check that `sensor_manager.load_configuration()` is called
2. **Data not updating**: Verify data provider callback is registered and working
3. **Configuration lost**: Ensure storage-first approach, don't overwrite existing configs
4. **Performance issues**: Use bulk operations and cache data in coordinator

### Debug Logging

Enable debug logging to troubleshoot:

```python
import ha_synthetic_sensors
ha_synthetic_sensors.configure_logging(logging.DEBUG)
```

### Validation

Validate sensor configurations before storing:

```python
from ha_synthetic_sensors.config_manager import SensorConfig

try:
    sensor_config = SensorConfig(...)
    # Configuration is valid
except ValueError as e:
    _LOGGER.error("Invalid sensor configuration: %s", e)
```

## API Reference

### Key Classes

- **`StorageManager`**: Manages persistent storage and sensor sets
- **`SensorSet`**: Handle for a group of sensors with CRUD operations
- **`SensorManager`**: Creates and manages Home Assistant sensor entities
- **`SensorConfig`**: Configuration for a single sensor
- **`FormulaConfig`**: Configuration for sensor formulas
- **`SyntheticSensorsIntegration`**: Main integration class

### Storage Manager Methods

- `async_load()`: Load storage from disk
- `async_create_sensor_set()`: Create new sensor set
- `get_sensor_set()`: Get existing sensor set handle
- `sensor_set_exists()`: Check if sensor set exists
- `to_config()`: Convert storage to config format
- `list_sensor_sets()`: List all sensor sets

### Sensor Set Methods

- `async_add_sensor()`: Add single sensor
- `async_update_sensor()`: Update existing sensor
- `async_remove_sensor()`: Remove sensor
- `async_replace_sensors()`: Replace all sensors (bulk)
- `get_sensor()`: Get single sensor
- `list_sensors()`: List all sensors
- `sensor_exists()`: Check if sensor exists

This guide provides the foundation for integrating synthetic sensors into your Home Assistant integration.
The storage-based approach ensures user customizations are preserved while providing a powerful framework for dynamic sensor creation.
