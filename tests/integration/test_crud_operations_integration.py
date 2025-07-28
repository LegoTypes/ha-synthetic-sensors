"""Integration test for CRUD operations on sensor sets with cross-sensor references."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import yaml as yaml_lib

from ha_synthetic_sensors import (
    async_setup_synthetic_sensors,
    StorageManager,
    DataProviderCallback,
)
from ha_synthetic_sensors.config_models import SensorConfig, FormulaConfig


class TestCrudOperationsIntegration:
    """Integration test for CRUD operations with cross-sensor references."""

    @pytest.fixture
    def crud_yaml_fixture_path(self):
        """Path to the CRUD operations test YAML fixture."""
        return "tests/yaml_fixtures/integration_test_crud_operations.yaml"

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback."""
        return Mock()

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"  # Will be slugified for entity IDs
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        return mock_device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    def create_data_provider_callback(self, backing_data: dict[str, any]) -> DataProviderCallback:
        """Create data provider for virtual backing entities."""

        def data_provider(entity_id: str):
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    def create_mock_state(self, state_value: str):
        """Create a mock HA state object."""
        return type("MockState", (), {"state": state_value, "attributes": {}})()

    async def test_crud_operations_with_cross_sensor_references(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        crud_yaml_fixture_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test CRUD operations: initial sensor set, add cross-referencing sensor, delete existing sensor."""

        # 1. Set up virtual backing entity data (NOT referenced in YAML)
        # These are resolved by the package through sensor-to-backing mapping
        backing_data = {
            "virtual_backing.main_power": 1000.0,
            "virtual_backing.secondary_sensor": 500.0,
            "virtual_backing.temp_sensor_to_delete": 20.0,
        }

        # 2. Create data provider for virtual backing entities
        data_provider = self.create_data_provider_callback(backing_data)

        # 3. Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock setup
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            # Use common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # 4. Load initial YAML configuration
            sensor_set_id = "crud_test_set"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="CRUD Test Sensors"
            )

            with open(crud_yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3  # main_power, secondary_sensor, temp_sensor_to_delete

            # 5. Set up synthetic sensors via public API with sensor-to-backing mapping
            # This mapping tells the package how to resolve 'state' tokens to virtual backing entities
            # Sensor keys (from YAML) map to virtual backing entity IDs
            sensor_to_backing_mapping = {
                "main_power": "virtual_backing.main_power",
                "secondary_sensor": "virtual_backing.secondary_sensor",
                "temp_sensor_to_delete": "virtual_backing.temp_sensor_to_delete",
            }

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass  # Change notification logic

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,  # Package resolves 'state' via this mapping
                allow_ha_lookups=True,  # Allow cross-sensor references to HA entities
            )

            # 6. Verify initial setup
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test initial formula evaluation
            await sensor_manager.async_update_sensors()

            # Verify initial sensors - use actual sensor keys from YAML
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3
            sensor_ids = [s.unique_id for s in sensors]
            assert "main_power" in sensor_ids
            assert "secondary_sensor" in sensor_ids
            assert "temp_sensor_to_delete" in sensor_ids

            # 7. CRUD Operation 1: Delete the temporary sensor
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)
            success = await sensor_set.async_remove_sensor("temp_sensor_to_delete")
            assert success is True

            # Verify deletion
            sensors_after_delete = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors_after_delete) == 2
            remaining_ids = [s.unique_id for s in sensors_after_delete]
            assert "temp_sensor_to_delete" not in remaining_ids
            assert "main_power" in remaining_ids
            assert "secondary_sensor" in remaining_ids

            # 8. CRUD Operation 2: Add a new sensor that references the main_power sensor
            # This demonstrates cross-sensor reference (not backing entity reference)
            new_sensor_config = SensorConfig(
                unique_id="power_efficiency",
                name="Power Efficiency",
                entity_id="sensor.test_device_power_efficiency",
                formulas=[
                    FormulaConfig(
                        id="power_efficiency_formula",
                        formula="main_power_result / 2500 * 100",  # Cross-sensor reference
                        variables={
                            "main_power_result": "sensor.test_device_main_power"  # References HA entity ID
                        },
                    )
                ],
                metadata={
                    "unit_of_measurement": "%",
                    "device_class": "power_factor",
                    "state_class": "measurement",
                    "icon": "mdi:gauge-full",
                },
            )

            await sensor_set.async_add_sensor(new_sensor_config)

            # 9. Verify the new sensor was added
            sensors_after_add = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors_after_add) == 3
            final_ids = [s.unique_id for s in sensors_after_add]
            assert "power_efficiency" in final_ids
            assert "main_power" in final_ids
            assert "secondary_sensor" in final_ids

            # 10. Test cross-sensor formula evaluation
            # Add the main_power sensor state to mock_states for cross-sensor reference
            mock_states["sensor.test_device_main_power"] = self.create_mock_state("1100.0")

            # Update sensors to test cross-sensor evaluation
            await sensor_manager.async_update_sensors()

            # Verify the new sensor exists and can be evaluated
            new_sensor = storage_manager.get_sensor("power_efficiency")
            assert new_sensor is not None
            assert new_sensor.unique_id == "power_efficiency"
            assert new_sensor.name == "Power Efficiency"
            assert len(new_sensor.formulas) == 1
            assert "main_power_result" in new_sensor.formulas[0].variables
            assert new_sensor.formulas[0].variables["main_power_result"] == "sensor.test_device_main_power"

            # 11. Test selective updates for virtual backing entities
            changed_entities = {"virtual_backing.main_power"}
            await sensor_manager.async_update_sensors_for_entities(changed_entities)

            # 12. Export YAML after CRUD operations to verify changes
            final_yaml = await sensor_set.async_export_yaml()

            # Verify the exported YAML reflects the CRUD operations
            final_config = yaml_lib.safe_load(final_yaml)

            # Should have 3 sensors (original 3 minus 1 deleted plus 1 added)
            assert len(final_config["sensors"]) == 3

            # Verify deleted sensor is not in export
            assert "temp_sensor_to_delete" not in final_config["sensors"]

            # Verify remaining original sensors are still there
            assert "main_power" in final_config["sensors"]
            assert "secondary_sensor" in final_config["sensors"]

            # Verify new sensor is in export with correct configuration
            assert "power_efficiency" in final_config["sensors"]
            new_sensor_yaml = final_config["sensors"]["power_efficiency"]
            assert new_sensor_yaml["name"] == "Power Efficiency"
            assert new_sensor_yaml["entity_id"] == "sensor.test_device_power_efficiency"

            # The formula is nested under attributes.formula for programmatically added sensors
            assert "formula" in new_sensor_yaml["attributes"]
            formula_config = new_sensor_yaml["attributes"]["formula"]
            assert formula_config["formula"] == "main_power_result / 2500 * 100"
            assert "main_power_result" in formula_config["variables"]
            assert formula_config["variables"]["main_power_result"] == "sensor.test_device_main_power"

            assert new_sensor_yaml["metadata"]["unit_of_measurement"] == "%"
            assert new_sensor_yaml["metadata"]["device_class"] == "power_factor"

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_crud_operations_error_handling(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        crud_yaml_fixture_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test error handling in CRUD operations."""

        # Set up minimal virtual backing entity data
        backing_data = {"virtual_backing.main_power": 1000.0}
        data_provider = self.create_data_provider_callback(backing_data)

        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "crud_error_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="CRUD Error Test"
            )

            with open(crud_yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            sensor_set = storage_manager.get_sensor_set(sensor_set_id)

            # Test removing non-existent sensor
            success = await sensor_set.async_remove_sensor("non_existent_sensor")
            assert success is False

            # Verify original sensors still exist
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_yaml_based_crud_operations(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        crud_yaml_fixture_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test new YAML-based CRUD interface for adding and updating sensors."""

        # Set up virtual backing entity data
        backing_data = {
            "virtual_backing.main_power": 1000.0,
            "virtual_backing.secondary_sensor": 500.0,
            "virtual_backing.temp_sensor_to_delete": 20.0,
            "virtual_backing.new_sensor": 750.0,
        }
        data_provider = self.create_data_provider_callback(backing_data)

        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "yaml_crud_test_set"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="YAML CRUD Test Sensors"
            )

            # Load initial configuration from fixture
            with open(crud_yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            # Parse the fixture YAML to work with it
            fixture_data = yaml_lib.safe_load(yaml_content)

            await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)

            # Verify initial state: 3 sensors from fixture
            initial_sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(initial_sensors) == 3
            initial_unique_ids = {s.unique_id for s in initial_sensors}
            assert "main_power" in initial_unique_ids
            assert "secondary_sensor" in initial_unique_ids
            assert "temp_sensor_to_delete" in initial_unique_ids

            # TEST 1: Add a new sensor using YAML CRUD
            # Create a new sensor definition similar to the fixture format
            new_sensor_key = "new_power_sensor"
            new_sensor_config = {
                "name": "New Power Sensor",
                "entity_id": "sensor.test_device_new_power",
                "formula": "state * 1.2",
                "variables": {"multiplier": 1.2},
                "attributes": {"calculation_type": "enhanced_power", "multiplier_value": 1.2},
                "metadata": {
                    "unit_of_measurement": "W",
                    "device_class": "power",
                    "state_class": "measurement",
                    "icon": "mdi:lightning-bolt",
                },
            }

            # Convert to YAML string with sensor key
            new_sensor_yaml = yaml_lib.dump({new_sensor_key: new_sensor_config}, default_flow_style=False)

            await sensor_set.async_add_sensor_from_yaml(new_sensor_yaml)

            # Verify sensor was added
            sensors_after_add = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors_after_add) == 4

            new_sensor = storage_manager.get_sensor(new_sensor_key)
            assert new_sensor is not None
            assert new_sensor.name == "New Power Sensor"
            assert new_sensor.entity_id == "sensor.test_device_new_power"

            # TEST 2: Update an existing sensor using YAML CRUD
            # Read the original secondary_sensor from fixture and modify it
            original_secondary = fixture_data["sensors"]["secondary_sensor"].copy()

            # Modify the configuration
            updated_secondary = original_secondary.copy()
            updated_secondary["name"] = "Updated Secondary Sensor"
            updated_secondary["formula"] = "state + offset + extra_offset"
            updated_secondary["variables"] = {"offset": 100.0, "extra_offset": 50.0}
            updated_secondary["attributes"] = {
                "calculation_type": "enhanced_addition",
                "offset_value": 150.0,
                "notes": "Updated with YAML CRUD",
            }
            updated_secondary["metadata"]["icon"] = "mdi:gauge-full"

            # Convert to YAML string with sensor key
            update_sensor_yaml = yaml_lib.dump({"secondary_sensor": updated_secondary}, default_flow_style=False)

            success = await sensor_set.async_update_sensor_from_yaml(update_sensor_yaml)
            assert success is True

            # Verify sensor was updated
            updated_sensor = storage_manager.get_sensor("secondary_sensor")
            assert updated_sensor is not None
            assert updated_sensor.name == "Updated Secondary Sensor"
            assert "extra_offset" in updated_sensor.formulas[0].variables
            assert updated_sensor.formulas[0].variables["extra_offset"] == 50.0

            # TEST 3: Export and compare YAML
            # Export the current sensor set configuration
            exported_yaml = sensor_set.export_yaml()
            exported_data = yaml_lib.safe_load(exported_yaml)

            # Verify the exported YAML contains our changes
            assert "new_power_sensor" in exported_data["sensors"]
            assert exported_data["sensors"]["secondary_sensor"]["name"] == "Updated Secondary Sensor"
            assert exported_data["sensors"]["secondary_sensor"]["variables"]["extra_offset"] == 50.0

            # TEST 4: Try to update non-existent sensor
            nonexistent_config = {
                "name": "Non-existent Sensor",
                "entity_id": "sensor.test_device_nonexistent",
                "formula": "state * 2",
            }
            nonexistent_yaml = yaml_lib.dump({"nonexistent_sensor": nonexistent_config}, default_flow_style=False)

            success = await sensor_set.async_update_sensor_from_yaml(nonexistent_yaml)
            assert success is False

            # TEST 5: Try to add duplicate sensor (should fail)
            with pytest.raises(Exception):  # Should raise SyntheticSensorsError
                await sensor_set.async_add_sensor_from_yaml(new_sensor_yaml)

            # Verify final state
            final_sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(final_sensors) == 4  # Still 4 sensors (3 original + 1 added)

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
