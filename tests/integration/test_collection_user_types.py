"""Test comparison logic in collection patterns."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors
from ha_synthetic_sensors.collection_resolver import CollectionResolver
from ha_synthetic_sensors.condition_parser import ConditionParser
from ha_synthetic_sensors.constants_types import TypeCategory
from ha_synthetic_sensors.type_analyzer import OperandType


class TestComparisonLogic:
    """Test comparison logic in collection patterns."""

    def test_numeric_comparisons(self):
        """Test numeric comparison logic."""
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

    def test_boolean_comparisons(self):
        """Test boolean comparison logic."""
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

    def test_string_comparisons(self):
        """Test string comparison logic."""
        # Test basic string comparisons
        assert ConditionParser.compare_values("hello", "==", "hello") is True
        assert ConditionParser.compare_values("hello", "!=", "world") is True
        assert ConditionParser.compare_values("abc", "<", "def") is True
        assert ConditionParser.compare_values("def", ">", "abc") is True

    def test_type_conversion_edge_cases(self):
        """Test edge cases in type conversion."""
        # Test scientific notation
        assert ConditionParser.compare_values(1.23e-4, "==", "0.000123") is True

        # Test invalid conversions return False
        assert ConditionParser.compare_values("invalid", ">", 5) is False
        assert ConditionParser.compare_values(5, ">", "invalid") is False

    def test_condition_parsing(self):
        """Test condition parsing functionality."""
        # Test basic condition parsing
        condition = ConditionParser.parse_state_condition("== 50")
        assert condition["operator"] == "=="
        assert condition["value"] == "50"

        condition = ConditionParser.parse_state_condition(">= 100")
        assert condition["operator"] == ">="
        assert condition["value"] == "100"

        condition = ConditionParser.parse_state_condition("!= off")
        assert condition["operator"] == "!="
        assert condition["value"] == "off"

        # Test negation
        condition = ConditionParser.parse_state_condition("!on")
        assert condition["operator"] == "!="
        assert condition["value"] == "on"

        # Test bare values (default to equality)
        condition = ConditionParser.parse_state_condition("active")
        assert condition["operator"] == "=="
        assert condition["value"] == "active"

    def test_condition_evaluation(self):
        """Test condition evaluation functionality."""
        # Test numeric condition evaluation
        condition = ConditionParser.parse_state_condition(">= 50")
        assert ConditionParser.evaluate_condition(75, condition) is True
        assert ConditionParser.evaluate_condition(25, condition) is False

        # Test boolean condition evaluation
        condition = ConditionParser.parse_state_condition("== true")
        assert ConditionParser.evaluate_condition(True, condition) is True
        assert ConditionParser.evaluate_condition(False, condition) is False

        # Test string condition evaluation
        condition = ConditionParser.parse_state_condition("!= off")
        assert ConditionParser.evaluate_condition("on", condition) is True
        assert ConditionParser.evaluate_condition("off", condition) is False

    def test_collection_resolver_integration(self, mock_hass, mock_entity_registry, mock_states):
        """Test that collection resolver works with the new comparison logic."""
        resolver = CollectionResolver(mock_hass)

        # Set up mock entities
        mock_states["sensor.power_meter"] = type("MockState", (), {"state": "1000", "attributes": {}})()
        mock_states["sensor.low_power"] = type("MockState", (), {"state": "100", "attributes": {}})()

        # Test state condition matching
        result = resolver._entity_matches_state_condition("sensor.power_meter", ">=", "500")
        assert result is True

        result = resolver._entity_matches_state_condition("sensor.low_power", ">=", "500")
        assert result is False

        # Test string condition matching
        mock_states["switch.device"] = type("MockState", (), {"state": "on", "attributes": {}})()
        result = resolver._entity_matches_state_condition("switch.device", "==", "on")
        assert result is True

        result = resolver._entity_matches_state_condition("switch.device", "==", "off")
        assert result is False
