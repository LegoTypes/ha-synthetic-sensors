"""Test that None values and bad data cause fatal errors instead of warnings."""

from unittest.mock import MagicMock

import pytest

from homeassistant.const import STATE_UNKNOWN

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.exceptions import DataValidationError
from ha_synthetic_sensors.type_definitions import DataProviderResult


def test_data_provider_returning_none_causes_fatal_error(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that when data provider callback returns None, it causes a fatal DataValidationError."""

    # Create evaluator with data provider callback that returns None
    def bad_data_provider(entity_id: str) -> None:
        return None  # This should cause a fatal error

    evaluator = Evaluator(mock_hass, data_provider_callback=bad_data_provider)
    evaluator.update_integration_entities({"sensor.test"})  # Tell evaluator this entity comes from integration

    config = FormulaConfig(id="test_formula", formula="test_var + 10", variables={"test_var": "sensor.test"})

    # Should raise DataValidationError for None data provider
    with pytest.raises(DataValidationError, match="Data provider callback returned None"):
        evaluator.evaluate_formula(config)


def test_data_provider_returning_none_value_handled_gracefully(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that when data provider returns valid structure but None value, it's handled gracefully."""

    # Create evaluator with data provider that returns None value
    def none_value_provider(entity_id: str) -> DataProviderResult:
        return {
            "value": None,
            "exists": True,
        }  # Entity exists but has None value - should be handled gracefully

    evaluator = Evaluator(mock_hass, data_provider_callback=none_value_provider)
    evaluator.update_integration_entities({"sensor.test"})  # Tell evaluator this entity comes from integration

    config = FormulaConfig(id="test_formula", formula="test_var", variables={"test_var": "sensor.test"})

    # Should handle None values gracefully by returning "unknown" state
    result = evaluator.evaluate_formula(config)
    assert result["success"] is True
    assert result["state"] == "unknown"
    assert result["value"] is None


def test_data_provider_returning_unavailable_state_handled_gracefully(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that unavailable state values are handled gracefully with state reflection."""

    # Create evaluator with data provider that returns unavailable state
    def unavailable_provider(entity_id: str) -> DataProviderResult:
        return {"value": "unavailable", "exists": True}  # Should be handled gracefully

    evaluator = Evaluator(mock_hass, data_provider_callback=unavailable_provider)
    evaluator.update_integration_entities({"sensor.test"})  # Tell evaluator this entity comes from integration

    config = FormulaConfig(id="test_formula", formula="test_var", variables={"test_var": "sensor.test"})

    # Should handle gracefully with state reflection
    result = evaluator.evaluate_formula(config)

    assert result["success"] is True  # Non-fatal - reflects dependency state
    assert result.get("state") == STATE_UNKNOWN  # Reflects unavailable dependency as unknown per design guide
    # Check that the enhanced dependency reporting includes the entity ID
    deps = result.get("unavailable_dependencies", [])
    assert any("sensor.test" in dep for dep in deps), f"Expected 'sensor.test' in dependencies: {deps}"
