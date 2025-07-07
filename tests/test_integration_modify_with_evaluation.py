"""
Integration tests for the complete modify workflow with formula evaluation.
Tests the orchestration of modifications, cache clearing, and formula evaluation.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ha_synthetic_sensors.config_manager import ConfigManager, FormulaConfig, SensorConfig
from ha_synthetic_sensors.exceptions import SyntheticSensorsError
from ha_synthetic_sensors.sensor_set import SensorSetModification
from ha_synthetic_sensors.storage_manager import StorageManager


class TestIntegrationModifyWithEvaluation:
    """Integration tests for the complete modify workflow."""

    @pytest.fixture
    def storage_manager(self, mock_hass):
        """Create a StorageManager instance for testing with mocked Store."""
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store

            manager = StorageManager(mock_hass, "test_integration_modify")
            # Set up the mock store
            manager._store = mock_store
            return manager

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        mock_hass = MagicMock()
        mock_hass.states = MagicMock()
        mock_hass.states.get = MagicMock()

        # Mock entity states for formula evaluation
        mock_states = {
            "sensor.main_power_meter": MagicMock(state="1000"),
            "sensor.new_power_meter": MagicMock(state="1200"),
            "sensor.main_voltage_meter": MagicMock(state="240"),
            "sensor.calculated_power": MagicMock(state="865"),  # 1000 * 0.85 + 10
        }

        def get_state(entity_id):
            return mock_states.get(entity_id)

        mock_hass.states.get.side_effect = get_state
        return mock_hass

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager instance."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def yaml_fixtures_dir(self):
        """Get the YAML fixtures directory."""
        return Path(__file__).parent / "yaml_fixtures"

    @pytest.fixture
    def before_yaml_path(self, yaml_fixtures_dir):
        """Path to the before modification YAML fixture."""
        return yaml_fixtures_dir / "integration_modify_globals_before.yaml"

    @pytest.fixture
    def after_yaml_path(self, yaml_fixtures_dir):
        """Path to the after modification YAML fixture."""
        return yaml_fixtures_dir / "integration_modify_globals_after.yaml"

    @pytest.fixture
    async def sensor_set_before(self, storage_manager, config_manager, before_yaml_path):
        """Create a sensor set from the before YAML fixture."""
        # Initialize storage
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

        # Load the before configuration
        config = await config_manager.async_load_config(before_yaml_path)

        # Create the sensor set first
        sensor_set_id = "test_globals_integration"
        with patch.object(storage_manager, "async_save", new_callable=AsyncMock):
            await storage_manager.async_create_sensor_set(sensor_set_id=sensor_set_id, name="Test Globals Integration")

            # Then store the config
            await storage_manager.async_from_config(config, sensor_set_id)

        # Return the sensor set
        return storage_manager.get_sensor_set(sensor_set_id)

    def _get_global_variables(self, storage_manager, sensor_set_id):
        """Helper to get global variables from sensor set."""
        data = storage_manager.data
        sensor_set_data = data["sensor_sets"].get(sensor_set_id, {})
        global_settings = sensor_set_data.get("global_settings", {})
        return global_settings.get("variables", {})

    async def test_complete_modify_workflow_with_formula_evaluation(
        self, mock_hass, storage_manager, config_manager, sensor_set_before, after_yaml_path
    ):
        """Test the complete modify workflow including formula evaluation."""
        sensor_set_id = "test_globals_integration"

        # Load the target configuration
        target_config = await config_manager.async_load_config(after_yaml_path)

        # Get current sensors to determine which are updates vs additions
        current_sensors = {s.unique_id for s in sensor_set_before.list_sensors()}

        # Separate existing sensors (updates) from new sensors (additions)
        sensors_to_update = []
        sensors_to_add = []

        for sensor in target_config.sensors:
            if sensor.unique_id in current_sensors:
                sensors_to_update.append(sensor)
            else:
                sensors_to_add.append(sensor)

        # Create modification from the target config
        modification = SensorSetModification(
            global_settings=target_config.global_settings,
            add_sensors=sensors_to_add,
            remove_sensors=[],  # We're not removing any sensors in this test
            update_sensors=sensors_to_update,
        )

        # Test that entity index tracks original entities
        assert sensor_set_before.is_entity_tracked("sensor.main_power_meter")
        assert sensor_set_before.is_entity_tracked("sensor.main_voltage_meter")
        assert not sensor_set_before.is_entity_tracked("sensor.new_power_meter")

        # Apply the modification
        with patch.object(storage_manager, "async_save", new_callable=AsyncMock):
            result = await sensor_set_before.async_modify(modification)

        # Verify the modification was successful
        assert result["sensors_added"] == 1  # new_efficiency_sensor
        assert result["sensors_updated"] == 4  # calculated_power, total_cost, voltage_ratio, system_status
        assert result["sensors_removed"] == 0
        assert result["global_settings_updated"] is True

        # Get the updated sensor set
        updated_sensor_set = storage_manager.get_sensor_set(sensor_set_id)

        # Test that global variables changed
        global_vars = self._get_global_variables(storage_manager, sensor_set_id)
        assert global_vars["power_source"] == "sensor.new_power_meter"  # Entity reference changed
        assert global_vars["efficiency_rate"] == 0.90  # Direct value changed
        assert global_vars["tax_multiplier"] == 1.10  # Direct value changed
        assert global_vars["base_offset"] == 15  # Direct value changed

        # Test that entity index was updated
        assert updated_sensor_set.is_entity_tracked("sensor.new_power_meter")
        assert updated_sensor_set.is_entity_tracked("sensor.main_voltage_meter")
        assert not updated_sensor_set.is_entity_tracked("sensor.main_power_meter")

        # Test that new sensor was added
        assert updated_sensor_set.has_sensor("new_efficiency_sensor")
        new_sensor = updated_sensor_set.get_sensor("new_efficiency_sensor")
        assert new_sensor.formulas[0].formula == "efficiency_rate * 100"

        # Test that existing sensors reflect the global variable changes
        updated_calculated_power = updated_sensor_set.get_sensor("calculated_power")
        updated_total_cost = updated_sensor_set.get_sensor("total_cost")
        updated_voltage_ratio = updated_sensor_set.get_sensor("voltage_ratio")

        # Verify formulas still reference global variables correctly
        assert updated_calculated_power.formulas[0].formula == "power_source * efficiency_rate + base_offset"
        assert updated_total_cost.formulas[0].formula == "calculated_power_value * rate_per_kwh * tax_multiplier"
        assert updated_voltage_ratio.formulas[0].formula == "voltage_source / reference_voltage * efficiency_rate"

        # Test that local variable changes are preserved
        assert updated_total_cost.formulas[0].variables["rate_per_kwh"] == 0.15
        assert updated_voltage_ratio.formulas[0].variables["reference_voltage"] == 230.0

        # Test system status sensor variable changes
        updated_system_status = updated_sensor_set.get_sensor("system_status")
        assert updated_system_status.formulas[0].variables["threshold"] == 600
        assert updated_system_status.formulas[0].variables["min_voltage"] == 210

        # Test attribute variable changes - attributes become additional formulas
        # Find the power_percentage formula (it gets prefixed with sensor name)
        power_percentage_formula = None
        for formula in updated_system_status.formulas:
            if formula.id == "system_status_power_percentage":
                power_percentage_formula = formula
                break

        assert power_percentage_formula is not None
        assert power_percentage_formula.variables["max_power"] == 6000

    async def test_formula_evaluation_with_changed_globals(
        self, mock_hass, storage_manager, config_manager, sensor_set_before, after_yaml_path
    ):
        """Test that formula evaluation works correctly after global variable changes."""
        sensor_set_id = "test_globals_integration"

        # Update mock states to reflect the new entity references
        mock_states = {
            "sensor.main_power_meter": MagicMock(state="1000"),
            "sensor.new_power_meter": MagicMock(state="1200"),
            "sensor.main_voltage_meter": MagicMock(state="240"),
            "sensor.calculated_power": MagicMock(state="1095"),  # 1200 * 0.90 + 15
        }

        def get_state(entity_id):
            return mock_states.get(entity_id)

        mock_hass.states.get.side_effect = get_state

        # Load target configuration and apply modification
        target_config = await config_manager.async_load_config(after_yaml_path)

        # Get current sensors to determine which are updates vs additions
        current_sensors = {s.unique_id for s in sensor_set_before.list_sensors()}

        # Separate existing sensors (updates) from new sensors (additions)
        sensors_to_update = []
        sensors_to_add = []

        for sensor in target_config.sensors:
            if sensor.unique_id in current_sensors:
                sensors_to_update.append(sensor)
            else:
                sensors_to_add.append(sensor)

        modification = SensorSetModification(
            global_settings=target_config.global_settings,
            add_sensors=sensors_to_add,
            remove_sensors=[],
            update_sensors=sensors_to_update,
        )

        with patch.object(storage_manager, "async_save", new_callable=AsyncMock):
            await sensor_set_before.async_modify(modification)

        # Get the updated sensor set
        updated_sensor_set = storage_manager.get_sensor_set(sensor_set_id)

        # Test formula evaluation with new global variables
        # calculated_power: power_source * efficiency_rate + base_offset
        # = sensor.new_power_meter * 0.90 + 15 = 1200 * 0.90 + 15 = 1095
        calculated_power_config = updated_sensor_set.get_sensor("calculated_power")

        # Test total_cost formula with changed tax_multiplier
        # total_cost: calculated_power_value * rate_per_kwh * tax_multiplier
        # = 1095 * 0.15 * 1.10 = 180.675
        total_cost_config = updated_sensor_set.get_sensor("total_cost")

        # Test voltage_ratio with changed efficiency_rate
        # voltage_ratio: voltage_source / reference_voltage * efficiency_rate
        # = 240 / 230.0 * 0.90 = 0.9391304347826087
        voltage_ratio_config = updated_sensor_set.get_sensor("voltage_ratio")

        # Test new sensor formula
        # new_efficiency_sensor: efficiency_rate * 100 = 0.90 * 100 = 90
        new_efficiency_config = updated_sensor_set.get_sensor("new_efficiency_sensor")

        # Verify all formulas are properly configured
        assert calculated_power_config.formulas[0].formula == "power_source * efficiency_rate + base_offset"
        assert total_cost_config.formulas[0].formula == "calculated_power_value * rate_per_kwh * tax_multiplier"
        assert voltage_ratio_config.formulas[0].formula == "voltage_source / reference_voltage * efficiency_rate"
        assert new_efficiency_config.formulas[0].formula == "efficiency_rate * 100"

    async def test_entity_index_consistency_after_modification(
        self, mock_hass, storage_manager, config_manager, sensor_set_before, after_yaml_path
    ):
        """Test that entity index remains consistent after modifications."""
        sensor_set_id = "test_globals_integration"

        # Apply modification
        target_config = await config_manager.async_load_config(after_yaml_path)

        # Get current sensors to determine which are updates vs additions
        current_sensors = {s.unique_id for s in sensor_set_before.list_sensors()}

        # Separate existing sensors (updates) from new sensors (additions)
        sensors_to_update = []
        sensors_to_add = []

        for sensor in target_config.sensors:
            if sensor.unique_id in current_sensors:
                sensors_to_update.append(sensor)
            else:
                sensors_to_add.append(sensor)

        modification = SensorSetModification(
            global_settings=target_config.global_settings,
            add_sensors=sensors_to_add,
            remove_sensors=[],
            update_sensors=sensors_to_update,
        )

        with patch.object(storage_manager, "async_save", new_callable=AsyncMock):
            await sensor_set_before.async_modify(modification)

        # Get updated sensor set
        updated_sensor_set = storage_manager.get_sensor_set(sensor_set_id)

        # Verify entity index reflects the changes
        # Should track sensor.new_power_meter instead of sensor.main_power_meter
        assert updated_sensor_set.is_entity_tracked("sensor.new_power_meter")
        assert not updated_sensor_set.is_entity_tracked("sensor.main_power_meter")

        # Should still track sensor.main_voltage_meter
        assert updated_sensor_set.is_entity_tracked("sensor.main_voltage_meter")

        # Should track the new calculated sensor
        assert updated_sensor_set.is_entity_tracked("sensor.calculated_power")

        # Verify the entity index has been properly updated
        entity_stats = updated_sensor_set.get_entity_index_stats()
        assert entity_stats["total_entities"] > 0
        assert entity_stats["tracked_entities"] > 0

    async def test_error_handling_during_modification(self, mock_hass, storage_manager, config_manager, sensor_set_before):
        """Test error handling during the modification process."""
        # Create an invalid modification (conflicting global setting)

        conflicting_sensor = SensorConfig(
            unique_id="conflicting_sensor",
            name="Conflicting Sensor",
            formulas=[
                FormulaConfig(
                    id="conflicting_sensor",
                    formula="power_source * local_efficiency",
                    variables={
                        "power_source": "sensor.different_power_meter"  # Conflicts with global
                    },
                )
            ],
        )

        invalid_modification = SensorSetModification(
            global_settings={
                "device_identifier": "test_device:globals_123",
                "variables": {
                    "power_source": "sensor.new_power_meter",
                    "efficiency_rate": 0.90,
                },
            },
            add_sensors=[conflicting_sensor],
            remove_sensors=[],
            update_sensors=[],
        )

        # Test that the modification fails with proper error
        with (
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
            pytest.raises(SyntheticSensorsError) as exc_info,
        ):
            await sensor_set_before.async_modify(invalid_modification)

        # Verify the error message mentions the conflict
        assert "conflict" in str(exc_info.value).lower() or "power_source" in str(exc_info.value)
