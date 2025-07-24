# State and Entity Reference Guide

This document describes the behavior of state and entity references in synthetic sensor formulas, including main formulas,
attributes, and attribute-to-attribute references.

## Overview

Synthetic sensors support multiple ways to reference entities and values within formulas. Understanding these reference
patterns is crucial for creating effective sensor configurations. The integration is responsible for properly constructing
sensor definitions and ensuring that references to other entities are valid, including the registration of backing entities
that may be in-memory objects.

These idioms define the fundamental rules and behaviors for state and entity references in synthetic sensor formulas. They
are the foundation for all formula evaluation and variable resolution in the package.

## Definitions

- The pre-evaluation state refers to the sensor's last calculated value from the previous evaluation cycle.
- A backing entity refers to synthetic sensor state represented in another object which could be an integration-owned object
  registered as a backing entity for the synthetic sensor or a reference in the formula of the synthetic sensor to an HA
  sensor. The integration is responsible for properly constructing sensor definitions and ensuring that references to other
  entities are valid. When an integration starts up, the initial data in backing entities may not be fully populated, but the
  registration of backing entities must be validated by the synthetic package such that a registration provides at least one
  dictionary entry for any backing entities that are registered. If backing entities were provided but no entries exist, this
  condition is a fatal error and an appropriate exception should be raised. If backing entities were provided, their values
  may be None and the package should treat these None entries as "unknown" to allow for the possibility that the integration
  has not fully initialized and will later populate the backing entity values.

## Home Assistant State Values

The synthetic sensor package handles special Home Assistant state values that represent the status of entities rather than
numeric or string data. These state values are treated as semantic states, not as string literals for formula evaluation.

### Standard HA State Values

The following state values are recognized and handled consistently throughout the package:

- **`"unknown"`**: Represents an entity that exists but has no current value (e.g., during integration initialization)
- **`"unavailable"`**: Represents an entity that exists but is temporarily unavailable (e.g., device offline)
- **`"None"`**: String representation that is converted to `"unknown"` for consistency

### State Value Handling Rules

1. **Consistent Casing**: All HA state values use lowercase (`"unknown"`, `"unavailable"`) for consistency
2. **Early Detection**: HA state values are detected during variable resolution phase, before formula evaluation begins
3. **Invalid Expression Prevention**: Expressions like `"unavailable" + 10` are invalid and are detected early to prevent
   formula evaluation errors
4. **State Reflection**: When a formula contains HA state values, the synthetic sensor immediately returns that state without
   attempting formula evaluation
5. **None Conversion**: `None` values from backing entities are treated as `"unknown"` to allow for integration
   initialization
6. **Enhanced Dependency Reporting**: Unavailable dependencies are reported with context including variable names and entity
   IDs

### Examples

```yaml
sensors:
  # Example: Backing entity with None value
  power_monitor:
    entity_id: sensor.panel_power # Entity exists but value is None
    formula: state * 2 # Resolves to "unknown" * 2
    # Result: Sensor state = "unknown" (not evaluated as formula)
    # unavailable_dependencies: ["source_value (sensor.panel_power) is unknown"]

  # Example: Entity with unavailable state
  temperature_sensor:
    entity_id: sensor.outdoor_temp # Entity state = "unavailable"
    formula: state + 5 # Resolves to "unavailable" + 5
    # Result: Sensor state = "unavailable" (not evaluated as formula)
    # unavailable_dependencies: ["source_value (sensor.outdoor_temp) is unavailable"]

  # Example: Invalid expression with HA state
  problematic_sensor:
    variables:
      offline_sensor: sensor.offline_sensor # Entity state = "unavailable"
    formula: offline_sensor + 10 # Resolves to "unavailable" + 10
    # Result: Sensor state = "unavailable" (invalid expression detected)
    # unavailable_dependencies: ["offline_sensor (sensor.offline_sensor) is unavailable"]

  # Example: Mixed state handling
  efficiency_calc:
    entity_id: sensor.panel_power # Entity state = "unknown"
    formula: sensor.working_power / state # Resolves to 1000 / "unknown"
    # Result: Sensor state = "unknown" (not evaluated as formula)
    # unavailable_dependencies: ["source_value (sensor.panel_power) is unknown"]
```

### Implementation Notes

- **Variable Resolution**: HA state values are detected during variable resolution phase using enhanced detection logic
- **Early Return**: When HA states are detected, the evaluator returns the state immediately, bypassing formula evaluation
- **Enhanced Dependency Tracking**: HA state values are tracked in `unavailable_dependencies` with format:
  `"variable_name (entity_id) is state_value"` for better debugging context
- **Entity Mapping**: Variable resolution tracks entity mappings to provide accurate entity IDs in dependency reporting
- **Integration Support**: This allows integrations to gracefully handle initialization periods and temporary unavailability
- **Architectural Integration**: HA state detection is integrated into the layered, compiler-like evaluation system
- **VariableResolutionResult**: Enhanced variable resolution returns structured results with HA state detection
- **Duplicate Prevention**: The system prevents duplicate dependency entries during variable resolution

## State and Entity Idioms

1. **Sensor Evaluation Order** The main sensor has two states - the pre-evaluation state and the post-evaluation state. The
   main sensor is evaluated before attributes are evaluated. A main sensor state cannot be circular to itself. References to
   the main sensor state (backing or external entities) are evaluated prior to any other evaluation. Attribute formulas are
   evaluated in dependency order, ensuring that all referenced values are available.
2. **Main Formula State Idiom** If a sensor has a resolvable backing entity, the `state` token in the main formula resolves
   to the current state of the backing entity. If the backing entity value is None, it is treated as "unknown" to allow for
   integration initialization. If there is no backing entity, `state` refers to the sensor's own pre-evaluation state.
3. **Attribute State Idiom** In attribute formulas, the `state` token always refers to the result of the main sensor's
   formula evaluation (i.e., the main sensor's calculated value after all variables and dependencies are resolved), never
   directly to the backing entity.
4. **Self-Reference Idiom** In main formulas, referencing the sensor by its key (e.g., `my_sensor`) or by its full entity ID
   (e.g., `sensor.my_sensor`) is equivalent to using the `state` token. All three resolve to the backing entity's state (if
   present) or the sensor's previous value (if not). If the backing entity value is None, it is treated as "unknown".
5. **Attribute Self-Reference Idiom** In attribute formulas, referencing the main sensor by its key or entity ID is
   equivalent to using the `state` token. All attribute forms resolve to the main sensor's calculated value
   (post-evaluation).
6. **State Reference Idiom** The main state can reference attributes but those attribute references are dereferenced prior to
   main sensor state evaluation. Attributes can reference other attributes within the same sensor by dot notation, i.e.,
   `state.myattribute`. These references are resolved in dependency order, and circular references (either with the main
   sensor state or to other attributes) are detected and prevented.
7. **Variable Inheritance Idiom** All variables defined in the parent sensor are automatically available in attribute
   formulas.
8. **Direct Entity Reference Idiom** Any formula can reference the state of any Home Assistant entity directly by its full
   entity ID (e.g., `sensor.some_entity`). This always resolves to the current state of that entity.
9. **Error Propagation Idiom** If a required entity or variable cannot be resolved, or if a data provider returns invalid
   data, a specific exception is raised (`BackingEntityResolutionError`, `MissingDependencyError`, or `DataValidationError`).
   Fatal errors are never silently converted to error results. However, None values from backing entities are treated as
   "unknown" rather than causing errors to allow for integration initialization.
10. **Consistent Reference Idiom** The same reference patterns (`state`, sensor key, entity ID) are supported in both main
    and attribute formulas, but their meaning is context-dependent (main formula = backing entity or previous value;
    attribute = main sensor's calculated value).

## Enhanced Dependency Reporting

The synthetic sensor package provides enhanced dependency reporting to improve debugging and monitoring capabilities. When
dependencies are unavailable or contain HA state values, the system reports detailed information including both variable
names and entity IDs.

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
  # Example: Backing entity with unknown state
  power_monitor:
    entity_id: sensor.panel_power # Entity exists but value is None
    formula: state * 2
    # Result:
    #   state: "unknown"
    #   unavailable_dependencies: ["source_value (sensor.panel_power) is unknown"]

  # Example: Variable reference with unavailable state
  efficiency_calc:
    variables:
      panel_power: sensor.panel_power # Entity state = "unavailable"
    formula: panel_power * 0.95
    # Result:
    #   state: "unavailable"
    #   unavailable_dependencies: ["panel_power (sensor.panel_power) is unavailable"]

  # Example: Multiple unavailable dependencies
  complex_calc:
    variables:
      power1: sensor.panel_power # Entity state = "unknown"
      power2: sensor.solar_power # Entity state = "unavailable"
    formula: power1 + power2
    # Result:
    #   state: "unknown" (first unavailable dependency determines state)
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
- **None Value Handling**: If the backing entity value is None, it is treated as "unknown" to allow for integration
  initialization
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

**Safety**: Using `state` is the recommended approach as it's completely safe and unambiguous. Entity ID self-references
require the entity to exist in Home Assistant.

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

All variables used in formulas must be explicitly defined by the user but sensor key references are updated by the cross
sensor reference implementation to the proper sensor entity_id after it is known through HA registration.

### Cross-Sensor Reference Replacement Strategy

The cross-sensor reference implementation replaces any reference to the main sensor key with the post-HA registration sensor
entity_id wherever the original reference (to either the sensor key or the sensor's entity_id, if defined in the yaml, was
placed.

#### Self-Reference in Attributes: State Token vs Entity ID

When an attribute formula references its own parent sensor, the system uses the `state` token instead of the `entity_id` to
ensure consistent evaluation within the current update cycle:

**Why Use State Token for Self-References:**

1. **Post-Evaluation State Access**: The `state` token in attributes resolves to the main sensor's post-evaluation state (the
   calculated result from the current update cycle), not the pre-evaluation state from the HA state machine.

2. **Update Cycle Consistency**: Using `entity_id` would re-fetch the sensor's state from HA, which could be the previous
   evaluation result rather than the current cycle's calculated value.

3. **Avoiding Stale Data**: The `state` token ensures attributes use the most current calculated value from the same
   evaluation cycle, preventing inconsistencies between the main sensor and its attributes.

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

- **Cross-Sensor Sensor Set Reference Resolution**: References within a sensor to other sensor keys within the same sensor
  set are replaced with the actual entity IDs assigned by HA upon registration. This ensures that HA uniqueness guarantees
  are honored.
- **Self-Reference Replacement**: References to either the same sensor's sensor key or entity_id field are replaced with the
  `state` token in ALL contexts (main formulas, attributes, variables, dependencies). The `state` token reference resolves to
  the sensor state within the same update cycle instead of requiring HA state machine lookups, preventing stale data and
  ensuring evaluation consistency. Variables are aliases, so self-references in variables also resolve to `state`.
- **State Token Resolution Context**:
  - **Main Formulas**: `state` resolves to backing entity state (if present) or pre-evaluation sensor state (pure
    calculation)
  - **Attributes**: `state` resolves to the main sensor's post-evaluation result
  - **No Circular References**: State token always refers to different evaluation phases, preventing circular dependencies
- **Entity ID Resolution**: Direct entity ID references to other sensors fetch from HA state machine.
- **Entity ID Field Updates**: When a sensor is registered, the actual entity_id that HA assigns is recorded and applied to
  the entity_id field, updating any existing entity_id in the YAML configuration or adding the entity_id field if not
  originally present. This update ensures that YAML exports always reflect current HA reality while sensor keys remain as
  user-friendly metadata and shorthand references within the same sensor set.
- **YAML Export Format**:
  - **Dictionary Keys**: Original sensor keys (preserved as metadata and user-friendly references)
  - **entity_id Fields**: HA-assigned entity IDs (current reality for accurate downstream references)
- **Storage Persistence**: Entity ID field updates persist to storage and YAML exports to maintain data accuracy.

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

- The integration is responsible for properly constructing sensor definitions and ensuring that references to other entities
  are valid
- When registering backing entities, the integration must provide at least one dictionary entry for any backing entities that
  are registered
- The integration should handle the case where initial data in backing entities may not be fully populated during startup

**Package Validation Requirements**:

- The synthetic package validates that backing entity registrations provide at least one dictionary entry
- Debug logging indicates how many backing entities were registered (including sensor key and backing entity_id)
- If backing entities were provided but no entries exist, this condition is a fatal error and an appropriate exception is
  raised
- If backing entities were provided, their values may be None and the package treats these None entries as "unknown" to allow
  for integration initialization

**Triggers**:

- Main formula uses `state` token but backing entity is not registered (no mapping exists)
- Direct self-reference to sensor's `entity_id` fails to resolve (no mapping exists)
- Backing entity registration is provided but contains no dictionary entries
- Backing entity exists but returns invalid data

**Behavior**: Exception is raised and propagated (not converted to error result). Note: If a mapping exists but the value is
None, this is treated as a transient condition and no exception is raised - the None value is converted to "unknown".

```yaml
sensors:
  # Example: Missing backing entity (will cause BackingEntityResolutionError)
  problematic_sensor:
    entity_id: sensor.nonexistent_entity # Entity doesn't exist
    formula: state * 2 # 'state' cannot be resolved
    # Result: BackingEntityResolutionError is raised

  # Example: Valid backing entity with None value (treated as "unknown")
  valid_sensor_with_none:
    entity_id: sensor.span_panel_instantaneous_power # Entity exists but value is None
    formula: state * 2 # 'state' resolves to "unknown" (None treated as "unknown")
    # Result: Formula evaluates with "unknown" value, allowing for integration initialization

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

### Invalid Expression Handling

The synthetic sensor package detects and handles invalid expressions that contain HA state values before they reach formula
evaluation.

#### Invalid Expression Detection

Expressions that contain HA state values are considered invalid and are detected during variable resolution:

```yaml
sensors:
  # Example: Invalid expression with HA state
  problematic_sensor:
    variables:
      offline_sensor: sensor.offline_sensor  # Entity state = "unavailable"
    formula: offline_sensor + 10  # Resolves to "unavailable" + 10
    # Result: Sensor state = "unavailable" (invalid expression detected)
    # unavailable_dependencies: ["offline_sensor (sensor.offline_sensor) is unavailable"]

  # Example: Invalid expression with quoted HA state
  another_problematic_sensor:
    formula: "unavailable" + 10  # Direct invalid expression
    # Result: Sensor state = "unavailable" (invalid expression detected)
    # unavailable_dependencies: []
```

#### Detection Rules

1. **Quoted HA States**: Expressions containing `"unknown"` or `"unavailable"` as string literals
2. **Unquoted HA States**: Expressions containing unquoted HA state values
3. **Mixed Expressions**: Any formula that would result in invalid mathematical operations with HA states

#### Behavior

- **Early Detection**: Invalid expressions are detected during variable resolution phase
- **State Reflection**: The sensor returns the appropriate HA state value immediately
- **No Formula Evaluation**: The formula is not evaluated to prevent mathematical errors
- **Enhanced Reporting**: Dependencies are reported with context for debugging

#### Examples of Invalid Expressions

```yaml
# These expressions are invalid and will return HA states:
formula: "unavailable" + 10        # Returns "unavailable"
formula: "unknown" * 2             # Returns "unknown"
formula: sensor.offline + 5        # Returns "unavailable" if sensor.offline is unavailable
formula: "unavailable" / 100       # Returns "unavailable"
formula: "unknown" - 50            # Returns "unknown"

# These expressions are valid:
formula: 100 + 200                 # Valid numeric expression
formula: sensor.online + 10        # Valid if sensor.online returns numeric value
formula: "valid_string"            # Valid string literal (for attributes)
```

## Integration Responsibilities and Backing Entity Registration

### Integration Startup and Initialization

Integrations that use synthetic sensors must properly manage backing entity registration and initialization:

#### Backing Entity Registration Requirements

When an integration registers backing entities with the synthetic sensor package:

```python
# Example: Proper backing entity registration
backing_entities = {
    "sensor.span_panel_instantaneous_power": 1000.0,  # Valid entry with value
    "sensor.span_panel_voltage": None,  # Valid entry with None (treated as "unknown")
    # Must provide at least one dictionary entry
}

# Invalid registration (will cause fatal error):
# backing_entities = {}  # Empty dictionary - fatal error
```

**Validation Rules**:

1. **Minimum Entry Requirement**: At least one dictionary entry must be provided for any backing entities that are registered
2. **None Value Handling**: None values are treated as "unknown" to allow for integration initialization
3. **Debug Logging**: The package logs how many backing entities were registered, including sensor key and backing entity_id
4. **Fatal Error**: If backing entities were provided but no entries exist, a fatal exception is raised

#### Integration Initialization Patterns

```yaml
# Example: Integration startup pattern with backing entities
sensors:
  power_analyzer:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity
    formula: state * 1.1 # May initially resolve to "unknown" if backing entity is None
    metadata:
      unit_of_measurement: W
    # During integration startup:
    # 1. Backing entity is registered with None value
    # 2. Formula evaluates with "unknown" result
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
    "sensor.span_panel_instantaneous_power": None,  # Will be treated as "unknown"
}
# Result: Formula evaluates with "unknown" value, allowing for later population
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
    formula: state * 1.1  # 'state' resolves to "unknown" (None treated as "unknown")
    # Result: Formula evaluates with "unknown" value (NO EXCEPTION)
```

**Behavior**: The None value is treated as "unknown", formula evaluation continues, and no exception is raised. This allows
for integration initialization where data may not be immediately available.

#### Key Distinction Summary

| Condition               | Mapping Exists | Value  | Result                | Exception                      |
| ----------------------- | -------------- | ------ | --------------------- | ------------------------------ |
| **Fatal Error**         | ❌ No          | N/A    | Cannot resolve        | `BackingEntityResolutionError` |
| **Transient Condition** | ✅ Yes         | `None` | Resolves to "unknown" | No exception                   |

This distinction is crucial for integration development:

- **Fatal errors** indicate configuration problems that must be fixed
- **Transient conditions** allow for graceful handling of initialization periods

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

The synthetic sensor package implements a compiler-like multi-phase approach to formula evaluation, ensuring clean separation
of concerns and extensible handler architecture.

### Evaluation Phases

#### Phase 0: Early Circular Reference Detection (Critical First Step)

Circular references are detected and rejected immediately before any dependency resolution or entity resolution attempts:

1. **Self-Reference Detection**: Attributes referencing themselves (e.g., `attr1: attr1 * 1.1`)
2. **Attribute-to-Attribute Cycles**: Circular dependencies between attributes within the same sensor
3. **Early Rejection**: Circular references cause immediate `CircularDependencyError` - no further processing occurs
4. **Fatal Error**: Circular references are treated as fatal errors that stop evaluation completely

This phase ensures that impossible configurations are rejected early, preventing wasted processing on formulas that can never
be resolved.

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
   - **Note**: Currently limited to string literals only. Future enhancements will support string concatenation and
     evaluation.

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

## Summary of Key Clarifications

This guide has been updated to reflect important clarifications and agreements from implementation discussions:

### HA State Value Handling

1. **Invalid Expressions**: Expressions like `"unavailable" + 10` are invalid and are detected early during variable
   resolution
2. **Early Detection**: HA state values are detected during variable resolution phase, before formula evaluation begins
3. **State Reflection**: When HA states are detected, the sensor immediately returns that state without attempting formula
   evaluation
4. **Enhanced Reporting**: Dependencies are reported with context: `"variable_name (entity_id) is state_value"`

### Enhanced Dependency Reporting

1. **Context-Rich Format**: Dependencies include both variable names and entity IDs for better debugging
2. **Entity Mapping**: Variable resolution tracks entity mappings to provide accurate entity IDs
3. **Duplicate Prevention**: The system prevents duplicate dependency entries
4. **Integration Support**: Enhanced reporting helps integrations manage entities directly

### Architectural Integration

1. **VariableResolutionResult**: Enhanced variable resolution returns structured results with HA state detection
2. **Layered Architecture**: HA state detection is integrated into the compiler-like evaluation system
3. **Early Return**: Evaluator handles early HA state returns from variable resolution
4. **Test Updates**: Test expectations updated to work with enhanced dependency reporting format

### Implementation Results

- **Test Improvement**: Reduced failures from 41 to 38, with 1250 tests passing (97% pass rate)
- **Enhanced Debugging**: Better context for troubleshooting dependency issues
- **Integration Support**: Improved entity management capabilities for integrations
- **Error Prevention**: Invalid expressions are caught early, preventing formula evaluation errors

These clarifications ensure that HA state values are handled consistently as semantic states rather than string literals,
providing better error prevention and enhanced debugging capabilities throughout the synthetic sensor package.
