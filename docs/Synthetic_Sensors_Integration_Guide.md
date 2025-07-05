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
│   Your Integration  │───▶│ BulkConfigService   │───▶│   StorageManager    │
│                     │    │                     │    │                     │
│ - Device data       │    │ - Device sensor     │    │ - HA storage        │
│ - Sensor configs    │    │   sets              │    │ - Sensor metadata   │
│ - Data provider     │    │ - Bulk operations   │    │ - Device association│
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
│   ConfigConverter   │    │ Config/Formula Data │
│                     │    │                     │
│ - YAML ↔ Storage    │    │ - Formulas          │
│ - Format conversion │    │ - Variables         │
│ - Migration support │    │ - Attributes        │
└─────────────────────┘    └─────────────────────┘
```

### Architectural Principles

1. **Dual Configuration Support**: Both file-based YAML and storage-based configuration
2. **Smart Configuration Detection**: Auto-discovery skipped when storage is in use
3. **Device-Centric Organization**: Sensors can be grouped by device for bulk management
4. **Integration Authority**: Your integration owns data, synthetic sensors handle entities
5. **Flexible Workflow**: Choose between file-based simplicity or storage-based programmatic control

## Quick Start Integration Pattern

### 1. Basic Setup in `__init__.py`

```python
import ha_synthetic_sensors
from ha_synthetic_sensors.bulk_config_service import BulkConfigService

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Configure logging
    ha_synthetic_sensors.configure_logging(logging.DEBUG)

    # Create your coordinator
    coordinator = YourIntegrationCoordinator(...)
    await coordinator.async_config_entry_first_refresh()

    # Initialize bulk config service
    bulk_service = BulkConfigService(hass, DOMAIN)
    await bulk_service.async_initialize()

    # Store for use in sensor platform
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "bulk_service": bulk_service,
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
    bulk_service = data["bulk_service"]

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
        bulk_service,
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
    bulk_service: BulkConfigService,
    sensor_manager: SensorManager,
    device_identifier: str
) -> None:
    """Set up synthetic sensors for your integration."""

    # Generate sensor configurations from your device data
    sensor_configs = generate_sensor_configs(coordinator.data, device_identifier)

    # Add sensors to device in bulk
    sensor_set_id = await bulk_service.async_add_sensors_to_device(
        device_identifier=device_identifier,
        sensor_configs=sensor_configs,
        device_name=coordinator.device_name,
    )

    # Register data provider entities
    backing_entities = generate_backing_entity_ids(coordinator.data, device_identifier)
    sensor_manager.register_data_provider_entities(backing_entities)

    # Convert storage to config and load
    config = bulk_service.storage_manager.to_config(device_identifier=device_identifier)
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

1. **Sensor Sets**: Groups of sensors defined within a single YAML file
2. **Storage Persistence**: Configuration stored in HA's storage system
3. **Bulk Operations**: Operations for managing multiple sensors within a sensor set

### BulkConfigService API

```python
# Device-centric sensor management
sensor_set_id = await bulk_service.async_create_device_sensor_set(
    device_identifier="your_device_123",
    device_name="Living Room Device",
    description="Power monitoring sensors"
)

# Add sensors to device
await bulk_service.async_add_sensors_to_device(
    device_identifier="your_device_123",
    sensor_configs=sensor_configs,
    device_name="Living Room Device"
)

# Replace all sensors for a device
await bulk_service.async_replace_device_sensors(
    device_identifier="your_device_123",
    sensor_configs=new_sensor_configs,
    device_name="Living Room Device"
)

# Delete all sensors for a device
deleted_count = await bulk_service.async_delete_device_sensors("your_device_123")

# Import from YAML (compatibility)
sensor_set_id = await bulk_service.async_import_yaml_for_device(
    device_identifier="your_device_123",
    yaml_content=yaml_content,
    replace_existing=True
)

# Export to YAML
yaml_content = await bulk_service.async_export_device_yaml("your_device_123")
```

### StorageManager Direct Access

```python
# For advanced use cases, access storage manager directly
storage_manager = bulk_service.storage_manager

# Convert between formats
config = storage_manager.to_config(device_identifier="your_device_123")
await storage_manager.async_from_config(config, sensor_set_id, device_identifier)

# Query sensors
sensors = storage_manager.list_sensors(device_identifier="your_device_123")
sensor_sets = storage_manager.list_sensor_sets(device_identifier="your_device_123")
```

## Migration from File-Based Configuration

### For Existing Integrations

If you have existing YAML-based configurations, use the migration path:

```python
async def migrate_yaml_to_storage(
    bulk_service: BulkConfigService,
    yaml_file_path: str,
    device_identifier: str
) -> bool:
    """Migrate existing YAML configuration to storage."""
    try:
        # Read existing YAML (non-blocking)
        def _read_yaml_file():
            with open(yaml_file_path, 'r') as f:
                return f.read()

        yaml_content = await hass.async_add_executor_job(_read_yaml_file)

        # Import to storage
        await bulk_service.async_import_yaml_for_device(
            device_identifier=device_identifier,
            yaml_content=yaml_content,
            replace_existing=True
        )

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

- **Integration-controlled**: Your integration interacts with configuration via `BulkConfigService`
- **HA storage system**: Configuration persisted in storage allocated by the integration (via Home Assistant)
- **Full CRUD**: Add, update, delete individual sensors programmatically
- **Device-centric**: Organize sensors by YAML in-memory handoff (with a sensor_set_id) for bulk loads
- **YAML Import/Export**: Full roundtrip lossless export on a per-sensor_set_id granularity
- **In storage Consistency**:  Event listeners update sensor references for any sensor entity_id and name changes in HA

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
async def bulk_service(hass):
    """Create bulk config service for testing."""
    service = BulkConfigService(hass, "test_storage")
    await service.async_initialize()
    return service

@pytest.fixture
async def synthetic_integration(hass, mock_config_entry):
    """Create synthetic sensors integration for testing."""
    return SyntheticSensorsIntegration(hass, mock_config_entry)

async def test_device_sensor_creation(hass, bulk_service, synthetic_integration):
    """Test creating sensors for a device."""
    # Generate test sensor configs
    sensor_configs = generate_test_sensor_configs("test_device_123")

    # Add to device
    sensor_set_id = await bulk_service.async_add_sensors_to_device(
        device_identifier="test_device_123",
        sensor_configs=sensor_configs,
        device_name="Test Device"
    )

    # Verify storage
    stored_sensors = bulk_service.storage_manager.list_sensors(
        device_identifier="test_device_123"
    )
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
await bulk_service.async_add_sensors_to_device(
    device_identifier="device_123",
    sensor_configs=all_sensor_configs  # Process all at once
)

# Avoid: Individual operations
for config in sensor_configs:
    await storage_manager.async_store_sensor(config, sensor_set_id)  # Slower
```

### Storage Optimization

```python
# Initialize storage once
await bulk_service.async_initialize()

# Batch updates
updates = [
    {"unique_id": "sensor1", "formula": "new_formula1"},
    {"unique_id": "sensor2", "formula": "new_formula2"},
]
results = await bulk_service.async_batch_update_sensors(updates)
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

1. **Storage Not Initialized**: Always call `async_initialize()` on BulkConfigService
2. **Missing Data Provider**: Register backing entities before loading configuration
3. **Device Association**: Ensure device_identifier is consistent across all operations
4. **Entity ID Conflicts**: Use unique device identifiers and sensor names

### Debugging Tools

```python
# Check device summary
summary = bulk_service.get_device_summary("device_123")
_LOGGER.info("Device summary: %s", summary)

# Validate configuration
validation = bulk_service.validate_device_configuration("device_123")
if not validation["is_valid"]:
    _LOGGER.error("Configuration errors: %s", validation["errors"])

# Check registered entities
registered = sensor_manager.get_registered_entities()
_LOGGER.debug("Registered backing entities: %s", registered)
```

## Best Practices

### Integration Design

1. **YAML-Centric Organization**: Sensors are organized by YAML file structure, with optional device association via global `device_identifier`
2. **Bulk Operations**: Use bulk operations for multiple sensors
3. **Storage-First**: Store configuration in HA storage, not files
4. **Error Handling**: Implement robust error handling in data providers
5. **Test Isolation**: Use unique storage keys per test to prevent test interference

### Configuration Management

1. **Consistent Naming**: Use consistent device identifiers and entity naming
2. **Backing Entities**: Use clear, parseable backing entity ID patterns
3. **Device Association**: Always associate sensors with devices when possible
4. **Validation**: Validate configurations before storing

### Performance

1. **Initialize Once**: Initialize services once during setup
2. **Batch Operations**: Use bulk operations for multiple sensors
3. **Efficient Data Providers**: Keep data provider callbacks fast and simple
4. **Storage Optimization**: Minimize storage operations
