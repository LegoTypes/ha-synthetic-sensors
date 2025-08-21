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

        # Create evaluator with HA lookups enabled
        evaluator = Evaluator(mock_hass)
        evaluator.update_integration_entities({"sensor.temperature"})

        # The entity state is already set up by mock_states fixture
        # sensor.temperature should return Mock(state="22.0") from conftest.py line 795-797
        print(f"Available mock states: {list(mock_states.keys())}")
        if "sensor.temperature" in mock_states:
            print(f"sensor.temperature state: {mock_states['sensor.temperature'].state}")

        # Test direct entity reference (no variables needed)
        config = FormulaConfig(id="test_formula", formula="sensor.temperature", variables={})

        result = evaluator.evaluate_formula(config, {})

    # Debug output
    print(f"Evaluation result: {result}")
    print(f"Mock state calls: {mock_hass.states.get.call_args_list}")

    # Debug the mock state object
    mock_state_obj = mock_hass.states.get.return_value
    print(f"Mock state object: {mock_state_obj}")
    print(f"Mock state.state: {mock_state_obj.state}")

    # Test alternate state detection
    from ha_synthetic_sensors.constants_alternate import identify_alternate_state_value

    alt_result = identify_alternate_state_value(mock_state_obj.state)
    print(f"Alternate state detection result for '{mock_state_obj.state}': {alt_result}")

    # Should succeed and return the value from HA state
    assert result["success"] is True
    assert result["value"] == 22.0, f"Expected 22.0, got {result['value']} (full result: {result})"

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
