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

A comprehensive Python package for creating formula-based synthetic sensors in Home Assistant integrations
using YAML configuration and mathematical expressions.

## What it does

- **Creates formula-based sensors** from mathematical expressions
- **YAML configuration** for easy sensor definition and management
- **Advanced dependency resolution** with automatic entity discovery
- **Storage-based configuration** with runtime modification capabilities
- **Variable support** for reusable calculations and shared configuration
- **Dynamic entity aggregation** using regex, tags, areas, and device class patterns
- **Comprehensive caching** with AST compilation for optimal performance
- **Integration with Home Assistant** device and entity registries

## Key Features

- **Variable reuse**: Define variables globally or per sensor for use across multiple formulas
- **Dependency tracking**: Automatic sensor update ordering and hierarchical dependencies
- **Type safety**: Complete TypedDict interfaces for better IDE support and validation
- **Storage-first architecture**: Runtime configuration changes without file modifications
- **Dot notation**: Easy access to entity attributes in formulas
- **Collection functions**: Support for aggregating multiple entities with filtering

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

For detailed implementation examples, API documentation, and integration patterns,
see the [Integration Guide](docs/Synthetic_Sensors_Integration_Guide.md).

The package provides a clean public API:

- **StorageManager** - Manages sensor set storage and configuration
- **SensorSet** - Handle for individual sensor set operations
- **FormulaConfig/SensorConfig** - Configuration classes for sensors and formulas
- **DataProviderResult** - Type definition for data provider callbacks

## YAML Configuration Examples

### Simple Calculated Sensors

```yaml
version: "1.0"

sensors:
  # Single formula sensor (90% of use cases)
  energy_cost_current:
    name: "Current Energy Cost"
    formula: "current_power * electricity_rate / conversion_factor"
    variables:
      current_power: "sensor.span_panel_instantaneous_power"
      electricity_rate: "input_number.electricity_rate_cents_kwh"
      conversion_factor: 1000                    # Literal: watts to kilowatts
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
      zero_threshold: 0                         # Literal: threshold value
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
        formula: "energy_cost_analysis * 24 * 30" # ref by main sensor key
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

### Device Association

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

  # Sensor associated with an existing device (minimal config)
  battery_status:
    name: "Battery Status"
    formula: "battery_level * battery_capacity / 100"
    variables:
      battery_level: "sensor.battery_percentage"
      battery_capacity: "sensor.battery_total_capacity"
    metadata:
      unit_of_measurement: "kWh"
      device_class: "energy_storage"
      state_class: "measurement"
      suggested_display_precision: 2
      icon: "mdi:battery"
    # Only device_identifier needed for existing devices
    device_identifier: "solar_inverter_001"
```

**Device Association Fields:**

- **`device_identifier`** *(required)*: Unique identifier for the device
- **`device_name`** *(optional)*: Human-readable device name
- **`device_manufacturer`** *(optional)*: Device manufacturer
- **`device_model`** *(optional)*: Device model
- **`device_sw_version`** *(optional)*: Software version
- **`device_hw_version`** *(optional)*: Hardware version
- **`suggested_area`** *(optional)*: Suggested Home Assistant area

**Device Behavior:**

- **New devices**: If a device with the `device_identifier` doesn't exist, it will be created with the provided information
- **Existing devices**: If a device already exists, the sensor will be associated with it (additional device fields are ignored)
- **No device association**: Sensors without `device_identifier` behave as standalone entities (default behavior)
- **Entity ID generation**: When using device association, entity IDs automatically include the device name prefix (e.g., `sensor.span_panel_main_power`)

**Integration Domain:**

Device association requires specifying the integration domain. See the
[Integration Guide](docs/Synthetic_Sensors_Integration_Guide.md) for implementation details.

**Benefits of device association:**

- Sensors appear grouped under their device in the Home Assistant UI
- Better organization for complex setups with multiple related sensors
- Device-level controls and automations
- Cleaner entity management and discovery

**Device-Aware Entity Naming:**

When sensors are associated with devices, entity IDs are automatically generated using the device's name as a prefix:

- **device_identifier** is used to look up the device in Home Assistant's device registry
- **Device name** (from the device registry) is "slugified" (converted to lowercase, spaces become
underscores, special characters removed)
- Entity ID pattern: `sensor.{slugified_device_name}_{sensor_key}`
- Examples:
  - device_identifier "njs-abc-123" → Device "SPAN Panel House" → `sensor.span_panel_house_current_power`
  - device_identifier "solar_inv_01" → Device "Solar Inverter" → `sensor.solar_inverter_efficiency`
  - device_identifier "circuit_a1" → Device "Circuit - Phase A" → `sensor.circuit_phase_a_current`

This automatic naming ensures consistent, predictable entity IDs that clearly indicate which device they belong to,
while avoiding conflicts between sensors from different devices.

**How attributes work:**

- Main sensor state is calculated first using the `formula`
- Attributes are calculated second and have access to the `state` variable
- `state` always refers to the fresh main sensor calculation
- Attributes can define their own `variables` section for attribute-specific entity references
- Attributes inherit all variables from their parent sensor and can add their own
- Attributes can also reference other entities directly (like `sensor.max_power_capacity` above)
- Each attribute shows up as `sensor.energy_cost_analysis.daily_projected` etc. in HA

### Metadata Dictionary

The `metadata` dictionary provides extensible support for all Home Assistant sensor propertiesl.
This metadata is added directly to the sensor when the sensor is created in Home Assistant.

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
      options: ["low", "medium", "high"]  # for enum device classes

      # Custom properties (passed through to HA)
      custom_property: "custom_value"
```

**Examples of Metadata Properties:**

**Core Sensor Properties:**

- `unit_of_measurement` - Primary unit for the sensor value
- `native_unit_of_measurement` - Native unit before conversion
- `device_class` - HA device class (power, energy, temperature, etc.)
- `state_class` - How HA should handle the state (measurement, total, total_increasing)

**Display Properties:**

- `suggested_display_precision` - Number of decimal places to show
- `suggested_unit_of_measurement` - Preferred unit for display
- `icon` - Material Design icon (mdi:icon-name)
- `attribution` - Data source attribution text

**Entity Registry Properties:**

- `entity_category` - Category for grouping (config, diagnostic, system)
- `entity_registry_enabled_default` - Whether enabled by default
- `entity_registry_visible_default` - Whether visible by default

**Advanced Properties:**

- `assumed_state` - Whether the state is assumed or confirmed
- `last_reset` - When the sensor was last reset (for totals)
- `options` - List of valid options for enum device classes

**Extensibility:**

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

**Entity-Only Properties:**
These properties are only valid for sensors and will cause validation errors if used in attribute metadata:

- **Device Properties**: `device_class`, `state_class`
- **Registry Properties**: `entity_category`, `entity_registry_enabled_default`, `entity_registry_visible_default`
- **Behavior Properties**: `assumed_state`, `last_reset`, `force_update`, `available`, `options`

**Attribute-Safe Properties:**
These properties are valid for both sensors and attributes:

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
      device_class: "power"  # ✅ Valid for sensors
      unit_of_measurement: "W"
    attributes:
      daily_total:
        formula: "state * 24"
        metadata:
          unit_of_measurement: "Wh"  # ✅ Valid for attributes
          device_class: "energy"     # ❌ ERROR: Not allowed for attributes
```

**Attribute Metadata:**
Attributes define their own metadata independently. Attributes cannot use entity-specific metadata properties:

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

**Attribute Metadata Restrictions:**
The following properties are only valid for sensors, not attributes:

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

- **Global metadata**: Applied to all sensors in the YAML file
- **Sensor metadata**: Overrides global metadata for specific sensors
- **Attribute metadata**: Independent of global and sensor metadata
- **Validation**: Entity-only properties rejected in attribute metadata

## Entity Reference Patterns

| Pattern Type | Syntax | Example | Use Case |
| ------------ | ------ | ------- | -------- |
| **Direct Entity ID** | `sensor.entity_name` | `sensor.power_meter` | Quick references, cross-sensor |
| **Variable Alias** | `variable_name` | `power_meter` | Most common, clean formulas |
| **Sensor Key Reference** | `sensor_key` | `energy_analysis` | Reference other synthetic sensors |
| **State Alias (attributes)** | `state` | `state * 24` | In attributes, reference main sensor |
| **Attribute Dot Notation** | `entity.attribute` | `sensor1.battery_level` | Access entity attributes |
| **Collection Functions** | `mathFunc(pattern:value)` | `sum(device_class:temperature)` | Aggregate entities by pattern |

**Entity ID Generation**:

- **With device association**: `sensor.{device_prefix}_{sensor_key}` where device_prefix is auto-generated from the device name
- **Without device association**: `sensor.{sensor_key}`
- **Explicit override**: Use the optional `entity_id` field to specify exact entity ID

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
      efficiency_factor: 0.85                    # Numeric literal: efficiency constant
      tax_rate: 0.095                           # Numeric literal: tax percentage
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
        formula: "energy_analysis * (1 + tax_rate)"  # Uses sensor-level variable
        metadata:
          unit_of_measurement: "¢"
          suggested_display_precision: 2
      low_battery_count:
        formula: "count(battery_devices.battery_level<20)" # Uses attribute-level variable
        variables:
          battery_devices: "device_class:battery"  # Attribute-specific variable
        metadata:
          unit_of_measurement: "devices"
          icon: "mdi:battery-alert"
      temperature_difference:
        formula: "outdoor_temp - indoor_temp"  # Uses only attribute-level variables
        variables:
          outdoor_temp: "sensor.outdoor_temperature"
          indoor_temp: "sensor.indoor_temperature"
        metadata:
          unit_of_measurement: "°C"
          device_class: "temperature"
          suggested_display_precision: 1
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
      local_meter_power: "span.meter_001"  # From integration callback
      grid_power: "sensor.grid_power"      # From Home Assistant
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
      internal_sensor_a: "span.efficiency_input"   # From integration
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

Sum, average, or count entities dynamically using collection patterns with OR logic support:

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

  # OR patterns for multiple conditions
  security_monitoring:
    name: "Security Device Count"
    formula: count("device_class:door|window|lock")
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:security"

  main_floor_power:
    name: "Main Floor Power"
    formula: sum("area:living_room|kitchen|dining_room")
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  # Attribute filtering with collection variables
  low_battery_devices:
    name: "Low Battery Devices"
    formula: count("battery_devices.battery_level<20")
    variables:
      battery_devices: "device_class:battery"
    metadata:
      unit_of_measurement: "count"
      icon: "mdi:battery-alert"

  # Complex mixed patterns
  comprehensive_analysis:
    name: "Comprehensive Analysis"
    formula: 'sum("device_class:power|energy") + count("area:upstairs|downstairs")'
    metadata:
      unit_of_measurement: "mixed"
      icon: "mdi:chart-line"
```

**Available Functions:** `sum()`, `avg()`/`mean()`, `count()`, `min()`/`max()`, `std()`/`var()`

**Collection Patterns:**

- `"device_class:power"` - Entities with specific device class
- `"regex:pattern_variable"` - Entities matching regex pattern from variable
- `"area:kitchen"` - Entities in specific area
- `"tags:tag1,tag2"` - Entities with specified tags
- `"attribute:battery_level<50"` - Entities with attribute conditions
- `"state:>100|=on"` - Entities with state conditions (supports OR with `|`)

**Empty Collection Behavior:**

When a collection pattern matches no entities, the collection functions return `0` instead of making the sensor
unavailable. This provides robust behavior for dynamic entity collections.

```yaml
# These return 0 when no entities match the pattern
sum("device_class:nonexistent")     # Returns: 0
avg("area:empty_room")              # Returns: 0
count("tags:missing_tag")           # Returns: 0
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

## Variables and Configuration

Numeric literals can be used directly in variable definitions for constants, conversion factors, and thresholds:

```yaml
sensors:
  temperature_converter:
    name: "Temperature Converter"
    formula: "(temp_f - freezing_f) * conversion_factor / celsius_factor"
    variables:
      temp_f: "sensor.outdoor_temperature_f"
      freezing_f: 32                     # Literal: Fahrenheit freezing point
      conversion_factor: 5               # Literal: F to C numerator
      celsius_factor: 9                  # Literal: F to C denominator
    metadata:
      unit_of_measurement: "°C"
      device_class: "temperature"
      suggested_display_precision: 1

  power_efficiency:
    name: "Power Efficiency"
    formula: "actual_power / rated_power * percentage"
    variables:
      actual_power: "sensor.current_power"
      rated_power: 1000                  # Literal: rated power in watts
      percentage: 100                    # Literal: convert to percentage
    metadata:
      unit_of_measurement: "%"
      suggested_display_precision: 1

  cost_calculator:
    name: "Energy Cost"
    formula: "energy_kwh * rate_per_kwh * (1 + tax_rate)"
    variables:
      energy_kwh: "sensor.energy_usage"
      rate_per_kwh: 0.12                 # Literal: cost per kWh
      tax_rate: 0.085                    # Literal: tax percentage
    metadata:
      unit_of_measurement: "$"
      device_class: "monetary"
      suggested_display_precision: 2
```

**Supported literal types:**

- **Integers**: `42`, `-10`, `0`
- **Floats**: `3.14159`, `-2.5`, `0.001`
- **Scientific notation**: `1.23e-4`, `2.5e6`

**Boolean State Conversion:**

Home Assistant's typical boolean states are automatically converted to numeric values for use in formulas:

```yaml
sensors:
  device_activity_score:
    name: "Device Activity Score"
    formula: "motion_sensor * 10 + door_sensor * 5 + switch_state * 2"
    variables:
      motion_sensor: "binary_sensor.living_room_motion"    # "motion" → 1.0, "clear" → 0.0
      door_sensor: "binary_sensor.front_door"              # "open" → 1.0, "closed" → 0.0
      switch_state: "switch.living_room_light"             # "on" → 1.0, "off" → 0.0
    metadata:
      unit_of_measurement: "points"
      icon: "mdi:chart-line"
```

**Supported boolean states (→ 1.0):**

- Basic: `on`, `true`, `yes`, `1`
- Sensors: `open`, `opened`, `motion`, `detected`, `wet`, `heat`, `locked`
- Presence: `home`, `present`
- Activity: `active`, `running`, `charging`, `connected`, `online`
- Security: `armed_home`, `armed_away`, `armed_night`

**Supported boolean states (→ 0.0):**

- Basic: `off`, `false`, `no`, `0`
- Sensors: `closed`, `clear`, `no_motion`, `dry`, `cold`, `unlocked`
- Presence: `away`, `not_home`, `absent`
- Activity: `inactive`, `idle`, `stopped`, `not_charging`, `disconnected`, `offline`
- Security: `disarmed`, `disabled`

Device class-specific states are also supported (e.g., `normal`/`low` for battery sensors).

**Available Mathematical Functions:**

- Basic: `abs()`, `round()`, `floor()`, `ceil()`
- Math: `sqrt()`, `pow()`, `sin()`, `cos()`, `tan()`, `log()`, `exp()`
- Statistics: `min()`, `max()`, `avg()`, `mean()`, `sum()`
- Utilities: `clamp(value, min, max)`, `map(value, in_min, in_max, out_min, out_max)`, `percent(part, whole)`

## Why use this instead of templates?

This package provides cleaner syntax for mathematical operations and better sensor management compared to Home Assistant templates.

**This package:** Clean mathematical expressions with variable mapping

```yaml
formula: "net_power * buy_rate / 1000 if net_power > 0 else abs(net_power) * sell_rate / 1000"
variables:
  net_power: "sensor.span_panel_net_power"
  buy_rate: "input_number.electricity_buy_rate"
  sell_rate: "input_number.electricity_sell_rate"
```

**Template equivalent:** Verbose Jinja2 syntax with manual state conversion

```yaml
value_template: >
  {% set net_power = states('sensor.span_panel_net_power')|float %}
  {% set buy_rate = states('input_number.electricity_buy_rate')|float %}
  {% set sell_rate = states('input_number.electricity_sell_rate')|float %}
  {% if net_power > 0 %}
    {{ net_power * buy_rate / 1000 }}
  {% else %}
    {{ (net_power|abs) * sell_rate / 1000 }}
  {% endif %}
```

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

The package uses a modular architecture with clear separation between configuration management,
formula evaluation, and Home Assistant integration. All internal implementation details are
encapsulated behind the public API.

## Contributing

Contributions are welcome! Please see the [Integration Guide](docs/Synthetic_Sensors_Integration_Guide.md)
for development setup and contribution guidelines.

## License

MIT License

## Repository

- GitHub: <https://github.com/SpanPanel/ha-synthetic-sensors>
- Issues: <https://github.com/SpanPanel/ha-synthetic-sensors/issues>
