"""Test validation of all example YAML files against the schema."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from ha_synthetic_sensors.schema_validator import SchemaValidator


def load_example_configs() -> list[tuple[str, dict[str, Any]]]:
    """Load all example YAML configurations."""
    examples_dir = Path(__file__).parent.parent / "examples"
    yaml_files = list(examples_dir.glob("*.yaml"))

    configs = []
    for yaml_file in sorted(yaml_files):
        with open(yaml_file) as f:
            config = yaml.safe_load(f)

        # Add version if missing (some examples might not have it)
        if "version" not in config:
            config["version"] = "1.0"

        configs.append((yaml_file.name, config))

    return configs


@pytest.mark.parametrize("filename,config", load_example_configs())
def test_example_file_validation(filename: str, config: dict[str, Any]) -> None:
    """Test that each example file passes schema validation."""
    validator = SchemaValidator()
    result = validator.validate_config(config)

    assert result["valid"] is True, f"{filename} has validation errors: {result['errors']}"
    assert len(result["errors"]) == 0, f"{filename} has unexpected errors: {result['errors']}"


def test_schema_rejects_state_formula() -> None:
    """Test that the schema properly rejects 'state_formula' field."""
    yaml_config = """
version: "1.0"
sensors:
  test_sensor:
    name: "Test Sensor"
    state_formula: "some_formula"  # This should be rejected
    variables: {}
    unit_of_measurement: "test"
"""

    config = yaml.safe_load(yaml_config)
    validator = SchemaValidator()
    result = validator.validate_config(config)

    assert result["valid"] is False, "Schema should reject 'state_formula' field"
    assert any("state_formula" in str(error).lower() or "additional properties" in str(error).lower() for error in result["errors"]), f"Expected error about state_formula, got: {result['errors']}"


def test_schema_requires_formula_field() -> None:
    """Test that the schema requires the 'formula' field."""
    yaml_config = """
version: "1.0"
sensors:
  test_sensor:
    name: "Test Sensor"
    # Missing 'formula' field
    variables: {}
    unit_of_measurement: "test"
"""

    config = yaml.safe_load(yaml_config)
    validator = SchemaValidator()
    result = validator.validate_config(config)

    assert result["valid"] is False, "Schema should require 'formula' field"
    assert any("formula" in str(error).lower() and ("required" in str(error).lower() or "missing" in str(error).lower()) for error in result["errors"]), f"Expected error about missing formula, got: {result['errors']}"
