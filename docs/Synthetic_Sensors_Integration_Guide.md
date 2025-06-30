# Home Assistant Synthetic Sensors Integration Guide

## Overview

This document provides a guide for Home Assistant integration developers on how to integrate
the `ha-synthetic-sensors` package into their custom integrations. It covers best practices,
import patterns, and implementation strategies for replacing native sensors with synthetic
equivalents while maintaining seamless migration and consistent entity IDs.

The SPAN Panel integration serves as a reference implementation demonstrating these patterns.

## Key Integration Principles

### Import Timing and Architecture

To successfully integrate ha-synthetic-sensors into your Home Assistant integration:

1. **Submodule Import Pattern**: Use lightweight top-level imports with submodule imports for heavy components
2. **Top-Level Imports**: Keep all imports at the top level of files to satisfy linters and type checkers
3. **Linter-Friendly**: Ensure proper type checking and IDE autocomplete support
4. **Performance Optimized**: Heavy modules only loaded when sensor platform loads (after HA is ready)

### Recommended Import Pattern

Use this **submodule import pattern** to avoid import timing issues:

#### In Your Integration's `__init__.py`

```python
# Lightweight import at top level - safe during HA initialization
import ha_synthetic_sensors

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Configure debug logging for ha-synthetic-sensors package
    ha_synthetic_sensors.configure_logging(logging.DEBUG)

    # ... rest of your setup logic
```

#### In Your Integration's `sensor.py`

```python
# Submodule imports at top level for heavy components
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.name_resolver import NameResolver

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    # Use the imported classes here
    sensor_manager = SensorManager(hass, name_resolver, async_add_entities, manager_config)
```

## Architecture Overview

### Integration Authority Model

When integrating ha-synthetic-sensors, use the **Integration Authority Model**:

1. **Your integration owns the data** - Your coordinator/API client fetches and manages device data
2. **Synthetic sensors package handles entity creation** - Creates HA entities based on YAML configuration
3. **Data provider callback** - Your integration provides data directly to synthetic sensors via callback
4. **Virtual backing entities** - Internal entity IDs used only for data mapping, never registered in HA

### Integration Components

```text
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   __init__.py   │───▶│ YourSensorManager│───▶│ ha-synthetic-sensors│
│                 │    │                  │    │     package         │
│ - Setup entry   │    │ - YAML generation│    │ - Entity creation   │
│ - Call synthetic│    │ - Data provider  │    │ - State management  │
│   setup         │    │ - Config mgmt    │    │                     │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
         │                       │                        │
         ▼                       ▼                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│  Coordinator    │    │ SyntheticConfig  │    │    sensor.py        │
│                 │    │    Manager       │    │                     │
│ - Data fetching │    │ - YAML file I/O  │    │ - Platform setup    │
│ - State updates │    │ - File mgmt      │    │ - Load synthetic    │
│                 │    │                  │    │   sensors           │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
```

## Integration Flow

### Your Integration → ha-synthetic-sensors Method Calls

#### Setup Phase (`__init__.py`)

```python
# Lightweight import at top level
import ha_synthetic_sensors

# Configure debug logging for ha-synthetic-sensors package
ha_synthetic_sensors.configure_logging(logging.DEBUG)

# Generate YAML configuration (writes to file system)
your_sensor_manager = YourSensorManager(hass, entry)
config_generated = await your_sensor_manager.generate_config(coordinator, coordinator.data)
```

#### Platform Setup (`sensor.py`)

```python
# Submodule imports at top level for heavy components
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.name_resolver import NameResolver

# Create SensorManager from ha-synthetic-sensors
sensor_manager = SensorManager(hass, name_resolver, async_add_entities, manager_config)

# Register backing entities (CRITICAL: must happen before load_configuration)
sensor_manager.register_data_provider_entities(backing_entities)

# Load YAML configuration - creates synthetic sensors in HA
await sensor_manager.load_configuration(config)
```

#### Runtime Data Updates

```python
# ha-synthetic-sensors calls your data provider callback
def data_provider_callback(entity_id: str) -> DataProviderResult:
    # Parse backing entity ID: "your_integration_synthetic_backing.device_1_power"
    # Return current coordinator data
    return {"value": actual_value, "exists": True}
```

### 1. Integration Setup (`__init__.py`)

```python
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # 1. Create your coordinator
    coordinator = YourIntegrationCoordinator(...)

    # 2. Perform initial data refresh
    await coordinator.async_config_entry_first_refresh()

    # 3. Set up synthetic sensors BEFORE platforms
    await setup_synthetic_sensors(hass, entry, coordinator)

    # 4. Set up platforms (sensor, switch, etc.)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
```

### 2. Synthetic Sensors Setup

```python
# Top-level imports - lightweight package import only
import ha_synthetic_sensors

async def setup_synthetic_sensors(hass: HomeAssistant, entry: ConfigEntry, coordinator: YourIntegrationCoordinator) -> None:
    # 1. Configure debug logging for ha-synthetic-sensors
    ha_synthetic_sensors.configure_logging(logging.DEBUG)

    # 2. Create your sensor manager
    your_sensor_manager = YourSensorManager(hass, entry)

    # 3. Generate YAML configuration
    config_generated = await your_sensor_manager.generate_config(coordinator, coordinator.data)

    # 4. Get registered backing entities
    registered_entities = await your_sensor_manager.get_registered_entity_ids(coordinator.data)

    # 5. Store manager and entities in hass.data for sensor.py
    hass.data[DOMAIN][entry.entry_id]["synthetic_manager"] = your_sensor_manager
    hass.data[DOMAIN][entry.entry_id]["backing_entities"] = registered_entities
```

### 3. Implementing Your Sensor Manager

You need to create a sensor manager class that generates YAML configuration for synthetic sensors:

```python
class YourSensorManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry

    async def generate_config(self, coordinator, device_data) -> bool:
        """Generate YAML configuration for synthetic sensors."""
        # Build your YAML configuration
        config = self._build_yaml_config(device_data)

        # Write to file
        config_manager = SyntheticConfigManager(self.hass, self.entry.entry_id)
        await config_manager.write_config(config)
        return True

    async def get_registered_entity_ids(self, device_data) -> set[str]:
        """Get backing entity IDs that your integration can provide data for."""
        entity_ids = set()

        # Generate backing entity IDs for your devices
        for device_id, device in device_data.devices.items():
            for sensor_type in ["power", "energy", "temperature"]:
                entity_id = f"your_integration_synthetic_backing.device_{device_id}_{sensor_type}"
                entity_ids.add(entity_id)

        return entity_ids
```

### 4. YAML Configuration Format

Your sensor manager generates YAML configuration that defines synthetic sensors:

```yaml
version: '1.0'
sensors:
  your_device_123_power:
    name: Living Room Device Power
    entity_id: sensor.your_integration_living_room_device_power
    formula: source_value
    variables:
      source_value: your_integration_synthetic_backing.device_123_power  # Virtual backing entity
    unit_of_measurement: W
    device_class: power
    state_class: measurement
    device_identifier: your_integration_device_123
```

#### Entity ID Construction

Entity IDs should be constructed consistently and respect user configuration options:

```python
# Device sensors
entity_id = construct_entity_id(
    coordinator,
    device_data,
    "sensor",
    device_name,
    device_id,
    sensor_suffix,
)

# Main device sensors
entity_id = construct_main_entity_id(
    coordinator,
    device_data,
    "sensor",
    suffix,
)
```

Consider implementing config options for:

- `use_device_prefix`: Controls whether integration name prefix is added
- `use_friendly_names`: Controls friendly vs technical naming
- `naming_pattern`: Different entity ID patterns for different use cases

### 5. Data Provider Callback

Your integration provides data directly to synthetic sensors via callback:

```python
def create_data_provider_callback(self, coordinator, device_data):
    """Create a data provider callback for synthetic sensors."""

    def data_provider_callback(entity_id: str) -> DataProviderResult:
        # Parse virtual entity ID: "your_integration_synthetic_backing.device_123_power"
        try:
            # Extract device ID and sensor type from entity_id
            parts = entity_id.split(".")
            if len(parts) != 2 or not parts[1].startswith("device_"):
                return {"value": None, "exists": False}

            # Parse device_123_power -> device_id=123, sensor_type=power
            device_part = parts[1]  # "device_123_power"
            device_id, sensor_type = self._parse_device_entity(device_part)

            # Get current data from coordinator
            device = device_data.devices.get(device_id)
            if not device:
                return {"value": None, "exists": False}

            # Return the requested sensor value
            value = getattr(device, sensor_type, None)
            return {"value": value, "exists": value is not None}

        except Exception as e:
            _LOGGER.error("Error in data provider callback: %s", e)
            return {"value": None, "exists": False}

    return data_provider_callback
```

### 6. Platform Setup (`sensor.py`)

```python
# Top-level submodule imports for heavy components
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.name_resolver import NameResolver

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    # 1. Get synthetic manager from hass.data
    synthetic_manager = hass.data[DOMAIN][entry.entry_id].get("synthetic_manager")

    # 2. Load synthetic sensors using ha-synthetic-sensors package
    if synthetic_manager:
        yaml_path = hass.data[DOMAIN][entry.entry_id].get("yaml_path")

        # Create data provider callback
        data_provider_callback = synthetic_manager.create_data_provider_callback(coordinator, coordinator.data)

        # Configure SensorManager with data provider
        manager_config = SensorManagerConfig(
            device_info=device_info,
            unique_id_prefix="",
            lifecycle_managed_externally=True,
            data_provider_callback=data_provider_callback,
            integration_domain=DOMAIN,
        )

        sensor_manager = SensorManager(hass, name_resolver, async_add_entities, manager_config)

        # Register backing entities that we can provide data for
        sensor_manager.register_data_provider_entities(backing_entities)

        # Load YAML configuration - THIS CREATES THE SYNTHETIC SENSORS
        await sensor_manager.load_configuration(config)

    # 3. Create native status sensors (non-synthetic)
    status_entities = create_status_sensors(...)
    async_add_entities(status_entities)
```

### 6. Backing Entity Registration

#### What are Backing Entities?

Backing entities are **virtual entity IDs** that represent the data sources for synthetic sensors. They are:

- **Never registered in Home Assistant** - They don't appear in `hass.states`
- **Used only for data mapping** - They connect synthetic sensors to our data provider
- **Internal to the integration** - They're implementation details, not user-facing

#### Backing Entity Format

```python
# Circuit sensors
"span_panel_synthetic_backing.circuit_1_power"
"span_panel_synthetic_backing.circuit_1_energy_consumed"
"span_panel_synthetic_backing.circuit_15_power"  # Solar panels

# Panel sensors
"span_panel_synthetic_backing.circuit_0_instant_grid_power"
"span_panel_synthetic_backing.circuit_0_feedthrough_power"
```

#### Registration Process

1. **Generation** (`SpanSensorManager.get_registered_entity_ids()`):

   ```python
   # Generate backing entity IDs for all circuits and panel sensors
   entity_ids = set()

   # Panel sensors (circuit_0)
   for panel_key in PANEL_SENSOR_MAP:
       entity_id = f"{device_name}_synthetic_backing.circuit_0_{panel_key}"
       entity_ids.add(entity_id)

   # Circuit sensors
   for circuit_id, circuit_data in span_panel.circuits.items():
       circuit_number = get_circuit_number(circuit_data)
       for suffix in CIRCUIT_FIELD_MAP:
           entity_id = f"{device_name}_synthetic_backing.circuit_{circuit_number}{suffix}"
           entity_ids.add(entity_id)
   ```

2. **Registration** (`sensor.py`):

   ```python
   # Tell synthetic package which backing entities we can provide data for
   sensor_manager.register_data_provider_entities(backing_entities)
   ```

3. **YAML Mapping** (Generated YAML):

   ```yaml
   sensors:
     span_sp3-242424-001_circuit_1_instantpowerw:
       entity_id: sensor.span_panel_kitchen_outlets_power  # User-facing entity
       variables:
         source_value: span_panel_synthetic_backing.circuit_1_power  # Backing entity
   ```

#### Why Registration is Critical

- **Validation**: Synthetic package validates that we can provide data for all backing entities referenced in YAML
- **Callback Routing**: When synthetic sensor needs data, it calls our callback with the backing entity ID
- **Error Prevention**: Prevents synthetic sensors from being created for non-existent data sources

#### Static Caching and Multiple Invocation Protection

The backing entity registration uses **static class-level caching** to ensure consistency:

```python
class SpanSensorManager:
    # Class-level cache for registered entities (static across all instances)
    _static_registered_entities: set[str] | None = None
    _static_entities_generated: bool = False
    static_entities_registered: bool = False  # Public for cross-module access

async def get_registered_entity_ids(self, span_panel: Any) -> set[str]:
    # Return static cached result if available to ensure consistency across ALL instances
    if SpanSensorManager._static_registered_entities is not None:
        return SpanSensorManager._static_registered_entities.copy()

    # Generate entities only once, then cache statically
    entity_ids = set()
    # ... generate backing entities ...

    # Cache the result statically for ALL instances
    SpanSensorManager._static_registered_entities = entity_ids.copy()
    SpanSensorManager._static_entities_generated = True

    return entity_ids
```

**Why Static Caching is Essential:**

The SPAN Panel integration has **multiple sensor platforms and configs** that all need backing entities:

- **Circuit sensors** (synthetic) - need `circuit_X_power`, `circuit_X_energy_consumed`, etc.
- **Panel sensors** (synthetic) - need `circuit_0_instant_grid_power`, `circuit_0_feedthrough_power`, etc.
- **Status sensors** (native) - don't need backing entities but share the same manager

Without static caching, each platform setup could generate **different backing entity lists**, causing:

- **Registration mismatches**: sensor.py registers one set, but YAML references another
- **Data provider failures**: Synthetic sensors request backing entities that weren't registered
- **Inconsistent behavior**: Different calls return different entity sets

**Static caching solves this by:**

- **Single generation**: First call generates the complete backing entity list for ALL sensor types
- **Shared consistency**: All subsequent calls (from any platform) get the same list
- **Cross-platform reliability**: Circuit sensors, panel sensors, and status sensors all see identical backing entities

#### Integration Ownership of Backing Store

The SPAN Panel integration **owns the entire backing store architecture**:

- **YAML generation**: Integration generates and manages the YAML configuration files
- **Backing entity definition**: Integration defines all virtual backing entity IDs
- **Data provider implementation**: Integration provides the callback that supplies live data
- **File lifecycle**: Integration handles YAML creation, updates, and cleanup

This gives the integration **complete control** over the synthetic sensor ecosystem, while the ha-synthetic-sensors
package handles the HA entity lifecycle and state management. Future enhancements might move to JSON storage or other
formats, but the integration will continue to own the backing store design and data flow.

### 7. Data Flow and Update Cycle

#### Who Calls What and When

1. **Integration Setup** (`__init__.py`):
   - Calls `setup_synthetic_sensors()`
   - Creates `SpanSensorManager`
   - Generates YAML configuration
   - Stores data provider callback in hass.data

2. **Platform Setup** (`sensor.py`):
   - Calls `SensorManager.register_data_provider_entities(backing_entities)` - **This tells synthetic package which virtual
     entities we can provide data for**
   - Calls `SensorManager.load_configuration(config)` - **This creates the actual synthetic sensor entities in HA**

3. **Data Updates** (Automatic via HA):
   - **Home Assistant calls synthetic sensor `async_update()`** when it needs fresh data
   - **Synthetic sensor calls our data provider callback** with backing entity ID like `"span_panel_synthetic_backing.circuit_1_power"`
   - **Our callback parses the entity ID** to extract circuit number and field type
   - **Our callback fetches current data from coordinator** (always live data, no caching)
   - **Our callback returns `{"value": actual_value, "exists": True}`**
   - **Synthetic sensor updates its state** with the returned value and triggers HA state change

#### Update Triggers

- **Coordinator Updates**: When SPAN panel coordinator fetches new data (every scan_interval)
- **HA State Requests**: When HA dashboard, automations, or other components request current state
- **Manual Refresh**: When user manually refreshes entity or calls `homeassistant.update_entity`
- **Dependency Updates**: When synthetic sensor dependencies change (though we use simple `source_value` formula)

#### Update Flow Diagram

```text
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│ Home Assistant  │───▶│ Synthetic Sensor │───▶│  Data Provider      │
│                 │    │                  │    │   Callback          │
│ - Calls         │    │ - async_update() │    │ - Gets coordinator  │
│   async_update()│    │ - Requests data  │    │   data              │
│ - Needs fresh   │    │   from callback  │    │ - Parses entity_id  │
│   sensor data   │    │                  │    │ - Returns value     │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
         ▲                       │                        │
         │                       ▼                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│ Updated Sensor  │◀───│ Synthetic Sensor │◀───│    Coordinator      │
│    State        │    │    Updates       │    │                     │
│                 │    │ - Sets new state │    │ - Current panel     │
│ - New value     │    │ - Triggers HA    │    │   data              │
│ - Attributes    │    │   state change   │    │ - Circuit data      │
│ - Timestamp     │    │                  │    │ - Panel data        │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
```

## 8. Entity Types and Mapping

### Circuit Sensors (Synthetic)

| Native Entity | Synthetic Entity | Backing Entity |
|---------------|------------------|----------------|
| `sensor.span_panel_kitchen_outlets_power` | Same entity ID | `span_panel_synthetic_backing.circuit_1_power` |
| `sensor.span_panel_kitchen_outlets_energy_consumed` | Same entity ID | `span_panel_synthetic_backing.circuit_1_energy_consumed` |
| `sensor.span_panel_kitchen_outlets_energy_produced` | Same entity ID | `span_panel_synthetic_backing.circuit_1_energy_produced` |

### Panel Sensors (Synthetic)

| Native Entity | Synthetic Entity | Backing Entity |
|---------------|------------------|----------------|
| `sensor.span_panel_current_power` | Same entity ID | `span_panel_synthetic_backing.circuit_0_instant_grid_power` |
| `sensor.span_panel_feed_through_power` | Same entity ID | `span_panel_synthetic_backing.circuit_0_feedthrough_power` |

### Status Sensors (Native - Not Synthetic)

| Entity | Type | Notes |
|--------|------|-------|
| `sensor.span_panel_dsm_state` | Native | Panel operational state |
| `sensor.span_panel_door_state` | Native | Hardware status |
| `sensor.span_panel_wifi_strength` | Native | Hardware status |

## 9. Configuration Management

### SyntheticConfigManager

Handles YAML file operations:

```python
class SyntheticConfigManager:
    # Singleton pattern for shared config management
    _instances: dict[str, SyntheticConfigManager] = {}

    async def write_config(self, config: dict) -> None:
        # Write YAML with timestamp for deterministic completion
        # Use flush() and fsync() for reliable file writing

    async def delete_all_device_sensors(self, device_id: str) -> int:
        # Remove sensors for specific device

    def write_config_with_timestamp(self, config: dict) -> None:
        # Atomic write with timestamp verification
```

### File Locations

- **Production**: `<config_dir>/custom_components/span_panel/span_sensors.yaml`
- **Testing**: `.venv/lib/python3.13/site-packages/pytest_homeassistant_custom_component/testing_config/custom_components/span_panel/span_sensors.yaml`

## 10. Test Isolation Issues and Solutions

### Root Cause Analysis

When tests run together, three types of state pollution occurred:

1. **YAML File Persistence**: YAML files from previous tests persisted in pytest testing directory
2. **SyntheticConfigManager Singleton Cache**: Config manager cached state between tests
3. **Static State in SpanSensorManager**: Class-level static variables carried over between tests

### Symptoms

- **Test works when run alone**: No previous state to interfere
- **Test fails when run with others**: State pollution from first test
- **Entity ID mismatches**: First test creates YAML with one config, second test uses cached version

## Quick Start Checklist

For integration developers wanting to add ha-synthetic-sensors support:

### 1. Import Pattern Setup

```python
# In your __init__.py
import ha_synthetic_sensors  # Lightweight import

# In your sensor.py
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.name_resolver import NameResolver
```

### 2. Create Your Sensor Manager

```python
class YourSensorManager:
    async def generate_config(self, coordinator, device_data) -> bool:
        # Generate YAML configuration

    async def get_registered_entity_ids(self, device_data) -> set[str]:
        # Return backing entity IDs you can provide data for

    def create_data_provider_callback(self, coordinator, device_data):
        # Return callback function that provides live data
```

### 3. Integration Setup Flow

1. **`__init__.py`**: Configure logging, generate YAML, store manager in hass.data
2. **`sensor.py`**: Create SensorManager, register backing entities, load configuration
3. **Runtime**: Data provider callback supplies live data to synthetic sensors

### Solution Implementation

#### conftest.py Test Isolation

```python
@pytest.fixture(autouse=True)
def reset_static_state():
    """Reset static state before each test to prevent pollution."""

    # 1. Reset SpanSensorManager static state
    from custom_components.span_panel.span_sensor_manager import SpanSensorManager
    SpanSensorManager._static_registered_entities = None
    SpanSensorManager._static_entities_generated = False
    SpanSensorManager.static_entities_registered = False

    # 2. Clean up YAML files in correct locations
    yaml_locations = [
        Path.cwd() / "custom_components" / "span_panel",
        Path(os.getcwd()) / ".venv/lib/python3.13/site-packages/pytest_homeassistant_custom_component/testing_config/custom_components/span_panel",
    ]

    for location in yaml_locations:
        for filename in ["span_sensors.yaml", "solar_synthetic_sensors.yaml"]:
            yaml_file = location / filename
            if yaml_file.exists():
                yaml_file.unlink()

    # 3. Clear SyntheticConfigManager singleton cache
    from custom_components.span_panel.synthetic_config_manager import SyntheticConfigManager
    SyntheticConfigManager._instances = {}

    # 4. Reset ha-synthetic-sensors package state
    import ha_synthetic_sensors
    if hasattr(ha_synthetic_sensors, '_global_sensor_managers'):
        ha_synthetic_sensors._global_sensor_managers = {}
    if hasattr(ha_synthetic_sensors, '_registered_integrations'):
        ha_synthetic_sensors._registered_integrations = set()

    yield
```

#### Test Configuration Consistency

All tests must use consistent config entry options:

```python
options = {
    "use_device_prefix": True,
    "use_circuit_numbers": False,
}
entry, _ = setup_span_panel_entry(hass, mock_responses, options=options)
```

## 11. Debugging and Logging

### Debug Logging Setup

```python
# Lightweight package import at top level
import ha_synthetic_sensors

# Enable debug logging for ha-synthetic-sensors package
ha_synthetic_sensors.configure_logging(logging.DEBUG)

# Check logging configuration
logging_info = ha_synthetic_sensors.get_logging_info()
_LOGGER.debug("Synthetic sensors logging config: %s", logging_info)
```

### Key Debug Points

1. **YAML Generation**: Log when YAML is created and file paths
2. **Entity Registration**: Log backing entities being registered
3. **Data Provider Calls**: Log when synthetic sensors request data
4. **File Operations**: Log YAML file creation/deletion
5. **Static State**: Log static variable resets

### Common Issues and Solutions

#### Issue: Entity IDs Don't Match Expected Format

**Symptom**: Test expects `sensor.span_panel_kitchen_outlets_power` but gets `sensor.kitchen_outlets_power`

**Cause**: Config entry options not set correctly or static state pollution

**Solution**:

1. Ensure all tests set consistent options
2. Verify conftest.py is resetting static state
3. Check YAML file cleanup

#### Issue: Synthetic Sensors Show as 'unavailable'

**Symptom**: Synthetic sensors exist but show unavailable state

**Cause**: Data provider callback not being called or returning invalid data

**Solution**:

1. Verify backing entities are registered correctly
2. Check data provider callback implementation
3. Ensure coordinator data is available

#### Issue: Tests Pass Individually But Fail Together

**Symptom**: Classic test isolation problem

**Cause**: State pollution between tests

### Specific Testing Fixes Implemented

#### 1. Static State Reset (`conftest.py`)

```python
@pytest.fixture(autouse=True)
def reset_static_state():
    """Reset static state before each test to prevent pollution."""
    # Reset SpanSensorManager static state
    from custom_components.span_panel.span_sensor_manager import SpanSensorManager
    SpanSensorManager._static_registered_entities = None
    SpanSensorManager._static_entities_generated = False
    SpanSensorManager.static_entities_registered = False

    # Clean up YAML files in both possible locations
    yaml_locations = [
        Path.cwd() / "custom_components" / "span_panel",
        Path(os.getcwd()) / ".venv/lib/python3.13/site-packages/pytest_homeassistant_custom_component/testing_config/custom_components/span_panel",
    ]

    for location in yaml_locations:
        for filename in ["span_sensors.yaml", "solar_synthetic_sensors.yaml"]:
            yaml_file = location / filename
            if yaml_file.exists():
                yaml_file.unlink()

    # Clear SyntheticConfigManager singleton cache
    from custom_components.span_panel.synthetic_config_manager import SyntheticConfigManager
    SyntheticConfigManager._instances = {}

    # Reset ha-synthetic-sensors package state
    import ha_synthetic_sensors
    if hasattr(ha_synthetic_sensors, '_global_sensor_managers'):
        ha_synthetic_sensors._global_sensor_managers.clear()
    if hasattr(ha_synthetic_sensors, '_registered_integrations'):
        ha_synthetic_sensors._registered_integrations.clear()
```

#### 2. Consistent Test Configuration

All tests were updated to use identical config entry options:

```python
options = {
    "use_device_prefix": True,
    "use_circuit_numbers": False,
}
entry, _ = setup_span_panel_entry(hass, mock_responses, options=options)
```

#### 3. Test Helper Functions (`tests/helpers.py`)

```python
def cleanup_synthetic_yaml_files(hass: HomeAssistant) -> None:
    """Clean up synthetic sensor YAML files to ensure clean test state."""
    main_yaml_path = Path(hass.config.config_dir) / "custom_components" / "span_panel" / "span_sensors.yaml"
    if main_yaml_path.exists():
        main_yaml_path.unlink()

    solar_yaml_path = Path(hass.config.config_dir) / "custom_components" / "span_panel" / "solar_synthetic_sensors.yaml"
    if solar_yaml_path.exists():
        solar_yaml_path.unlink()

def reset_span_sensor_manager_static_state() -> None:
    """Reset static state in SpanSensorManager to prevent test pollution."""
    from custom_components.span_panel.span_sensor_manager import SpanSensorManager
    SpanSensorManager._static_registered_entities = None
    SpanSensorManager._static_entities_generated = False
    SpanSensorManager.static_entities_registered = False

async def wait_for_synthetic_sensors(hass: HomeAssistant) -> None:
    """Wait for synthetic sensors to be created by yielding to the event loop."""
    for _ in range(5):
        await hass.async_block_till_done()
```

#### 4. Logging Configuration Issues (Unresolved)

The logging configuration was never fully resolved. There are conflicting fixtures in `conftest.py`:

```python
@pytest.fixture(autouse=True)
def configure_ha_synthetic_logging():
    # Attempts to set up ha-synthetic-sensors logging

@pytest.fixture(autouse=True)
def force_ha_synthetic_sensors_logging():
    # Different approach to logging setup
```

**Issues encountered:**

- **Conflicting fixtures**: Multiple auto-use fixtures trying to configure the same loggers
- **Handler conflicts**: Duplicate handlers causing logging issues
- **Package integration**: ha-synthetic-sensors internal logging not cooperating with test setup
- **Propagation problems**: Logger propagation settings interfering with output

**Current state**: Logging configuration remains problematic and was not essential for solving the core test isolation issues.

**Solution**: These comprehensive fixes ensure complete test isolation

## 12. Migration Considerations

### Seamless Migration Strategy

1. **Same Unique IDs**: Synthetic sensors should use identical unique IDs as original native sensors that you are replacing
2. **Same Entity IDs**: Users should see no change in entity IDs
3. **Same Device Association**: Sensors remain associated with same device

## 13. Performance Considerations

### Static Caching

SpanSensorManager uses static caching to ensure consistency:

```python
# Cache results statically for ALL instances
SpanSensorManager._static_registered_entities = entity_ids.copy()
SpanSensorManager._static_entities_generated = True
```

### File I/O Optimization

- **Atomic writes**: Single write operation instead of multiple incremental writes
- **Timestamp verification**: Ensure file completion before proceeding
- **Flush and fsync**: Guarantee data is written to disk
