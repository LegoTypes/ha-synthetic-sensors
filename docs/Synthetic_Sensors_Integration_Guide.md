# Home Assistant Synthetic Sensors Integration Guide

## Overview

This document provides a guide for Home Assistant integration developers on how to integrate
the `ha-synthetic-sensors` package into their custom integrations. The package supports both
file-based YAML configuration and Home Assistant's built-in storage system, allowing integrations
to choose the approach that best fits their needs.

## Integration Architecture

### Core Components

**Storage-Based Path (Programmatic):**

```text
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   Your Integration  │───▶│   StorageManager    │───▶│     SensorSet       │
│                     │    │                     │    │                     │
│ - Device data       │    │ - HA storage        │    │ - Individual CRUD   │
│ - Sensor configs    │    │ - Sensor metadata   │    │ - Bulk operations   │
│ - Data provider     │    │ - Sensor set mgmt   │    │ - YAML import/export│
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
```

**File-Based Path (Auto-Discovery):**

```text
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   YAML Files        │───▶│   ConfigManager     │───▶│   SensorManager     │
│                     │    │                     │    │                     │
│ - sensor_config.yaml│    │ - YAML parsing      │    │ - Entity creation   │
│ - syn2_config.yaml  │    │ - Validation        │    │ - State management  │
│ - Auto-discovery    │    │ - Config objects    │    │ - Device association│
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
```

**Common Components:**

```text
┌─────────────────────┐    ┌─────────────────────┐
│   StorageManager    │    │ Config/Formula Data │
│                     │    │                     │
│ - YAML ↔ Storage    │    │ - Formulas          │
│ - Format conversion │    │ - Variables         │
│ - SensorSet API     │    │ - Attributes        │
└─────────────────────┘    └─────────────────────┘
```

### Architectural Principles

1. **Dual Configuration Support**: Both file-based YAML and storage-based configuration
2. **Smart Configuration Detection**: Auto-discovery skipped when storage is in use
3. **Device-Centric Organization**: Sensors can be grouped by device for bulk management
4. **Integration Authority**: Your integration owns data, synthetic sensors handle entities
5. **Flexible Workflow**: Choose between file-based simplicity or storage-based programmatic control

## Integration Team Feedback

The SensorSet architecture has received positive feedback from integration teams, particularly the SPAN Panel integration team
who were the first to implement the storage-based API. Key benefits identified:

**✅ RESOLVED** - The SensorSet architecture addresses major integration concerns:

- Integration-controlled sensor_set_id ✅
- Individual sensor CRUD operations ✅
- Sensor set-focused YAML operations ✅
- Proper abstraction between sensor set management and individual sensor operations ✅

**Integration Usage Patterns:**

### Setup Phase (Bulk Operations)

```python
# Initialize storage manager
storage_manager = StorageManager(hass, f"{DOMAIN}_synthetic")
await storage_manager.async_load()

# Create sensor set and get handle
sensor_set = await storage_manager.async_create_sensor_set(
    sensor_set_id=f"{device_identifier}_sensors",
    device_identifier=device_identifier,
    name=f"SPAN Panel {device_identifier}"
)

# Generate complete configuration
config = generate_all_sensor_configs()
yaml_content = yaml.dump(config)

# Bulk import via SensorSet
await sensor_set.async_import_yaml(yaml_content)
```

### Runtime Phase (Individual CRUD)

```python
# Get sensor set handle
sensor_set = storage_manager.get_sensor_set(sensor_set_id)

# Individual operations via SensorSet
sensor = sensor_set.get_sensor(unique_id)
await sensor_set.async_update_sensor(modified_sensor)
await sensor_set.async_remove_sensor(unique_id)

# Property access for debugging/logging
logger.debug(f"Sensor set {sensor_set.sensor_set_id} has {sensor_set.sensor_count} sensors")
```

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

    # Store for use in sensor platform
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "storage_manager": storage_manager,
    }

    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True
```

### 2. Sensor Platform Setup in `sensor.py`

```python
from ha_synthetic_sensors.integration import SyntheticSensorsIntegration
from ha_synthetic_sensors.sensor_manager import SensorManagerConfig

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    storage_manager = data["storage_manager"]

    # Create synthetic sensors integration
    synthetic_integration = SyntheticSensorsIntegration(hass, entry)

    # Configure sensor manager with your integration domain
    manager_config = SensorManagerConfig(
        integration_domain=DOMAIN,
        device_info=your_device_info,
        lifecycle_managed_externally=True,
        data_provider_callback=create_data_provider_callback(coordinator),
    )

    # Create managed sensor manager
    sensor_manager = await synthetic_integration.create_managed_sensor_manager(
        add_entities_callback=async_add_entities,
        manager_config=manager_config
    )

    # Generate and store sensor configurations
    await setup_synthetic_sensors(
        coordinator,
        storage_manager,
        sensor_manager,
        your_device_identifier
    )

    # Create any native (non-synthetic) sensors
    native_entities = create_native_sensors(coordinator)
    async_add_entities(native_entities)
```

### 3. Sensor Configuration Generation

```python
async def setup_synthetic_sensors(
    coordinator: YourCoordinator,
    storage_manager: StorageManager,
    sensor_manager: SensorManager,
    device_identifier: str
) -> None:
    """Set up synthetic sensors for your integration."""

    # Generate sensor configurations from your device data
    sensor_configs = generate_sensor_configs(coordinator.data, device_identifier)

    # Create sensor set and populate with sensors
    sensor_set = await storage_manager.async_create_sensor_set(
        sensor_set_id=f"{device_identifier}_config_v1",
        device_identifier=device_identifier,
        name=f"{coordinator.device_name} Configuration",
    )

    await sensor_set.async_replace_sensors(sensor_configs)

    # Register data provider entities
    backing_entities = generate_backing_entity_ids(coordinator.data, device_identifier)
    sensor_manager.register_data_provider_entities(backing_entities)

    # Convert storage to config and load
    config = storage_manager.to_config(device_identifier=device_identifier)
    await sensor_manager.load_configuration(config)

def generate_sensor_configs(device_data: Any, device_identifier: str) -> list[SensorConfig]:
    """Generate sensor configurations from your device data."""
    from ha_synthetic_sensors.config_manager import SensorConfig, FormulaConfig

    configs = []

    # Example: Power sensor
    power_config = SensorConfig(
        unique_id=f"{device_identifier}_power",
        formulas=[
            FormulaConfig(
                formula="power_value",
                variables={"power_value": f"your_integration_backing.{device_identifier}_power"},
                unit_of_measurement="W",
                device_class="power",
                state_class="measurement",
            )
        ],
        name=f"{device_data.name} Power",
        device_identifier=device_identifier,
    )
    configs.append(power_config)

    # Add more sensor configurations...

    return configs
```

### 4. Data Provider Implementation

```python
def create_data_provider_callback(coordinator: YourCoordinator) -> DataProviderCallback:
    """Create data provider callback for synthetic sensors."""

    def data_provider_callback(entity_id: str) -> DataProviderResult:
        """Provide live data for synthetic sensors."""
        try:
            # Parse backing entity ID: "your_integration_backing.device_123_power"
            if not entity_id.startswith("your_integration_backing."):
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
    name=f"SPAN Panel {device_identifier}",
    description="Power monitoring sensors"
)

# Bulk operations on sensor set
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
```

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
) -> bool:
    """Migrate existing YAML configuration to storage."""
    try:
        # Read existing YAML (non-blocking)
        def _read_yaml_file():
            with open(yaml_file_path, 'r') as f:
                return f.read()

        yaml_content = await hass.async_add_executor_job(_read_yaml_file)

        # Create sensor set and import YAML
        sensor_set = await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier=device_identifier,
            name=f"Migrated from {yaml_file_path}"
        )

        await sensor_set.async_import_yaml(yaml_content)

        # Optionally remove old YAML file (non-blocking)
        await hass.async_add_executor_job(os.remove, yaml_file_path)
        return True

    except Exception as e:
        _LOGGER.error("Failed to migrate YAML to storage: %s", e)
        return False
```

### Configuration Sources

The package supports two configuration approaches:

#### Auto-Discovery (files managed by the integration)

- **Automatic**: Package automatically searches for YAML files in the integration directory
- **No configuration needed**: Just place a YAML file and the package finds it (reload when changes are made)
- **Standalone mode**: Works without any integration storage setup code

#### Storage-Based (storage managed by the package)

- **Integration-controlled**: Your integration interacts with configuration via `StorageManager` and `SensorSet`
- **HA storage system**: Configuration persisted in storage allocated by the integration (via Home Assistant)
- **Full CRUD**: Add, update, delete individual sensors programmatically
- **Sensor set-focused**: Organize sensors by integration-controlled sensor_set_id
- **YAML Import/Export**: Full roundtrip lossless export on a per-sensor_set_id granularity
- **Storage Consistency**: Event listeners update sensor references for any sensor entity_id and name changes in HA

#### Configuration Behavior

**IMPORTANT**: These approaches are **mutually exclusive** - only one configuration is active at a time:

- **Auto-discovery runs first** when the package initializes
- **Storage-based configuration, when loaded, replaces** any auto-discovered configuration
- **Smart conflict prevention**: Auto-discovery is automatically skipped if storage already contains sensor sets
- **Last loaded wins**: Each `load_configuration()` call completely replaces the previous configuration

## Device Association and Entity IDs

### Device-Aware Entity Naming

When sensors are associated with devices, entity IDs are automatically generated:

```python
# Device association in sensor config
sensor_config = SensorConfig(
    unique_id=f"{device_identifier}_power",
    device_identifier=device_identifier,  # Associates with device
    formulas=[...],
    name="Device Power",
)

# Results in entity ID: sensor.your_integration_device_name_power
```

### Device Integration

```python
# Configure sensor manager with device info
manager_config = SensorManagerConfig(
    integration_domain="your_integration",
    device_info=DeviceInfo(
        identifiers={(DOMAIN, device_identifier)},
        name=device_name,
        manufacturer="Your Company",
        model="Device Model",
    ),
    lifecycle_managed_externally=True,
    data_provider_callback=data_provider_callback,
)
```

## Data Provider Patterns

### Backing Entity Naming Convention

Use consistent naming for backing entities:

```python
def generate_backing_entity_ids(device_data: Any, device_identifier: str) -> set[str]:
    """Generate backing entity IDs for data provider."""
    entity_ids = set()

    # Format: {integration}_backing.{device_id}_{sensor_type}
    for sensor_type in ["power", "energy", "temperature"]:
        entity_id = f"your_integration_backing.{device_identifier}_{sensor_type}"
        entity_ids.add(entity_id)

    return entity_ids
```

### Data Provider Error Handling

```python
def data_provider_callback(entity_id: str) -> DataProviderResult:
    """Robust data provider with error handling."""
    try:
        # Validate entity ID format
        if not entity_id.startswith("your_integration_backing."):
            return {"value": None, "exists": False}

        # Parse and validate
        device_id, sensor_type = parse_backing_entity(entity_id)
        if not device_id or not sensor_type:
            return {"value": None, "exists": False}

        # Get data with fallbacks
        device_data = coordinator.data.get_device(device_id)
        if not device_data:
            _LOGGER.warning("Device %s not found in coordinator data", device_id)
            return {"value": None, "exists": False}

        # Get sensor value with type checking
        value = getattr(device_data, sensor_type, None)
        if value is None:
            return {"value": None, "exists": False}

        # Validate numeric values
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                _LOGGER.warning("Non-numeric value for %s: %s", entity_id, value)
                return {"value": None, "exists": False}

        return {"value": value, "exists": True}

    except Exception as e:
        _LOGGER.error("Error in data provider for %s: %s", entity_id, e)
        return {"value": None, "exists": False}
```

## Testing Integration

### Test Setup

```python
@pytest.fixture
async def storage_manager(hass):
    """Create storage manager for testing."""
    storage_manager = StorageManager(hass, "test_storage")
    await storage_manager.async_load()
    return storage_manager

@pytest.fixture
async def synthetic_integration(hass, mock_config_entry):
    """Create synthetic sensors integration for testing."""
    return SyntheticSensorsIntegration(hass, mock_config_entry)

async def test_device_sensor_creation(hass, storage_manager, synthetic_integration):
    """Test creating sensors for a device."""
    # Generate test sensor configs
    sensor_configs = generate_test_sensor_configs("test_device_123")

    # Create sensor set and add sensors
    sensor_set = await storage_manager.async_create_sensor_set(
        sensor_set_id="test_device_123_config",
        device_identifier="test_device_123",
        name="Test Device Configuration"
    )

    await sensor_set.async_replace_sensors(sensor_configs)

    # Verify storage
    stored_sensors = sensor_set.list_sensors()
    assert len(stored_sensors) == len(sensor_configs)
```

### Test Isolation

```python
@pytest.fixture(autouse=True)
async def cleanup_storage(hass):
    """Clean up storage between tests."""
    # Storage is automatically isolated per test via unique storage keys
    yield

    # Additional cleanup if needed
    storage_path = hass.config.path(".storage/test_storage")
    if os.path.exists(storage_path):
        os.remove(storage_path)
```

## Performance Considerations

### Bulk Operations

Use bulk operations for better performance:

```python
# Good: Bulk operation
sensor_set = await storage_manager.async_create_sensor_set(
    sensor_set_id="device_123_config",
    device_identifier="device_123"
)
await sensor_set.async_replace_sensors(all_sensor_configs)  # Process all at once

# Avoid: Individual operations
for config in sensor_configs:
    await sensor_set.async_add_sensor(config)  # Slower
```

### Storage Optimization

```python
# Initialize storage once
await storage_manager.async_load()

# Use SensorSet for focused operations
sensor_set = storage_manager.get_sensor_set("device_123_config")

# Batch updates using replace
updated_configs = modify_sensor_configs(existing_configs)
await sensor_set.async_replace_sensors(updated_configs)
```

## Error Handling and Debugging

### Logging Configuration

```python
import ha_synthetic_sensors

# Enable debug logging
ha_synthetic_sensors.configure_logging(logging.DEBUG)

# Check logging status
logging_info = ha_synthetic_sensors.get_logging_info()
_LOGGER.debug("Synthetic sensors logging: %s", logging_info)
```

### Common Issues

1. **Storage Not Initialized**: Always call `async_load()` on StorageManager
2. **Missing Data Provider**: Register backing entities before loading configuration
3. **Device Association**: Ensure device_identifier is consistent across all operations
4. **Entity ID Conflicts**: Use unique device identifiers and sensor names

### Debugging Tools

```python
# Check sensor set summary - clean handle pattern
sensor_set = storage_manager.get_sensor_set(f"{device_identifier}_config")

# Property access for debugging/logging
_LOGGER.info(f"Sensor set {sensor_set.sensor_set_id} has {sensor_set.sensor_count} sensors")
_LOGGER.debug(f"Device identifier: {sensor_set.device_identifier}")
_LOGGER.debug(f"Set name: {sensor_set.name}")

# Check sensor existence before operations
if sensor_set.sensor_exists("unique_id"):
    sensor = sensor_set.get_sensor("unique_id")
    _LOGGER.debug(f"Found sensor: {sensor.unique_id}")

# List all sensor sets with convenience methods
if storage_manager.sensor_set_exists(sensor_set_id):
    all_sets = storage_manager.list_sensor_sets()
    _LOGGER.debug("All sensor sets: %s", [s for s in all_sets])

# Check individual sensors
sensors = sensor_set.list_sensors()
_LOGGER.debug("Sensors in set: %s", [s.unique_id for s in sensors])

# Check registered entities
registered = sensor_manager.get_registered_entities()
_LOGGER.debug("Registered backing entities: %s", registered)
```

## Best Practices

### Integration Design

1. **SensorSet-Centric Organization**: Use SensorSet handles for focused operations on specific sensor groups
2. **Clean Handle Pattern**: Get SensorSet handle once, use for all operations on that sensor set
3. **Integration-Controlled IDs**: Maintain full control over sensor_set_id format and organization
4. **Bulk Operations**: Use bulk operations for multiple sensors via SensorSet interface
5. **Storage-First**: Store configuration in HA storage, not files
6. **Error Handling**: Implement robust error handling in data providers with custom exceptions
7. **Test Isolation**: Use unique storage keys per test to prevent test interference

### Configuration Management

1. **Consistent Naming**: Use consistent device identifiers and entity naming
2. **Backing Entities**: Use clear, parseable backing entity ID patterns
3. **Device Association**: Always associate sensors with devices when possible
4. **Validation**: Validate configurations before storing

### Performance

1. **Initialize Once**: Initialize StorageManager once during setup
2. **SensorSet Handles**: Use SensorSet handles for efficient, focused operations
3. **Batch Operations**: Use bulk operations for multiple sensors via SensorSet interface
4. **Efficient Data Providers**: Keep data provider callbacks fast and simple
5. **Storage Optimization**: Minimize storage operations, leverage SensorSet caching
