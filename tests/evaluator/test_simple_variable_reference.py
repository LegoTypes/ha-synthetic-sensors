"""Test simple variable reference formulas."""

from typing import Any

from ha_synthetic_sensors.schema_validator import SchemaValidator


def test_simple_variable_reference() -> None:
    """Test that a formula can be just a simple variable reference."""
    config: dict[str, Any] = {
        "version": "1.0",
        "sensors": {
            "simple_passthrough": {
                "name": "Simple Passthrough Sensor",
                "formula": "source_value",
                "variables": {"source_value": "sensor.original_sensor"},
                "unit_of_measurement": "W",
            }
        },
    }  # Just the variable name

    validator = SchemaValidator()
    result = validator.validate_config(config)

    assert result["valid"] is True, f"Validation failed with errors: {result['errors']}"
    assert len(result["errors"]) == 0


def test_various_simple_references() -> None:
    """Test various simple reference patterns."""
    configs: list[dict[str, Any]] = [
        # Simple variable reference
        {"formula": "power_meter", "variables": {"power_meter": "sensor.power"}},
        # Direct entity reference (no variables needed)
        {"formula": "sensor.temperature", "variables": {}},
        # Numeric literal (no variables needed)
        {"formula": "42", "variables": {}},
    ]

    for i, config_data in enumerate(configs):
        config: dict[str, Any] = {
            "version": "1.0",
            "sensors": {
                f"test_sensor_{i}": {
                    "name": f"Test Sensor {i}",
                    "formula": config_data["formula"],
                    "variables": config_data["variables"],
                    "unit_of_measurement": "test",
                }
            },
        }

        validator = SchemaValidator()
        result = validator.validate_config(config)

        assert result["valid"] is True, f"Config {i} with formula '{config_data['formula']}' failed: {result['errors']}"
        assert len(result["errors"]) == 0


if __name__ == "__main__":
    test_simple_variable_reference()
    test_various_simple_references()
