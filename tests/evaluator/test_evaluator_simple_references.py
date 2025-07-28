"""Test simple variable reference with actual evaluator."""

import pytest
from unittest.mock import MagicMock

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator


def test_simple_variable_evaluator(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that evaluator works with simple variable references."""
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

    # Should not call Home Assistant since context provides the value
    mock_hass.states.get.assert_not_called()


def test_direct_entity_reference(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test direct entity reference without variables."""
    # Create evaluator with HA lookups enabled
    evaluator = Evaluator(mock_hass, allow_ha_lookups=True)

    # Test direct entity reference (no variables needed)
    config = FormulaConfig(id="test_formula", formula="sensor.temperature", variables={})

    # Create context with the entity value
    context = {"sensor.temperature": 22.0}

    result = evaluator.evaluate_formula(config, context)

    # Should succeed and return the value
    assert result["success"] is True
    assert result["value"] == 22.0

    # Should not call Home Assistant since context provides the value
    mock_hass.states.get.assert_not_called()


def test_numeric_literal(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test numeric literal (no variables or entities needed)."""
    # Create evaluator
    evaluator = Evaluator(mock_hass)

    # Test numeric literal
    config = FormulaConfig(id="test_formula", formula="123.45", variables={})

    result = evaluator.evaluate_formula(config)

    # Should succeed and return the value
    assert result["success"] is True
    assert result["value"] == 123.45

    # Should not have called any entities - but let's be safe about checking this
