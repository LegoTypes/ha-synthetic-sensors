"""Unit tests for formula_helpers identify_variables_for_attribute_access function."""

import re
from unittest.mock import Mock

import pytest

from ha_synthetic_sensors.evaluator_phases.variable_resolution.formula_helpers import FormulaHelpers
from ha_synthetic_sensors.config_models import FormulaConfig


class TestIdentifyVariablesForAttributeAccess:
    """Test the identify_variables_for_attribute_access function."""

    def test_metadata_function_syntax_not_matched_by_attribute_pattern(self):
        """Test that metadata(state, 'last_changed') syntax is NOT matched by current attribute pattern."""

        # This is the formula from the failing test
        formula = "minutes_between(metadata(state, 'last_changed'), now()) < grace_minutes"

        # Create a mock formula config with the state variable
        formula_config = Mock(spec=FormulaConfig)
        formula_config.variables = {
            "state": "sensor.test_entity"  # This looks like an entity ID
        }

        # Test the current regex pattern directly
        from ha_synthetic_sensors.regex_helper import RegexHelper

        regex_helper = RegexHelper()
        attribute_pattern = regex_helper.create_attribute_access_pattern()

        # Show what the pattern actually is
        print(f"Attribute pattern: {attribute_pattern.pattern}")

        # Test if it matches the metadata function syntax
        matches = list(attribute_pattern.finditer(formula))
        print(f"Matches found: {matches}")

        # This should demonstrate the bug - no matches found
        assert len(matches) == 0, "Current pattern incorrectly matches metadata() syntax"

        # Test the actual function
        result = FormulaHelpers.identify_variables_for_attribute_access(formula, formula_config)

        # This demonstrates the bug - state should be identified but isn't
        assert len(result) == 0, "Function should identify 'state' but doesn't due to regex mismatch"

    def test_dot_syntax_is_matched_by_attribute_pattern(self):
        """Test that variable.attribute syntax IS matched by current attribute pattern."""

        # This formula uses dot syntax instead of metadata() function
        formula = "state.last_changed < grace_minutes"

        # Create a mock formula config with the state variable
        formula_config = Mock(spec=FormulaConfig)
        formula_config.variables = {
            "state": "sensor.test_entity"  # This looks like an entity ID
        }

        # Test the current regex pattern directly
        from ha_synthetic_sensors.regex_helper import RegexHelper

        regex_helper = RegexHelper()
        attribute_pattern = regex_helper.create_attribute_access_pattern()

        # Test if it matches the dot syntax
        matches = list(attribute_pattern.finditer(formula))
        print(f"Matches found for dot syntax: {matches}")

        # This should work with current pattern
        assert len(matches) == 1, "Current pattern should match dot syntax"
        assert matches[0].group(1) == "state"
        assert matches[0].group(2) == "last_changed"

        # Test the actual function
        result = FormulaHelpers.identify_variables_for_attribute_access(formula, formula_config)

        # This should work correctly
        assert "state" in result, "Function should identify 'state' with dot syntax"

    def test_correct_metadata_pattern_exists_in_regex_helper(self):
        """Test that the correct pattern for metadata() already exists in regex_helper."""

        # This is what we want to support
        formula = "minutes_between(metadata(state, 'last_changed'), now()) < grace_minutes"

        # Test the existing extract_variable_references_from_metadata function
        from ha_synthetic_sensors.regex_helper import extract_variable_references_from_metadata

        result = extract_variable_references_from_metadata(formula)
        print(f"Variables found in metadata calls: {result}")

        # This should work correctly with the existing function
        assert "state" in result, "extract_variable_references_from_metadata should find 'state'"

        print("✓ The correct regex pattern already exists!")
        print("✓ We should use extract_variable_references_from_metadata instead of attribute_access_pattern")

    def test_expected_behavior_for_metadata_function(self):
        """Test what the function SHOULD do for metadata() function syntax."""

        # This is what we want to support
        formula = "minutes_between(metadata(state, 'last_changed'), now()) < grace_minutes"

        # Create a mock formula config
        formula_config = Mock(spec=FormulaConfig)
        formula_config.variables = {
            "state": "sensor.test_entity"  # This looks like an entity ID
        }

        # TODO: The function should use extract_variable_references_from_metadata
        # instead of create_attribute_access_pattern for metadata function calls

        print("ISSUE IDENTIFIED:")
        print("- identify_variables_for_attribute_access uses create_attribute_access_pattern")
        print("- This pattern only matches variable.attribute syntax")
        print("- Should ALSO use extract_variable_references_from_metadata for metadata() calls")
        print(f"Formula: {formula}")
        print("Expected: 'state' should be identified as needing entity ID preservation")

    def test_proposed_fix_for_metadata_function_support(self):
        """Test the proposed fix: combine both dot notation and metadata() patterns."""

        formula = "minutes_between(metadata(state, 'last_changed'), now()) < grace_minutes"

        # Create a mock formula config
        formula_config = Mock(spec=FormulaConfig)
        formula_config.variables = {
            "state": "sensor.test_entity"  # This looks like an entity ID
        }

        # Simulate the proposed fix by combining both approaches
        variables_needing_entity_ids = set()

        # 1. Check dot notation (existing logic)
        from ha_synthetic_sensors.regex_helper import RegexHelper

        regex_helper = RegexHelper()
        attribute_pattern = regex_helper.create_attribute_access_pattern()

        for match in attribute_pattern.finditer(formula):
            var_name = match.group(1)
            if var_name in formula_config.variables:
                var_value = formula_config.variables[var_name]
                if isinstance(var_value, str) and "." in var_value:
                    variables_needing_entity_ids.add(var_name)

        # 2. Check metadata() calls (proposed addition)
        from ha_synthetic_sensors.regex_helper import extract_variable_references_from_metadata

        metadata_vars = extract_variable_references_from_metadata(formula)

        for var_name in metadata_vars:
            if var_name in formula_config.variables:
                var_value = formula_config.variables[var_name]
                if isinstance(var_value, str) and "." in var_value:
                    variables_needing_entity_ids.add(var_name)

        print(f"Variables needing entity IDs (with fix): {variables_needing_entity_ids}")

        # This should work with the proposed fix
        assert "state" in variables_needing_entity_ids, "Proposed fix should identify 'state'"

        print("✓ PROPOSED FIX WORKS!")
        print("✓ Function should use BOTH patterns to handle dot notation AND metadata() calls")

    def test_fixed_function_now_handles_metadata_calls(self):
        """Test that the fixed function now properly handles metadata() calls."""

        formula = "minutes_between(metadata(state, 'last_changed'), now()) < grace_minutes"

        # Create a mock formula config
        formula_config = Mock(spec=FormulaConfig)
        formula_config.variables = {
            "state": "sensor.test_entity"  # This looks like an entity ID
        }

        # Test the fixed function
        result = FormulaHelpers.identify_variables_for_attribute_access(formula, formula_config)

        print(f"Fixed function result: {result}")

        # This should now work correctly
        assert "state" in result, "Fixed function should identify 'state' in metadata() calls"

        print("✅ FIX SUCCESSFUL!")
        print("✅ Function now properly handles both dot notation AND metadata() function calls")

    def test_state_token_special_handling(self):
        """Test that 'state' token is handled specially even when not in formula_config.variables."""

        formula = "minutes_between(metadata(state, 'last_changed'), now()) < grace_minutes"

        # Create a mock formula config WITHOUT 'state' in variables (like in the debugger)
        formula_config = Mock(spec=FormulaConfig)
        formula_config.variables = {
            "grace_minutes": 15,
            "current_sensor_entity_id": "sensor.test_allow_unresolved_sensor",
            # NOTE: 'state' is NOT in variables - this matches the debugger scenario
        }

        # Test the fixed function
        result = FormulaHelpers.identify_variables_for_attribute_access(formula, formula_config)

        print(f"Result with 'state' not in variables: {result}")

        # This should work because 'state' is handled as a special token
        assert "state" in result, "Function should identify 'state' as special token even when not in variables"

        print("✅ SPECIAL TOKEN HANDLING WORKS!")
        print("✅ 'state' token is correctly identified even when not yet resolved")
