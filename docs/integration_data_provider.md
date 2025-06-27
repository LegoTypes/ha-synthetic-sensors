# Integration Data Provider Support

The synthetic sensors evaluator now supports a dual data source approach where sensor data can come from both
Home Assistant entities and directly from parent integrations through callbacks.

## Overview

This feature allows parent integrations to provide sensor data directly to the synthetic sensors evaluator
without requiring the data to be available as Home Assistant entities. This is useful when:

1. The parent integration has raw data that hasn't been processed into HA entities yet
2. You want to avoid creating intermediate entities just for synthetic sensor calculations
3. You need better performance by bypassing HA state lookups for certain entities

## How It Works - Integration Authority Model

The integration proactively registers which entities it can provide data for, establishing **authoritative entity ownership**:

1. **Entity Registration**: Integration registers a set of entity IDs it can provide data for
2. **Data Provider Callback**: Integration provides a callback function to return actual data values

### Data Flow Diagram

```text
┌─────────────────────┐     ┌─────────────────────────┐
│   Your Integration  │     │  Synthetic Sensors      │
│                     │     │  Package                │
├─────────────────────┤     ├─────────────────────────┤
│                     │     │                         │
│ register_entities() ├────►│ 1. Register entity      │
│ {entity_id_1, ...}  │     │    ownership list       │
│                     │     │                         │
│ DataProviderCallback│◄────┤ 2. Call to get data     │
│ returns: TypedDict  │     │    for owned entities   │
│                     │     │                         │
└─────────────────────┘     │ 3. Query HA states      │
                            │    for non-owned        │
┌─────────────────────┐     │                         │
│   Home Assistant    │     │                         │
│   State Machine     │◄────┤ 4. ERROR if entity      │
│                     │     │    not found anywhere   │
└─────────────────────┘     └─────────────────────────┘

Flow: Formula "sensor.a + sensor.b"
├─ Check if sensor.a in registered entities
│  └─ If Yes → Call DataProviderCallback("sensor.a")
├─ Check if sensor.b in registered entities
│  └─ If No → Get sensor.b from HA States
└─ ERROR if any entity not found in either source
```

**Key Principle**: The integration **proactively registers** which entities it owns. No fallback behavior -
missing entities result in evaluation errors.

For each entity dependency in a formula:

1. Check if the entity is in the integration's registered entity list
2. If yes, use `DataProviderCallback` exclusively to get the value
3. If no, use normal HA state lookup exclusively
4. If entity not found in either source, evaluation fails with an error

**Entity State Independence**: Entities registered by the integration don't need to exist in Home Assistant's
entity registry. The integration can provide state for entities that only exist conceptually or internally.

## Integration Registration Model

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                            Integration                                  │
│                                                                         │
│  ┌─────────────────────┐    ┌─────────────────────────────────────────┐ │
│  │   Raw Device Data   │    │      Registration & Callbacks           │ │
│  │  • Temperature      │    │                                         │ │
│  │  • Humidity         │    │  register_entities({entity_ids})        │ │
│  │  • Status           │    │  └─ Push entity list to package         │ │
│  └─────────────────────┘    │                                         │ │
│                             │  DataProviderCallback(entity_id)        │ │
│                             │  └─ Returns: DataProviderResult         │ │
│                             └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                         │
                                         │ Entity Registration
                                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  Synthetic Sensors Package                              │
│                                                                         │
│  ┌─────────────────────┐    ┌─────────────────────────────────────────┐ │
│  │    Entity Store     │    │           Evaluator                     │ │
│  │                     │    │                                         │ │
│  │ Registered Entities │    │  For each entity:                       │ │
│  │ {entity_id_1,       │    │  1. Check entity store                  │ │
│  │  entity_id_2, ...}  │    │  2. If registered:                      │ │
│  │                     │    │     Call DataProviderCallback           | │
│  └─────────────────────┘    │  3. If not registered:                  │ │
│                             │     Query HA State Machine              | | 
│                             │  4. ERROR if not found anywhere         │ │
│                             └────────────────────────────────────────-┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │   Home Assistant    │
                              │   State Machine     │
                              └─────────────────────┘
```

## Implementation

### Setting Up Entity Registration

```python
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.types import DataProviderCallback

def my_data_provider_callback(entity_id: str) -> DataProviderResult:
    """Return DataProviderResult for the requested entity."""
    if entity_id == "sensor.my_integration_temp":
        return {"value": get_temperature_from_device(), "exists": True}
    elif entity_id == "sensor.my_integration_humidity":
        return {"value": get_humidity_from_device(), "exists": True}
    elif entity_id == "binary_sensor.my_integration_status":
        return {"value": is_device_online(), "exists": True}
    else:
        return {"value": None, "exists": False}

# Configure sensor manager with data provider callback
manager_config = SensorManagerConfig(
    data_provider_callback=my_data_provider_callback
)

sensor_manager = SensorManager(
    hass=hass,
    name_resolver=name_resolver,
    add_entities_callback=add_entities_callback,
    manager_config=manager_config
)

# Register entities that this integration can provide data for
sensor_manager.register_data_provider_entities({
    "sensor.my_integration_temp",
    "sensor.my_integration_humidity", 
    "binary_sensor.my_integration_status"
})

# Update the entity list dynamically when devices are added/removed
def on_device_added(device_id: str):
    current_entities = sensor_manager.get_registered_entities()
    current_entities.add(f"sensor.{device_id}_temp")
    sensor_manager.update_data_provider_entities(current_entities)
```

### Hybrid Approach Example

```yaml
synthetic_sensors:
  sensors:
    comfort_index
      name: "Comfort Index"
      formulas:
        # sensor.my_integration_temp comes from integration callback
        # sensor.weather_outside_temp comes from HA state
        formula: "(sensor.my_integration_temp + sensor.weather_outside_temp) / 2"
        unit_of_measurement: "°C"
```

In this example:

- `sensor.my_integration_temp` will be retrieved via the data provider callback
- `sensor.weather_outside_temp` will be retrieved from HA states as usual

## API Reference

### Entity Registration Methods

```python
# Register entities that the integration can provide data for
sensor_manager.register_data_provider_entities(entity_ids: set[str]) -> None

# Update the registered entity list (replaces existing list)
sensor_manager.update_data_provider_entities(entity_ids: set[str]) -> None

# Get current registered entities
sensor_manager.get_registered_entities() -> set[str]
```

### DataProviderCallback

```python
DataProviderCallback = Callable[[str], DataProviderResult]
```

Where `DataProviderResult` is:

```python
class DataProviderResult(TypedDict):
    value: FormulaResult  # The data value (can be numeric, string, boolean)
    exists: bool          # True if the entity exists and data is available
```

- **Parameters**:
  - `entity_id`: The entity ID to get data for
- **Returns**:
  - `DataProviderResult`: A TypedDict with `value` (data value) and `exists` (availability) fields
- **Called**: When evaluating formulas that reference integration entities
- **Purpose**: Provides the actual data values

## Error Handling

The evaluator provides strict error handling with no fallback behavior:

1. **Missing Integration Entities**: If a registered entity cannot be provided by the `DataProviderCallback`,
   evaluation fails immediately
2. **Missing HA Entities**: If a non-registered entity doesn't exist in HA, evaluation fails immediately
3. **Callback Errors**: If `DataProviderCallback` throws an exception, evaluation fails immediately
4. **No Zero Defaults**: There are no default values - missing data always results in evaluation errors

This strict approach ensures data integrity and prevents silent calculation errors from missing or invalid data.

## Benefits

- **Performance**: Direct data access bypasses HA state machine for integration entities
- **Flexibility**: Mix integration data with HA entities seamlessly in the same formula
- **Simplicity**: No need to create intermediate HA entities for calculation-only data
- **Data Integrity**: Strict error handling prevents silent calculation errors
- **Type Safety**: TypedDict interface provides clear data contracts and IDE support

## Backward Compatibility

This feature is completely backward compatible:

- Existing configurations work unchanged
- If no callbacks are provided, behavior is identical to before
- Callbacks are optional and can be added incrementally
