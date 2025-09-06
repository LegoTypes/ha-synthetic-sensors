"""Tests for specific regex patterns used in formula processing.

This module tests the specific regex patterns that were consolidated from
various parts of the codebase to ensure they work correctly and consistently.
"""

import pytest
from ha_synthetic_sensors.regex_helper import (
    regex_helper,
    extract_formula_variables_for_resolution,
    filter_variables_needing_resolution,
)


class TestFormulaVariableResolutionPatterns:
    """Test formula variable resolution pattern functionality."""

    def test_extract_formula_variables_basic(self):
        """Test basic variable extraction from formulas."""
        formula = "sensor_power + battery_level"
        variables = extract_formula_variables_for_resolution(formula)
        assert "sensor_power" in variables
        assert "battery_level" in variables

    def test_extract_formula_variables_with_entity_ids(self):
        """Test variable extraction with entity IDs (should extract parts)."""
        formula = "sensor.power + binary_sensor.door"
        variables = extract_formula_variables_for_resolution(formula)
        # Should extract both domain and entity parts
        assert "sensor" in variables
        assert "power" in variables
        assert "binary_sensor" in variables
        assert "door" in variables

    def test_extract_formula_variables_with_functions(self):
        """Test variable extraction with function calls."""
        formula = "max(sensor_power, battery_level) + min(voltage, current)"
        variables = extract_formula_variables_for_resolution(formula)
        assert "max" in variables
        assert "sensor_power" in variables
        assert "battery_level" in variables
        assert "min" in variables
        assert "voltage" in variables
        assert "current" in variables

    def test_extract_formula_variables_with_numbers(self):
        """Test that numbers are not extracted as variables."""
        formula = "sensor_power + 100 + 3.14"
        variables = extract_formula_variables_for_resolution(formula)
        assert "sensor_power" in variables
        assert "100" not in variables
        assert "3" not in variables  # From 3.14
        assert "14" not in variables  # From 3.14

    def test_extract_formula_variables_with_operators(self):
        """Test that operators don't interfere with variable extraction."""
        formula = "sensor_power + battery_level - 100 * 2 / voltage"
        variables = extract_formula_variables_for_resolution(formula)
        assert "sensor_power" in variables
        assert "battery_level" in variables
        assert "voltage" in variables
        # Operators should not be extracted
        assert "+" not in variables
        assert "-" not in variables
        assert "*" not in variables
        assert "/" not in variables

    def test_extract_formula_variables_with_underscores(self):
        """Test variable extraction with underscores."""
        formula = "_private_var + __dunder__ + normal_var_2"
        variables = extract_formula_variables_for_resolution(formula)
        assert "_private_var" in variables
        assert "__dunder__" in variables
        assert "normal_var_2" in variables

    def test_extract_formula_variables_with_string_literals(self):
        """Test that string literals don't interfere with variable extraction."""
        formula = 'sensor_power + "fake_variable" + battery_level'
        variables = extract_formula_variables_for_resolution(formula)
        assert "sensor_power" in variables
        assert "battery_level" in variables
        # String content should be extracted as individual tokens
        assert "fake_variable" in variables  # This is expected with current pattern

    def test_extract_formula_variables_complex_formula(self):
        """Test variable extraction from complex formula."""
        formula = "max(sensor.circuit_a_power, sensor.circuit_b_power) + metadata(panel_sensor, 'device_class')"
        variables = extract_formula_variables_for_resolution(formula)
        assert "max" in variables
        assert "sensor" in variables
        assert "circuit_a_power" in variables
        assert "circuit_b_power" in variables
        assert "metadata" in variables
        assert "panel_sensor" in variables
        assert "device_class" in variables


class TestVariableFilteringPatterns:
    """Test variable filtering functionality."""

    def test_filter_variables_default_functions(self):
        """Test filtering with default known functions."""
        variables = ["sensor_power", "max", "min", "battery_level", "sum", "int"]
        filtered = filter_variables_needing_resolution(variables)
        assert "sensor_power" in filtered
        assert "battery_level" in filtered
        # Known functions should be filtered out
        assert "max" not in filtered
        assert "min" not in filtered
        assert "sum" not in filtered
        assert "int" not in filtered

    def test_filter_variables_custom_functions(self):
        """Test filtering with custom known functions."""
        variables = ["sensor_power", "custom_func", "battery_level", "my_function"]
        custom_functions = {"custom_func", "my_function"}
        filtered = filter_variables_needing_resolution(variables, custom_functions)
        assert "sensor_power" in filtered
        assert "battery_level" in filtered
        # Custom functions should be filtered out
        assert "custom_func" not in filtered
        assert "my_function" not in filtered

    def test_filter_variables_empty_list(self):
        """Test filtering with empty variable list."""
        variables = []
        filtered = filter_variables_needing_resolution(variables)
        assert filtered == []

    def test_filter_variables_no_functions_to_filter(self):
        """Test filtering when no variables match known functions."""
        variables = ["sensor_power", "battery_level", "voltage"]
        filtered = filter_variables_needing_resolution(variables)
        assert len(filtered) == 3
        assert "sensor_power" in filtered
        assert "battery_level" in filtered
        assert "voltage" in filtered

    def test_filter_variables_all_functions(self):
        """Test filtering when all variables are known functions."""
        variables = ["max", "min", "sum", "int", "float"]
        filtered = filter_variables_needing_resolution(variables)
        assert filtered == []

    def test_filter_variables_mixed_case_sensitivity(self):
        """Test that filtering is case sensitive."""
        variables = ["MAX", "Min", "sensor_power"]
        filtered = filter_variables_needing_resolution(variables)
        # Case sensitive - should not filter uppercase versions
        assert "MAX" in filtered
        assert "Min" in filtered
        assert "sensor_power" in filtered


class TestFormulaVariableIntegration:
    """Test integration of variable extraction and filtering."""

    def test_full_workflow_simple_formula(self):
        """Test complete workflow for simple formula."""
        formula = "sensor_power + max(battery_level, 100)"
        variables = extract_formula_variables_for_resolution(formula)
        filtered = filter_variables_needing_resolution(variables)

        # Should extract variables needing resolution
        assert "sensor_power" in filtered
        assert "battery_level" in filtered
        # Should filter out known functions
        assert "max" not in filtered

    def test_full_workflow_complex_formula(self):
        """Test complete workflow for complex formula."""
        formula = "sum(sensor.circuit_a_power, sensor.circuit_b_power) + min(voltage, current) * 2"
        variables = extract_formula_variables_for_resolution(formula)
        filtered = filter_variables_needing_resolution(variables)

        # Should extract entity parts and variables
        assert "sensor" in filtered
        assert "circuit_a_power" in filtered
        assert "circuit_b_power" in filtered
        assert "voltage" in filtered
        assert "current" in filtered
        # Should filter out known functions
        assert "sum" not in filtered
        assert "min" not in filtered

    def test_full_workflow_no_variables_needed(self):
        """Test workflow when no variables need resolution."""
        formula = "max(100, 200) + min(50, 75)"
        variables = extract_formula_variables_for_resolution(formula)
        filtered = filter_variables_needing_resolution(variables)

        # Should filter out all function names
        assert "max" not in filtered
        assert "min" not in filtered
        # Numbers should not be extracted as variables
        assert len(filtered) == 0

    def test_full_workflow_only_literals(self):
        """Test workflow with only literals and operators."""
        formula = "100 + 200 - 50 * 2"
        variables = extract_formula_variables_for_resolution(formula)
        filtered = filter_variables_needing_resolution(variables)

        # Should extract no variables
        assert len(variables) == 0
        assert len(filtered) == 0


class TestRegexHelperDirectAccess:
    """Test direct access to RegexHelper methods."""

    def test_regex_helper_instance_methods(self):
        """Test that RegexHelper instance methods work correctly."""
        helper = regex_helper

        formula = "sensor_power + max(battery_level, 100)"
        variables = helper.extract_formula_variables_for_resolution(formula)
        filtered = helper.filter_variables_needing_resolution(variables)

        assert "sensor_power" in filtered
        assert "battery_level" in filtered
        assert "max" not in filtered

    def test_pattern_caching_for_new_methods(self):
        """Test that new methods use pattern caching."""
        helper = regex_helper

        # Call method multiple times
        formula = "test_variable + another_var"
        result1 = helper.extract_formula_variables_for_resolution(formula)
        result2 = helper.extract_formula_variables_for_resolution(formula)

        # Results should be identical
        assert result1 == result2

        # Pattern should be cached
        assert len(helper._patterns) > 0
        assert any("formula_variables_resolution" in str(key) for key in helper._patterns.keys())


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_formula(self):
        """Test handling of empty formula."""
        formula = ""
        variables = extract_formula_variables_for_resolution(formula)
        filtered = filter_variables_needing_resolution(variables)

        assert variables == []
        assert filtered == []

    def test_whitespace_only_formula(self):
        """Test handling of whitespace-only formula."""
        formula = "   \t\n  "
        variables = extract_formula_variables_for_resolution(formula)
        filtered = filter_variables_needing_resolution(variables)

        assert variables == []
        assert filtered == []

    def test_formula_with_special_characters(self):
        """Test handling of formulas with special characters."""
        formula = "sensor_power + battery@level + voltage#current"
        variables = extract_formula_variables_for_resolution(formula)

        # Should extract valid identifier parts
        assert "sensor_power" in variables
        # Invalid identifiers should not be extracted
        # Note: The pattern should handle this correctly

    def test_formula_with_parentheses_and_brackets(self):
        """Test handling of formulas with various brackets."""
        formula = "max(sensor_power, battery_level) + states['sensor.voltage']"
        variables = extract_formula_variables_for_resolution(formula)
        filtered = filter_variables_needing_resolution(variables)

        assert "sensor_power" in filtered
        assert "battery_level" in filtered
        assert "states" in filtered
        assert "sensor" in filtered
        assert "voltage" in filtered
        assert "max" not in filtered
