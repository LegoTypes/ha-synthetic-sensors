# Synthetic Sensors Integration Guide

This guide demonstrates how to integrate the `ha-synthetic-sensors` library into your Home Assistant custom integration for
creating dynamic, formula-based sensors.

## Overview: How Synthetic Sensors Work

Synthetic sensors are **wrapper sensors** that extend other sensors with formula-based calculations. They provide a new state
value by applying mathematical formulas to to other entities, allowing you to:

- **Extend sensor capabilities** with calculated attributes
- **Transform sensor values** using mathematical formulations
- **Combine multiple sensors** into derived metrics
- **Add computed states** without modifying original sensors
- **Add computed attributes** that evaluate base on the main sensor state or other entities
- **Use custom comparison logic** for domain-specific data types (energy, versions, IP addresses, etc.)

### Data Sources for Synthetic Sensors

Synthetic sensors calculate their state using formulas that reference other sensor data. **The formula determines the
synthetic sensor's final state value** - there is no requirement for a single "backing entity." Instead, synthetic sensors
can:

- **Use a dedicated state backing entity** (referenced via `state` token) as the primary data source
- **Combine multiple existing sensors or attriubutes** using their entity IDs in formulas
- **Perform pure calculations** across any combination of sensor references

The data sources for the evaluated formulas can be:

**A) Virtual Backing Entity (Integration-Managed)**

- Custom data structure in your integration's memory
- Not registered in HA's entity registry
- Updated by your integration's coordinator
- Referenced via `state` token in formulas when sensor has a dedicated backing entity

**B) Native HA Entity References (Integration-Provided)**

- Real HA sensors created by your integration
- Registered in HA's entity registry
- Referenced by entity ID in synthetic sensor formulas
- Enables extending or combining your integration's existing sensors

**C) External HA Entity References (Cross-Integration)**

- Sensors from other integrations or manual configuration
- Referenced by entity ID in synthetic sensor formulas
- Automatically tracked via HA state change events
- Enables cross-integration calculations and combinations

### Process Flow for Each Pattern

#### Pattern A: Virtual Entity Extension (Device Integrations)

```text
Your Integration Data → Virtual Backing Entity → Synthetic Sensor Extension
        ↓                        ↓                           ↓
   Device API Data        coordinator.register()     Formula calculates new state
   coordinator.update()   virtual_entity.value      from virtual entity value
   notify_changes()       (not in HA registry)      (appears in HA as sensor)
```

**Steps:**

1. **Set up virtual backing entities** in your coordinator's memory
2. **Register entities** with synthetic sensor package via mapping
3. **Update virtual values** when your device data changes
4. **Notify changes** to trigger selective synthetic sensor updates
5. **Synthetic sensors calculate** new states from virtual entity values

#### Pattern B: Native HA Entity Extension (Integration Sensors)

```text
Your Integration → Native HA Sensor → Synthetic Sensor Extension
        ↓                ↓                      ↓
   Create real sensor   HA entity lifecycle    Formula extends existing
   via async_add_entities   state updates      sensor with new calculations
```

**Steps:**

1. **Create native HA sensors** via `async_add_entities`
2. **Set up synthetic sensors** to reference native sensor entity IDs
3. **Update native sensors** through normal HA mechanisms
4. **Synthetic sensors automatically update** via HA state change tracking
5. **Extended sensors provide** calculated values based on native sensor states

#### Pattern C: External HA Entity Extension (Cross-Integration)

```text
Other Integration → HA Entity → Synthetic Sensor Extension
        ↓              ↓              ↓
   External sensor    HA state      Formula combines/transforms
   updates normally   changes       external entity values
```

**Steps:**

1. **Identify external HA entities** you want to extend or combine
2. **Reference entity IDs** directly in synthetic sensor YAML variables
3. **Set up synthetic sensors** with `allow_ha_lookups=True`
4. **External entities update** independently via their own integrations
5. **Synthetic sensors automatically recalculate** when referenced entities change

### Sythetic Benefits

- **No modification** of original sensors or integrations required
- **Dynamic formulas** can be updated without code changes (via YAML)
- **Selective updates** - only affected sensors recalculate when dependencies change
- **Clean architecture** - separates data provision from sensor presentation
- **Cross-integration** capabilities for combining data from multiple sources

## Quick Start - Recommended Pattern

For most integrations, use this simplified pattern with **one function call**:

```python
# In your sensor.py platform
from ha_synthetic_sensors import async_setup_synthetic_sensors

async def async_setup_entry(hass, config_entry, async_add_entities):
    # Create your native sensors first
    native_entities = create_native_sensors(coordinator)
    async_add_entities(native_entities)

    # Register custom comparison handlers (optional)
    from ha_synthetic_sensors.comparison_handlers import register_user_comparison_handler
    energy_handler = EnergyComparisonHandler()  # Your custom handler
    register_user_comparison_handler(energy_handler)

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

This approach handles everything automatically using storage-based configuration and supports custom comparison logic for
domain-specific data types.

## Data Provider Interface with Real-Time Updates

The library supports **change notification** for real-time synthetic sensor updates when using virtual backing entities. This
approach provides optimal performance by only updating sensors whose underlying data has actually changed.

### Data Provider Components

**Data Provider Callback**: Returns current values for virtual backing entities **Change Notifier Callback**: Receives
notifications when specific backing entities change **Selective Updates**: Only sensors using changed backing entities are
updated

### Type Definitions

```python
from typing import Callable
from ha_synthetic_sensors import DataProviderCallback, DataProviderChangeNotifier

# Data provider returns current values
DataProviderCallback = Callable[[str], DataProviderResult]

# Change notifier receives set of changed backing entity IDs
DataProviderChangeNotifier = Callable[[set[str]], None]
```

## User-Defined Comparison Handlers

The synthetic sensors library includes an **extensible comparison handler architecture** that allows users to define custom
comparison logic for specialized data types. This enables advanced pattern matching in collection functions and condition
evaluation.

For comprehensive documentation on creating and using custom comparison handlers, see the dedicated guide:

**[User-Defined Comparison Handlers](User_Defined_Comparison_Handlers.md)**

This guide covers:

- **Handler Architecture**: Understanding the extensible comparison system
- **Creating Custom Handlers**: Step-by-step implementation guide
- **Priority System**: Handler selection and precedence rules
- **Advanced Examples**: IP address, version string, and energy handlers
- **Best Practices**: Design patterns and testing strategies
- **Integration**: Using handlers with collection functions and patterns

**Quick Start:**

```python
from ha_synthetic_sensors.comparison_handlers import register_user_comparison_handler

# Register your custom handler
energy_handler = EnergyComparisonHandler()
register_user_comparison_handler(energy_handler)

# Use in collection patterns
formula: count("attribute:power_consumption>=1kW")  # Uses energy handler
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
    sensor_to_backing_mapping: dict[str, str] | None = None,    # Synthetic Sensor Key -> Backing entity_id
    allow_ha_lookups: bool = False,
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
    change_notifier: DataProviderChangeNotifier | None = None,
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
    sensor_to_backing_mapping: dict[str, str] | None = None,   # Synthetic Sensor Key -> Backing entity_id
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

## Input Validation

The library performs strict validation on key parameters to ensure data integrity and prevent runtime errors:

### Sensor-to-Backing Mapping Validation

The `sensor_to_backing_mapping` parameter is validated to ensure:

- **No `None` values**: Neither keys nor values can be `None`
- **Valid strings**: All keys and values must be non-empty strings (no empty strings or whitespace-only strings)
- **Proper types**: All entries must be strings (not integers, booleans, etc.)
- **HA Compliance**: Entity ID's are NOT validated as HA compliant because in-memory backing may be any valid string
- **Non-empty mapping**: The mapping cannot be empty (at least one entry is required for state token resolution)

**Example of valid mapping:**

```python
sensor_to_backing_mapping = {
    "span_nj-2316-005k6_0dad2f16cd514812ae1807b0457d473e_power": "sensor.span_nj-2316-005k6_0dad2f16cd514812ae1807b0457d473e_backing_power",
    "span_nj-2316-005k6_0dad2f16cd514812ae1807b0457d473e_energy_consumed": "sensor.span_nj-2316-005k6_0dad2f16cd514812ae1807b0457d473e_backing_energy_consumed",
}
```

**Examples that will raise `ValueError`:**

```python
# Invalid - Empty mapping (breaks state token resolution)
{}

# Invalid - None values
{"sensor_key": None}
{None: "sensor.backing_entity"}

# Invalid - Empty strings
{"": "sensor.backing_entity"}
{"sensor_key": ""}
async def setup_with_yaml_import(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    yaml_content: str
) -> StorageManager:
    """Set up sensor set by importing YAML content."""

    storage_manager = StorageManager(hass, f"{DOMAIN}_synthetic")
    await storage_manager.async_load()

    device_identifier = "your_device_id"
    sensor_set_id = f"{device_identifier}_sensors"

    # Create sensor set first
    await storage_manager.async_create_sensor_set(
        sensor_set_id=sensor_set_id,
        device_identifier=device_identifier,
        name="My Device Sensors",
    )

    # Import YAML content
    sensor_set = storage_manager.get_sensor_set(sensor_set_id)
    await sensor_set.async_import_yaml(yaml_content)

    return storage_manager
# Invalid - Whitespace-only strings
{"   ": "sensor.backing_entity"}
{"sensor_key": "   "}

# Invalid - Wrong types
{123: "sensor.backing_entity"}
{"sensor_key": 456}
```

### Entity IDs Validation

The `backing_entity_ids` parameter (when used directly) is validated to ensure:

- **No `None` values**: No entity ID can be `None`
- **Valid strings**: All entity IDs must be non-empty strings
- **Proper types**: All entity IDs must be strings

**Example of valid entity IDs:**

```python
backing_entity_ids = {
    "sensor.span_nj-2316-005k6_0dad2f16cd514812ae1807b0457d473e_backing_power",
    "sensor.span_nj-2316-005k6_0dad2f16cd514812ae1807b0457d473e_backing_energy_consumed",
}
```

**Examples that will raise `SyntheticSensorsConfigError`:**

```python
# Invalid - Direct registration with empty set in virtual-only mode
register_data_provider_entities(set(), allow_ha_lookups=False)

# Invalid - Direct registration with empty set (even with HA lookups)
register_data_provider_entities(set(), allow_ha_lookups=True)

# Invalid - None values in entity set
{None, "sensor.backing_entity"}

# Invalid - Empty strings in entity set
{"", "sensor.backing_entity"}

# Invalid - Whitespace-only strings in entity set
{"   ", "sensor.backing_entity"}

# Invalid - Wrong types in entity set
{123, "sensor.backing_entity"}
```

**Valid usage patterns:**

```python
# Valid - Populated entity set
backing_entity_ids = {"sensor.virtual_power", "sensor.virtual_energy"}
register_data_provider_entities(backing_entity_ids, allow_ha_lookups=False)

# Valid - HA-only mode (no direct registration needed)
# Use convenience methods with sensor_to_backing_mapping=None and allow_ha_lookups=True

# Valid - Empty mapping in convenience method with HA lookups
sensor_to_backing_mapping = {}  # Empty dict is allowed in convenience methods
async_setup_synthetic_sensors(..., sensor_to_backing_mapping=sensor_to_backing_mapping, allow_ha_lookups=True)
```

### API Design Logic

The library distinguishes between **convenience methods** and **direct API calls** to provide appropriate validation:

#### Convenience Methods (Lenient)

```python
# Empty mapping in convenience methods = HA-only mode (when allow_ha_lookups=True)
async_setup_synthetic_sensors(
    sensor_to_backing_mapping={},  # Empty dict is OK
    allow_ha_lookups=True,  # Will use HA entities only
)

# No mapping in convenience methods = valid for pure calculation sensors
async_setup_synthetic_sensors(
    sensor_to_backing_mapping=None,  # No mapping is OK
    allow_ha_lookups=False,  # Sensors cannot use 'state' token
)

```

#### Direct API Calls (Strict)

```python
# Explicit empty set is always an error - indicates confusion about intent
sensor_manager.register_data_provider_entities(set())  # ERROR: Empty set is explicit mistake


# Use None or omit parameter for HA-only mode instead

# (Don't call register_data_provider_entities at all for HA-only mode)
```

#### Validation Context

- **`allow_ha_lookups=False`**: Virtual entities required, empty/None backing entities is error
- **`allow_ha_lookups=True`**: HA fallback allowed, but explicit empty set still error (use None instead)

### Error Handling

When validation fails, the library raises a `SyntheticSensorsConfigError` with detailed information about the issue:

```python
try:
    sensor_manager = await async_setup_synthetic_sensors(
        # ... other parameters ...
        sensor_to_backing_mapping=invalid_mapping,
        allow_ha_lookups=False,
    )
except SyntheticSensorsConfigError as e:
    # Error message will explain the validation issue
    print(f"Configuration error: {e}")
    # Example: "Empty sensor-to-backing mapping in virtual-only mode (allow_ha_lookups=False)"

try:
    sensor_manager.register_data_provider_entities(set(), allow_ha_lookups=False)
except SyntheticSensorsConfigError as e:
    print(f"Direct API error: {e}")
    # Example: "No backing entities provided in virtual-only mode (allow_ha_lookups=False).
    # Either provide backing entities or enable HA lookups."
```

## Real-Time Update Patterns

The update pattern depends on your backing entity source:

### Virtual Backing Entities (Custom Data Provider)

When your integration provides its own data via virtual backing entities:

```python
# Pattern 1 setup - Virtual backing entities with change notification
sensor_manager = await async_setup_synthetic_sensors(
    hass=hass,
    config_entry=config_entry,
    async_add_entities=async_add_entities,
    storage_manager=storage_manager,
    device_identifier=coordinator.device_id,
    data_provider_callback=create_data_provider_callback(coordinator),
    change_notifier=change_notifier_callback,  # Enable real-time selective updates
    sensor_to_backing_mapping=sensor_to_backing_mapping,  # Register your virtual entities
    allow_ha_lookups=False,  # Virtual entities only
)
```

### HA Entity Backing (Cross-Integration References)

When your YAML references existing HA entities from other integrations:

```python
# Pattern 2 setup - HA entity references with automatic tracking
sensor_manager = await async_setup_synthetic_sensors(
    hass=hass,
    config_entry=config_entry,
    async_add_entities=async_add_entities,
    storage_manager=storage_manager,
    device_identifier=coordinator.device_id,
    # No data_provider_callback - uses HA entity state lookups
    # No change_notifier - automatic via async_track_state_change_event
    # No sensor_to_backing_mapping - entities resolved from YAML variable references
    allow_ha_lookups=True,  # Use real HA entities
)
```

### Hybrid Backing (Mixed Virtual and HA Entities)

When your YAML uses both virtual entities and existing HA entities:

```python
# Pattern 3 setup - Hybrid virtual and HA entity backing
sensor_manager = await async_setup_synthetic_sensors(
    hass=hass,
    config_entry=config_entry,
    async_add_entities=async_add_entities,
    storage_manager=storage_manager,
    device_identifier=coordinator.device_id,
    data_provider_callback=create_data_provider_callback(coordinator),  # For virtual entities
    change_notifier=change_notifier_callback,  # For virtual entity updates
    sensor_to_backing_mapping=virtual_backing_mapping,  # Only virtual entities registered
    allow_ha_lookups=True,  # Allow fallback to HA entity lookups
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

When you provide both a `data_provider_callback` and `change_notifier`, the synthetic sensors package enables **real-time
updates**:

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

## YAML-Based Sensor Set Patterns

When working with YAML-based sensor definitions, choose the appropriate pattern based on your backing entity needs:

### Pattern 1: Custom Virtual Backing Entities (Recommended for Device Integrations)

**Use when:** Your integration provides its own data and needs virtual backing entities that don't exist in HA.

**Benefits:**

- **Clean separation** between templates and data
- **Type-safe helpers** for all ID generation
- **Real-time selective updates** via change notification
- **Optimal performance** - only update what changed
- **Virtual entities** don't pollute HA's entity registry
- **Custom data provider** controls all backing entity values

**Backing Entity Registration Required:** Yes - you must register virtual backing entities with your coordinator.

```python
# Register virtual backing entities with your coordinator
for sensor_unique_id, backing_entity_id in sensor_to_backing_mapping.items():
    api_key = get_api_key_for_sensor(sensor_unique_id)
    synthetic_coord.register_backing_entity(backing_entity_id, api_key)
```

### Pattern 2: Reference Existing HA Entities (For Cross-Integration Formulas)

**Use when:** Your YAML references existing HA entities from other integrations or manual entities.

**Benefits:**

- **Simple setup** - no backing entity registration needed
- **Automatic HA state tracking** via `async_track_state_change_event`
- **Cross-integration formulas** can reference any HA entity
- **Mixed mode support** - can combine with virtual entities

**Backing Entity Registration Required:** No - HA entities are automatically resolved.

```python
# YAML can directly reference existing HA entities
sensors:
  combined_power:
    formula: "solar_power + battery_power"
    # sensor.solar_power and sensor.battery_power are existing HA entities
    # 'state' references this sensor's backing entity (if any)
```

### Pattern 3: Hybrid Approach (Mixed Virtual and HA Entities)

**Use when:** You need both custom virtual entities AND references to existing HA entities.

**Benefits:**

- **Maximum flexibility** - combine custom data with HA entities
- **Selective registration** - only register virtual entities you provide
- **Fallback support** - missing virtual entities can fall back to HA lookups

**Backing Entity Registration Required:** Partial - only for virtual entities you provide.

```python
# Register only your virtual backing entities
for sensor_unique_id, backing_entity_id in sensor_to_backing_mapping.items():
    if is_virtual_entity(backing_entity_id):  # Your logic to identify virtual entities
        api_key = get_api_key_for_sensor(sensor_unique_id)
        synthetic_coord.register_backing_entity(backing_entity_id, api_key)
# HA entities are automatically resolved via allow_ha_lookups=True
```

## Pattern Selection Guide

| Integration Type    | Backing Entity Source | Pattern   | `allow_ha_lookups` | Registration Required  |
| ------------------- | --------------------- | --------- | ------------------ | ---------------------- |
| Device Integration  | Custom device data    | Pattern 1 | `False`            | Yes - Virtual entities |
| Cross-Integration   | Existing HA entities  | Pattern 2 | `True`             | No                     |
| Utility Integration | Mix of both           | Pattern 3 | `True`             | Partial - Virtual only |

### Complete Implementation Example - Pattern 1 (Custom Virtual Backing)

Here's how to implement Pattern 1 using a real-world example from the SPAN Panel integration:

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

**Important: Understanding YAML Entity References and Backing Entities**

The backing entity resolution depends on your pattern choice and how entities are referenced in YAML:

#### Pattern 1: Virtual Backing with `state` Token + Mapping

For custom virtual backing entities, use the `state` special token with sensor-to-backing mapping:

```yaml
# In your YAML template
formula: "state" # References the backing entity for this sensor
```

**Resolution Process:**

1. **Sensor-to-Backing Mapping**: Integration provides mapping from sensor keys to virtual backing entity IDs
2. **State Token Resolution**: When formula uses `state`, package looks up sensor key to find backing entity ID
3. **Data Provider Callback**: Virtual backing entity ID is passed to your data provider callback

**Example Mapping:**

```python
sensor_to_backing_mapping = {
    "span_power_sensor": "sensor.span_virtual_backing_power",
    "span_energy_sensor": "sensor.span_virtual_backing_energy",
}
# Virtual entities registered with your coordinator, not HA
```

#### Pattern 2: Direct HA Entity References in YAML

For existing HA entities, reference them directly in YAML variables:

```yaml
# In your YAML configuration
sensors:
  combined_power:
    formula: "solar_power + battery_power"
    variables:
      solar_power: "sensor.solar_inverter_power" # Real HA entity
      battery_power: "sensor.battery_system_power" # Real HA entity
```

**Resolution Process:**

1. **Direct Entity References**: YAML variables contain actual HA entity IDs
2. **Automatic HA Lookup**: Package resolves entities via HA state lookups
3. **No Registration Required**: HA entities are automatically tracked

#### Pattern 3: Hybrid - Mixed References

Combine both approaches in the same YAML:

```yaml
sensors:
  total_power:
    formula: "state + external_solar" # state = virtual, external_solar = HA entity
    variables:
      external_solar: "sensor.neighbor_solar_power" # Real HA entity
# 'state' resolved via sensor_to_backing_mapping to virtual entity
# 'external_solar' resolved directly to HA entity
```

**Key Distinctions:**

| Reference Type     | YAML Syntax                           | Registration Required | Data Source        |
| ------------------ | ------------------------------------- | --------------------- | ------------------ |
| Virtual Backing    | `state` token                         | Yes - via mapping     | Your data provider |
| HA Entity Variable | `variable_name: "sensor.real_entity"` | No                    | HA state lookups   |
| Global HA Variable | From global_settings variables        | No                    | HA state lookups   |

### Attribute Formulas and the 'state' Variable

Attribute formulas are always evaluated after the main sensor state is calculated. Every attribute formula automatically has
access to a special variable called `state`, which contains the freshly calculated value of the main sensor. This allows
attribute formulas to reference the main sensor's value directly, along with any additional variables defined for the
attribute.

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
{ { sensor_key } }:
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
{ { sensor_key } }:
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
) -> tuple[dict[str, Any], dict[str, str]]:
    """Generate panel-level synthetic sensors using templates."""
    sensor_configs: dict[str, Any] = {}
    sensor_to_backing_mapping: dict[str, str] = {}

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

        # Create sensor-to-backing mapping
        sensor_to_backing_mapping[sensor_unique_id] = backing_entity_id

    return sensor_configs, sensor_to_backing_mapping

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
    sensor_configs, sensor_to_backing_mapping = await generate_panel_sensors(main_coordinator, device_data)

    # Register virtual backing entities with the synthetic coordinator
    for sensor_unique_id, backing_entity_id in sensor_to_backing_mapping.items():
        # Find the data path for this sensor
        sensor_def = next((s for s in PANEL_SENSOR_DEFINITIONS if get_entity_suffix(s["key"]) in sensor_unique_id), None)
        if sensor_def:
            api_key = sensor_def["data_path"]
            synthetic_coord.register_backing_entity(backing_entity_id, api_key)

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

    # Generate sensor configurations and mapping
    device_data = coordinator.data
    sensor_configs, sensor_to_backing_mapping = await generate_panel_sensors(coordinator, device_data)

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
        sensor_to_backing_mapping=sensor_to_backing_mapping,  # Provide mapping
        allow_ha_lookups=False,
    )

    # Store references for configuration management
    hass.data[DOMAIN][config_entry.entry_id].update({
        "sensor_manager": sensor_manager,
        "synthetic_coordinator": synthetic_coord,
    })
```
