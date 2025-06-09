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

```yaml
version: "1.0"

sensors:
  - unique_id: "energy_cost_analysis"
    name: "Energy Cost Analysis"
    formulas:
      - id: "current_cost_rate"
        formula: "current_power * electricity_rate / 1000"
        variables:
          current_power: "sensor.span_panel_instantaneous_power"
          electricity_rate: "input_number.electricity_rate_cents_kwh"
        unit_of_measurement: "¢/h"
        device_class: "monetary"
        state_class: "measurement"

      - id: "daily_projected_cost"
        formula: "current_cost_rate * 24"
        unit_of_measurement: "¢"
        device_class: "monetary"
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

# Math functions
"abs(min(grid_power, 0))"
"max(heating_power, cooling_power)"

# Sensor references (by entity ID)
"sensor.syn2_hvac_total_power_hvac_total + sensor.syn2_lighting_total_power_lighting_total"
```

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
formulas:
  - id: "base_calculation"
    formula: "power_usage * rate"
  - id: "with_tax"
    formula: "base_calculation * 1.08"
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
