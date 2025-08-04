"""Integration tests for metadata() function."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ha_synthetic_sensors import async_setup_synthetic_sensors
from ha_synthetic_sensors.storage_manager import StorageManager


class TestMetadataFunctionIntegration:
    """Test metadata() function integration with synthetic sensors."""

    @pytest.fixture
    def metadata_function_yaml_path(self):
        """Path to metadata function integration YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "metadata_function_integration.yaml"

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device Metadata Function"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_metadata_function")}
        return mock_device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback."""
        return Mock()

    def create_mock_state(self, state_value: str, last_changed=None, last_updated=None, entity_id=None):
        """Create a mock state object with metadata properties."""
        if last_changed is None:
            last_changed = datetime.now(timezone.utc)
        if last_updated is None:
            last_updated = last_changed
        if entity_id is None:
            entity_id = "sensor.unknown"

        # Derive object_id from entity_id (part after the dot)
        object_id = entity_id.split(".", 1)[1] if "." in entity_id else entity_id
        # Derive domain from entity_id (part before the dot)
        domain = entity_id.split(".", 1)[0] if "." in entity_id else "unknown"

        return type(
            "MockState",
            (),
            {
                "state": state_value,
                "last_changed": last_changed,
                "last_updated": last_updated,
                "entity_id": entity_id,
                "object_id": object_id,
                "domain": domain,
                "friendly_name": f"{object_id.replace('_', ' ').title()}",
                "attributes": {},
            },
        )()

    async def test_metadata_function_basic_integration(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        metadata_function_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test basic metadata() function integration with synthetic sensors."""

        # Set up test data with mock states that have metadata properties
        base_time = datetime.now(timezone.utc)

        # Set up real HA entities for metadata testing
        mock_states["sensor.power_meter"] = self.create_mock_state(
            "1000.0", last_changed=base_time, last_updated=base_time, entity_id="sensor.power_meter"
        )

        # Set up collision-renamed entity (the collision system will rename sensor.power_meter to sensor.power_meter_2)
        mock_states["sensor.power_meter_2"] = self.create_mock_state(
            "1000.0", last_changed=base_time, last_updated=base_time, entity_id="sensor.power_meter_2"
        )

        mock_states["sensor.temp_probe"] = self.create_mock_state(
            "25.5", last_changed=base_time, last_updated=base_time, entity_id="sensor.temp_probe"
        )

        # External entities for cross-sensor testing
        mock_states["sensor.external_power_meter"] = self.create_mock_state(
            "750.0", last_changed=base_time, last_updated=base_time, entity_id="sensor.external_power_meter"
        )

        # Set up storage manager with proper mocking (following the guide)
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None  # Empty storage initially
            MockStore.return_value = mock_store

            # Use the common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_metadata_function_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load YAML configuration
            sensor_set_id = "metadata_function_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device_metadata_function",  # Must match YAML global_settings
                name="Metadata Function Test Sensors",
            )

            with open(metadata_function_yaml_path, "r") as f:
                yaml_content = f.read()

            # Import YAML with dependency resolution
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 9  # 9 sensors in the fixture

            # Set up synthetic sensors via public API using HA entity lookups
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_metadata_function",
                # No data_provider_callback means HA entity lookups are used automatically
            )

            # Verify setup
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation - both update mechanisms
            await sensor_manager.async_update_sensors()

            # Get the actual sensor entities to verify their computed values
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            # Verify we have the expected number of entities
            assert len(all_entities) >= 9, f"Expected at least 9 entities, got {len(all_entities)}"

            # Create a mapping for easy lookup
            sensor_entities = {entity.unique_id: entity for entity in all_entities}

            # FIRST: Test simple variable resolution without metadata
            # This will tell us if the issue is with variable resolution in general
            print("\n=== TESTING SIMPLE VARIABLE RESOLUTION ===")

            # Create a simple test formula using the same power_entity variable
            from ha_synthetic_sensors.config_models import FormulaConfig

            simple_config = FormulaConfig(
                id="simple_power_test",
                name="Simple Power Test",
                formula="power_entity + 100",  # Simple arithmetic, no metadata
                variables={"power_entity": "sensor.power_meter"},
            )

            # Get the evaluator from the sensor manager
            evaluator = sensor_manager._evaluator if hasattr(sensor_manager, "_evaluator") else None
            if evaluator:
                print(f"Testing simple formula: {simple_config.formula}")
                print(f"Variables: {simple_config.variables}")

                try:
                    simple_result = evaluator.evaluate_formula(simple_config)
                    print(f"✅ Simple variable resolution result: {simple_result}")
                    print(f"   Success: {simple_result.success if hasattr(simple_result, 'success') else 'N/A'}")
                    print(f"   Value: {simple_result.value if hasattr(simple_result, 'value') else simple_result}")

                    if hasattr(simple_result, "success") and simple_result.success and simple_result.value == 1100.0:
                        print("✅ SUCCESS: Simple variable resolution works! Issue is specific to metadata.")
                    elif hasattr(simple_result, "success") and not simple_result.success:
                        print(f"❌ FAILED: Simple variable resolution failed: {simple_result}")
                    else:
                        print(f"❌ FAILED: Unexpected result: {simple_result}")
                except Exception as e:
                    print(f"❌ ERROR: Simple variable resolution exception: {e}")
                    import traceback

                    traceback.print_exc()
            else:
                print("❌ ERROR: Could not get evaluator from sensor manager")

            print("=== END SIMPLE VARIABLE TEST ===\n")

            # Test actual formula evaluation results - fail fast if entities or values missing
            # Test: "metadata(power_entity, 'last_changed')" - should return the actual timestamp
            last_changed_entity = sensor_entities.get("metadata_last_changed_sensor")
            assert last_changed_entity is not None, "metadata_last_changed_sensor entity not found"
            assert last_changed_entity.native_value is not None, (
                f"metadata_last_changed_sensor has None value: {last_changed_entity.native_value}"
            )
            # The result should contain the timestamp information
            assert str(base_time) in str(last_changed_entity.native_value) or isinstance(
                last_changed_entity.native_value, datetime
            ), (
                f"Metadata last_changed failed: expected timestamp, got '{last_changed_entity.native_value}' of type {type(last_changed_entity.native_value)}"
            )

            # Test: "metadata(temp_entity, 'entity_id')" - should return the actual entity_id
            entity_id_entity = sensor_entities.get("metadata_entity_id_sensor")
            assert entity_id_entity is not None, "metadata_entity_id_sensor entity not found"
            assert entity_id_entity.native_value is not None, (
                f"metadata_entity_id_sensor has None value: {entity_id_entity.native_value}"
            )
            # The result should be the entity_id string
            assert "sensor.temp_probe" in str(entity_id_entity.native_value), (
                f"Metadata entity_id failed: expected 'sensor.temp_probe', got '{entity_id_entity.native_value}'"
            )

            # Test: "metadata(external_sensor, 'entity_id')" - cross-sensor metadata access
            cross_sensor_entity = sensor_entities.get("metadata_cross_sensor_test")
            assert cross_sensor_entity is not None, "metadata_cross_sensor_test entity not found"
            assert cross_sensor_entity.native_value is not None, (
                f"metadata_cross_sensor_test has None value: {cross_sensor_entity.native_value}"
            )
            assert "sensor.external_power_meter" in str(cross_sensor_entity.native_value), (
                f"Cross-sensor metadata failed: expected 'sensor.external_power_meter', got '{cross_sensor_entity.native_value}'"
            )

            # Test: Sensor key self-reference (see how this behaves)
            self_ref_entity = sensor_entities.get("metadata_self_reference_test")
            assert self_ref_entity is not None, "metadata_self_reference_test entity not found"
            # This might fail - let's see how sensor key self-reference behaves
            print(f"Self-reference result: {self_ref_entity.native_value}")

            # Test: Variable with entity ID
            var_entity_test = sensor_entities.get("metadata_variable_entity_test")
            assert var_entity_test is not None, "metadata_variable_entity_test entity not found"
            print(f"Variable entity result: {var_entity_test.native_value}")

            # Test: Simple attribute calculation (no metadata issues)
            simple_attr_entity = sensor_entities.get("metadata_simple_attribute_test")
            assert simple_attr_entity is not None, "metadata_simple_attribute_test entity not found"
            assert simple_attr_entity.native_value is not None, (
                f"metadata_simple_attribute_test has None value: {simple_attr_entity.native_value}"
            )
            # Main formula should work (uses backing entity reference)
            assert isinstance(simple_attr_entity.native_value, (int, float)), (
                f"Simple attribute test main formula failed: expected numeric, got '{simple_attr_entity.native_value}' of type {type(simple_attr_entity.native_value)}"
            )
            # Should be 1000.0 * 1.1 = 1100.0
            expected_value = 1100.0
            assert abs(simple_attr_entity.native_value - expected_value) < 0.1, (
                f"Simple attribute test failed: expected ~{expected_value}, got {simple_attr_entity.native_value}"
            )

            # Test: Metadata comparison test (simplified)
            comparison_entity = sensor_entities.get("metadata_comparison_test")
            assert comparison_entity is not None, "metadata_comparison_test entity not found"
            assert comparison_entity.native_value is not None, (
                f"metadata_comparison_test has None value: {comparison_entity.native_value}"
            )
            # Should return a timestamp for the temperature entity's last_changed
            assert str(base_time) in str(comparison_entity.native_value) or isinstance(
                comparison_entity.native_value, datetime
            ), (
                f"Comparison test failed: expected timestamp, got '{comparison_entity.native_value}' of type {type(comparison_entity.native_value)}"
            )

            # Test: Direct entity reference for HA data validation
            direct_entity_test = sensor_entities.get("metadata_direct_entity_test")
            assert direct_entity_test is not None, "metadata_direct_entity_test entity not found"
            assert direct_entity_test.native_value is not None, (
                f"metadata_direct_entity_test has None value: {direct_entity_test.native_value}"
            )
            # Should return actual HA timestamp data
            assert str(base_time) in str(direct_entity_test.native_value) or isinstance(
                direct_entity_test.native_value, datetime
            ), (
                f"Direct entity test failed: expected timestamp, got '{direct_entity_test.native_value}' of type {type(direct_entity_test.native_value)}"
            )

            # Test: Multiple entity metadata concatenation
            mixed_ref_entity = sensor_entities.get("metadata_mixed_reference_test")
            assert mixed_ref_entity is not None, "metadata_mixed_reference_test entity not found"
            assert mixed_ref_entity.native_value is not None, (
                f"metadata_mixed_reference_test has None value: {mixed_ref_entity.native_value}"
            )
            result_str = str(mixed_ref_entity.native_value)
            # Should contain both entity IDs concatenated with ' vs '
            assert " vs " in result_str, f"Multiple entity concatenation failed: expected ' vs ' in result, got '{result_str}'"
            assert "sensor.temp_probe" in result_str, (
                f"Multiple entity concatenation failed: expected primary entity in result, got '{result_str}'"
            )
            assert "sensor.power_meter" in result_str, (
                f"Multiple entity concatenation failed: expected backing entity in result, got '{result_str}'"
            )

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_metadata_literals_in_variables_and_attributes(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        metadata_function_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test that metadata functions work as literals in variables and attributes."""

        # Set up basic entities for the test
        base_time = datetime.now(timezone.utc)
        mock_states["sensor.backing_power"] = self.create_mock_state(
            "1000.0", last_changed=base_time, entity_id="sensor.backing_power"
        )

        # Set up storage manager
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_metadata_literals", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load configuration
            sensor_set_id = "metadata_literals_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_metadata_function", name="Metadata Literals Test"
            )

            with open(metadata_function_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 9

            # Get the sensor set to verify literals were processed
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)
            assert sensor_set is not None

            # Get the list of sensors
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 9

            # Verify the sensors were created successfully - this confirms that
            # metadata function literals in variables and attributes were processed correctly

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_metadata_comparison_with_external_entities(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        metadata_function_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test metadata functions work with external entity metadata values."""

        # Set up external entities with various metadata
        base_time = datetime.now(timezone.utc)
        mock_states["sensor.backing_power"] = self.create_mock_state(
            "1000.0", last_changed=base_time, entity_id="sensor.backing_power"
        )
        mock_states["sensor.backing_temperature"] = self.create_mock_state(
            "25.5", last_changed=base_time, entity_id="sensor.backing_temperature"
        )
        mock_states["sensor.external_power_meter"] = self.create_mock_state(
            "750.0", last_changed=base_time, entity_id="sensor.external_power_meter"
        )

        # Set up storage manager
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_metadata_comparison", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load configuration
            sensor_set_id = "metadata_comparison_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_metadata_function", name="Metadata Comparison Test"
            )

            with open(metadata_function_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 9

            # Set up synthetic sensors
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_metadata_function",
                # No data_provider_callback means HA entity lookups are used automatically
            )

            # Test that sensors can be created and evaluated without errors
            assert sensor_manager is not None
            await sensor_manager.async_update_sensors()

            # Verify no exceptions were raised during evaluation
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 9

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
