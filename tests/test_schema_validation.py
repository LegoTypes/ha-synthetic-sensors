"""
Test schema validation functionality.

This module tests the comprehensive YAML schema validation system.
"""

import yaml

from ha_synthetic_sensors.schema_validator import SchemaValidator, validate_yaml_config


class TestSchemaValidation:
    """Test schema validation functionality."""

    def test_valid_config_passes_validation(self):
        """Test that a valid configuration passes validation."""
        config_data = {
            "version": "1.0",
            "sensors": [
                {
                    "unique_id": "test_sensor",
                    "name": "Test Sensor",
                    "formulas": [
                        {
                            "id": "test_formula",
                            "name": "Test Formula",
                            "formula": "temp + humidity",
                            "variables": {
                                "temp": "sensor.temperature",
                                "humidity": "sensor.humidity",
                            },
                            "unit_of_measurement": "index",
                            "state_class": "measurement",
                        }
                    ],
                }
            ],
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_missing_required_fields(self):
        """Test validation fails for missing required fields."""
        config_data = {
            "version": "1.0",
            "sensors": [
                {
                    # Missing unique_id
                    "name": "Test Sensor",
                    "formulas": [
                        {
                            # Missing id and formula
                            "name": "Test Formula",
                        }
                    ],
                }
            ],
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False
        assert len(result["errors"]) > 0

        # Check for specific error messages
        error_messages = [error.message for error in result["errors"]]
        assert any(
            "'unique_id' is a required property" in msg for msg in error_messages
        )
        assert any("'id' is a required property" in msg for msg in error_messages)
        assert any("'formula' is a required property" in msg for msg in error_messages)

    def test_invalid_data_types(self):
        """Test validation fails for invalid data types."""
        config_data = {
            "version": 1.0,  # Should be string
            "sensors": [
                {
                    "unique_id": "test_sensor",
                    "enabled": "yes",  # Should be boolean
                    "update_interval": "60",  # Should be integer
                    "formulas": [
                        {
                            "id": "test_formula",
                            "formula": "temp + humidity",
                            "variables": "invalid",  # Should be object
                        }
                    ],
                }
            ],
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_duplicate_unique_ids(self):
        """Test validation catches duplicate unique IDs."""
        config_data = {
            "version": "1.0",
            "sensors": [
                {
                    "unique_id": "duplicate_sensor",
                    "formulas": [{"id": "formula1", "formula": "1 + 1"}],
                },
                {
                    "unique_id": "duplicate_sensor",  # Duplicate
                    "formulas": [{"id": "formula2", "formula": "2 + 2"}],
                },
            ],
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

        error_messages = [error.message for error in result["errors"]]
        assert any("Duplicate unique_id" in msg for msg in error_messages)

    def test_duplicate_formula_ids(self):
        """Test validation catches duplicate formula IDs within a sensor."""
        config_data = {
            "version": "1.0",
            "sensors": [
                {
                    "unique_id": "test_sensor",
                    "formulas": [
                        {"id": "duplicate_formula", "formula": "1 + 1"},
                        {"id": "duplicate_formula", "formula": "2 + 2"},  # Duplicate
                    ],
                }
            ],
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

        error_messages = [error.message for error in result["errors"]]
        assert any("Duplicate formula id" in msg for msg in error_messages)

    def test_invalid_entity_id_format(self):
        """Test validation catches invalid entity ID formats."""
        config_data = {
            "version": "1.0",
            "sensors": [
                {
                    "unique_id": "test_sensor",
                    "formulas": [
                        {
                            "id": "test_formula",
                            "formula": "temp",
                            "variables": {
                                # Missing domain.entity format
                                "temp": "invalid_entity_id",
                            },
                        }
                    ],
                }
            ],
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

    def test_invalid_device_class(self):
        """Test validation catches invalid device class values."""
        config_data = {
            "version": "1.0",
            "sensors": [
                {
                    "unique_id": "test_sensor",
                    "formulas": [
                        {
                            "id": "test_formula",
                            "formula": "1 + 1",
                            "device_class": "invalid_device_class",
                        }
                    ],
                }
            ],
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

    def test_invalid_state_class(self):
        """Test validation catches invalid state class values."""
        config_data = {
            "version": "1.0",
            "sensors": [
                {
                    "unique_id": "test_sensor",
                    "formulas": [
                        {
                            "id": "test_formula",
                            "formula": "1 + 1",
                            "state_class": "invalid_state_class",
                        }
                    ],
                }
            ],
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

    def test_formula_variable_validation_warnings(self):
        """Test that undefined variables generate warnings."""
        config_data = {
            "version": "1.0",
            "sensors": [
                {
                    "unique_id": "test_sensor",
                    "formulas": [
                        {
                            "id": "test_formula",
                            # undefined_variable not in variables
                            "formula": "temp + undefined_variable",
                            "variables": {
                                "temp": "sensor.temperature",
                            },
                        }
                    ],
                }
            ],
        }

        result = validate_yaml_config(config_data)
        # Should be valid but with warnings
        assert result["valid"] is True
        assert len(result["warnings"]) > 0

        warning_messages = [warning.message for warning in result["warnings"]]
        assert any("undefined variable" in msg.lower() for msg in warning_messages)

    def test_unsupported_version(self):
        """Test that unsupported schema versions are rejected."""
        config_data = {
            "version": "2.0",  # Unsupported version
            "sensors": [],
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

        error_messages = [error.message for error in result["errors"]]
        assert any("Unsupported schema version" in msg for msg in error_messages)

    def test_empty_sensors_array(self):
        """Test that empty sensors array fails validation."""
        config_data = {
            "version": "1.0",
            "sensors": [],  # Empty array should fail minItems: 1
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

    def test_additional_properties_rejected(self):
        """Test that unknown properties are rejected."""
        config_data = {
            "version": "1.0",
            "unknown_property": "should_be_rejected",
            "sensors": [
                {
                    "unique_id": "test_sensor",
                    "unknown_sensor_property": "also_rejected",
                    "formulas": [
                        {
                            "id": "test_formula",
                            "formula": "1 + 1",
                            "unknown_formula_property": "rejected_too",
                        }
                    ],
                }
            ],
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

        error_messages = [error.message for error in result["errors"]]
        assert any(
            "Additional properties are not allowed" in msg for msg in error_messages
        )

    def test_schema_validator_class_directly(self):
        """Test using SchemaValidator class directly."""
        validator = SchemaValidator()

        config_data = {
            "version": "1.0",
            "sensors": [
                {
                    "unique_id": "test_sensor",
                    "formulas": [{"id": "test_formula", "formula": "1 + 1"}],
                }
            ],
        }

        result = validator.validate_config(config_data)
        assert result["valid"] is True

    def test_validation_with_global_settings(self):
        """Test validation with global settings."""
        config_data = {
            "version": "1.0",
            "global_settings": {
                "domain_prefix": "syn2",
                "enabled": True,
                "update_interval": 30,
            },
            "sensors": [
                {
                    "unique_id": "test_sensor",
                    "formulas": [{"id": "test_formula", "formula": "1 + 1"}],
                }
            ],
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is True

    def test_invalid_domain_prefix_pattern(self):
        """Test that invalid domain prefix patterns are rejected."""
        config_data = {
            "version": "1.0",
            "global_settings": {
                "domain_prefix": "Invalid-Prefix",  # lowercase with underscores only
            },
            "sensors": [
                {
                    "unique_id": "test_sensor",
                    "formulas": [{"id": "test_formula", "formula": "1 + 1"}],
                }
            ],
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

    def test_validation_error_suggested_fixes(self):
        """Test that validation errors include helpful suggested fixes."""
        config_data = {
            "version": "1.0",
            "sensors": [
                {
                    # Missing unique_id
                    "formulas": [
                        {
                            # Missing id and formula
                            "name": "Test Formula",
                        }
                    ],
                }
            ],
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

        # Check that errors have suggested fixes
        for error in result["errors"]:
            if "'unique_id' is a required property" in error.message:
                assert "Add 'unique_id' field" in error.suggested_fix
            elif "'formula' is a required property" in error.message:
                assert "Add 'formula' field" in error.suggested_fix

    def test_yaml_parsing_from_string(self):
        """Test validation of YAML content as string."""
        yaml_content = """
version: "1.0"
sensors:
  - unique_id: test_sensor
    formulas:
      - id: test_formula
        formula: "1 + 1"
        """

        yaml_data = yaml.safe_load(yaml_content)
        result = validate_yaml_config(yaml_data)
        assert result["valid"] is True
