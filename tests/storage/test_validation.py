"""Test validation helper functionality."""

import pytest

from ha_synthetic_sensors.exceptions import MissingDependencyError, NonNumericStateError
from ha_synthetic_sensors.validation_helper import (
    DataValidationError,
    convert_to_numeric,
    is_valid_numeric_state,
    validate_data_provider_result,
    validate_entity_state,
)


class TestValidateDataProviderResult:
    """Test validate_data_provider_result function."""

    def test_validate_data_provider_result_valid(self):
        """Test validation of valid data provider result."""
        result = {"value": 42.5, "exists": True}

        validated = validate_data_provider_result(result, "test.entity", "test provider")

        assert validated == {"value": 42.5, "exists": True}

    def test_validate_data_provider_result_none_callback_return(self):
        """Test validation when callback returns None."""
        with pytest.raises(DataValidationError) as exc_info:
            validate_data_provider_result(None, "test.entity", "test provider")

        assert "test provider callback returned None" in str(exc_info.value)
        assert "test.entity" in str(exc_info.value)
        assert "should return {{'value': <value>, 'exists': <bool>}}" in str(exc_info.value)

    def test_validate_data_provider_result_non_dict_return(self):
        """Test validation when callback returns non-dictionary."""
        with pytest.raises(DataValidationError) as exc_info:
            validate_data_provider_result("invalid", "test.entity", "test provider")

        assert "test provider callback returned str" in str(exc_info.value)
        assert "test.entity" in str(exc_info.value)
        assert "should return {{'value': <value>, 'exists': <bool>}}" in str(exc_info.value)

    def test_validate_data_provider_result_missing_value_key(self):
        """Test validation when result is missing 'value' key."""
        result = {"exists": True}

        with pytest.raises(DataValidationError) as exc_info:
            validate_data_provider_result(result, "test.entity", "test provider")

        assert "missing required keys ['value']" in str(exc_info.value)
        assert "test.entity" in str(exc_info.value)

    def test_validate_data_provider_result_missing_exists_key(self):
        """Test validation when result is missing 'exists' key."""
        result = {"value": 42}

        with pytest.raises(DataValidationError) as exc_info:
            validate_data_provider_result(result, "test.entity", "test provider")

        assert "missing required keys ['exists']" in str(exc_info.value)
        assert "test.entity" in str(exc_info.value)

    def test_validate_data_provider_result_missing_both_keys(self):
        """Test validation when result is missing both required keys."""
        result = {"other_key": "value"}

        with pytest.raises(DataValidationError) as exc_info:
            validate_data_provider_result(result, "test.entity", "test provider")

        assert "missing required keys ['value', 'exists']" in str(exc_info.value)
        assert "test.entity" in str(exc_info.value)

    def test_validate_data_provider_result_non_boolean_exists(self):
        """Test validation when 'exists' is not a boolean."""
        result = {"value": 42, "exists": "true"}

        with pytest.raises(DataValidationError) as exc_info:
            validate_data_provider_result(result, "test.entity", "test provider")

        assert "non-boolean 'exists' (str)" in str(exc_info.value)
        assert "test.entity" in str(exc_info.value)
        assert "'exists' should be True or False" in str(exc_info.value)

    def test_validate_data_provider_result_entity_not_exists(self):
        """Test validation when entity doesn't exist."""
        result = {"value": None, "exists": False}

        with pytest.raises(MissingDependencyError) as exc_info:
            validate_data_provider_result(result, "test.entity", "test provider")

        assert "Entity 'test.entity' not found by test provider" in str(exc_info.value)

    def test_validate_data_provider_result_entity_exists_none_value(self):
        """Test validation when entity exists but has None value."""
        result = {"value": None, "exists": True}

        with pytest.raises(MissingDependencyError) as exc_info:
            validate_data_provider_result(result, "test.entity", "test provider")

        assert "Entity 'test.entity' exists but has None value - entity is unavailable" in str(exc_info.value)

    def test_validate_data_provider_result_valid_zero_value(self):
        """Test validation with valid zero value."""
        result = {"value": 0, "exists": True}

        validated = validate_data_provider_result(result, "test.entity", "test provider")

        assert validated == {"value": 0, "exists": True}

    def test_validate_data_provider_result_valid_string_value(self):
        """Test validation with valid string value."""
        result = {"value": "on", "exists": True}

        validated = validate_data_provider_result(result, "test.entity", "test provider")

        assert validated == {"value": "on", "exists": True}

    def test_validate_data_provider_result_valid_negative_value(self):
        """Test validation with valid negative value."""
        result = {"value": -42.5, "exists": True}

        validated = validate_data_provider_result(result, "test.entity", "test provider")

        assert validated == {"value": -42.5, "exists": True}

    def test_validate_data_provider_result_default_context(self):
        """Test validation with default context parameter."""
        result = {"value": None, "exists": False}

        with pytest.raises(MissingDependencyError) as exc_info:
            validate_data_provider_result(result, "test.entity")

        assert "Entity 'test.entity' not found by data provider" in str(exc_info.value)


class TestValidateEntityState:
    """Test validate_entity_state function."""

    def test_validate_entity_state_valid_numeric(self):
        """Test validation of valid numeric state."""
        result = validate_entity_state(42.5, "test.entity")
        assert result == 42.5

    def test_validate_entity_state_valid_string(self):
        """Test validation of valid string state."""
        result = validate_entity_state("on", "test.entity")
        assert result == "on"

    def test_validate_entity_state_valid_zero(self):
        """Test validation of valid zero state."""
        result = validate_entity_state(0, "test.entity")
        assert result == 0

    def test_validate_entity_state_valid_negative(self):
        """Test validation of valid negative state."""
        result = validate_entity_state(-42.5, "test.entity")
        assert result == -42.5

    def test_validate_entity_state_none_state(self):
        """Test validation when state is None."""
        with pytest.raises(MissingDependencyError) as exc_info:
            validate_entity_state(None, "test.entity")

        assert "Entity 'test.entity' has None state - entity is unavailable" in str(exc_info.value)

    def test_validate_entity_state_custom_context(self):
        """Test validation with custom context."""
        with pytest.raises(MissingDependencyError) as exc_info:
            validate_entity_state(None, "test.entity", "custom context")

        assert "Entity 'test.entity' has None state - entity is unavailable" in str(exc_info.value)

    def test_validate_entity_state_valid_boolean(self):
        """Test validation of valid boolean state."""
        result = validate_entity_state(True, "test.entity")
        assert result is True

        result = validate_entity_state(False, "test.entity")
        assert result is False


class TestIsValidNumericState:
    """Test is_valid_numeric_state function."""

    def test_is_valid_numeric_state_integer(self):
        """Test numeric validation with integer."""
        assert is_valid_numeric_state(42) is True

    def test_is_valid_numeric_state_float(self):
        """Test numeric validation with float."""
        assert is_valid_numeric_state(42.5) is True

    def test_is_valid_numeric_state_zero(self):
        """Test numeric validation with zero."""
        assert is_valid_numeric_state(0) is True
        assert is_valid_numeric_state(0.0) is True

    def test_is_valid_numeric_state_negative(self):
        """Test numeric validation with negative numbers."""
        assert is_valid_numeric_state(-42) is True
        assert is_valid_numeric_state(-42.5) is True

    def test_is_valid_numeric_state_string_number(self):
        """Test numeric validation with string numbers."""
        assert is_valid_numeric_state("42") is True
        assert is_valid_numeric_state("42.5") is True
        assert is_valid_numeric_state("-42.5") is True
        assert is_valid_numeric_state("0") is True

    def test_is_valid_numeric_state_scientific_notation(self):
        """Test numeric validation with scientific notation."""
        assert is_valid_numeric_state("1.23e-4") is True
        assert is_valid_numeric_state("2.5e6") is True

    def test_is_valid_numeric_state_none(self):
        """Test numeric validation with None."""
        assert is_valid_numeric_state(None) is False

    def test_is_valid_numeric_state_non_numeric_string(self):
        """Test numeric validation with non-numeric strings."""
        assert is_valid_numeric_state("on") is False
        assert is_valid_numeric_state("off") is False
        assert is_valid_numeric_state("unknown") is False
        assert is_valid_numeric_state("unavailable") is False
        assert is_valid_numeric_state("text") is False

    def test_is_valid_numeric_state_empty_string(self):
        """Test numeric validation with empty string."""
        assert is_valid_numeric_state("") is False

    def test_is_valid_numeric_state_boolean(self):
        """Test numeric validation with boolean."""
        assert is_valid_numeric_state(True) is True  # bool is subclass of int
        assert is_valid_numeric_state(False) is True

    def test_is_valid_numeric_state_list(self):
        """Test numeric validation with list."""
        assert is_valid_numeric_state([1, 2, 3]) is False

    def test_is_valid_numeric_state_dict(self):
        """Test numeric validation with dictionary."""
        assert is_valid_numeric_state({"value": 42}) is False


class TestConvertToNumeric:
    """Test convert_to_numeric function."""

    def test_convert_to_numeric_integer(self):
        """Test numeric conversion with integer."""
        result = convert_to_numeric(42, "test.entity")
        assert result == 42.0
        assert isinstance(result, float)

    def test_convert_to_numeric_float(self):
        """Test numeric conversion with float."""
        result = convert_to_numeric(42.5, "test.entity")
        assert result == 42.5

    def test_convert_to_numeric_zero(self):
        """Test numeric conversion with zero."""
        result = convert_to_numeric(0, "test.entity")
        assert result == 0.0

    def test_convert_to_numeric_negative(self):
        """Test numeric conversion with negative numbers."""
        result = convert_to_numeric(-42.5, "test.entity")
        assert result == -42.5

    def test_convert_to_numeric_string_number(self):
        """Test numeric conversion with string numbers."""
        result = convert_to_numeric("42", "test.entity")
        assert result == 42.0

        result = convert_to_numeric("42.5", "test.entity")
        assert result == 42.5

        result = convert_to_numeric("-42.5", "test.entity")
        assert result == -42.5

    def test_convert_to_numeric_scientific_notation(self):
        """Test numeric conversion with scientific notation."""
        result = convert_to_numeric("1.23e-4", "test.entity")
        assert result == 1.23e-4

        result = convert_to_numeric("2.5e6", "test.entity")
        assert result == 2.5e6

    def test_convert_to_numeric_boolean(self):
        """Test numeric conversion with boolean."""
        result = convert_to_numeric(True, "test.entity")
        assert result == 1.0

        result = convert_to_numeric(False, "test.entity")
        assert result == 0.0

    def test_convert_to_numeric_none(self):
        """Test numeric conversion with None."""
        with pytest.raises(NonNumericStateError) as exc_info:
            convert_to_numeric(None, "test.entity")

        assert "Entity 'test.entity' has non-numeric state 'None'" in str(exc_info.value)

    def test_convert_to_numeric_non_numeric_string(self):
        """Test numeric conversion with non-numeric string."""
        with pytest.raises(NonNumericStateError) as exc_info:
            convert_to_numeric("on", "test.entity")

        assert "Entity 'test.entity' has non-numeric state 'on'" in str(exc_info.value)

    def test_convert_to_numeric_empty_string(self):
        """Test numeric conversion with empty string."""
        with pytest.raises(NonNumericStateError) as exc_info:
            convert_to_numeric("", "test.entity")

        assert "Entity 'test.entity' has non-numeric state ''" in str(exc_info.value)

    def test_convert_to_numeric_list(self):
        """Test numeric conversion with list."""
        with pytest.raises(NonNumericStateError) as exc_info:
            convert_to_numeric([1, 2, 3], "test.entity")

        assert "Entity 'test.entity' has non-numeric state '[1, 2, 3]'" in str(exc_info.value)

    def test_convert_to_numeric_dict(self):
        """Test numeric conversion with dictionary."""
        with pytest.raises(NonNumericStateError) as exc_info:
            convert_to_numeric({"value": 42}, "test.entity")

        assert "Entity 'test.entity' has non-numeric state '{'value': 42}'" in str(exc_info.value)

    def test_convert_to_numeric_whitespace_string(self):
        """Test numeric conversion with whitespace strings."""
        result = convert_to_numeric("  42  ", "test.entity")
        assert result == 42.0

        result = convert_to_numeric("\t42.5\n", "test.entity")
        assert result == 42.5

    def test_convert_to_numeric_special_float_values(self):
        """Test numeric conversion with special float values."""
        # Test infinity
        result = convert_to_numeric("inf", "test.entity")
        assert result == float("inf")

        result = convert_to_numeric("-inf", "test.entity")
        assert result == float("-inf")

        # Test NaN - this should convert but result in NaN
        result = convert_to_numeric("nan", "test.entity")
        assert str(result) == "nan"  # NaN != NaN, so we check string representation


class TestDataValidationErrorClass:
    """Test DataValidationError exception class."""

    def test_data_validation_error_creation(self):
        """Test DataValidationError exception creation."""
        error = DataValidationError("Test error message")
        assert str(error) == "Test error message"
        assert isinstance(error, Exception)

    def test_data_validation_error_inheritance(self):
        """Test DataValidationError inheritance."""
        error = DataValidationError("Test error")
        assert isinstance(error, Exception)

        # Test that it can be caught as a general Exception
        try:
            raise DataValidationError("Test error")
        except Exception as e:
            assert isinstance(e, DataValidationError)
            assert str(e) == "Test error"


class TestValidationHelperIntegration:
    """Test integration scenarios combining multiple validation functions."""

    def test_data_provider_to_numeric_conversion_flow(self):
        """Test full flow from data provider validation to numeric conversion."""
        # Valid numeric data provider result
        provider_result = {"value": "42.5", "exists": True}

        validated = validate_data_provider_result(provider_result, "test.entity")
        assert validated["value"] == "42.5"

        numeric_value = convert_to_numeric(validated["value"], "test.entity")
        assert numeric_value == 42.5

    def test_data_provider_invalid_numeric_flow(self):
        """Test flow with invalid numeric value from data provider."""
        # Non-numeric data provider result
        provider_result = {"value": "on", "exists": True}

        validated = validate_data_provider_result(provider_result, "test.entity")
        assert validated["value"] == "on"

        # Should fail on numeric conversion
        with pytest.raises(NonNumericStateError):
            convert_to_numeric(validated["value"], "test.entity")

    def test_entity_state_validation_flow(self):
        """Test entity state validation and numeric conversion flow."""
        # Valid entity state
        state = validate_entity_state("123.45", "test.entity")
        assert state == "123.45"

        # Check if it's numeric before conversion
        assert is_valid_numeric_state(state) is True

        # Convert to numeric
        numeric_value = convert_to_numeric(state, "test.entity")
        assert numeric_value == 123.45

    def test_entity_state_none_flow(self):
        """Test entity state validation flow with None state."""
        # None state should fail validation
        with pytest.raises(MissingDependencyError):
            validate_entity_state(None, "test.entity")

    def test_numeric_validation_edge_cases(self):
        """Test numeric validation with various edge cases."""
        # Test values that should be valid
        valid_values = [
            0,
            0.0,
            -0,
            -0.0,
            42,
            -42,
            42.5,
            -42.5,
            "0",
            "42",
            "-42.5",
            "1.23e-4",
            True,
            False,
            float("inf"),
            float("-inf"),
        ]

        for value in valid_values:
            assert is_valid_numeric_state(value) is True, f"Value {value} should be valid numeric"
            # Should not raise exception
            convert_to_numeric(value, "test.entity")

        # Test values that should be invalid
        invalid_values = [None, "on", "off", "unknown", "unavailable", "", "text", [], {}, object()]

        for value in invalid_values:
            assert is_valid_numeric_state(value) is False, f"Value {value} should be invalid numeric"
            if value is not None:  # None has special handling in convert_to_numeric
                with pytest.raises(NonNumericStateError):
                    convert_to_numeric(value, "test.entity")
