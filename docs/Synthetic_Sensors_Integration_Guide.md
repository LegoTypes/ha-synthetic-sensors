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
    await async_setup_synthetic_sensors(
        hass=hass,
        config_entry=config_entry,
        async_add_entities=async_add_entities,
        data_provider_callback=create_data_provider_callback(coordinator),
        device_identifier=coordinator.device_id,
    )
```

This approach handles everything automatically using storage-based configuration.

## Recommended Architecture: YAML Templates with Virtual Backing Entities

The cleanest approach for creating synthetic sensors uses **YAML templates** with **virtual backing entities**. This pattern provides:

- **Clean separation** between templates and data
- **Type-safe helpers** for all ID generation
- **No string parsing** or manual YAML construction
- **Maintainable** template-driven configuration

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
version: "1.0"

global_settings:
  device_identifier: "{{device_identifier}}"
  metadata:
    attribution: "Data from Your Device"
    entity_registry_enabled_default: true
    suggested_display_precision: 2

sensors: {}
```

```yaml
# yaml_templates/power_sensor.yaml.txt
{{sensor_key}}:
  name: "{{sensor_name}}"
  entity_id: "{{entity_id}}"
  formula: "source_value"
  variables:
    source_value: "{{backing_entity_id}}"
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
  formula: "source_value"
  variables:
    source_value: "{{backing_entity_id}}"
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
        entity_id = construct_panel_entity_id(coordinator, device, "sensor", entity_suffix)
        backing_entity_id = construct_backing_entity_id(device, "0", entity_suffix)
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

#### 5. Virtual Backing Entity Coordinator

**This is the missing piece** - how virtual backing entities get populated with live data:

```python
# synthetic_sensors.py
class SyntheticSensorCoordinator:
    """Coordinator for synthetic sensor data updates.

    This class listens to your main coordinator updates and ensures
    virtual backing entities are populated with live data.
    """

    def __init__(self, hass: HomeAssistant, main_coordinator: YourCoordinator):
        """Initialize the synthetic sensor coordinator."""
        self.hass = hass
        self.main_coordinator = main_coordinator
        self.backing_entities: dict[str, Any] = {}

        # Listen for main coordinator updates
        self._unsub = main_coordinator.async_add_listener(self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle coordinator updates by refreshing virtual backing data."""
        if not self.main_coordinator.last_update_success:
            return

        try:
            device_data = self.main_coordinator.data
            if not device_data:
                return

            # Update ALL virtual backing entity values with live data
            for entity_id, entity_info in self.backing_entities.items():
                api_key = entity_info["api_key"]
                try:
                    # Get live value from your device data
                    value = getattr(device_data, api_key, None)
                    entity_info["value"] = value
                    _LOGGER.debug("Updated virtual backing entity %s: %s = %s",
                                entity_id, api_key, value)
                except AttributeError:
                    _LOGGER.warning("Failed to get value for %s from device data", api_key)

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
) -> StorageManager:
    """Set up synthetic sensor configuration using storage manager."""

    # Initialize storage manager
    storage_manager = StorageManager(hass, f"{DOMAIN}_synthetic")
    await storage_manager.async_load()

    device_identifier = main_coordinator.data.serial_number
    sensor_set_id = f"{device_identifier}_sensors"

    # Create synthetic sensor coordinator for virtual backing entities
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

    return storage_manager

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
```

## Benefits of This Approach

### 1. **Clean Architecture**

- Templates handle YAML structure
- Helpers handle all ID generation
- No string parsing or manual construction

### 2. **Virtual Backing Entities**

- No entity registry pollution
- Better memory performance
- Coordinator automatically updates all virtual entities

### 3. **Type Safety**

- `BackingEntity` TypedDict ensures consistency
- Helper functions prevent ID conflicts
- Template placeholders are validated

### 4. **Maintainability**

- Adding new sensors requires only template + definition
- YAML structure changes only require template updates
- All ID generation logic is centralized in helpers

This pattern scales well and provides the cleanest integration with the synthetic sensors package.
