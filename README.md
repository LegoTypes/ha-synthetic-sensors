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
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg?style=flat-square)](https://github.com/psf/black)
[![Linting: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)
[![Type Checking: MyPy](https://img.shields.io/badge/type%20checking-mypy-blue?style=flat-square)](https://mypy-lang.org/)

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-support%20development-FFDD00?style=flat-square&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/cayossarian)

A Python package for creating and managing synthetic, math-based, and hierarchical sensors in Home Assistant integrations
using YAML configuration.

## What it does

- Creates Home Assistant sensor entities from mathematical formulas
- Evaluates math expressions using `simpleeval` library
- Maps variable names to Home Assistant entity IDs
- Manages sensor lifecycle (creation, updates, removal)
- Provides Home Assistant services for configuration management
- Tracks dependencies between sensors
- Caches formula results
- Variable declarations for shortcut annotations in math formulas
- Dynamic entity aggregation (regex, tags, areas, device_class patterns)
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

**Key benefits of device integration:**

- **Unified Device View**: Synthetic sensors appear under your integration's device in HA UI
- **Lifecycle Control**: Parent integration controls setup, reload, and teardown
- **Update Coordination**: Synthetic sensors update within parent's async update routines
- **Entity Naming**: Sensors use parent integration's naming conventions
- **Resource Sharing**: Parent can provide its own HA dependencies (hass, coordinators, etc.)

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
    # entity_id: "sensor.custom_entity_id"  # Optional: override auto-generated entity_id
    formula: "current_power * electricity_rate / 1000"
    attributes:
      daily_projected:
        formula: "state * 24" # ref by main state alias
        unit_of_measurement: "¢"
      monthly_projected:
        formula: "energy_cost_analysis * 24 * 30" # ref by main sensor key
        unit_of_measurement: "¢"
      annual_projected:
        formula: "sensor.syn2_energy_cost_analysis * 24 * 365" # ref by entity_id
        unit_of_measurement: "¢"
      battery_efficiency:
        formula: "current_power * device.battery_level / 100" # using attribute access
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

## Entity Reference Patterns

| Pattern Type                   | Syntax                          | Example                                | Use Case                               |
| ------------------------------ | ------------------------------- | -------------------------------------- | -------------------------------------- |
| **Direct Entity ID**           | `sensor.entity_name`            | `sensor.power_meter`                   | Quick references, cross-sensor         |
| **Variable Alias**             | `variable_name`                 | `power_meter`                          | Most common, clean formulas            |
| **Sensor Key Reference**       | `sensor_key`                    | `energy_analysis`                      | Reference other synthetic sensors      |
| **State Alias (attributes)**   | `state`                         | `state * 24`                           | In attributes, reference main sensor   |
| **Attribute Dot Notation**     | `entity.attribute`              | `sensor1.battery_level`                | Access entity attributes               |
| **Collection Functions**       | `mathFunc(pattern:value)`       | `sum(device_class:temperature)`        | Aggregate entities by pattern          |

**Entity ID Generation**: The sensor key serves as the unique_id. Home Assistant creates entity_ids as
`sensor.syn2_{key}` unless overridden with the optional `entity_id` field.

### Variable Purpose and Scope

A variable serves as a short alias for the sensor or filter that it references.

Once defined a variable can be used in any formula whether in the main sensor state formula or attribute formula.

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
      battery_devices: "device_class:battery"
    attributes:
      daily_projection:
        formula: "energy_analysis * 24" # References main sensor by key
      efficiency_percent:
        formula: "solar_power / (grid_power + solar_power) * 100" # Uses inherited variables
      low_battery_count:
        formula: "count(battery_devices.battery_level<20)" # Uses collection variable with dot notation
        unit_of_measurement: "devices"
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"
```

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
    unit_of_measurement: "W"

  # OR patterns for multiple conditions  
  security_monitoring:
    name: "Security Device Count"
    formula: count("device_class:door|window|lock")
    unit_of_measurement: "devices"
    
  main_floor_power:
    name: "Main Floor Power"
    formula: sum("area:living_room|kitchen|dining_room")
    unit_of_measurement: "W"

  # Attribute filtering with collection variables
  low_battery_devices:
    name: "Low Battery Devices"
    formula: count("battery_devices.battery_level<20")
    variables:
      battery_devices: "device_class:battery"
    unit_of_measurement: "count"

  # Complex mixed patterns
  comprehensive_analysis:
    name: "Comprehensive Analysis"
    formula: 'sum("device_class:power|energy") + count("area:upstairs|downstairs")'
    unit_of_measurement: "mixed"
```

**Available Functions:** `sum()`, `avg()`/`mean()`, `count()`, `min()`/`max()`, `std()`/`var()`

**Collection Patterns:**

- `"device_class:power"` - Entities with specific device class
- `"regex:pattern_variable"` - Entities matching regex pattern from variable
- `"area:kitchen"` - Entities in specific area  
- `"tags:tag1,tag2"` - Entities with specified tags
- `"attribute:battery_level<50"` - Entities with attribute conditions
- `"state:>100|=on"` - Entities with state conditions (supports OR with `|`)

## Formula examples

```python
# Basic arithmetic and conditionals
"circuit_1 + circuit_2 + circuit_3"
"net_power * buy_rate / 1000 if net_power > 0 else abs(net_power) * sell_rate / 1000"

# Mathematical functions
"sqrt(power_a**2 + power_b**2)"              # Square root, exponents
"round(temperature, 1)"                      # Rounding
"clamp(efficiency, 0, 100)"                  # Constrain to range
"map(brightness, 0, 255, 0, 100)"            # Map from one range to another

# Collection functions with OR patterns
sum("device_class:power|energy")            # Sum all power OR energy entities
count("device_class:door|window")           # Count all door OR window entities
avg("device_class:temperature|humidity")    # Average temperature OR humidity sensors

# Dot notation attribute access
"sensor1.battery_level + climate.living_room.current_temperature"

# Cross-sensor references
"sensor.syn2_hvac_total_power + sensor.syn2_lighting_total_power"
```

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

**Key advantages:**

- **Variable reuse**: Define once, use in multiple sensors and attributes
- **Bulk management**: Single YAML file for dozens of related sensors
- **Dependency tracking**: Automatic sensor update ordering
- **Type safety**: TypedDict interfaces for better IDE support
- **Services**: Built-in reload, update, and testing capabilities

## Home Assistant services

```yaml
# Reload configuration
service: synthetic_sensors.reload_config

# Get sensor information  
service: synthetic_sensors.get_sensor_info
data:
  entity_id: "sensor.syn2_energy_cost_analysis"

# Update sensor configuration
service: synthetic_sensors.update_sensor
data:
  entity_id: "sensor.syn2_energy_cost_analysis"
  formula: "updated_formula"

# Test formula evaluation
service: synthetic_sensors.evaluate_formula
data:
  formula: "A + B * 2"
  context: { A: 10, B: 5 }
```

## Manual component setup

```python
from ha_synthetic_sensors import (
    ConfigManager, Evaluator, NameResolver, SensorManager, ServiceLayer
)

# Initialize and setup
config_manager = ConfigManager(hass)
name_resolver = NameResolver(hass, variables=variables)
evaluator = Evaluator(hass)
sensor_manager = SensorManager(hass, name_resolver, async_add_entities)
service_layer = ServiceLayer(hass, config_manager, sensor_manager, name_resolver, evaluator)

# Load configuration and setup services
config = config_manager.load_from_file("config.yaml")
await sensor_manager.load_configuration(config)
await service_layer.async_setup_services()
```

## Type safety

Uses TypedDict for all data structures providing type safety and IDE support:

```python
from ha_synthetic_sensors.config_manager import FormulaConfigDict, SensorConfigDict
from ha_synthetic_sensors.evaluator import EvaluationResult

# Typed configuration validation
validation_result = validate_yaml_content(yaml_content)
if validation_result["is_valid"]:
    sensors_count = validation_result["sensors_count"]

# Typed formula evaluation
result = evaluator.evaluate_formula(formula_config)
if result["success"]:
    value = result["value"]
```

**Available TypedDict interfaces:** Configuration structures, evaluation results, service responses, entity creation results,
integration management, and more.

## Configuration format

**Required:** `formula` - Mathematical expression

**Recommended:** `name`, `device_class`, `state_class`, `unit_of_measurement`

**Optional:** `variables`, `attributes`, `enabled`, `icon`

**Auto-configuration files:** `<config>/synthetic_sensors_config.yaml`, `<config>/syn2_config.yaml`, etc.

**Entity ID format:** `sensor.syn2_{sensor_key}`

## Integration Setup

### Standalone Integration

```python
from ha_synthetic_sensors import async_setup_integration

async def async_setup_entry(hass, config_entry, async_add_entities):
    return await async_setup_integration(hass, config_entry, async_add_entities)
```

### Device Integration (sensors appear under parent device)

```python
from ha_synthetic_sensors.integration import SyntheticSensorsIntegration

class MyCustomIntegration:
    async def async_setup_sensors(self, async_add_entities):
        synthetic_integration = SyntheticSensorsIntegration(self.hass)
        
        self.sensor_manager = await synthetic_integration.create_managed_sensor_manager(
            add_entities_callback=async_add_entities,
            device_info=self.device_info,
            lifecycle_managed_externally=True
        )
        
        # Load YAML config and apply
        config = await self.sensor_manager.load_config_from_yaml(yaml_config)
        await self.sensor_manager.apply_config(config)
```

**Device integration benefits:** Unified device view, lifecycle control, update coordination, entity naming consistency.

## Exception Handling

Follows Home Assistant coordinator patterns with **two-tier error handling**:

**Fatal Errors** (permanent configuration issues):

- Syntax errors, missing entities, invalid patterns
- Triggers circuit breaker, sensor becomes "unavailable"

**Transitory Errors** (temporary conditions):

- Unavailable entities, non-numeric states, cache issues
- Allows graceful degradation, sensor becomes "unknown"

**Exception Types:**

- `SyntheticSensorsError` - Base for all package errors
- `SyntheticSensorsConfigError` - Configuration issues
- `FormulaSyntaxError`, `MissingDependencyError` - Formula evaluation
- `SensorConfigurationError`, `SensorCreationError` - Sensor management

**Integration with parent coordinators:** Fatal errors are logged but don't crash coordinators; transitory errors result
in "unknown" state until resolved.

## Dependencies

**Core:** `pyyaml`, `simpleeval`, `voluptuous`
**Development:** `pytest`, `pytest-asyncio`, `pytest-cov`, `black`, `ruff`, `mypy`, `bandit`, `pre-commit`

## Development

```bash
# Setup
poetry install --with dev
poetry run pre-commit install

# Testing and quality
poetry run pytest --cov=src/ha_synthetic_sensors
poetry run black --line-length 88 .
poetry run ruff check --fix .
poetry run mypy src/ha_synthetic_sensors
poetry run pre-commit run --all-files

# Fix markdown (if markdownlint fails)
./scripts/fix-markdown.sh
```

**Important:** Pre-commit hooks check but don't auto-fix markdown. Run `./scripts/fix-markdown.sh` locally if markdownlint fails.

## Architecture

**Core components:** `ConfigManager`, `Evaluator`, `NameResolver`, `SensorManager`, `ServiceLayer`, `SyntheticSensorsIntegration`

## License

MIT License

## Repository

- GitHub: <https://github.com/SpanPanel/ha-synthetic-sensors>
- Issues: <https://github.com/SpanPanel/ha-synthetic-sensors/issues>
