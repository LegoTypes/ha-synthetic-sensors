# HA Synthetic Sensors Cookbook

A guide to using HA Synthetic Sensors with detailed syntax examples and patterns.

## Table of Contents

- [Basic Sensor Configuration](#basic-sensor-configuration)
- [References in YAML](#references-in-yaml)
- [Variables and Configuration](#variables-and-configuration)
- [Globals](#globals)
- [Formulas](#formulas)
- [Attributes and Metadata](#attributes-and-metadata)
- [Comparison Logic](#comparison-logic)
- [Cross-Sensor Dependencies](#cross-sensor-dependencies)
- [Device Association](#device-association)
- [String Operations](#string-operations)
- [Date and Time Operations](#date-and-time-operations)
- [Collection Functions](#collection-functions)
- [Alternate State Handling](#alternate-state-handling)

## Basic Sensor Configuration

### Simple Calculated Sensors

```yaml
version: "1.0" # Required: YAML schema version

sensors:
  # Single formula sensor (90% of use cases)
  energy_cost_current:
    name: "Current Energy Cost"
    formula: "current_power * electricity_rate / conversion_factor"
    variables:
      current_power: "sensor.span_panel_instantaneous_power"
      electricity_rate: "input_number.electricity_rate_cents_kwh"
      conversion_factor: 1000 # Literal: watts to kilowatts
    metadata:
      unit_of_measurement: "¢/h"
      state_class: "total"
      device_class: "monetary"
      icon: "mdi:currency-usd"

  # Another simple sensor with numeric literals
  solar_sold_power:
    name: "Solar Sold Power"
    formula: "abs(min(grid_power, zero_threshold))"
    variables:
      grid_power: "sensor.span_panel_current_power"
      zero_threshold: 0 # Literal: threshold value
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
      suggested_display_precision: 0
      icon: "mdi:solar-power"
```

### Rich sensors with calculated sensor attributes

```yaml
sensors:
  # Sensor with calculated attributes
  energy_cost_analysis:
    name: "Energy Cost Analysis"
    # entity_id: "sensor.custom_entity_id"  # Optional: override auto-generated entity_id
    formula: "current_power * electricity_rate / 1000"
    attributes:
      daily_projected:
        formula: "state * 24" # ref by main state alias
        metadata:
          unit_of_measurement: "¢"
          suggested_display_precision: 2
      monthly_projected:
        formula: "state * 24 * 30" # ref by main sensor state (preferred)
        metadata:
          unit_of_measurement: "¢"
          suggested_display_precision: 2
      annual_projected:
        formula: "sensor.energy_cost_analysis * 24 * 365" # ref by entity_id
        metadata:
          unit_of_measurement: "¢"
          suggested_display_precision: 0
      battery_efficiency:
        formula: "current_power * device.battery_level / 100" # using attribute access
        variables:
          device: "sensor.backup_device"
        metadata:
          unit_of_measurement: "W"
          device_class: "power"
      efficiency:
        formula: "state / max_capacity * 100"
        variables:
          max_capacity: "sensor.max_power_capacity"
        metadata:
          unit_of_measurement: "%"
          suggested_display_precision: 1
      temperature_analysis:
        formula: "outdoor_temp - indoor_temp"
        variables:
          outdoor_temp: "sensor.outdoor_temperature"
          indoor_temp: "sensor.indoor_temperature"
        metadata:
          unit_of_measurement: "°C"
          device_class: "temperature"
          suggested_display_precision: 1
    variables:
      current_power: "sensor.span_panel_instantaneous_power"
      electricity_rate: "input_number.electricity_rate_cents_kwh"
    metadata:
      unit_of_measurement: "¢/h"
      device_class: "monetary"
      state_class: "total"
      icon: "mdi:currency-usd"
      attribution: "Calculated from SPAN Panel data"
```

## References in YAML

References to various sensors, state, or attributes are simple to use:

- The main sensor state is `state` where ever it is used in that sensor's references (varaiables, attributes, formulas)
- The main sensor state can be use to reference attributes like `state.my_attribute`
- Any sensor in the YAML can be referred to by its key (the top level key)
- The sensor's key is internally related in storage and the runtime to the actual HA entity_id when registered
- All references are kept in sync with HA changes so if a user renames an entity_id the package references are updated

## Variables and Configuration

Variables serve as aliases for entity IDs, collection patterns, or numeric literals, making formulas more readable and
maintainable.

### Variable Purpose and Scope

A variable, unlike an attribute, has a life cycle for the duration of the sensors calculation. Variables are very much like a
local variable in programmming languages.

Variables can be:

- **Entity IDs**: `"sensor.power_meter"` - References Home Assistant entities
- **Numeric Literals**: `42`, `3.14`, `-5.0` - Direct numeric values for constants
- **Collection Patterns**: `"device_class:temperature"` - Dynamic entity aggregation
- **Computed Variables**: Formulas that calculate values dynamically using its own `formula:` sub-key

**Variable Scope**: Variables can be defined at both the sensor level and attribute level:

- **Sensor-level variables**: Defined in the main sensor's `variables` section and available to all formulas
- **Attribute-level variables**: Defined in an attribute's `variables` section and available only to that attribute
- **Variable inheritance**: Attributes inherit all sensor-level variables and can add their own
- **Variable precedence**: Attribute-level variables with the same name override sensor-level variables for that attribute

**Supported Literal Types:**

- **Numeric values**: `42`, `3.14`, `-5.0`, `1.23e-4`
- **String values**: `"test_string"`, `"Hello World"`, `""` (empty string)
- **Boolean values**: `True`, `False`
- **Special characters**: `"test@#$%^&*()"`, `"测试"` (Unicode)

## Globals

Global device information, variables, and metadata apply to all sensors in a sensor set. Globals _cannot_ have formulas. Globals
alleviate the user from defining the same information in individual sensors like device or literals. Individual sensors and
their attributes may contain the same global name but the value must also be the same to avoid conflicts in sensor formulas.
This override restriction is the same concept as programming languages that disallow renaming from outer to innner scope.

### Global Settings Structure

Complete global settings structure:

```yaml
version: "1.0"

global_settings:
  # Device information fields
  device_identifier: "my_device_001"
  device_name: "My Smart Device"
  device_manufacturer: "Acme Corp"
  device_model: "Smart-1000"
  device_sw_version: "1.2.3"
  device_hw_version: "2.1"
  suggested_area: "Kitchen"

  # Global variables accessible to all sensors
  variables:
    base_power: "sensor.power_meter"
    rate_multiplier: 1.15
    threshold_value: 100.0
    backup_sensor: "sensor.backup_power"

  # Custom metadata
  metadata:
    installation_date: "2024-01-15"
    location: "Kitchen Counter"
    notes: "Primary measurement device"
```

## Formulas

The main sensor must have a formula. Attributes, or variables can contain formulas that calculate values dynamically with
automatic dependency resolution.

- A variable or attribute can refer to simple state's; examples are literals, main sensor `state`, or date-time `now()`,
  `today()`, `yesterday()`, and so on.
- Using a sub-key `formula:` complex formula syntax that have references to other sensor keys, entity_id, or that sensor's
  variables

### Syntax Reference

| Pattern Type     | Explicit Syntax                                          | Shorthand Syntax                         | Negation Syntax               |
| ---------------- | -------------------------------------------------------- | ---------------------------------------- | ----------------------------- |
| **State**        | `"state:==on \|\| !=off \|\| >=50"`                      | `"state:on \|\| !off \|\| >=50"`         | `"state:!off \|\| !inactive"` |
| **Attribute**    | `"battery_level>=50 \|\| status==active"`                | `"battery_level>=50 \|\| status:active"` | `"battery_level:!<20"`        |
| **String**       | `"name in 'Living' \|\| manufacturer not in 'Test'"`     | `"name:Living \|\| manufacturer:!Test"`  | `"name:!'Kitchen'"`           |
| **String Func**  | `"lower(name)=='living' \|\| contains(name, 'sensor')"`  | `"lower(name):living"`                   | `"contains(name):!sensor"`    |
| **Version**      | `"firmware_version>='v2.1.0' \|\| app_version<'v3.0.1'"` | `"firmware_version:>=v2.1.0"`            | `"version:!<v1.0.1"`          |
| **DateTime**     | `"last_seen>='2024-01-01T00:00:00Z'"`                    | `"last_seen:>=2024-01-01"`               | `"updated_at:!<yesterday"`    |
| **Device Class** | `"device_class:power \|\| device_class:energy"`          | `"device_class:power \|\| energy"`       | `"device_class:!diagnostic"`  |
| **Area**         | `"area:kitchen \|\| area:living_room"`                   | `"area:kitchen \|\| living_room"`        | `"area:!basement"`            |
| **Label**        | `"label:critical \|\| label:important"`                  | `"label:critical \|\| important"`        | `"label:!deprecated"`         |

```yaml
sensors:
  energy_analysis: # Sensor key that can be referenced (references are replaced with `state` or entity_id)
    name: "Energy Analysis"
    formula: "final_total" # Main Sensor formula, simple or complex
    variables:
      # Simple variables
      grid_power: "sensor.grid_meter" # entity_id reference
      solar_power: "sensor.solar_inverter" # entity_id reference
      efficiency_factor: 0.85 # Literal

      # Computed variables with dependency ordering
      total_power:
        formula: "grid_power + solar_power" # Variable with computed formula
      efficiency_percent:
        formula: "solar_power / total_power * 100" # Variable with computed formula
      final_total:
        formula: "total_power * efficiency_factor" # Variable with computed formula

    attributes: # Computed after main sensor state, can reference main sensor `state`
      daily_projection:
        formula: "state * 24" # Uses main sensor post-eval result
        metadata:
          device_class: "energy" # Must be a valid HA device_class
          unit_of_measurement: "Wh" # Must be valid with device_class
      cost_analysis:
        formula: "state * rate" # calculated attribute
        variables:
          rate: 0.12 # Literal number or string
        metadata:
          unit_of_measurement: "¢"
          suggested_display_precision: 2
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
```

### Complex Dependency Chains

Create complex variable dependency chains with automatic resolution:

```yaml
sensors:
  complex_dependency_chain:
    name: "Complex Dependency Chain Sensor"
    formula: "result"
    variables:
      # Simple inputs
      a: 10
      b: 5
      c: sensor.factor_sensor

      # Chain of computed variables
      step1:
        formula: "a + b" # 15
      step2:
        formula: "step1 * 2" # 30
      step3:
        formula: "step2 + c" # 30 + c
      step4:
        formula: "step3 * 1.1" # (30 + c) * 1.1
      result:
        formula: "round(step4, 2)"

    metadata:
      unit_of_measurement: "units"
```

### Conditional Computed Variables

Use conditional logic in computed variables:

```yaml
sensors:
  energy_sensor_with_computed_variables:
    name: "Energy Sensor with Computed Variables"
    formula: "final_total"
    variables:
      # Simple variables
      input_power: sensor.inverter_input
      efficiency: 0.85
      grace_minutes: 15

      # Computed variables with dependency ordering
      output_power:
        formula: "input_power * efficiency"
      power_threshold:
        formula: "output_power * 0.8"

      # Time-based computed variable
      minutes_since_update:
        formula: "(42 - 2) / 2" # Simplified for example
      within_grace:
        formula: "minutes_since_update < grace_minutes"

      # Final computed result with conditional logic
      final_total:
        formula: "output_power if within_grace else power_threshold"

    metadata:
      unit_of_measurement: "W"
      device_class: "power"
```

### Mathematical Functions in Computed Variables

Use mathematical functions in computed variable formulas:

```yaml
sensors:
  mathematical_functions_sensor:
    name: "Mathematical Functions Sensor"
    formula: "processed_result"
    variables:
      raw_value: sensor.raw_sensor
      processed_result:
        formula: "abs(round(raw_value * 1.5, 2))"

    metadata:
      unit_of_measurement: "processed"
```

## Attributes and Metadata

### How attributes work

- Main sensor state is calculated _first_ using the `formula`
- Attributes are calculated _second_ and have access to the sensor `state` variable
- Attribute `state` tokens refers to the _calculated_ main sensor state
- Attributes can reference other attributes
- Attributes can define their own `variables` section for attribute-specific entity references or use the main sensors variables
- Attributes can define their own `formula` section
- Attributes can also reference other entities (like `sensor.max_power_capacity` above)

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

- The main sensor `state` is set to the value of the sensor's backing entity or the previous HA sensor state.
- The `daily_total` attribute is calculated as the main state times 24.
- The `with_multiplier` attribute is calculated as the main state times a custom multiplier (2.5).
- Both attribute formulas use the `state` variable, which is the freshly calculated main sensor value.

### Metadata Function

The `metadata()` function provides access to Home Assistant entity/sensor metadata properties. This allows you to retrieve
information about entity state changes, domain, friendly name, and other metadata.

**Syntax:**

```yaml
metadata(entity_reference, 'metadata_key')
```

**Common Metadata Keys:**

- `last_changed` - When the entity state last changed
- `last_updated` - When the entity was last updated
- `domain` - Entity domain (e.g., "sensor", "switch")
- `object_id` - Entity object ID (e.g., "power_meter")
- `friendly_name` - Entity friendly name
- `entity_id` - Full entity ID (e.g., "sensor.power_meter", not practical since you provide what you ask for)

**Examples:**

```yaml
sensors:
  # Data staleness detection
  power_data_freshness:
    name: "Power Data Freshness"
    formula: "1 if (now() - metadata(power_entity, \"last_changed\")) < hours(1) else 0" # Using metadata function to retrieve last_changed
    variables:
      power_entity: "sensor.power_meter"
    metadata: # metadata you set on your sensor
      unit_of_measurement: "binary"

  # Entity domain validation
  entity_type_check:
    name: "Entity Type Validation"
    formula: "1 if metadata(sensor.temp_probe, \"domain\") == \"sensor\" else 0"
    metadata:
      unit_of_measurement: "binary"

  # Display friendly names in attributes
  sensor_with_metadata_info:
    name: "Enhanced Sensor Info"
    formula: "power_sensor * efficiency_factor"
    variables:
      power_sensor: "sensor.power_meter"
      efficiency_factor: 0.95
    attributes:
      source_name:
        formula: "metadata(power_sensor, \"friendly_name\")" # Retrieve friendly name
              data_age_minutes:
          formula: "(now() - metadata(power_sensor, \"last_changed\")) / minutes(1)"
          metadata:
            unit_of_measurement: "min"
            suggested_display_precision: 1
        is_recent:
          formula: "metadata(power_sensor, \"last_updated\") > (now() - minutes(5)) ? \"Yes\" : \"No\""
    metadata:
      unit_of_measurement: "W"
      device_class: "power"

  # State token for current sensor metadata
  self_reference_metadata:
    name: "Self Reference Metadata"
    entity_id: "sensor.power_meter"
    formula: "metadata(state, \"object_id\")" # Uses state token to reference current sensor by entity_id
    metadata:
      unit_of_measurement: ""
```

**Metadata Function Reference Types:**

- **Variable names**: `metadata(power_entity, 'entity_id')` - Uses variable that resolves to entity ID
- **Direct entity IDs**: `metadata(sensor.power_meter, 'last_changed')` - Direct entity reference
- **State token**: `metadata(state, 'entity_id')` - References the current sensor's backing entity
- **Global variables**: `metadata(external_sensor, 'domain')` - Uses global variable reference

### Engine-managed last-good attributes

The engine records the most recent valid (non-alternate) calculated result on each sensor as two extra state attributes that are
exposed on the entity at runtime:

- `last_valid_state` — the last valid calculated state (number or string)
- `last_valid_changed` — ISO timestamp (string) when that value was recorded

Access patterns:

```yaml
variables:
  source: "sensor.span_panel_main_meter_produced_energy"
formula: "minutes_between(metadata(source, 'last_valid_changed'), now()) < energy_grace_period_minutes"
```

Avoid direct `entity.attribute` access (e.g., `source.last_valid_state` / `source.last_valid_changed`) for engine-provided
last-good values in templates.

### Prefer central variables for last-good values

When multiple formulas or attributes need the engine-provided last-good values, define sensor-level variables that resolve
`metadata(state, ...)` once and reference those variables throughout the sensor. This centralizes the lookup, reduces repeated
metadata calls, and makes templates easier to read and maintain.

Recommended pattern (sensor-level variables):

```yaml
sensors:
  example_energy_sensor:
    name: "Example Energy"
    formula: state
    variables:
      # centralize last-good references once
      last_valid_state: "metadata(state, 'last_valid_state')"
      last_valid_changed: "metadata(state, 'last_valid_changed')"
      within_grace:
        formula: "last_valid_changed is not None and minutes_between(last_valid_changed, now()) < energy_grace_period_minutes"
    alternate_states:
      FALLBACK:
        formula: "state if state is not None else (last_valid_state if within_grace else None)"
    attributes:
      energy_reporting_status:
        formula: "'Live' if state is not None else ('Off-Line, reporting previous value' if within_grace else None)"
        alternate_states:
          FALLBACK: false
```

Benefits:

- Single location to update if the key name or behavior changes.
- Cleaner formulas and attributes that reference `last_valid_*` without repeating `metadata()`.
- Easier to debug because `within_grace` and the last-good variables are centralized and logged consistently.

### Metadata Dictionary

The `metadata` dictionary provides extensible support for all Home Assistant sensor properties. This metadata is added directly
to the sensor when the sensor is created in Home Assistant.

```yaml
sensors:
  comprehensive_sensor:
    name: "Comprehensive Sensor Example"
    formula: "power_input * efficiency_factor"
    variables:
      power_input: "sensor.input_power"
      efficiency_factor: 0.95
    metadata:
      # Core sensor properties
      unit_of_measurement: "W"
      native_unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

      # Display properties
      suggested_display_precision: 2
      suggested_unit_of_measurement: "kW"
      icon: "mdi:flash"
      attribution: "Data from SPAN Panel"

      # Entity registry properties
      entity_category: "diagnostic"
      entity_registry_enabled_default: true
      entity_registry_visible_default: true

      # Advanced properties
      assumed_state: false
      last_reset: null
      options: ["low", "medium", "high"] # for enum device classes

      # Custom properties (passed through to HA)
      custom_property: "custom_value"
```

## Boolean Logic and State Comparisons

Synthetic sensors support boolean logic using Python operators (`and`, `or`, `not`) and state comparisons.

### Boolean vs String Comparisons

The system provides explicit control over boolean and string comparisons:

**For boolean comparisons (use unquoted names):**

```yaml
sensors:
  door_sensor:
    formula: "binary_sensor.front_door == on"
    # Uses boolean mapping: 'on' -> True
```

**For string comparisons (use quoted strings):**

```yaml
sensors:
  alarm_sensor:
    formula: "alarm_control_panel.home == 'armed_away'"
    # Uses string comparison: 'armed_away' == 'armed_away'
```

### Boolean Logic Examples

```yaml
sensors:
  security_check:
    name: "Security Check"
    formula: "door_state == locked and motion_state == 'clear'"
    variables:
      door_state: "binary_sensor.front_door"
      motion_state: "binary_sensor.motion_detector"
    # door_state == locked: boolean comparison (locked -> True)
    # motion_state == 'clear': string comparison ('clear' == 'clear')

  presence_logic:
    name: "Presence Logic"
    formula: "home_presence == home or work_presence == 'office'"
    variables:
      home_presence: "device_tracker.phone_home"
      work_presence: "device_tracker.phone_work"
    # home_presence == home: boolean comparison (home -> True)
    # work_presence == 'office': string comparison ('office' == 'office')
```

### Available Boolean States

Common boolean states that can be used unquoted:

- `on`, `off`
- `home`, `not_home`
- `locked`, `not_locked`
- `occupied`, `not_occupied`
- `motion`, `no_motion`
- `true`, `false`

### Comparison Logic

The system has built-in support for:

- Numeric comparisons (`>`, `<`, `>=`, `<=`, `==`, `!=`)
- Boolean logic (`and`, `or`, `not`)
- String comparisons (with quoted strings)
- Boolean conversions (with unquoted names)

For custom comparison logic, see the [Custom Comparison Logic](../examples/custom_comparison_type.py) example.

## Comparison Logic

The synthetic sensors library provides built-in comparison logic for common data types, enabling sophisticated filtering and
analysis in collection functions.

For examples of implementing custom comparison logic, see:

- **examples/custom_comparison_type.py**: Shows how to create helper classes for custom comparisons
- **examples/using_typed_conditions.py**: Demonstrates condition parsing and evaluation

### Built-in Comparison Handlers

#### DateTime Comparisons

Compare datetime strings with full timezone support:

```yaml
sensors:
  recent_devices:
    name: "Recent Devices"
    formula: "count(attribute:last_seen>=cutoff_date)"
    variables:
      cutoff_date: "2024-01-01T00:00:00Z"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:clock-check"

  maintenance_due:
    name: "Maintenance Due"
    formula: "count(attribute:last_maintenance<cutoff_date|attribute:next_service<=recent_threshold)"
    variables:
      cutoff_date: "2024-01-01T00:00:00Z"
      recent_threshold: "2024-06-01T12:00:00+00:00"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:wrench-clock"
```

#### Version String Comparisons

Compare semantic version strings with automatic parsing:

```yaml
sensors:
  compatible_firmware:
    name: "Compatible Firmware"
    formula: "count(attribute:firmware_version>=min_firmware)"
    variables:
      min_firmware: "v2.1.0"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:chip"

  upgrade_candidates:
    name: "Upgrade Candidates"
    formula: "count(attribute:current_version<target_version) - count(attribute:min_supported_version>target_version)"
    variables:
      target_version: "v3.0.0"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:arrow-up-bold"
```

#### String Containment Operations

Use `in` and `not in` operators for substring matching:

```yaml
sensors:
  living_room_devices:
    name: "Living Room Devices"
    formula: "count(attribute:name in living_filter)"
    variables:
      living_filter: "Living"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:sofa"

  non_error_devices:
    name: "Non Error Devices"
    formula: "count(state not in error_pattern)"
    variables:
      error_pattern: "error"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:shield-check"

  multi_room_devices:
    name: "Multi Room Devices"
    formula: "count(attribute:name in 'Living'|attribute:name in 'Bedroom')"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:home-variant"
```

#### Numeric Comparisons

Standard numeric comparisons with support for floating-point precision:

```yaml
sensors:
  high_power_devices:
    name: "High Power Devices"
    formula: "count(attribute:power_rating>=high_threshold)"
    variables:
      high_threshold: 800
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:flash"

  efficient_devices:
    name: "Efficient Devices"
    formula: "count(attribute:efficiency_rating<=precision_value)"
    variables:
      precision_value: 42.5
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:leaf"
```

#### Equality and Inequality

Compare values for exact matches or differences:

```yaml
sensors:
  active_devices:
    name: "Active Devices"
    formula: "count(state==target_state)"
    variables:
      target_state: "on"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:power"

  non_auto_devices:
    name: "Non Auto Devices"
    formula: "count(attribute:mode!=target_mode)"
    variables:
      target_mode: "auto"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:cog"
```

## Cross-Sensor Dependencies

Create sensors that depend on other synthetic sensors with automatic dependency resolution:

```yaml
sensors:
  base_power:
    name: "Base Power"
    formula: "state"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  adjusted_power:
    name: "Adjusted Power"
    formula: "base_power * efficiency"
    variables:
      base_power: "sensor.base_power"
      efficiency: 0.95
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  peak_power:
    name: "Peak Power"
    formula: "adjusted_power * peak_factor"
    variables:
      adjusted_power: "sensor.adjusted_power"
      peak_factor: 1.2
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  total_system_power:
    name: "Total System Power"
    formula: "peak_power + auxiliary_power + grid_power"
    variables:
      peak_power: "sensor.peak_power"
      auxiliary_power: "sensor.auxiliary_system"
      grid_power: "sensor.grid_connection"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  efficiency_ratio:
    name: "System Efficiency Ratio"
    formula: "total_system_power / theoretical_max * 100"
    variables:
      total_system_power: "sensor.total_system_power"
      theoretical_max: 5000
    metadata:
      unit_of_measurement: "%"
      suggested_display_precision: 1
```

### Dependency Extraction and Analysis

The library automatically extracts and analyzes dependencies between sensors:

```yaml
sensors:
  dependency_chain_sensor:
    name: "Dependency Chain Sensor"
    formula: "final_result"
    variables:
      # Simple inputs
      input_a: "sensor.input_sensor_a"
      input_b: "sensor.input_sensor_b"

      # Computed intermediate values
      intermediate_1:
        formula: "input_a * 2"
      intermediate_2:
        formula: "input_b + 10"

      # Final computed result
      final_result:
        formula: "intermediate_1 + intermediate_2"
    metadata:
      unit_of_measurement: "units"
      device_class: "enum"
```

### Collection Function Dependencies

Use collection functions with complex dependency patterns:

```yaml
sensors:
  collection_dependency_sensor:
    name: "Collection Dependency Sensor"
    formula: "sum('device_class:power') + count('area:living_room')"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
```

## Device Association

Associate sensors with Home Assistant devices for better organization and device-centric management:

```yaml
sensors:
  # Sensor associated with a new device
  solar_inverter_efficiency:
    name: "Solar Inverter Efficiency"
    formula: "solar_output / solar_capacity * 100"
    variables:
      solar_output: "sensor.solar_current_power"
      solar_capacity: "sensor.solar_max_capacity"
    metadata:
      unit_of_measurement: "%"
      device_class: "power_factor"
      state_class: "measurement"
      suggested_display_precision: 1
      icon: "mdi:solar-panel"
    # Device association fields
    device_identifier: "solar_inverter_001"
    device_name: "Solar Inverter"
    device_manufacturer: "SolarTech"
    device_model: "ST-5000"
    device_sw_version: "2.1.0"
    device_hw_version: "1.0"
    suggested_area: "Garage"
```

**Device Association Fields:**

- **`device_identifier`** _(required)_: Unique identifier for the device
- **`device_name`** _(optional)_: Human-readable device name
- **`device_manufacturer`** _(optional)_: Device manufacturer
- **`device_model`** _(optional)_: Device model
- **`device_sw_version`** _(optional)_: Software version
- **`device_hw_version`** _(optional)_: Hardware version
- **`suggested_area`** _(optional)_: Suggested Home Assistant area

**Device Behavior:**

- **New devices**: If a device with the `device_identifier` doesn't exist, it will be created with the provided information
- **Existing devices**: If a device already exists, the sensor will be associated with it (additional device fields are ignored)
- **No device association**: Sensors without `device_identifier` behave as standalone entities (default behavior)
- **Entity ID generation**: When using device association, entity IDs automatically include the device name prefix (e.g.,
  `sensor.span_panel_main_power`)

**Device-Aware Entity Naming:**

When sensors are associated with devices, entity IDs are automatically generated using the device's name as a prefix:

- **device_identifier** is used to look up the device in Home Assistant's device registry
- **Device name** (from the device registry) is "slugified" (converted to lowercase, spaces become underscores, special
  characters removed)
- Entity ID pattern: `sensor.{slugified_device_name}_{sensor_key}`
- Examples:
  - device_identifier "njs-abc-123" → Device "SPAN Panel House" → `sensor.span_panel_house_current_power`
  - device_identifier "solar_inv_01" → Device "Solar Inverter" → `sensor.solar_inverter_efficiency`
  - device_identifier "circuit_a1" → Device "Circuit - Phase A" → `sensor.circuit_phase_a_current`

This automatic naming ensures consistent, predictable entity IDs that clearly indicate which device they belong to, while
avoiding conflicts between sensors from different device

### Available Mathematical Functions

- Basic: `abs()`, `round()`, `floor()`, `ceil()`
- Math: `sqrt()`, `pow()`, `sin()`, `cos()`, `tan()`, `log()`, `exp()`
- Statistics: `min()`, `max()`, `avg()`, `mean()`, `sum()`
- Utilities: `clamp(value, min, max)`, `map(value, in_min, in_max, out_min, out_max)`, `percent(part, whole)`

## String Operations

### String Functions

The package provides comprehensive string manipulation capabilities:

**Basic String Functions:**

- `str(value)` - Convert value to string
- `trim(text)` - Remove leading and trailing whitespace
- `lower(text)` - Convert to lowercase
- `upper(text)` - Convert to uppercase
- `title(text)` - Convert to title case

**Pattern Matching Functions:**

- `contains(text, substring)` - Check if text contains substring
- `startswith(text, prefix)` - Check if text starts with prefix
- `endswith(text, suffix)` - Check if text ends with suffix

**Text Processing Functions:**

- `normalize(text)` - Normalize whitespace
- `clean(text)` - Remove special characters
- `sanitize(text)` - Convert to safe identifier

**String Validation Functions:**

- `isalpha(text)` - Check if all characters are alphabetic
- `isdigit(text)` - Check if all characters are digits
- `isnumeric(text)` - Check if text represents a number
- `isalnum(text)` - Check if all characters are alphanumeric

**String Manipulation Functions:**

- `length(text)` - Get string length
- `replace(text, old, new)` - Replace substring
- `replace_all(text, old, new)` - Replace all occurrences
- `split(text, delimiter)` - Split text by delimiter
- `join(list, separator)` - Join list with separator
- `pad_left(text, length, char)` - Pad left with character
- `pad_right(text, length, char)` - Pad right with character
- `center(text, length, char)` - Center text with character

### Advanced String Operations

```yaml
sensors:
  # String concatenation and formatting
  device_status_message:
    name: "Device Status Message"
    formula: "'Device: ' + device_name + ' is ' + status + ' at ' + power + 'W'"
    variables:
      device_name: "sensor.device_name"
      status: "sensor.device_status"
      power: "sensor.power_reading"
    metadata:
      icon: "mdi:message-text"

  # String functions for text processing
  normalized_device_name:
    name: "Normalized Device Name"
    formula: "trim(lower(device_name))"
    variables:
      device_name: "sensor.raw_device_name"
    metadata:
      icon: "mdi:format-text"

  # String pattern matching
  living_room_devices:
    name: "Living Room Devices"
    formula: "count(contains(attribute:name, 'Living'))"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:home"

  # String validation and cleaning
  clean_device_names:
    name: "Clean Device Names"
    formula: "count(sanitize(attribute:name) == 'device_name')"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:identifier"

  # Complex string processing
  formatted_device_info:
    name: "Formatted Device Info"
    formula: "'Device: ' + str(title(trim(attribute:name))) + ' | ' + str(upper(attribute:status))"
    metadata:
      icon: "mdi:devices"

  # Nested functions
  nested_functions_sensor:
    name: "Nested Functions Test"
    formula: "'sensor' in lower(trim(device_description))"
    variables:
      device_description: "sensor.device_description"
    metadata:
      unit_of_measurement: ""
      device_class: "enum"

  # Concatenation with functions
  concatenation_with_functions_sensor:
    name: "Concatenation with Functions Test"
    formula: "'Device: ' + trim(device_name) + ' | Length: ' + len(device_name)"
    variables:
      device_name: sensor.device_name # attribute reference
    metadata:
      unit_of_measurement: ""
      device_class: "enum"

  # Complex parameters
  complex_parameters_sensor:
    name: "Complex Parameters Test"
    formula: "contains('Device: ' + device_type, prefix + ' Type')"
    variables:
      device_type: "sensor.device_type"
      prefix: sensor.type_prefix # attribute reference
    metadata:
      unit_of_measurement: ""
      device_class: "enum"

  # Mixed operations
  mixed_operations_sensor:
    name: "Mixed Operations Test"
    formula: "'Power: ' + str(power_value * 1.1) + 'W | Status: ' + upper(status)"
    variables:
      power_value: "sensor.power_reading"
      status: sensor.device_status # attribute reference
    metadata:
      unit_of_measurement: ""
      device_class: "enum"
```

### String Operations in Collection Patterns

String functions can be used in collection patterns for advanced filtering:

```yaml
sensors:
  # Case-insensitive device filtering
  living_area_devices:
    name: "Living Area Devices"
    formula: "count(lower(attribute:name) == 'living room')"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:home"

  # Normalized text matching
  active_devices:
    name: "Active Devices"
    formula: "count(trim(attribute:description) == 'active device')"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:check"

  # Substring pattern matching
  sensor_devices:
    name: "Sensor Devices"
    formula: "count(contains(attribute:name, 'sensor'))"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:magnify"

  # Prefix and suffix matching
  power_meters:
    name: "Power Meters"
    formula: "count(startswith(attribute:name, 'power') or endswith(attribute:name, 'meter'))"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:flash"
```

## Date and Time Operations

### Datetime Functions

**Basic Datetime Functions:**

- `now()` - Current datetime in local timezone (ISO format)
- `local_now()` - Current datetime in local timezone (ISO format)
- `utc_now()` - Current datetime in UTC timezone (ISO format)
- `today()` - Today's date at midnight in local timezone (ISO format)
- `yesterday()` - Yesterday's date at midnight in local timezone (ISO format)
- `tomorrow()` - Tomorrow's date at midnight in local timezone (ISO format)
- `utc_today()` - Today's date at midnight in UTC timezone (ISO format)
- `utc_yesterday()` - Yesterday's date at midnight in UTC timezone (ISO format)
- `date(year, month, day)` - Create date object from integers
- `date("YYYY-MM-DD")` - Parse date string to ISO datetime format

**Duration Functions:**

- `seconds(n)` - Duration in seconds
- `minutes(n)` - Duration in minutes
- `hours(n)` - Duration in hours
- `days(n)` - Duration in days
- `weeks(n)` - Duration in weeks
- `months(n)` - Duration in months (average 30.44 days)

### Date Arithmetic

```yaml
sensors:
  # Basic date arithmetic
  future_date:
    name: "Future Date"
    formula: "date(2025, 1, 1) + days(30)"
    metadata:
      device_class: "date"

  # Date arithmetic with variables
  maintenance_schedule:
    name: "Next Maintenance"
    formula: "date(last_service_date) + months(6)"
    variables:
      last_service_date: sensor.last_maintenance_date # attribute reference
    metadata:
      device_class: "date"

  # Complex date calculations
  project_deadline:
    name: "Project Deadline"
    formula: "date(start_date) + weeks(4) + days(3)"
    variables:
      start_date: sensor.project_start_date # attribute reference
    metadata:
      device_class: "date"

  # Date differences
  days_since_created:
    name: "Days Since Created"
    formula: "now() - date(created_timestamp)"
    variables:
      created_timestamp: sensor.creation_date # attribute reference
    metadata:
      unit_of_measurement: "days"
      device_class: "duration"

  # Conditional date arithmetic
  maintenance_overdue:
    name: "Maintenance Overdue"
    formula: "1 if now() > date(last_service) + months(12) else 0"
    variables:
      last_service: sensor.last_maintenance_date # attribute reference
    metadata:
      unit_of_measurement: "binary"
      icon: "mdi:alert"

  # Time-based calculations
  device_uptime:
    name: "Device Uptime"
    formula: "now() - date(state.last_changed)"
    metadata:
      unit_of_measurement: "days"
      device_class: "duration"

  # Recent activity monitoring
  recent_activity:
    name: "Recent Activity"
    formula: "count(state.last_changed >= now() - hours(24))"
    metadata:
      unit_of_measurement: "events"
```

### Advanced Date Arithmetic Patterns

```yaml
sensors:
  # Multi-duration calculations
  complex_schedule:
    name: "Complex Schedule"
    formula: "date(base_date) + months(3) + weeks(2) + days(5)"
    variables:
      base_date: sensor.base_date # attribute reference
    metadata:
      device_class: "date"

  # Date arithmetic with conditional logic
  smart_maintenance:
    name: "Smart Maintenance"
    formula: "date(last_service) + (months(3) if is_critical else months(6))"
    variables:
      last_service: "sensor.last_service_date"
      is_critical: "binary_sensor.critical_equipment"
    metadata:
      device_class: "date"

  # Time zone calculations
  utc_conversion:
    name: "UTC Conversion"
    formula: "date(local_time) + hours(offset)"
    variables:
      local_time: sensor.local_timestamp # attribute reference
      offset: -5
    metadata:
      device_class: "timestamp"

  # Duration-based calculations
  energy_period:
    name: "Energy Period"
    formula: "now() - date(period_start) + days(1)"
    variables:
      period_start: sensor.energy_period_start # attribute reference
    metadata:
      unit_of_measurement: "days"
      device_class: "duration"
```

### Date Arithmetic with Collection Functions

```yaml
sensors:
  # Recent devices
  recent_devices:
    name: "Recent Devices"
    formula: "count(attribute:last_seen >= cutoff_date)"
    variables:
      cutoff_date: "2024-01-01T00:00:00Z"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:clock-check"

  # Maintenance due devices
  maintenance_due:
    name: "Maintenance Due"
    formula: "count(attribute:last_maintenance < cutoff_date)"
    variables:
      cutoff_date: "2024-01-01T00:00:00Z"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:wrench-clock"

  # Active devices in time window
  active_devices_window:
    name: "Active Devices in Window"
    formula: "count(attribute:last_seen >= window_start and attribute:last_seen <= window_end)"
    variables:
      window_start: "2024-01-01T00:00:00Z"
      window_end: "2024-01-31T23:59:59Z"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:calendar-clock"
```

## Collection Functions

Sum, average, or count entities dynamically using collection patterns with OR logic and exclusion support:

```yaml
sensors:
  # Basic collection patterns
  total_circuit_power:
    name: "Total Circuit Power"
    formula: "sum(regex:circuit_pattern)"
    variables:
      circuit_pattern: input_text.circuit_regex_pattern
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  # Collection with attribute comparisons - filter by thresholds
  high_power_devices:
    name: "High Power Devices"
    formula: "count("attribute:power_rating>=1000)"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:flash"

  # Collection with exclusions - exclude specific sensors
  power_without_kitchen:
    name: "Power Without Kitchen"
    formula: "sum(device_class:power, !"kitchen_oven", !"kitchen_fridge")"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  # Collection with pattern exclusions - exclude entire areas
  main_floor_power:
    name: "Main Floor Power"
    formula: "sum("device_class:power, !area:basement, !area:garage)"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  # OR patterns for multiple conditions
  security_monitoring:
    name: "Security Device Count"
    formula: "count(device_class:door|device_class:window|device_class:lock)"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:security"

  # Enhanced syntax examples with string containment
  room_devices:
    name: "Living Room Devices"
    formula: "count(attribute:name in 'Living')"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:sofa"

  # Version-based filtering
  updated_firmware:
    name: "Updated Firmware Devices"
    formula: "count(attribute:firmware_version>='v2.1.0')"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:update"

  # Enhanced syntax examples
  active_devices:
    name: "Active Devices"
    formula: "count(state:on|active|connected)"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:check-circle"

  # Complex collection with mixed exclusions
  filtered_power_analysis:
    name: "Filtered Power Analysis"
    formula: "avg(device_class:power, !high_power_device, !area:utility_room)"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
```

### Collection Negation

Use negation operators to exclude entities from collection functions:

```yaml
sensors:
  # Basic negation
  non_error_devices:
    name: "Non Error Devices"
    formula: "count(state!=error)"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:shield-check"

  # Multiple negations
  filtered_devices:
    name: "Filtered Devices"
    formula: "count(device_class:power !area:basement | !attribute:high_power_device)"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:filter"

  # Negation with patterns
  non_kitchen_power:
    name: "Non Kitchen Power"
    formula: "sum(device_class:power, !area:kitchen)"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  # Complex negation patterns
  selective_devices:
    name: "Selective Devices"
    formula: "count(device_class:sensor, !attribute:name in 'test', !area:utility)"
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:select"

  # Negation with multiple conditions
  filtered_analysis:
    name: "Filtered Analysis"
    formula: "avg(device_class:power, !state:off, !attribute:maintenance_mode:true)"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
```

**Available Functions:** `sum()`, `avg()`/`mean()`, `count()`, `min()`/`max()`, `std()`/`var()`

### Collection Patterns

- `"device_class:power"` - Entities with specific device class
- `"regex:pattern_variable"` - Entities matching regex pattern from variable (variable must reference an `input_text` entity)
- `"area:kitchen"` - Entities in specific area
- `"label:critical|important"` - Entities with specified label (pipe-separated OR logic)
- `"attribute:battery_level>=50"` - Entities with attribute conditions (supports `==`, `!=`, `<`, `<=`, `>`, `>=`)
- `"state:>=100|on"` - Entities with state conditions (supports all comparison operators and OR with `|`)
- `"attribute:name in 'Living'"` - String containment matching (supports `in`, `not in`)
- `"attribute:firmware_version>='v2.1.0'"` - Semantic version comparisons where version is in the form `vN.N.N`
- `"attribute:last_seen>='2024-01-01'"` - Datetime comparisons (ISO format)
- `"lower(attribute:name)=='living room'"` - Case-insensitive string comparisons
- `"trim(attribute:description)=='active device'"` - Normalized string comparisons
- `"contains(attribute:name, 'sensor')"` - Substring pattern matching
- `"startswith(attribute:name, 'living')"` - Prefix pattern matching
- `"endswith(attribute:name, 'meter')"` - Suffix pattern matching

### Exclusion Syntax

Collection functions support excluding entities using the `!` prefix:

- `sum("device_class:power", !"specific_sensor")` - Exclude specific sensor by entity ID
- `avg("area:kitchen", !"kitchen_oven", !"kitchen_fridge")` - Exclude multiple specific sensors
- `count("device_class:power", !"area:basement")` - Exclude all sensors in basement area
- `max("label:critical", !"device_class:diagnostic")` - Exclude all diagnostic device class sensors

### Calculations That Reference None, Unavailable, or Unknown States

Handle entities that are not ready gracefully in dependency chains by using UNAVAILABLE or UNKNOWN: Note that entities that
cannot be referenced are fatal errors and checked on YAML import.

**State Value Handling**:

- `None` values are `STATE_NONE` (Python None)
- `"unavailable"` values are `STATE_UNAVAILABLE`
- `"unknown"` values are `STATE_UNKNOWN`
- Missing entities raise `MissingDependencyError` (fatal)

```yaml
sensors:
  robust_dependency_sensor:
    name: "Robust Dependency Sensor"
    formula: "primary_source + backup_source" # Resolves to STATE_UNKNOWN if entities are unready...
    alternate_states:
      UNAVAILABLE: "fallback_calculation" # Use this calculation instead
    variables:
      primary_source: "sensor.primary_entity"
      backup_source: "sensor.backup_entity"
      fallback_calculation: "estimated_value"
      estimated_value: 100
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
```

## Alternate State Handling

Synthetic sensors support handling of `UNKNOWN`, `UNAVAILABLE`, `NONE`, and `FALLBACK` states through alternate state handling
formulas. Alternate handlers are grouped under the `alternate_states` key and support two shapes:

- Literal value: boolean/number/string returned directly (typed via the analyzer)
- Object with `formula:` and optional `variables:` evaluated via the standard pipeline

Examples:

```yaml
alternate_states:
  UNAVAILABLE: false
  UNKNOWN: 0
  NONE: None
  FALLBACK: 100
```

```yaml
alternate_states:
  UNAVAILABLE:
    formula: "backup + 1"
    variables:
      backup: 5
```

When a formula references an entity that is unavailable or unknown, you can specify alternative formulas to evaluate instead. If
no alternate state handlers are defined, the evaluation will proceed with the original values.

- **UNAVAILABLE**: Triggered when an entity is unavailable or doesn't exist
- **UNKNOWN**: Triggered when an entity exists but has an unknown state
- **NONE**: Triggered when an entity returns None (useful for energy sensors)
- **FALLBACK**: Catch-all handler for any alternate state when specific handlers aren't defined
- **Fallback chains**: Alternate formulas can reference other entities that may also have alternate handling
- **Nested handling**: Alternate formulas can themselves include alternate state handling
- **Variable scope**: Alternate formulas inherit the same variable scope as the main formula
- **Metadata**: Alternate formulas use the same metadata as the main formula

### Early Detection vs. Formula Evaluation

By default, alternate states are detected early during variable extraction and trigger handlers before formula evaluation. This
prevents evaluation errors and provides predictable behavior. You can control this behavior using the `allow_unresolved_states`
option:

```yaml
variables:
  within_grace:
    formula: "minutes_between(metadata(state, 'last_changed'), now()) < energy_grace_period_minutes"
    alternate_states:
      UNAVAILABLE: false
      UNKNOWN: false
    allow_unresolved_states: true # Allow alternate states to proceed into formula evaluation
```

**Behavior Options:**

- **`allow_unresolved_states: false`** (default): Alternate states are detected early during variable extraction and trigger
  handlers immediately
- **`allow_unresolved_states: true`**: Alternate states are allowed to proceed into formula evaluation, where they may trigger
  handlers based on evaluation results or exceptions

**Use Cases:**

- **Early detection** (default): Provides predictable, fast handling of alternate states without evaluation overhead
- **Formula evaluation**: Useful when you need the formula to process alternate states as part of complex calculations or when
  alternate states should only trigger handlers under specific evaluation conditions

### Alternate State Handling Examples

```yaml
version: "1.0"

global_settings:
  variables: # Global variables cannot have formulas
    global_factor: 0

sensors:
  power_analysis:
    name: "Power Analysis"
    formula: "missing_main_entity + 100"
    alternate_states:
      UNAVAILABLE: "fallback_main_value"
      UNKNOWN: "estimated_main_value * 2"
    variables:
      fallback_main_value: "50"
      estimated_main_value: "25"
      computed_adjustment:
        formula: "missing_sensor_a + missing_sensor_b"
        alternate_states:
          UNAVAILABLE: "backup_calculation"
          UNKNOWN: "conservative_estimate"
      backup_calculation:
        formula: "sensor.backup_entity * 0.8"
        alternate_states:
          UNAVAILABLE: "10"
      conservative_estimate: "5"
    attributes:
      efficiency:
        formula: "undefined_efficiency_sensor * 100"
        alternate_states:
          UNAVAILABLE: "estimated_efficiency"
        variables:
          estimated_efficiency: "82.5"
        metadata:
          unit_of_measurement: "%"
      health_score:
        formula: "undefined_health_metric"
        alternate_states:
          UNAVAILABLE: "calculated_health"
          UNKNOWN: "default_health"
        variables:
          calculated_health:
            formula: "state / 100 * 100"
            alternate_states:
              UNAVAILABLE: "baseline_health"
          baseline_health: "85"
          default_health: "75"
```

This example shows alternate state handling in:

- **Main sensor formulas** with alternative calculations using the `alternate_states` key
- **Computed variables** with nested alternate state handling
- **Attribute formulas** with independent fallback logic

Alternate state handling ensures your synthetic sensors remain functional even when dependencies are unavailable, providing
robust fallback mechanisms for critical calculations. Users can define custom behavior for each type of alternate state.
