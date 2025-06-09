"""Tests for non-numeric state handling in the evaluator."""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import (
    CircuitBreakerConfig,
    Evaluator,
    NonNumericStateError,
)


class TestNonNumericStateHandling:
    """Test cases for non-numeric state handling."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()
        return hass

    def test_non_numeric_state_detection(self, mock_hass):
        """Test that non-numeric states are properly detected and handled."""
        evaluator = Evaluator(mock_hass)

        # Mock entity with non-numeric state
        mock_state = MagicMock()
        mock_state.state = "on"  # Non-numeric string
        mock_state.entity_id = "switch.test"
        mock_state.attributes = {}
        mock_hass.states.get.return_value = mock_state

        config = FormulaConfig(
            id="test_non_numeric", name="test", formula="switch.test + 1"
        )

        # Should detect non-numeric state and return unknown
        result = evaluator.evaluate_formula(config)
        assert result["success"] is False  # Switch is fundamentally non-numeric
        assert result["state"] == "unavailable"
        assert "missing_dependencies" in result
        assert "switch.test" in result["missing_dependencies"]

    def test_numeric_extraction_from_units(self, mock_hass):
        """Test that numeric values can be extracted from unit strings."""
        evaluator = Evaluator(mock_hass)

        # Test the numeric conversion directly
        assert evaluator._convert_to_numeric("25.5°C", "sensor.temp") == 25.5
        assert evaluator._convert_to_numeric("100 kWh", "sensor.energy") == 100.0
        assert evaluator._convert_to_numeric("-5.2°F", "sensor.outdoor_temp") == -5.2

    def test_non_numeric_exception_raised(self, mock_hass):
        """Test that NonNumericStateError is raised for truly non-numeric values."""
        evaluator = Evaluator(mock_hass)

        # These should raise NonNumericStateError
        with pytest.raises(NonNumericStateError) as exc_info:
            evaluator._convert_to_numeric("on", "switch.test")
        assert "switch.test" in str(exc_info.value)
        assert "on" in str(exc_info.value)

        with pytest.raises(NonNumericStateError):
            evaluator._convert_to_numeric("running", "sensor.status")

    def test_mixed_dependencies_handling(self, mock_hass):
        """Test handling of mixed numeric and non-numeric dependencies."""
        evaluator = Evaluator(mock_hass)

        def mock_states_get(entity_id):
            """Mock state getter with mixed states."""
            if entity_id == "sensor.numeric":
                state = MagicMock()
                state.state = "42.5"
                state.entity_id = entity_id
                state.attributes = {}
                return state
            elif entity_id == "sensor.non_numeric":
                state = MagicMock()
                state.state = "unavailable"
                state.entity_id = entity_id
                state.attributes = {}
                return state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        config = FormulaConfig(
            id="mixed_test", name="mixed", formula="sensor.numeric + sensor.non_numeric"
        )

        # Should return unknown due to non-numeric dependency
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True
        assert result["state"] == "unknown"
        assert "sensor.non_numeric" in result["unavailable_dependencies"]

    def test_circuit_breaker_for_non_numeric_states(self, mock_hass):
        """Test that non-numeric states are treated as transitory errors."""
        cb_config = CircuitBreakerConfig(
            max_fatal_errors=2, track_transitory_errors=True
        )
        evaluator = Evaluator(mock_hass, circuit_breaker_config=cb_config)

        # Mock entity that should be numeric but isn't
        mock_state = MagicMock()
        mock_state.state = "starting_up"
        mock_state.entity_id = "sensor.temperature"
        mock_state.attributes = {"device_class": "temperature"}
        mock_hass.states.get.return_value = mock_state

        config = FormulaConfig(
            id="temp_test", name="temp", formula="sensor.temperature + 10"
        )

        # Should continue trying even after many attempts (transitory error)
        for i in range(10):
            result = evaluator.evaluate_formula(config)
            assert result["success"] is True
            assert result["state"] == "unknown"
            assert "sensor.temperature" in result["unavailable_dependencies"]

    def test_backward_compatibility_fallback(self, mock_hass):
        """Test that _get_numeric_state still provides fallback for compatibility."""
        evaluator = Evaluator(mock_hass)

        # Mock state with non-numeric value
        mock_state = MagicMock()
        mock_state.state = "unavailable"
        mock_state.entity_id = "sensor.broken"

        # Should return 0.0 as fallback but log warning
        result = evaluator._get_numeric_state(mock_state)
        assert result == 0.0

    def test_missing_vs_non_numeric_entities(self, mock_hass):
        """Test distinction between missing entities (fatal) and non-numeric."""
        cb_config = CircuitBreakerConfig(max_fatal_errors=2)
        evaluator = Evaluator(mock_hass, circuit_breaker_config=cb_config)

        def mock_states_get(entity_id):
            if entity_id == "sensor.missing":
                return None  # Missing entity
            elif entity_id == "sensor.non_numeric":
                state = MagicMock()
                state.state = "unavailable"  # Use clearly transitory state
                state.entity_id = entity_id
                state.attributes = {}  # Add empty attributes dict
                return state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        # Test missing entity (should be fatal)
        missing_config = FormulaConfig(
            id="missing_test", name="missing", formula="sensor.missing + 1"
        )

        result1 = evaluator.evaluate_formula(missing_config)
        assert result1["success"] is False
        assert result1["state"] == "unavailable"

        result2 = evaluator.evaluate_formula(missing_config)
        assert result2["success"] is False

        # After max_fatal_errors, should skip evaluation
        result3 = evaluator.evaluate_formula(missing_config)
        assert result3["success"] is False
        assert "Skipping formula" in result3["error"]

        # Test non-numeric entity (should be transitory)
        non_numeric_config = FormulaConfig(
            id="non_numeric_test", name="non_numeric", formula="sensor.non_numeric + 1"
        )

        # Should continue evaluating even after many attempts
        for i in range(10):
            result = evaluator.evaluate_formula(non_numeric_config)
            assert result["success"] is True
            assert result["state"] == "unknown"
