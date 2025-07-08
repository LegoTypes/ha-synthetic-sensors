"""Test handling of None values from data providers - strict error handling."""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.exceptions import DataValidationError
from ha_synthetic_sensors.type_definitions import DataProviderResult
from ha_synthetic_sensors.variable_resolver import IntegrationResolutionStrategy


def test_data_provider_returns_none() -> None:
    """Test that when data provider callback returns None, it raises DataValidationError."""
    mock_callback = MagicMock(return_value=None)
    strategy = IntegrationResolutionStrategy(mock_callback)

    with pytest.raises(DataValidationError, match="Data provider callback returned None.*fatal implementation error"):
        strategy.resolve_variable("test_var", "sensor.test")


def test_data_provider_returns_none_value() -> None:
    """Test that when data provider returns None as value, it's treated as fatal error."""
    mock_callback = MagicMock(return_value={"value": None, "exists": True})
    strategy = IntegrationResolutionStrategy(mock_callback)

    # Should raise DataValidationError for None values (new strict behavior)
    with pytest.raises(DataValidationError, match="None state value.*fatal error"):
        strategy.resolve_variable("test_var", "sensor.test")


def test_evaluator_handles_none_from_data_provider() -> None:
    """Test that evaluator treats None values from data provider as fatal errors."""
    # Mock Home Assistant instance
    mock_hass = MagicMock()
    mock_hass.states = MagicMock()

    # Mock data provider callback that returns None value (entity exists but unavailable)
    def mock_data_provider(entity_id: str) -> DataProviderResult:
        return {"value": None, "exists": True}

    # Create evaluator with data provider
    evaluator = Evaluator(mock_hass, data_provider_callback=mock_data_provider)
    evaluator.update_integration_entities({"sensor.power_meter"})

    # Test simple variable reference with None value
    config = FormulaConfig(
        id="test_formula",
        formula="power_reading",
        variables={"power_reading": "sensor.power_meter"},
    )

    # Should raise DataValidationError for None values (new strict behavior)
    with pytest.raises(DataValidationError, match="None state value.*fatal error"):
        evaluator.evaluate_formula(config)


def test_evaluator_handles_callback_returning_none() -> None:
    """Test that evaluator handles callback returning None as fatal error."""
    # Mock Home Assistant instance
    mock_hass = MagicMock()
    mock_hass.states = MagicMock()

    # Mock data provider callback that returns None (bad implementation)
    def mock_bad_data_provider(entity_id: str) -> DataProviderResult:
        return None  # type: ignore[return-value]

    # Create evaluator with bad data provider
    evaluator = Evaluator(mock_hass, data_provider_callback=mock_bad_data_provider)
    evaluator.update_integration_entities({"sensor.power_meter"})

    # Test simple variable reference
    config = FormulaConfig(
        id="test_formula",
        formula="power_reading",
        variables={"power_reading": "sensor.power_meter"},
    )

    # Should raise DataValidationError for None callback result (new strict behavior)
    with pytest.raises(DataValidationError, match="Data provider callback returned None.*fatal implementation error"):
        evaluator.evaluate_formula(config)


def test_data_provider_with_valid_values() -> None:
    """Test that data provider works correctly with valid values."""
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
    test_data_provider_returns_none()
    test_data_provider_returns_none_value()
    test_evaluator_handles_none_from_data_provider()
    test_evaluator_handles_callback_returning_none()
    test_data_provider_with_valid_values()
