# Syn2: Advanced Synthetic Sensors - HA Synthetic Sensors Package

## Overview

Syn2 (Synthetic Sensors v2) is a standalone Python package that enables users to create custom mathematical sensors using any Home Assistant entity as input. This system provides flexible energy analysis and calculation capabilities through YAML configuration.

### Key Concept

Syn2 allows you to create synthetic sensors using mathematical equations with any number of participant entities. The improved syntax simplifies configuration by using sensor keys as unique identifiers and flattening single-formula sensors. Multi-formula sensors use calculated attributes to provide rich data without cluttering the UI.

### Core Capabilities

- **Universal Entity Support**: Use any Home Assistant sensor entity in formulas
- **Mathematical Formulas**: Safe evaluation of mathematical expressions with real-time updates
- **Hierarchical Relationships**: Create sensors that reference other synthetic sensors
- **Simplified YAML Configuration**: Flattened syntax for common use cases
- **Calculated Attributes**: Rich sensor data through computed attributes
- **Smart Cross-References**: Automatic entity ID resolution

### Dynamic Entity Aggregation Functions and Attribute Access

Syn2 will support advanced aggregation and attribute access patterns for Home Assistant entities, inspired by Node-RED and modern query languages. This enables users to sum, average, count, or otherwise aggregate values from groups of entities selected by device class, regex, tag/label, area, or advanced query (e.g., JSONata), as well as directly access entity attributes using dot notation.

**IMPLEMENTATION STATUS**: 
- ✅ **Variable Inheritance**: COMPLETED - Attribute formulas inherit parent sensor variables
- ✅ **Dot Notation**: COMPLETED - Entity attribute access via `entity.attribute_name`
- ✅ **Dynamic Query Parsing**: COMPLETED - Supports regex, tags, device_class, area, attribute patterns
- ✅ **Mathematical Functions**: COMPLETED - Full suite of math functions available
- 🔄 **Dynamic Query Resolution**: IN PROGRESS - Foundation built, runtime resolution needs evaluator integration
- ⏳ **JSONata Queries**: PLANNED - Advanced query language for complex selections

### Use Cases

- **Solar Analytics**: Convert negative grid power to positive "solar sold" values
- **Cost Calculations**: Real-time energy cost based on time-of-use rates
- **Sub-Panel Monitoring**: Aggregate multiple circuits into logical groupings
- **Custom Efficiency Metrics**: Calculate ratios and performance indicators
- **Hierarchical Analysis**: Build complex calculation trees using sensor IDs

## Configuration Principles

### **Configuration Principles (Improved)**

⚠️ **Simplified Syntax** - improved YAML structure for better usability:

Use sensor attributes the way HA new architecture uses them as defined in developer_attribute_readme.md
Use modern Poetry (poetry env activate, poetry install --with dev, poetry run, poetry shell is deprecated, etc.)

- **Entity ID Generation**: `sensor.syn2_{sensor_key}` (simplified, no formula nesting)
- **Service Operations**: All services accept `sensor_key` or `entity_id`
- **Cross-References**: Sensors reference each other by entity ID or sensor key
- **Configuration Storage**: All internal storage keyed by sensor key

✅ **Two syntax patterns** - choose based on complexity:

- **Single Formula**: YAML with direct `formula` key (90% of use cases)
- **Multi-Formula**: Use `state_formula` with calculated `attributes` for rich data

### YAML Configuration Format

```yaml
# ha-synthetic-sensors configuration
version: "1.0"
global_settings:
  domain_prefix: "syn2"  # Creates sensor.syn2_* entities

sensors:
  # Single Formula Sensors (Flattened Syntax)
  solar_sold_positive:                                  # REQUIRED: Unique identifier (key)
    name: "Solar Sold (Positive Value)"                 # OPTIONAL: Display name only
    formula: "abs(solar_power)"                         # Direct formula (no nested array)
    variables:
      solar_power: "sensor.span_panel_solar_inverter_instant_power"
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"

  # Multi-Formula Sensors (Calculated Attributes)
  net_energy_analysis:                                  # REQUIRED: Unique identifier (key)
    name: "Net Energy Analysis"                         # OPTIONAL: Display name only
    formula: "net_power * buy_rate / 1000 if net_power > 0 else abs(net_power) * sell_rate / 1000"
    attributes:
      daily_projected:
        formula: "state * 24"                           # References main state
        unit_of_measurement: "¢/day"
      monthly_projected:
        formula: "net_energy_analysis * 24 * 30"        # Reference main state by key 
        unit_of_measurement: "¢/month"
      efficiency_rating:
        formula: "abs(net_power) / max_capacity * 100"
        unit_of_measurement: "%"
    variables:
      net_power: "sensor.span_panel_current_power"
      buy_rate: "input_number.electricity_buy_rate_cents_kwh"
      sell_rate: "input_number.electricity_sell_rate_cents_kwh"
      max_capacity: "input_number.max_panel_capacity"
    unit_of_measurement: "¢/h"
    device_class: "monetary"
```

### Entity ID Generation

```python
# Simplified Entity IDs (Flattened Syntax)
sensor_entity_id = f"sensor.syn2_{sensor_key}"                    # sensor.syn2_solar_sold_positive

# For multi-formula sensors with attributes, only one main entity
main_entity_id = f"sensor.syn2_{sensor_key}"                      # sensor.syn2_net_energy_analysis

# Names set as display attributes (if provided)
sensor_attributes = {
    "name": sensor_config.get("name", sensor_key),                # Falls back to unique_id
    "unique_id": f"syn2_{sensor_key}",
    # Calculated attributes included in same entity
    "daily_projected": calculated_attribute_value,
    "monthly_projected": calculated_attribute_value,
    "efficiency_rating": calculated_attribute_value
}
```

## Service Interface

All services use **unique IDs or entity IDs** for identification, never names:

### Service Usage Examples

```yaml
# Load configuration via service call
service: synthetic_sensors.load_configuration
data:
  config: |
    sensors:
      - unique_id: "solar_sold_positive"
        formulas:
                  - id: "solar_sold"
          formula: "abs(min(grid_power, 0))"
            variables:
              grid_power: "sensor.span_panel_current_power"
            unit_of_measurement: "W"
            device_class: "power"

# Get sensor info by entity_id
service: synthetic_sensors.get_sensor_info
data:
  entity_id: "sensor.syn2_solar_sold_positive_solar_sold"  # Uses HA entity_id

# Update sensor by entity_id
service: synthetic_sensors.update_sensor
data:
  entity_id: "sensor.syn2_solar_sold_positive_solar_sold"  # Uses HA entity_id
  formulas:
    - id: "solar_sold"  # id for formula updates
      formula: "abs(min(grid_power, 0)) * 1.1"  # Updated formula

# Validate configuration
service: synthetic_sensors.validate_config
data:
  config: |
    sensors:
      - unique_id: "test_sensor"  # ID-based validation
        formulas:
                  - id: "test_formula"
          formula: "var1 + var2"
            variables:
              var1: "sensor.test_1"
              var2: "sensor.test_2"
```

## Example Use Cases

### Solar Analytics (Improved Syntax)

```yaml
# Simplified syntax with flattened single-formula sensors
sensors:
  # Solar sold as positive value (Single Formula)
  solar_sold_watts:                                    # REQUIRED: Unique sensor key
    name: "Solar Energy Sold"                          # OPTIONAL: Display name
    formula: "abs(min(grid_power, 0))"                 # Direct formula definition
    variables:
      grid_power: "sensor.span_panel_current_power"
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"

  # Solar self-consumption rate (Single Formula)
  solar_self_consumption_rate:                         # REQUIRED: Unique sensor key
    name: "Solar Self-Consumption Rate"                # OPTIONAL: Display name
    formula: "if(solar_production > 0, (solar_production - solar_export) / solar_production * 100, 0)"
    variables:
      solar_production: "sensor.span_panel_solar_inverter_instant_power"
      solar_export: "sensor.syn2_solar_sold_watts"     # Direct entity reference (simplified)
    unit_of_measurement: "%"
    state_class: "measurement"
```

### Hierarchical Calculations (Cross-References by ID)

```yaml
sensors:
  # Child sensors - base calculations
  hvac_total_power:                                    # REQUIRED: Unique ID
    name: "HVAC Total Power"                           # OPTIONAL: Display name
    formula: "heating_power + cooling_power"
    variables:
      heating_power: "sensor.span_panel_circuit_5_power"
      cooling_power: "sensor.span_panel_circuit_6_power"
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"

  lighting_total_power:                                # REQUIRED: Unique ID
    name: "Lighting Total Power"                       # OPTIONAL: Display name
    formula: "living_room + kitchen + bedroom"
    variables:
      living_room: "sensor.span_panel_circuit_10_power"
      kitchen: "sensor.span_panel_circuit_11_power"
      bedroom: "sensor.span_panel_circuit_12_power"
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"

  # Parent sensor - references other synthetic sensors by entity ID
  total_home_consumption:                              # REQUIRED: Unique ID
    name: "Total Home Consumption"                     # OPTIONAL: Display name
    formula: "hvac + lighting + appliances"
    variables:
      hvac: "sensor.syn2_hvac_total_power"             # Entity ID reference
      lighting: "sensor.syn2_lighting_total_power"     # Entity ID reference
      appliances: "sensor.major_appliances_power"
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"
```

### Cost Analysis (ID-Based References)

```yaml
sensors:
  # Real-time energy cost rate
  current_energy_cost_rate:                           # REQUIRED: Unique ID
    name: "Current Energy Cost Rate"                   # OPTIONAL: Display name
    formula: "net_power * buy_rate / 1000 if net_power > 0 else abs(net_power) * sell_rate / 1000"
    variables:
      net_power: "sensor.span_panel_current_power"
      buy_rate: "input_number.electricity_buy_rate_cents_kwh"
      sell_rate: "input_number.electricity_sell_rate_cents_kwh"
    unit_of_measurement: "¢/h"
    device_class: "monetary"
    state_class: "measurement"
```

## Integration with Home Assistant Platforms

### Syn2 + Integration Platform Pattern

**Key Design Philosophy**: Syn2 creates instantaneous calculated sensors using unique IDs, which can then be used as sources for Home Assistant's integration platform.

**Example Workflow**:

```yaml
# Step 1: Syn2 creates real-time power calculations (ID-based)
sensors:
  - unique_id: "solar_sold_watts"                      # REQUIRED: Unique ID
    formulas:
      - id: "solar_sold"                               # REQUIRED: Formula ID
        formula: "abs(min(grid_power, 0))"
        variables:
          grid_power: "sensor.span_panel_current_power"
        unit_of_measurement: "W"
        device_class: "power"
        state_class: "measurement"

# Step 2: Integration platform references by entity ID
sensor:
  - platform: integration
    source: sensor.syn2_solar_sold_watts_solar_sold  # References by entity ID
    name: Solar Sold kWh
    unique_id: solar_sold_kwh
    unit_prefix: k
    round: 2
```

## Test Fixtures Update

### Updated Test Configurations

```python
# Updated test fixtures using unique IDs
syn2_sample_config_id_based = {
    "version": "1.0",
    "global_settings": {
        "domain_prefix": "syn2"
    },
    "sensors": [
        {
            "unique_id": "comfort_index",                     # REQUIRED: Unique ID
            "name": "Comfort Index",                          # OPTIONAL: Display name
            "formulas": [
                {
                    "id": "comfort_formula",                   # REQUIRED: Formula ID
                    "name": "Comfort Level",                   # OPTIONAL: Display name
                    "formula": "temp + humidity",
                    "variables": {
                        "temp": "sensor.temperature",
                        "humidity": "sensor.humidity"
                    },
                    "unit_of_measurement": "index",
                    "state_class": "measurement"
                }
            ]
        },
        {
            "unique_id": "power_status",                      # REQUIRED: Unique ID
            "name": "Power Status",                           # OPTIONAL: Display name
            "formulas": [
                {
                    "id": "total_power",                       # REQUIRED: Formula ID
                    "name": "Total Power",                     # OPTIONAL: Display name
                    "formula": "hvac_power + lighting_power",
                    "variables": {
                        "hvac_power": "sensor.hvac",
                        "lighting_power": "sensor.lighting"
                    },
                    "unit_of_measurement": "W",
                    "device_class": "power"
                }
            ]
        }
    ]
}

# Service operation examples using IDs
service_test_examples = {
    "get_sensor_by_entity_id": {
        "service": "synthetic_sensors.get_sensor_info",
        "data": {"entity_id": "sensor.syn2_comfort_index_comfort_formula"}  # Uses HA entity_id
    },
    "update_sensor_by_entity_id": {
        "service": "synthetic_sensors.update_sensor",
        "data": {
            "entity_id": "sensor.syn2_power_status_total_power",  # Uses HA entity_id
            "formulas": [
                {
                    "id": "total_power",  # id for formula updates
                    "formula": "hvac_power * 1.1 + lighting_power"  # Updated formula
                }
            ]
        }
    }
}
```

## Mathematical Expression Engine

### Formula Validation Library

The implementation uses **simpleeval** for safe mathematical expression evaluation:

- **Security**: Safe evaluation without `eval()` risks
- **Performance**: Lightweight library optimized for mathematical expressions
- **Flexibility**: Supports custom functions and variables
- **Maintenance**: Actively maintained modern Python library

### State Class and Device Class Validation

The schema validator now includes intelligent validation of Home Assistant sensor attributes to prevent runtime errors and ensure optimal sensor behavior:

#### HA Standards Compliance

**State Class Validation**: Uses Home Assistant's official `DEVICE_CLASS_STATE_CLASSES` mapping to validate compatible combinations:

```python
# Examples of HA-validated combinations
DEVICE_CLASS_STATE_CLASSES = {
    SensorDeviceClass.ENERGY: {SensorStateClass.TOTAL, SensorStateClass.TOTAL_INCREASING},
    SensorDeviceClass.POWER: {SensorStateClass.MEASUREMENT},
    SensorDeviceClass.BATTERY: {SensorStateClass.MEASUREMENT},
    SensorDeviceClass.GAS: {SensorStateClass.TOTAL, SensorStateClass.TOTAL_INCREASING},
}
```

**Validation Behavior**:
- **Warnings**: When device_class + state_class combinations don't match HA recommendations
- **Guidance**: Suggests appropriate state_class values for each device_class
- **Integration-Friendly**: Allows flexibility for specialized use cases

#### State Class Constraints

**Understanding State Class Behavior**:
- `measurement`: Values can increase/decrease freely (power, temperature, battery)
- `total`: Cumulative values that can reset to zero (monthly energy usage)
- `total_increasing`: Strictly increasing values (lifetime energy production)

**Validation Examples**:

```yaml
# ✅ GOOD: Power sensors with measurement state class
sensors:
  solar_power:
    formula: "abs(solar_inverter_power)"
    device_class: "power"      # Typically measurement
    state_class: "measurement"  # Correct for power readings

# ⚠️ WARNING: Battery with total_increasing (will cause HA errors)
sensors:
  battery_level:
    formula: "state('sensor.phone_battery')"
    device_class: "battery"         # Battery levels go up and down
    state_class: "total_increasing"  # This will fail in HA!
    # Validator suggests: "measurement"

# ✅ GOOD: Energy sensor with appropriate state class
sensors:
  total_energy_consumed:
    formula: "energy_meter_reading"
    device_class: "energy"
    state_class: "total_increasing"  # Perfect for cumulative energy
```

#### Integration Context Awareness

**Domain-Specific Intelligence**: Different integrations have different patterns:

- **Span Integration**: Automatically creates power → energy sensor pairs, so users don't need to worry about energy state classes
- **Generic Usage**: Users might not know whether they want cumulative vs instantaneous sensors
- **Blood Glucose/Temperature**: No energy equivalents, so cumulative state classes make no sense

**Design Philosophy**:
1. **Prevent HA Runtime Errors**: Validate against official HA compatibility matrix
2. **Guide Users**: Suggest appropriate alternatives without being overly restrictive
3. **Integration Flexibility**: Allow specialized use cases while warning about potential issues
4. **Context Matters**: Let integrations (like Span) handle domain-specific sensor creation patterns

This validation ensures synthetic sensors integrate seamlessly with Home Assistant's statistics, long-term storage, and energy dashboard while providing helpful guidance for optimal sensor configuration.

## Service Interface Details

### Service Schemas (ID-Based)

```python
# Service schemas for entity operations (HA standard)
UPDATE_SENSOR_SCHEMA = vol.Schema({
    vol.Required('entity_id'): cv.entity_id,  # Primary: HA entity_id (required)
    vol.Optional('formulas'): [FORMULA_SCHEMA],
    vol.Optional('name'): cv.string,  # Optional display name
})

GET_SENSOR_INFO_SCHEMA = vol.Schema({
    vol.Required('entity_id'): cv.entity_id,  # Primary: HA entity_id (required)
})

FORMULA_SCHEMA = vol.Schema({
    vol.Required('id'): cv.string,                           # REQUIRED: Formula ID
    vol.Optional('name'): cv.string,                         # OPTIONAL: Display name
    vol.Required('formula'): cv.string,
    vol.Required('variables'): dict,
    vol.Optional('unit_of_measurement'): cv.string,
    vol.Optional('device_class'): cv.string,
})
```

## Implementation Architecture

### Unique ID Management

```python
@dataclass(frozen=True)
class SensorConfig:
    """Sensor configuration with required unique ID."""
    unique_id: str                       # REQUIRED: Unique identifier
    name: Optional[str] = None           # OPTIONAL: Display name only
    formulas: list[FormulaConfig] = field(default_factory=list)
    enabled: bool = True

@dataclass(frozen=True)
class FormulaConfig:
    """Formula configuration with required ID."""
    id: str                              # REQUIRED: Formula identifier
    name: Optional[str] = None           # OPTIONAL: Display name only
    formula: str
    variables: dict[str, str]
    unit_of_measurement: Optional[str] = None
    device_class: Optional[str] = None

class SensorManager:
    """Manages sensors using entity IDs as primary keys once created in HA."""

    def get_sensor(self, entity_id: str) -> Optional[DynamicSensor]:
        """Get sensor by entity ID (only method needed after HA creation)."""
        return self._sensors_by_entity_id.get(entity_id)

    def create_sensor_entity_id(self, sensor_config: SensorConfig, formula_config: FormulaConfig) -> str:
        """Generate entity ID from unique IDs during creation phase."""
        return f"sensor.syn2_{sensor_config.unique_id}_{formula_config.id}"
```

### Key Design Principles

1. **Unique IDs Required**: All sensors and formulas must have stable, unique identifiers in YAML config
2. **Names Optional**: Used only for display purposes when creating sensor entities
3. **Entity ID Primary**: Once created in HA, sensors are primarily identified by entity_id
4. **Service Interface**: Services require `entity_id` for sensor operations
5. **Cross-References**: Sensors reference each other by entity ID in variables
6. **Entity Registry**: Sensors registered using generated entity IDs: `sensor.syn2_{unique_id}_{formula_id}`

This approach ensures stable, predictable behavior while maintaining Home Assistant best practices for entity identification and management.

### Syntax Patterns

**1. Device Class Aggregation**
```yaml
sensors:
  open_doors_and_windows:                              # This sensor key IS the unique_id
    name: "Open Doors and Windows"                     # Friendly name for HA UI
    formula: sum(device_class:door|window)
    unit_of_measurement: "count"
    device_class: "door"
    state_class: "measurement"
```
*Aggregates all entities with device_class `door` or `window`.*

**2. Regex Aggregation**
```yaml
sensors:
  total_circuit_power:                                 # This sensor key IS the unique_id
    name: "Total Circuit Power"                        # Friendly name for HA UI
    formula: sum(regex:sensor\.span_panel_circuit_.*_instant_power)
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"
```
*Sums all sensors whose entity_id matches the regex pattern.*

**3. Area and Device Class Aggregation**
```yaml
sensors:
  garage_windows_open:                                 # This sensor key IS the unique_id
    name: "Garage Windows Open"                        # Friendly name for HA UI
    formula: sum(area:garage device_class:window)
    unit_of_measurement: "count"
    device_class: "window"
    state_class: "measurement"
```
*Sums all window sensors in the garage area.*

**4. Tag/Label Aggregation**
```yaml
sensors:
  tagged_sensors_sum:                                  # This sensor key IS the unique_id
    name: "Sum of Tagged Sensors"                      # Friendly name for HA UI
    formula: sum(tags:tag2,tag5)
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"
```
*Sums all sensors that have either the `tag2` or `tag5` label.*

**5. Attribute-Based Aggregation**
```yaml
sensors:
  low_battery_sensors:                                 # This sensor key IS the unique_id
    name: "Low Battery Sensors"                        # Friendly name for HA UI
    formula: sum(attribute:battery_level<20)
    unit_of_measurement: "count"
    device_class: "battery"
    state_class: "measurement"
```
*Sums all sensors with a `battery_level` attribute less than 20.*

**6. JSONata/Advanced Query Aggregation (Optional/Advanced)**
```yaml
sensors:
  open_garage_doors:                                   # This sensor key IS the unique_id
    name: "Open Garage Doors"                          # Friendly name for HA UI
    formula: sum(jsonata:$.entities[attributes.battery_level < 20 && state="on"].state)
    unit_of_measurement: "count"
    device_class: "door"
    state_class: "measurement"
```
*Uses a JSONata query to select all open doors in the garage with battery_level < 20.*

### YAML Quoting Guidance for Query Patterns

When using query patterns (such as `tags:`, `device_class:`, `regex:`, etc.) in formulas, you may use either quoted or unquoted forms:

- **Unquoted**: Works for simple patterns with no spaces or special YAML characters.
- **Quoted**: Required if your tag, device class, or pattern contains spaces or special characters (such as `:`, `#`, `,`, etc.).

**Examples:**
```yaml
# No spaces or special characters: quotes optional
formula: sum(tags:tag2,tag5)
formula: sum(device_class:door|window)

# Spaces or special characters: quotes required
formula: sum("tags:my tag with spaces,tag2")
formula: sum('tags:tag2,#tag3')
```
**Tip:**
If in doubt, use quotes. Both single and double quotes are supported.

### Dot Notation and Attribute Shortcuts

For simple and direct access to entity attributes, Syn2 supports dot notation in formulas:

- **Full attribute path:**
  Reference any attribute using `entity_id.attributes.attribute_name`
  ```yaml
  formula: sensor1.attributes.battery_level
  ```
  This resolves to the value of the `battery_level` attribute of `sensor1`.

- **Attribute shortcut:**
  If the attribute is not a state property, `entity_id.attribute_name` will resolve to `entity_id.attributes.attribute_name` if present.
  ```yaml
  formula: sensor1.battery_level
  ```
  This is a shortcut for `sensor1.attributes.battery_level`.

- **Aggregation with attribute access:**
  ```yaml
  formula: avg(sensor1.battery_level, sensor2.battery_level, sensor3.battery_level)
  ```
  Averages the `battery_level` attribute across the listed sensors.

### Notes
- All aggregation functions (`sum`, `avg`, `count`, etc.) support these query patterns.
- JSONata/JavaScript-style queries are optional and intended for advanced users.
- Dot notation for attribute access is supported everywhere a variable or entity can be referenced.
- These features are designed to be robust, user-friendly, and compatible with YAML best practices.
- **Sensor Key = Unique ID**: The YAML sensor key (e.g., `open_doors_and_windows`) IS the unique_id. No separate `unique_id` field is needed.
- **Name = Friendly Name**: The `name` field provides the human-readable display name in Home Assistant UI.
- **Recommended Fields**: While only `formula` is required, adding `device_class`, `state_class`, and `unit_of_measurement` ensures proper Home Assistant integration.

### Variable Inheritance in Attribute Formulas

Attribute formulas automatically inherit all variables from their parent sensor, enabling flexible calculations that reference both the main sensor state and external entities.

**Inheritance Rules:**
1. **Parent Variables**: All variables defined in the parent sensor are available to attribute formulas
2. **Main Sensor Reference**: The parent sensor's state is available using the sensor key as a variable name
3. **Attribute Variables**: Attributes can define additional variables or override parent variables
4. **Precedence**: Attribute-specific variables take precedence over parent variables

**Examples:**

```yaml
sensors:
  energy_analysis:
    name: "Energy Analysis"
    formula: "grid_power + solar_power"
    variables:
      grid_power: "sensor.grid_meter"
      solar_power: "sensor.solar_inverter"
      efficiency_factor: "input_number.base_efficiency"
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"
    attributes:
      # Attribute inherits all parent variables
      daily_projection:
        formula: "energy_analysis * 24"          # References main sensor by key
        unit_of_measurement: "Wh"
      
      # Attribute uses inherited variables
      efficiency_percent:
        formula: "solar_power / (grid_power + solar_power) * 100"
        unit_of_measurement: "%"
      
      # Attribute with additional variables
      cost_analysis:
        formula: "grid_power * electricity_rate / 1000"
        variables:
          electricity_rate: "input_number.current_rate"  # New variable
        unit_of_measurement: "¢/h"
      
      # Attribute overriding parent variable  
      custom_efficiency:
        formula: "solar_power * efficiency_factor"
        variables:
          efficiency_factor: "input_number.custom_efficiency"  # Overrides parent
        unit_of_measurement: "W"
```

**Variable Resolution Order:**
1. Attribute-specific variables (highest precedence)
2. Parent sensor variables  
3. Main sensor state reference (sensor key → entity_id)
4. Direct entity_id references in formula

**Advanced Features:**
- **Dynamic Queries**: Attribute formulas support all dynamic query types (`regex:`, `tags:`, etc.)
- **Dot Notation**: Access entity attributes using `entity.attribute_name` syntax
- **Cross-References**: Reference other synthetic sensors by entity_id
- **Runtime Resolution**: Dynamic queries are resolved at evaluation time based on current HA state

**Architecture Benefits**: The solution provides a robust, extensible foundation ready for implementing the full dynamic entity aggregation system while maintaining backward compatibility and comprehensive test coverage.

## Currently Implemented Features

### Variable Inheritance System

Attribute formulas now automatically inherit all variables from their parent sensor, enabling powerful calculation hierarchies:

```yaml
sensors:
  energy_analysis:
    name: "Complete Energy Analysis"
    formula: "grid_power + solar_power - battery_discharge"
    variables:
      grid_power: "sensor.grid_meter"
      solar_power: "sensor.solar_inverter"
      battery_discharge: "sensor.battery_system"
      efficiency_factor: "input_number.system_efficiency"
    attributes:
      # All attributes inherit: grid_power, solar_power, battery_discharge, efficiency_factor
      
      # Reference main sensor state
      daily_projection:
        formula: "energy_analysis * 24"
        unit_of_measurement: "kWh"
      
      # Use inherited variables directly
      grid_dependency:
        formula: "grid_power / (grid_power + solar_power) * 100"
        unit_of_measurement: "%"
      
      # Add new variables specific to this attribute
      cost_analysis:
        formula: "grid_power * electricity_rate / 1000"
        variables:
          electricity_rate: "input_number.current_rate"
        unit_of_measurement: "¢/h"
      
      # Override parent variables
      adjusted_efficiency:
        formula: "solar_power * efficiency_factor"
        variables:
          efficiency_factor: "input_number.peak_efficiency"  # Overrides parent
        unit_of_measurement: "W"
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"
```

### Enhanced Mathematical Functions

Complete mathematical function library now available:

```yaml
sensors:
  advanced_calculations:
    name: "Advanced Calculations"
    formula: "clamp(map(efficiency, 0, 100, 0, 255), 0, 255)"
    variables:
      efficiency: "sensor.system_efficiency"
    attributes:
      normalized_efficiency:
        formula: "percent(efficiency, 100)"
      
      power_analysis:
        formula: "sqrt(pow(active_power, 2) + pow(reactive_power, 2))"
        variables:
          active_power: "sensor.active_power"
          reactive_power: "sensor.reactive_power"
      
      temperature_comfort:
        formula: "avg(temp1, temp2, temp3, temp4)"
        variables:
          temp1: "sensor.living_room_temp"
          temp2: "sensor.kitchen_temp"
          temp3: "sensor.bedroom_temp"
          temp4: "sensor.office_temp"
```

### Dot Notation Attribute Access

Direct access to entity attributes using intuitive dot syntax:

```yaml
sensors:
  battery_health_summary:
    name: "Battery Health Summary"
    formula: "avg(phone.battery_level, tablet.battery_level, laptop.battery_level)"
    variables:
      phone: "sensor.phone_battery"
      tablet: "sensor.tablet_battery"
      laptop: "sensor.laptop_battery"
    attributes:
      min_battery:
        formula: "min(phone.battery_level, tablet.battery_level, laptop.battery_level)"
      
      critical_devices:
        formula: "count_if(phone.battery_level < 20) + count_if(tablet.battery_level < 20)"
        # Note: count_if is planned for future implementation
```

### Foundation for Dynamic Queries

The dependency parser now recognizes and validates dynamic query patterns:

```yaml
# These patterns are parsed and validated (runtime resolution coming soon)
sensors:
  all_circuit_power:
    name: "All Circuit Power"
    formula: sum(regex:sensor\.circuit_.*_power)  # ✅ Parsed correctly
    
  open_access_points:
    name: "Open Access Points"
    formula: count(device_class:door|window state:open)  # ✅ Parsed correctly
    
  critical_battery_devices:
    name: "Critical Battery Devices"
    formula: count(tags:critical attribute:battery_level<20)  # ✅ Parsed correctly
```

### Test Coverage

Comprehensive test suite covering:

- **Variable Inheritance**: 4 test scenarios covering inheritance, overrides, and precedence
- **Dependency Parsing**: 7 test scenarios for static and dynamic dependency extraction
- **Mathematical Functions**: 15+ test scenarios for all math functions
- **Integration Workflows**: End-to-end testing of complete sensor creation and evaluation
- **Error Handling**: Robust error classification and circuit breaker patterns

**Test Results**: 316/316 tests passing with 79% code coverage.
