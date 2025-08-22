"""Test simple variable reference with actual evaluator."""

import pytest
from unittest.mock import MagicMock, patch

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator


def test_simple_variable_evaluator(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that evaluator works with simple variable references."""
    # Create evaluator
    evaluator = Evaluator(mock_hass)

    # Test simple variable reference
    config = FormulaConfig(id="test_formula", formula="power_reading", variables={"power_reading": "sensor.power_meter"})

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
    # Register the entity in mock entity registry
    mock_entity_registry.register_entity("sensor.temperature", "sensor.temperature", "sensor")

    # Mock domain resolution (required for direct entity reference resolution)
    with (
        patch(
            "ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase.get_ha_domains"
        ) as mock_get_domains,
        patch("ha_synthetic_sensors.collection_resolver.er.async_get") as mock_er_collection,
        patch("ha_synthetic_sensors.constants_entities.er.async_get") as mock_er_constants,
    ):
        mock_get_domains.return_value = frozenset({"sensor", "binary_sensor", "switch", "light", "climate"})
        mock_er_collection.return_value = mock_entity_registry
        mock_er_constants.return_value = mock_entity_registry

        # Set up proper mock state function
        def mock_get_state(entity_id):
            if entity_id == "sensor.temperature":
                mock_state = MagicMock()
                mock_state.state = "22.0"
                return mock_state
            return None

        mock_hass.states.get.side_effect = mock_get_state

        # Create evaluator with HA lookups enabled
        evaluator = Evaluator(mock_hass)
        evaluator.update_integration_entities({"sensor.temperature"})

        # Test direct entity reference (no variables needed)
        config = FormulaConfig(id="test_formula", formula="sensor.temperature", variables={})

        result = evaluator.evaluate_formula(config, {})

    # Debug output
    print(f"Evaluation result: {result}")

    # Should succeed and return the value from HA state
    assert result["success"] is True
    # With ReferenceValue architecture, extract the value for comparison
    value = result["value"]
    if hasattr(value, "value"):
        # This is a ReferenceValue object - extract the raw value
        assert value.value == 22.0, f"Expected 22.0, got {value.value} (full result: {result})"
    else:
        # This is a raw value
        assert value == 22.0, f"Expected 22.0, got {value} (full result: {result})"

    # Should have called Home Assistant to get the entity state
    mock_hass.states.get.assert_called_with("sensor.temperature")


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
