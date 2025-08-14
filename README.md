# HA Synthetic Sensors

[![GitHub Release](https://img.shields.io/github/v/release/LegoTypes/ha-synthetic-sensors?style=flat-square)](https://github.com/LegoTypes/ha-synthetic-sensors/releases)
[![PyPI Version](https://img.shields.io/pypi/v/ha-synthetic-sensors?style=flat-square)](https://pypi.org/project/ha-synthetic-sensors/)
[![Python Version](https://img.shields.io/pypi/pyversions/ha-synthetic-sensors?style=flat-square)](https://pypi.org/project/ha-synthetic-sensors/)
[![License](https://img.shields.io/github/license/LegoTypes/ha-synthetic-sensors?style=flat-square)](https://github.com/LegoTypes/ha-synthetic-sensors/blob/main/LICENSE)

[![CI Status](https://img.shields.io/github/actions/workflow/status/LegoTypes/ha-synthetic-sensors/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/LegoTypes/ha-synthetic-sensors/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/codecov/c/github/LegoTypes/ha-synthetic-sensors?style=flat-square)](https://codecov.io/gh/LegoTypes/ha-synthetic-sensors)
[![Code Quality](https://img.shields.io/codefactor/grade/github/LegoTypes/ha-synthetic-sensors?style=flat-square)](https://www.codefactor.io/repository/github/legotypes/ha-synthetic-sensors)
[![Security](https://img.shields.io/snyk/vulnerabilities/github/LegoTypes/ha-synthetic-sensors?style=flat-square)](https://snyk.io/test/github/LegoTypes/ha-synthetic-sensors)

[![Pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&style=flat-square)](https://github.com/pre-commit/pre-commit)
[![Linting: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)
[![Type Checking: MyPy](https://img.shields.io/badge/type%20checking-mypy-blue?style=flat-square)](https://mypy-lang.org/)

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-support%20development-FFDD00?style=flat-square&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/cayossarian)

A Python package for creating formula-based synthetic sensors in Home Assistant integrations using YAML configuration and
mathematical expressions.

## What it does

Synthetic sensors are **sensor extensions** that provide capabilities beyond the base sensors or create new sensors with
formula-based calculations. They provide a new state value by applying mathematical formulas to other entities, allowing you
to:

- **Extend sensor capabilities** with calculated attributes
- **Transform sensor values** using mathematical formulations
- **Combine multiple sensors** into derived metrics
- **Add computed states** without modifying original sensors
- **Add computed attributes** that evaluate based on the main sensor state or other entities

## Key Features

- **Sensor Definition and Modification**: Without code modification change the sensor or attribute state with YAML
- **Bulk Load/Modify and Per-Sensor CRUD**: Load complete sensor sets or make granular changes
- **Rich Formula Based States**: Formulas with natural syntax and powerful evaluation and collection patterns
- **Variable reuse**: Define variables globally or per sensor and use those variables in formulas or attributes
- **Dot notation**: Easy access to entity attributes in formulas
- **Automatic Entity-ID Tracking**: Updates the definitions based on external HA entity renaming
- **Type safety**: Complete TypedDict interfaces for better IDE support and validation
- **Storage-first architecture**: Runtime configuration changes without file modifications
- **Built for Performance**: AST caching and evaluation of formulas and bulk modification event storm avoidance
- **Cross-Attribute References**: Formulas can reference other attributes with proper evaluation order
- **Dependency Validation**: Automatic detection of circular dependencies and variable conflicts

## Installation

Install the package using pip:

```bash
pip install ha-synthetic-sensors
```

For development setup:

```bash
git clone https://github.com/LegoTypes/ha-synthetic-sensors
git clone https://github.com/LegoTypes/ha-synthetic-sensors
cd ha-synthetic-sensors
poetry install --with dev
./setup-hooks.sh
```

## Quick Start

Here's a simple example of how to create synthetic sensors:

```yaml
version: "1.0"

sensors:
  energy_cost_current:
    name: "Current Energy Cost"
    formula: "current_power * electricity_rate / conversion_factor"
    variables:
      current_power: "sensor.span_panel_instantaneous_power"
      electricity_rate: "input_number.electricity_rate_cents_kwh"
      conversion_factor: 1000
    metadata:
      unit_of_measurement: "¢/h"
      state_class: "total"
      device_class: "monetary"
      icon: "mdi:currency-usd"

  energy_cost_analysis:
    name: "Energy Cost Analysis"
    formula: "current_power * electricity_rate / 1000"
    attributes:
      daily_projected:
        formula: "state * 24"
        metadata:
          unit_of_measurement: "¢"
          suggested_display_precision: 2
      monthly_projected:
        formula: "state * 24 * 30"
        metadata:
          unit_of_measurement: "¢"
          suggested_display_precision: 2
    variables:
      current_power: "sensor.span_panel_instantaneous_power"
      electricity_rate: "input_number.electricity_rate_cents_kwh"
    metadata:
      unit_of_measurement: "¢/h"
      device_class: "monetary"
      state_class: "total"
```

### Major Components

- **StorageManager** - Manages sensor set storage and configuration
- **SensorSet** - Handle for individual sensor set operations
- **FormulaConfig/SensorConfig** - Configuration classes for sensors and formulas
- **DataProviderResult** - Type definition for data provider callbacks
- **SyntheticSensorsIntegration** - Main integration class for standalone use

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

## Syntax Documentation

For detailed syntax examples and advanced usage patterns, see the
[Cookbook](https://github.com/LegoTypes/ha-synthetic-sensors/blob/main/docs/cookbook.md).

## Integration Documentation

For detailed implementation examples, API documentation, and integration patterns, see the
[Integration Guide](https://github.com/LegoTypes/ha-synthetic-sensors/blob/main/docs/Synthetic_Sensors_Integration_Guide.md).
