"""Integration tests for state token example YAML configuration and backing entity behavior."""

import pytest
import yaml
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.exceptions import BackingEntityResolutionError, SensorMappingError
from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager


class TestStateTokenExample:
    """Test the state token example YAML configuration and backing entity behavior."""

    @pytest.fixture
    def config_manager(self, mock_hass, mock_entity_registry, mock_states):
        """Create a config manager with mock HA."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def state_token_example_yaml(self, load_yaml_fixture):
        """Load the state token example YAML fixture."""
        return load_yaml_fixture("state_token_example")

    def test_state_token_example_loads_correctly(self, config_manager, state_token_example_yaml):
        """Test that the state token example YAML loads without errors."""
        # Validate the YAML data
        validation_result = config_manager.validate_yaml_data(state_token_example_yaml)
        assert validation_result["valid"], (
            f"Configuration validation failed: {validation_result.get('errors', 'Unknown error')}"
        )

        # Load the config from the validated data
        config = config_manager.load_from_dict(state_token_example_yaml)

        # Verify all sensors are loaded
        assert len(config.sensors) == 4

        # Check that the test_power_with_processing sensor is present
        sensor_names = [s.name for s in config.sensors]
        assert "Processed Power" in sensor_names

        # Find the test_power_with_processing sensor
        processed_sensor = next(s for s in config.sensors if s.unique_id == "test_power_with_processing")
        assert processed_sensor.unique_id == "test_power_with_processing"
        assert processed_sensor.entity_id == "sensor.raw_power"

    async def test_state_token_in_main_formula_and_attributes(
        self, mock_hass, mock_entity_registry, mock_states, state_token_example_yaml, mock_config_entry, mock_async_add_entities
    ):
        """Test that state token works correctly in both main formula and attributes using public API."""
        # Set up virtual backing entity data
        backing_data = {
            "sensor.raw_power": 1000.0  # Virtual backing entity for test_power_with_processing sensor
        }

        # Create data provider for virtual backing entities
        def create_data_provider_callback(backing_data: dict[str, any]):
            def data_provider(entity_id: str):
                return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

            return data_provider

        data_provider = create_data_provider_callback(backing_data)

        # Create storage manager using public API with mocked Store
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            mock_device_registry = Mock()
            mock_device_registry.devices = Mock()
            mock_device_registry.async_get_device.return_value = None
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set and load YAML configuration
            sensor_set_id = "state_token_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test-device-001",  # Must match YAML global_settings
                name="State Token Test Sensors",
            )

            # Convert dict to YAML string for import
            import yaml

            yaml_content = yaml.dump(state_token_example_yaml)

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4  # Expected number of sensors in state_token_example.yaml

            # Create sensor-to-backing mapping for 'state' token resolution
            sensor_to_backing_mapping = {"test_power_with_processing": "sensor.raw_power"}

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass  # Change notification logic

            # Use public API to set up synthetic sensors
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Verify sensors were created
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Exercise formula evaluation through public API
            await sensor_manager.async_update_sensors()

            # Get the created entities to verify results
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            # Find the test_power_with_processing sensor
            processed_power_sensor = None
            for entity in all_entities:
                if hasattr(entity, "_config") and entity._config.unique_id == "test_power_with_processing":
                    processed_power_sensor = entity
                    break

            # Verify main formula evaluation: state * 1.1 = 1000 * 1.1 = 1100
            assert processed_power_sensor is not None, (
                f"test_power_with_processing sensor not found. Available entities: "
                f"{[getattr(e, '_config', type('', (), {'unique_id': 'unknown'})).unique_id for e in all_entities]}"
            )

            expected_main_value = 1100.0  # 1000.0 * 1.1
            actual_main_value = (
                float(processed_power_sensor.native_value) if processed_power_sensor.native_value is not None else None
            )
            assert actual_main_value == expected_main_value, (
                f"Main formula calculation wrong: expected {expected_main_value}, got {actual_main_value}"
            )

            # Verify attribute formula evaluation: state / 240 = 1100 / 240 = 4.583...
            # The amperage attribute should use the main sensor's result (1100) not the backing entity (1000)
            amperage_attr = processed_power_sensor.extra_state_attributes.get("amperage")
            if amperage_attr is not None:
                expected_amperage = 4.583  # 1100 / 240
                actual_amperage = float(amperage_attr)
                assert abs(actual_amperage - expected_amperage) < 0.001, (
                    f"Amperage attribute calculation wrong: expected {expected_amperage}, got {actual_amperage}"
                )

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_state_token_main_formula_with_self_reference(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
        state_token_example_yaml,
    ):
        """Test that state token main formula works with self-reference to sensor's own HA state."""
        # Set up mock state for the sensor itself (self-reference case)
        # The sensor's entity_id is sensor.raw_power (from YAML config)
        mock_states["sensor.raw_power"] = type(
            "MockState",
            (),
            {
                "state": "100",  # The sensor's own state
                "attributes": {},
                "entity_id": "sensor.raw_power",
            },
        )()

        # Use public API to set up synthetic sensors
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            # Use the common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "test_self_reference"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_state_token", name="Test Self Reference Sensors"
            )

            # Load YAML content (convert dict to YAML string)
            yaml_content = yaml.dump(state_token_example_yaml)
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4  # Should import 4 sensors from state_token_example.yaml

            # Set up synthetic sensors via public API
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                sensor_set_id=sensor_set_id,
            )

            # Verify sensor manager was created
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Exercise formula evaluation through public API
            await sensor_manager.async_update_sensors()

            # Get all entities from the registry
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            # Set hass attribute on all entities to prevent warnings
            for entity in all_entities:
                entity.hass = mock_hass

            # Find the test_power_with_processing sensor
            processing_sensor = None
            for entity in all_entities:
                if hasattr(entity, "_config") and entity._config.unique_id == "test_power_with_processing":
                    processing_sensor = entity
                    break

            # Verify sensor was created and has expected value
            assert processing_sensor is not None, (
                f"test_power_with_processing sensor not found. Available entities: "
                f"{[getattr(e, '_config', type('', (), {'unique_id': 'unknown'})).unique_id for e in all_entities]}"
            )

            expected_value = 110.0  # 100 * 1.1 (self-reference)
            actual_value = float(processing_sensor.native_value) if processing_sensor.native_value is not None else None
            assert actual_value is not None, "Sensor value should not be None for self-reference"
            assert abs(actual_value - expected_value) < 0.001, (
                f"Self-reference calculation wrong: expected {expected_value}, got {actual_value}"
            )

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    def test_state_token_example_all_sensors_have_correct_formulas(self, config_manager, state_token_example_yaml):
        """Test that all sensors in the example have the expected formulas."""
        # Validate and load the config
        validation_result = config_manager.validate_yaml_data(state_token_example_yaml)
        assert validation_result["valid"]
        config = config_manager.load_from_dict(state_token_example_yaml)

        # Check each sensor has the expected formulas
        for sensor in config.sensors:
            if sensor.unique_id == "test_current_power":
                assert len(sensor.formulas) == 2  # 1 main + 1 formula attribute (voltage is literal in main)
                main_formula = next(f for f in sensor.formulas if f.id == "test_current_power")
                amperage_formula = next(f for f in sensor.formulas if f.id == "test_current_power_amperage")
                assert main_formula.formula == "state"  # Main formula - references backing entity
                assert (
                    "voltage" in main_formula.attributes and main_formula.attributes["voltage"] == 240
                )  # Literal voltage in main formula
                assert amperage_formula.formula == "state / 240"  # Amperage attribute
            elif sensor.unique_id == "test_feed_through_power":
                assert len(sensor.formulas) == 2  # 1 main + 1 formula attribute (voltage is literal in main)
                main_formula = next(f for f in sensor.formulas if f.id == "test_feed_through_power")
                amperage_formula = next(f for f in sensor.formulas if f.id == "test_feed_through_power_amperage")
                assert main_formula.formula == "state"  # Main formula - references backing entity
                assert (
                    "voltage" in main_formula.attributes and main_formula.attributes["voltage"] == 240
                )  # Literal voltage in main formula
                assert amperage_formula.formula == "state / 240"  # Amperage attribute
            elif sensor.unique_id == "test_energy_consumed":
                assert len(sensor.formulas) == 1  # 1 main only (voltage is literal in main)
                main_formula = sensor.formulas[0]
                assert main_formula.formula == "state"  # Main formula - references backing entity
                assert (
                    "voltage" in main_formula.attributes and main_formula.attributes["voltage"] == 240
                )  # Literal voltage in main formula
            elif sensor.unique_id == "test_power_with_processing":
                assert len(sensor.formulas) == 3  # 1 main + 2 attribute formulas
                assert sensor.formulas[0].formula == "state * 1.1"  # Main formula with processing
                assert sensor.formulas[1].formula == "state / 240"  # Amperage attribute
                assert sensor.formulas[2].formula == "state / (state / 1.1) * 100"  # Efficiency attribute

    async def test_backing_entity_state_token_behavior(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
        state_token_example_yaml,
    ):
        """Test that state token in main formula correctly references backing entity."""
        # Set up virtual backing entity data
        backing_data = {"sensor.raw_power": 500.0}

        # Create data provider for virtual backing entities
        def create_data_provider_callback(backing_data: dict[str, any]):
            def data_provider(entity_id: str):
                return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

            return data_provider

        data_provider = create_data_provider_callback(backing_data)

        # Use public API to set up synthetic sensors
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            # Use the common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "test_backing_entity"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_state_token", name="Test Backing Entity Sensors"
            )

            # Load YAML content (convert dict to YAML string)
            yaml_content = yaml.dump(state_token_example_yaml)
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4  # Should import 4 sensors from state_token_example.yaml

            # Create sensor-to-backing mapping for 'state' token resolution
            sensor_to_backing_mapping = {"test_power_with_processing": "sensor.raw_power"}

            # Set up synthetic sensors via public API with backing entity mapping
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                sensor_set_id=sensor_set_id,
                data_provider_callback=data_provider,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Verify sensor manager was created
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Exercise formula evaluation through public API
            await sensor_manager.async_update_sensors()

            # Get all entities from the registry
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            # Set hass attribute on all entities to prevent warnings
            for entity in all_entities:
                entity.hass = mock_hass

            # Find the test_power_with_processing sensor
            processing_sensor = None
            for entity in all_entities:
                if hasattr(entity, "_config") and entity._config.unique_id == "test_power_with_processing":
                    processing_sensor = entity
                    break

            # Verify sensor was created and has expected value
            assert processing_sensor is not None, (
                f"test_power_with_processing sensor not found. Available entities: "
                f"{[getattr(e, '_config', type('', (), {'unique_id': 'unknown'})).unique_id for e in all_entities]}"
            )

            expected_value = 550.0  # 500.0 * 1.1 (backing entity * processing)
            actual_value = float(processing_sensor.native_value) if processing_sensor.native_value is not None else None
            assert actual_value is not None, "Sensor value should not be None for backing entity"
            assert actual_value == expected_value, (
                f"Backing entity calculation wrong: expected {expected_value}, got {actual_value}"
            )

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_attribute_state_token_uses_main_sensor_result(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
        state_token_example_yaml,
    ):
        """Test that state token in attributes uses the main sensor's calculated result."""
        # Set up virtual backing entity data
        backing_data = {"sensor.raw_power": 500.0}

        # Create data provider for virtual backing entities
        def create_data_provider_callback(backing_data: dict[str, any]):
            def data_provider(entity_id: str):
                return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

            return data_provider

        data_provider = create_data_provider_callback(backing_data)

        # Use public API to set up synthetic sensors
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            # Use the common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "test_attribute_state"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_state_token", name="Test Attribute State Sensors"
            )

            # Load YAML content (convert dict to YAML string)
            yaml_content = yaml.dump(state_token_example_yaml)
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4  # Should import 4 sensors from state_token_example.yaml

            # Create sensor-to-backing mapping for 'state' token resolution
            sensor_to_backing_mapping = {"test_power_with_processing": "sensor.raw_power"}

            # Set up synthetic sensors via public API with backing entity mapping
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                sensor_set_id=sensor_set_id,
                data_provider_callback=data_provider,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Verify sensor manager was created
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Exercise formula evaluation through public API
            await sensor_manager.async_update_sensors()

            # Get all entities from the registry
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            # Set hass attribute on all entities to prevent warnings
            for entity in all_entities:
                entity.hass = mock_hass

            # Find the test_power_with_processing sensor
            processing_sensor = None
            for entity in all_entities:
                if hasattr(entity, "_config") and entity._config.unique_id == "test_power_with_processing":
                    processing_sensor = entity
                    break

            # Verify sensor was created and has expected values
            assert processing_sensor is not None, (
                f"test_power_with_processing sensor not found. Available entities: "
                f"{[getattr(e, '_config', type('', (), {'unique_id': 'unknown'})).unique_id for e in all_entities]}"
            )

            # Main formula: state * 1.1 = 500.0 * 1.1 = 550.0
            expected_main_value = 550.0
            actual_main_value = float(processing_sensor.native_value) if processing_sensor.native_value is not None else None
            assert actual_main_value is not None, "Main sensor value should not be None"
            assert actual_main_value == expected_main_value, (
                f"Main formula calculation wrong: expected {expected_main_value}, got {actual_main_value}"
            )

            # Attribute formula: state / 240 = 550.0 / 240 = 2.291...
            # In attributes, 'state' refers to the main sensor's calculated result (550.0)
            expected_amperage = 550.0 / 240  # ≈ 2.291
            actual_amperage = processing_sensor.extra_state_attributes.get("amperage")
            assert actual_amperage is not None, "Amperage attribute should not be None"
            assert abs(float(actual_amperage) - expected_amperage) < 0.001, (
                f"Attribute calculation wrong: expected {expected_amperage}, got {actual_amperage}"
            )

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_state_token_self_reference_succeeds(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
        state_token_example_yaml,
    ):
        """Test that state token succeeds with self-reference when no backing entity is registered."""
        # Set up mock state for the sensor itself (self-reference case)
        # The sensor's entity_id is sensor.raw_power (from YAML config)
        mock_states["sensor.raw_power"] = type(
            "MockState",
            (),
            {
                "state": "100",  # The sensor's own state
                "attributes": {},
                "entity_id": "sensor.raw_power",
            },
        )()

        # Use public API to set up synthetic sensors (no backing entity mapping)
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            # Use the common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "test_self_reference_succeeds"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device_state_token",
                name="Test Self Reference Success Sensors",
            )

            # Load YAML content (convert dict to YAML string)
            yaml_content = yaml.dump(state_token_example_yaml)
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4  # Should import 4 sensors from state_token_example.yaml

            # Set up synthetic sensors via public API (no backing entity mapping - should use self-reference)
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                sensor_set_id=sensor_set_id,
            )

            # Verify sensor manager was created
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Exercise formula evaluation through public API
            await sensor_manager.async_update_sensors()

            # Get all entities from the registry
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            # Set hass attribute on all entities to prevent warnings
            for entity in all_entities:
                entity.hass = mock_hass

            # Find the test_power_with_processing sensor
            processing_sensor = None
            for entity in all_entities:
                if hasattr(entity, "_config") and entity._config.unique_id == "test_power_with_processing":
                    processing_sensor = entity
                    break

            # Verify sensor was created and has expected value
            assert processing_sensor is not None, (
                f"test_power_with_processing sensor not found. Available entities: "
                f"{[getattr(e, '_config', type('', (), {'unique_id': 'unknown'})).unique_id for e in all_entities]}"
            )

            expected_value = 110.0  # 100 * 1.1 (self-reference)
            actual_value = float(processing_sensor.native_value) if processing_sensor.native_value is not None else None
            assert actual_value is not None, "Sensor value should not be None for self-reference"
            assert abs(actual_value - expected_value) < 0.001, (
                f"Self-reference calculation wrong: expected {expected_value}, got {actual_value}"
            )

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    def test_self_reference_replacement_behavior(self, mock_hass, mock_entity_registry, mock_states, config_manager):
        """Test that self-references in YAML are replaced with state tokens according to design guide."""
        # This test verifies the behavior described in the design guide where:
        # - Self-references (sensor referring to itself) are replaced with 'state' token
        # - Cross-sensor references are replaced with HA entity IDs

        # Create a YAML with self-references (as described in design guide example)
        self_reference_yaml = {
            "version": "1.0",
            "sensors": {
                "base_power_sensor": {
                    "entity_id": "sensor.base_power",
                    "formula": "base_power_sensor * 1.1",  # Self-reference by sensor key
                    "attributes": {
                        "daily_power": {
                            "formula": "base_power_sensor * 24"  # Self-reference in attribute
                        }
                    },
                },
                "efficiency_calc": {
                    "formula": "base_power_sensor * 0.85",  # Cross-sensor reference
                    "attributes": {
                        "power_comparison": {
                            "formula": "efficiency_calc + base_power_sensor"  # Self + cross reference
                        }
                    },
                },
            },
        }

        # Load the configuration
        validation_result = config_manager.validate_yaml_data(self_reference_yaml)
        if not validation_result["valid"]:
            print(f"Validation failed: {validation_result.get('errors', 'Unknown error')}")
        assert validation_result["valid"]
        config = config_manager.load_from_dict(self_reference_yaml)

        # Verify that self-references are properly handled
        # Note: The actual replacement happens during cross-sensor reference resolution
        # This test verifies that the configuration loads correctly

        assert len(config.sensors) == 2

        # Check base_power_sensor
        base_sensor = next(s for s in config.sensors if s.unique_id == "base_power_sensor")
        assert base_sensor.formulas[0].formula == "base_power_sensor * 1.1"  # Original formula preserved

        # Check efficiency_calc
        efficiency_sensor = next(s for s in config.sensors if s.unique_id == "efficiency_calc")
        assert efficiency_sensor.formulas[0].formula == "base_power_sensor * 0.85"  # Cross-reference preserved

        # Note: The actual replacement of self-references with 'state' tokens
        # and cross-references with HA entity IDs happens during the cross-sensor
        # reference resolution phase, which is tested in the cross-sensor reference tests
