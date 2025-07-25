"""Tests for boolean_handler module."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.config_manager import ConfigManager, FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.evaluator_handlers.boolean_handler import BooleanHandler


class TestBooleanHandler:
    """Test BooleanHandler functionality."""

    def test_boolean_handler_initialization(self):
        """Test BooleanHandler initialization."""
        handler = BooleanHandler()
        assert handler is not None

    def test_can_handle_comparison_operators(self):
        """Test that BooleanHandler can handle comparison operators."""
        handler = BooleanHandler()

        # Test comparison operators
        assert handler.can_handle("A > B") is True
        assert handler.can_handle("A < B") is True
        assert handler.can_handle("A >= B") is True
        assert handler.can_handle("A <= B") is True
        assert handler.can_handle("A == B") is True
        assert handler.can_handle("A != B") is True

    def test_can_handle_logical_operators(self):
        """Test that BooleanHandler can handle logical operators."""
        handler = BooleanHandler()

        # Test logical operators
        assert handler.can_handle("A and B") is True
        assert handler.can_handle("A or B") is True
        assert handler.can_handle("not A") is True
        assert handler.can_handle("A AND B") is True  # Case insensitive
        assert handler.can_handle("A OR B") is True  # Case insensitive

    def test_can_handle_boolean_literals(self):
        """Test that BooleanHandler can handle boolean literals."""
        handler = BooleanHandler()

        # Test boolean literals
        assert handler.can_handle("True") is True
        assert handler.can_handle("False") is True
        assert handler.can_handle("A == True") is True
        assert handler.can_handle("B == False") is True

    def test_can_handle_boolean_functions(self):
        """Test that BooleanHandler can handle boolean functions."""
        handler = BooleanHandler()

        # Test boolean functions
        assert handler.can_handle("is_on()") is True
        assert handler.can_handle("is_off()") is True
        assert handler.can_handle("is_home()") is True
        assert handler.can_handle("is_away()") is True
        assert handler.can_handle("IS_ON()") is True  # Case insensitive

    def test_can_handle_non_boolean_formulas(self):
        """Test that BooleanHandler correctly rejects non-boolean formulas."""
        handler = BooleanHandler()

        # Test non-boolean formulas
        assert handler.can_handle("A + B") is False
        assert handler.can_handle("A * B") is False
        assert handler.can_handle("sin(A)") is False
        assert handler.can_handle("100") is False

    def test_evaluate_simple_comparison(self):
        """Test evaluating simple comparison expressions."""
        handler = BooleanHandler()

        # Test simple comparisons
        context = {"A": 10, "B": 5}
        assert handler.evaluate("A > B", context) is True
        assert handler.evaluate("A < B", context) is False
        assert handler.evaluate("A == 10", context) is True
        assert handler.evaluate("A != B", context) is True

    def test_evaluate_logical_operations(self):
        """Test evaluating logical operations."""
        handler = BooleanHandler()

        # Test logical operations
        context = {"A": True, "B": False, "C": 10}
        assert handler.evaluate("A and True", context) is True
        assert handler.evaluate("A and B", context) is False
        assert handler.evaluate("A or B", context) is True
        assert handler.evaluate("not B", context) is True
        assert handler.evaluate("C > 5 and C < 15", context) is True

    def test_evaluate_boolean_literals(self):
        """Test evaluating boolean literals."""
        handler = BooleanHandler()

        # Test boolean literals
        context = {}
        assert handler.evaluate("True", context) is True
        assert handler.evaluate("False", context) is False
        assert handler.evaluate("True == True", context) is True
        assert handler.evaluate("False == False", context) is True

    def test_evaluate_complex_boolean_expressions(self):
        """Test evaluating complex boolean expressions."""
        handler = BooleanHandler()

        # Test complex expressions
        context = {"A": 10, "B": 5, "C": 15, "D": 0}
        assert handler.evaluate("A > B and C > A", context) is True
        assert handler.evaluate("A < B or C > A", context) is True
        assert handler.evaluate("not (A < B)", context) is True
        assert handler.evaluate("(A > B) and (C > A) and (D == 0)", context) is True

    def test_evaluate_with_numeric_conversion(self):
        """Test that numeric values are properly converted to boolean."""
        handler = BooleanHandler()

        # Test numeric to boolean conversion
        context = {"A": 10, "B": 0, "C": -5}
        assert handler.evaluate("A", context) is True  # Non-zero is True
        assert handler.evaluate("B", context) is False  # Zero is False
        assert handler.evaluate("C", context) is True  # Negative non-zero is True

    def test_evaluate_error_handling(self):
        """Test error handling in boolean evaluation."""
        handler = BooleanHandler()

        # Test with invalid expressions
        context = {"A": 10}

        with pytest.raises(Exception):
            handler.evaluate("invalid syntax", context)

        with pytest.raises(Exception):
            handler.evaluate("A / 0", context)  # Division by zero

    def test_boolean_handler_direct_evaluation(self, mock_hass, mock_entity_registry, mock_states):
        """Test BooleanHandler directly with entity context."""
        handler = BooleanHandler()

        # Set up entity context
        context = {
            "binary_sensor_motion": "motion",
            "binary_sensor_door": "open",
            "switch_light": "on",
            "binary_sensor_presence": "home",
        }

        # Test boolean expressions with entity values
        assert handler.evaluate("binary_sensor_motion == 'motion'", context) is True
        assert handler.evaluate("binary_sensor_door == 'open'", context) is True
        assert handler.evaluate("binary_sensor_motion == 'motion' and binary_sensor_door == 'open'", context) is True

    def test_boolean_handler_mixed_entity_states(self, mock_hass, mock_entity_registry, mock_states):
        """Test BooleanHandler with mixed entity states."""
        handler = BooleanHandler()

        # Set up mixed entity context
        context = {
            "binary_sensor_motion": "motion",  # true
            "binary_sensor_door": "closed",  # false
            "switch_light": "on",  # true
            "binary_sensor_presence": "away",  # false
        }

        # Test mixed boolean expressions
        assert handler.evaluate("binary_sensor_motion == 'motion'", context) is True
        assert handler.evaluate("binary_sensor_door == 'closed'", context) is True
        assert handler.evaluate("binary_sensor_motion == 'motion' and binary_sensor_door == 'closed'", context) is True
        assert handler.evaluate("binary_sensor_motion == 'motion' and binary_sensor_door == 'open'", context) is False

    def test_boolean_handler_numeric_comparison(self, mock_hass, mock_entity_registry, mock_states):
        """Test BooleanHandler with numeric comparisons."""
        handler = BooleanHandler()

        # Set up numeric and boolean entity context
        context = {"sensor_temperature": 25.5, "binary_sensor_motion": "motion"}

        # Test numeric and boolean logic
        assert handler.evaluate("sensor_temperature > 20", context) is True
        assert handler.evaluate("binary_sensor_motion == 'motion'", context) is True
        assert handler.evaluate("sensor_temperature > 20 and binary_sensor_motion == 'motion'", context) is True

    def test_boolean_handler_unknown_states(self, mock_hass, mock_entity_registry, mock_states):
        """Test BooleanHandler with unknown states."""
        handler = BooleanHandler()

        # Set up unknown states context
        context = {"binary_sensor_unknown": "unknown", "binary_sensor_valid": "motion"}

        # Test unknown state handling
        assert handler.evaluate("binary_sensor_unknown == 'unknown'", context) is True
        assert handler.evaluate("binary_sensor_valid == 'motion'", context) is True
        assert handler.evaluate("binary_sensor_unknown == 'unknown' and binary_sensor_valid == 'motion'", context) is True

    async def test_boolean_handler_yaml_fixture_validation(self, mock_hass, mock_entity_registry, mock_states):
        """Test that the boolean_handler_test.yaml fixture loads correctly and uses proper Python operators."""
        from ha_synthetic_sensors.config_manager import ConfigManager

        # Load the YAML fixture
        config_manager = ConfigManager(mock_hass)
        fixture_path = Path(__file__).parent / "yaml_fixtures" / "boolean_handler_test.yaml"
        config = await config_manager.async_load_from_file(fixture_path)

        # Test that the YAML loaded successfully
        assert config is not None
        assert len(config.sensors) > 0

        # Find the boolean logic sensors and verify they use Python operators
        door_lock_and_sensor = next((s for s in config.sensors if s.unique_id == "door_lock_and"), None)
        assert door_lock_and_sensor is not None
        formula = door_lock_and_sensor.formulas[0].formula
        assert "and" in formula
        assert "&&" not in formula, "YAML fixture should not contain symbolic operators"

        presence_or_sensor = next((s for s in config.sensors if s.unique_id == "presence_or"), None)
        assert presence_or_sensor is not None
        formula = presence_or_sensor.formulas[0].formula
        assert "or" in formula
        assert "||" not in formula, "YAML fixture should not contain symbolic operators"

        security_check_sensor = next((s for s in config.sensors if s.unique_id == "security_check"), None)
        assert security_check_sensor is not None
        formula = security_check_sensor.formulas[0].formula
        assert "not" in formula
        assert "!" not in formula, "YAML fixture should not contain symbolic operators"

        print(f"✓ All boolean sensors use correct Python operators:")
        print(f"  door_lock_and: {door_lock_and_sensor.formulas[0].formula}")
        print(f"  presence_or: {presence_or_sensor.formulas[0].formula}")
        print(f"  security_check: {security_check_sensor.formulas[0].formula}")
