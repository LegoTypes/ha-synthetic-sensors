"""Test handling of None values from data providers - strict error handling."""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.exceptions import DataValidationError
from ha_synthetic_sensors.type_definitions import DataProviderResult
from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalContextDict
from ha_synthetic_sensors.evaluation_context import HierarchicalEvaluationContext
from homeassistant.const import STATE_UNKNOWN


def _create_empty_context() -> HierarchicalContextDict:
    """Create empty HierarchicalContextDict for testing - architectural compliance."""
    hierarchical_context = HierarchicalEvaluationContext("test")
    return HierarchicalContextDict(hierarchical_context)


def test_data_provider_returns_none(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that when data provider callback returns None, it raises DataValidationError."""

    def mock_bad_data_provider(entity_id: str) -> DataProviderResult:
        return None  # type: ignore[return-value]

    evaluator = Evaluator(mock_hass, data_provider_callback=mock_bad_data_provider)
    evaluator.update_integration_entities({"sensor.test"})

    config = FormulaConfig(id="test_formula", formula="test_var", variables={"test_var": "sensor.test"})

    with pytest.raises(DataValidationError, match="Data provider callback returned None.*fatal implementation error"):
        evaluator.evaluate_formula(config, _create_empty_context())


def test_data_provider_returns_none_value(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that when data provider returns None as value, it's handled gracefully."""

    def mock_data_provider(entity_id: str) -> DataProviderResult:
        return {"value": None, "exists": True}

    evaluator = Evaluator(mock_hass, data_provider_callback=mock_data_provider)
    evaluator.update_integration_entities({"sensor.test"})

    config = FormulaConfig(id="test_formula", formula="test_var", variables={"test_var": "sensor.test"})

    # Should handle None values gracefully by returning an alternate HA state with no numeric value
    result = evaluator.evaluate_formula(config, _create_empty_context())
    assert result["success"] is True
    assert result.get("state") == STATE_UNKNOWN
    assert result.get("value") is None


def test_evaluator_handles_none_from_data_provider(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that evaluator handles None values from data provider gracefully."""

    # Mock data provider callback that returns None value (entity exists but unavailable)
    def mock_data_provider(entity_id: str) -> DataProviderResult:
        return {"value": None, "exists": True}

    # Create evaluator with data provider
    evaluator = Evaluator(mock_hass, data_provider_callback=mock_data_provider)
    evaluator.update_integration_entities({"sensor.power_meter"})

    # Test simple variable reference with None value
    config = FormulaConfig(id="test_formula", formula="power_reading", variables={"power_reading": "sensor.power_meter"})

    # Should handle None values gracefully by returning an alternate HA state with no numeric value
    result = evaluator.evaluate_formula(config, _create_empty_context())
    assert result["success"] is True
    assert result.get("state") == STATE_UNKNOWN
    assert result.get("value") is None


def test_evaluator_handles_callback_returning_none(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that evaluator handles callback returning None as fatal error."""

    # Mock data provider callback that returns None (bad implementation)
    def mock_bad_data_provider(entity_id: str) -> DataProviderResult:
        return None  # type: ignore[return-value]

    # Create evaluator with bad data provider
    evaluator = Evaluator(mock_hass, data_provider_callback=mock_bad_data_provider)
    evaluator.update_integration_entities({"sensor.power_meter"})

    # Test simple variable reference
    config = FormulaConfig(id="test_formula", formula="power_reading", variables={"power_reading": "sensor.power_meter"})

    # Should raise DataValidationError for None callback result (new strict behavior)
    with pytest.raises(DataValidationError, match="Data provider callback returned None.*fatal implementation error"):
        evaluator.evaluate_formula(config, _create_empty_context())


def test_data_provider_with_valid_values(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that data provider works correctly with valid values."""

    # Mock data provider that returns valid values
    def mock_data_provider(entity_id: str) -> DataProviderResult:
        if entity_id == "sensor.valid_power":
            return {"value": 42.5, "exists": True}  # Valid value
        return {"value": None, "exists": False}  # Entity doesn't exist

    # Create evaluator with data provider
    evaluator = Evaluator(mock_hass, data_provider_callback=mock_data_provider)
    evaluator.update_integration_entities({"sensor.valid_power"})

    # Test simple variable reference with valid value
    config = FormulaConfig(id="test_formula", formula="power_reading", variables={"power_reading": "sensor.valid_power"})

    result = evaluator.evaluate_formula(config, _create_empty_context())

    # Should succeed and return the value
    assert result["success"] is True
    assert result["value"] == 42.5


if __name__ == "__main__":
    test_data_provider_returns_none()
    test_data_provider_returns_none_value()
    test_evaluator_handles_none_from_data_provider()
    test_evaluator_handles_callback_returning_none()
    test_data_provider_with_valid_values()
