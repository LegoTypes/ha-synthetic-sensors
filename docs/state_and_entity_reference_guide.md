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
  may be None and the package should treat these None entries as Unknown to allow for the possibility that the integration
  has not fully initialized and will later populate the backing entity values.

## State and Entity Idioms

1. **Sensor Evaluation Order** The main sensor has two states - the pre-evaluation state and the post-evaluation state. The
   main sensor is evaluated before attributes are evaluated. A main sensor state cannot be circular to itself. References to
   the main sensor state (backing or external entities) are evaluated prior to any other evaluation. Attribute formulas are
   evaluated in dependency order, ensuring that all referenced values are available.
2. **Main Formula State Idiom** If a sensor has a resolvable backing entity, the `state` token in the main formula resolves
   to the current state of the backing entity. If the backing entity value is None, it is treated as Unknown to allow for
   integration initialization. If there is no backing entity, `state` refers to the sensor's own pre-evaluation state.
3. **Attribute State Idiom** In attribute formulas, the `state` token always refers to the result of the main sensor's
   formula evaluation (i.e., the main sensor's calculated value after all variables and dependencies are resolved), never
   directly to the backing entity.
4. **Self-Reference Idiom** In main formulas, referencing the sensor by its key (e.g., `my_sensor`) or by its full entity ID
   (e.g., `sensor.my_sensor`) is equivalent to using the `state` token. All three resolve to the backing entity's state (if
   present) or the sensor's previous value (if not). If the backing entity value is None, it is treated as Unknown.
5. **Attribute Self-Reference Idiom** In attribute formulas, referencing the main sensor by its key or entity ID is
   equivalent to using the `state` token. All attribute forms resolve to the main sensor's calculated value
   (post-evaluation).
6. **State Reference Idiom** The main state can reference attributes but those attribute references are dereferenced prior to
   main sensor state evaluation. Attributes can reference other attributes within the same sensor by dot notation, i.e.,
   `state.myattribute`. These references are resolved in dependency order, and circular references (either with the main
   sensor state or to other attributes) are detected and prevented.
7. **Variable Inheritance Idiom** All variables defined in the parent sensor are automatically available in attribute
   formulas. Additionally, the main sensor's key is injected as a variable for use in attributes.
8. **Direct Entity Reference Idiom** Any formula can reference the state of any Home Assistant entity directly by its full
   entity ID (e.g., `sensor.some_entity`). This always resolves to the current state of that entity.
9. **Error Propagation Idiom** If a required entity or variable cannot be resolved, or if a data provider returns invalid
   data, a specific exception is raised (`BackingEntityResolutionError`, `MissingDependencyError`, or `DataValidationError`).
   Fatal errors are never silently converted to error results. However, None values from backing entities are treated as
   Unknown rather than causing errors to allow for integration initialization.
10. **Consistent Reference Idiom** The same reference patterns (`state`, sensor key, entity ID) are supported in both main
    and attribute formulas, but their meaning is context-dependent (main formula = backing entity or previous value;
    attribute = main sensor's calculated value).

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
- **None Value Handling**: If the backing entity value is None, it is treated as Unknown to allow for integration
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

Main formulas support three equivalent ways to reference the backing entity:

```yaml
sensors:
  # Example: Three equivalent ways to reference backing entity
  power_calculator:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity = 1000W
    # All three formulas produce the same result (2000W):
    formula: state * 2 # Method 1: State token
    # formula: power_calculator * 2       # Method 2: Sensor key (auto-injected)
    # formula: sensor.power_calculator * 2 # Method 3: Direct entity ID
    metadata:
      unit_of_measurement: W
```

**Note**: All three patterns resolve to the backing entity's state value when a backing entity is configured.

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

Attributes support the same three reference patterns as main formulas:

```yaml
sensors:
  # Example: Three equivalent ways to reference main sensor in attributes
  power_analyzer:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity = 1000W
    formula: state * 1.1 # Main result = 1100W
    attributes:
      # All three produce the same result (26400W):
      daily_power:
        formula: state * 24 # Method 1: State token
        metadata:
          unit_of_measurement: W
      weekly_power:
        formula: power_analyzer * 24 * 7 # Method 2: Sensor key (auto-injected)
        metadata:
          unit_of_measurement: W
      monthly_power:
        formula: sensor.power_analyzer * 24 * 30 # Method 3: Direct entity ID
        metadata:
          unit_of_measurement: W
```

**Note**: All three patterns in attributes resolve to the main sensor's calculated value (post-evaluation).

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

### Main Sensor Variables

For attributes, the config manager automatically injects the main sensor's entity ID as a variable:

```yaml
sensors:
  # Example: Automatic variable injection for attributes
  energy_cost_analysis:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity
    formula: state * 0.25 # Main formula
    attributes:
      daily_projection:
        formula: state * 24 # Uses main sensor result
        metadata:
          unit_of_measurement: cents
      # Auto-injected variable: energy_cost_analysis = sensor.energy_cost_analysis
      # This allows attributes to reference the main sensor's calculated value
```

**Injected Variable**: `energy_cost_analysis: sensor.energy_cost_analysis`

This allows attributes to reference the main sensor's calculated value using the sensor key.

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
      # - power_efficiency (auto-injected main sensor reference)
```

**Available Variables**: `current_power`, `efficiency_factor`, `power_efficiency` (main sensor reference)

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
- If backing entities were provided, their values may be None and the package treats these None entries as Unknown to allow
  for integration initialization

**Triggers**:

- Main formula uses `state` token but backing entity is not registered (no mapping exists)
- Direct self-reference to sensor's `entity_id` fails to resolve (no mapping exists)
- Backing entity registration is provided but contains no dictionary entries
- Backing entity exists but returns invalid data

**Behavior**: Exception is raised and propagated (not converted to error result). Note: If a mapping exists but the value is
None, this is treated as a transient condition and no exception is raised - the None value is converted to Unknown.

```yaml
sensors:
  # Example: Missing backing entity (will cause BackingEntityResolutionError)
  problematic_sensor:
    entity_id: sensor.nonexistent_entity # Entity doesn't exist
    formula: state * 2 # 'state' cannot be resolved
    # Result: BackingEntityResolutionError is raised

  # Example: Valid backing entity with None value (treated as Unknown)
  valid_sensor_with_none:
    entity_id: sensor.span_panel_instantaneous_power # Entity exists but value is None
    formula: state * 2 # 'state' resolves to Unknown (None treated as Unknown)
    # Result: Formula evaluates with Unknown value, allowing for integration initialization

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

## Integration Responsibilities and Backing Entity Registration

### Integration Startup and Initialization

Integrations that use synthetic sensors must properly manage backing entity registration and initialization:

#### Backing Entity Registration Requirements

When an integration registers backing entities with the synthetic sensor package:

```python
# Example: Proper backing entity registration
backing_entities = {
    "sensor.span_panel_instantaneous_power": 1000.0,  # Valid entry with value
    "sensor.span_panel_voltage": None,  # Valid entry with None (treated as Unknown)
    # Must provide at least one dictionary entry
}

# Invalid registration (will cause fatal error):
# backing_entities = {}  # Empty dictionary - fatal error
```

**Validation Rules**:

1. **Minimum Entry Requirement**: At least one dictionary entry must be provided for any backing entities that are registered
2. **None Value Handling**: None values are treated as Unknown to allow for integration initialization
3. **Debug Logging**: The package logs how many backing entities were registered, including sensor key and backing entity_id
4. **Fatal Error**: If backing entities were provided but no entries exist, a fatal exception is raised

#### Integration Initialization Patterns

```yaml
# Example: Integration startup pattern with backing entities
sensors:
  power_analyzer:
    entity_id: sensor.span_panel_instantaneous_power # Backing entity
    formula: state * 1.1 # May initially resolve to Unknown if backing entity is None
    metadata:
      unit_of_measurement: W
    # During integration startup:
    # 1. Backing entity is registered with None value
    # 2. Formula evaluates with Unknown result
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
    "sensor.span_panel_instantaneous_power": None,  # Will be treated as Unknown
}
# Result: Formula evaluates with Unknown value, allowing for later population
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
    formula: state * 1.1  # 'state' resolves to Unknown (None treated as Unknown)
    # Result: Formula evaluates with Unknown value (NO EXCEPTION)
```

**Behavior**: The None value is treated as Unknown, formula evaluation continues, and no exception is raised. This allows for
integration initialization where data may not be immediately available.

#### Key Distinction Summary

| Condition               | Mapping Exists | Value  | Result              | Exception                      |
| ----------------------- | -------------- | ------ | ------------------- | ------------------------------ |
| **Fatal Error**         | ❌ No          | N/A    | Cannot resolve      | `BackingEntityResolutionError` |
| **Transient Condition** | ✅ Yes         | `None` | Resolves to Unknown | No exception                   |

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

**Benefits**:

- Extracts ~200+ lines from evaluator
- Enables independent testing of variable resolution logic
- Supports future variable types (dates, times, etc.)
- Clear separation of resolution strategies

#### Layer 2: Dependency Management System (Planned)

**Purpose**: Analysis, validation, and management of formula dependencies **Location**:
`evaluator_phases/dependency_management/` (future) **Components**:

- `DependencyManagementPhase`: Main orchestration phase
- `DependencyExtractor`: Extracts dependencies from formulas
- `DependencyValidator`: Validates dependency availability
- `CircularReferenceDetector`: Prevents circular dependencies

**Benefits**:

- Extracts ~150+ lines from evaluator
- Centralized dependency analysis logic
- Improved error handling for missing dependencies
- Support for complex dependency graphs

#### Layer 3: Context Building Engine (Planned)

**Purpose**: Construction and management of evaluation contexts **Location**: `evaluator_phases/context_building/` (future)
**Components**:

- `ContextBuildingPhase`: Main orchestration phase
- `EntityContextBuilder`: Builds entity-based contexts
- `VariableContextBuilder`: Builds variable-based contexts
- `SensorRegistryContextBuilder`: Builds cross-sensor contexts

**Benefits**:

- Extracts ~100+ lines from evaluator
- Centralized context management
- Improved context validation
- Support for complex context scenarios

#### Layer 4: Pre-Evaluation Processing (Complete)

**Purpose**: Pre-evaluation checks and validation **Location**: `evaluator_phases/pre_evaluation/` **Components**:

- `PreEvaluationPhase`: Main orchestration phase
- `StateTokenValidator`: Validates state token resolution
- `CircuitBreakerChecker`: Manages circuit breaker logic
- `CacheChecker`: Handles cache validation

**Benefits**:

- Extracts ~80+ lines from evaluator
- Centralized pre-evaluation logic
- Improved error isolation
- Enhanced debugging capabilities

#### Layer 5: Cross-Sensor Reference Management (Complete)

**Purpose**: Management of cross-sensor references and registry **Location**: `evaluator_phases/sensor_registry/`
**Components**:

- `SensorRegistryPhase`: Main orchestration phase
- `SensorRegistrar`: Registers sensors in the registry
- `SensorValueUpdater`: Updates sensor values
- `CrossReferenceResolver`: Resolves cross-sensor references

**Benefits**:

- Extracts ~60+ lines from evaluator
- Centralized sensor registry management
- Improved cross-sensor reference handling
- Support for complex sensor networks

### Compiler-Like Formula Evaluation Architecture

The synthetic sensor package implements a compiler-like multi-phase approach to formula evaluation, ensuring clean separation
of concerns and extensible handler architecture.

### Evaluation Phases

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
   - Handles all mathematical operations and functions including collection functions (`sum()`, `avg()`, `max()`, `min()`, `count()`)

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

#### Current Implementation Status

**Phase 1 Complete**:

- ✅ `SensorRegistryPhase`: Registry management for cross-sensor references
- ✅ `CrossSensorReferenceResolver`: Variable resolution for cross-sensor references
- ✅ Variable resolution integration: Steps for cross-sensor reference resolution
- ✅ Sensor lifecycle integration: Automatic registration/updates in cross-sensor registry
- ✅ Value updates: Registry updates when sensor values change
- ✅ Test framework: Comprehensive tests passing

**Phase 2 Complete**:

- ✅ Evaluation order management: Cross-sensor dependency ordering
- ✅ Circular reference detection: For cross-sensor dependencies

**Phase 3 Pending**:

- 🔄 Enhanced variable resolution: Improved error handling and dependency tracking
- 🔄 Enhanced error messages: Better error reporting for cross-sensor reference issues

**Phase 4 Pending**:

- 🔄 Integration points: Additional integration points for sensor registration and evaluation loops
- 🔄 Advanced dependency analysis: Enhanced dependency analysis methods

#### Sensor Registry

```python
# Registry structure (implemented)
self._sensor_registry: dict[str, float | str | bool] = {}
self._sensor_entity_id_mapping: dict[str, str] = {}
```

#### Cross-Sensor Evaluation (Fully Implemented)

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

**Key Features**:

- ✅ **Automatic Registration**: Sensors are registered in cross-sensor registry
- ✅ **Dependency Analysis**: Cross-sensor dependencies are automatically detected
- ✅ **Evaluation Order**: Sensors are evaluated in correct dependency order
- ✅ **Circular Detection**: Circular dependencies are detected and reported
- ✅ **Value Updates**: Cross-sensor registry is updated after each evaluation
- ✅ **Error Handling**: Comprehensive error handling and validation

#### Implementation Plan

**Phase 1: Sensor Lifecycle Integration** ✅ **COMPLETE**

**Location**: `sensor_manager.py` integration with existing `SensorRegistryPhase`

**Status**: ✅ Fully implemented and integrated

**Phase 2: Evaluation Order Management** ✅ **COMPLETE**

**Location**: `CrossSensorDependencyManager` in `evaluator_phases/dependency_management/`

**Status**: ✅ Fully implemented and integrated

**Key Features Implemented**:

- ✅ Cross-sensor dependency analysis
- ✅ Topological sort for evaluation order
- ✅ Circular reference detection
- ✅ Dependency validation
- ✅ Integration with sensor manager

**Phase 3: Enhanced Variable Resolution** ✅ **COMPLETE**

**Location**: Update existing `CrossSensorReferenceResolver`

**Status**: ✅ Fully implemented and tested - Enhanced error handling and dependency tracking

**Implementation Plan**:

**3.1 Enhanced Error Handling**

- **Target**: `src/ha_synthetic_sensors/evaluator_phases/variable_resolution/cross_sensor_resolver.py`
- **Enhancements**:
  - Enhanced error messages with specific error types
  - Dependency validation before resolution
  - Improved error context and debugging information

**3.2 Dependency Tracking Integration**

- **New Methods**:
  - `_track_dependency_usage()`: Track dependency usage for debugging
  - `_validate_dependency_availability()`: Validate dependency availability
- **Enhanced Resolution Logic**:
  - Check if sensor exists but hasn't been evaluated yet
  - Provide specific error messages for different failure scenarios

**3.3 Enhanced Error Types**

- **New Exception Classes**:
  - `DependencyValidationError`: Cross-sensor dependency validation failed
  - `CrossSensorResolutionError`: Cross-sensor reference resolution failed

**Implementation Steps**:

1. Enhance error handling in `CrossSensorReferenceResolver`
2. Add dependency tracking methods
3. Create new exception classes
4. Update tests to validate enhanced error handling
5. Run linting and type checking

**Success Criteria**:

- ✅ Enhanced error messages for cross-sensor reference issues
- ✅ Dependency tracking and validation
- ✅ All tests pass (idioms, integration, dependency management)
- ✅ Ruff and mypy compliance
- ✅ No regression in existing functionality

**Phase 4: Integration Points** ✅ **COMPLETE**

**Status**: ✅ Fully implemented and tested - Enhanced integration points and advanced dependency analysis

**Implementation Plan**:

**4.1 Enhanced Sensor Registration**

- **Target**: `src/ha_synthetic_sensors/sensor_manager.py`
- **Enhancements**:
  - Register all sensors in cross-sensor registry first
  - Validate cross-sensor dependencies after registration
  - Enhanced error handling for registration failures

**4.2 Enhanced Evaluation Loop**

- **Target**: `src/ha_synthetic_sensors/sensor_manager.py`
- **Enhancements**:
  - Get evaluation order considering cross-sensor dependencies
  - Update cross-sensor registry immediately after evaluation
  - Handle cross-sensor resolution errors with appropriate logging

**4.3 Advanced Dependency Analysis**

- **New Methods**:
  - `_analyze_sensor_cross_dependencies()`: Analyze cross-sensor dependencies for specific sensor
  - `_validate_cross_sensor_dependencies()`: Validate all cross-sensor dependencies across sensor set
  - `_handle_cross_sensor_error()`: Handle cross-sensor resolution errors

**Implementation Steps**:

1. Enhance sensor registration with cross-sensor registry integration
2. Enhance evaluation loop with dependency management
3. Add advanced dependency analysis methods
4. Add error handling for cross-sensor resolution failures
5. Update tests to validate enhanced integration
6. Run linting and type checking

**Success Criteria**:

- ✅ Enhanced sensor registration with cross-sensor registry
- ✅ Enhanced evaluation loop with dependency management
- ✅ Advanced dependency analysis capabilities
- ✅ All tests pass (idioms, integration, dependency management)
- ✅ Ruff and mypy compliance
- ✅ No regression in existing functionality

**Implementation Strategy**:

1. **Step 1: Complete Lifecycle Integration** ✅ **COMPLETE**
   - ✅ Connect sensor registration to cross-sensor registry
   - ✅ Update registry values after each sensor evaluation
   - ✅ Add cross-sensor registry cleanup on sensor removal

2. **Step 2: Add Dependency Analysis** ✅ **COMPLETE**
   - ✅ Implement cross-sensor dependency detection in formulas
   - ✅ Create evaluation order calculator (topological sort)
   - ✅ Add circular reference detection for cross-sensor dependencies

3. **Step 3: Enhance Error Handling** ✅ **COMPLETE**
   - ✅ Improve error messages for missing cross-sensor references
   - ✅ Add validation for undefined sensor references
   - ✅ Handle evaluation order conflicts

4. **Step 4: Testing Integration** ✅ **COMPLETE**
   - ✅ Enable existing cross-sensor reference tests
   - ✅ Add comprehensive integration tests
   - ✅ Validate circular reference detection

**Phase 2 Summary**: All core cross-sensor reference functionality has been implemented and tested. The system now supports:

- Cross-sensor dependency analysis and evaluation order management
- Circular reference detection and validation
- Integration with sensor lifecycle and dependency management
- Comprehensive testing with passing test suites
- Full integration with the evaluator architecture

**Phase 3 & 4 Implementation Status**:

**Phase 3: Enhanced Variable Resolution** ✅ **COMPLETE**

- ✅ **Enhanced Error Handling**: Implemented specific exception types (`DependencyValidationError`, `CrossSensorResolutionError`)
- ✅ **Dependency Tracking**: Added usage tracking and validation methods
- ✅ **Improved Error Messages**: Enhanced error context and debugging information
- ✅ **Comprehensive Testing**: 17 enhanced tests covering all error scenarios

**Phase 4: Integration Points** ✅ **COMPLETE**

- ✅ **Enhanced Sensor Registration**: Cross-sensor registry integration with validation
- ✅ **Enhanced Evaluation Loop**: Dependency-aware evaluation with registry updates
- ✅ **Advanced Dependency Analysis**: Methods for analyzing and validating cross-sensor dependencies
- ✅ **Comprehensive Testing**: 9 Phase 4 tests covering all integration scenarios

**Coding Standards Compliance**:

**Type Safety Requirements**:

- **Strict Typing**: Use `TypedDict` and specific types instead of `Any`
- **No Any Types**: Avoid `Any` unless absolutely necessary
- **Type Annotations**: All methods must have complete type annotations
- **Mypy Compliance**: All code must pass mypy strict type checking

**Code Quality Standards**:

- **Ruff Compliance**: All code must pass ruff linting
- **Import Organization**: All imports at top of file
- **Single Responsibility**: Each method handles one specific aspect
- **Error Handling**: Use specific exception types, not generic exceptions
- **Documentation**: Clear docstrings for all public methods

**Testing Requirements**:

- **Test Coverage**: All new functionality must have comprehensive tests
- **Test Independence**: Tests should not depend on implementation details
- **Test Fixtures**: Use existing YAML fixtures from `tests/yaml_fixtures/`
- **Error Testing**: Test error scenarios and exception handling

**Risk Mitigation**:

**Technical Risks**:

- **Integration Complexity**: Use incremental approach with extensive testing
- **Type Safety**: Maintain strict typing throughout implementation
- **Performance Impact**: Monitor evaluation performance during implementation
- **Backward Compatibility**: Ensure no breaking changes to existing APIs

**Quality Assurance**:

- **Continuous Testing**: Run tests after each implementation step
- **Code Review**: Follow established coding standards
- **Documentation**: Update documentation as implementation progresses
- **Validation**: Validate against existing test suites

**Implementation Summary**: All phases of cross-sensor reference functionality have been successfully completed:

- ✅ **Phase 1**: Sensor lifecycle integration with cross-sensor registry
- ✅ **Phase 2**: Evaluation order management and circular reference detection
- ✅ **Phase 3**: Enhanced error handling and dependency tracking
- ✅ **Phase 4**: Advanced integration points and dependency analysis

**Total Test Coverage**: 44 tests passing across all cross-sensor reference functionality
**Code Quality**: All code passes ruff linting and mypy strict type checking
**Architecture**: Fully integrated with layered, compiler-like evaluation system

### Integration Approach

The layered architecture integrates with the existing evaluator through a phased migration approach:

#### Phase 1: Variable Resolution Engine (Complete)

- **Status**: ✅ Implemented and tested
- **Integration**: ✅ Integrated with evaluator
- **Impact**: Reduces evaluator complexity by ~200 lines
- **Files**: `evaluator_phases/variable_resolution/`

#### Phase 2: Dependency Management System (Complete)

- **Status**: ✅ Implemented and tested
- **Integration**: ✅ Integrated with evaluator
- **Impact**: Reduces evaluator complexity by ~150 lines
- **Files**: `evaluator_phases/dependency_management/`

#### Phase 3: Context Building Engine (Complete)

- **Status**: ✅ Implemented and tested
- **Integration**: ✅ Fully integrated with evaluator
- **Impact**: Reduced evaluator complexity by ~100 lines
- **Files**: `evaluator_phases/context_building/` (7 files, ~477 lines)
- **Note**: Successfully integrated using incremental approach with dependency injection

#### Phase 4: Pre-Evaluation Processing (Complete)

- **Status**: ✅ Implemented and tested
- **Integration**: ✅ Integrated with evaluator
- **Impact**: Reduced evaluator complexity by ~80-100 lines
- **Files**: `evaluator_phases/pre_evaluation/` (3 files, ~244 lines)
- **Note**: Successfully integrated with comprehensive pre-evaluation checks and validation

#### Phase 5: Cross-Sensor Reference Management (Phase 2 Complete)

- **Status**: ✅ Phase 2 implemented and tested
- **Integration**: ✅ Integrated with sensor lifecycle and dependency management
- **Impact**: Framework reduces evaluator complexity by ~60-80 lines
- **Files**: `evaluator_phases/sensor_registry/` (2 files, ~156 lines) +
  `evaluator_phases/dependency_management/cross_sensor_dependency_manager.py` (~295 lines)
- **Note**: Phase 2 complete with cross-sensor dependency analysis, evaluation order management, and circular reference
  detection

### Integration Lessons Learned & Refined Approach

#### Success Patterns Identified

**Phase 1 & 2 Integration Success Factors**:

- **Clear delegation points**: Single method replacements with straightforward interfaces
- **Minimal dependencies**: Self-contained logic with simple input/output contracts
- **Low integration risk**: Direct method-to-method delegation without complex state sharing

**Phase 3 Integration Challenges**:

- **Complex interdependencies**: Entity resolution requires access to multiple evaluator components
- **State sharing requirements**: Context building needs evaluator's resolver creation logic
- **Test complexity**: Existing tests assume inline context building patterns

#### Refined Integration Strategy

**Incremental Migration Approach**:

```text
Phase 3 Context Building Integration:
Step 1: Delegate variable context building only (lowest risk)
Step 2: Delegate entity context building (medium risk)
Step 3: Delegate sensor registry context building (higher risk)
Step 4: Remove original methods after full validation
```

**Architectural Adjustments**:

- **Target revision**: 550-650 lines (more realistic than 400-500)
- **Integration testing**: Enhanced phase integration test suite
- **Gradual delegation**: Piece-by-piece migration instead of wholesale replacement

### Current Status

- **Original Evaluator**: 992 lines (monolithic)
- **Current Evaluator**: 538 lines (45.8% reduction achieved)
- **Target Evaluator**: ~550-650 lines (realistic orchestration target)
- **Phase 5 Status**: ✅ Phase 2 complete
- **Phase Modules**: 2,437 lines total across 34 focused files
- **Total Reduction**: ~46% reduction in single-file complexity (target achieved)

#### Maintainability Improvements

- **Single Responsibility**: Each layer handles one aspect of evaluation
- **Testability**: Each layer can be tested independently with 96% test pass rate
- **Extensibility**: Factory patterns enable easy addition of new resolvers, validators, or builders
- **Debugging**: Clear separation of concerns for easier troubleshooting
- **Code Quality**: All phases pass mypy strict typing and ruff linting checks

#### Architecture Benefits

- **Clear Phase Separation**: Variable resolution → Dependency analysis → Context building → Pre-evaluation → Cross-sensor
  reference → Evaluation
- **Extensible Pipelines**: Easy to add new phases or modify existing ones with factory patterns
- **Error Isolation**: Errors contained within specific phases for better debugging
- **Performance Optimization**: Each phase can be optimized independently
- **Integration Success**: 4 phases fully integrated, 1 phase complete with Phase 2 complete

### Maintaining Extensibility

When making changes to the evaluation system, the following principles ensure extensibility is maintained:

1. **Layer Separation**: Keep layers distinct and focused on specific responsibilities
2. **Clear Interfaces**: Define clear contracts between layers and the main evaluator
3. **Factory Patterns**: Use factories for managing specialized components within each layer
4. **Registration Mechanisms**: Provide clean ways to register new components
5. **Composition Support**: Allow layers to delegate to other layers when needed
6. **Incremental Integration**: Use gradual migration for complex integrations to maintain stability

This layered architecture enables the system to evolve with new data types and evaluation patterns while maintaining clean
separation of concerns and predictable behavior. The current implementation demonstrates successful application of these
principles with 4 phases fully integrated and 1 phase complete with Phase 2 complete, providing full cross-sensor reference
functionality.
