"""Test that the 'state' token in main formulas resolves to the backing entity."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.sensor_manager import DynamicSensor, SensorManager
from ha_synthetic_sensors.evaluator import Evaluator


class TestStateTokenInMainFormula:
    """Test that the 'state' token in main formulas resolves to the backing entity."""

    @pytest.fixture
    def evaluator(self, mock_hass, mock_entity_registry, mock_states):
        """Create an evaluator instance."""
        return Evaluator(mock_hass)

    @pytest.fixture
    def sensor_manager(self, mock_hass, mock_entity_registry, mock_states):
        """Create a sensor manager instance."""
        name_resolver = MagicMock()
        add_entities_callback = MagicMock()
        return SensorManager(mock_hass, name_resolver, add_entities_callback)

    @pytest.fixture
    def state_token_sensor_config(self):
        """Create a sensor configuration that uses the 'state' token in main formula."""
        return SensorConfig(
            unique_id="span_span_panel_current_power",
            name="Current Power",
            entity_id="sensor.current_power",  # Backing entity
            device_identifier="sp3-simulation-001",
            formulas=[
                FormulaConfig(id="main", formula="state"),  # Should resolve to sensor.current_power
                FormulaConfig(id="amperage", formula="state / 240", variables={}),
            ],
        )

    async def test_state_token_resolves_to_backing_entity(
        self, mock_hass, mock_entity_registry, mock_states, sensor_manager, state_token_sensor_config
    ):
        """Test that the 'state' token in main formula resolves to the backing entity."""

        # Set up data provider callback to return the backing entity value
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.current_power":
                return {"value": 1200.0, "exists": True}
            return {"value": None, "exists": False}

        # Register the backing entity with the sensor manager
        sensor_manager.register_data_provider_entities({"sensor.current_power"}, allow_ha_lookups=False, change_notifier=None)

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"span_span_panel_current_power": "sensor.current_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Update the sensor manager's evaluator's data provider callback using the property setter
        sensor_manager.evaluator.data_provider_callback = mock_data_provider

        # Create the sensor using the sensor manager's evaluator
        sensor = DynamicSensor(
            hass=mock_hass, config=state_token_sensor_config, evaluator=sensor_manager.evaluator, sensor_manager=sensor_manager
        )
        sensor.hass = mock_hass
        sensor.entity_id = "sensor.span_span_panel_current_power"

        # Mock async_write_ha_state to avoid Home Assistant lifecycle issues
        with patch.object(sensor, "async_write_ha_state"):
            # Call the update method
            await sensor._async_update_sensor()

            # Verify the sensor state was set correctly
            assert sensor._attr_native_value == 1200.0

            # Verify the attribute was calculated correctly
            assert "amperage" in sensor._calculated_attributes
            assert sensor._calculated_attributes["amperage"] == 5.0

    async def test_state_token_without_backing_entity_fails(
        self, mock_hass, mock_entity_registry, mock_states, evaluator, sensor_manager
    ):
        """Test that using 'state' token without backing entity fails gracefully."""
        config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            # No entity_id specified - this should cause the state token to fail
            formulas=[
                FormulaConfig(id="main", formula="state"),
            ],
        )

        sensor = DynamicSensor(hass=mock_hass, config=config, evaluator=evaluator, sensor_manager=sensor_manager)
        sensor.hass = mock_hass
        sensor.entity_id = "sensor.test_sensor"

        # Mock the evaluator to simulate the failure
        def mock_evaluate_formula_with_sensor_config(config, context=None, sensor_config=None):
            # Should fail because there's no backing entity to resolve 'state' to
            return {"success": False, "error": "'state' is not defined for expression 'state'", "state": "unavailable"}

        evaluator.evaluate_formula_with_sensor_config = mock_evaluate_formula_with_sensor_config

        # Mock async_write_ha_state to avoid Home Assistant lifecycle issues
        with patch.object(sensor, "async_write_ha_state"):
            # Call the update method
            await sensor._async_update_sensor()

            # Verify the sensor is unavailable due to the error
