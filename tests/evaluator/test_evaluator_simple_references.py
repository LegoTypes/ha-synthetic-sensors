"""Test simple variable reference with actual evaluator."""

from unittest.mock import MagicMock

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator


def test_simple_variable_evaluator() -> None:
    """Test that evaluator works with simple variable references."""
    # Mock Home Assistant instance
    mock_hass = MagicMock()
    mock_hass.states = MagicMock()

    # Mock state object with a numeric value
    mock_state = MagicMock()
    mock_state.state = "25.5"
    mock_state.attributes = {}

    # Mock the get method to return our state
    mock_hass.states.get.return_value = mock_state

    # Create evaluator
    evaluator = Evaluator(mock_hass)

    # Test simple variable reference
    config = FormulaConfig(
        id="test_formula",
        formula="power_reading",
        variables={"power_reading": "sensor.power_meter"},
    )

    # Create context with the variable value
    context = {"power_reading": 25.5}

    result = evaluator.evaluate_formula(config, context)

    # Should succeed and return the value
    assert result["success"] is True
    assert result["value"] == 25.5

    # Verify it called the right entity
    mock_hass.states.get.assert_called_with("sensor.power_meter")


def test_direct_entity_reference() -> None:
    """Test direct entity reference without variables."""
    # Mock Home Assistant instance
    mock_hass = MagicMock()
    mock_hass.states = MagicMock()

    # Mock state object
    mock_state = MagicMock()
    mock_state.state = "42.0"
    mock_state.attributes = {}

    mock_hass.states.get.return_value = mock_state

    # Create evaluator with HA lookups enabled
    evaluator = Evaluator(mock_hass, allow_ha_lookups=True)

    # Test direct entity reference (no variables needed)
    config = FormulaConfig(id="test_formula", formula="sensor.temperature", variables={})

    result = evaluator.evaluate_formula(config)

    # Should succeed and return the value
    assert result["success"] is True
    assert result["value"] == 42.0

    # Verify it called the right entity
    mock_hass.states.get.assert_called_with("sensor.temperature")


def test_numeric_literal() -> None:
    """Test numeric literal (no variables or entities needed)."""
    mock_hass = MagicMock()

    # Create evaluator
    evaluator = Evaluator(mock_hass)

    # Test numeric literal
    config = FormulaConfig(id="test_formula", formula="123.45", variables={})

    result = evaluator.evaluate_formula(config)

    # Should succeed and return the value
    assert result["success"] is True
    assert result["value"] == 123.45

    # Should not have called any entities - but let's be safe about checking this
