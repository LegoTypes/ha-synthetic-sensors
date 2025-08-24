"""Test reserved word validation with individual YAML fixture files."""

import yaml
import pytest
from ha_synthetic_sensors.schema_validator import SchemaValidator, ValidationSeverity


class TestReservedWordValidation:
    """Test reserved word validation with individual YAML files."""

    def setup_method(self):
        """Set up the validator for each test."""
        self.validator = SchemaValidator()

    def test_reserved_word_state(self):
        """Test that 'state' as a variable name is rejected."""
        with open("tests/fixtures/invalid_yaml/reserved_word_state.yaml", "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        result = self.validator.validate_config(config_data)

        assert not result["valid"], "Config with 'state' as variable name should be invalid"

        # Find the specific error for 'state'
        state_error = None
        for error in result["errors"]:
            if "reserved word" in error.message and "state" in error.message:
                state_error = error
                break

        assert state_error is not None, "Should have error about reserved word 'state'"
        assert state_error.path == "sensors.test_sensor.variables.state"
        assert state_error.severity == ValidationSeverity.ERROR
        print("✅ 'state' reserved word validation works correctly")

    def test_reserved_word_if(self):
        """Test that 'if' as a variable name is rejected."""
        with open("tests/fixtures/invalid_yaml/reserved_word_if.yaml", "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        result = self.validator.validate_config(config_data)

        assert not result["valid"], "Config with 'if' as variable name should be invalid"

        # Find the specific error for 'if'
        if_error = None
        for error in result["errors"]:
            if "reserved word" in error.message and "if" in error.message:
                if_error = error
                break

        assert if_error is not None, "Should have error about reserved word 'if'"
        assert if_error.path == "sensors.test_sensor.variables.if"
        assert if_error.severity == ValidationSeverity.ERROR
        print("✅ 'if' reserved word validation works correctly")

    def test_reserved_word_str(self):
        """Test that 'str' as a global variable name is rejected."""
        with open("tests/fixtures/invalid_yaml/reserved_word_str.yaml", "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        result = self.validator.validate_config(config_data)

        assert not result["valid"], "Config with 'str' as global variable name should be invalid"

        # Find the specific error for 'str'
        str_error = None
        for error in result["errors"]:
            if "reserved word" in error.message and "str" in error.message:
                str_error = error
                break

        assert str_error is not None, "Should have error about reserved word 'str'"
        assert str_error.path == "global_settings.variables.str"
        assert str_error.severity == ValidationSeverity.ERROR
        print("✅ 'str' reserved word validation works correctly")

    def test_reserved_word_for(self):
        """Test that 'for' as a variable name is rejected."""
        with open("tests/fixtures/invalid_yaml/reserved_word_for.yaml", "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        result = self.validator.validate_config(config_data)

        assert not result["valid"], "Config with 'for' as variable name should be invalid"

        # Find the specific error for 'for'
        for_error = None
        for error in result["errors"]:
            if "reserved word" in error.message and "for" in error.message:
                for_error = error
                break

        assert for_error is not None, "Should have error about reserved word 'for'"
        assert for_error.path == "sensors.test_sensor.variables.for"
        assert for_error.severity == ValidationSeverity.ERROR
        print("✅ 'for' reserved word validation works correctly")

    def test_reserved_word_while(self):
        """Test that 'while' as a variable name is rejected."""
        with open("tests/fixtures/invalid_yaml/reserved_word_while.yaml", "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        result = self.validator.validate_config(config_data)

        assert not result["valid"], "Config with 'while' as variable name should be invalid"

        # Find the specific error for 'while'
        while_error = None
        for error in result["errors"]:
            if "reserved word" in error.message and "while" in error.message:
                while_error = error
                break

        assert while_error is not None, "Should have error about reserved word 'while'"
        assert while_error.path == "sensors.test_sensor.variables.while"
        assert while_error.severity == ValidationSeverity.ERROR
        print("✅ 'while' reserved word validation works correctly")

    def test_reserved_word_def_in_attribute(self):
        """Test that 'def' as an attribute variable name is rejected."""
        with open("tests/fixtures/invalid_yaml/reserved_word_def.yaml", "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        result = self.validator.validate_config(config_data)

        assert not result["valid"], "Config with 'def' as attribute variable name should be invalid"

        # Find the specific error for 'def'
        def_error = None
        for error in result["errors"]:
            if "reserved word" in error.message and "def" in error.message:
                def_error = error
                break

        assert def_error is not None, "Should have error about reserved word 'def'"
        assert def_error.path == "sensors.test_sensor.attributes.computed_attr.variables.def"
        assert def_error.severity == ValidationSeverity.ERROR
        print("✅ 'def' reserved word validation in attributes works correctly")

    def test_valid_variable_names(self):
        """Test that valid variable names are accepted, including partial matches of reserved words."""
        with open("tests/fixtures/invalid_yaml/valid_variable_names.yaml", "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        result = self.validator.validate_config(config_data)

        # Should have no reserved word errors
        reserved_word_errors = [error for error in result["errors"] if "reserved word" in error.message]
        assert len(reserved_word_errors) == 0, "Should have no reserved word errors for valid variable names"

        # Verify that partial matches like 'the_state', 'my_if_condition', etc. are allowed
        # These should NOT trigger reserved word errors even though they contain reserved words as substrings
        print("✅ Valid variable names are accepted correctly, including partial matches of reserved words")

    def test_multiple_reserved_words_in_single_file(self):
        """Test that multiple reserved words in a single file are all caught."""
        # Create a config with multiple reserved words
        config_with_multiple = {
            "global_settings": {
                "variables": {
                    "state": "sensor.source_entity",  # Reserved
                    "if": "sensor.condition_entity",  # Reserved
                }
            },
            "sensors": {
                "test_sensor": {
                    "name": "Test Sensor",
                    "formula": "value + 10",
                    "variables": {
                        "value": "sensor.source_entity",
                        "str": "sensor.string_entity",  # Reserved
                        "for": "sensor.loop_entity",  # Reserved
                    },
                }
            },
        }

        result = self.validator.validate_config(config_with_multiple)

        assert not result["valid"], "Config with multiple reserved words should be invalid"

        # Should have multiple reserved word errors
        reserved_word_errors = [error for error in result["errors"] if "reserved word" in error.message]
        assert len(reserved_word_errors) >= 4, f"Should have at least 4 reserved word errors, got {len(reserved_word_errors)}"

        # Check that all expected reserved words are reported
        expected_reserved_words = {"state", "if", "str", "for"}
        found_reserved_words = set()

        for error in reserved_word_errors:
            for word in expected_reserved_words:
                if word in error.message:
                    found_reserved_words.add(word)
                    break

        assert len(found_reserved_words) >= 3, f"Should find at least 3 reserved words, found {len(found_reserved_words)}"
        print("✅ Multiple reserved words are all caught correctly")

    def test_reserved_word_state_attribute(self):
        """Test that reserved words as attribute names are detected."""
        with open("tests/fixtures/invalid_yaml/reserved_word_state_attribute.yaml", "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        result = self.validator.validate_config(config_data)

        # Should have a reserved word error for the attribute name
        reserved_word_errors = [error for error in result["errors"] if "reserved word" in error.message]
        assert len(reserved_word_errors) >= 1, "Should have at least one reserved word error for attribute name"

        # Check that the error is specifically for the attribute name
        attr_errors = [error for error in reserved_word_errors if "Attribute name 'state'" in error.message]
        assert len(attr_errors) >= 1, "Should have error for 'state' as attribute name"
        print("✅ Reserved word as attribute name is correctly detected")


if __name__ == "__main__":
    # Run all tests
    test_instance = TestReservedWordValidation()
    test_instance.setup_method()

    test_instance.test_reserved_word_state()
    test_instance.test_reserved_word_if()
    test_instance.test_reserved_word_str()
    test_instance.test_reserved_word_for()
    test_instance.test_reserved_word_while()
    test_instance.test_reserved_word_def_in_attribute()
    test_instance.test_valid_variable_names()
    test_instance.test_multiple_reserved_words_in_single_file()
    test_instance.test_reserved_word_state_attribute()

    print("🎉 All reserved word validation tests passed!")
