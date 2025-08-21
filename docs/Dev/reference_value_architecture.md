# ReferenceValue Architecture Implementation Guide

## Overview

The synthetic sensors system has migrated from using raw values in evaluation contexts to a type-safe **ReferenceValue**
architecture. This change ensures that handlers have access to both the original entity reference (entity ID) and the resolved
state value, enabling features like the `metadata()` function that need to know the actual Home Assistant entity ID.

## Key Changes

### Before: Raw Values

```python
# Old evaluation context
eval_context = {
    "temp_entity": "25.0",           # Raw state value
    "power_sensor": "1000.0",        # Raw state value
    "device_name": "Kitchen Sensor"  # Raw string value
}
```

### After: ReferenceValue Objects with Entity Registry

```python
# New evaluation context with centralized entity registry
eval_context = {
    "_entity_reference_registry": {
        "sensor.temperature": ReferenceValue(reference="sensor.temperature", value=25.0),
        "sensor.power_meter_2": ReferenceValue(reference="sensor.power_meter_2", value=1000.0),
        "Kitchen Sensor": ReferenceValue(reference="Kitchen Sensor", value="Kitchen Sensor")
    },
    "temp_entity": ReferenceValue(reference="sensor.temperature", value=25.0),  # Shared instance
    "power_sensor": ReferenceValue(reference="sensor.power_meter_2", value=1000.0),  # Shared instance
    "device_name": ReferenceValue(reference="Kitchen Sensor", value="Kitchen Sensor")  # Shared instance
}
```

## ReferenceValue Class

```python
class ReferenceValue:
    """Universal container for entity references and their resolved values."""

    def __init__(self, reference: str, value: StateType):
        """Initialize a reference/value pair.

        Args:
            reference: Original reference (variable name, entity ID, etc.)
            value: Resolved value (e.g., "25.5", 42, True)
        """
        self._reference = reference
        self._value = value

    @property
    def reference(self) -> str:
        """Get the original reference."""
        return self._reference

    @property
    def value(self) -> StateType:
        """Get the resolved value."""
        return self._value
```

**Key Properties:**

- **Entity-centric**: One `ReferenceValue` object per unique `entity_id` stored in `_entity_reference_registry`
- **Shared instances**: All variables referencing the same entity share the same `ReferenceValue` object
- **Collision-aware**: The `reference` includes collision suffixes (e.g., `sensor.power_meter_2`)
- **Type-safe**: Prevents raw values from being passed to handlers expecting entity references

## Entity Registry Architecture

The system maintains a centralized registry of `ReferenceValue` objects to ensure consistency and eliminate duplication:

### Registry Structure

```python
eval_context = {
    "_entity_reference_registry": {
        "sensor.temperature": ReferenceValue(reference="sensor.temperature", value=25.0),
        "sensor.power_meter_2": ReferenceValue(reference="sensor.power_meter_2", value=1000.0)
    },
    "temp_entity": ReferenceValue(reference="sensor.temperature", value=25.0),  # Shared instance
    "power_entity": ReferenceValue(reference="sensor.power_meter_2", value=1000.0)  # Shared instance
}
```

### Registry Benefits

1. **Memory Efficiency**: Single `ReferenceValue` instance per unique entity
2. **Consistency**: All variables referencing the same entity use identical objects
3. **Collision Handling**: Automatic entity ID suffix management (`_2`, `_3`, etc.)
4. **Type Safety**: Centralized management prevents raw value injection

## Variable Resolution Architecture

The system uses a unified `VariableResolverFactory` with multiple specialized resolvers:

### Resolver Hierarchy

```python
VariableResolverFactory
├── StateAttributeResolver      # Handles state.attribute patterns
├── StateResolver              # Resolves HA entity states
├── SelfReferenceResolver      # Handles entity ID self-references
├── EntityAttributeResolver    # Handles variable.attribute patterns
├── EntityReferenceResolver    # Resolves HA entity references
├── AttributeReferenceResolver # Handles attribute-to-attribute references
├── CrossSensorReferenceResolver # Manages cross-sensor dependencies
└── ConfigVariableResolver     # Fallback for direct values and entity references
```

### Direct Factory Usage

The system uses VariableResolverFactory:

```python
# Modern resolver factory usage in ContextBuildingPhase
def _create_resolver_factory(self, context: dict[str, ContextValue] | None) -> VariableResolverFactory:
    """Create modern variable resolver factory for direct resolution."""
    return VariableResolverFactory(
        hass=self._hass,
        data_provider_callback=self._data_provider_callback,
        sensor_to_backing_mapping=self._sensor_to_backing_mapping,
    )

# Direct resolution without tuple unpacking
resolved_value = resolver_factory.resolve_variable(
    variable_name=entity_id,
    variable_value=entity_id,
    context=eval_context
)
```

### Resolution Benefits

1. **Single Code Path**: Direct factory usage eliminates adapter complexity
2. **Type Safety**: All resolvers return `ReferenceValue` objects directly
3. **Performance**: No tuple packing/unpacking overhead
4. **Modular Design**: Each resolver handles specific resolution patterns
5. **Extensible**: Easy to add new resolution strategies
6. **Simple Error Handling**: Direct exception propagation without translation

## Entity ID Collision Handling

When multiple sensors reference the same entity ID, the system automatically adds suffixes:

```python
# Original entity: sensor.power_meter
# After collision detection: sensor.power_meter_2
ReferenceValue(reference="sensor.power_meter_2", value=1000.0)
```

### Collision Resolution Process

1. **Detection**: System identifies entity ID conflicts during sensor registration
2. **Suffix Assignment**: Automatic `_2`, `_3`, etc. suffix generation on entity_id collision in registry
3. **Configuration Update**: All references updated with collision-resolved IDs
4. **Runtime Consistency**: `ReferenceValue` objects use final entity IDs

## ReferenceValue Lifecycle

### 1. **Sensor Creation Phase (Initialization)**

**ReferenceValue objects are NOT created during sensor creation.** The sensor creation process focuses on:

- Creating `DynamicSensor` entities
- Setting up device associations
- Configuring entity attributes
- Registering with Home Assistant

No ReferenceValue objects exist at this stage - they are created dynamically during evaluation.

### 2. **Evaluation Context Creation (Runtime)**

ReferenceValue objects are created during the **Context Building Phase** (`context_building_phase.py`):

```python
# In ContextBuildingPhase._add_entity_to_context()
if isinstance(value, ReferenceValue):
    eval_context[entity_id] = value  # Reuse existing ReferenceValue
else:
    # Create new ReferenceValue for entity
    ReferenceValueManager.set_variable_with_reference_value(
        eval_context, entity_id, entity_id, value
    )
```

### 3. **Variable Resolution Process**

ReferenceValue objects are created in **two main locations**:

#### A. **Data Provider Resolution** (`utils_resolvers.py`)

```python
# In resolve_via_data_provider_entity()
return ReferenceValue(reference=entity_id, value=value)
```

#### B. **Home Assistant State Resolution** (`utils_resolvers.py`)

```python
# In resolve_via_hass_entity()
result = ReferenceValue(reference=entity_id, value=converted_value)
return result
```

### 4. **Entity Registry Management**

The **ReferenceValueManager** (`reference_value_manager.py`) manages the centralized registry:

```python
# Entity-centric registry: one ReferenceValue per unique entity_id
entity_registry = eval_context["_entity_reference_registry"]

if entity_reference in entity_registry:
    # Reuse existing ReferenceValue for this entity
    existing_ref_value = entity_registry[entity_reference]
    eval_context[var_name] = existing_ref_value
else:
    # Create new ReferenceValue for this entity
    ref_value = ReferenceValue(reference=entity_reference, value=resolved_value)
    entity_registry[entity_reference] = ref_value
    eval_context[var_name] = ref_value
```

### 5. **Handler Usage Patterns**

#### **Numeric Handler** (`numeric_handler.py`)

```python
def _extract_values_for_numeric_evaluation(self, context: EvaluationContext) -> dict[str, Any]:
    for key, value in context.items():
        if isinstance(value, ReferenceValue):
            # Extract the value from ReferenceValue for numeric computation
            numeric_context[key] = value.value
```

#### **Metadata Handler** (`metadata_handler.py`)

```python
if isinstance(context_value, ReferenceValue):
    # This is a ReferenceValue - use the reference directly
    ref_value_obj: ReferenceValue = context_value
    reference = ref_value_obj.reference  # Use for HA metadata lookup
    return reference
```

### 6. **Runtime Lifecycle Flow**

1. **Formula Evaluation Triggered**
2. **Dependency Extraction** - Identifies required entities
3. **Context Building Phase** - Creates evaluation context
4. **Variable Resolution** - Creates ReferenceValue objects via resolvers
5. **Registry Population** - Stores ReferenceValue objects in `_entity_reference_registry`
6. **Handler Execution** - Handlers extract values or use references as needed
7. **Context Cleanup** - ReferenceValue objects are garbage collected after evaluation

### 7. **Memory Management**

- ReferenceValue objects are **short-lived** - created per evaluation
- No persistent storage of ReferenceValue objects between evaluations
- Registry is recreated for each evaluation context
- Shared instances only exist within a single evaluation cycle

## Type System Dynamics

### Two-Tier Type Safety

The system uses **two-tier type safety** to balance flexibility during resolution with strict typing for handlers:

#### **Resolution Phase: ContextValue (Flexible)**

```python
# Type definitions show the difference:
ContextValue = ReferenceValue | Callable[..., Any] | State | ConfigType | StateType | None
```

During variable resolution, the system allows mixed types for flexibility:

- Raw values during initial resolution
- ReferenceValue objects after resolution
- Callables for mathematical functions
- State objects for HA entity access

#### **Handler Phase: EvaluationContext (Strict)**

```python
EvaluationContext = dict[str, ReferenceValue | Callable[..., Any] | State | ConfigType | None]
```

When handlers receive the context, it enforces strict typing:

- **Only ReferenceValue objects** for variables (no raw values)
- Callables for mathematical functions
- State objects for HA entity access
- ConfigType for configuration data

### Type Conversion Process

The system converts between these types automatically:

```python
# In ReferenceValueManager.convert_to_evaluation_context()
def convert_to_evaluation_context(context: dict[str, ContextValue]) -> EvaluationContext:
    evaluation_context: EvaluationContext = {}

    for key, value in context.items():
        if isinstance(value, (ReferenceValue, type(None))) or callable(value) or key.startswith("_"):
            # These are allowed in EvaluationContext
            evaluation_context[key] = value
        elif isinstance(value, (str, int, float, bool)):
            # Raw values are NOT allowed - this is a type safety violation
            raise TypeError(
                f"Context contains raw value for variable '{key}': {type(value).__name__}: {value}. "
                "All variables must be ReferenceValue objects."
            )
```

### Handler Type Safety Enforcement

Handlers receive `EvaluationContext` which guarantees:

- All variables are `ReferenceValue` objects
- No raw values can reach handlers
- Type safety is enforced at the handler boundary

## Entity ID Change Resilience

### **Complete Immunity to Entity ID Renaming**

The package is **completely immune** to entity ID renaming because ReferenceValue objects exist only for the duration of
evaluation.

### Entity Registry Listener Architecture

The `EntityRegistryListener` provides robust entity ID change detection and update mechanism:

#### **Event Detection**

```python
# In EntityRegistryListener._handle_entity_registry_updated()
if action == "update" and "entity_id" in changes:
    old_entity_id = changes["entity_id"]["old"]
    new_entity_id = changes["entity_id"]["new"]

    if self._is_entity_tracked(old_entity_id):
        self.hass.async_create_task(
            self._async_process_entity_id_change(old_entity_id, new_entity_id)
        )
```

#### **Storage Update Process**

When an entity ID changes, the system performs comprehensive updates:

```python
# In EntityRegistryListener._async_process_entity_id_change()
async def _async_process_entity_id_change(self, old_entity_id: str, new_entity_id: str):
    # 1. Update storage configurations
    await self._update_storage_entity_ids(old_entity_id, new_entity_id)

    # 2. Notify change handler to coordinate updates
    self.entity_change_handler.handle_entity_id_change(old_entity_id, new_entity_id)
```

**Storage updates include:**

- **Sensor configurations** (variables, formulas, attributes)
- **Global settings** (variables, device_identifier)
- **Entity index rebuilding**

#### **Cache Invalidation and Coordination**

The `EntityChangeHandler` ensures system-wide consistency:

```python
# In EntityChangeHandler.handle_entity_id_change()
def handle_entity_id_change(self, old_entity_id: str, new_entity_id: str):
    # Invalidate formula caches in all evaluators
    for evaluator in self._evaluators:
        evaluator.clear_cache()  # Clear ALL caches

    # Notify sensor managers and integration callbacks
    for callback in self._integration_callbacks:
        callback(old_entity_id, new_entity_id)
```

#### **Entity Index Rebuilding**

The system rebuilds entity indexes to reflect new entity IDs:

```python
# In EntityRegistryListener._save_and_rebuild_if_needed()
for sensor_set in sensor_sets_needing_rebuild:
    await sensor_set.async_rebuild_entity_index()
```

**Entity index tracks all entity references** in sensors and global settings:

```python
# In SensorSetEntityIndex.rebuild_entity_index()
def rebuild_entity_index(self, sensors: list[SensorConfig]) -> None:
    self._entity_index.clear()

    # Add entities from all sensors
    for sensor_config in sensors:
        self._entity_index.add_sensor_entities(sensor_config)

    # Add entities from global settings
    global_variables = global_settings.get("variables", {})
    if global_variables:
        self._entity_index.add_global_entities(global_variables)
```

### **Change Flow Verification**

The integration tests verify the complete flow:

```python
# Test verifies:
# 1. Entity is tracked before change
assert sensor_set.is_entity_tracked("sensor.main_power_meter")

# 2. Fire entity registry event
event_data = {
    "action": "update",
    "changes": {"entity_id": {"old": "sensor.main_power_meter", "new": "sensor.new_main_power_meter"}}
}
mock_hass.bus.async_fire(EVENT_ENTITY_REGISTRY_UPDATED, event_data)

# 3. Verify complete update
assert not sensor_set.is_entity_tracked("sensor.main_power_meter")
assert sensor_set.is_entity_tracked("sensor.new_main_power_meter")

# 4. Verify YAML configuration was updated
updated_yaml = sensor_set.export_yaml()
assert "sensor.new_main_power_meter" in updated_yaml
```

### **Entity ID Change Resilience Summary**

**✅ CONFIRMED:** The package is **completely resilient** to entity ID renaming because:

1. **ReferenceValue objects are ephemeral** - created fresh for each evaluation
2. **Configuration storage is immediately updated** when entity IDs change
3. **Entity indexes are rebuilt** to reflect new entity IDs
4. **Formula caches are cleared** to ensure fresh resolution
5. **Next evaluation uses updated entity IDs** from storage

**The ReferenceValue architecture's evaluation-scoped lifecycle is the key design decision** that eliminates any persistent
references to old entity IDs. When an entity ID changes:

- **Current evaluation** (if any) completes with old ReferenceValue objects
- **Storage is updated** with new entity IDs
- **Caches are cleared** to force fresh resolution
- **Next evaluation** creates new ReferenceValue objects with updated entity IDs from storage

This design ensures **zero impact** from entity ID renaming - the system automatically adapts without any manual intervention or
configuration changes.

## Impact on Different Components

### 1. Handler Signatures

**All handlers now receive `EvaluationContext` instead of raw values:**

```python
# Before
def evaluate(self, formula: str, context: dict[str, Any] | None = None) -> Any:

# After
def evaluate(self, formula: str, context: EvaluationContext | None = None) -> Any:
```

Where `EvaluationContext = dict[str, ReferenceValue | Callable[..., Any] | State | ConfigType | None]`

### 2. Formula Evaluation Pipeline

The system now has two parallel paths:

1. **Formula String Resolution**: Extracts values from `ReferenceValue` objects for SimpleEval

   ```python
   # Formula: "temp_entity * 1.0" becomes "25.0 * 1.0"
   ```

2. **Handler Context**: Preserves `ReferenceValue` objects for handlers that need entity references

   ```python
   # Handlers receive: {"temp_entity": ReferenceValue(reference="sensor.temperature", value=25.0)}
   ```

### 3. Variable Setting

**All variables must be set using `ReferenceValueManager`:**

```python
# Before
eval_context[var_name] = resolved_value

# After
ReferenceValueManager.set_variable_with_reference_value(
    eval_context, var_name, entity_reference, resolved_value
)
```

### 4. Double Wrapping Prevention

The system prevents `ReferenceValue` objects from being nested:

```python
def set_variable_with_reference_value(eval_context, var_name, entity_reference, resolved_value):
    if isinstance(resolved_value, ReferenceValue):
        # If resolved_value is already a ReferenceValue, use it directly
        ref_value = resolved_value
    else:
        # Create new ReferenceValue for raw values
        ref_value = ReferenceValue(reference=entity_reference, value=resolved_value)

    # Update registry and context
    entity_registry[entity_reference] = ref_value
    eval_context[var_name] = ref_value
```

## Required Test Updates

### 1. Context Assertions

**Tests expecting raw values need updates:**

```python
# Before
assert context["temp"] == 25.0

# After - Option 1: Check ReferenceValue
assert isinstance(context["temp"], ReferenceValue)
assert context["temp"].value == 25.0
assert context["temp"].reference == "sensor.temperature"

# After - Option 2: Extract value if that's what matters
temp_value = context["temp"].value if isinstance(context["temp"], ReferenceValue) else context["temp"]
assert temp_value == 25.0
```

### 2. Handler Tests

**Handlers must handle `ReferenceValue` objects:**

```python
# Numeric handlers need to extract values
def test_numeric_evaluation(self):
    context = {"temp": ReferenceValue("sensor.temperature", 25.0)}
    result = numeric_handler.evaluate("temp * 2", context)
    assert result == 50.0  # Handler extracts 25.0 and computes 25.0 * 2

# Metadata handlers can access entity references
def test_metadata_function(self):
    context = {"temp": ReferenceValue("sensor.temp_probe", 25.0)}
    result = metadata_handler.evaluate("metadata(temp, 'entity_id')", context)
    assert result == "sensor.temp_probe"  # Handler uses .reference
```

### 3. Integration Test Patterns

**Complex scenarios with collision resolution:**

```python
# Test collision resolution
assert "sensor.power_meter_2" in str(result)  # Collision suffix

# Test metadata with ReferenceValue
context = {"temp": ReferenceValue("sensor.temp_probe", 25.5)}
result = metadata_handler.evaluate("metadata(temp, 'entity_id')", context)
assert result == "sensor.temp_probe"
```

### 4. Mock Data Provider

**Update mock setups to return appropriate structures:**

```python
def mock_data_provider(entity_id: str):
    if entity_id == "sensor.temperature":
        return {"value": 25.0, "exists": True}  # Returns raw value for resolution
    return {"value": None, "exists": False}
```

## Handler Implementation Patterns

### Numeric Handlers

```python
def evaluate(self, formula: str, context: EvaluationContext | None = None) -> float:
    # Extract values for SimpleEval
    numeric_context = {}
    for key, value in context.items():
        if isinstance(value, ReferenceValue):
            numeric_context[key] = value.value
        else:
            numeric_context[key] = value

    return compiled_formula.evaluate(numeric_context)
```

### Metadata Handlers

```python
def evaluate(self, formula: str, context: EvaluationContext | None = None) -> Any:
    # Access original entity references
    for key, value in context.items():
        if isinstance(value, ReferenceValue):
            entity_id = value.reference  # Use for HA metadata lookup
            state_value = value.value    # Current state if needed
```

## Benefits

1. **Type Safety**: Prevents raw values from being passed to handlers expecting entity references
2. **Metadata Function Support**: Handlers can access original entity IDs for HA metadata lookups
3. **Clear Architecture**: Separation of concerns between formula evaluation and entity reference handling
4. **Future Extensibility**: Foundation for additional entity-aware features
5. **Unified Resolution**: Single code path eliminates technical debt
6. **Collision Handling**: Automatic entity ID conflict resolution
7. **Memory Efficiency**: Shared `ReferenceValue` instances per entity
8. **Entity ID Change Resilience**: Complete immunity to entity ID renaming

## Migration Checklist

- [ ] Update handler signatures to use `EvaluationContext`
- [ ] Replace direct context assignments with `ReferenceValueManager.set_variable_with_reference_value()`
- [ ] Update tests expecting raw values to handle `ReferenceValue` objects
- [ ] Move any inline imports to file tops
- [ ] Ensure handlers extract values appropriately for their use case
- [ ] Verify collision handling works correctly
- [ ] Test double wrapping prevention
- [ ] Verify entity ID change resilience through integration tests

## Common Issues

1. **`name 'ReferenceValue' is not defined`**: Add proper imports to file tops
2. **`assert ReferenceValue(...) == 25.0`**: Update test to compare `.value` property
3. **Handler receives wrong types**: Ensure handler signature uses `EvaluationContext`
4. **SimpleEval errors**: Verify value extraction happens before passing to SimpleEval
5. **Double wrapping**: Check for nested `ReferenceValue` objects
6. **Collision mismatches**: Ensure tests expect correct entity IDs with suffixes
7. **Type safety violations**: Ensure raw values don't reach handlers

This architecture provides a robust foundation for the synthetic sensors system while maintaining backward compatibility for
formula evaluation and eliminating technical debt through unified variable resolution. The evaluation-scoped lifecycle of
ReferenceValue objects ensures complete resilience to entity ID changes, making the system self-adapting to Home Assistant
entity registry modifications.
