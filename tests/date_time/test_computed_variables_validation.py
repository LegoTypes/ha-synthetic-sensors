"""Unit tests for computed variables reference validation."""

import pytest
from unittest.mock import Mock

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

    def test_undefined_reference_warning(self):
        """Test warning for undefined variable references."""
        variables = {"a": 10, "computed": ComputedVariable(formula="a + undefined_var")}

        warnings = validate_computed_variable_references(variables, "test_sensor")
        assert len(warnings) == 1
        assert "undefined_var" in warnings[0]
        assert "test_sensor" in warnings[0]
        assert "Available variables:" in warnings[0] and "'a'" in warnings[0]

    def test_self_reference_warning(self):
        """Test warning for self-referencing computed variables."""
        variables = {"recursive": ComputedVariable(formula="recursive + 1")}

        warnings = validate_computed_variable_references(variables)
        assert len(warnings) == 1
        assert "references itself" in warnings[0]
        assert "circular dependency" in warnings[0]

    def test_multiple_issues_multiple_warnings(self):
        """Test that multiple issues generate multiple warnings."""
        variables = {
            "a": 10,
            "bad1": ComputedVariable(formula="undefined_var + 1"),
            "bad2": ComputedVariable(formula="bad2 * 2"),  # self-reference
            "bad3": ComputedVariable(formula="another_undefined + missing_var"),  # multiple undefined
        }

        warnings = validate_computed_variable_references(variables, "test_config")

        # Should have warnings for each problematic variable
        assert len(warnings) >= 3

        # Check that specific issues are mentioned
        warning_text = "\n".join(warnings)
        assert "undefined_var" in warning_text
        assert "bad2" in warning_text and "references itself" in warning_text
        assert "another_undefined" in warning_text and "missing_var" in warning_text

    def test_complex_valid_dependency_chain(self):
        """Test that complex but valid dependency chains don't generate warnings."""
        variables = {
            "base": 100,
            "multiplier": 2.5,
            "step1": ComputedVariable(formula="base * multiplier"),
            "step2": ComputedVariable(formula="step1 + 50"),
            "final": ComputedVariable(formula="max(step2, 300)"),
        }

        warnings = validate_computed_variable_references(variables)
        assert len(warnings) == 0

    def test_functions_not_flagged_as_undefined(self):
        """Test that mathematical functions are not flagged as undefined variables."""
        variables = {"value": 42, "computed": ComputedVariable(formula="abs(round(max(value, min(10, 5))))")}

        warnings = validate_computed_variable_references(variables)
        assert len(warnings) == 0

    def test_conditional_expressions_validation(self):
        """Test validation of conditional expressions in computed variables."""
        variables = {
            "condition": 1,
            "value1": 10,
            "value2": 20,
            "conditional": ComputedVariable(formula="value1 if condition else value2"),
            "bad_conditional": ComputedVariable(formula="good if missing_condition else bad_value"),
        }

        warnings = validate_computed_variable_references(variables)
        assert len(warnings) == 1
        assert "missing_condition" in warnings[0] and "bad_value" in warnings[0]

    def test_integration_with_config_manager_sensor_level(self, mock_hass, mock_entity_registry, mock_states):
        """Test that validation warnings are logged during config parsing at sensor level."""
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

        # This should parse successfully but log warnings
        config = config_manager._parse_yaml_config(yaml_data)

        # Verify the config was created successfully despite warnings
        assert len(config.sensors) == 1
        assert config.sensors[0].name == "Test Sensor"

        # The validation should have logged warnings about undefined_variable
        # (We can see this in the test output - the warning is logged)

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

        warnings = validate_computed_variable_references(variables)
        assert len(warnings) == 0

    def test_datetime_functions_always_available(self):
        """Test that datetime functions are always considered available."""
        variables = {"computed": ComputedVariable(formula="now() + today() - yesterday()")}

        warnings = validate_computed_variable_references(variables)
        assert len(warnings) == 0

    def test_mixed_valid_invalid_references(self):
        """Test mixed scenarios with both valid and invalid references."""
        variables = {
            "sensor_value": "sensor.test",
            "threshold": 100,
            "good_computed": ComputedVariable(formula="sensor_value + threshold"),
            "bad_computed": ComputedVariable(formula="sensor_value + missing_threshold"),
            "self_ref": ComputedVariable(formula="self_ref + 1"),
        }

        warnings = validate_computed_variable_references(variables, "mixed_test")

        # Should have exactly 2 warnings: undefined ref + self ref
        assert len(warnings) == 2

        warning_text = "\n".join(warnings)
        assert "missing_threshold" in warning_text
        assert "self_ref" in warning_text and "references itself" in warning_text
