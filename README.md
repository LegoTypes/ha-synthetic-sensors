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
    formula: "current_power * electricity_rate / conversion_factor"
    variables:
      current_power: "sensor.span_panel_instantaneous_power"
      electricity_rate: "input_number.electricity_rate_cents_kwh"
      conversion_factor: 1000                    # Literal: watts to kilowatts
    unit_of_measurement: "¢/h"
    state_class: "measurement"

  # Another simple sensor with numeric literals
  solar_sold_power:
    name: "Solar Sold Power"
    formula: "abs(min(grid_power, zero_threshold))"
    variables:
      grid_power: "sensor.span_panel_current_power"
      zero_threshold: 0                         # Literal: threshold value
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
    unit_of_measurement: "%"
    device_class: "power_factor"
    state_class: "measurement"
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
    unit_of_measurement: "kWh"
    device_class: "energy_storage"
    state_class: "measurement"
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

**Benefits of device association:**

- Sensors appear grouped under their device in the Home Assistant UI
- Better organization for complex setups with multiple related sensors
- Device-level controls and automations
- Cleaner entity management and discovery

**How attributes work:**

- Main sensor state is calculated first using the `formula`
- Attributes are calculated second and have access to the `state` variable
- `state` always refers to the fresh main sensor calculation
- Attributes can also reference other entities normally (like `sensor.max_power_capacity` above)
- Each attribute shows up as `sensor.energy_cost_analysis.daily_projected` etc. in HA

## Entity Reference Patterns

| Pattern Type | Syntax | Example | Use Case |
| ------------ | ------ | ------- | -------- |
| **Direct Entity ID** | `sensor.entity_name` | `sensor.power_meter` | Quick references, cross-sensor |
| **Variable Alias** | `variable_name` | `power_meter` | Most common, clean formulas |
| **Sensor Key Reference** | `sensor_key` | `energy_analysis` | Reference other synthetic sensors |
| **State Alias (attributes)** | `state` | `state * 24` | In attributes, reference main sensor |
| **Attribute Dot Notation** | `entity.attribute` | `sensor1.battery_level` | Access entity attributes |
| **Collection Functions** | `mathFunc(pattern:value)` | `sum(device_class:temperature)` | Aggregate entities by pattern |

**Entity ID Generation**: The sensor key serves as the unique_id. Home Assistant creates entity_ids as
`sensor.syn2_{key}` unless overridden with the optional `entity_id` field.

### Variable Purpose and Scope

A variable serves as a short alias for an entity ID, collection pattern, or numeric literal that it references.

Variables can be:

- **Entity IDs**: `"sensor.power_meter"` - References Home Assistant entities
- **Numeric Literals**: `42`, `3.14`, `-5.0` - Direct numeric values for constants
- **Collection Patterns**: `"device_class:temperature"` - Dynamic entity aggregation

**Important**: All variables must be defined at the sensor level in the `variables` section. Attribute-level variable
definitions are not supported.

Once defined, a variable can be used in any formula whether in the main sensor state formula or attribute formula.

Attribute formulas automatically inherit all variables from their parent sensor:

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
      battery_devices: "device_class:battery"
    attributes:
      daily_projection:
        formula: "energy_analysis * 24" # References main sensor by key
      efficiency_percent:
        formula: "solar_power / (grid_power + solar_power) * efficiency_factor * 100"
        unit_of_measurement: "%"
      cost_with_tax:
        formula: "energy_analysis * (1 + tax_rate)"  # Uses numeric literal
        unit_of_measurement: "¢"
      low_battery_count:
        formula: "count(battery_devices.battery_level<20)" # Uses collection variable with dot notation
        unit_of_measurement: "devices"
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
    unit_of_measurement: "%"
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

**Detecting Empty Collections (Advanced):**

If you need to distinguish between "no matching entities" and "entities with zero values", you can use a formula like this:

```yaml
sensors:
  smart_power_monitor:
    name: "Smart Power Monitor"
    formula: "count(power_pattern) > 0 ? sum(power_pattern) : null"
    variables:
      power_pattern: "device_class:power"
    # This sensor will be unavailable when no power entities exist,
    # but will show 0 when power entities exist but all have zero values
```

## Formula examples

```python
# Basic arithmetic and conditionals
"circuit_1 + circuit_2 + circuit_3"
"net_power * buy_rate / 1000 if net_power > 0 else abs(net_power) * sell_rate / 1000"

# Using numeric literals in formulas
"sensor_value * 0.85 + 100"                     # Efficiency factor and offset
"(temperature - 32) * 5 / 9"                    # Fahrenheit to Celsius conversion
"power * 1.0955"                                 # Tax calculation with literal rate

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

### Numeric Literals in Variables

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
    unit_of_measurement: "°C"

  power_efficiency:
    name: "Power Efficiency"
    formula: "actual_power / rated_power * percentage"
    variables:
      actual_power: "sensor.current_power"
      rated_power: 1000                  # Literal: rated power in watts
      percentage: 100                    # Literal: convert to percentage
    unit_of_measurement: "%"

  cost_calculator:
    name: "Energy Cost"
    formula: "energy_kwh * rate_per_kwh * (1 + tax_rate)"
    variables:
      energy_kwh: "sensor.energy_usage"
      rate_per_kwh: 0.12                 # Literal: cost per kWh
      tax_rate: 0.085                    # Literal: tax percentage
    unit_of_measurement: "$"
```

**Supported literal types:**

- **Integers**: `42`, `-10`, `0`
- **Floats**: `3.14159`, `-2.5`, `0.001`
- **Scientific notation**: `1.23e-4`, `2.5e6`

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

## Logging Configuration

The package provides logging utilities to help with debugging and troubleshooting. By default, the package uses
Python's standard logging hierarchy, but you may need to explicitly configure it in Home Assistant environments.

### Enable Debug Logging

```python
import logging
import ha_synthetic_sensors

# Configure debug logging for the entire package
ha_synthetic_sensors.configure_logging(logging.DEBUG)

# Test that logging is working (optional)
ha_synthetic_sensors.test_logging()

# Check current logging configuration (optional)
logging_info = ha_synthetic_sensors.get_logging_info()
_LOGGER.debug("Synthetic sensors logging: %s", logging_info)
```

### Home Assistant Configuration

Alternatively, you can configure logging in Home Assistant's `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    # Your integration
    custom_components.your_integration: debug
    # The synthetic sensors package
    ha_synthetic_sensors: debug
    # Specific modules (optional)
    ha_synthetic_sensors.evaluator: debug
    ha_synthetic_sensors.service_layer: debug
```

### Troubleshooting Logging Issues

If you're not seeing log output from the package:

1. **Call the test function**: `ha_synthetic_sensors.test_logging()` outputs test messages to verify logging works
2. **Check configuration**: `ha_synthetic_sensors.get_logging_info()` shows current logger levels and settings
3. **Verify integration setup**: Ensure your integration is also set to debug level
4. **Check HA logs**: Look for the configuration confirmation message from `configure_logging()`

## Type safety

Uses TypedDict for all data structures providing type safety and IDE support:

```python
from ha_synthetic_sensors.config_manager import FormulaConfigDict, SensorConfigDict
from ha_synthetic_sensors.types import EvaluationResult, DataProviderResult

# Typed configuration validation
validation_result = validate_yaml_content(yaml_content)
if validation_result["is_valid"]:
    sensors_count = validation_result["sensors_count"]

# Typed formula evaluation
result = evaluator.evaluate_formula(formula_config)
if result["success"]:
    value = result["value"]

# Typed data provider callback
def my_data_provider(entity_id: str) -> DataProviderResult:
    return {"value": get_sensor_value(entity_id), "exists": True}
```

**Available TypedDict interfaces:** Configuration structures, evaluation results, data provider callbacks, service responses,
entity creation results, integration management, and more.

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

### Integration Data Provider (hybrid data access)

For integrations that need to provide some sensor data directly while still using Home Assistant entities for others:

**See [Integration Data Provider Documentation](docs/integration_data_provider.md) for complete setup guide.**

```python
from ha_synthetic_sensors.sensor_manager import SensorManagerConfig
from ha_synthetic_sensors.types import DataProviderCallback, DataProviderResult

class MyCustomIntegration:
    def get_integration_data(self, entity_id: str) -> DataProviderResult:
        """Provide data directly from integration for specific entities."""
        if entity_id in self.local_sensors:
            value = self.local_sensors[entity_id].current_value
            return {"value": value, "exists": True}
        return {"value": None, "exists": False}

    async def async_setup_sensors(self, async_add_entities):
        # Configure sensor manager with data provider callback
        manager_config = SensorManagerConfig(
            device_info=self.device_info,
            lifecycle_managed_externally=True,
            data_provider_callback=self.get_integration_data
        )

        synthetic_integration = SyntheticSensorsIntegration(self.hass)
        self.sensor_manager = await synthetic_integration.create_managed_sensor_manager(
            add_entities_callback=async_add_entities,
            manager_config=manager_config
        )

        # Register entities that this integration can provide data for
        self.sensor_manager.register_data_provider_entities(set(self.local_sensors.keys()))

        # Load config - evaluator will automatically use callbacks for registered entities
        # and Home Assistant state queries for all other entities
        config = await self.sensor_manager.load_config_from_yaml(yaml_config)
        await self.sensor_manager.apply_config(config)
```

**Registration Methods:**

- **`register_data_provider_entities(entity_ids: set[str])`**: Register entities that integration can provide data for
- **`update_data_provider_entities(entity_ids: set[str])`**: Update the registered entity list (replaces existing)
- **`get_registered_entities() -> set[str]`**: Get current registered entities

**Data Provider Callback:**

- **`DataProviderCallback`**: `(entity_id: str) -> DataProviderResult` - Returns a TypedDict with `value` and `exists` fields

**Hybrid Data Access Behavior - Integration Authority Model:**

- **Entity registration**: The integration **proactively registers** which entities it owns for synthetic sensor evaluation
- **Integration entities**: All registered entities use the data provider callback exclusively
- **Home Assistant entities**: All other entities use standard Home Assistant state queries exclusively
- **No fallback**: Each entity uses exactly one data source - strict error handling prevents silent failures
- **Entity state independence**: Integration-provided entities don't need to exist in Home Assistant's entity registry
- **Seamless configuration**: YAML syntax is identical regardless of data source - the evaluator automatically routes
  requests

**Device integration benefits:** Unified device view, lifecycle control, update coordination, entity naming consistency.

**For detailed implementation guide:** See [Integration Data Provider Documentation](docs/integration_data_provider.md) for
complete examples, error handling details, and advanced usage patterns.

## Exception Handling

Follows Home Assistant coordinator patterns with **strict error handling**:

**Fatal Errors** (permanent configuration issues):

- Syntax errors, missing entities, invalid patterns, undefined variables
- Triggers circuit breaker, sensor becomes "unavailable"
- **Missing entities**: When a variable references a non-existent entity ID, a critical error is raised

**Transitory Errors** (temporary conditions):

- Unavailable entities (temporarily), non-numeric states, cache issues
- Allows graceful degradation, sensor becomes "unknown"

**Key Behavior Changes**:

- **No silent fallbacks**: Missing entities or undefined variables cause immediate errors rather than defaulting to 0
- **Strict validation**: All entity IDs in variables must exist, or the sensor will fail to evaluate
- **Clear error messages**: Detailed error information helps identify configuration issues

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
