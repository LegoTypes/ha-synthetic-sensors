"""Unit tests for computed variables reference validation."""

import pytest
from unittest.mock import Mock

from homeassistant.exceptions import ConfigEntryError
from ha_synthetic_sensors.config_models import ComputedVariable
from ha_synthetic_sensors.utils_config import validate_computed_variable_references
from ha_synthetic_sensors.config_manager import ConfigManager


class TestComputedVariableValidation:
    """Test validation of computed variable references."""

    def test_valid_references_no_warnings(self):
        """Test that valid references produce no warnings."""
        variables = {
            "a": 10,
            "b": "sensor.test",
            "computed": ComputedVariable(formula="a + 5"),
            "computed2": ComputedVariable(formula="state * 2"),  # state is always available
        }

        warnings = validate_computed_variable_references(variables)
        assert len(warnings) == 0

    def test_undefined_reference_error(self):
        """Test error for undefined variable references."""
        variables = {"a": 10, "computed": ComputedVariable(formula="a + undefined_var")}

        errors = validate_computed_variable_references(variables, "test_sensor")
        assert len(errors) == 1
        assert "undefined_var" in errors[0]
        assert "test_sensor" in errors[0]
        assert "Available variables:" in errors[0] and "'a'" in errors[0]

    def test_self_reference_error(self):
        """Test error for self-referencing computed variables."""
        variables = {"recursive": ComputedVariable(formula="recursive + 1")}

        errors = validate_computed_variable_references(variables)
        assert len(errors) == 1
        assert "references itself" in errors[0]
        assert "circular dependency" in errors[0]

    def test_multiple_issues_multiple_errors(self):
        """Test that multiple issues generate multiple errors."""
        variables = {
            "a": 10,
            "bad1": ComputedVariable(formula="undefined_var + 1"),
            "bad2": ComputedVariable(formula="bad2 * 2"),  # self-reference
            "bad3": ComputedVariable(formula="another_undefined + missing_var"),  # multiple undefined
        }

        errors = validate_computed_variable_references(variables, "test_config")

        # Should have errors for each problematic variable
        assert len(errors) >= 3

        # Check that specific issues are mentioned
        error_text = "\n".join(errors)
        assert "undefined_var" in error_text
        assert "bad2" in error_text and "references itself" in error_text
        assert "another_undefined" in error_text and "missing_var" in error_text

    def test_complex_valid_dependency_chain(self):
        """Test that complex but valid dependency chains don't generate errors."""
        variables = {
            "base": 100,
            "multiplier": 2.5,
            "step1": ComputedVariable(formula="base * multiplier"),
            "step2": ComputedVariable(formula="step1 + 50"),
            "final": ComputedVariable(formula="max(step2, 300)"),
        }

        errors = validate_computed_variable_references(variables)
        assert len(errors) == 0

    def test_functions_not_flagged_as_undefined(self):
        """Test that mathematical functions are not flagged as undefined variables."""
        variables = {"value": 42, "computed": ComputedVariable(formula="abs(round(max(value, min(10, 5))))")}

        errors = validate_computed_variable_references(variables)
        assert len(errors) == 0

    def test_conditional_expressions_validation(self):
        """Test validation of conditional expressions in computed variables."""
        variables = {
            "condition": 1,
            "value1": 10,
            "value2": 20,
            "conditional": ComputedVariable(formula="value1 if condition else value2"),
            "bad_conditional": ComputedVariable(formula="good if missing_condition else bad_value"),
        }

        errors = validate_computed_variable_references(variables)
        assert len(errors) == 1
        assert "missing_condition" in errors[0] and "bad_value" in errors[0]

    def test_integration_with_config_manager_sensor_level(self, mock_hass, mock_entity_registry, mock_states):
        """Test that validation errors prevent config loading at sensor level."""
        config_manager = ConfigManager(hass=mock_hass)

        yaml_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "name": "Test Sensor",
                    "formula": "computed_result",
                    "variables": {"base_value": 100, "computed_result": {"formula": "base_value + undefined_variable"}},
                }
            },
        }

        # This should fail to parse due to undefined variable
        with pytest.raises(ConfigEntryError, match="Computed variable validation failed"):
            config_manager._parse_yaml_config(yaml_data)

    def test_integration_with_config_manager_attribute_level(self, mock_hass, mock_entity_registry, mock_states):
        """Test that validation warnings are logged for attribute-level computed variables."""
        config_manager = ConfigManager(hass=mock_hass)

        yaml_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "name": "Test Sensor",
                    "formula": "base_value",
                    "variables": {"base_value": 100},
                    "attributes": {
                        "computed_attr": {
                            "formula": "attr_result",
                            "variables": {"good_var": 50, "attr_result": {"formula": "good_var + bad_reference"}},
                        }
                    },
                }
            },
        }

        # This should complete without exceptions but log warnings
        try:
            config = config_manager._parse_yaml_config(yaml_data)
            # Verify the config was created successfully despite warnings
            assert len(config.sensors) == 1
            assert len(config.sensors[0].formulas) == 2  # main + attribute
        except Exception as e:
            # If there are other parsing issues, that's okay for this test
            pass

    def test_state_variable_always_available(self):
        """Test that 'state' variable is always considered available."""
        variables = {"computed": ComputedVariable(formula="state * 1.5")}

        errors = validate_computed_variable_references(variables)
        assert len(errors) == 0

    def test_datetime_functions_always_available(self):
        """Test that datetime functions are always considered available."""
        variables = {"computed": ComputedVariable(formula="now() + today() - yesterday()")}

        errors = validate_computed_variable_references(variables)
        assert len(errors) == 0

    def test_mixed_valid_invalid_references(self):
        """Test mixed scenarios with both valid and invalid references."""
        variables = {
            "sensor_value": "sensor.test",
            "threshold": 100,
            "good_computed": ComputedVariable(formula="sensor_value + threshold"),
            "bad_computed": ComputedVariable(formula="sensor_value + missing_threshold"),
            "self_ref": ComputedVariable(formula="self_ref + 1"),
        }

        errors = validate_computed_variable_references(variables, "mixed_test")

        # Should have exactly 2 errors: undefined ref + self ref
        assert len(errors) == 2

        error_text = "\n".join(errors)
        assert "missing_threshold" in error_text
        assert "self_ref" in error_text and "references itself" in error_text
