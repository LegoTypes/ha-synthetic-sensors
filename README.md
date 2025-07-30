# HA Synthetic Sensors

[![GitHub Release](https://img.shields.io/github/v/release/SpanPanel/ha-synthetic-sensors?style=flat-square)](https://github.com/SpanPanel/ha-synthetic-sensors/releases)
[![PyPI Version](https://img.shields.io/pypi/v/ha-synthetic-sensors?style=flat-square)](https://pypi.org/project/ha-synthetic-sensors/)
[![Python Version](https://img.shields.io/pypi/pyversions/ha-synthetic-sensors?style=flat-square)](https://pypi.org/project/ha-synthetic-sensors/)
[![License](https://img.shields.io/github/license/SpanPanel/ha-synthetic-sensors?style=flat-square)](https://github.com/SpanPanel/ha-synthetic-sensors/blob/main/LICENSE)

[![CI Status](https://img.shields.io/github/actions/workflow/status/SpanPanel/ha-synthetic-sensors/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/SpanPanel/ha-synthetic-sensors/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/codecov/c/github/SpanPanel/ha-synthetic-sensors?style=flat-square)](https://codecov.io/gh/SpanPanel/ha-synthetic-sensors)
[![Code Quality](https://img.shields.io/codefactor/grade/github/SpanPanel/ha-synthetic-sensors?style=flat-square)](https://www.codefactor.io/repository/github/spanpanel/ha-synthetic-sensors)
[![Security](https://img.shields.io/snyk/vulnerabilities/github/SpanPanel/ha-synthetic-sensors?style=flat-square)](https://snyk.io/test/github/SpanPanel/ha-synthetic-sensors)

[![Pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&style=flat-square)](https://github.com/pre-commit/pre-commit)
[![Linting: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)
[![Type Checking: MyPy](https://img.shields.io/badge/type%20checking-mypy-blue?style=flat-square)](https://mypy-lang.org/)

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-support%20development-FFDD00?style=flat-square&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/cayossarian)

A Python package for creating formula-based synthetic sensors in Home Assistant integrations using YAML configuration and
mathematical expressions.

## Overview: How Synthetic Sensors Work

Synthetic sensors are **sensor extensions** that provide capabilities beyond the base sensors or create new sensors with
formula-based calculations. They provide a new state value by applying mathematical formulas to other entities, allowing you
to:

- **Extend sensor capabilities** with calculated attributes
- **Transform sensor values** using mathematical formulations
- **Combine multiple sensors** into derived metrics
- **Add computed states** without modifying original sensors
- **Add computed attributes** that evaluate based on the main sensor state or other entities

### Data Sources for Synthetic Sensors

Synthetic sensors calculate their state using formulas that reference other sensor data. **The formula determines the
synthetic sensor's final state value** - there is no requirement for a single "backing entity." Instead, synthetic sensors
can:

- **Use a dedicated state backing entity** (referenced via `state` token) as the primary data source
- **Combine multiple existing sensors or attributes** using their entity IDs in formulas
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

### Synthetic Benefits

- **No modification** of original sensors or integrations required
- **Dynamic formulas** can be updated without code changes (via YAML)
- **Selective updates** - only affected sensors recalculate when dependencies change
- **Clean architecture** - separates data provision from sensor presentation
- **Cross-integration** capabilities for combining data from multiple sources

## What it does

- **Creates formula-based sensors** from mathematical expressions
- **YAML configuration** for easy sensor definition and management
- **Advanced dependency resolution** with automatic entity discovery
- **Storage-based configuration** with runtime modification capabilities
- **Variable support** for reusable calculations and shared configuration
- **Dynamic entity aggregation** using regex, label, areas, and device class patterns
- **Comprehensive caching** with AST compilation for optimal performance
- **Integration with Home Assistant** device and entity registries

## Key Features

- **Sensor Definition and Modification**: Without code modification change the sensor or attribute state with YAML
- **Bulk Load/Modify and Per-Sensor CRUD**: Load complete sensor sets or make granular changes
- **Rich Formuala Based States**: Formulas with natural syntax and powerful evaluation and collection patterns
- **Variable reuse**: Define variables globally or per sensor and use those vairables in formulas or attributes
- **Dot notation**: Easy access to entity attributes in formulas
- **Automatic Entity-ID Tracking**: Updates the definitions based on external HA entity renaming
- **Type safety**: Complete TypedDict interfaces for better IDE support and validation
- **Storage-first architecture**: Runtime configuration changes without file modifications
- **Built for Performance**: AST caching and evaluation of formulas and bulk modification event storm avoidance

## Installation

Install the package using pip:

```bash
pip install ha-synthetic-sensors
```

For development setup:

```bash
git clone https://github.com/SpanPanel/ha-synthetic-sensors
cd ha-synthetic-sensors
poetry install --with dev
./setup-hooks.sh
```

**Note**: The `setup-hooks.sh` script ensures pre-commit hooks are installed correctly to avoid migration mode issues.

## Getting Started

For detailed implementation examples, API documentation, and integration patterns, see the
[Integration Guide](docs/Synthetic_Sensors_Integration_Guide.md).

The package provides a public API:

- **StorageManager** - Manages sensor set storage and configuration
- **SensorSet** - Handle for individual sensor set operations
- **FormulaConfig/SensorConfig** - Configuration classes for sensors and formulas
- **DataProviderResult** - Type definition for data provider callbacks

## YAML Configuration Introduction

**Required YAML Structure:** All YAML configuration files must start with a version declaration.

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
      state_class: "measurement"
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
      state_class: "measurement"
      icon: "mdi:currency-usd"
      attribution: "Calculated from SPAN Panel data"
```

## Variables and Configuration

Variables serve as aliases for entity IDs, collection patterns, or numeric literals, making formulas more readable and
maintainable.

### Variable Purpose and Scope

A variable serves as a short alias for an entity ID, collection pattern, or numeric literal that it references. They can be
used in any formula in the main sensor or attribute.

Variables can be:

- **Entity IDs**: `"sensor.power_meter"` - References Home Assistant entities
- **Numeric Literals**: `42`, `3.14`, `-5.0` - Direct numeric values for constants
- **Collection Patterns**: `"device_class:temperature"` - Dynamic entity aggregation

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

**Literal vs Formula Attributes:**

- **Literal attributes**: Static values that don't change based on sensor state
- **Formula attributes**: Calculated values that depend on sensor state or other entities
- **Mixed usage**: Both literal and formula attributes can be used together in the same sensor

## How attributes work

- Main sensor state is calculated _first_ using the `formula`
- Attributes are calculated _second_ and have access to the sensor `state` variable
- Attribute `state` tokens refers to the _caclulated_ main sensor state
- Attributres can reference other attributes
- Attributes can define their own `variables` section for attribute-specific entity references or use the main sensors
  variables
- Attributes can define their onw `formula` section
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

### Metadata Dictionary

The `metadata` dictionary provides extensible support for all Home Assistant sensor propertiesl. This metadata is added
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

**Metadata Extensibility:**

- Any additional properties are passed through to Home Assistant
- Custom properties can be added for integration-specific needs
- Properties are validated against Home Assistant's entity model

## Metadata Architecture

### Metadata Inheritance Rules

The metadata system follows a clear hierarchy:

1. **Global Metadata** (lowest precedence): Defined in `global_settings.metadata`
   - Applied to all sensors in the YAML file
   - Only affects sensors, never attributes

2. **Sensor Metadata** (medium precedence): Defined in sensor `metadata` section
   - Overrides global metadata for the same property
   - Merged with global metadata during sensor creation

3. **Attribute Metadata** (independent): Defined in attribute `metadata` section
   - Completely independent from global and sensor metadata
   - No inheritance or merging with sensor-level metadata

### Validation Rules

**Entity-Only Properties:** These properties are only valid for sensors and will cause validation errors if used in attribute
metadata:

- **Device Properties**: `device_class`, `state_class`
- **Registry Properties**: `entity_category`, `entity_registry_enabled_default`, `entity_registry_visible_default`
- **Behavior Properties**: `assumed_state`, `last_reset`, `force_update`, `available`, `options`

**Attribute-Safe Properties:** These properties are valid for both sensors and attributes:

- **Display Properties**: `unit_of_measurement`, `icon`, `suggested_display_precision`, `suggested_unit_of_measurement`
- **Attribution**: `attribution`
- **Custom Properties**: Any custom properties specific to your integration

**Example of Validation Errors:**

```yaml
sensors:
  power_sensor:
    name: "Power Sensor"
    formula: "base_power"
    metadata:
      device_class: "power" # Valid for sensors
      unit_of_measurement: "W"
    attributes:
      daily_total:
        formula: "state * 24"
        metadata:
          unit_of_measurement: "Wh" # Valid for attributes
          device_class: "energy" # ERROR: Not allowed for attributes
```

**Attribute Metadata:** Attributes define their own metadata independently. Attributes cannot use entity-specific metadata
properties:

```yaml
attributes:
  daily_total:
    formula: "state * 24"
    metadata:
      unit_of_measurement: "kWh"
      suggested_display_precision: 3
      icon: "mdi:lightning-bolt"
      # device_class: "energy"  # ERROR: Not allowed for attributes
```

**Attribute Metadata Restrictions:** The following properties are only valid for sensors, not attributes:

- `device_class`, `state_class`, `entity_category`
- `entity_registry_enabled_default`, `entity_registry_visible_default`
- `assumed_state`, `last_reset`, `force_update`, `available`, `options`

Attempting to use these properties in attribute metadata will cause validation errors.

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

  mixed_variables_sensor:
    name: "Mixed Variables"
    # No device_identifier needed - inherits from global_settings
    formula: "base_power_meter + local_adjustment"
    variables:
      local_adjustment: "sensor.local_adjustment_value"
    # Uses base_power_meter from global, local_adjustment from local
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
```

**Supported Global Settings:**

- **`device_identifier`**: Applied to sensors that don't specify their own device_identifier
- **`variables`**: Available to all sensors in the YAML file
- **`metadata`**: Applied to all sensors, with sensor-level metadata taking precedence

**Global Metadata Inheritance:**

- Global metadata applies only to sensors, not attributes
- Sensor-level metadata overrides global metadata for the same property
- Attributes define their own metadata independently with no inheritance
- Global metadata is merged at the sensor level during sensor creation

**Variable Conflict Rules:**

- Global and sensor variables with the same name **must have identical values**
- Different values for the same variable name cause validation errors
- Use different variable names to avoid conflicts

**Metadata Architecture:**

- **Global metadata**: Applied to all sensors in the YAML file at runtime
- **Sensor metadata**: Overrides global metadata for specific sensors
- **Attribute metadata**: Independent of global and sensor metadata
- **Validation**: Entity-only properties rejected in attribute metadata

## Entity Reference Patterns

| Pattern Type                 | Syntax                    | Example                         | Use Case                             |
| ---------------------------- | ------------------------- | ------------------------------- | ------------------------------------ |
| **Direct Entity ID**         | `sensor.entity_name`      | `sensor.power_meter`            | Quick references, cross-sensor       |
| **Variable Alias**           | `variable_name`           | `power_meter`                   | Most common, clean formulas          |
| **State Alias (attributes)** | `state`                   | `state * 24`                    | In attributes, reference main sensor |
| **Attribute Dot Notation**   | `entity.attribute`        | `sensor1.battery_level`         | Access entity attributes             |
| **Collection Functions**     | `mathFunc(pattern:value)` | `sum(device_class:temperature)` | Aggregate entities by pattern        |

**Entity ID Generation**:

- **With device association**: `sensor.{device_prefix}_{sensor_key}` where device_prefix is auto-generated from the device
  name
- **Without device association**: `sensor.{sensor_key}`
- **Explicit override**: Use the optional `entity_id` field to specify exact entity ID

**Cross-Sensor References**:

Cross-sensor references work through **variable aliases**, not direct sensor key references. To reference other synthetic
sensors, define them as variables:

```yaml
sensors:
  base_power:
    name: "Base Power"
    formula: "1000"

  derived_power:
    name: "Derived Power"
    formula: "base_power * 1.1" # Equivalent to "sensor.base_power * 1.1"
    variables:
      base_power: "sensor.base_power" # Alias to base_power sensor
```

**Device prefix examples:**

- Device "SPAN Panel Main" → entity `sensor.span_panel_main_power`
- Device "Solar Inverter" → entity `sensor.solar_inverter_efficiency`

### Variable Purpose and Scope

A variable serves as a short alias for an entity ID, collection pattern, or numeric literal that it references.

Variables can be:

- **Entity IDs**: `"sensor.power_meter"` - References Home Assistant entities
- **Numeric Literals**: `42`, `3.14`, `-5.0` - Direct numeric values for constants
- **Collection Patterns**: `"device_class:temperature"` - Dynamic entity aggregation

**Variable Scope**: Variables can be defined at both the sensor level and attribute level:

- **Sensor-level variables**: Defined in the main sensor's `variables` section and available to all formulas
- **Attribute-level variables**: Defined in an attribute's `variables` section and available only to that attribute
- **Variable inheritance**: Attributes inherit all sensor-level variables and can add their own
- **Variable precedence**: Attribute-level variables with the same name override sensor-level variables for that attribute

Once defined, variables can be used in any formula whether in the main sensor state formula or attribute formulas.

Attribute formulas inherit all variables from their parent sensor and can define additional ones:

```yaml
sensors:
  energy_analysis:
    name: "Energy Analysis"
    formula: "grid_power + solar_power"
    variables:
      grid_power: "sensor.grid_meter"
      solar_power: "sensor.solar_inverter"
      efficiency_factor: 0.85 # Numeric literal: efficiency constant
      tax_rate: 0.095 # Numeric literal: tax percentage
    attributes:
      daily_projection:
        formula: "energy_analysis * 24" # References main sensor by key
        metadata:
          unit_of_measurement: "Wh"
          device_class: "energy"
      efficiency_percent:
        formula: "solar_power / (grid_power + solar_power) * efficiency_factor * 100"
        metadata:
          unit_of_measurement: "%"
          suggested_display_precision: 1
      cost_with_tax:
        formula: "energy_analysis * (1 + tax_rate)" # Uses sensor-level variable
        metadata:
          unit_of_measurement: "¢"
          suggested_display_precision: 2
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
```

```yaml
sensors:
  # Mixed data sources - integration data + HA entities
  power_analysis:
    name: "Power Analysis"
    # This formula uses both integration-provided data and HA entities
    formula: "local_meter_power + grid_power + solar_power"
    variables:
      local_meter_power: "span.meter_001" # From integration callback
      grid_power: "sensor.grid_power" # From Home Assistant
      solar_power: "sensor.solar_inverter" # From Home Assistant
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  # Purely integration data
  internal_efficiency:
    name: "Internal Efficiency"
    formula: "internal_sensor_a / internal_sensor_b * 100"
    variables:
      internal_sensor_a: "span.efficiency_input" # From integration
      internal_sensor_b: "span.efficiency_baseline" # From integration
    metadata:
      unit_of_measurement: "%"
      suggested_display_precision: 1
```

**Data Source Resolution:**

- If integration registers entity IDs like `["span.meter_001", "span.efficiency_input", "span.efficiency_baseline"]`
- Evaluator calls `data_provider_callback` for those entities
- All other entities (`sensor.grid_power`, `sensor.solar_inverter`) use standard HA state queries
- Completely transparent to YAML configuration - same syntax for both data sources

### Collection Functions (Entity Aggregation)

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
    formula: count("attribute:firmware_version>='2.1.0'")
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

**Comparison Capabilities:**

- **Numeric**: Standard comparisons (`==`, `!=`, `<`, `<=`, `>`, `>=`) for integers and floats
- **String**: Equality (`==`, `!=`) and containment (`in`, `not in`) operations
- **DateTime**: Full comparisons with ISO datetime strings and datetime objects
- **Version**: Semantic version comparisons (e.g., `"2.1.0" > "1.5.3"`)
- **Type-safe**: Explicit errors for unsupported type combinations

**Collection Patterns:**

- `"device_class:power"` - Entities with specific device class
- `"regex:pattern_variable"` - Entities matching regex pattern from variable (variable must reference an `input_text` entity)
- `"area:kitchen"` - Entities in specific area
- `"label:critical|important"` - Entities with specified label (pipe-separated OR logic)
- `"attribute:battery_level>=50"` - Entities with attribute conditions (supports `==`, `!=`, `<`, `<=`, `>`, `>=`)
- `"state:>=100|on"` - Entities with state conditions (supports all comparison operators and OR with `|`)
- `"attribute:name in 'Living'"` - String containment matching (supports `in`, `not in`)
- `"attribute:firmware_version>='2.1.0'"` - Semantic version comparisons
- `"attribute:last_seen>='2024-01-01'"` - Datetime comparisons (ISO format)

**Exclusion Syntax:**

Collection functions support excluding entities using the `!` prefix:

- `sum("device_class:power", !"specific_sensor")` - Exclude specific sensor by entity ID
- `avg("area:kitchen", !"kitchen_oven", !"kitchen_fridge")` - Exclude multiple specific sensors
- `count("device_class:power", !"area:basement")` - Exclude all sensors in basement area
- `max("label:critical", !"device_class:diagnostic")` - Exclude all diagnostic device class sensors

**Automatic Self-Exclusion:**

Collection functions automatically exclude the sensor that contains them to prevent circular dependencies:

```yaml
sensors:
  total_power:
    name: "Total Power"
    formula: sum("device_class:power") # Automatically excludes total_power itself
    metadata:
      device_class: "power" # Would normally be included, but gets auto-excluded
      unit_of_measurement: "W"
      state_class: "measurement"

  filtered_power:
    name: "Filtered Power"
    formula: sum("device_class:power", !"kitchen_oven") # Auto-excludes itself + manual exclusion
    metadata:
      device_class: "power"
      unit_of_measurement: "W"
      state_class: "measurement"
```

- **No configuration needed**: Self-exclusion happens automatically
- **Combines with manual exclusions**: Works alongside explicit `!` exclusions
- **Prevents circular dependencies**: Eliminates infinite loops in collection functions

**Sensor State Token:**

The `state` of the sensor is referenced by this special token. When `state` is referenced in the main formula the reference
is to the sensor state before the formula is evaluated. When `state` is used in an attribute formula the token refers to the
main sensor's formula result (post-eval). This disctinction makes sense because the main sensor state is evaluated _before_
attributes. The state flow is always logically evaluated in order.

References to attributes can also be made from the state like `state.my_sensor_attribute`. So if `state.my_attribute *10`is
used in the main formula the result is the state of the main sensor's`my_attribute` prior to the formula being evaluated.

If `state.my_attribute` is used in the attribute formula the `state` reference is to the main formula's state after the main
sensor is evaluted. This ordering matters if the attribute was influcened by the main sensor state. The key is to always
remember the the main sensor state is evaluated before attributes.

- **Explicit operators**: `"state:==on|!=off|>50"`
- **Shorthand boolean**: `"state:on|!off|>50"` (implicit equality for simple values)
- **Negation**: `"state:!off|!inactive"` (excludes specific states)

**Attribute Patterns:**

- **Explicit operators**: `"battery_level>=50|status==active|firmware_version>='2.1.0'"`
- **Shorthand with colon**: `"battery_level>=50|status:active|mode:!inactive"`
- **String containment**: `"name in 'Living'|manufacturer not in 'Corp'"`
- **Negation**: `"device_class:!humidity|battery_level:!<20"`

**Simple Patterns (device_class, area, label):**

- **Inclusion**: `"device_class:power|area:kitchen|label:critical"`
- **Negation**: `"device_class:!diagnostic|area:!garage|label:!deprecated"`
- **Mixed**: `"device_class:power|!humidity|area:kitchen|!basement"`

**Syntax Reference:**

| Pattern Type     | Explicit Syntax                       | Shorthand Syntax             | Negation Syntax              |
| ---------------- | ------------------------------------- | ---------------------------- | ---------------------------- |
| **State**        | `"state:==on \| !=off \| >=50"`       | `"state:on \| !off \| >=50"` | `"state:!off \| !inactive"` |
| **Attribute**    | `"battery_level>=50 \| status==active"` | `"battery_level>=50 \| status:active"` | `"battery_level:!<20"` |
| **String**       | `"name in 'Living' \| manufacturer not in 'Test'"` | `"name:Living \| manufacturer:!Test"` | `"name:!'Kitchen'"` |
| **Version**      | `"firmware_version>='2.1.0' \| app_version<'3.0'"` | `"firmware_version:>=2.1.0"` | `"version:!<1.0"` |
| **DateTime**     | `"last_seen>='2024-01-01T00:00:00Z'"` | `"last_seen:>=2024-01-01"`   | `"updated_at:!<yesterday"`   |
| **Device Class** | `"device_class:power \| device_class:energy"` | `"device_class:power \| energy"` | `"device_class:!diagnostic"` |
| **Area**         | `"area:kitchen \| area:living_room"`   | `"area:kitchen \| living_room"` | `"area:!basement"`           |
| **Label**        | `"label:critical \| label:important"`  | `"label:critical \| important"` | `"label:!deprecated"`        |

**Key Features:**

- **Pipe-only OR logic**: All patterns use `\|` for OR conditions (no comma support)
- **Shorthand evaluation**: Simple values like `on`, `active`, `connected` are automatically evaluated as boolean
- **Negation support**: `!` prefix excludes specific values or patterns
- **Mixed patterns**: Combine inclusion and exclusion in the same pattern

**Important:** For regex patterns, the variable must reference an `input_text` entity containing the regex pattern:

```yaml
# Correct: Variable references input_text entity
variables:
  circuit_pattern: "input_text.circuit_regex_pattern"  # input_text entity with regex
formula: sum("regex:circuit_pattern")

# Wrong: Variable contains direct regex string
variables:
  circuit_pattern: "sensor\\.circuit_.*"  # Direct regex string
formula: sum("regex:circuit_pattern")
```

Collection patterns use the pipe (`|`) character for OR logic between patterns:

- Correct: `"device_class:power|device_class:energy"`(long hand inclusion of power and energy)
- Correct: `"state:on|active|connected"` (shorthand boolean evaluation that includes active and connected)
- Correct: `"device_class:power|!humidity"` (inclusion of power and exclusion of humidity)
- Wrong: `"device_class:power or energy"` (must use the pipe `|`operator)
- Wrong: `"label:critical,important"` (comma syntax not supported - use pipe)

**Empty Collection Behavior:**

When a collection pattern matches no entities, the collection functions return `0` instead of making the sensor unavailable.
This provides robust behavior for dynamic entity collections.

```yaml
# These return 0 when no entities match the pattern
sum("device_class:nonexistent")     # Returns: 0
avg("area:empty_room")              # Returns: 0
count("label:missing_label")       # Returns: 0
min("state:>9999")                  # Returns: 0
max("attribute:invalid<0")          # Returns: 0
```

**Detecting Empty Collections:**

If you need to distinguish between "no matching entities" and "entities with zero values", you can use a formula like this:

```yaml
sensors:
  smart_power_monitor:
    name: "Smart Power Monitor"
    formula: "count(power_pattern) > 0 ? sum(power_pattern) : null"
    variables:
      power_pattern: "device_class:power"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
    # This sensor will be unavailable when no power entities exist,
    # but will show 0 when power entities exist but all have zero values
```

## Formula Examples

For detailed formula examples and programming patterns, see the
[Integration Guide](docs/Synthetic_Sensors_Integration_Guide.md).

## Python Operators in Formulas

The formula engine supports Python logical operators, conditionals, comparison operators, and membership testing for
sophisticated sensor calculations. For comprehensive examples and advanced patterns, see
[Formula Operators Guide](docs/formulas_with_operators.md).

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
```

### Logical Operators with Power Systems

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
```

**Key Python Operators Available:**

- **Conditional**: `value_if_true if condition else value_if_false`
- **Logical**: `and`, `or`, `not`
- **Comparison**: `==`, `!=`, `<`, `>`, `<=`, `>=` (supports numeric, datetime, version, and string types)
- **Membership**: `in`, `not in` (for string containment)
- **Boolean values**: `True`, `False`

**Boolean State Conversion:**

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

**Available Mathematical Functions:**

- Basic: `abs()`, `round()`, `floor()`, `ceil()`
- Math: `sqrt()`, `pow()`, `sin()`, `cos()`, `tan()`, `log()`, `exp()`
- Statistics: `min()`, `max()`, `avg()`, `mean()`, `sum()`
- Utilities: `clamp(value, min, max)`, `map(value, in_min, in_max, out_min, out_max)`, `percent(part, whole)`

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

**Integration Domain:**

Device association requires specifying the integration domain. See the
[Integration Guide](docs/Synthetic_Sensors_Integration_Guide.md) for implementation details.

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
avoiding conflicts between sensors from different devices.

## Home Assistant services

```yaml
# Reload configuration
service: synthetic_sensors.reload_config

# Get sensor information
service: synthetic_sensors.get_sensor_info
data:
  entity_id: "sensor.span_panel_main_energy_cost_analysis"

# Update sensor configuration
service: synthetic_sensors.update_sensor
data:
  entity_id: "sensor.span_panel_main_energy_cost_analysis"
  formula: "updated_formula"

# Test formula evaluation
service: synthetic_sensors.evaluate_formula
data:
  formula: "A + B * 2"
  context: { A: 10, B: 5 }
```

## Development and Integration

For detailed implementation examples, API documentation, and integration patterns, see the
[Integration Guide](docs/Synthetic_Sensors_Integration_Guide.md).

### Public API

The package provides a clean, stable public API:

- **StorageManager** - Manages sensor set storage and configuration
- **SensorSet** - Handle for individual sensor set operations
- **FormulaConfig/SensorConfig** - Configuration classes for sensors and formulas
- **DataProviderResult** - Type definition for data provider callbacks
- **SyntheticSensorsIntegration** - Main integration class for standalone use

### Architecture

The package uses a modular architecture with clear separation between configuration management, formula evaluation, and Home
Assistant integration. All internal implementation details are encapsulated behind the public API.

## Contributing

Contributions are welcome! Please see the [Integration Guide](docs/Synthetic_Sensors_Integration_Guide.md) for development
setup and contribution guidelines.

## License

MIT License

## Repository

- GitHub: [https://github.com/SpanPanel/ha-synthetic-sensors](https://github.com/SpanPanel/ha-synthetic-sensors)
- Issues:
  [https://github.com/SpanPanel/ha-synthetic-sensors/issues](https://github.com/SpanPanel/ha-synthetic-sensors/issues)
