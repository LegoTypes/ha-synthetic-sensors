"""Unit tests for boolean_handler module."""

import pytest

from ha_synthetic_sensors.evaluator_handlers.boolean_handler import BooleanHandler


class TestBooleanHandler:
    """Test BooleanHandler functionality."""

    def test_boolean_handler_initialization(self):
        """Test BooleanHandler initialization."""
        handler = BooleanHandler()
        assert isinstance(handler, BooleanHandler)

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

    def test_cannot_handle_non_boolean_expressions(self):
        """Test that BooleanHandler rejects non-boolean expressions."""
        handler = BooleanHandler()

        # Test non-boolean expressions
        assert handler.can_handle("A + B") is False
        assert handler.can_handle("A * B") is False
        assert handler.can_handle("A / B") is False
        assert handler.can_handle("A - B") is False

    def test_evaluate_simple_boolean_expressions(self):
        """Test evaluation of simple boolean expressions."""
        handler = BooleanHandler()

        # Test simple boolean expressions
        assert handler.evaluate("True") is True
        assert handler.evaluate("False") is False
        assert handler.evaluate("True and False") is False
        assert handler.evaluate("True or False") is True
        assert handler.evaluate("not True") is False
        assert handler.evaluate("not False") is True

    def test_evaluate_comparison_operators(self):
        """Test evaluation of comparison operators."""
        handler = BooleanHandler()

        # Test with context
        context = {"A": 10, "B": 5}

        assert handler.evaluate("A > B", context) is True
        assert handler.evaluate("A < B", context) is False
        assert handler.evaluate("A >= B", context) is True
        assert handler.evaluate("A <= B", context) is False
        assert handler.evaluate("A == B", context) is False
        assert handler.evaluate("A != B", context) is True

    def test_evaluate_complex_boolean_expressions(self):
        """Test evaluation of complex boolean expressions."""
        handler = BooleanHandler()

        context = {"A": 10, "B": 5, "C": 15}

        # Test complex expressions
        assert handler.evaluate("A > B and C > A", context) is True
        assert handler.evaluate("A > B or C < A", context) is True
        assert handler.evaluate("not (A < B)", context) is True
        assert handler.evaluate("(A > B) and (C > A)", context) is True

    def test_evaluate_with_entity_states(self):
        """Test evaluation with entity state-like values."""
        handler = BooleanHandler()

        context = {
            "binary_sensor_motion": "motion",
            "binary_sensor_door": "open",
            "switch_light": "on",
            "sensor_temperature": 25.5,
        }

        # Test entity state comparisons
        assert handler.evaluate("binary_sensor_motion == 'motion'", context) is True
        assert handler.evaluate("binary_sensor_door == 'open'", context) is True
        assert handler.evaluate("switch_light == 'on'", context) is True
        assert handler.evaluate("sensor_temperature > 20", context) is True

        # Test complex entity expressions
        assert handler.evaluate("binary_sensor_motion == 'motion' and binary_sensor_door == 'open'", context) is True
        assert handler.evaluate("sensor_temperature > 20 and binary_sensor_motion == 'motion'", context) is True

    def test_evaluate_with_unknown_states(self):
        """Test evaluation with unknown entity states."""
        handler = BooleanHandler()

        context = {"binary_sensor_unknown": "unknown", "binary_sensor_valid": "motion"}

        # Test unknown state handling
        assert handler.evaluate("binary_sensor_unknown == 'unknown'", context) is True
        assert handler.evaluate("binary_sensor_valid == 'motion'", context) is True
        assert handler.evaluate("binary_sensor_unknown == 'unknown' and binary_sensor_valid == 'motion'", context) is True
