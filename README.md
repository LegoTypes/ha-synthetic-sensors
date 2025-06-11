# HA Synthetic Sensors

A Python package for creating formula-based sensors in Home Assistant integrations using YAML configuration.

## What it does

- Creates Home Assistant sensor entities from mathematical formulas
- Evaluates expressions using `simpleeval` library
- Maps variable names to Home Assistant entity IDs
- Manages sensor lifecycle (creation, updates, removal)
- Provides Home Assistant services for configuration management
- Tracks dependencies between sensors
- Caches formula results
- Variable inheritance in attribute formulas
- Dynamic entity aggregation (regex, tags, device_class patterns)
- Dot notation for entity attribute access

## Installation

```bash
pip install ha-synthetic-sensors
```

Development setup:

```bash
git clone https://github.com/SpanPanel/ha-synthetic-sensors
cd ha-synthetic-sensors
poetry install --with dev
```

## Basic integration setup

```python
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ha_synthetic_sensors import async_setup_integration

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> bool:
    return await async_setup_integration(
        hass, config_entry, async_add_entities
    )
```

## YAML configuration

### Simple calculated sensors

```yaml
version: "1.0"

sensors:
  # Single formula sensor (90% of use cases)
  energy_cost_current:
    name: "Current Energy Cost"
    formula: "current_power * electricity_rate / 1000"
    variables:
      current_power: "sensor.span_panel_instantaneous_power"
      electricity_rate: "input_number.electricity_rate_cents_kwh"
    unit_of_measurement: "¢/h"
    device_class: "monetary"
    state_class: "measurement"

  # Another simple sensor
  solar_sold_power:
    name: "Solar Sold Power"
    formula: "abs(min(grid_power, 0))"
    variables:
      grid_power: "sensor.span_panel_current_power"
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"
```

### Rich sensors with calculated attributes

```yaml
sensors:
  # Sensor with calculated attributes
  energy_cost_analysis:
    name: "Energy Cost Analysis"
    formula: "current_power * electricity_rate / 1000"
    attributes:
      daily_projected:
        formula: "state * 24"                       # by main state alias
        unit_of_measurement: "¢"
      monthly_projected:
        formula: "energy_cost_analysis * 24 * 30"   # by main sensor key
        unit_of_measurement: "¢"
      annual_projected:
        formula: "sensor.syn2_energy_cost_analysis * 24 * 365"  # by entity_id
        unit_of_measurement: "¢"
      battery_efficiency:
        formula: "current_power * device.battery_level / 100"  # by attribute access
        variables:
          device: "sensor.backup_device"
        unit_of_measurement: "W"
      efficiency:
        formula: "state / sensor.max_power_capacity * 100"
        unit_of_measurement: "%"
    variables:
      current_power: "sensor.span_panel_instantaneous_power"
      electricity_rate: "input_number.electricity_rate_cents_kwh"
    unit_of_measurement: "¢/h"
    device_class: "monetary"
    state_class: "measurement"
```

**How attributes work:**

- Main sensor state is calculated first using the `formula`
- Attributes are calculated second and have access to the `state` variable
- `state` always refers to the fresh main sensor calculation
- Attributes can also reference other entities normally (like `sensor.max_power_capacity` above)
- Each attribute shows up as `sensor.energy_cost_analysis.daily_projected` etc. in HA

## Advanced Entity References

### Variable Inheritance in Attributes

Attribute formulas automatically inherit all variables from their parent sensor:

```yaml
sensors:
  energy_analysis:
    name: "Energy Analysis"
    formula: "grid_power + solar_power"
    variables:
      grid_power: "sensor.grid_meter"
      solar_power: "sensor.solar_inverter" 
      efficiency_factor: "input_number.base_efficiency"
    attributes:
      # Inherits all parent variables (grid_power, solar_power, efficiency_factor)
      daily_projection:
        formula: "energy_analysis * 24"          # References main sensor by key
      
      efficiency_percent:
        formula: "solar_power / (grid_power + solar_power) * 100"  # Uses inherited variables
      
      # Attributes can add new variables or override parent ones
      cost_analysis:
        formula: "grid_power * electricity_rate / 1000"
        variables:
          electricity_rate: "input_number.current_rate"  # New variable
      
      custom_efficiency:
        formula: "solar_power * efficiency_factor"
        variables:
          efficiency_factor: "input_number.custom_efficiency"  # Overrides parent
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"
```

### Direct Entity References

You can reference entities directly in formulas without variables:

```yaml
sensors:
  simple_calculation:
    name: "Simple Calculation"
    formula: "sensor.power_meter + sensor.backup_generator"  # Direct entity_ids
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"
```

### Dot Notation for Attributes

Access entity attributes using dot notation:

```yaml
sensors:
  battery_analysis:
    name: "Battery Analysis"
    formula: "sensor1.battery_level + sensor2.battery_level"  # Shortcut
    # Equivalent to: sensor1.attributes.battery_level + sensor2.attributes.battery_level
    unit_of_measurement: "%"
    device_class: "battery"
    state_class: "measurement"
    
  temperature_comfort:
    name: "Temperature Comfort"
    formula: "clamp(temp_sensor.temperature, 18, 26)"
    variables:
      temp_sensor: "climate.living_room"
```

### Dynamic Entity Aggregation

Sum, average, or count entities dynamically using patterns:

```yaml
sensors:
  # Aggregate by device class
  open_doors_windows:
    name: "Open Doors and Windows"
    formula: sum(device_class:door|window)
    unit_of_measurement: "count"
    
  # Aggregate using regex patterns
  total_circuit_power:
    name: "Total Circuit Power"
    formula: sum(regex:sensor\.circuit_.*_power)
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"
    
  # Aggregate by area and device class
  garage_windows:
    name: "Garage Windows Open"
    formula: sum(area:garage device_class:window)
    unit_of_measurement: "count"
    
  # Aggregate by tags/labels
  critical_sensors:
    name: "Critical Sensors Active"
    formula: count(tags:critical,important)
    unit_of_measurement: "count"
    
  # Aggregate by attribute values
  low_battery_devices:
    name: "Low Battery Devices"
    formula: count(attribute:battery_level<20)
    unit_of_measurement: "count"
```

**Aggregation Functions Available:**
- `sum()` - Sum all matching entity values
- `avg()` / `mean()` - Average of all matching entities
- `count()` - Count of matching entities
- `min()` / `max()` - Minimum/maximum value
- `std()` / `var()` - Standard deviation/variance

**Query Patterns:**
- `device_class:power` - Entities with specific device class
- `regex:sensor\..*_power` - Entities matching regex pattern
- `area:kitchen` - Entities in specific area
- `tags:tag1,tag2` - Entities with any of the specified tags
- `attribute:battery_level<50` - Entities with attribute conditions

### Mixed Reference Types

You can combine different reference types in the same formula:

```yaml
sensors:
  comprehensive_analysis:
    name: "Comprehensive Power Analysis"
    formula: "base_load + sum(regex:sensor\.circuit_.*_power) + backup_power.current_power"
    variables:
      base_load: "sensor.main_panel_power"
      backup_power: "sensor.backup_generator"
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"
```

## Variable mapping

```python
from ha_synthetic_sensors import NameResolver

variables = {
    "current_power": "sensor.span_panel_instantaneous_power",
    "electricity_rate": "input_number.electricity_rate_cents_kwh",
    "hvac_upstairs": "sensor.hvac_upstairs_power",
}

name_resolver = NameResolver(hass, variables=variables)
```

## Formula examples

```python
# Basic arithmetic
"circuit_1 + circuit_2 + circuit_3"

# Conditional logic
"net_power * buy_rate / 1000 if net_power > 0 else abs(net_power) * sell_rate / 1000"

# Mathematical functions
"abs(min(grid_power, 0))"                    # Absolute value, min/max
"sqrt(power_a**2 + power_b**2)"              # Square root, exponents
"round(temperature, 1)"                      # Rounding
"clamp(efficiency, 0, 100)"                  # Constrain to range
"map(brightness, 0, 255, 0, 100)"            # Map from one range to another
"avg(temp1, temp2, temp3)"                   # Average of values
"percent(used_space, total_space)"           # Percentage calculation

# Dynamic aggregation
"sum(regex:sensor\.circuit_.*_power)"        # Sum all circuit sensors
"avg(device_class:temperature)"              # Average all temperature sensors
"count(tags:critical)"                       # Count entities with 'critical' tag

# Dot notation attribute access
"sensor1.battery_level + sensor2.battery_level"
"climate.living_room.current_temperature"

# Sensor references (by entity ID)
"sensor.syn2_hvac_total_power + sensor.syn2_lighting_total_power"
```

**Available Mathematical Functions:**
- Basic: `abs()`, `round()`, `floor()`, `ceil()`
- Math: `sqrt()`, `pow()`, `sin()`, `cos()`, `tan()`, `log()`, `exp()`
- Statistics: `min()`, `max()`, `avg()`, `mean()`, `sum()`
- Utilities: `clamp(value, min, max)`, `map(value, in_min, in_max, out_min, out_max)`, `percent(part, whole)`

## Why use this instead of templates?

While Home Assistant templates can create calculated sensors, this package provides much cleaner syntax for mathematical operations and bulk sensor management.

### Syntax comparison

**This package:**
```yaml
formula: "net_power * buy_rate / 1000 if net_power > 0 else abs(net_power) * sell_rate / 1000"
variables:
  net_power: "sensor.span_panel_net_power"
  buy_rate: "input_number.electricity_buy_rate"
  sell_rate: "input_number.electricity_sell_rate"
```

**Template equivalent:**
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

### Complex mathematics

**This package:**
```yaml
formula: "sqrt(power_a**2 + power_b**2 + power_c**2) * efficiency_factor"
```

**Template equivalent:**
```yaml
value_template: >
  {% set power_a = states('sensor.power_a')|float %}
  {% set power_b = states('sensor.power_b')|float %}
  {% set power_c = states('sensor.power_c')|float %}
  {% set efficiency_factor = states('input_number.efficiency_factor')|float %}
  {{ (power_a**2 + power_b**2 + power_c**2)**0.5 * efficiency_factor }}
```

### Variable reuse

**This package:**
```yaml
# Base calculation sensor
base_calculation:
  formula: "power_usage * rate"
  variables:
    power_usage: "sensor.power_meter"
    rate: "input_number.electricity_rate"

# Derived calculation referencing the first sensor
with_tax:
  formula: "sensor.syn2_base_calculation * 1.08"

# Or use attributes for related calculations
comprehensive_analysis:
  formula: "power_usage * rate"
  attributes:
    with_tax:
      formula: "state * 1.08"
    with_discount:
      formula: "state * 0.90"
  variables:
    power_usage: "sensor.power_meter"
    rate: "input_number.electricity_rate"
```

**Templates:** Each sensor needs separate template with repeated calculations.

### Bulk sensor management

**This package:** Single YAML file defines dozens of related sensors with shared variables and automatic dependency management.

**Templates:** Each sensor requires separate configuration entry with manual entity ID management.

## Home Assistant services

The package registers these services automatically:

```yaml
# Reload configuration
service: synthetic_sensors.reload_config

# Get sensor information
service: synthetic_sensors.get_sensor_info
data:
  entity_id: "sensor.syn2_energy_cost_analysis_current_cost_rate"

# Update sensor configuration
service: synthetic_sensors.update_sensor
data:
  entity_id: "sensor.syn2_energy_cost_analysis_current_cost_rate"
  formula: "updated_formula"

# Evaluate formula for testing
service: synthetic_sensors.evaluate_formula
data:
  formula: "A + B * 2"
  context:
    A: 10
    B: 5
```

## Manual component setup

```python
from ha_synthetic_sensors import (
    ConfigManager,
    Evaluator,
    NameResolver,
    SensorManager,
    ServiceLayer
)

# Initialize components
config_manager = ConfigManager(hass)
name_resolver = NameResolver(hass, variables=variables)
evaluator = Evaluator(hass)
sensor_manager = SensorManager(hass, name_resolver, async_add_entities)
service_layer = ServiceLayer(
    hass, config_manager, sensor_manager, name_resolver, evaluator
)

# Load configuration
config = config_manager.load_from_file("config.yaml")
await sensor_manager.load_configuration(config)

# Set up services
await service_layer.async_setup_services()
```

## Type safety

The package uses TypedDict for all data structures to provide type safety and better IDE support:

```python
from ha_synthetic_sensors.config_manager import FormulaConfigDict, SensorConfigDict
from ha_synthetic_sensors.evaluator import EvaluationResult
from ha_synthetic_sensors.service_layer import ServiceResponseData

# Configuration validation with types
validation_result = validate_yaml_content(yaml_content)
if validation_result["is_valid"]:
    sensors_count = validation_result["sensors_count"]
    formulas_count = validation_result["formulas_count"]

# Formula evaluation with typed results
result = evaluator.evaluate_formula(formula_config)
if result["success"]:
    value = result["value"]
else:
    error = result["error"]

# Integration status checking
status = integration.get_integration_status()
sensors_active = status["sensors_count"]
services_running = status["services_registered"]
```

Available TypedDict interfaces:

- `FormulaConfigDict`, `SensorConfigDict`, `ConfigDict` - Configuration structures
- `EvaluationResult`, `CacheStats`, `DependencyValidation` - Evaluator results
- `ServiceResponseData`, `EvaluationResponseData` - Service responses
- `EntityCreationResult`, `ValidationResult` - Entity factory results
- `VariableValidationResult`, `FormulaDependencies` - Name resolver results
- `IntegrationSetupResult`, `IntegrationStatus` - Integration management

## Configuration file format

Required fields:
- `unique_id`: Unique identifier for the sensor
- `formulas.id`: Unique identifier for each formula
- `formulas.formula`: Mathematical expression

Optional fields:
- `name`: Display name for the sensor
- `formulas.name`: Display name for the formula
- `formulas.variables`: Map variable names to entity IDs
- `formulas.unit_of_measurement`: Units for the result
- `formulas.device_class`: Home Assistant device class
- `formulas.state_class`: State class for statistics
- `formulas.icon`: Icon for the entity

## Auto-configuration

The package automatically loads configuration files from these locations:

- `<config>/synthetic_sensors_config.yaml`
- `<config>/synthetic_sensors.yaml`
- `<config>/syn2_config.yaml`
- `<config>/syn2.yaml`

## Entity ID generation

Sensors create entities with predictable IDs:

- Sensor entities: `sensor.syn2_{unique_id}`
- Formula entities: `sensor.syn2_{unique_id}_{formula_id}`

## Dependencies

Core dependencies:
- `pyyaml` - YAML configuration parsing
- `simpleeval` - Safe mathematical expression evaluation
- `voluptuous` - Configuration validation

Development dependencies:
- `pytest` - Testing framework
- `pytest-asyncio` - Async test support
- `pytest-cov` - Coverage reporting
- `ruff` - Code linting and formatting
- `mypy` - Type checking
- `bandit` - Security scanning

## Development commands

```bash
# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=src/ha_synthetic_sensors

# Format code
poetry run ruff format .

# Lint code
poetry run ruff check .

# Type checking
poetry run mypy src/ha_synthetic_sensors

# Run all pre-commit hooks
poetry run pre-commit run --all-files
```

## Architecture

Core components:

- `ConfigManager` - YAML configuration loading and validation
- `Evaluator` - Mathematical expression evaluation with caching
- `NameResolver` - Entity ID resolution and variable mapping
- `SensorManager` - Sensor lifecycle management
- `ServiceLayer` - Home Assistant service integration
- `SyntheticSensorsIntegration` - Main integration class

## License

MIT License

## Repository

- GitHub: https://github.com/SpanPanel/ha-synthetic-sensors
- Issues: https://github.com/SpanPanel/ha-synthetic-sensors/issues
