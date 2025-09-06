# Context and Referenve Value Implementation Guide

## Overview

The synthetic sensors system has migrated from using raw values in evaluation contexts to a type-safe **ReferenceValue**
architecture. This change ensures that handlers have access to both the original entity reference (entity ID) and the resolved
state value, enabling features like the `metadata()` function that need to know the actual Home Assistant entity ID.

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

The system maintains an **internal cache** for entity deduplication that works alongside the hierarchical context architecture.
This approach ensures entity consistency while keeping the user-visible context clean.

### Internal Cache Structure

The `ReferenceValueManager` maintains a static internal cache that spans all layers of the hierarchical context:

```python
class ReferenceValueManager:
    # Internal cache for entity deduplication across all layers
    _entity_cache: dict[str, ReferenceValue] = {}

    @classmethod
    def set_variable_with_reference_value(cls, context, var_name, entity_reference, resolved_value):
        if entity_reference in cls._entity_cache:
            # Reuse existing ReferenceValue for this entity
            existing_ref_value = cls._entity_cache[entity_reference]
            context.set(var_name, existing_ref_value)
        else:
            # Create new ReferenceValue for this entity
            ref_value = ReferenceValue(reference=entity_reference, value=resolved_value)
            cls._entity_cache[entity_reference] = ref_value
            context.set(var_name, ref_value)
```

### How Internal Cache and Hierarchical Context Work Together

The **internal cache** and **hierarchical context** serve **different but complementary purposes**:

#### 1. **Hierarchical Context** = **Data Organization & Inheritance**

The hierarchical context manages **layers of context** that inherit from each other:

```python
# Hierarchical Context Structure
HierarchicalEvaluationContext("sensor_evaluation")
├── Layer 0: Global variables    {"global_constant": ReferenceValue(...)}
├── Layer 1: Sensor config vars  {"power_entity": ReferenceValue(...)}
├── Layer 2: Formula variables   {"temp_sensor": ReferenceValue(...)}
└── Layer 3: Runtime context     {"state": ReferenceValue(...)}
```

**Purpose**: Manage **variable scoping, inheritance, and context building** throughout the evaluation pipeline.

#### 2. **Internal Cache** = **Entity Deduplication Across All Layers**

The internal cache ensures **the same entity gets the same ReferenceValue object** regardless of which layer it appears in:

```python
# Internal Cache (spans all layers)
ReferenceValueManager._entity_cache = {
    "sensor.power_meter": ReferenceValue(ref="sensor.power_meter", val=1200.0),
    "sensor.temperature": ReferenceValue(ref="sensor.temperature", val=22.5)
}
```

**Purpose**: Ensure **entity deduplication and object sharing** across the entire evaluation context.

### Architecture Flow

![Internal Cache vs Hierarchical Context Architecture](internal_cache_hierarchical_context_relationship.jpeg)

This diagram shows how the internal cache and hierarchical context work together during variable resolution. The internal cache
ensures entity deduplication across all layers, while the hierarchical context manages variable scoping and inheritance.

### Cross-Layer Entity Sharing Example

```python
# Create hierarchical context with multiple layers
base_context = HierarchicalEvaluationContext("evaluation")
base_context.set("global_power", ReferenceValue(ref="sensor.power_meter", val=1200.0))

# Add a new layer
formula_context = base_context.create_child_layer("formula_vars")

# When resolving a variable in the new layer:
ReferenceValueManager.set_variable_with_reference_value(
    context=HierarchicalContextDict(formula_context),
    var_name="local_power",
    var_value="sensor.power_meter",  # Same entity as global_power!
    resolved_value=1200.0
)

# Result: Both layers reference the same ReferenceValue object
global_ref = base_context.get("global_power")
local_ref = formula_context.get("local_power")
assert global_ref is local_ref  # Same object across layers!
```

### Key Benefits

1. **Memory Efficiency**: Single `ReferenceValue` instance per unique entity across all layers
2. **Consistency**: All variables referencing the same entity use identical objects regardless of layer
3. **Clean User Context**: No internal bookkeeping keys visible to users
4. **Cross-Layer Sharing**: Same entity shared efficiently across global, sensor, and attribute layers
5. **Performance**: O(1) lookup for entity reuse
6. **Type Safety**: Centralized management prevents raw value injection

### Why Both Systems Are Needed

**Without Hierarchical Context**: No variable scoping, inheritance, or layered evaluation **Without Internal Cache**: Duplicate
ReferenceValue objects for the same entity across layers

```python
# BAD: Without internal cache
layer1["power"] = ReferenceValue(ref="sensor.power", val=1200.0)  # Object A
layer2["power"] = ReferenceValue(ref="sensor.power", val=1200.0)  # Object B (duplicate!)

# GOOD: With internal cache
layer1["power"] = cached_ref  # Object A
layer2["power"] = cached_ref  # Same Object A (shared!)
```

### Summary

The **internal cache** is a **cross-cutting concern** that ensures entity deduplication **across all layers** of the
hierarchical context. They work together to provide:

- **Hierarchical Context**: Proper variable scoping and inheritance
- **Internal Cache**: Efficient entity deduplication and object sharing

The cache operates **orthogonally** to the hierarchical structure - it doesn't care about layers, it just ensures the same
entity always gets the same `ReferenceValue` object, regardless of which layer it appears in!

### How Internal Cache Works with Hierarchical Flow

The internal cache operates **across all layers** of the hierarchical context, ensuring entity deduplication throughout the
entire YAML evaluation pipeline:

```python
# Example: Same entity referenced across multiple layers
# Layer 1: Global variables
global_context.set("power_limit", ReferenceValue("config.power_limit", 5000.0))

# Layer 2: Sensor variables
sensor_context.set("power_entity", ReferenceValue("sensor.power_meter", 1200.0))

# Layer 4: Attribute evaluation
attribute_context.set("is_critical", ReferenceValue("attr.is_critical", False))

# All three layers can reference the same entity (e.g., sensor.power_meter)
# The internal cache ensures they share the same ReferenceValue object
```

**Key Benefits of This Architecture**:

- **Cross-Layer Consistency**: Same entity gets same object regardless of which layer it's referenced in
- **Memory Efficiency**: No duplicate ReferenceValue objects for the same entity
- **Clean User Context**: Users only see their variables, not internal deduplication logic
- **Performance**: O(1) lookup for entity reuse across all evaluation phases

## Variable Resolution Architecture

The system uses a unified `VariableResolverFactory` with multiple specialized resolvers. **Resolvers return raw values for
formula substitution, but all values are immediately wrapped in ReferenceValue objects before being stored in the hierarchical
context.**

### Resolver Workflow

1. **Resolver Execution**: Resolver returns raw value (e.g., `240`, `7`, `True`)
2. **Value Wrapping**: Raw value is immediately wrapped in `ReferenceValue(reference=entity_id, value=raw_value)`
3. **Context Storage**: ReferenceValue object is stored in hierarchical context via `context.set(key, reference_value)`
4. **Formula Substitution**: Raw value is used for formula string substitution (e.g., `"power_entity * 1.0"` becomes
   `"1200.0 * 1.0"`)
5. **Context Accumulation**: ReferenceValue object persists in context for all subsequent evaluation phases

**Example Flow**:

```python
# 1. Resolver returns raw value
raw_value = state_resolver.resolve("power", "state.voltage", context)  # Returns: 240

# 2. Value is wrapped in ReferenceValue
reference_value = ReferenceValue(reference="state.voltage", value=240)

# 3. ReferenceValue is stored in context
context.set("power", reference_value)

# 4. Raw value is used for formula substitution
formula = "power * 2"  # Becomes: "240 * 2"

# 5. ReferenceValue persists in context for all phases
```

### Resolver Hierarchy

```text
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
2. **Type Safety**: Resolvers return raw values for formula substitution, then values are wrapped in ReferenceValue objects
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

#### **Resolution Phase: Raw Values for Formula Substitution**

```python
# Type definitions show the difference:
ContextValue = ReferenceValue | Callable[..., Any] | State | ConfigType | None
```

During variable resolution, resolvers return raw values for formula substitution:

- **Resolvers return raw values** (int, float, str, bool) for direct formula use
- **Values are immediately wrapped in ReferenceValue objects** before context storage
- **Callables** for mathematical functions
- **State objects** for HA entity access
- **No raw values are ever stored in context** - only ReferenceValue objects

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

### Complete Evaluation Cycle Context Accumulation

The hierarchical context accumulates **all resolved variables** throughout the entire evaluation cycle, ensuring nothing is lost
between phases:

#### **Phase 1: Global Variables**

```python
# Global configuration constants are resolved and stored
global_context.set("temp_offset", ReferenceValue("config.temp_offset", 2.0))
global_context.set("power_limit", ReferenceValue("config.power_limit", 5000.0))
```

#### **Phase 2: Sensor Variables**

```python
# Sensor-specific variables are resolved and stored
sensor_context.set("power_entity", ReferenceValue("sensor.power_meter", 1200.0))
sensor_context.set("temp_sensor", ReferenceValue("sensor.temperature", 25.0))
```

#### **Phase 3: Main Formula Evaluation**

```python
# Computed results from main formula are stored
formula_context.set("main_result", ReferenceValue("formula_result", 1200.0))
formula_context.set("is_within_limit", ReferenceValue("formula_result", True))
```

#### **Phase 4: Attribute Evaluation**

```python
# Attribute-specific formulas use accumulated context
# All previous variables (global, sensor, formula) are available
attr_context.set("is_critical", ReferenceValue("attr.is_critical", False))
attr_context.set("status", ReferenceValue("attr.status", "normal"))
```

#### **Phase 5: Alternate State Evaluation**

```python
# Alternate state conditions use complete accumulated context
# All variables from all previous phases are available
alt_context.set("offline_state", ReferenceValue("alt.offline", False))
alt_context.set("warning_state", ReferenceValue("alt.warning", True))
```

#### **Context Persistence Guarantee**

- **No variables are lost** between evaluation phases
- **Context only grows** - variables are never removed or overwritten
- **All phases inherit** the complete context from previous phases
- **ReferenceValue objects persist** throughout the entire evaluation lifecycle

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

## Common Issues

1. **`name 'ReferenceValue' is not defined`**: Add proper imports to file tops
2. **`assert ReferenceValue(...) == 25.0`**: Update test to compare `.value` property
3. **Handler receives wrong types**: Ensure handler signature uses `EvaluationContext`
4. **SimpleEval errors**: Verify value extraction happens before passing to SimpleEval
5. **Double wrapping**: Check for nested `ReferenceValue` objects
6. **Collision mismatches**: Ensure tests expect correct entity IDs with suffixes
7. **Type safety violations**: Ensure raw values don't reach handlers
8. **Metadata handler context assignment errors**: See detailed troubleshooting section below

## Metadata Handler Context Assignment Troubleshooting

### Issue: `'HierarchicalContextDict' object has no attribute 'set'`

**Problem**: When the metadata handler processes `metadata(state, 'last_changed')`, it needs to store the metadata result (e.g.,
`_metadata_0`) in the evaluation context for SimpleEval to access. However, direct assignment to `HierarchicalContextDict` is
prohibited by design.

**Error Messages**:

```text
DIRECT_ASSIGNMENT_VIOLATION: Attempted direct assignment _metadata_0 = ReferenceValue(...) bypasses hierarchical context unified setter!
Use context.set('_metadata_0', value) instead of context['_metadata_0'] = value
```

**Root Cause**: The `HierarchicalContextDict` is a protective wrapper that enforces the `ReferenceValue` architecture. It
prevents direct assignment (`context[key] = value`) to ensure all modifications go through the unified setter pattern.

**Solution**: Use the underlying `HierarchicalEvaluationContext.set()` method:

```python
# WRONG: Direct assignment
handler_context[key] = ReferenceValue(reference=key, value=value)

# CORRECT: Use hierarchical context's unified setter
handler_context.get_hierarchical_context().set(key, ReferenceValue(reference=key, value=value))
```

### Issue: `cannot access local variable 'traceback' where it is not associated with a value`

**Problem**: The `HierarchicalContextDict.__setitem__` method uses `traceback.format_stack()` for error reporting but doesn't
import the `traceback` module at the method level.

**Solution**: Add local import before using `traceback`:

```python
# In hierarchical_context_dict.py
def __setitem__(self, key: str, value: ContextValue) -> None:
    # ... other code ...

    # BULLETPROOF: Throw exception on direct assignment to catch violations
    import traceback  # Add this line
    stack_trace = "".join(traceback.format_stack())
```

### Metadata Handler Architecture Flow

1. **Metadata Processing**: `metadata(state, 'last_changed')` → `metadata_result(_metadata_0)`
2. **State Resolution**: `state` variable resolves to `ReferenceValue(reference='sensor.ok', value=100.0)`
3. **Metadata Retrieval**: Handler gets `last_changed` timestamp from `sensor.ok`
4. **Context Storage**: Metadata result stored as `_metadata_0` →
   `ReferenceValue(reference='_metadata_0', value='2025-09-02T23:40:01.626918+00:00')`
5. **SimpleEval Execution**: Formula `minutes_between(metadata_result(_metadata_0), now()) < 30` evaluates with context lookup

### Key Architectural Points

- **`ReferenceValue` Wrapping**: Metadata results must be wrapped in `ReferenceValue` objects before storage
- **Unified Setter Usage**: All context modifications must go through `HierarchicalEvaluationContext.set()`
- **Context Preservation**: The `HierarchicalContextDict` enforces architectural consistency by preventing raw value injection
- **AST Caching**: The `_metadata_0` key enables formula AST caching while providing runtime value lookup

## Hierarchical Context Architecture

The enhanced architecture introduces **hierarchical context management** with **cumulative ReferenceValue persistence**:

### Complete YAML Evaluation Flow

![Hierarchical Context YAML Flow](hierarchical_context_yaml_flow.jpeg)

This diagram shows the complete flow of how the hierarchical context grows and accumulates variables throughout the entire YAML
evaluation pipeline. The system maintains a single `HierarchicalEvaluationContext` instance that grows through multiple phases:

1. **Global Variables Phase**: Creates Layer 0 with configuration constants
2. **Sensor Variables Phase**: Adds Layer 1 with sensor-specific variables
3. **Main Formula Evaluation**: Adds Layer 2 with computed formula results
4. **Attribute Evaluation**: Adds Layer 4 with attribute-specific overrides
5. **Alternate State Evaluation**: Adds Layer 5 with alternate state conditions

Each layer inherits from the previous layers, ensuring that variables resolved in earlier phases remain available throughout the
entire evaluation lifecycle. This prevents the "False to None" conversion issue by maintaining variable persistence across
evaluation phases.

### CRITICAL ARCHITECTURAL PRINCIPLE: NO NEW CONTEXT CREATION

**NO layer should EVER start with a new, empty context. Every evaluation phase MUST inherit and build upon the previous
context.**

#### Absolute Rules

1. **NEVER create new HierarchicalEvaluationContext instances** - Always inherit from existing context
2. **NEVER allow methods to accept `HierarchicalContextDict | None`** - Context is always required
3. **NEVER start attribute evaluation with empty context** - Always inherit sensor's accumulated context
4. **ALWAYS pass context through** - Every method must accept and return HierarchicalContextDict
5. **ALWAYS build upon previous context** - Add new layers, never replace existing ones
6. **ALWAYS use unified setter** - All modifications go through `context.set(key, value)`

#### Context Inheritance Pattern

```python
# CORRECT: Inherit existing context
def evaluate_attribute(self, formula: FormulaConfig, sensor_context: SensorEvaluationContext) -> bool:
    # Get the sensor's accumulated context - NEVER create new one
    inherited_context = sensor_context.get_context_for_evaluation()

    # Add attribute-specific variables to existing context
    sensor_context.begin_attribute_evaluation(attr_name)

    # Evaluate with inherited context
    result = self._evaluator.evaluate_formula_with_sensor_config(formula, inherited_context, self._config)
    return result

# WRONG: Creating new context
def evaluate_attribute(self, formula: FormulaConfig) -> bool:
    # ❌ NEVER create new context
    new_context = HierarchicalEvaluationContext("attribute")  # WRONG!
    result = self._evaluator.evaluate_formula_with_sensor_config(formula, new_context, self._config)
    return result
```

#### Method Signature Requirements

```python
# CORRECT: Always require context
def evaluate_formula(self, formula: str, context: HierarchicalContextDict) -> EvaluationResult:
    # Context is guaranteed to exist and contain previous evaluation results
    pass

# WRONG: Optional context
def evaluate_formula(self, formula: str, context: HierarchicalContextDict | None = None) -> EvaluationResult:
    # ❌ NEVER allow None - this breaks the inheritance chain
    if context is None:
        context = HierarchicalEvaluationContext("new")  # WRONG!
    pass
```

#### Core Principles

1. **ONE Context Per Sensor Evaluation**: Each sensor gets a single `SensorEvaluationContext` that persists throughout the
   entire evaluation lifecycle
2. **Context Inheritance Chain**: Every evaluation phase inherits the previous context - NO exceptions
3. **Hierarchical Scoping**: Context layers respect programming language scoping rules (global → sensor → attribute)
4. **Cumulative Growth**: Once a variable is resolved to a ReferenceValue, it remains in context and never disappears
5. **Reference Immutability**: The `reference` part of ReferenceValue never changes; only `value` can be updated
6. **Unified Context Setter**: All context modifications go through a single setter to ensure consistency
7. **No Context Creation**: Never create new HierarchicalEvaluationContext instances during evaluation

#### Architecture Components

```python
# New hierarchical context classes
class EvaluationContext:
    """Hierarchical context with layered scoping and integrity tracking."""

    def __init__(self, name: str = "root"):
        self._layers: list[dict[str, ContextValue]] = []
        self._layer_names: list[str] = []
        self._instance_id = id(self)  # For integrity tracking
        self._item_count = 0
        self._generation = 0

    def push_layer(self, name: str, variables: dict[str, ContextValue] | None = None) -> None:
        """Push new context layer (global → sensor → attribute)."""

    def set(self, key: str, value: ContextValue) -> None:
        """Set variable in current layer - ONLY way to modify context."""

    def get(self, key: str, default: Any = None) -> ContextValue:
        """Get variable respecting scoping (inner layers override outer)."""

    def flatten(self) -> dict[str, ContextValue]:
        """Return flattened view respecting scoping rules."""

class SensorEvaluationContext:
    """Manages hierarchical context for single sensor evaluation lifecycle."""

    def __init__(self, sensor_id: str):
        self.context = EvaluationContext(f"sensor_{sensor_id}")
        self._context_uuid = str(uuid.uuid4())  # For tracking propagation

    def add_global_variables(self, globals_dict: dict[str, ContextValue]) -> None:
        """Add global variables as base layer."""

    def add_sensor_variables(self, sensor_vars: dict[str, ContextValue]) -> None:
        """Add sensor-level variables as new layer."""

    def get_context_for_evaluation(self) -> dict[str, ContextValue]:
        """Get flattened context with integrity tracking."""
```

#### Context Lifecycle Flow

```text
graph TD
    A[Sensor Update Triggered] --> B[Create SensorEvaluationContext]
    B --> C[Push Global Layer]
    C --> D[Push Sensor Variables Layer]
    D --> E[Main Formula Evaluation]
    E --> F[Computed Variables Resolved]
    F --> G[Variables Added to Context via set()]
    G --> H[Attribute Evaluation Phase - INHERITS Previous Context]
    H --> I[Context Contains All Resolved Variables]
    I --> J[Cleanup Context]

    style H fill:#ffeb3b
    style H stroke:#f57c00
    style H stroke-width:3px
```

**Key Point**: The arrow from G to H shows **inheritance**, not creation. Attribute evaluation receives the existing context
with all previous variables intact.

#### Context Integrity Tracking

```python
# Integrity tracking prevents context corruption
integrity_info = {
    "instance_id": self._instance_id,      # Memory address - must never change
    "item_count": self._item_count,        # Total unique variables - only grows
    "generation": self._generation,        # Modification counter - only increases
    "checksum": self._get_checksum(),      # Hash of all keys
    "layer_count": len(self._layers)       # Number of context layers
}
```

#### Unified Context Setter Pattern

**CRITICAL**: All context modifications must go through the unified setter:

```python
# CORRECT: Always use the setter
sensor_context.context.set("computed_var", ReferenceValue("formula_result", False))

# WRONG: Direct assignment bypasses integrity tracking
eval_context["computed_var"] = False  # ❌ Breaks architecture
```

#### Variable Resolution Integration

The evaluator now properly integrates with hierarchical context:

```python
# In evaluator.py - BEFORE variable resolution
initial_integrity = eval_context.get("_context_integrity", {})

# Variable resolution happens
resolution_result, resolved_formula = self._resolve_formula_variables(config, sensor_config, eval_context)

# AFTER variable resolution - check for new variables
new_keys = set(eval_context.keys()) - initial_keys
if new_keys:
    # Variables were added during resolution
    for key in new_keys:
        if not key.startswith("_"):  # Skip internal keys
            # Variable is already in context via unified setter
            _LOGGER.info("CONTEXT_GROWTH: Added %s to context", key)
```

#### Context Propagation Between Phases

```python
# In sensor_manager.py - Context propagation
eval_context = sensor_context.get_context_for_evaluation()
initial_integrity = eval_context.get("_context_integrity", {})

# Main formula evaluation
main_result = self._evaluator.evaluate_formula_with_sensor_config(
    self._main_formula, eval_context, self._config
)

# Get updated context from evaluator
updated_context = self._evaluator.get_evaluation_context(self._main_formula, self._config)

# Propagate resolved variables back to hierarchical context
for key, value in updated_context.items():
    if not key.startswith("_") and key not in current_keys:
        sensor_context.context.set(key, value)  # Unified setter
```

### Benefits of Hierarchical Context

1. **Context Persistence**: Resolved variables never disappear between evaluation phases
2. **Scoping Rules**: Attribute variables can override sensor variables naturally
3. **Integrity Tracking**: Detect context corruption with instance ID, counters, checksums
4. **Single Source of Truth**: One context per sensor evaluation eliminates confusion
5. **Unified Modification**: All context changes go through validated setter
6. **Reference Immutability**: ReferenceValue.reference never changes, only .value updates
7. **Cumulative Growth**: Context only grows, never loses variables

### Context Scoping Example

```python
# Layer 1: Global variables
globals_layer = {
    "global_temp_offset": ReferenceValue("config.temp_offset", 2.0)
}

# Layer 2: Sensor variables
sensor_layer = {
    "temp_sensor": ReferenceValue("sensor.temperature", 25.0),
    "global_temp_offset": ReferenceValue("sensor.local_offset", 1.5)  # Overrides global
}

# Layer 3: Computed variables from main formula
computed_layer = {
    "is_within_grace_period": ReferenceValue("formula_result", False),
    "panel_offline_minutes": ReferenceValue("formula_result", 45)
}

# Layer 4: Attribute-specific variables
attribute_layer = {
    "temp_sensor": ReferenceValue("attr.override_temp", 30.0)  # Overrides sensor layer
}

# Flattened context respects scoping:
flattened = {
    "global_temp_offset": ReferenceValue("sensor.local_offset", 1.5),    # Sensor overrides global
    "temp_sensor": ReferenceValue("attr.override_temp", 30.0),           # Attribute overrides sensor
    "is_within_grace_period": ReferenceValue("formula_result", False),   # From computed layer
    "panel_offline_minutes": ReferenceValue("formula_result", 45)        # From computed layer
}
```

All layers are built upon the same `HierarchicalEvaluationContext` instance. The `push_layer()` method adds new layers to the
existing context, never creates a new context object.

### Common Anti-Patterns to Avoid

```python
# WRONG: Creating new context in attribute evaluation
def evaluate_attribute(self, formula: FormulaConfig) -> bool:
    new_context = HierarchicalEvaluationContext("attribute")  # WRONG!
    return self._evaluator.evaluate_formula(formula, new_context)

# WRONG: Optional context parameter
def evaluate_formula(self, formula: str, context: HierarchicalContextDict | None = None) -> EvaluationResult:
    if context is None:
        context = HierarchicalEvaluationContext("default")  # WRONG!
    # ... rest of method

# WRONG: Starting with empty context
def process_variables(self, variables: dict) -> HierarchicalContextDict:
    context = HierarchicalEvaluationContext("variables")  # WRONG!
    for key, value in variables.items():
        context.set(key, value)
    return context

# CORRECT: Inherit existing context
def evaluate_attribute(self, formula: FormulaConfig, sensor_context: SensorEvaluationContext) -> bool:
    inherited_context = sensor_context.get_context_for_evaluation()  # Inherit!
    return self._evaluator.evaluate_formula(formula, inherited_context)

# CORRECT: Required context parameter
def evaluate_formula(self, formula: str, context: HierarchicalContextDict) -> EvaluationResult:
    # Context is guaranteed to exist and contain previous results
    # ... rest of method

# CORRECT: Build upon existing context
def process_variables(self, variables: dict, existing_context: HierarchicalContextDict) -> HierarchicalContextDict:
    for key, value in variables.items():
        existing_context.set(key, value)  # Add to existing context
    return existing_context
```

### **Summary: Context Inheritance is MANDATORY**

This hierarchical context architecture ensures that computed variables are properly accumulated and persist throughout the
entire sensor evaluation lifecycle, eliminating the `False` to `None` conversion issue and providing a robust foundation for
complex formula dependencies.
