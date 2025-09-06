"""Test dynamic dependency discovery with attribute formulas that use state references."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.sensor_manager import DynamicSensor, SensorManager
from ha_synthetic_sensors.evaluator import Evaluator


class TestDynamicDependencyDiscoveryAttributes:
    """Test that dynamic dependency discovery works correctly with attribute formulas using state."""

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
    def sensor_config_with_state_attributes(self):
        """Create a sensor config with attribute formulas that use state."""
        return SensorConfig(
            unique_id="test_power_sensor",
            name="Test Power Sensor",
            entity_id="sensor.test_power_sensor",
            device_identifier="test_device",
            formulas=[
                # Main formula
                FormulaConfig(
                    id="main", formula="sensor.backing_power", variables={"sensor.backing_power": "sensor.backing_power"}
                ),
                # Attribute formula that uses state (like SPAN panel amperage)
                FormulaConfig(id="amperage", formula="state / 120", variables={}),
                # Another attribute formula with state
                FormulaConfig(id="efficiency", formula="state * 0.95", variables={}),
            ],
        )

    async def test_dynamic_dependency_discovery_with_state_attributes(
        self, mock_hass, mock_entity_registry, mock_states, evaluator, sensor_manager, sensor_config_with_state_attributes
    ):
        """Test that dynamic dependency discovery works when attribute formulas use state references."""

        # Set up backing entity state
        mock_states["sensor.backing_power"] = MagicMock(state="1200", attributes={})

        # Create the sensor
        sensor = DynamicSensor(
            hass=mock_hass, config=sensor_config_with_state_attributes, evaluator=evaluator, sensor_manager=sensor_manager
        )
        sensor.hass = mock_hass
        sensor.entity_id = "sensor.test_power_sensor"

        # The key test: Mock the evaluator to simulate the scenario where
        # the dynamic dependency discovery code tries to evaluate attribute formulas
        # This is the code path that was failing with BackingEntityResolutionError

        evaluation_calls = []
        original_evaluate = evaluator.evaluate_formula_with_sensor_config

        def mock_evaluate_formula_with_sensor_config(config, context=None, sensor_config=None):
            evaluation_calls.append(
                {
                    "formula_id": config.id,
                    "formula": config.formula,
                    "context_keys": list(context.keys()) if context else None,
                    "has_state_in_context": "state" in context if context else False,
                }
            )

            # For attribute formulas with state, verify they have state in context
            if config.id in ["amperage", "efficiency"] and "state" in config.formula:
                if not context or "state" not in context:
                    # This would be the BackingEntityResolutionError scenario
                    raise Exception(f"Attribute formula {config.id} missing state in context!")

            # Return mock results
            if config.id == "main":
                return {"success": True, "value": 1200.0, "state": "ok"}
            elif config.id == "amperage":
                return {"success": True, "value": 10.0, "state": "ok"}  # 1200 / 120
            elif config.id == "efficiency":
                return {"success": True, "value": 1140.0, "state": "ok"}  # 1200 * 0.95
            else:
                return {"success": False, "error": "Unknown formula", "state": "unknown"}

        evaluator.evaluate_formula_with_sensor_config = mock_evaluate_formula_with_sensor_config

        # Mock async_write_ha_state to avoid HA lifecycle issues
        with patch.object(sensor, "async_write_ha_state"):
            # This should trigger the dynamic dependency discovery path
            # The key test is that it doesn't raise BackingEntityResolutionError
            await sensor._async_update_sensor()

        # Verify that attribute formulas were evaluated with state in context
        attribute_calls = [call for call in evaluation_calls if call["formula_id"] in ["amperage", "efficiency"]]
        assert len(attribute_calls) >= 2, f"Expected attribute formula calls, got: {evaluation_calls}"

        for call in attribute_calls:
            assert call["has_state_in_context"], f"Attribute formula {call['formula_id']} missing state in context: {call}"

    async def test_dynamic_dependency_discovery_with_failed_main_formula(
        self, mock_hass, mock_entity_registry, mock_states, evaluator, sensor_manager, sensor_config_with_state_attributes
    ):
        """Test dynamic dependency discovery when main formula fails but attributes should still get STATE_UNKNOWN."""

        # Set up backing entity to be unavailable
        mock_states["sensor.backing_power"] = MagicMock(state="unavailable", attributes={})

        # Create the sensor
        sensor = DynamicSensor(
            hass=mock_hass, config=sensor_config_with_state_attributes, evaluator=evaluator, sensor_manager=sensor_manager
        )
        sensor.hass = mock_hass
        sensor.entity_id = "sensor.test_power_sensor"

        # Mock async_write_ha_state to avoid HA lifecycle issues
        with patch.object(sensor, "async_write_ha_state"):
            # This should trigger evaluation where main fails but attributes get STATE_UNKNOWN
            await sensor._async_update_sensor()

        # Main sensor should be unavailable
        assert sensor._attr_native_value is None

        # But attributes should still be evaluated with state = STATE_UNKNOWN
        # The exact behavior depends on how the evaluator handles STATE_UNKNOWN in formulas
        # At minimum, the evaluation should not crash with BackingEntityResolutionError

        # This test primarily ensures no BackingEntityResolutionError is raised
        # which was the original issue with the SPAN panel
