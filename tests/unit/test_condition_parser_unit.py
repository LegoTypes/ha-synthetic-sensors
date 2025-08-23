"""Unit tests for ConditionParser."""

from __future__ import annotations

import pytest

from ha_synthetic_sensors.condition_parser import ConditionParser, ParsedCondition, ParsedAttributeCondition
from ha_synthetic_sensors.exceptions import DataValidationError


class TestConditionParser:
    """Test ConditionParser functionality."""

    def test_parse_state_condition_basic_operators(self) -> None:
        """Test parsing of basic comparison operators."""
        # Test explicit operators
        condition = ConditionParser.parse_state_condition("== 50")
        assert condition["operator"] == "=="
        assert condition["value"] == "50"

        condition = ConditionParser.parse_state_condition("!= off")
        assert condition["operator"] == "!="
        assert condition["value"] == "off"

        condition = ConditionParser.parse_state_condition("< 100")
        assert condition["operator"] == "<"
        assert condition["value"] == "100"

        condition = ConditionParser.parse_state_condition("<= 75")
        assert condition["operator"] == "<="
        assert condition["value"] == "75"

        condition = ConditionParser.parse_state_condition("> 25")
        assert condition["operator"] == ">"
        assert condition["value"] == "25"

        condition = ConditionParser.parse_state_condition(">= 50")
        assert condition["operator"] == ">="
        assert condition["value"] == "50"

    def test_parse_state_condition_negation(self) -> None:
        """Test parsing of negation operator."""
        # Test simple negation
        condition = ConditionParser.parse_state_condition("!on")
        assert condition["operator"] == "!="
        assert condition["value"] == "on"

        condition = ConditionParser.parse_state_condition("!off")
        assert condition["operator"] == "!="
        assert condition["value"] == "off"

        condition = ConditionParser.parse_state_condition("!active")
        assert condition["operator"] == "!="
        assert condition["value"] == "active"

    def test_parse_state_condition_bare_values(self) -> None:
        """Test parsing of bare values (default to equality)."""
        # Test bare values default to equality
        condition = ConditionParser.parse_state_condition("on")
        assert condition["operator"] == "=="
        assert condition["value"] == "on"

        condition = ConditionParser.parse_state_condition("off")
        assert condition["operator"] == "=="
        assert condition["value"] == "off"

        condition = ConditionParser.parse_state_condition("active")
        assert condition["operator"] == "=="
        assert condition["value"] == "active"

    def test_parse_state_condition_whitespace_handling(self) -> None:
        """Test whitespace handling in condition parsing."""
        # Test various whitespace patterns
        condition = ConditionParser.parse_state_condition("  ==  50  ")
        assert condition["operator"] == "=="
        assert condition["value"] == "50"

        condition = ConditionParser.parse_state_condition("\t>=\t100\t")
        assert condition["operator"] == ">="
        assert condition["value"] == "100"

        condition = ConditionParser.parse_state_condition("  !  on  ")
        assert condition["operator"] == "!="
        assert condition["value"] == "on"

    def test_parse_state_condition_quoted_values(self) -> None:
        """Test parsing of quoted values."""
        # Test quoted values
        condition = ConditionParser.parse_state_condition('== "quoted value"')
        assert condition["operator"] == "=="
        assert condition["value"] == "quoted value"

        condition = ConditionParser.parse_state_condition("== 'single quoted'")
        assert condition["operator"] == "=="
        assert condition["value"] == "single quoted"

        condition = ConditionParser.parse_state_condition('!= "spaces in value"')
        assert condition["operator"] == "!="
        assert condition["value"] == "spaces in value"

    def test_parse_state_condition_invalid_cases(self) -> None:
        """Test parsing rejects invalid conditions."""
        # Test empty condition
        with pytest.raises(DataValidationError, match="State condition cannot be empty"):
            ConditionParser.parse_state_condition("")

        with pytest.raises(DataValidationError, match="State condition cannot be empty"):
            ConditionParser.parse_state_condition("   ")

        # Test operators without values
        with pytest.raises(DataValidationError, match="is just an operator without a value"):
            ConditionParser.parse_state_condition("==")

        with pytest.raises(DataValidationError, match="is just an operator without a value"):
            ConditionParser.parse_state_condition(">=")

        with pytest.raises(DataValidationError, match="is just an operator without a value"):
            ConditionParser.parse_state_condition("!=")

        # Test single equals (assignment, not comparison)
        with pytest.raises(DataValidationError, match="Use '==' for comparison, not '='"):
            ConditionParser.parse_state_condition("= 50")

        # Test non-comparison operators
        with pytest.raises(DataValidationError, match="Expected comparison operators"):
            ConditionParser.parse_state_condition("& 50")

        with pytest.raises(DataValidationError, match="Expected comparison operators"):
            ConditionParser.parse_state_condition("| 50")

        with pytest.raises(DataValidationError, match="Expected comparison operators"):
            ConditionParser.parse_state_condition("* 50")

        with pytest.raises(DataValidationError, match="Expected comparison operators"):
            ConditionParser.parse_state_condition("/ 50")

        with pytest.raises(DataValidationError, match="Expected comparison operators"):
            ConditionParser.parse_state_condition("+ 50")

        # Test multiple comparison operators
        with pytest.raises(DataValidationError, match="Expected comparison operators"):
            ConditionParser.parse_state_condition(">> 50")

        with pytest.raises(DataValidationError, match="Expected comparison operators"):
            ConditionParser.parse_state_condition("<< 50")

        # Test negation without value (falls through to bare value case)
        condition = ConditionParser.parse_state_condition("!")
        assert condition["operator"] == "=="
        assert condition["value"] == "!"

        condition = ConditionParser.parse_state_condition("! ")
        assert condition["operator"] == "=="
        assert condition["value"] == "!"

    def test_parse_attribute_condition_valid_cases(self) -> None:
        """Test parsing of valid attribute conditions."""
        # Test basic attribute conditions
        condition = ConditionParser.parse_attribute_condition("friendly_name == 'Living Room'")
        assert condition is not None
        assert condition["attribute"] == "friendly_name"
        assert condition["operator"] == "=="
        assert condition["value"] == "Living Room"

        condition = ConditionParser.parse_attribute_condition("battery_level > 50")
        assert condition is not None
        assert condition["attribute"] == "battery_level"
        assert condition["operator"] == ">"
        assert condition["value"] == "50"

        condition = ConditionParser.parse_attribute_condition("temperature <= 25.5")
        assert condition is not None
        assert condition["attribute"] == "temperature"
        assert condition["operator"] == "<="
        assert condition["value"] == "25.5"

        condition = ConditionParser.parse_attribute_condition("status != 'offline'")
        assert condition is not None
        assert condition["attribute"] == "status"
        assert condition["operator"] != "offline"
        assert condition["value"] == "offline"

    def test_parse_attribute_condition_whitespace_handling(self) -> None:
        """Test whitespace handling in attribute condition parsing."""
        # Test various whitespace patterns
        condition = ConditionParser.parse_attribute_condition("  friendly_name  ==  'Living Room'  ")
        assert condition is not None
        assert condition["attribute"] == "friendly_name"
        assert condition["operator"] == "=="
        assert condition["value"] == "Living Room"

        condition = ConditionParser.parse_attribute_condition("\tbattery_level\t>\t50\t")
        assert condition is not None
        assert condition["attribute"] == "battery_level"
        assert condition["operator"] == ">"
        assert condition["value"] == "50"

    def test_parse_attribute_condition_quoted_values(self) -> None:
        """Test parsing of quoted values in attribute conditions."""
        # Test double quotes
        condition = ConditionParser.parse_attribute_condition('friendly_name == "Living Room"')
        assert condition is not None
        assert condition["value"] == "Living Room"

        # Test single quotes
        condition = ConditionParser.parse_attribute_condition("friendly_name == 'Living Room'")
        assert condition is not None
        assert condition["value"] == "Living Room"

        # Test spaces in quoted values
        condition = ConditionParser.parse_attribute_condition('status == "off line"')
        assert condition is not None
        assert condition["value"] == "off line"

    def test_parse_attribute_condition_invalid_cases(self) -> None:
        """Test parsing rejects invalid attribute conditions."""
        # Test empty condition
        assert ConditionParser.parse_attribute_condition("") is None
        assert ConditionParser.parse_attribute_condition("   ") is None

        # Test invalid patterns
        assert ConditionParser.parse_attribute_condition("invalid") is None
        assert ConditionParser.parse_attribute_condition("friendly_name") is None
        assert ConditionParser.parse_attribute_condition("friendly_name =") is None
        assert ConditionParser.parse_attribute_condition("friendly_name ==") is None

        # Test invalid attribute names
        assert ConditionParser.parse_attribute_condition("123name == 'value'") is None
        assert ConditionParser.parse_attribute_condition("name-with-dash == 'value'") is None
        assert ConditionParser.parse_attribute_condition("name with space == 'value'") is None

        # Test invalid operators
        assert ConditionParser.parse_attribute_condition("friendly_name = 'value'") is None
        assert ConditionParser.parse_attribute_condition("friendly_name & 'value'") is None
        assert ConditionParser.parse_attribute_condition("friendly_name | 'value'") is None

    def test_clean_value_string(self) -> None:
        """Test value string cleaning functionality."""
        # Test double quotes removal
        result = ConditionParser._clean_value_string('"quoted"')
        assert result == "quoted"

        # Test single quotes removal
        result = ConditionParser._clean_value_string("'quoted'")
        assert result == "quoted"

        # Test whitespace trimming
        result = ConditionParser._clean_value_string("  value  ")
        assert result == "value"

        # Test combined quote removal and trimming
        result = ConditionParser._clean_value_string('  "quoted"  ')
        assert result == "quoted"

        # Test no change for simple strings
        result = ConditionParser._clean_value_string("hello")
        assert result == "hello"

        # Test numeric strings
        result = ConditionParser._clean_value_string("42")
        assert result == "42"

        # Test boolean strings
        result = ConditionParser._clean_value_string("true")
        assert result == "true"

    def test_convert_value_for_comparison_numeric(self) -> None:
        """Test numeric value conversion."""
        # Test integer conversion
        result = ConditionParser._convert_value_for_comparison("42")
        assert result == 42
        assert isinstance(result, int)

        # Test float conversion
        result = ConditionParser._convert_value_for_comparison("3.14")
        assert result == 3.14
        assert isinstance(result, float)

        # Test integer with decimal
        result = ConditionParser._convert_value_for_comparison("42.0")
        assert result == 42.0
        assert isinstance(result, float)

    def test_convert_value_for_comparison_boolean(self) -> None:
        """Test boolean value conversion."""
        # Test true values
        result = ConditionParser._convert_value_for_comparison("true")
        assert result is True
        assert isinstance(result, bool)

        result = ConditionParser._convert_value_for_comparison("True")
        assert result is True
        assert isinstance(result, bool)

        # Test false values
        result = ConditionParser._convert_value_for_comparison("false")
        assert result is False
        assert isinstance(result, bool)

        result = ConditionParser._convert_value_for_comparison("False")
        assert result is False
        assert isinstance(result, bool)

    def test_convert_value_for_comparison_string(self) -> None:
        """Test string value conversion."""
        # Test string values that can't be converted
        result = ConditionParser._convert_value_for_comparison("hello")
        assert result == "hello"
        assert isinstance(result, str)

        result = ConditionParser._convert_value_for_comparison("on")
        assert result == "on"
        assert isinstance(result, str)

        result = ConditionParser._convert_value_for_comparison("off")
        assert result == "off"
        assert isinstance(result, str)

        # Test empty string
        result = ConditionParser._convert_value_for_comparison("")
        assert result == ""
        assert isinstance(result, str)

    def test_evaluate_condition_numeric(self) -> None:
        """Test numeric condition evaluation."""
        # Test equality
        condition = ParsedCondition(operator="==", value="42")
        assert ConditionParser.evaluate_condition(42, condition) is True
        assert ConditionParser.evaluate_condition(43, condition) is False

        # Test inequality
        condition = ParsedCondition(operator="!=", value="42")
        assert ConditionParser.evaluate_condition(42, condition) is False
        assert ConditionParser.evaluate_condition(43, condition) is True

        # Test less than
        condition = ParsedCondition(operator="<", value="50")
        assert ConditionParser.evaluate_condition(40, condition) is True
        assert ConditionParser.evaluate_condition(50, condition) is False
        assert ConditionParser.evaluate_condition(60, condition) is False

        # Test less than or equal
        condition = ParsedCondition(operator="<=", value="50")
        assert ConditionParser.evaluate_condition(40, condition) is True
        assert ConditionParser.evaluate_condition(50, condition) is True
        assert ConditionParser.evaluate_condition(60, condition) is False

        # Test greater than
        condition = ParsedCondition(operator=">", value="50")
        assert ConditionParser.evaluate_condition(40, condition) is False
        assert ConditionParser.evaluate_condition(50, condition) is False
        assert ConditionParser.evaluate_condition(60, condition) is True

        # Test greater than or equal
        condition = ParsedCondition(operator=">=", value="50")
        assert ConditionParser.evaluate_condition(40, condition) is False
        assert ConditionParser.evaluate_condition(50, condition) is True
        assert ConditionParser.evaluate_condition(60, condition) is True

    def test_evaluate_condition_boolean(self) -> None:
        """Test boolean condition evaluation."""
        # Test boolean equality
        condition = ParsedCondition(operator="==", value="true")
        assert ConditionParser.evaluate_condition(True, condition) is True
        assert ConditionParser.evaluate_condition(False, condition) is False

        condition = ParsedCondition(operator="==", value="false")
        assert ConditionParser.evaluate_condition(True, condition) is False
        assert ConditionParser.evaluate_condition(False, condition) is True

        # Test boolean inequality
        condition = ParsedCondition(operator="!=", value="true")
        assert ConditionParser.evaluate_condition(True, condition) is False
        assert ConditionParser.evaluate_condition(False, condition) is True

    def test_evaluate_condition_string(self) -> None:
        """Test string condition evaluation."""
        # Test string equality
        condition = ParsedCondition(operator="==", value="on")
        assert ConditionParser.evaluate_condition("on", condition) is True
        assert ConditionParser.evaluate_condition("off", condition) is False

        # Test string inequality
        condition = ParsedCondition(operator="!=", value="on")
        assert ConditionParser.evaluate_condition("on", condition) is False
        assert ConditionParser.evaluate_condition("off", condition) is True

        # Test string comparison
        condition = ParsedCondition(operator="<", value="def")
        assert ConditionParser.evaluate_condition("abc", condition) is True
        assert ConditionParser.evaluate_condition("def", condition) is False
        assert ConditionParser.evaluate_condition("ghi", condition) is False

    def test_evaluate_condition_type_conversion(self) -> None:
        """Test type conversion during condition evaluation."""
        # Test string to numeric conversion
        condition = ParsedCondition(operator="==", value="42")
        assert ConditionParser.evaluate_condition("42", condition) is True
        assert ConditionParser.evaluate_condition(42, condition) is True

        # Test string to boolean conversion
        condition = ParsedCondition(operator="==", value="true")
        assert ConditionParser.evaluate_condition("true", condition) is True
        assert ConditionParser.evaluate_condition(True, condition) is True

        # Test numeric to string conversion
        condition = ParsedCondition(operator="==", value="42")
        assert ConditionParser.evaluate_condition(42, condition) is True
        assert ConditionParser.evaluate_condition("42", condition) is True

    def test_evaluate_condition_invalid_operator(self) -> None:
        """Test evaluation with invalid operator."""
        condition = ParsedCondition(operator="invalid", value="42")
        assert ConditionParser.evaluate_condition(42, condition) is False

    def test_evaluate_condition_type_error_handling(self) -> None:
        """Test handling of type errors during evaluation."""
        # Test incompatible types
        condition = ParsedCondition(operator=">", value="invalid")
        assert ConditionParser.evaluate_condition(42, condition) is False

        condition = ParsedCondition(operator=">", value="42")
        assert ConditionParser.evaluate_condition("invalid", condition) is False

    def test_compare_values_numeric(self) -> None:
        """Test numeric value comparison."""
        # Test basic numeric comparisons
        assert ConditionParser.compare_values(10, ">", 5) is True
        assert ConditionParser.compare_values(5, "<=", 10) is True
        assert ConditionParser.compare_values(5, "==", 5) is True
        assert ConditionParser.compare_values(5, "!=", 10) is True

        # Test string to numeric conversion
        assert ConditionParser.compare_values(10, ">", "5") is True
        assert ConditionParser.compare_values("5", "<=", 10) is True
        assert ConditionParser.compare_values("5", "==", 5) is True
        assert ConditionParser.compare_values("5", "!=", 10) is True

        # Test float comparisons
        assert ConditionParser.compare_values(3.14, ">", 3.0) is True
        assert ConditionParser.compare_values("3.14", ">=", 3.0) is True

    def test_compare_values_boolean(self) -> None:
        """Test boolean value comparison."""
        # Test boolean comparisons
        assert ConditionParser.compare_values(True, "==", True) is True
        assert ConditionParser.compare_values(False, "==", False) is True
        assert ConditionParser.compare_values(True, "!=", False) is True

        # Test string to boolean conversion
        assert ConditionParser.compare_values(True, "==", "true") is True
        assert ConditionParser.compare_values(False, "==", "false") is True
        assert ConditionParser.compare_values(True, "!=", "false") is True

        # Test numeric to boolean conversion
        assert ConditionParser.compare_values(True, "==", 1) is True
        assert ConditionParser.compare_values(False, "==", 0) is True
        assert ConditionParser.compare_values(True, ">", 0) is True

    def test_compare_values_string(self) -> None:
        """Test string value comparison."""
        # Test basic string comparisons
        assert ConditionParser.compare_values("hello", "==", "hello") is True
        assert ConditionParser.compare_values("hello", "!=", "world") is True
        assert ConditionParser.compare_values("abc", "<", "def") is True
        assert ConditionParser.compare_values("def", ">", "abc") is True

    def test_compare_values_edge_cases(self) -> None:
        """Test edge cases in value comparison."""
        # Test scientific notation
        assert ConditionParser.compare_values(1.23e-4, "==", "0.000123") is True

        # Test invalid conversions return False
        assert ConditionParser.compare_values("invalid", ">", 5) is False
        assert ConditionParser.compare_values(5, ">", "invalid") is False

        # Test invalid operators
        assert ConditionParser.compare_values(5, "invalid", 10) is False

        # Test type errors
        assert ConditionParser.compare_values("string", ">", 5) is False
        assert ConditionParser.compare_values(5, ">", "string") is False

    def test_compare_values_all_operators(self) -> None:
        """Test all comparison operators."""
        # Test equality
        assert ConditionParser.compare_values(5, "==", 5) is True
        assert ConditionParser.compare_values(5, "==", 6) is False

        # Test inequality
        assert ConditionParser.compare_values(5, "!=", 6) is True
        assert ConditionParser.compare_values(5, "!=", 5) is False

        # Test less than
        assert ConditionParser.compare_values(4, "<", 5) is True
        assert ConditionParser.compare_values(5, "<", 5) is False
        assert ConditionParser.compare_values(6, "<", 5) is False

        # Test less than or equal
        assert ConditionParser.compare_values(4, "<=", 5) is True
        assert ConditionParser.compare_values(5, "<=", 5) is True
        assert ConditionParser.compare_values(6, "<=", 5) is False

        # Test greater than
        assert ConditionParser.compare_values(6, ">", 5) is True
        assert ConditionParser.compare_values(5, ">", 5) is False
        assert ConditionParser.compare_values(4, ">", 5) is False

        # Test greater than or equal
        assert ConditionParser.compare_values(6, ">=", 5) is True
        assert ConditionParser.compare_values(5, ">=", 5) is True
        assert ConditionParser.compare_values(4, ">=", 5) is False
