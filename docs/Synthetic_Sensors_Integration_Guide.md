# Synthetic Sensors Integration Guide

This guide demonstrates how to integrate the `ha-synthetic-sensors` library into your Home Assistant custom integration for
creating dynamic, formula-based sensors.

## Quick Start - Recommended Pattern

For most integrations, use this simplified pattern with **one function call**:

```python
# In your sensor.py platform
from ha_synthetic_sensors import async_setup_synthetic_sensors

async def async_setup_entry(hass, config_entry, async_add_entities):
    # Create your native sensors first
    native_entities = create_native_sensors(coordinator)
    async_add_entities(native_entities)

    # Then add synthetic sensors with one function call
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

The `async_setup_synthetic_sensors()` function handles all complexity while supporting both storage-based and YAML-based
configurations with full reload capabilities.

## Overview

The `ha-synthetic-sensors` library provides a complete solution for creating synthetic sensors that can perform calculations

- **Configuration Storage**: Persistent storage using HA's storage system OR YAML file discovery
- **Entity Creation**: Creates and manages actual Home Assistant sensor entities
- **Formula Evaluation**: Real-time calculation of sensor values using live data
- **Lifecycle Management**: Automatic entity updates, creation, and deletion
- **Reload Support**: Dynamic configuration reloading without HA restart

## Key Concepts

### Architecture

The library creates **actual Home Assistant sensor entities** that evaluate formulas using live data from your integration:

- **StorageManager**: Manages persistent storage and sensor configurations
- **SensorManager**: Creates and manages actual Home Assistant sensor entities
- **Data Provider**: Supplies live data to synthetic sensors from your integration
- **Formula Evaluator**: Calculates sensor values in real-time using formulas

### Configuration Options

Choose between two configuration approaches:

1. **Storage-Based** (Recommended): Configurations stored in HA's storage system, preserves user customizations
2. **YAML-Based**: Configurations in YAML files, supports file discovery and reload

### Integration Flow

1. **Setup Phase** (`__init__.py`): Generate and store sensor configurations
2. **Entity Creation Phase** (`sensor.py`): Create actual Home Assistant sensor entities
3. **Runtime Phase**: Sensors evaluate formulas using live data from your integration

## Standard Integration Pattern

### 1. Setup in `__init__.py`

```python
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
import ha_synthetic_sensors
from ha_synthetic_sensors import StorageManager

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up your integration from a config entry."""

    # Configure logging (optional)
    ha_synthetic_sensors.configure_logging(logging.DEBUG)

    # Create your coordinator
    coordinator = YourIntegrationCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    # Initialize storage manager for synthetic sensors
    storage_manager = StorageManager(hass, f"{DOMAIN}_synthetic")
    await storage_manager.async_load()

    # Generate synthetic sensor configurations (storage-first approach)
    await setup_synthetic_sensors_config(coordinator, storage_manager, entry)

    # Store for use in sensor platform
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "storage_manager": storage_manager,
    }

    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def setup_synthetic_sensors_config(
    coordinator: YourCoordinator,
    storage_manager: StorageManager,
    entry: ConfigEntry
) -> None:
    """Generate and store synthetic sensor configurations (storage-first approach)."""

    device_identifier = coordinator.device_id
    sensor_set_id = f"{device_identifier}_sensors"

    # Create or get sensor set
    if storage_manager.sensor_set_exists(sensor_set_id):
        sensor_set = storage_manager.get_sensor_set(sensor_set_id)

        # Existing storage - preserve user customizations
        # Only add new sensors that don't exist
        existing_sensor_ids = {s.unique_id for s in sensor_set.list_sensors()}
        default_configs = generate_default_sensor_configs(coordinator.data, device_identifier)
        new_sensors = [s for s in default_configs if s.unique_id not in existing_sensor_ids]

        if new_sensors:
            for sensor_config in new_sensors:
                await sensor_set.async_add_sensor(sensor_config)
            _LOGGER.info(f"Added {len(new_sensors)} new synthetic sensors")
    else:
        # Fresh install - create sensor set with defaults
        sensor_set = await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier=device_identifier,
            name=f"{coordinator.device_name} Sensors",
        )

        default_configs = generate_default_sensor_configs(coordinator.data, device_identifier)
        await sensor_set.async_replace_sensors(default_configs)
        _LOGGER.info(f"Created {len(default_configs)} default synthetic sensors")
```

### 2. Sensor Platform Setup in `sensor.py`

**Use the simplified one-function approach:**

```python
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from ha_synthetic_sensors import async_setup_synthetic_sensors
from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor platform."""

    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    storage_manager = data["storage_manager"]

    # Create native (non-synthetic) sensors first
    native_entities = create_native_sensors(coordinator)
    async_add_entities(native_entities)

    # Create synthetic sensors with one function call
    sensor_manager = await async_setup_synthetic_sensors(
        hass=hass,
        config_entry=entry,
        async_add_entities=async_add_entities,
        storage_manager=storage_manager,
        device_identifier=coordinator.device_id,
        data_provider_callback=create_data_provider_callback(coordinator),
    )

    # Optional: Store sensor manager for reload functionality
    data["sensor_manager"] = sensor_manager

def create_native_sensors(coordinator):
    """Create your integration's native sensors."""
    return [
        YourNativeSensor(coordinator, "power"),
        YourNativeSensor(coordinator, "energy"),
        # ... other native sensors
    ]
```

### 3. Data Provider Implementation

**Critical**: The data provider supplies live data to synthetic sensors:

```python
from ha_synthetic_sensors.types import DataProviderCallback, DataProviderResult

def create_data_provider_callback(coordinator: YourCoordinator) -> DataProviderCallback:
    """Create data provider callback for synthetic sensors."""

    def data_provider_callback(entity_id: str) -> DataProviderResult:
        """Provide live data for synthetic sensors from coordinator."""
        try:
            # Parse backing entity ID format: "your_domain_backing.device_123_power"
            if not entity_id.startswith(f"{DOMAIN}_backing."):
                return {"value": None, "exists": False}

            # Extract the backing entity part
            backing_part = entity_id.split(".", 1)[1]  # "device_123_power"

            # Parse device and sensor type from backing entity
            device_id, sensor_type = parse_backing_entity_id(backing_part)

            # Get current data from coordinator (no API calls!)
            device_data = coordinator.data.get_device(device_id)
            if not device_data:
                return {"value": None, "exists": False}

            # Return the requested sensor value
            value = getattr(device_data, sensor_type, None)
            return {"value": value, "exists": value is not None}

        except Exception as e:
            _LOGGER.error("Error in data provider callback for %s: %s", entity_id, e)
            return {"value": None, "exists": False}

    return data_provider_callback

def parse_backing_entity_id(backing_part: str) -> tuple[str, str]:
    """Parse 'device_123_power' -> ('123', 'power')"""
    # Implement based on your entity ID format
    parts = backing_part.rsplit("_", 1)
    if len(parts) == 2:
        device_id = parts[0].replace("device_", "")
        sensor_type = parts[1]
        return device_id, sensor_type
    raise ValueError(f"Invalid backing entity format: {backing_part}")
```

### 4. Sensor Configuration Generation

```python
from ha_synthetic_sensors.config_manager import SensorConfig, FormulaConfig

def generate_default_sensor_configs(device_data: Any, device_identifier: str) -> list[SensorConfig]:
    """Generate default sensor configurations for a device."""

    configs = []

    # Example 1: Simple power sensor
    power_config = SensorConfig(
        unique_id=f"{device_identifier}_current_power",
        name=f"{device_data.name} Current Power",
        entity_id=f"sensor.{device_identifier}_current_power",
        device_identifier=device_identifier,
        formulas=[
            FormulaConfig(
                id="main",
                formula="power_watts",
                variables={
                    "power_watts": f"{DOMAIN}_backing.{device_identifier}_power"
                },
                unit_of_measurement="W",
                device_class="power",
                state_class="measurement",
            )
        ],
    )
    configs.append(power_config)

    # Example 2: Calculated energy sensor
    daily_energy_config = SensorConfig(
        unique_id=f"{device_identifier}_daily_energy",
        name=f"{device_data.name} Daily Energy",
        entity_id=f"sensor.{device_identifier}_daily_energy",
        device_identifier=device_identifier,
        formulas=[
            FormulaConfig(
                id="main",
                formula="power_watts * hours_in_day / 1000",  # Convert W to kWh
                variables={
                    "power_watts": f"{DOMAIN}_backing.{device_identifier}_power",
                    "hours_in_day": "24"
                },
                unit_of_measurement="kWh",
                device_class="energy",
                state_class="total_increasing",
            )
        ],
    )
    configs.append(daily_energy_config)

    # Example 3: Multi-device calculation
    if device_data.has_multiple_circuits:
        total_power_config = SensorConfig(
            unique_id=f"{device_identifier}_total_power",
            name=f"{device_data.name} Total Power",
            entity_id=f"sensor.{device_identifier}_total_power",
            device_identifier=device_identifier,
            formulas=[
                FormulaConfig(
                    id="main",
                    formula="circuit_1 + circuit_2 + circuit_3",
                    variables={
                        "circuit_1": f"{DOMAIN}_backing.{device_identifier}_circuit_1_power",
                        "circuit_2": f"{DOMAIN}_backing.{device_identifier}_circuit_2_power",
                        "circuit_3": f"{DOMAIN}_backing.{device_identifier}_circuit_3_power",
                    },
                    unit_of_measurement="W",
                    device_class="power",
                    state_class="measurement",
                )
            ],
        )
        configs.append(total_power_config)

    return configs
```

## YAML-Based Configuration (Alternative)

For integrations that prefer YAML configuration files:

### 1. Enable YAML Discovery

```python
# In your __init__.py
from ha_synthetic_sensors import async_setup_integration, async_reload_integration

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Setup your coordinator...

    # Use YAML-based setup instead of storage
    success = await async_setup_integration(hass, entry, async_add_entities_callback)

    if success:
        # Register reload service for YAML files
        async def reload_synthetic_sensors(call):
            await async_reload_integration(hass, entry, async_add_entities_callback)

        hass.services.async_register(DOMAIN, "reload_synthetic_sensors", reload_synthetic_sensors)

    return success
```

### 2. YAML Configuration Files

Place YAML files in your integration's config directory:

```yaml
# config/synthetic_sensors/your_integration.yaml
version: "1.0"

global_settings:
  device_identifier: "device_123"

sensors:
  device_123_power:
    name: "Device Power"
    entity_id: "sensor.device_123_power"
    formula:
      formula: "power_value"
      variables:
        power_value: "your_integration_backing.device_123_power"
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  device_123_daily_energy:
    name: "Device Daily Energy"
    entity_id: "sensor.device_123_daily_energy"
    formula:
      formula: "power_value * 24 / 1000"
      variables:
        power_value: "your_integration_backing.device_123_power"
      unit_of_measurement: "kWh"
      device_class: "energy"
      state_class: "total_increasing"
```

### 3. Reload Support

```python
# Add reload capability to your integration
from ha_synthetic_sensors import async_reload_integration

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration and synthetic sensors."""

    # Reload your integration's data
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    await coordinator.async_refresh()

    # Reload synthetic sensors from YAML
    await async_reload_integration(hass, entry, async_add_entities_callback)
```

## Best Practices

### 1. Storage-First Approach (Recommended)

Always preserve user customizations:

```python
# CORRECT: Check existing storage first
if sensor_set.sensor_count == 0:
    # Fresh install - populate with defaults
    await sensor_set.async_replace_sensors(default_configs)
else:
    # Existing storage - only add missing sensors
    existing_ids = {s.unique_id for s in sensor_set.list_sensors()}
    new_sensors = [s for s in default_configs if s.unique_id not in existing_ids]
    for sensor in new_sensors:
        await sensor_set.async_add_sensor(sensor)

# WRONG: Always overwrite (destroys user customizations)
await sensor_set.async_replace_sensors(default_configs)
```

### 2. Efficient Data Providers

Use cached data, never make API calls in data providers:

```python
def create_data_provider_callback(coordinator):
    def data_provider_callback(entity_id: str):
        # CORRECT: Use coordinator's cached data
        return coordinator.get_cached_value(entity_id)

        # WRONG: Make API calls (will block sensor updates)
        # return api_client.get_live_value(entity_id)

    return data_provider_callback
```

### 3. Unique Sensor IDs

Use consistent, globally unique sensor IDs:

```python
# CORRECT: Include device identifier
unique_id = f"{device_identifier}_{sensor_type}"

# WRONG: Not unique across devices
unique_id = f"{sensor_type}"
```

### 4. Error Handling

Handle configuration errors gracefully:

```python
try:
    await async_setup_synthetic_sensors(...)
except Exception as e:
    _LOGGER.error("Failed to setup synthetic sensors: %s", e)
    # Continue with native sensors only
```

### 5. Configuration Validation

Validate configurations before storing:

```python
from ha_synthetic_sensors.config_manager import SensorConfig

def create_sensor_config(device_data, device_id):
    try:
        return SensorConfig(
            unique_id=f"{device_id}_power",
            name=f"{device_data.name} Power",
            # ... other fields
        )
    except ValueError as e:
        _LOGGER.error("Invalid sensor config for %s: %s", device_id, e)
        return None
```

## Reload and Dynamic Updates

### Service-Based Reload

```python
# Register reload service in your integration
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # ... setup code ...

    async def reload_synthetic_sensors(call):
        """Reload synthetic sensor configurations."""
        try:
            if "sensor_manager" in hass.data[DOMAIN][entry.entry_id]:
                # Storage-based reload
                storage_manager = hass.data[DOMAIN][entry.entry_id]["storage_manager"]
                sensor_manager = hass.data[DOMAIN][entry.entry_id]["sensor_manager"]

                # Reload from storage
                config = storage_manager.to_config(device_identifier=coordinator.device_id)
                await sensor_manager.load_configuration(config)
            else:
                # YAML-based reload
                await async_reload_integration(hass, entry, async_add_entities_callback)

            _LOGGER.info("Synthetic sensors reloaded successfully")
        except Exception as e:
            _LOGGER.error("Failed to reload synthetic sensors: %s", e)

    hass.services.async_register(DOMAIN, "reload_synthetic_sensors", reload_synthetic_sensors)
```

### Configuration Updates

```python
# Update configurations programmatically
async def update_sensor_configuration(sensor_set, unique_id, new_formula):
    """Update a sensor's formula."""

    sensor = sensor_set.get_sensor(unique_id)
    if sensor:
        # Modify the sensor configuration
        sensor.formulas[0].formula = new_formula
        await sensor_set.async_update_sensor(sensor)

        # Trigger reload to apply changes
        await reload_synthetic_sensors()
```

## Troubleshooting

### Common Issues

1. **Sensors not appearing**:
   - Check that `async_setup_synthetic_sensors()` is called in sensor platform
   - Verify storage manager is properly initialized

2. **Data not updating**:
   - Verify data provider callback returns correct format
   - Check that backing entity IDs match what data provider expects

3. **Configuration lost on restart**:
   - Ensure storage-first approach (don't overwrite existing configs)
   - Check storage manager is loaded before creating sensor sets

4. **Performance issues**:
   - Use cached data in data providers
   - Avoid API calls in data provider callbacks

### Debug Logging

Enable comprehensive debug logging:

```python
import ha_synthetic_sensors
ha_synthetic_sensors.configure_logging(logging.DEBUG)

# Check logging status
info = ha_synthetic_sensors.get_logging_info()
_LOGGER.debug("Logging configuration: %s", info)

# Test logging
ha_synthetic_sensors.test_logging()
```

### Validation

Test your integration with validation:

```python
from ha_synthetic_sensors import validate_yaml_content

# Validate YAML configuration
yaml_content = """
version: "1.0"
sensors:
  test_sensor:
    name: "Test"
    formula:
      formula: "a + b"
      variables:
        a: "sensor.input_a"
        b: "sensor.input_b"
"""

result = validate_yaml_content(yaml_content)
if result["is_valid"]:
    _LOGGER.info("Configuration valid: %d sensors", result["sensors_count"])
else:
    _LOGGER.error("Configuration errors: %s", result["errors"])
```

## API Reference

### Main Functions

- **`async_setup_synthetic_sensors()`**: Recommended one-function setup
- **`async_setup_integration()`**: YAML-based integration setup
- **`async_reload_integration()`**: Reload YAML configurations
- **`async_unload_integration()`**: Clean unload of integration

### Core Classes

- **`StorageManager`**: Manages persistent storage and sensor sets
- **`SensorSet`**: Handle for a group of sensors with CRUD operations
- **`SensorConfig`**: Configuration for individual sensors
- **`FormulaConfig`**: Configuration for sensor formulas
- **`SyntheticSensorsIntegration`**: Advanced integration class

### Utility Classes

- **`DeviceAssociationHelper`**: Device identification and association utilities
- **`EntityFactory`**: Factory patterns for creating sensor entities

### Type Definitions

- **`DataProviderCallback`**: Function signature for data providers
- **`DataProviderResult`**: Return format for data provider callbacks

This guide provides the complete, current approach for integrating synthetic sensors into Home Assistant custom integrations.
