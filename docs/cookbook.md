# HA Synthetic Sensors Cookbook

A guide to using HA Synthetic Sensors with detailed syntax examples and patterns.

## Table of Contents

- [Basic Sensor Configuration](#basic-sensor-configuration)
- [Variables and Configuration](#variables-and-configuration)
- [Attributes and Metadata](#attributes-and-metadata)
- [String Operations](#string-operations)
- [Date and Time Operations](#date-and-time-operations)
- [Collection Functions](#collection-functions)
- [Formula Examples](#formula-examples)
- [Exception Handling](#exception-handling)
- [Device Association](#device-association)

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

### Rich sensors with calculated attributes

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

## Variables and Configuration

Variables serve as aliases for entity IDs, collection patterns, or numeric literals, making formulas more readable and
maintainable.

### Variable Purpose and Scope

A variable serves as a short alias for an entity ID, collection pattern, numeric literal, or computed formula that it
references. They can be used in any formula in the main sensor or attribute.

Variables can be:

- **Entity IDs**: `"sensor.power_meter"` - References Home Assistant entities
- **Numeric Literals**: `42`, `3.14`, `-5.0` - Direct numeric values for constants
- **Collection Patterns**: `"device_class:temperature"` - Dynamic entity aggregation
- **Computed Variables**: Formulas that calculate values dynamically with dependency ordering

**Variable Scope**: Variables can be defined at both the sensor level and attribute level:

- **Sensor-level variables**: Defined in the main sensor's `variables` section and available to all formulas
- **Attribute-level variables**: Defined in an attribute's `variables` section and available only to that attribute
- **Variable inheritance**: Attributes inherit all sensor-level variables and can add their own
- **Variable precedence**: Attribute-level variables with the same name override sensor-level variables for that attribute

### Literal Attribute Values

Attributes can be defined as literal values without requiring formulas. This is useful for static information like device
specifications, constants, or metadata that doesn't need calculation:

```yaml
sensors:
  device_info_sensor:
    name: "Device Information"
    formula: "current_power * efficiency_factor"
    variables:
      current_power: "sensor.power_meter"
      efficiency_factor: 0.95
    attributes:
      # Literal values - no formula required
      voltage: 240
      manufacturer: "TestCorp"
      model: "PowerMeter Pro"
      serial_number: "PM-2024-001"
      max_capacity: 5000
      installation_date: "2024-01-15"
      warranty_years: 5
      is_active: True
      firmware_version: "2.1.0"
      last_updated: "now()"
      tracking_since: "today()"

      # Mixed literal and calculated attributes
      calculated_power:
        formula: "state * 1.1"
        metadata:
          unit_of_measurement: "W"
          suggested_display_precision: 0
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
```

**Supported Literal Types:**

- **Numeric values**: `42`, `3.14`, `-5.0`, `1.23e-4`
- **String values**: `"test_string"`, `"Hello World"`, `""` (empty string)
- **Boolean values**: `True`, `False`
- **Special characters**: `"test@#$%^&*()"`, `"测试"` (Unicode)
- **Datetime functions**: `now()`, `today()`, `yesterday()`, `tomorrow()`, `utc_now()`, `utc_today()`, `utc_yesterday()`

### Computed Variables

Variables can contain formulas that calculate values dynamically:

```yaml
sensors:
  energy_analysis:
    name: "Energy Analysis"
    formula: "final_total"
    variables:
      # Simple variables
      grid_power: "sensor.grid_meter"
      solar_power: "sensor.solar_inverter"
      efficiency_factor: 0.85

      # Computed variables with dependency ordering
      total_power:
        formula: "grid_power + solar_power"
      efficiency_percent:
        formula: "solar_power / total_power * 100"
      final_total:
        formula: "total_power * efficiency_factor"

    attributes:
      daily_projection:
        formula: "state * 24" # Uses main sensor result
        metadata:
          unit_of_measurement: "Wh"
          device_class: "energy"
      cost_analysis:
        formula: "state * rate"
        variables:
          rate: 0.12
        metadata:
          unit_of_measurement: "¢"
          suggested_display_precision: 2
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
```

## Attributes and Metadata

### How attributes work

- Main sensor state is calculated _first_ using the `formula`
- Attributes are calculated _second_ and have access to the sensor `state` variable
- Attribute `state` tokens refers to the _calculated_ main sensor state
- Attributes can reference other attributes
- Attributes can define their own `variables` section for attribute-specific entity references or use the main sensors
  variables
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

- The main sensor state is set to the value of the backing entity or the previous HA sensor state (accessed via the `state`
  token).
- The `daily_total` attribute is calculated as the main state times 24.
- The `with_multiplier` attribute is calculated as the main state times a custom multiplier (2.5).
- Both attribute formulas use the `state` variable, which is the freshly calculated main sensor value.

### Metadata Function

The `metadata()` function provides access to Home Assistant entity metadata properties. This allows you to retrieve
information about entity state changes, entity IDs, and other metadata.

**Syntax:**

```yaml
metadata(entity_reference, 'metadata_key')
```

**Available Metadata Keys:**

- `last_changed` - When the entity state last changed
- `last_updated` - When the entity was last updated
- `entity_id` - Full entity ID (e.g., "sensor.power_meter", not useful)
- `domain` - Entity domain (e.g., "sensor", "switch")
- `object_id` - Entity object ID (e.g., "power_meter")
- `friendly_name` - Entity friendly name

**Examples:**

```yaml
sensors:
  # Data staleness detection
  power_data_freshness:
    name: "Power Data Freshness"
    formula: "(now() - metadata(power_entity, 'last_changed')) < hours(1) ? 1 : 0"
    variables:
      power_entity: "sensor.power_meter"
    metadata:
      unit_of_measurement: "binary"

  # Entity domain validation
  entity_type_check:
    name: "Entity Type Validation"
    formula: "metadata(sensor.temp_probe, 'domain') == 'sensor' ? 1 : 0"
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
        formula: "metadata(power_sensor, 'friendly_name')"
      data_age_minutes:
        formula: "(now() - metadata(power_sensor, 'last_changed')) / minutes(1)"
        metadata:
          unit_of_measurement: "min"
          suggested_display_precision: 1
      is_recent:
        formula: "metadata(power_sensor, 'last_updated') > (now() - minutes(5)) ? 'Yes' : 'No'"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"

  # State token for current sensor metadata
  self_reference_metadata:
    name: "Self Reference Metadata"
    entity_id: "sensor.power_meter"

    formula: "metadata(state, 'object_id')" # Uses state token for current sensor
    metadata:
      unit_of_measurement: ""
```

**Entity Reference Types:**

- **Variable names**: `metadata(power_entity, 'entity_id')` - Uses variable that resolves to entity ID
- **Direct entity IDs**: `metadata(sensor.power_meter, 'last_changed')` - Direct entity reference
- **State token**: `metadata(state, 'entity_id')` - References the current sensor's backing entity
- **Global variables**: `metadata(external_sensor, 'domain')` - Uses global variable reference

### Metadata Dictionary

The `metadata` dictionary provides extensible support for all Home Assistant sensor properties. This metadata is added
directly to the sensor when the sensor is created in Home Assistant.

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

### Global YAML Settings

Global settings allow you to define common configuration that applies to all sensors in a YAML file, reducing duplication
making sensor sets easier to manage:

```yaml
version: "1.0"

global_settings:
  device_identifier: "njs-abc-123"
  variables:
    electricity_rate: "input_number.electricity_rate_cents_kwh"
    base_power_meter: "sensor.span_panel_instantaneous_power"
    conversion_factor: 1000
  metadata:
    # Common metadata applied to all sensors
    attribution: "Data from SPAN Panel"
    entity_registry_enabled_default: true
    suggested_display_precision: 2

sensors:
  # These sensors inherit global settings
  current_power:
    name: "Current Power"
    # No device_identifier needed - inherits from global_settings
    formula: "base_power_meter"
    # No variables needed - inherits from global_settings
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
      # Inherits attribution, entity_registry_enabled_default, suggested_display_precision from global

  energy_cost:
    name: "Energy Cost"
    # No device_identifier needed - inherits from global_settings
    formula: "base_power_meter * electricity_rate / conversion_factor"
    # Uses global variables: base_power_meter, electricity_rate, conversion_factor
    metadata:
      unit_of_measurement: "¢/h"
      state_class: "measurement"
```

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

### String Operation Examples

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

**Duration Functions:**

- `seconds(n)` - Duration in seconds
- `minutes(n)` - Duration in minutes
- `hours(n)` - Duration in hours
- `days(n)` - Duration in days
- `weeks(n)` - Duration in weeks
- `months(n)` - Duration in months (average 30.44 days)

### Date Arithmetic Examples

```yaml
sensors:
  # Sensor using datetime functions in formulas
  power_analysis:
    name: "Power Analysis"
    formula: "now() > yesterday() ? current_power : 0"
    variables:
      current_power: "sensor.span_panel_instantaneous_power"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  # Sensor with datetime variables and attributes
  energy_tracking:
    name: "Energy Tracking"
    formula: "daily_energy * efficiency_factor"
    variables:
      daily_energy: "sensor.daily_energy_consumption"
      efficiency_factor: 0.95
      start_date: "today()"
      last_updated: "now()"
    attributes:
      tracking_since:
        formula: "start_date"
        metadata:
          device_class: "timestamp"
      last_calculation:
        formula: "last_updated"
        metadata:
          device_class: "timestamp"
      is_active_today:
        formula: "now() >= today() and now() < tomorrow()"
        metadata:
          device_class: "timestamp"
    metadata:
      unit_of_measurement: "kWh"
      device_class: "energy"
      state_class: "total"

  # Date arithmetic with explicit duration functions
  maintenance_schedule:
    name: "Next Maintenance"
    formula: "date(last_service_date) + months(6)"
    variables:
      last_service_date: "sensor.last_maintenance_date"
    metadata:
      device_class: "date"

  # Device uptime calculation
  device_uptime:
    name: "Device Uptime"
    formula: "date(now()) - date(state.last_changed)"
    metadata:
      unit_of_measurement: "days"
      device_class: "duration"

  # Recent activity monitoring
  recent_activity:
    name: "Recent Activity"
    formula: "count(state.last_changed >= date(now()) - hours(24))"
    metadata:
      unit_of_measurement: "events"
```

### Date Arithmetic Patterns

```yaml
sensors:
  # Add time to dates
  future_date:
    name: "Future Date"
    formula: "date('2025-01-01') + days(30)" # January 31st, 2025
    metadata:
      device_class: "date"

  # Subtract time from dates
  past_date:
    name: "Past Date"
    formula: "date(now()) - weeks(2)" # 2 weeks ago
    metadata:
      device_class: "date"

  # Calculate date differences
  days_since_created:
    name: "Days Since Created"
    formula: "date(now()) - date(created_timestamp)" # Days between dates
    metadata:
      unit_of_measurement: "days"
      device_class: "duration"

  # Multi-duration calculations
  project_deadline:
    name: "Project Deadline"
    formula: "date(start_date) + weeks(4) + days(3)" # 4 weeks 3 days later
    metadata:
      device_class: "date"

  # Conditional date arithmetic
  maintenance_overdue:
    name: "Maintenance Overdue"
    formula: "date(now()) > date(last_service) + months(12) ? 1 : 0"
    metadata:
      unit_of_measurement: "binary"
      icon: "mdi:alert"
```

## Collection Functions

Sum, average, or count entities dynamically using collection patterns with OR logic and exclusion support:

```yaml
sensors:
  # Basic collection patterns
  total_circuit_power:
    name: "Total Circuit Power"
    formula: sum("regex:circuit_pattern")
    variables:
      circuit_pattern: "input_text.circuit_regex_pattern"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  # Collection with attribute comparisons - filter by thresholds
  high_power_devices:
    name: "High Power Devices"
    formula: count("attribute:power_rating>=1000")
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:flash"

  # Collection with exclusions - exclude specific sensors
  power_without_kitchen:
    name: "Power Without Kitchen"
    formula: sum("device_class:power", !"kitchen_oven", !"kitchen_fridge")
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  # Collection with pattern exclusions - exclude entire areas
  main_floor_power:
    name: "Main Floor Power"
    formula: sum("device_class:power", !"area:basement", !"area:garage")
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  # OR patterns for multiple conditions
  security_monitoring:
    name: "Security Device Count"
    formula: count("device_class:door|device_class:window|device_class:lock")
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:security"

  # Enhanced syntax examples with string containment
  room_devices:
    name: "Living Room Devices"
    formula: count("attribute:name in 'Living'")
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:sofa"

  # Version-based filtering
  updated_firmware:
    name: "Updated Firmware Devices"
    formula: count("attribute:firmware_version>='v2.1.0'")
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:update"

  # Enhanced syntax examples
  active_devices:
    name: "Active Devices"
    formula: count("state:on|active|connected")
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:check-circle"

  # Complex collection with mixed exclusions
  filtered_power_analysis:
    name: "Filtered Power Analysis"
    formula: avg("device_class:power", !"high_power_device", !"area:utility_room")
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

### Syntax Reference

| Pattern Type     | Explicit Syntax                                        | Shorthand Syntax                       | Negation Syntax              |
| ---------------- | ------------------------------------------------------ | -------------------------------------- | ---------------------------- |
| **State**        | `"state:==on \| !=off \| >=50"`                        | `"state:on \| !off \| >=50"`           | `"state:!off \| !inactive"`  |
| **Attribute**    | `"battery_level>=50 \| status==active"`                | `"battery_level>=50 \| status:active"` | `"battery_level:!<20"`       |
| **String**       | `"name in 'Living' \| manufacturer not in 'Test'"`     | `"name:Living \| manufacturer:!Test"`  | `"name:!'Kitchen'"`          |
| **String Func**  | `"lower(name)=='living' \| contains(name, 'sensor')"`  | `"lower(name):living"`                 | `"contains(name):!sensor"`   |
| **Version**      | `"firmware_version>='v2.1.0' \| app_version<'v3.0.1'"` | `"firmware_version:>=v2.1.0"`          | `"version:!<v1.0.1"`         |
| **DateTime**     | `"last_seen>='2024-01-01T00:00:00Z'"`                  | `"last_seen:>=2024-01-01"`             | `"updated_at:!<yesterday"`   |
| **Device Class** | `"device_class:power \| device_class:energy"`          | `"device_class:power \| energy"`       | `"device_class:!diagnostic"` |
| **Area**         | `"area:kitchen \| area:living_room"`                   | `"area:kitchen \| living_room"`        | `"area:!basement"`           |
| **Label**        | `"label:critical \| label:important"`                  | `"label:critical \| important"`        | `"label:!deprecated"`        |

## Formula Examples

### Conditional Expressions (Ternary Operator)

Use Python's conditional syntax for dynamic calculations based on conditions:

```yaml
sensors:
  # Power direction detection (1=importing, -1=exporting, 0=balanced)
  power_flow:
    name: "Power Flow Direction"
    formula: "1 if grid_power > 100 else -1 if grid_power < -100 else 0"
    variables:
      grid_power: "sensor.grid_power"
    metadata:
      unit_of_measurement: "direction"
      icon: "mdi:transmission-tower"

  # Dynamic energy pricing
  current_rate:
    name: "Current Energy Rate"
    formula: "peak_rate if is_peak_hour else off_peak_rate"
    variables:
      peak_rate: "input_number.peak_electricity_rate"
      off_peak_rate: "input_number.off_peak_electricity_rate"
      is_peak_hour: "binary_sensor.peak_hours"
    metadata:
      unit_of_measurement: "¢/kWh"
      device_class: "monetary"

  # String-based conditional formatting
  device_status_display:
    name: "Device Status Display"
    formula: "'ON' if device_state == 'on' else 'OFF' if device_state == 'off' else 'UNKNOWN'"
    variables:
      device_state: "sensor.device_state"
    metadata:
      icon: "mdi:lightbulb"

  # Date-based conditional logic
  maintenance_overdue:
    name: "Maintenance Overdue"
    formula: "1 if date(now()) > date(last_service) + months(12) else 0"
    variables:
      last_service: "sensor.last_maintenance_date"
    metadata:
      unit_of_measurement: "binary"
      icon: "mdi:alert"
```

### Logical Operators

Combine conditions using `and`, `or`, and `not` for energy management:

```yaml
sensors:
  # Optimal battery charging conditions
  should_charge_battery:
    name: "Battery Charging Recommended"
    formula: "solar_available and battery_low and not peak_hours"
    variables:
      solar_available: "binary_sensor.solar_producing"
      battery_low: "binary_sensor.battery_below_threshold"
      peak_hours: "binary_sensor.peak_electricity_hours"
    metadata:
      device_class: "power"

  # Load balancing decision
  high_demand_alert:
    name: "High Demand Alert"
    formula: "total_load > 8000 or (battery_low and grid_expensive)"
    variables:
      total_load: "sensor.total_house_load"
      battery_low: "binary_sensor.battery_needs_charging"
      grid_expensive: "binary_sensor.high_electricity_rates"
    metadata:
      icon: "mdi:alert"
```

### Membership Testing with 'in' Operator

Test values against lists or ranges for energy monitoring:

```yaml
sensors:
  # Check if current power is in normal operating range (1=normal, 0=abnormal)
  power_status:
    name: "Power Status"
    formula: "1 if current_power in normal_range else 0"
    variables:
      current_power: "sensor.main_panel_power"
      normal_range: [1000, 1500, 2000, 2500, 3000] # Acceptable power levels
    metadata:
      unit_of_measurement: "binary"
      icon: "mdi:gauge"

  # Voltage quality assessment (1=good, 0=poor)
  voltage_quality:
    name: "Voltage Quality"
    formula: "1 if voltage in [230, 240, 250] else 0"
    variables:
      voltage: "sensor.main_voltage"
    metadata:
      unit_of_measurement: "binary"
      icon: "mdi:sine-wave"

  # String containment testing
  device_type_check:
    name: "Device Type Check"
    formula: "1 if device_type in ['sensor', 'switch', 'light'] else 0"
    variables:
      device_type: "sensor.device_type"
    metadata:
      unit_of_measurement: "binary"
      icon: "mdi:devices"

  # String pattern matching with functions
  living_area_devices:
    name: "Living Area Devices"
    formula: "1 if contains(lower(device_name), 'living') else 0"
    variables:
      device_name: "sensor.device_name"
    metadata:
      unit_of_measurement: "binary"
      icon: "mdi:home"
```

### Boolean State Conversion

Home Assistant's boolean states are automatically converted to numeric values for use in formulas:

```yaml
sensors:
  device_activity_score:
    name: "Device Activity Score"
    formula: "motion_sensor * 10 + door_sensor * 5 + switch_state * 2"
    variables:
      motion_sensor: "binary_sensor.living_room_motion" # "motion" → 1.0, "clear" → 0.0
      door_sensor: "binary_sensor.front_door" # "open" → 1.0, "closed" → 0.0
      switch_state: "switch.living_room_light" # "on" → 1.0, "off" → 0.0
    metadata:
      unit_of_measurement: "points"
      icon: "mdi:chart-line"
```

**Boolean State Types:**

- `True` states: `on`, `true`, `yes`, `open`, `motion`, `armed_*`, `home`, `active`, `connected` → `1.0`
- `False` states: `off`, `false`, `no`, `closed`, `clear`, `disarmed`, `away`, `inactive`, `disconnected` → `0.0`

### Available Mathematical Functions

- Basic: `abs()`, `round()`, `floor()`, `ceil()`
- Math: `sqrt()`, `pow()`, `sin()`, `cos()`, `tan()`, `log()`, `exp()`
- Statistics: `min()`, `max()`, `avg()`, `mean()`, `sum()`
- Utilities: `clamp(value, min, max)`, `map(value, in_min, in_max, out_min, out_max)`, `percent(part, whole)`

## Exception Handling

Synthetic sensors support graceful handling of `UNKNOWN` and `UNAVAILABLE` states through exception handling formulas. When a
formula references an entity that is unavailable or unknown, you can specify alternative formulas to evaluate instead.

- **UNAVAILABLE**: Triggered when an entity is unavailable or doesn't exist
- **UNKNOWN**: Triggered when an entity exists but has an unknown state
- **Fallback chains**: Exception formulas can reference other entities that may also have exceptions
- **Nested handling**: Exception formulas can themselves include exception handling
- **Variable scope**: Exception formulas inherit the same variable scope as the main formula
- **Metadata**: Exception formulas use the same metadata as the main formula

### Exception Handling Examples

```yaml
version: "1.0"

global_settings:
  variables: # Global variables cannot have formulas
    global_factor: 0

sensors:
  power_analysis:
    name: "Power Analysis"
    formula: "missing_main_entity + 100"
    UNAVAILABLE: "fallback_main_value"
    UNKNOWN: "estimated_main_value * 2"
    variables:
      fallback_main_value: "50"
      estimated_main_value: "25"
      computed_adjustment:
        formula: "missing_sensor_a + missing_sensor_b"
        UNAVAILABLE: "backup_calculation"
        UNKNOWN: "conservative_estimate"
      backup_calculation:
        formula: "sensor.backup_entity * 0.8"
        UNAVAILABLE: "10"
      conservative_estimate: "5"
    attributes:
      efficiency:
        formula: "undefined_efficiency_sensor * 100"
        UNAVAILABLE: "estimated_efficiency"
        variables:
          estimated_efficiency: "82.5"
        metadata:
          unit_of_measurement: "%"
      health_score:
        formula: "undefined_health_metric"
        UNAVAILABLE: "calculated_health"
        UNKNOWN: "default_health"
        variables:
          calculated_health:
            formula: "state / 100 * 100"
            UNAVAILABLE: "baseline_health"
          baseline_health: "85"
          default_health: "75"
```

This example shows exception handling in:

- **Main sensor formulas** with alternative calculations
- **Computed variables** with nested exception handling
- **Attribute formulas** with independent fallback logic

Exception handling ensures your synthetic sensors remain functional even when dependencies are unavailable, providing robust
fallback mechanisms for critical calculations.

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
- **Existing devices**: If a device already exists, the sensor will be associated with it (additional device fields are
  ignored)
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
