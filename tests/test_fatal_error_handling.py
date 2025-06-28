"""Test that None values and bad data cause fatal errors instead of warnings."""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.exceptions import DataValidationError
from ha_synthetic_sensors.types import DataProviderResult


def test_data_provider_returning_none_raises_fatal_error() -> None:
    """Test that when data provider callback returns None, it raises a fatal error."""
    mock_hass = MagicMock()

    # Create evaluator with data provider callback that returns None
    def bad_data_provider(entity_id: str) -> None:
        return None  # This should be fatal

    evaluator = Evaluator(mock_hass, data_provider_callback=bad_data_provider)
    evaluator.update_integration_entities({"sensor.test"})  # Tell evaluator this entity comes from integration

    config = FormulaConfig(id="test_formula", formula="test_var", variables={"test_var": "sensor.test"})

    # Should raise DataValidationError, not return success with warnings
    with pytest.raises(DataValidationError) as exc_info:
        evaluator.evaluate_formula(config)

    assert "returned None" in str(exc_info.value)
    assert "fatal implementation error" in str(exc_info.value)


def test_data_provider_returning_none_value_raises_fatal_error() -> None:
    """Test that when data provider returns valid structure but None value, it raises fatal error."""
    mock_hass = MagicMock()

    # Create evaluator with data provider that returns None value
    def none_value_provider(entity_id: str) -> DataProviderResult:
        return {
            "value": None,
            "exists": True,
        }  # Entity exists but has None value - should be fatal

    evaluator = Evaluator(mock_hass, data_provider_callback=none_value_provider)
    evaluator.update_integration_entities({"sensor.test"})  # Tell evaluator this entity comes from integration

    config = FormulaConfig(id="test_formula", formula="test_var", variables={"test_var": "sensor.test"})

    # Should raise DataValidationError when evaluating the formula
    with pytest.raises(DataValidationError) as exc_info:
        evaluator.evaluate_formula(config)

    assert "None state value" in str(exc_info.value)
    assert "fatal error" in str(exc_info.value)


def test_data_provider_returning_unavailable_state_raises_fatal_error() -> None:
    """Test that unavailable state values also raise fatal errors."""
    mock_hass = MagicMock()

    # Create evaluator with data provider that returns unavailable state
    def unavailable_provider(entity_id: str) -> DataProviderResult:
        return {"value": "unavailable", "exists": True}  # Should be fatal

    evaluator = Evaluator(mock_hass, data_provider_callback=unavailable_provider)
    evaluator.update_integration_entities({"sensor.test"})  # Tell evaluator this entity comes from integration

    config = FormulaConfig(id="test_formula", formula="test_var", variables={"test_var": "sensor.test"})

    # Should raise DataValidationError for unavailable state
    with pytest.raises(DataValidationError) as exc_info:
        evaluator.evaluate_formula(config)

    assert "unavailable state" in str(exc_info.value)
    assert "fatal error" in str(exc_info.value)
