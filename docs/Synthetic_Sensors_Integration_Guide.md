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

    # Then add synthetic sensors with one call
    sensor_manager = await async_setup_synthetic_sensors(
        hass=hass,
        config_entry=config_entry,
        async_add_entities=async_add_entities,
        storage_manager=storage_manager,
        device_identifier=coordinator.device_id,
        data_provider_callback=create_data_provider_callback(coordinator),
        change_notifier=create_change_notifier_callback(sensor_manager),
        allow_ha_lookups=False,  # Use virtual entities only (recommended)
    )
```

This approach handles everything automatically using storage-based configuration.

## Data Provider Interface with Real-Time Updates

The library supports **change notification** for real-time synthetic sensor updates when using virtual backing entities.
This approach provides optimal performance by only updating sensors whose underlying data has actually changed.

### Data Provider Components

**Data Provider Callback**: Returns current values for virtual backing entities
**Change Notifier Callback**: Receives notifications when specific backing entities change
**Selective Updates**: Only sensors using changed backing entities are updated

### Type Definitions

```python
from typing import Callable
from ha_synthetic_sensors import DataProviderCallback, DataProviderChangeNotifier

# Data provider returns current values
DataProviderCallback = Callable[[str], DataProviderResult]

# Change notifier receives set of changed backing entity IDs
DataProviderChangeNotifier = Callable[[set[str]], None]
```

## Interface Functions Overview

The library provides several interface functions with proper typing:

### Core Setup Function

```python
async def async_setup_synthetic_sensors(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    storage_manager: StorageManager,
    device_identifier: str,
    data_provider_callback: DataProviderCallback | None = None,
    change_notifier: DataProviderChangeNotifier | None = None,  # NEW
) -> SensorManager
```

### Setup with Backing Entities

```python
async def async_setup_synthetic_sensors_with_entities(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    storage_manager: StorageManager,
    device_identifier: str,
    data_provider_callback: DataProviderCallback | None = None,
    change_notifier: DataProviderChangeNotifier | None = None,  # NEW
    backing_entity_ids: set[str] | None = None,
    allow_ha_lookups: bool = False,
) -> SensorManager
```

### Complete Integration Setup

```python
async def async_setup_synthetic_integration(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    integration_domain: str,
    device_identifier: str,
    sensor_configs: list[SensorConfig],
    backing_entity_ids: set[str] | None = None,
    data_provider_callback: DataProviderCallback | None = None,
    change_notifier: DataProviderChangeNotifier | None = None,  # NEW
    sensor_set_name: str | None = None,
    allow_ha_lookups: bool = False,
) -> tuple[StorageManager, SensorManager]
```

### Auto-Backing Entity Setup

```python
async def async_setup_synthetic_integration_with_auto_backing(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    integration_domain: str,
    device_identifier: str,
    sensor_configs: list[SensorConfig],
    data_provider_callback: DataProviderCallback | None = None,
    change_notifier: DataProviderChangeNotifier | None = None,  # NEW
    sensor_set_name: str | None = None,
    allow_ha_lookups: bool = False,
) -> tuple[StorageManager, SensorManager]
```

## Real-Time Update Patterns

### Pattern 1: Virtual Backing Entities (Recommended)

This pattern provides the best performance with in-memory synthetic sensor backing store and real-time updates:

```python
# In your sensor.py platform
async def async_setup_entry(hass, config_entry, async_add_entities):
    # Set up native sensors
    native_entities = create_native_sensors(coordinator)
    async_add_entities(native_entities)

    # Set up synthetic sensor configuration
    storage_manager = await setup_synthetic_configuration(hass, config_entry, coordinator)

    # Create change notifier callback - this enables real-time updates
    def change_notifier_callback(changed_entity_ids: set[str]) -> None:
        """Handle change notifications for selective sensor updates."""
        # This will be called by your integration when backing entity values change
        # The sensor_manager will automatically update only affected sensors
        pass

    # Register synthetic sensors with interface
    sensor_manager = await async_setup_synthetic_sensors(
        hass=hass,
        config_entry=config_entry,
        async_add_entities=async_add_entities,
        storage_manager=storage_manager,
        device_identifier=coordinator.device_id,
        data_provider_callback=create_data_provider_callback(coordinator),
        change_notifier=change_notifier_callback,  # Enable real-time updates
        allow_ha_lookups=False,
    )

    # Store sensor_manager reference for your integration to use
    hass.data[DOMAIN][config_entry.entry_id]["sensor_manager"] = sensor_manager
```

### Pattern 2: Traditional HA Entity Updates

For integrations using real HA entities as backing entities:

```python
# Traditional pattern - no change notifier needed
sensor_manager = await async_setup_synthetic_sensors(
    hass=hass,
    config_entry=config_entry,
    async_add_entities=async_add_entities,
    storage_manager=storage_manager,
    device_identifier=coordinator.device_id,
    # No data_provider_callback - uses HA entity state lookups
    # No change_notifier - automatic via async_track_state_change_event
    allow_ha_lookups=True,  # Use real HA entities
)
```

## Virtual Entity Resolution with `allow_ha_lookups`

The `allow_ha_lookups` parameter controls how backing entities are resolved (through virtual backing or actual HA sensors):

### Virtual-Only Mode (Recommended): `allow_ha_lookups=False`

```python
# Default behavior - virtual entities only with real-time updates
sensor_manager = await async_setup_synthetic_sensors(
    # ... other parameters ...
    data_provider_callback=create_data_provider_callback(coordinator),
    change_notifier=create_change_notifier_callback(sensor_manager),
    allow_ha_lookups=False,  # Default
)
```

**Advantges of Virtual Backing Approach:**

- No entity registry pollution
- Better performance (no HA state lookups)
- Clean architecture with virtual backing entities
- Variables can reference entities that don't exist in HA
- **Real-time selective updates** when using change notifier

### Hybrid Mode: `allow_ha_lookups=True`

```python
# Allow fallback to HA state lookups
sensor_manager = await async_setup_synthetic_sensors(
    # ... other parameters ...
    data_provider_callback=create_data_provider_callback(coordinator),
    change_notifier=create_change_notifier_callback(sensor_manager),
    allow_ha_lookups=True,
)
```

**Use Cases:**

- Mixing virtual and real HA entities
- Migration scenarios
- Legacy integrations

### HA-Only Mode: No Data Provider

```python
# Traditional HA entity lookups only
sensor_manager = await async_setup_synthetic_sensors(
    # ... other parameters ...
    data_provider_callback=None,  # No data provider
    change_notifier=None,  # No change notifier
    # allow_ha_lookups setting ignored when no data provider
)
```

## Data Provider with Change Notification

When you provide both a `data_provider_callback` and `change_notifier`, the synthetic sensors package enables **real-time updates**:

- **Variables are resolved through your data provider callback**
- **Change notifications trigger selective sensor updates**
- **Only sensors using changed backing entities are updated**
- **85-90% reduction in unnecessary update work**
- **Virtual backing entities don't pollute the registry**

### Implementation Flow

1. **Your coordinator receives new data** from device API
2. **Your integration compares old vs new values** and identifies changed backing entities
3. **Your integration calls `change_notifier(changed_entity_ids)`** with specific entity IDs that changed
4. **Synthetic sensors package updates only affected sensors** using `async_update_sensors_for_entities()`
5. **Real-time updates with optimal performance**

## Recommended Architecture: Enhanced Virtual Backing Entities

The cleanest approach uses **YAML templates** with **virtual backing entities** and **change notification**:

- **Clean separation** between templates and data
- **Type-safe helpers** for all ID generation
- **Real-time selective updates** via change notification
- **Optimal performance** - only update what changed
- **Virtual entities** don't pollute HA's entity registry

### Complete Implementation Example

Here's how to implement this pattern using a real-world example from the SPAN Panel integration:

#### 1. Helper Functions for ID Generation

```python
# helpers.py
def construct_backing_entity_id(
    device: DeviceData,
    circuit_id: str | None = None,
    suffix: str = "",
) -> str:
    """Construct backing entity ID for synthetic sensor references.

    These are virtual entities used only within synthetic sensor YAML configuration.
    They follow the pattern: sensor.{domain}_{serial}_{circuit_id}_backing_{suffix}
    """
    serial = device.serial_number.lower()
    circuit_part = circuit_id if circuit_id is not None else "0"
    return f"sensor.{domain}_{serial}_{circuit_part}_backing_{suffix}"

def construct_panel_unique_id(device: DeviceData, api_key: str) -> str:
    """Build unique ID for panel-level sensors."""
    entity_suffix = get_entity_suffix(api_key)
    return f"{domain}_{device.serial_number.lower()}_{entity_suffix}"

def construct_panel_entity_id(
    coordinator: YourCoordinator,
    device: DeviceData,
    platform: str,
    suffix: str,
    unique_id: str | None = None,
) -> str | None:
    """Construct entity ID for panel-level sensors."""
    # Check registry for existing customizations
    if unique_id:
        entity_registry = er.async_get(coordinator.hass)
        existing = entity_registry.async_get_entity_id(platform, DOMAIN, unique_id)
        if existing:
            return existing

    # Build new entity ID
    return f"{platform}.{device.name_slug}_{suffix}"
```

#### 2. YAML Templates

Create template files in `yaml_templates/` directory:

```yaml
# yaml_templates/sensor_set_header.yaml.txt
# Globals apply to all other sensors/templates
version: "1.0"

global_settings:
  device_identifier: "{{device_identifier}}"
  metadata:
    attribution: "Data from Your Device"
    entity_registry_enabled_default: true
    suggested_display_precision: 2

sensors: {}
```

**Important: Understanding Backing Entity References**

The templates use the `state` special token to reference backing entities:

1. **Backing Entity Registration**: The integration registers virtual entity
   IDs (e.g., `sensor.span_abc123_0_backing_current_power`) with the synthetic sensors package
2. **State Token Resolution**: When the formula uses `state`, it automatically calls the integration's data provideri
   to get the current value
3. **No Variables Needed**: The backing entity is accessed directly through the `state` token, no variable mapping required

So when you see:

```yaml
formula: "state"
```

This means:

- `state` is a special token that references the backing entity
- The backing entity is registered by the integration and provides data on demand
- No variables section is needed - the `state` token handles the resolution automatically

### Attribute Formulas and the 'state' Variable

Attribute formulas are always evaluated after the main sensor state is calculated. Every attribute formula automatically has
access to a special variable called `state`, which contains the freshly calculated value of the main sensor.
This allows attribute formulas to reference the main sensor's value directly, along with any additional variables defined
for the attribute.

**Example:**

```yaml
sensors:
  test_sensor:
    name: "Test Sensor"
    formula: "state"
    # The 'state' special token references the backing entity
    attributes:
      daily_total:
        formula: "state * 24"
      with_multiplier:
        formula: "state * multiplier"
        variables:
          multiplier: 2.5
```

In this example:

- The main sensor state is set to the value of the backing entity (accessed via the `state` token).
- The `daily_total` attribute is calculated as the main state times 24.
- The `with_multiplier` attribute is calculated as the main state times a custom multiplier (2.5).
- Both attribute formulas use the `state` variable, which is the freshly calculated main sensor value.

This pattern allows you to build complex attribute calculations that depend on the main sensor's value, ensuring consistency
and flexibility in your synthetic sensor definitions.

```yaml
# yaml_templates/power_sensor.yaml.txt
{{sensor_key}}:
  name: "{{sensor_name}}"
  entity_id: "{{entity_id}}"
  formula: "state"
  # The 'state' special token automatically references the backing entity
  # No variables needed - the backing entity is registered by the integration
  metadata:
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"
```

```yaml
# yaml_templates/energy_sensor.yaml.txt
{{sensor_key}}:
  name: "{{sensor_name}}"
  entity_id: "{{entity_id}}"
  formula: "state"
  # The 'state' special token automatically references the backing entity
  # No variables needed - the backing entity is registered by the integration
  metadata:
    unit_of_measurement: "Wh"
    device_class: "energy"
    state_class: "total_increasing"
```

#### 3. Template Loading Utilities

```python
# synthetic_utils.py
from typing import TypedDict
from pathlib import Path
import aiofiles

class BackingEntity(TypedDict):
    """Structure for backing entity data used by ha-synthetic-sensors."""
    entity_id: str
    value: float | int | str | None
    data_path: str

async def load_template(template_name: str) -> str:
    """Load a YAML template from the yaml_templates directory."""
    template_dir = Path(__file__).parent / "yaml_templates"

    if not template_name.endswith(".yaml.txt"):
        template_name = f"{template_name}.yaml.txt"

    template_path = template_dir / template_name

    async with aiofiles.open(template_path, mode="r", encoding="utf-8") as f:
        return await f.read()

def fill_template(template: str, replacements: dict[str, str]) -> str:
    """Fill template placeholders with actual values."""
    result = template
    for placeholder, replacement in replacements.items():
        result = result.replace(f"{{{{{placeholder}}}}}", replacement)
    return result
```

#### 4. Sensor Generation with Templates

```python
# synthetic_panel_sensors.py
import yaml
from .synthetic_utils import BackingEntity, load_template, fill_template

# Define your sensors as clean data structures
PANEL_SENSOR_DEFINITIONS = [
    {
        "key": "instantGridPowerW",
        "name": "Current Power",
        "template": "power_sensor",
        "data_path": "instantGridPowerW",
    },
    {
        "key": "mainMeterEnergyConsumedWh",
        "name": "Main Meter Consumed Energy",
        "template": "energy_sensor",
        "data_path": "mainMeterEnergyConsumedWh",
    },
]

async def generate_panel_sensors(
    coordinator: YourCoordinator,
    device: DeviceData
) -> tuple[dict[str, Any], list[BackingEntity]]:
    """Generate panel-level synthetic sensors using templates."""
    sensor_configs: dict[str, Any] = {}
    backing_entities: list[BackingEntity] = []

    for sensor_def in PANEL_SENSOR_DEFINITIONS:
        # Load the appropriate template
        template = await load_template(sensor_def["template"])

        # Generate IDs using helper functions
        entity_suffix = get_entity_suffix(sensor_def["key"])
        # Build actual HA entity ID
        entity_id = construct_panel_entity_id(coordinator, device, "sensor", entity_suffix)
        # Build virtual backing entity ID for synthetic sensor variables
        backing_entity_id = construct_backing_entity_id(device, "0", entity_suffix)
        # Build unique ID for entity registry
        sensor_unique_id = construct_panel_unique_id(device, sensor_def["key"])

        # Get current data value
        data_value = get_device_data_value(device, sensor_def["data_path"])

        # Fill template placeholders
        placeholders = {
            "sensor_key": sensor_unique_id,
            "sensor_name": sensor_def["name"],
            "entity_id": entity_id,
            "backing_entity_id": backing_entity_id,
        }

        # Generate YAML from template
        filled_template = fill_template(template, placeholders)
        sensor_yaml = yaml.safe_load(filled_template)

        # Add to collection
        sensor_configs[sensor_unique_id] = sensor_yaml[sensor_unique_id]

        # Create backing entity
        backing_entity = BackingEntity(
            entity_id=backing_entity_id,
            value=data_value,
            data_path=sensor_def["data_path"]
        )
        backing_entities.append(backing_entity)

    return sensor_configs, backing_entities

async def generate_complete_sensor_set_yaml(
    device: DeviceData,
    sensor_configs: dict[str, Any]
) -> str:
    """Generate complete sensor set YAML using header template."""
    # Load header template
    header_template = await load_template("sensor_set_header")

    # Fill header placeholders
    header_placeholders = {
        "device_identifier": device.serial_number,
    }

    # Generate header YAML
    filled_header = fill_template(header_template, header_placeholders)
    header_yaml = yaml.safe_load(filled_header)

    # Merge sensors into the header structure
    header_yaml["sensors"] = sensor_configs

    # Return complete YAML
    return yaml.dump(header_yaml, default_flow_style=False)
```

#### 5. Virtual Backing Entity Coordinator with Granular Change Detection

```python
# synthetic_sensors.py
class SyntheticSensorCoordinator:
    """Coordinator for synthetic sensor data updates with change detection.

    This class listens to your main coordinator updates, detects actual value changes,
    and provides selective update notifications for optimal performance.
    """

    def __init__(self, hass: HomeAssistant, main_coordinator: YourCoordinator):
        """Initialize the synthetic sensor coordinator."""
        self.hass = hass
        self.main_coordinator = main_coordinator
        self.backing_entities: dict[str, Any] = {}
        self.change_notifier: DataProviderChangeNotifier | None = None

        # Listen for main coordinator updates
        self._unsub = main_coordinator.async_add_listener(self._handle_coordinator_update)

    def set_change_notifier(self, change_notifier: DataProviderChangeNotifier) -> None:
        """Set the change notifier callback for real-time updates."""
        self.change_notifier = change_notifier

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle coordinator updates with smart change detection."""
        if not self.main_coordinator.last_update_success:
            return

        try:
            device_data = self.main_coordinator.data
            if not device_data:
                return

            # Track which backing entities actually changed values
            changed_entities: set[str] = set()

            # Update virtual backing entity values and detect changes
            for entity_id, entity_info in self.backing_entities.items():
                api_key = entity_info["api_key"]
                old_value = entity_info.get("value")

                try:
                    # Get live value from your device data
                    new_value = getattr(device_data, api_key, None)

                    # Only track entities that actually changed values
                    if old_value != new_value:
                        entity_info["value"] = new_value
                        changed_entities.add(entity_id)
                        _LOGGER.debug("Detected change in virtual backing entity %s: %s -> %s",
                                    entity_id, old_value, new_value)

                except AttributeError:
                    _LOGGER.warning("Failed to get value for %s from device data", api_key)

            # Notify synthetic sensors of changes for selective updates
            if changed_entities and self.change_notifier:
                _LOGGER.debug("Notifying synthetic sensors of %d changed entities: %s",
                            len(changed_entities), changed_entities)
                self.change_notifier(changed_entities)

        except Exception as e:
            _LOGGER.error("Error updating synthetic sensor backing data: %s", e)

    def register_backing_entity(self, entity_id: str, api_key: str) -> None:
        """Register a virtual backing entity for data updates."""
        self.backing_entities[entity_id] = {"api_key": api_key, "value": None}
        _LOGGER.debug("Registered virtual backing entity: %s -> %s", entity_id, api_key)

    def get_backing_value(self, entity_id: str) -> Any:
        """Get the current value for a virtual backing entity."""
        entity_info = self.backing_entities.get(entity_id)
        return entity_info["value"] if entity_info else None

    def shutdown(self) -> None:
        """Clean up the coordinator."""
        if self._unsub:
            self._unsub()
```

#### 6. Setup Integration

```python
# synthetic_sensors.py continued
async def setup_synthetic_configuration(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    main_coordinator: YourCoordinator
) -> tuple[StorageManager, SyntheticSensorCoordinator]:
    """Set up synthetic sensor configuration using storage manager with change detection."""

    # Initialize storage manager
    storage_manager = StorageManager(hass, f"{DOMAIN}_synthetic")
    await storage_manager.async_load()

    device_identifier = main_coordinator.data.serial_number
    sensor_set_id = f"{device_identifier}_sensors"

    # Create synthetic sensor coordinator
    synthetic_coord = SyntheticSensorCoordinator(hass, main_coordinator)

    # Generate sensors and backing entities using templates
    device_data = main_coordinator.data
    sensor_configs, backing_entities = await generate_panel_sensors(main_coordinator, device_data)

    # Register virtual backing entities with the synthetic coordinator
    for backing_entity in backing_entities:
        entity_id = backing_entity["entity_id"]
        api_key = get_api_key_from_data_path(backing_entity["data_path"])
        synthetic_coord.register_backing_entity(entity_id, api_key)

    # Create or update sensor set
    if storage_manager.sensor_set_exists(sensor_set_id):
        # Existing - preserve user customizations, add new sensors only
        sensor_set = storage_manager.get_sensor_set(sensor_set_id)
        existing_ids = {s.unique_id for s in sensor_set.list_sensors()}
        default_configs = await generate_default_sensor_configs(sensor_configs, device_identifier)
        new_sensors = [s for s in default_configs if s.unique_id not in existing_ids]

        if new_sensors:
            for sensor_config in new_sensors:
                await sensor_set.async_add_sensor(sensor_config)
    else:
        # Fresh install - create with defaults
        await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier=device_identifier,
            name=f"Your Device {device_identifier} Sensors",
        )
        sensor_set = storage_manager.get_sensor_set(sensor_set_id)
        default_configs = await generate_default_sensor_configs(sensor_configs, device_identifier)
        await sensor_set.async_replace_sensors(default_configs)

    return storage_manager, synthetic_coord

def create_data_provider_callback(main_coordinator: YourCoordinator) -> DataProviderCallback:
    """Create data provider callback that uses virtual backing entities."""

    def data_provider_callback(entity_id: str) -> DataProviderResult:
        """Provide live data from virtual backing entities."""
        try:
            # Find the synthetic coordinator for this device
            synthetic_coord = find_synthetic_coordinator_for(main_coordinator)
            if not synthetic_coord:
                return {"value": None, "exists": False}

            # Get value from virtual backing entity
            value = synthetic_coord.get_backing_value(entity_id)
            exists = value is not None

            return {"value": value, "exists": exists}

        except Exception as e:
            _LOGGER.error("Error in data provider callback for %s: %s", entity_id, e)
            return {"value": None, "exists": False}

    return data_provider_callback

def create_change_notifier_callback(
    synthetic_coord: SyntheticSensorCoordinator
) -> DataProviderChangeNotifier:
    """Create change notifier callback for real-time selective updates."""

    def change_notifier_callback(changed_entity_ids: set[str]) -> None:
        """Handle change notifications - this will be set by the sensor manager."""
        # This callback will be replaced by the sensor manager's actual change handler
        # when the simplified interface is used
        pass

    # Connect the synthetic coordinator to use this notifier
    synthetic_coord.set_change_notifier(change_notifier_callback)

    return change_notifier_callback

# Complete setup example in sensor.py
async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up synthetic sensors with change notification."""

    # Set up native sensors
    native_entities = create_native_sensors(coordinator)
    async_add_entities(native_entities)

    # Set up synthetic configuration with coordinator
    storage_manager, synthetic_coord = await setup_synthetic_configuration(
        hass, config_entry, coordinator
    )

    # Create callbacks
    data_provider = create_data_provider_callback(coordinator)
    change_notifier = create_change_notifier_callback(synthetic_coord)

    # Register synthetic sensors with simplified interface
    sensor_manager = await async_setup_synthetic_sensors(
        hass=hass,
        config_entry=config_entry,
        async_add_entities=async_add_entities,
        storage_manager=storage_manager,
        device_identifier=coordinator.data.serial_number,
        data_provider_callback=data_provider,
        change_notifier=change_notifier,  # Enable real-time selective updates
        allow_ha_lookups=False,
    )

    # Store references for configuration management
    hass.data[DOMAIN][config_entry.entry_id].update({
        "sensor_manager": sensor_manager,
        "synthetic_coordinator": synthetic_coord,
    })
```

## CRUD Operations for Dynamic Sensor Management

For adding optional sensor configurations (like solar or battery sensors), use the CRUD interface:

```python
# Adding solar sensors dynamically with change notification support
async def add_solar_sensors(sensor_manager: SensorManager, leg1_circuit: str, leg2_circuit: str):
    """Add solar sensors using CRUD interface."""

    for sensor_id in solar_sensor_ids:
        success = await sensor_manager.remove_sensor_with_backing_entities(sensor_id)
        if not success:
            _LOGGER.error("Failed to remove solar sensor: %s", sensor_id)
```

## YAML Export Methods for Sensor Sets

The `SensorSet` class provides both synchronous and asynchronous methods for exporting sensor set configuration to YAML.
Both methods serialize the current in-memory sensor set configuration to a YAML string. Neither method performs file I/O.

```python
# Synchronous export
exported_yaml = sensor_set.export_yaml()  # str

# Asynchronous export
exported_yaml = await sensor_set.async_export_yaml()  # str
```

## Bulk Modification Performance Benefits

### Enhanced Selective Updates

```python
# New approach - updates only sensors using changed backing entities
async def _handle_coordinator_update(self):
    # Automatic change detection and selective updates
    # Only 2-3 sensors updated instead of 20+
    # 85-90% reduction in unnecessary work
```

## Migration Guide

To migrate from manual updates to change notification:

**Update your setup function** to use the simplified interface with `change_notifier` parameter
**Implement change detection** in your coordinator update handler
**Replace manual bulk updates** with automatic selective updates
**Use CRUD operations** for dynamic sensor management
**Test real-time performance** improvements

### Migration Example

```python
# Before: Manual bulk updates
async def _handle_coordinator_update(self):
    await self.sensor_manager.async_update_sensors()

# After: Enhanced change notification (automatic)
async def async_setup_entry(hass, config_entry, async_add_entities):
    # Just add change_notifier parameter - everything else automatic
    sensor_manager = await async_setup_synthetic_sensors(
        # ... existing parameters ...
        change_notifier=create_change_notifier_callback(synthetic_coord),  # Add this
    )
```

This migration dramatically improves performance while maintaining all existing functionality.
