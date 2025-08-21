# State and Entity Reference Guide

This document describes the behavior of state and entity references in synthetic sensor formulas, including main formulas,
attributes, and attribute-to-attribute references.

## Overview

Synthetic sensors support multiple ways to reference entities and values within formulas. Understanding these reference patterns
is crucial for creating effective sensor configurations. The integration is responsible for properly constructing sensor
definitions and ensuring that references to other entities are valid, including the registration of backing entities that may be
in-memory objects.

These idioms define the fundamental rules and behaviors for state and entity references in synthetic sensor formulas. They are
the foundation for all formula evaluation and variable resolution in the package.

The system implements entities reference and values internally using a **ReferenceValue architecture** that ensures type safety
and provides handlers with access to both entity references and resolved values. This architecture enables features like the
`metadata()` function that require knowledge of the actual Home Assistant entity ID. For detailed implementation information,
see the [ReferenceValue Architecture Implementation Guide](reference_value_architecture.md).

## Synthetic Sensor Definitions

- YAML provides the synthetic sensor definition with a main sensor formula at a minimum.
- The pre-evaluation state refers to the sensor's last calculated value from the previous evaluation cycle.
- The pos-evaluation state refers to the sensor state after the formula is evaluated.
- A backing entity refers to synthetic sensor state referenced through another object which could be an integration-owned
  virtual object or a an HA registered sensor (whether owned by the integration or not). Backing entities are registered and
  referenced by their entity_id.
- A formula can be purely a calculated state and not have a backing entity in which case the state of the sensor is the
  synthetic state itself.
- The integration is responsible for properly constructing sensor definitions (YAML) and ensuring that references to other
  entities within that YAML are valid. When an integration starts up, the initial data in backing entities (if any) should be
  fully populated.
- The registration of backing entities will be validated by the synthetic package such that a registration provides at least one
  dictionary entry for any backing entities that are registered. If backing entities were provided but no entries exist, this
  condition is a fatal error and an appropriate exception should be raised.

## Standard HA State Values

The following state values are recognized and handled consistently throughout the package:

- **`"unavailable"`**: Represents an entity that exists but is temporarily unavailable (e.g., device offline)
- **`"unknown"`**: Represents an entity that exists but has no known state value
- **`"None"`**: String representation that can be handled by alternate state handlers

### State Value Handling Rules

1. **Consistent Casing**: All HA state values use lowercase (`"unknown"`, `"unavailable"`) for consistency
2. **Early Detection**: HA state values are detected during variable resolution phase, before formula evaluation begins
3. **Alternate State Handler Processing**: When HA state values are detected, they trigger alternate state handlers if defined
4. **Early Detection**: Single variables with alternate states are detected during variable resolution phase
5. **Post-Evaluation Processing**: Results containing alternate states trigger handlers after formula evaluation
6. **Exception Mapping**: Evaluation exceptions are mapped to appropriate alternate states (undefined → unavailable, etc.)
7. **Enhanced Dependency Reporting**: Unavailable dependencies are reported with context including variable names and entity IDs

### Implementation Notes

- **Variable Resolution**: HA state values are detected during variable resolution phase using enhanced detection logic
- **Alternate State Handler Integration**: When HA states are detected, they trigger the comprehensive alternate state handler
  system
- **Two-Phase Processing**: Early detection during variable resolution and post-evaluation processing for results and exceptions
- **Enhanced Dependency Tracking**: HA state values are tracked in `unavailable_dependencies` with format:
  `"variable_name (entity_id) is state_value"` for better debugging context
- **Entity Mapping**: Variable resolution tracks entity mappings to provide accurate entity IDs in dependency reporting
- **Integration Support**: This allows integrations to gracefully handle initialization periods and temporary unavailability
- **Architectural Integration**: HA state detection is integrated into the layered, compiler-like evaluation system
- **VariableResolutionResult**: Enhanced variable resolution returns structured results with HA state detection
- **Duplicate Prevention**: The system prevents duplicate dependency entries during variable resolution
- **Handler Priority System**: Specific handlers (none/unknown/unavailable) take precedence over fallback handlers

## State and Entity Idioms

1. **Sensor Evaluation Order** The main sensor has two states - the pre-evaluation state and the post-evaluation state. The main
   sensor is evaluated before attributes are evaluated. A main sensor state cannot be circular to itself. References to the main
   sensor state (backing or external entities) are evaluated prior to any other evaluation. Attribute formulas are evaluated in
   dependency order, ensuring that all referenced values are available.
2. **Main Formula State Idiom** If a sensor has a resolvable backing entity, the `state` token in the main formula resolves to
   the current state of the backing entity. If there is no backing entity, `state` refers to the sensor's own pre-evaluation
   state.
3. **Attribute State Idiom** In attribute formulas, the `state` token always refers to the result of the main sensor's formula
   evaluation (i.e., the main sensor's calculated value after all variables and dependencies are resolved), never directly to
   the backing entity.
4. **Self-Reference Idiom** In main formulas, referencing the sensor by its key (e.g., `my_sensor`) or by its full entity ID
   (e.g., `sensor.my_sensor`) is equivalent to using the `state` token. All three resolve to the backing entity's state (if
   present) or the sensor's previous value (if not). If the backing entity value is None, it can be handled by alternate state
   handlers.
5. **Attribute Self-Reference Idiom** In attribute formulas, referencing the main sensor by its key or entity ID is equivalent
   to using the `state` token. All attribute forms resolve to the main sensor's calculated value (post-evaluation).
6. **State Reference Idiom** The main state can reference attributes but those attribute references are dereferenced prior to
   main sensor state evaluation. Attributes can reference other attributes within the same sensor by dot notation, i.e.,
   `state.myattribute`. These references are resolved in dependency order, and circular references (either with the main sensor
   state or to other attributes) are detected and prevented.
7. **Variable Inheritance Idiom** All variables defined in the parent sensor are automatically available in attribute formulas.
8. **Direct Entity Reference Idiom** Any formula can reference the state of any Home Assistant entity directly by its full
   entity ID (e.g., `sensor.some_entity`). This always resolves to the current state of that entity.
9. **Error Propagation Idiom** If a required entity or variable cannot be resolved, or if a data provider returns invalid data,
   a specific exception is raised (`BackingEntityResolutionError`, `MissingDependencyError`, or `DataValidationError`). Fatal
   errors are never silently converted to error results. However, None values from backing entities can be handled by alternate
   state handlers to allow for integration initialization.
10. **Consistent Reference Idiom** The same reference patterns (`state`, sensor key, entity ID) are supported in both main and
    attribute formulas, but their meaning is context-dependent (main formula = backing entity or previous value; attribute =
    main sensor's calculated value).

## Enhanced Dependency Reporting

The synthetic sensor package provides enhanced dependency reporting to improve debugging and monitoring capabilities. When
dependencies are unavailable or contain HA state values, the system reports detailed information including both variable names
and entity IDs.

### Dependency Reporting Format

Unavailable dependencies are reported in the following format:

```python
"variable_name (entity_id) is state_value"
```

This format provides:

- **Variable Name**: The variable or reference name used in the formula
- **Entity ID**: The actual Home Assistant entity ID that was referenced
- **State Value**: The HA state value that caused the dependency to be unavailable

### Examples

```yaml
sensors:
  # Example: Backing entity with unknown state - handled by alternate state handler
  power_monitor:
    entity_id: sensor.panel_power # Entity exists but value is None
    formula: state * 2
    alternate_states:
      NONE: 0 # Handle None values by returning 0
    # Result:
    #   state: "ok"
    #   value: 0 (from none handler)
    #   unavailable_dependencies: ["source_value (sensor.panel_power) is unknown"]

  # Example: Variable reference with unavailable state - handled by fallback
  efficiency_calc:
    variables:
      panel_power: sensor.panel_power # Entity state = "unavailable"
    formula: panel_power * 0.95
    alternate_states:
      FALLBACK: 100 # Fallback value when dependencies are unavailable
    # Result:
    #   state: "ok"
    #   value: 100 (from fallback handler)
    #   unavailable_dependencies: ["panel_power (sensor.panel_power) is unavailable"]

  # Example: Multiple unavailable dependencies - handled by specific handlers
  complex_calc:
    variables:
      power1: sensor.panel_power # Entity state = "unknown"
      power2: sensor.solar_power # Entity state = "unavailable"
    formula: power1 + power2
    alternate_states:
      UNKNOWN: 50 # Handle unknown state
      UNAVAILABLE: 25 # Handle unavailable state
    # Result:
    #   state: "ok"
    #   value: 75 (from handlers: 50 + 25)
    #   unavailable_dependencies: [
    #     "power1 (sensor.panel_power) is unknown",
    #     "power2 (sensor.solar_power) is unavailable"
    #   ]
```

### Implementation Details

- **Entity Mapping Tracking**: Variable resolution tracks mappings between variable names and entity IDs
- **Config Variable Resolution**: Variables defined in sensor configuration are resolved and tracked
- **Cross-Sensor References**: Cross-sensor references maintain their entity ID mappings
- **Duplicate Prevention**: The system prevents duplicate dependency entries
- **Context Preservation**: Both variable names and entity IDs are preserved for debugging context

### Benefits

1. **Enhanced Debugging**: Developers can see both the variable name used in formulas and the actual entity ID
2. **Integration Support**: Integrations can use entity IDs for direct entity management
3. **Monitoring**: System administrators can correlate variable names with actual Home Assistant entities
4. **Error Context**: Clear indication of which specific entities are causing formula evaluation issues

## Main Sensor Formula References

### State Token (`state`)

The `state` token in a main sensor formula has specific behavior based on the sensor configuration:

#### With Backing Entity

When a sensor has a `entity_id` field (backing entity):

```yaml
sensors:
  # Example: Power meter with backing entity
  power_analysis:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity
    formula: state * 1.1 # 'state' = backing entity value (e.g., 1000W)
    metadata:
      unit_of_measurement: W
```

- **Behavior**: `state` resolves to the backing entity's current state value
- **Evaluation**: The backing entity's state is fetched and used in the formula
- **None Value Handling**: If the backing entity value is None, it can be handled by alternate state handlers to allow for
  integration initialization
- **Error Handling**: If the backing entity is not registered or the registration contains no entries,
  `BackingEntityResolutionError` is raised

#### Without Backing Entity (Pure Mathematical)

When a sensor has no `entity_id` field:

```yaml
sensors:
  # Example: Pure calculation sensor (no backing entity)
  efficiency_calculator:
    formula: sensor.solar_power / sensor.total_power * 100 # No 'state' token used
    metadata:
      unit_of_measurement: "%"

  # Example: Recursive calculation using previous value
  power_trend:
    formula: (state + sensor.current_power) / 2 # 'state' = previous calculated value
    metadata:
      unit_of_measurement: W
```

- **Behavior**: `state` refers to the sensor's previous calculated value
- **Evaluation**: Uses the last known value of the sensor itself
- **Use Case**: Useful for calculations that depend on the sensor's own history

### Self-Reference Patterns

Main formulas support two safe ways to reference the backing entity:

```yaml
sensors:
  # Example: Two safe ways to reference backing entity
  power_calculator:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity = 1000W
    # Both formulas produce the same result (2000W):
    formula: state * 2 # Method 1: State token (recommended)
    # formula: sensor.power_calculator * 2 # Method 2: Explicit entity ID self-reference
    metadata:
      unit_of_measurement: W
```

**Note**: Both patterns resolve to the backing entity's state value when a backing entity is configured.

**Safety**: Using `state` is the recommended approach as it's completely safe and unambiguous. Entity ID self-references require
the entity to exist in Home Assistant.

## Attribute Formula References

### State Token in Attributes

The `state` token in attribute formulas has different behavior than in main formulas:

```yaml
sensors:
  # Example: Attribute state vs main formula state
  energy_cost:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity = 1000W
    formula: state * 0.25 # Main formula: 1000W * 0.25 = 250 cents/h
    attributes:
      daily_cost:
        formula: state * 24 # Attribute: 250 cents/h * 24 = 6000 cents/day
        metadata:
          unit_of_measurement: cents
      # Key difference:
      # - Main formula 'state' = backing entity (1000W)
      # - Attribute 'state' = main sensor result (250 cents/h)
```

- **Behavior**: `state` refers to the **result of the main sensor's formula evaluation**
- **Evaluation Order**:
  1. Main formula evaluates using backing entity state
  2. Attribute formula evaluates using the main sensor's calculated result
- **Key Point**: Attributes always reference the main sensor's post-evaluation value, never the backing entity directly

### Attribute Reference Patterns

Attributes support the same two reference patterns as main formulas:

```yaml
sensors:
  # Example: Two safe ways to reference main sensor in attributes
  power_analyzer:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity = 1000W
    formula: state * 1.1 # Main result = 1100W
    attributes:
      # Both produce the same result (26400W):
      daily_power:
        formula: state * 24 # Method 1: State token (recommended)
        metadata:
          unit_of_measurement: W
      weekly_power:
        formula: sensor.power_analyzer * 24 * 7 # Method 2: Explicit entity ID self-reference
        metadata:
          unit_of_measurement: W
```

**Note**: Both patterns in attributes resolve to the main sensor's calculated value (post-evaluation).

**Safety**: Using `state` is the recommended approach for attributes as it clearly indicates reference to the main sensor's
result.

## Attribute-to-Attribute References (A-A)

### Overview

Attributes can reference other attributes within the same sensor, enabling complex calculations:

```yaml
sensors:
  # Example: Attribute-to-attribute references (A-A)
  energy_analyzer:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity = 1000W
    formula: state * 0.25 # Main result = 250 cents/h
    attributes:
      hourly_cost:
        formula: state # 250 cents/h (from main sensor)
        metadata:
          unit_of_measurement: cents/h
      daily_cost:
        formula: hourly_cost * 24 # A-A reference: 250 * 24 = 6000 cents/day
        metadata:
          unit_of_measurement: cents/day
      weekly_cost:
        formula: daily_cost * 7 # A-A reference: 6000 * 7 = 42000 cents/week
        metadata:
          unit_of_measurement: cents/week
      monthly_cost:
        formula: weekly_cost * 4 # A-A reference: 42000 * 4 = 168000 cents/month
        metadata:
          unit_of_measurement: cents/month
```

### Reference Syntax

Attribute-to-attribute references use direct attribute names (not dot notation):

```yaml
attributes:
  # Correct syntax:
  attribute2:
    formula: attribute1 * 2 # Direct attribute name reference


  # Incorrect syntax (not supported):
  # formula: state.attribute1 * 2  # Dot notation not supported
```

### Evaluation Order

Attributes are evaluated in dependency order to prevent circular references:

1. **Dependency Analysis**: The system analyzes attribute dependencies
2. **Topological Sort**: Attributes are ordered based on their dependencies
3. **Sequential Evaluation**: Attributes are evaluated in dependency order
4. **Circular Reference Detection**: Infinite loops are prevented

### Circular Reference Protection

The system detects and prevents circular references:

```yaml
sensors:
  # Example: Circular reference (will cause error)
  problematic_sensor:
    entity_id: sensor.power_meter
    formula: state * 2
    attributes:
      attr1:
        formula: attr2 * 2 # References attr2
        metadata:
          unit_of_measurement: W
      attr2:
        formula: attr1 * 3 # References attr1 (circular!)
        metadata:
          unit_of_measurement: W
      # Result: CircularDependencyError is raised

  # Example: Valid linear dependency
  valid_sensor:
    entity_id: sensor.power_meter
    formula: state * 2
    attributes:
      hourly:
        formula: state # References main sensor
        metadata:
          unit_of_measurement: W
      daily:
        formula: hourly * 24 # References hourly attribute
        metadata:
          unit_of_measurement: W
      weekly:
        formula: daily * 7 # References daily attribute
        metadata:
          unit_of_measurement: W
      # Result: Valid linear dependency chain
```

**Error**: `CircularDependencyError` is raised when circular references are detected.

## State Attribute References and Circular Reference Rules

### State Attribute Behavior

The `state.attribute` pattern has different meanings depending on context:

#### In Main Formulas

```yaml
sensors:
  # Example: Main formula referencing backing entity attributes
  power_analyzer:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity with voltage attribute
    formula: state.voltage * state # 'state.voltage' = backing entity's voltage attribute
    metadata:
      unit_of_measurement: V
```

- **`state.attribute`**: References the **backing entity's attribute** (pre-evaluation)
- **Behavior**: Uses the current/previous value of the backing entity's attribute
- **No Circular Issue**: Since `state` refers to pre-evaluation backing entity state, there's no circular dependency

#### In Attribute Formulas

```yaml
sensors:
  # Example: Attribute referencing main sensor attributes
  energy_calculator:
    entity_id: sensor.power_meter
    formula: state * 2 # Main result = 2000W
    attributes:
      voltage_analysis:
        formula: state.voltage * 1.1 # 'state.voltage' = main sensor's voltage attribute
        metadata:
          unit_of_measurement: V
      # 'state' = main sensor post-evaluation (2000W)
      # 'state.voltage' = main sensor's voltage attribute after evaluation
```

- **`state.attribute`**: References the **main sensor's attribute** (post-evaluation)
- **Behavior**: Uses the newly calculated value of the main sensor's attribute
- **Evaluation Order**: Main sensor attributes are calculated before attribute formulas

### Circular Reference Detection

The system detects and prevents circular references in several scenarios:

#### 1. Attribute-to-Attribute Circular References

```yaml
sensors:
  # Example: Circular reference between attributes (DISALLOWED)
  problematic_sensor:
    entity_id: sensor.power_meter
    formula: state * 2
    attributes:
      attr_a:
        formula: attr_b * 2 # References attr_b
        metadata:
          unit_of_measurement: W
      attr_b:
        formula: attr_a * 3 # References attr_a (circular!)
        metadata:
          unit_of_measurement: W
      # Result: CircularDependencyError is raised
```

#### 2. Self-Referencing Attributes

```yaml
sensors:
  # Example: Attribute referencing itself (DISALLOWED)
  invalid_sensor:
    entity_id: sensor.power_meter
    formula: state * 2
    attributes:
      voltage:
        formula: state.voltage + 1 # References its own voltage attribute
        metadata:
          unit_of_measurement: V
      # Result: CircularDependencyError is raised
```

#### 3. Valid Attribute References

```yaml
sensors:
  # Example: Valid linear attribute dependencies (ALLOWED)
  valid_sensor:
    entity_id: sensor.power_meter
    formula: state * 2 # Main result = 2000W
    attributes:
      hourly:
        formula: state # References main sensor (2000W)
        metadata:
          unit_of_measurement: W
      daily:
        formula: hourly * 24 # References hourly attribute (48000W)
        metadata:
          unit_of_measurement: W
      weekly:
        formula: daily * 7 # References daily attribute (336000W)
        metadata:
          unit_of_measurement: W
      # Result: Valid linear dependency chain
```

### Allowed vs Disallowed Patterns

| Pattern                     | Context           | Allowed | Example                 |
| --------------------------- | ----------------- | ------- | ----------------------- |
| `state.attribute`           | Main formula      | ✅      | `state.voltage * state` |
| `state.attribute`           | Attribute formula | ✅      | `state.voltage * 1.1`   |
| `attr1` → `attr2` → `attr1` | Attribute chain   | ❌      | Circular reference      |
| `attr1` → `attr1`           | Self-reference    | ❌      | Self-referencing        |
| `attr1` → `attr2` → `attr3` | Linear chain      | ✅      | Valid dependency        |

### Testing Requirements

The following scenarios should be tested to ensure proper behavior:

1. **Main formula `state.attribute`**: Resolves to backing entity attribute
2. **Attribute formula `state.attribute`**: Resolves to main sensor attribute
3. **Circular reference detection**: Prevents infinite loops
4. **Self-reference detection**: Prevents attributes referencing themselves
5. **Linear attribute chains**: Allows valid attribute-to-attribute references

## Variable Injection Rules

### Explicit Variable Definition

All variables used in formulas must be explicitly defined by the user but sensor key references are updated by the cross sensor
reference implementation to the proper sensor entity_id after it is known through HA registration.

### Cross-Sensor Reference Replacement Strategy

The cross-sensor reference implementation replaces any reference to the main sensor key with the post-HA registration sensor
entity_id wherever the original reference (to either the sensor key or the sensor's entity_id, if defined in the yaml, was
placed.

**Critical Implementation Insight**: Cross-sensor variable resolution correctly updates variables to use HA-assigned entity IDs
rather than original sensor keys. This ensures that cross-sensor references remain valid after entity registration, even when
collision resolution occurs and entities receive different entity IDs than originally specified.

#### Self-Reference in Attributes: State Token vs Entity ID

When an attribute formula references its own parent sensor, the system uses the `state` token instead of the `entity_id` to
ensure consistent evaluation within the current update cycle:

**Why Use State Token for Self-References:**

1. **Post-Evaluation State Access**: The `state` token in attributes resolves to the main sensor's post-evaluation state (the
   calculated result from the current update cycle), not the pre-evaluation state from the HA state machine.

2. **Update Cycle Consistency**: Using `entity_id` would re-fetch the sensor's state from HA, which could be the previous
   evaluation result rather than the current cycle's calculated value.

3. **Avoiding Stale Data**: The `state` token ensures attributes use the most current calculated value from the same evaluation
   cycle, preventing inconsistencies between the main sensor and its attributes.

**Example:**

```yaml
sensors:
  power_analyzer:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity = 1000W
    formula: state * 1.1 # Main result = 1100W (current cycle)
    attributes:
      # CORRECT: Uses state token for self-reference
      daily_power:
        formula: state * 24 # Uses 1100W (current cycle result)
        metadata:
          unit_of_measurement: W

      # INCORRECT: Would use entity_id (could be stale)
      # daily_power:
      #   formula: sensor.power_analyzer * 24 # Could use previous cycle result
      #   metadata:
      #     unit_of_measurement: W
```

**Implementation Details:**

- **Cross-Sensor Sensor Set Reference Resolution**: References within a sensor to other sensor keys within the same sensor set
  are replaced with the actual entity IDs assigned by HA upon registration. This ensures that HA uniqueness guarantees are
  honored.
- **Self-Reference Replacement**: References to either the same sensor's sensor key or entity_id field are replaced with the
  `state` token in ALL contexts (main formulas, attributes, variables, dependencies). The `state` token reference resolves to
  the sensor state within the same update cycle instead of requiring HA state machine lookups, preventing stale data and
  ensuring evaluation consistency. Variables are aliases, so self-references in variables also resolve to `state`.
- **State Token Resolution Context**:
  - **Main Formulas**: `state` resolves to backing entity state (if present) or pre-evaluation sensor state (pure calculation)
  - **Attributes**: `state` resolves to the main sensor's post-evaluation result
  - **No Circular References**: State token always refers to different evaluation phases, preventing circular dependencies
- **Entity ID Resolution**: Direct entity ID references to other sensors fetch from HA state machine.
- **Entity ID Field Updates**: When a sensor is registered, the actual entity_id that HA assigns is recorded and applied to the
  entity_id field, updating any existing entity_id in the YAML configuration or adding the entity_id field if not originally
  present. This update ensures that YAML exports always reflect current HA reality while sensor keys remain as user-friendly
  metadata and shorthand references within the same sensor set.
- **YAML Export Format**:
  - **Dictionary Keys**: Original sensor keys (preserved as metadata and user-friendly references)
  - **entity_id Fields**: HA-assigned entity IDs (current reality for accurate downstream references)
- **Storage Persistence**: Entity ID field updates persist to storage and YAML exports to maintain data accuracy.

**Design Decision**: YAML exports include HA-assigned entity_ids for ALL sensors, including those that didn't originally specify
an entity_id. This ensures that exported YAML reflects the current system state and enables reliable sensor referencing for
subsequent CRUD operations.

### Example: YAML Export Format After HA Registration

```yaml
# Original YAML (BEFORE HA registration):

sensors:
  base_power_sensor:                  # Sensor A - Original sensor key
    entity_id: sensor.base_power      # Optional original entity_id hint
    formula: base_power_sensor * 1.1  # Self-reference by sensor key
    attributes:
      daily_power:
        formula: base_power_sensor * 24  # Self-reference in attribute
      efficiency_rating:
        formula: my_ref * scale_factor   # Uses variables with self-reference
        variables:
          my_ref: base_power_sensor      # Self-reference in variable
          scale_factor: 0.95

  efficiency_calc:                    # Sensor B - Original sensor key
    formula: base_power_sensor * 0.85 # Cross-sensor reference to Sensor A
    attributes:
      power_comparison:
        formula: efficiency_calc + base_power_sensor  # Self + cross reference
        variables:
          other_power: base_power_sensor              # Cross-sensor reference in variable

# YAML Export (AFTER HA registration and cross-sensor resolution):
sensors:
  base_power_sensor:                  # Sensor A - Key preserved (metadata/reference)
    entity_id: sensor.base_power_sensor_2   # HA-assigned entity_id (reality)
    formula: state * 1.1              # Self-reference → 'state'
    attributes:
      daily_power:
        formula: state * 24           # Self-reference → 'state'
      efficiency_rating:
        formula: my_ref * scale_factor   # Formula unchanged
        variables:
          my_ref: state               # Self-reference → 'state'
          scale_factor: 0.95          # Non-reference unchanged

  efficiency_calc:                    # Sensor B - Key preserved (metadata/reference)
    entity_id: sensor.efficiency_calc_3     # HA-assigned entity_id (reality)
    formula: sensor.base_power_sensor_2 * 0.85  # Cross-reference → HA entity_id
    attributes:
      power_comparison:
        formula: state + sensor.base_power_sensor_2  # Self → 'state', Cross → HA entity_id
        variables:
          other_power: sensor.base_power_sensor_2    # Cross-reference → HA entity_id
```

**Key Points**:

- **Sensor keys**: Preserved as dictionary keys for user reference and metadata
- **entity_id fields**: Updated with actual HA-assigned values for accuracy
- **Self-references** (within same sensor): Replaced with `state` token in ALL contexts
  - Sensor A referring to itself: `base_power_sensor` → `state`
  - Variables, dependencies, attributes: All self-references become `state`
- **Cross-sensor references** (between different sensors): Replaced with HA-assigned entity IDs
  - Sensor B referring to Sensor A: `base_power_sensor` → `sensor.base_power_sensor_2`
  - Maintains proper HA entity resolution and dependency tracking
- **Collision Resolution**: Entity ID collisions are automatically handled by HA's entity registry (e.g., `sensor.base_power` →
  `sensor.base_power_2` when collision occurs). All cross-sensor references are updated to use the final collision-resolved
  entity IDs.

```yaml
sensors:
  # Example: Explicit variable definition
  energy_cost_analysis:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity
    formula: state * 0.25 # Main formula
    attributes:
      daily_projection:
        formula: state * 24 # Uses main sensor result via state token
        metadata:
          unit_of_measurement: cents
      custom_calculation:
        formula: main_sensor_result * scale_factor # Uses explicit variables
        variables:
          main_sensor_result: state # Self-reference resolved to 'state' token
          scale_factor: 1.5
        metadata:
          unit_of_measurement: scaled_units
```

**Safety**: Explicit variable definition prevents naming conflicts and makes formulas self-documenting.

### Inherited Variables

Attributes inherit all variables from the parent sensor:

```yaml
sensors:
  # Example: Variable inheritance in attributes
  power_efficiency:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity
    formula: current_power * efficiency_factor / 100
    variables:
      current_power: sensor.span_panel_instantaneous_power # Inherited by attributes
      efficiency_factor: input_number.efficiency_factor # Inherited by attributes
    attributes:
      daily_efficiency:
        formula: current_power * efficiency_factor * 24 # Uses inherited variables
        metadata:
          unit_of_measurement: W
      # Available variables in attributes:
      # - current_power (inherited from parent)
      # - efficiency_factor (inherited from parent)
```

**Available Variables**: `current_power`, `efficiency_factor` (both inherited from parent sensor)

## Error Handling

### Backing Entity Resolution Errors

When a backing entity cannot be resolved:

```python
class BackingEntityResolutionError(MissingDependencyError):
    """Backing entity for state token cannot be resolved."""
```

**Integration Responsibilities**:

- The integration is responsible for properly constructing sensor definitions and ensuring that references to other entities are
  valid
- When registering backing entities, the integration must provide at least one dictionary entry for any backing entities that
  are registered
- The integration should handle the case where initial data in backing entities may not be fully populated during startup

**Package Validation Requirements**:

- The synthetic package validates that backing entity registrations provide at least one dictionary entry
- Debug logging indicates how many backing entities were registered (including sensor key and backing entity_id)
- If backing entities were provided but no entries exist, this condition is a fatal error and an appropriate exception is raised
- If backing entities were provided, their values may be None and the package treats these None entries as `STATE_NONE` (Python
  None) to allow for integration initialization

**Triggers**:

- Main formula uses `state` token but backing entity is not registered (no mapping exists)
- Direct self-reference to sensor's `entity_id` fails to resolve (no mapping exists)
- Backing entity registration is provided but contains no dictionary entries
- Backing entity exists but returns invalid data

**Behavior**: Exception is raised and propagated (not converted to error result). Note: If a mapping exists but the value is
None, this is treated as a transient condition and no exception is raised - the None value can be handled by alternate state
handlers if defined.

```yaml
sensors:
  # Example: Missing backing entity (will cause BackingEntityResolutionError)
  problematic_sensor:
    entity_id: sensor.nonexistent_entity # Entity doesn't exist
    formula: state * 2 # 'state' cannot be resolved
    # Result: BackingEntityResolutionError is raised

  # Example: Valid backing entity with None value (handled by alternate state handler)
  valid_sensor_with_none:
    entity_id: sensor.span_panel_instantaneous_power # Entity exists but value is None
    formula: state * 2 # 'state' resolves to None
    alternate_states:
      NONE: 0 # Handle None values by returning 0
    # Result: Formula evaluates with value 0, allowing for integration initialization

  # Example: Valid backing entity with populated value
  valid_sensor:
    entity_id: sensor.span_panel_instantaneous_power # Entity exists with value
    formula: state * 2 # 'state' resolves to backing entity value
    # Result: Formula evaluates successfully
```

### Missing Entity Errors

For general missing entity references:

```python
class MissingDependencyError(Exception):
    """Required entity or variable is missing."""
```

**Triggers**:

- Entity ID in formula cannot be resolved
- Variable reference fails
- Attribute-to-attribute reference fails

**Behavior**: Exception is raised and propagated

### Critical Distinction: Missing Dependencies vs Special State Values

The system makes a critical distinction between two scenarios:

#### 1. Missing Dependencies (Fatal)

- **Definition**: Entity doesn't exist in Home Assistant

- **Behavior**: Raises `MissingDependencyError` (fatal, stops evaluation)

- **Example**: `sensor.nonexistent_entity` in formula when entity doesn't exist

#### 2. Special State Values (Handled by Alternate State Handlers)

- **Definition**: Entity exists but has special state value (`None`, `"unknown"`, `"unavailable"`)
- **Behavior**: Triggers alternate state handlers if defined
- **Example**: `sensor.existing_entity` exists but returns `None` or `"unknown"`

```yaml
sensors:
  # Example: Missing entity (fatal error)
  problematic_sensor:
    entity_id: sensor.span_panel_instantaneous_power
    formula: sensor.nonexistent_entity * 2 # Entity doesn't exist
    # Result: MissingDependencyError is raised (fatal)

  # Example: Entity with special state (handled by alternate state handlers)
  valid_sensor_with_special_state:
    entity_id: sensor.span_panel_instantaneous_power
    formula: sensor.existing_but_unknown * 2 # Entity exists but returns "unknown"
    alternate_states:
      UNKNOWN: 0 # Handle unknown state by returning 0
    # Result: Formula evaluates with value 0
```

```yaml
sensors:
  # Example: Missing entity reference (will cause MissingDependencyError)
  problematic_sensor:
    entity_id: sensor.span_panel_instantaneous_power
    formula: sensor.nonexistent_entity * 2 # Entity doesn't exist
    # Result: MissingDependencyError is raised

  # Example: Missing variable reference
  another_problematic_sensor:
    entity_id: sensor.span_panel_instantaneous_power
    formula: external_power * 2 # Variable not defined
    # Result: MissingDependencyError is raised

  # Example: Valid entity and variable references
  valid_sensor:
    entity_id: sensor.span_panel_instantaneous_power
    formula: state * 2 # Valid backing entity reference
    variables:
      external_power: sensor.external_power # Valid variable
    # Result: Formula evaluates successfully
```

### Data Validation Errors

When data providers return invalid data:

```python
class DataValidationError(Exception):
    """Data provider returned invalid data."""
```

**Triggers**:

- Data provider returns `None`

### Alternate State Handler Processing

The synthetic sensor package uses a comprehensive alternate state handler system to process HA state values and evaluation
exceptions, providing flexible and user-defined handling instead of automatic conversion to `STATE_UNKNOWN`.

#### Two-Phase Processing System

The system implements two trigger points for alternate state handlers:

1. **Early Detection**: Single variables with alternate states are detected during variable resolution phase
2. **Post-Evaluation Processing**: Results and exceptions containing alternate states trigger handlers after formula evaluation

#### Exception-to-State Mapping

Evaluation exceptions are intelligently mapped to appropriate alternate states:

- **Missing dependencies** → `MissingDependencyError` (fatal, stops evaluation)
- **`"undefined"` or `"not defined"`** → `unavailable` (entity not available)
- **`"unavailable"`** → `unavailable`
- **`"unknown"`** → `unknown`
- **Other evaluation exceptions** → `STATE_NONE` (triggers alternate state handlers)

#### Handler Priority System

Alternate state handlers follow a priority order:

1. **Specific handlers** (none/unknown/unavailable) - highest priority
2. **FALLBACK handler** - catch-all for any alternate state
3. **Final fallback** - none → unavailable → unknown (if no specific handlers defined)

#### Examples of Alternate State Handler Usage

```yaml
sensors:
  # Example: Handling unavailable entity with fallback
  power_monitor:
    variables:
      offline_sensor: sensor.offline_sensor # Entity state = "unavailable"
    formula: offline_sensor + 10
    alternate_states:
      FALLBACK: 100 # Return 100 when dependencies are unavailable
    # Result: value = 100 (from fallback handler)

  # Example: Specific handlers for different states
  energy_calculator:
    variables:
      power_sensor: sensor.power_meter # Entity state = "unknown"
    formula: power_sensor * 2
    alternate_states:
      UNKNOWN: 50 # Handle unknown state
      UNAVAILABLE: 0 # Handle unavailable state
      NONE: None # Preserve None for energy sensors
    # Result: value = 50 (from unknown handler)

  # Example: Object-form handler with variables
  complex_calc:
    variables:
      missing_sensor: sensor.missing # Entity doesn't exist
    formula: missing_sensor * scale_factor
    alternate_states:
      UNAVAILABLE:
        formula: backup_value * scale_factor
        variables:
          backup_value: 200
          scale_factor: 1.5
    # Result: value = 300 (from object-form handler)
```

#### Circular Dependency Protection

The system includes circular dependency detection for alternate state handlers:

```yaml
# This configuration will cause a CircularDependencyError:
alternate_state_handler:
  none: "STATE_NONE"      # none → none (circular!)
  fallback: "STATE_UNKNOWN"

# This configuration is valid:
alternate_state_handler:
  none: 0                 # none → 0 (valid)
  fallback: 100           # fallback → 100 (valid)
```

#### STATE_NONE YAML Constant

The system supports a special YAML constant for None values:

```yaml
alternate_state_handler:
  none: "STATE_NONE" # YAML constant that converts to Python None
  # Equivalent to:
  # none: null
```

This is particularly useful for energy sensors that need to preserve `None` values.

#### State Constants

The system uses specific constants for state values:

- **`STATE_NONE`**: Python `None` (internal representation)
- **`STATE_UNKNOWN`**: String `"unknown"` (entity exists but has no current value)
- **`STATE_UNAVAILABLE`**: String `"unavailable"` (entity exists but is temporarily unavailable)

**Important**: These constants should be used instead of raw strings in code. The system automatically handles conversion
between YAML representation and internal Python values.

## Integration Responsibilities and Backing Entity Registration

### Integration Startup and Initialization

Integrations that use synthetic sensors must properly manage backing entity registration and initialization:

#### Backing Entity Registration Requirements

When an integration registers backing entities with the synthetic sensor package:

```python
# Example: Proper backing entity registration
backing_entities = {
    "sensor.span_panel_instantaneous_power": 1000.0,  # Valid entry with value
    "sensor.span_panel_voltage": None,  # Valid entry with None (treated as "unavailable")
    # Must provide at least one dictionary entry
}

# Invalid registration (will cause fatal error):
# backing_entities = {}  # Empty dictionary - fatal error
```

**Validation Rules**:

1. **Minimum Entry Requirement**: At least one dictionary entry must be provided for any backing entities that are registered
2. **None Value Handling**: None values can be handled by alternate state handlers to allow for integration initialization
3. **Debug Logging**: The package logs how many backing entities were registered, including sensor key and backing entity_id
4. **Fatal Error**: If backing entities were provided but no entries exist, a fatal exception is raised

#### Integration Initialization Patterns

```yaml
# Example: Integration startup pattern with backing entities
sensors:
  power_analyzer:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity
    formula: "state * 1.1" # May initially resolve to None if backing entity is None
    alternate_state_handler:
      none: 0 # Handle None values during initialization
    metadata:
      unit_of_measurement: W
    # During integration startup:
    # 1. Backing entity is registered with None value
    # 2. Formula evaluates with 0 result (from none handler)
    # 3. Integration later updates backing entity with actual value
    # 4. Formula evaluates with actual value
```

#### Debug Logging Output

The synthetic package provides debug logging for backing entity registration:

```python
DEBUG: Registered 3 backing entities:
  - sensor_key: power_analyzer, entity_id: sensor.span_panel_instantaneous_power
  - sensor_key: voltage_monitor, entity_id: sensor.span_panel_voltage
  - sensor_key: current_tracker, entity_id: sensor.span_panel_current
```

### Error Scenarios and Handling

#### Fatal Error: Empty Backing Entity Registration

```python
# This will cause a fatal error:
backing_entities = {}  # Empty dictionary
# Result: Fatal exception raised - backing entities provided but no entries exist
```

#### Valid Scenario: None Values During Initialization

```python
# This is valid during integration startup:
backing_entities = {
    "sensor.span_panel_instantaneous_power": None,  # Can be handled by alternate state handlers
}
# Result: Formula evaluates with handler-defined value, allowing for later population
```

#### Valid Scenario: Populated Values

```python
# This is valid with populated data:
backing_entities = {
    "sensor.span_panel_instantaneous_power": 1000.0,  # Actual value
}
# Result: Formula evaluates with actual value
```

### Backing Entity Resolution: Fatal vs. Transient Conditions

The package distinguishes between two critical scenarios when resolving backing entities:

#### Scenario 1: No Mapping Exists (Fatal Error)

When the package tries to resolve a backing entity but no mapping exists in the registration:

```python
# Integration registers backing entities:
backing_entities = {
    "sensor.span_panel_instantaneous_power": 1000.0,
    # Missing: "sensor.span_panel_voltage" - no mapping exists
}

# Sensor configuration:
sensors:
  voltage_analyzer:
    entity_id: sensor.span_panel_voltage  # No mapping exists for this entity
    formula: state * 1.1  # Cannot resolve 'state'
    # Result: BackingEntityResolutionError is raised (FATAL ERROR)
```

**Behavior**: `BackingEntityResolutionError` is raised immediately - this is a fatal error that indicates a configuration
problem.

#### Scenario 2: Mapping Exists but Value is None (Transient Condition)

When a mapping exists for the backing entity but the value is None:

```python
# Integration registers backing entities:
backing_entities = {
    "sensor.span_panel_instantaneous_power": 1000.0,
    "sensor.span_panel_voltage": None,  # Mapping exists but value is None
}

# Sensor configuration:
sensors:
  voltage_analyzer:
    entity_id: sensor.span_panel_voltage  # Mapping exists but value is None
    formula: "state * 1.1"  # 'state' resolves to "unknown" (None treated as STATE_UNKNOWN)
    # Result: Formula evaluates with "unknown" value (NO EXCEPTION)
```

**Behavior**: The None value can be handled by alternate state handlers, formula evaluation continues, and no exception is
raised. This allows for integration initialization where data may not be immediately available.

#### Key Distinction Summary

| Condition               | Mapping Exists | Value  | Result                     | Exception                      |
| ----------------------- | -------------- | ------ | -------------------------- | ------------------------------ |
| **Fatal Error**         | ❌ No          | N/A    | Cannot resolve             | `BackingEntityResolutionError` |
| **Transient Condition** | ✅ Yes         | `None` | Can be handled by handlers | No exception                   |

This distinction is crucial for integration development:

- **Fatal errors** indicate configuration problems that must be fixed
- **Transient conditions** allow for graceful handling of initialization periods where None values can be handled by alternate
  state handlers

## Code Standards

- Use Strict Type Checks - Avoid the use of Any types wherever possible
- When crafting new code or refactoring use proper type annotation initally to avoid later linter work
- Run formatters like Ruff, Pylint, Mypy and resolve any errors.
- Do not accept complexity overrides - refactor using the layered design and compiler-like phased approach
- Place imports at the top of the file, not in the middle of the file or within methods or classes
- Tests are excluded from linting, mypy, and import placement rules

## Layered Architecture and Compiler-Like Formula Evaluation

The synthetic sensor package implements a layered, compiler-like multi-phase approach to formula evaluation, ensuring clean
separation of concerns and extensible architecture. This design follows the principle of single responsibility and enables
independent testing, maintenance, and extension of each layer.

### Architectural Layers

The evaluation system is organized into distinct layers, each with a specific responsibility:

#### Layer 1: Variable Resolution Engine

**Purpose**: Complete resolution of all variable references in formulas **Location**: `evaluator_phases/variable_resolution/`
**Components**:

- `VariableResolutionPhase`: Main orchestration phase
- `VariableResolverFactory`: Factory for managing specialized resolvers
- `StateAttributeResolver`: Handles `state.voltage` → `240.0`
- `EntityReferenceResolver`: Handles `sensor.temperature` → `23.5`
- `CrossSensorReferenceResolver`: Handles `base_power_sensor` → `1000.0`
- `ConfigVariableResolver`: Handles direct values and entity references

#### Layer 2: Dependency Management System (Planned)

**Purpose**: Analysis, validation, and management of formula dependencies **Location**:
`evaluator_phases/dependency_management/` (future) **Components**:

- `DependencyManagementPhase`: Main orchestration phase
- `DependencyExtractor`: Extracts dependencies from formulas
- `DependencyValidator`: Validates dependency availability
- `CircularReferenceDetector`: Prevents circular dependencies

#### Layer 3: Context Building Engine (Planned)

**Purpose**: Construction and management of evaluation contexts **Location**: `evaluator_phases/context_building/` (future)
**Components**:

- `ContextBuildingPhase`: Main orchestration phase
- `EntityContextBuilder`: Builds entity-based contexts
- `VariableContextBuilder`: Builds variable-based contexts
- `SensorRegistryContextBuilder`: Builds cross-sensor contexts

#### Layer 4: Pre-Evaluation Processing (Complete)

**Purpose**: Pre-evaluation checks and validation **Location**: `evaluator_phases/pre_evaluation/` **Components**:

- `PreEvaluationPhase`: Main orchestration phase
- `CircularReferenceValidator`: Early circular reference detection (Phase 0)
- `StateTokenValidator`: Validates state token resolution
- `CircuitBreakerChecker`: Manages circuit breaker logic
- `CacheChecker`: Handles cache validation

#### Layer 5: Cross-Sensor Reference Management (Complete)

**Purpose**: Management of cross-sensor references and registry **Location**: `evaluator_phases/sensor_registry/`
**Components**:

- `SensorRegistryPhase`: Main orchestration phase
- `SensorRegistrar`: Registers sensors in the registry
- `SensorValueUpdater`: Updates sensor values
- `CrossReferenceResolver`: Resolves cross-sensor references

### Compiler-Like Formula Evaluation Architecture

The synthetic sensor package implements a compiler-like multi-phase approach to formula evaluation, ensuring clean separation of
concerns and extensible handler architecture.

### Evaluation Phases

#### Phase 0: Early Circular Reference Detection (Critical First Step)

Circular references are detected and rejected immediately before any dependency resolution or entity resolution attempts:

1. **Self-Reference Detection**: Attributes referencing themselves (e.g., `attr1: attr1 * 1.1`)
2. **Attribute-to-Attribute Cycles**: Circular dependencies between attributes within the same sensor
3. **Early Rejection**: Circular references cause immediate `CircularDependencyError` - no further processing occurs
4. **Fatal Error**: Circular references are treated as fatal errors that stop evaluation completely

This phase ensures that impossible configurations are rejected early, preventing wasted processing on formulas that can never be
resolved.

#### Phase 1: Complete Reference Resolution

All references in formulas are fully resolved before evaluation begins:

1. **State Attribute References**: `state.voltage` → `240.0`
2. **Entity References**: `sensor.temperature` → `23.5`
3. **Cross-Sensor References**: `base_power_sensor` → `1000.0`
4. **Variable References**: `efficiency_factor` → `0.95`

This phase ensures that all dependencies are resolved and no lazy evaluation occurs during the computation phase.

#### Phase 2: Handler Routing and Evaluation

Formulas are routed to appropriate handlers based on content analysis:

1. **String Handler**: Processes string literals for attributes only
   - Examples: `attribute: "tab [30,32]"` → `"tab [30,32]"`
   - Handles string literals in attribute configurations
   - **Note**: Currently limited to string literals only. Future enhancements will support string concatenation and evaluation.

2. **Numeric Handler**: Processes mathematical expressions using SimpleEval
   - Examples: `240.0 * 4.17 * 0.95` → `950.76`
   - Handles all mathematical operations and functions including collection functions (`sum()`, `avg()`, `max()`, `min()`,
     `count()`)

3. **Boolean Handler**: Processes logical expressions
   - Examples: `state > 1000` → `True`
   - Handles comparison operations and logical operators

#### Phase 3: Result Validation and Caching

Results are validated against expected types and cached for performance:

1. **Type Validation**: Ensures results match expected data types
2. **Cache Storage**: Stores results for subsequent evaluations
3. **Error Propagation**: Handles and reports evaluation errors

### Extensible Handler Architecture

The evaluation system is designed with extensible handlers that can be added or composed as needed:

#### Handler Composition

Handlers can include other handlers to create complex evaluation chains:

```python
# Example: Text pattern handler that delegates to numeric handler
class TextPatternHandler:
    def evaluate(self, formula: str) -> float | str:
        if self._contains_pattern(formula):
            # Extract numeric component and delegate to numeric handler
            numeric_part = self._extract_numeric(formula)
            return self._numeric_handler.evaluate(numeric_part)
        else:
            # Handle as pure text
            return self._text_handler.evaluate(formula)
```

#### Handler Registration

New handlers can be registered to extend formula evaluation capabilities:

```python
# Example: Adding a date/time handler
evaluator.register_handler("datetime", DateTimeHandler())
evaluator.register_handler("text_pattern", TextPatternHandler())
```

#### Handler Routing Logic

The system automatically routes formulas to appropriate handlers:

```python
def _route_formula_to_handler(self, formula: str) -> Handler:
    if self._is_string_formula(formula):
        return self._string_handler
    elif self._is_boolean_formula(formula):
        return self._boolean_handler
    else:
        return self._numeric_handler
```

### Cross-Sensor Reference Support

The system maintains a registry of all sensors and their current values, enabling cross-sensor references. The cross-sensor
reference functionality is now fully implemented and operational.

#### Sensor Registry

```python
# Registry structure (implemented)
self._sensor_registry: dict[str, float | str | bool] = {}
self._sensor_entity_id_mapping: dict[str, str] = {}
```

#### Cross-Sensor Evaluation

Sensors can reference other sensors by name with automatic dependency management:

```yaml
sensors:
  base_power_sensor:
    entity_id: sensor.span_panel_instantaneous_power
    formula: state * 1.0 # 1000W

  derived_power_sensor:
    entity_id: sensor.span_panel_instantaneous_power
    formula: base_power_sensor * 1.1 # 1100W (references base_power_sensor)
```

**Features**:

- **Automatic Registration**: Sensors are registered in cross-sensor registry
- **Dependency Analysis**: Cross-sensor dependencies are automatically detected
- **Evaluation Order**: Sensors are evaluated in correct dependency order
- **Circular Detection**: Circular dependencies are detected and reported
- **Value Updates**: Cross-sensor registry is updated after each evaluation
- **Error Handling**: Comprehensive error handling and validation

**Quality Assurance**:

- **Continuous Testing**: Run tests after each implementation step
- **Code Review**: Follow established coding standards
- **Documentation**: Update documentation as implementation progresses
- **Validation**: Validate against existing test suites

### Integration Approach

## Testing and Entity Registry Mocking

### Common Entity Registry Fixtures

When writing tests for synthetic sensors, it's critical to use the common entity registry fixtures provided in `conftest.py`
rather than manually patching the entity registry. This ensures consistent behavior across all tests.

**Correct Pattern**:

```python
async def test_sensor_functionality(self, mock_hass, mock_entity_registry, mock_states):
    """Test using common fixtures that provide proper entity registry mocking."""

    # Test implementation uses properly configured mock_entity_registry

```

**Incorrect Pattern** (leads to test failures):

```python
@patch("homeassistant.helpers.entity_registry.async_get")
async def test_sensor_functionality(self, mock_er_async_get, ...):
    """Manual patching breaks async method mocking."""

    # Manual entity registry setup that doesn't work with async methods
```

### Entity Index Tracking Behavior

**Key Insight**: The entity index correctly tracks both external entity references AND HA-assigned entity IDs of synthetic
sensors themselves. This means that after cross-sensor resolution, the entity index will contain more entities than just the
explicit external references.

**Expected Behavior**:

- External entity references (e.g., `sensor.power_meter`, `binary_sensor.grid_connected`)
- HA-assigned entity IDs of synthetic sensors (e.g., `sensor.power_efficiency`, `sensor.temperature_status`)
- Total count = external references + synthetic sensor entity IDs

### Test Expectation Updates

**Cross-Sensor Formula Resolution**: Tests should expect cross-sensor variables to reference HA-assigned entity IDs, not
original sensor keys:

```yaml
# Expected in test assertions AFTER cross-sensor resolution:
formula: "sum('device_class:power', !'sensor.kitchen_oven')" # HA-assigned entity ID
# NOT: "sum('device_class:power', !'kitchen_oven')"          # Original sensor key
```

This reflects the correct behavior where cross-sensor references are updated to use actual entity IDs for proper HA integration.

## Comprehensive Alternate State Handler System

The synthetic sensor package implements an alternate state handler system that provides user-defined handling of HA state values
and evaluation exceptions.

### System Overview

The alternate state handler system consists of:

1. **Two-Phase Processing**: Early detection during variable resolution and post-evaluation processing
2. **Exception Mapping**: Intelligent mapping of exceptions to appropriate alternate states
3. **Handler Priority**: Specific handlers take precedence over fallback handlers
4. **Circular Dependency Protection**: Detection and prevention of circular references
5. **STATE_NONE Support**: Special YAML constant for None values

This integration ensures that alternate state handlers work consistently across all sensor types and evaluation scenarios.

## Summary of Key Clarifications
