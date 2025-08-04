"""Test that the 'state' variable is available in attribute formulas."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.sensor_manager import DynamicSensor, SensorManager
from ha_synthetic_sensors.evaluator import Evaluator


class TestStateVariableInAttributes:
    """Test that attribute formulas can access the sensor's state via the 'state' variable."""

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
    def basic_sensor_config(self):
        """Create a basic sensor configuration with attributes."""
        return SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            entity_id="sensor.test_sensor",
            device_identifier="test_device",
            formulas=[
                FormulaConfig(id="main", formula="source_value", variables={"source_value": "sensor.backing_entity"}),
                FormulaConfig(id="daily_total", formula="state * 24", variables={}),
                FormulaConfig(id="weekly_total", formula="state * 24 * 7", variables={}),
                FormulaConfig(id="with_additional_vars", formula="state * multiplier", variables={"multiplier": 2.5}),
            ],
        )

    async def test_state_variable_available_in_attributes(
        self, mock_hass, mock_entity_registry, mock_states, evaluator, sensor_manager, basic_sensor_config
    ):
        """Test that attribute formulas can access the sensor's state."""
        # Create the sensor
        sensor = DynamicSensor(hass=mock_hass, config=basic_sensor_config, evaluator=evaluator, sensor_manager=sensor_manager)
        # Set the hass attribute properly
        sensor.hass = mock_hass
        sensor.entity_id = "sensor.test_sensor"

        # Mock the evaluator to return a known value for the main formula
        main_result = {"success": True, "value": 100.0, "state": "ok"}

        # Mock the attribute formula evaluations
        def mock_evaluate_formula_with_sensor_config(config, context=None, sensor_config=None):
            if config.id == "daily_total":
                # Should have access to state=100.0
                assert context is not None
                assert "state" in context
                # With ReferenceValue architecture, check the .value property
                state_value = context["state"].value if hasattr(context["state"], "value") else context["state"]
                assert state_value == 100.0
                return {"success": True, "value": 2400.0, "state": "ok"}
            elif config.id == "weekly_total":
                # Should have access to state=100.0
                assert context is not None
                assert "state" in context
                # With ReferenceValue architecture, check the .value property
                state_value = context["state"].value if hasattr(context["state"], "value") else context["state"]
                assert state_value == 100.0
                return {"success": True, "value": 16800.0, "state": "ok"}
            elif config.id == "with_additional_vars":
                # Should have access to both state and multiplier
                assert context is not None
                assert "state" in context
                assert "multiplier" in context
                # With ReferenceValue architecture, check the .value property
                state_value = context["state"].value if hasattr(context["state"], "value") else context["state"]
                multiplier_value = (
                    context["multiplier"].value if hasattr(context["multiplier"], "value") else context["multiplier"]
                )
                assert state_value == 100.0
                assert multiplier_value == 2.5
                return {"success": True, "value": 250.0, "state": "ok"}
            else:
                return main_result

        evaluator.evaluate_formula_with_sensor_config = mock_evaluate_formula_with_sensor_config

        # Mock the _build_variable_context method to return proper variable values
        def mock_build_context(formula_config):
            if formula_config.id == "with_additional_vars":
                return {"multiplier": 2.5}
            elif formula_config.id == "main":
                return {"source_value": 100.0}
            else:
                return {}

        sensor._build_variable_context = mock_build_context

        # Mock async_write_ha_state to avoid Home Assistant lifecycle issues
        with patch.object(sensor, "async_write_ha_state"):
            # Call the update method
            await sensor._async_update_sensor()

            # Verify the sensor state was set
            assert sensor._attr_native_value == 100.0

            # Verify the attributes were calculated correctly
            assert "daily_total" in sensor._calculated_attributes
            assert sensor._calculated_attributes["daily_total"] == 2400.0

            assert "weekly_total" in sensor._calculated_attributes
            assert sensor._calculated_attributes["weekly_total"] == 16800.0

            assert "with_additional_vars" in sensor._calculated_attributes
            assert sensor._calculated_attributes["with_additional_vars"] == 250.0

    async def test_state_variable_with_none_context(
        self, mock_hass, mock_entity_registry, mock_states, evaluator, sensor_manager
    ):
        """Test that state variable works even when _build_variable_context returns None."""
        config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            entity_id="sensor.test_sensor",
            device_identifier="test_device",
            formulas=[
                FormulaConfig(id="main", formula="source_value", variables={"source_value": "sensor.backing_entity"}),
                FormulaConfig(
                    id="simple_attr",
                    formula="state * 2",
                    variables={},  # No variables, so _build_variable_context returns None
                ),
            ],
        )

        sensor = DynamicSensor(hass=mock_hass, config=config, evaluator=evaluator, sensor_manager=sensor_manager)
        # Set the hass attribute properly
        sensor.hass = mock_hass
        sensor.entity_id = "sensor.test_sensor"

        # Mock the evaluator
        main_result = {"success": True, "value": 50.0, "state": "ok"}

        def mock_evaluate_formula_with_sensor_config(config, context=None, sensor_config=None):
            if config.id == "simple_attr":
                # Should have context with state even though _build_variable_context returned None
                assert context is not None
                assert "state" in context
                # With ReferenceValue architecture, check the .value property
                state_value = context["state"].value if hasattr(context["state"], "value") else context["state"]
                assert state_value == 50.0
                return {"success": True, "value": 100.0, "state": "ok"}
            else:
                return main_result

        evaluator.evaluate_formula_with_sensor_config = mock_evaluate_formula_with_sensor_config

        # Mock async_write_ha_state to avoid Home Assistant lifecycle issues
        with patch.object(sensor, "async_write_ha_state"):
            # Call the update method
            await sensor._async_update_sensor()

            # Verify the attribute was calculated
            assert "simple_attr" in sensor._calculated_attributes
            assert sensor._calculated_attributes["simple_attr"] == 100.0
