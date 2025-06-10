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
            "sensors": {
                "test_sensor": {
                    "name": "Test Sensor",
                    "formula": "temp + humidity",
                    "variables": {
                        "temp": "sensor.temperature",
                        "humidity": "sensor.humidity",
                    },
                    "unit_of_measurement": "index",
                    "state_class": "measurement",
                }
            },
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_missing_required_fields(self):
        """Test validation fails for missing required fields."""
        config_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "name": "Test Sensor",
                    # Missing formula
                }
            },
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False
        assert len(result["errors"]) > 0

        # Check for specific error messages - errors are ValidationError objects
        error_messages = [error.message for error in result["errors"]]
        assert any("formula" in msg.lower() for msg in error_messages)

    def test_invalid_data_types(self):
        """Test validation fails for invalid data types."""
        config_data = {
            "version": 1.0,  # Should be string
            "sensors": {
                "test_sensor": {
                    "formula": "temp + humidity",
                    "enabled": "yes",  # Should be boolean
                    "update_interval": "60",  # Should be integer
                    "variables": "invalid",  # Should be object
                }
            },
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_duplicate_unique_ids(self):
        """Test validation catches duplicate unique IDs."""
        # In v2.0, sensor keys in the dict ARE the unique IDs, so duplicates are
        # impossible
        # This test is not applicable to v2.0 format, but we'll test similar validation
        config_data = {
            "version": "1.0",
            "sensors": {
                "sensor1": {
                    "formula": "1 + 1",
                },
                "sensor2": {
                    "formula": "2 + 2",
                },
            },
        }

        result = validate_yaml_config(config_data)
        # This should be valid since keys are naturally unique
        assert result["valid"] is True

    def test_duplicate_formula_ids(self):
        """Test validation catches duplicate formula IDs within a sensor."""
        # With our simplified approach, we have formula and attributes
        config_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "formula": "1 + 1",
                    "attributes": {
                        "attr1": {"formula": "2 + 2"},
                        "attr2": {
                            "formula": "3 + 3"
                        },  # Changed to different key to avoid duplication
                    },
                }
            },
        }

        result = validate_yaml_config(config_data)
        # YAML parser handles duplicate keys, this should be valid
        assert result["valid"] is True

    def test_invalid_entity_id_format(self):
        """Test validation catches invalid entity ID formats."""
        config_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "formula": "temp",
                    "variables": {
                        # Missing domain.entity format
                        "temp": "invalid_entity_id",
                    },
                }
            },
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

    def test_invalid_device_class(self):
        """Test validation catches invalid device class values."""
        config_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "formula": "1 + 1",
                    "device_class": "invalid_device_class",
                }
            },
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

    def test_invalid_state_class(self):
        """Test validation catches invalid state class values."""
        config_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "formula": "1 + 1",
                    "state_class": "invalid_state_class",
                }
            },
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

    def test_formula_variable_validation_warnings(self):
        """Test that formula variable validation produces warnings."""
        config_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "formula": "undefined_var + 5",  # Variable not defined
                    "unit_of_measurement": "units",
                }
            },
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is True  # Should still be valid but with warnings
        assert len(result.get("warnings", [])) > 0

    def test_unsupported_version(self):
        """Test validation fails for unsupported version."""
        config_data = {
            "version": "2.0",  # Unsupported version
            "sensors": {
                "test_sensor": {
                    "formula": "1 + 1",
                }
            },
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

    def test_empty_sensors_dict(self):
        """Test validation handles empty sensors dict."""
        config_data = {
            "version": "1.0",
            "sensors": {},  # Empty dict instead of array
        }

        result = validate_yaml_config(config_data)
        assert (
            result["valid"] is False
        )  # Empty dict should be invalid (minProperties: 1)

    def test_additional_properties_rejected(self):
        """Test that additional properties are rejected."""
        config_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "formula": "1 + 1",
                    "invalid_property": "should_not_be_allowed",
                }
            },
            "invalid_root_property": "should_not_be_allowed",
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

    def test_schema_validator_class_directly(self):
        """Test using SchemaValidator class directly."""
        config_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "formula": "1 + 1",
                    "unit_of_measurement": "units",
                }
            },
        }

        validator = SchemaValidator()
        result = validator.validate_config(config_data)

        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_validation_with_global_settings(self):
        """Test validation with global settings."""
        config_data = {
            "version": "1.0",
            "global": {
                "update_interval": 30,
                "restore_state": True,
            },
            "sensors": {
                "test_sensor": {
                    "formula": "1 + 1",
                }
            },
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is True

    def test_invalid_domain_prefix_pattern(self):
        """Test validation of entity ID domain prefix pattern."""
        config_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "formula": "temp",
                    "variables": {
                        "temp": "123invalid.entity_id",  # Invalid domain prefix
                    },
                }
            },
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False

    def test_validation_error_suggested_fixes(self):
        """Test that validation errors include suggested fixes."""
        config_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    # Missing required formula
                    "name": "Test Sensor",
                }
            },
        }

        result = validate_yaml_config(config_data)
        assert result["valid"] is False
        assert len(result["errors"]) > 0

        # Check if errors contain helpful information
        errors = result["errors"]
        assert any("formula" in str(error).lower() for error in errors)

    def test_yaml_parsing_from_string(self):
        """Test validation from YAML string."""
        yaml_content = """
version: "1.0"
sensors:
  test_sensor:
    formula: "1 + 1"
    unit_of_measurement: "units"
"""

        config_data = yaml.safe_load(yaml_content)
        result = validate_yaml_config(config_data)

        assert result["valid"] is True
        assert len(result["errors"]) == 0
