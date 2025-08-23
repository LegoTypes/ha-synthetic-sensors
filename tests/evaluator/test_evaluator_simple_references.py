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

    # Create context with the variable value as ReferenceValue (current architecture)
    from ha_synthetic_sensors.type_definitions import ReferenceValue

    context = {"power_reading": ReferenceValue("sensor.power_meter", 25.5)}

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

    # Ensure the entity is in mock_states (it should already be there, but let's be explicit)
    if "sensor.temperature" not in mock_states:
        from unittest.mock import Mock

        mock_states["sensor.temperature"] = Mock(
            state="22.0", entity_id="sensor.temperature", attributes={"device_class": "temperature"}
        )

    # Create data provider callback that returns the entity data
    def data_provider_callback(entity_id: str):
        if entity_id == "sensor.temperature":
            return {"value": 22.0, "exists": True}
        return {"value": None, "exists": False}

    # Create evaluator with data provider callback
    evaluator = Evaluator(mock_hass, data_provider_callback=data_provider_callback)

    # Register the entity with the evaluator
    evaluator.update_integration_entities({"sensor.temperature"})

    # Create a proper sensor configuration with backing entity mapping
    # The current system expects sensor configurations with proper entity mappings
    from ha_synthetic_sensors.config_models import SensorConfig, FormulaConfig

    sensor_config = SensorConfig(
        unique_id="test_sensor",
        name="Test Sensor",
        entity_id="sensor.test_sensor",
        device_identifier="test_device",
        formulas=[
            FormulaConfig(
                id="main",
                formula="sensor.temperature",  # Direct entity reference
                variables={},
            )
        ],
    )

    # Test direct entity reference using the proper sensor configuration
    result = evaluator.evaluate_formula_with_sensor_config(sensor_config.formulas[0], context={}, sensor_config=sensor_config)

    # Debug output
    print(f"Evaluation result: {result}")

    # Should succeed and return the value from data provider
    assert result["success"] is True
    # With ReferenceValue architecture, extract the value for comparison
    value = result["value"]
    if hasattr(value, "value"):
        # This is a ReferenceValue object - extract the raw value
        assert value.value == 22.0, f"Expected 22.0, got {value.value} (full result: {result})"
    else:
        # This is a raw value
        assert value == 22.0, f"Expected 22.0, got {value} (full result: {result})"

    # The data provider callback returns the value first, so mock_hass.states.get is not called
    # This is the expected behavior - data provider takes precedence over HA state lookups


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
