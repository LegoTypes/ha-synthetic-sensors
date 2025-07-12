"""Test allow_ha_lookups parameter functionality."""

import pytest
from unittest.mock import MagicMock, patch

from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.config_models import SensorConfig, FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.states = MagicMock()
    return hass


@pytest.fixture
def data_provider_callback():
    """Create a mock data provider callback."""
    def mock_provider(entity_id: str):
        # Return different values for different backing entities
        if entity_id == "sensor.backing_virtual":
            return {"value": 100.0, "success": True}
        elif entity_id == "sensor.backing_mixed":
            return {"value": 200.0, "success": True}
        # For sensor.backing_ha_only, return None to simulate not found in data provider
        return None

    return mock_provider


@pytest.fixture
def sensor_config_virtual():
    """Create a sensor config that uses virtual backing entity."""
    return SensorConfig(
        unique_id="virtual_sensor",
        name="Virtual Sensor",
        entity_id="sensor.virtual_test",
        formulas=[
            FormulaConfig(
                id="main",
                formula="backing_value",
                variables={"backing_value": "sensor.backing_virtual"}
            )
        ]
    )


@pytest.fixture
def sensor_config_ha_only():
    """Create a sensor config that should fall back to HA lookup."""
    return SensorConfig(
        unique_id="ha_sensor",
        name="HA Sensor",
        entity_id="sensor.ha_test",
        formulas=[
            FormulaConfig(
                id="main",
                formula="backing_value",
                variables={"backing_value": "sensor.backing_ha_only"}
            )
        ]
    )


def test_register_data_provider_entities_with_allow_ha_lookups():
    """Test that register_data_provider_entities properly sets allow_ha_lookups flag."""
    # Create evaluator with data provider callback
    evaluator = Evaluator(MagicMock(), data_provider_callback=lambda x: {"value": 42, "success": True})

    # Create a minimal sensor manager instance by patching the problematic parts
    with patch("ha_synthetic_sensors.sensor_manager.dr.async_get"):
        sensor_manager = SensorManager.__new__(SensorManager)
        sensor_manager._registered_entities = set()
        sensor_manager._allow_ha_lookups = False
        sensor_manager._evaluator = evaluator

    # Test default behavior (allow_ha_lookups=False)
    sensor_manager.register_data_provider_entities({"sensor.test1"})
    assert sensor_manager._allow_ha_lookups is False

    # Test setting allow_ha_lookups=True
    sensor_manager.register_data_provider_entities({"sensor.test1"}, allow_ha_lookups=True)
    assert sensor_manager._allow_ha_lookups is True

    # Test setting allow_ha_lookups=False explicitly
    sensor_manager.register_data_provider_entities({"sensor.test1"}, allow_ha_lookups=False)
    assert sensor_manager._allow_ha_lookups is False


def test_build_variable_context_with_data_provider_and_allow_ha_lookups_false(mock_hass, data_provider_callback):
    """Test _build_variable_context when data provider exists and allow_ha_lookups=False."""
    # Create evaluator with data provider callback
    evaluator = Evaluator(mock_hass, data_provider_callback=data_provider_callback)

    # Create a DynamicSensor instance
    from ha_synthetic_sensors.sensor_manager import DynamicSensor

    sensor_config = SensorConfig(
        unique_id="test_sensor",
        name="Test Sensor",
        entity_id="sensor.test",
        formulas=[
            FormulaConfig(
                id="main",
                formula="backing_value",
                variables={"backing_value": "sensor.backing_virtual"}
            )
        ]
    )

    # Mock sensor manager
    mock_sensor_manager = MagicMock()
    mock_sensor_manager._allow_ha_lookups = False
    mock_sensor_manager.allow_ha_lookups = False

    # Create sensor
    sensor = DynamicSensor(
        mock_hass, sensor_config, evaluator, mock_sensor_manager
    )

    # Mock HA state
    mock_state = MagicMock()
    mock_state.state = "999.0"
    mock_hass.states.get.return_value = mock_state

    # Build variable context - should return None (use data provider)
    context = sensor._build_variable_context(sensor_config.formulas[0])
    assert context is None  # Should delegate to evaluator's data provider

    # Verify HA states.get was not called
    mock_hass.states.get.assert_not_called()


def test_build_variable_context_with_data_provider_and_allow_ha_lookups_true(mock_hass, data_provider_callback):
    """Test _build_variable_context when data provider exists and allow_ha_lookups=True."""
    # Create evaluator with data provider callback
    evaluator = Evaluator(mock_hass, data_provider_callback=data_provider_callback)

    # Create a DynamicSensor instance
    from ha_synthetic_sensors.sensor_manager import DynamicSensor

    sensor_config = SensorConfig(
        unique_id="test_sensor",
        name="Test Sensor",
        entity_id="sensor.test",
        formulas=[
            FormulaConfig(
                id="main",
                formula="backing_value",
                variables={"backing_value": "sensor.backing_ha_only"}
            )
        ]
    )

    # Mock sensor manager with allow_ha_lookups=True
    mock_sensor_manager = MagicMock()
    mock_sensor_manager._allow_ha_lookups = True
    mock_sensor_manager.allow_ha_lookups = True

    # Create sensor
    sensor = DynamicSensor(
        mock_hass, sensor_config, evaluator, mock_sensor_manager
    )

    # Mock HA state
    mock_state = MagicMock()
    mock_state.state = "42.5"
    mock_hass.states.get.return_value = mock_state

    # Build variable context - should return context with HA values
    context = sensor._build_variable_context(sensor_config.formulas[0])
    assert context is not None
    assert context["backing_value"] == 42.5  # Should use HA state value

    # Verify HA states.get was called
    mock_hass.states.get.assert_called_with("sensor.backing_ha_only")


def test_build_variable_context_no_data_provider_always_uses_ha(mock_hass):
    """Test _build_variable_context when no data provider is configured."""
    # Create evaluator without data provider callback
    evaluator = Evaluator(mock_hass, data_provider_callback=None)

    # Create a DynamicSensor instance
    from ha_synthetic_sensors.sensor_manager import DynamicSensor

    sensor_config = SensorConfig(
        unique_id="test_sensor",
        name="Test Sensor",
        entity_id="sensor.test",
        formulas=[
            FormulaConfig(
                id="main",
                formula="backing_value",
                variables={"backing_value": "sensor.backing_virtual"}
            )
        ]
    )

    # Mock sensor manager with allow_ha_lookups=False (should be ignored)
    mock_sensor_manager = MagicMock()
    mock_sensor_manager._allow_ha_lookups = False
    mock_sensor_manager.allow_ha_lookups = False

    # Create sensor
    sensor = DynamicSensor(
        mock_hass, sensor_config, evaluator, mock_sensor_manager
    )

    # Mock HA state
    mock_state = MagicMock()
    mock_state.state = "123.45"
    mock_hass.states.get.return_value = mock_state

    # Build variable context - should return context with HA values since no data provider
    context = sensor._build_variable_context(sensor_config.formulas[0])
    assert context is not None
    assert context["backing_value"] == 123.45

    # Verify HA states.get was called
    mock_hass.states.get.assert_called_with("sensor.backing_virtual")