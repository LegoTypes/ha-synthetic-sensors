"""Test natural fallback behavior for entity resolution."""

import pytest
from unittest.mock import MagicMock, patch

from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.config_models import SensorConfig, FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.exceptions import MissingDependencyError


@pytest.fixture
def data_provider_callback():
    """Create a mock data provider callback."""

    def mock_provider(entity_id: str):
        # Return different values for different backing entities
        if entity_id == "sensor.backing_virtual":
            return {"value": 100.0, "exists": True}
        elif entity_id == "sensor.backing_mixed":
            return {"value": 200.0, "exists": True}
        # For sensor.backing_ha_only, return None to simulate not found in data provider
        return {"value": None, "exists": False}

    return mock_provider


@pytest.fixture
def sensor_config_virtual():
    """Create a sensor config that uses virtual backing entity."""
    return SensorConfig(
        unique_id="virtual_sensor",
        name="Virtual Sensor",
        entity_id="sensor.virtual_test",
        formulas=[FormulaConfig(id="main", formula="backing_value", variables={"backing_value": "sensor.backing_virtual"})],
    )


@pytest.fixture
def sensor_config_ha_only():
    """Create a sensor config that should fall back to HA lookup."""
    return SensorConfig(
        unique_id="ha_sensor",
        name="HA Sensor",
        entity_id="sensor.ha_test",
        formulas=[FormulaConfig(id="main", formula="backing_value", variables={"backing_value": "sensor.backing_ha_only"})],
    )


def test_register_data_provider_entities_with_natural_fallback(mock_hass, mock_entity_registry, mock_states):
    """Test that register_data_provider_entities works with natural fallback behavior."""
    # Create evaluator with data provider callback
    evaluator = Evaluator(MagicMock(), data_provider_callback=lambda x: {"value": 42, "exists": True})

    # Create a minimal sensor manager instance by patching the problematic parts
    with patch("ha_synthetic_sensors.sensor_manager.dr.async_get"):
        sensor_manager = SensorManager.__new__(SensorManager)
        sensor_manager._evaluator = evaluator

        # Test with natural fallback behavior
        sensor_manager.register_data_provider_entities({"sensor.backing_entity"})

        # Verify the entities are registered
        assert "sensor.backing_entity" in sensor_manager._registered_entities


def test_build_variable_context_with_data_provider_and_natural_fallback(
    mock_hass, mock_entity_registry, mock_states, data_provider_callback
):
    """Test _build_variable_context when data provider exists and natural fallback is used."""
    # Create evaluator with data provider callback
    evaluator = Evaluator(mock_hass, data_provider_callback=data_provider_callback)

    # Create a DynamicSensor instance
    from ha_synthetic_sensors.sensor_manager import DynamicSensor

    sensor_config = SensorConfig(
        unique_id="test_sensor",
        name="Test Sensor",
        entity_id="sensor.test",
        formulas=[FormulaConfig(id="main", formula="backing_value", variables={"backing_value": "sensor.backing_virtual"})],
    )

    # Create mock sensor manager
    mock_sensor_manager = MagicMock()
    # allow_ha_lookups attribute removed - natural fallback is always enabled

    # Create sensor
    sensor = DynamicSensor(mock_hass, sensor_config, evaluator, mock_sensor_manager)

    # Mock HA state
    mock_state = MagicMock()
    mock_state.state = "999.0"
    mock_hass.states.get.return_value = mock_state

    # Build variable context - should return None (use data provider)
    context = sensor._build_variable_context(sensor_config.formulas[0])
    assert context is None  # Should delegate to evaluator's data provider

    # Verify HA states.get was not called since data provider has the entity
    mock_hass.states.get.assert_not_called()


def test_build_variable_context_with_data_provider_and_ha_fallback(
    mock_hass, mock_entity_registry, mock_states, data_provider_callback
):
    """Test _build_variable_context when data provider doesn't have entity and falls back to HA."""
    # Create evaluator with data provider callback
    evaluator = Evaluator(mock_hass, data_provider_callback=data_provider_callback)

    # Create a DynamicSensor instance
    from ha_synthetic_sensors.sensor_manager import DynamicSensor

    sensor_config = SensorConfig(
        unique_id="test_sensor",
        name="Test Sensor",
        entity_id="sensor.test",
        formulas=[FormulaConfig(id="main", formula="backing_value", variables={"backing_value": "sensor.backing_ha_only"})],
    )

    # Create mock sensor manager
    mock_sensor_manager = MagicMock()
    # allow_ha_lookups attribute removed - natural fallback is always enabled

    # Create sensor
    sensor = DynamicSensor(mock_hass, sensor_config, evaluator, mock_sensor_manager)

    # Mock HA state by adding it to the mock_states dictionary
    mock_state = MagicMock()
    mock_state.state = "42.5"
    mock_states["sensor.backing_ha_only"] = mock_state

    # Build variable context - should return None when data provider is available
    # The evaluator will handle variable resolution through natural fallback
    context = sensor._build_variable_context(sensor_config.formulas[0])
    assert context is None  # Should return None to let evaluator handle resolution

    # Verify HA states.get was not called since data provider handles resolution
    mock_hass.states.get.assert_not_called()


def test_build_variable_context_no_data_provider_always_uses_ha(mock_hass, mock_entity_registry, mock_states):
    """Test _build_variable_context when no data provider is configured."""
    # Create evaluator without data provider callback
    evaluator = Evaluator(mock_hass, data_provider_callback=None)

    # Create a DynamicSensor instance
    from ha_synthetic_sensors.sensor_manager import DynamicSensor

    sensor_config = SensorConfig(
        unique_id="test_sensor",
        name="Test Sensor",
        entity_id="sensor.test",
        formulas=[FormulaConfig(id="main", formula="backing_value", variables={"backing_value": "sensor.backing_virtual"})],
    )

    # Create mock sensor manager
    mock_sensor_manager = MagicMock()
    # allow_ha_lookups attribute removed - natural fallback is always enabled

    # Create sensor
    sensor = DynamicSensor(mock_hass, sensor_config, evaluator, mock_sensor_manager)

    # Mock HA state by adding it to the mock_states dictionary
    mock_state = MagicMock()
    mock_state.state = "123.45"
    mock_states["sensor.backing_virtual"] = mock_state

    # Build variable context - should return context with HA values since no data provider
    context = sensor._build_variable_context(sensor_config.formulas[0])
    assert context is not None
    assert context["backing_value"] == 123.45

    # Verify HA states.get was called
    mock_hass.states.get.assert_called_with("sensor.backing_virtual")


def test_build_variable_context_missing_entity_returns_none(
    mock_hass, mock_entity_registry, mock_states, data_provider_callback
):
    """Test _build_variable_context when entity is missing from both data provider and HA."""
    # Create evaluator with data provider callback
    evaluator = Evaluator(mock_hass, data_provider_callback=data_provider_callback)

    # Create a DynamicSensor instance
    from ha_synthetic_sensors.sensor_manager import DynamicSensor

    sensor_config = SensorConfig(
        unique_id="test_sensor",
        name="Test Sensor",
        entity_id="sensor.test",
        formulas=[FormulaConfig(id="main", formula="backing_value", variables={"backing_value": "sensor.missing_entity"})],
    )

    # Create mock sensor manager
    mock_sensor_manager = MagicMock()

    # Create sensor
    sensor = DynamicSensor(mock_hass, sensor_config, evaluator, mock_sensor_manager)

    # Mock HA state to return None (entity not found)
    mock_hass.states.get.return_value = None

    # Build variable context - should return None when data provider is available
    # The evaluator will handle missing entity detection during evaluation
    context = sensor._build_variable_context(sensor_config.formulas[0])
    assert context is None  # Should return None to let evaluator handle resolution

    # Verify HA states.get was not called since data provider handles resolution
    mock_hass.states.get.assert_not_called()
