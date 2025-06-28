"""Test evaluator handling of None values from data providers - strict error handling."""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.exceptions import DataValidationError
from ha_synthetic_sensors.types import DataProviderResult


def test_evaluator_handles_none_value_from_data_provider() -> None:
    """Test that evaluator properly handles None values from data provider callbacks as fatal errors."""
    # Mock Home Assistant instance
    mock_hass = MagicMock()
    mock_hass.states = MagicMock()

    # Mock data provider that returns None for an entity (e.g., panel-level sensor)
    def mock_data_provider(entity_id: str) -> DataProviderResult:
        if entity_id == "sensor.panel_power":
            return {"value": None, "exists": True}  # Entity exists but has None value
        return {"value": None, "exists": False}  # Entity doesn't exist

    # Create evaluator with data provider
    evaluator = Evaluator(mock_hass, data_provider_callback=mock_data_provider)
    evaluator.update_integration_entities({"sensor.panel_power"})

    # Test simple variable reference where the variable resolves to None
    config = FormulaConfig(
        id="test_formula",
        formula="source_value",
        variables={"source_value": "sensor.panel_power"},
    )  # Simple variable reference

    # Should raise DataValidationError for None values (new strict behavior)
    with pytest.raises(DataValidationError) as exc_info:
        evaluator.evaluate_formula(config)

    assert "None state value" in str(exc_info.value)
    assert "fatal error" in str(exc_info.value)


def test_evaluator_handles_none_entity_reference() -> None:
    """Test that evaluator handles None values for direct entity references as fatal errors."""
    # Mock Home Assistant instance
    mock_hass = MagicMock()
    mock_hass.states = MagicMock()

    # Mock data provider that returns None for an entity
    def mock_data_provider(entity_id: str) -> DataProviderResult:
        if entity_id == "sensor.offline_sensor":
            return {"value": None, "exists": True}  # Entity exists but has None value
        return {"value": None, "exists": False}  # Entity doesn't exist

    # Create evaluator with data provider
    evaluator = Evaluator(mock_hass, data_provider_callback=mock_data_provider)
    evaluator.update_integration_entities({"sensor.offline_sensor"})

    # Test direct entity reference in formula
    config = FormulaConfig(id="test_formula", formula="sensor.offline_sensor + 10", variables={})  # Direct entity reference

    # Should raise DataValidationError for None values (new strict behavior)
    with pytest.raises(DataValidationError) as exc_info:
        evaluator.evaluate_formula(config)

    assert "None state value" in str(exc_info.value)
    assert "fatal error" in str(exc_info.value)


def test_evaluator_works_with_valid_values() -> None:
    """Test that evaluator still works correctly with valid values."""
    # Mock Home Assistant instance
    mock_hass = MagicMock()
    mock_hass.states = MagicMock()

    # Mock data provider that returns valid values
    def mock_data_provider(entity_id: str) -> DataProviderResult:
        if entity_id == "sensor.valid_power":
            return {"value": 42.5, "exists": True}  # Valid value
        return {"value": None, "exists": False}  # Entity doesn't exist

    # Create evaluator with data provider
    evaluator = Evaluator(mock_hass, data_provider_callback=mock_data_provider)
    evaluator.update_integration_entities({"sensor.valid_power"})

    # Test simple variable reference with valid value
    config = FormulaConfig(
        id="test_formula",
        formula="power_reading",
        variables={"power_reading": "sensor.valid_power"},
    )

    result = evaluator.evaluate_formula(config)

    # Should succeed and return the value
    assert result["success"] is True
    assert result["value"] == 42.5


if __name__ == "__main__":
    test_evaluator_handles_none_value_from_data_provider()
    test_evaluator_handles_none_entity_reference()
    test_evaluator_works_with_valid_values()
    test_evaluator_works_with_valid_values()
