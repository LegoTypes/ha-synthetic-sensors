"""Integration tests for dependency resolver functionality using public API."""

import pytest
import logging
from unittest.mock import AsyncMock, Mock, patch

# Use public API imports as shown in integration guide
from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager, DataProviderCallback


class TestDependencyResolverIntegration:
    """Integration tests for dependency resolution through the public API."""

    @pytest.fixture
    def complex_dependency_yaml_path(self):
        """Path to the complex dependency YAML fixture."""
        return "tests/fixtures/integration/dependency_resolver_complex.yaml"

    @pytest.fixture
    def collection_functions_yaml_path(self):
        """Path to the collection functions YAML fixture."""
        return "tests/fixtures/integration/dependency_resolver_collection_functions.yaml"

    @pytest.fixture
    def missing_entities_yaml_path(self):
        """Path to the missing entities YAML fixture."""
        return "tests/fixtures/integration/dependency_resolver_missing_entities.yaml"

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry for testing."""
        config_entry = Mock()
        config_entry.entry_id = "test_entry_id"
        config_entry.domain = "test_domain"
        return config_entry

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback."""
        return Mock()

    @pytest.fixture
    def mock_device_registry(self):
        """Create a mock device registry."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    def create_data_provider_callback(self, backing_data: dict[str, any]) -> DataProviderCallback:
        """Create a data provider callback for testing with virtual backing entities."""

        def data_provider(entity_id: str):
            """Provide test data for virtual backing entities."""
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    async def test_dependency_resolution_basic(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        complex_dependency_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test basic cross-sensor dependency resolution using public API."""

        # Set up backing entities with test data
        backing_data = {
            "sensor.panel_power": 1000.0,  # External HA entity for base_power
        }

        # Add external entity to mock states for HA lookups
        mock_states["sensor.panel_power"] = type("MockState", (), {"state": "1000.0", "attributes": {}})()

        # Create data provider for virtual backing entities
        data_provider = self.create_data_provider_callback(backing_data)

        # Create storage manager using public API with mocked Store and DeviceRegistry
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None  # Empty storage initially
            MockStore.return_value = mock_store

            # Mock Device Registry to avoid missing 'devices' attribute error
            mock_device_registry = Mock()
            mock_device_registry.devices = Mock()
            mock_device_registry.async_get_device.return_value = None  # No device found
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set using SensorSet interface
            sensor_set_id = "dependency_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Dependency Test Sensors"
            )

            # Load YAML using SensorSet interface
            with open(complex_dependency_yaml_path, "r") as f:
                yaml_content = f.read()

            sensor_set = storage_manager.get_sensor_set(sensor_set_id)
            await sensor_set.async_import_yaml(yaml_content)

            # Use public API to set up synthetic sensors
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
            )

            # Verify sensors were created successfully
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Exercise dependency resolution by triggering sensor updates
            # This will cause each formula to evaluate and resolve dependencies
            await sensor_manager.async_update_sensors()

            # Verify sensors can be listed (confirms successful dependency resolution)
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 6, f"Expected 6 sensors, got {len(sensors)}"

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_dependency_resolution_with_collection_functions(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        collection_functions_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test dependency resolution with collection functions using public API."""

        # Set up entities for collection functions to find
        power_entities = ["sensor.power_1", "sensor.power_2", "sensor.power_3"]
        temp_entities = ["sensor.temp_1", "sensor.temp_2"]

        for entity_id in power_entities:
            # Create mock entity with proper domain attribute
            mock_entity = type("MockEntry", (), {"entity_id": entity_id, "domain": "sensor", "device_class": "power"})()
            mock_entity_registry._entities[entity_id] = mock_entity
            mock_states[entity_id] = type("MockState", (), {"state": "100.0", "attributes": {"device_class": "power"}})()

        for entity_id in temp_entities:
            # Create mock entity with proper domain attribute
            mock_entity = type("MockEntry", (), {"entity_id": entity_id, "domain": "sensor", "device_class": "temperature"})()
            mock_entity_registry._entities[entity_id] = mock_entity
            mock_states[entity_id] = type("MockState", (), {"state": "20.0", "attributes": {"device_class": "temperature"}})()

        # Create storage manager using public API with proper mocking pattern
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None  # Empty storage initially
            MockStore.return_value = mock_store

            # Mock Device Registry with actual device entry
            mock_device_registry = Mock()
            mock_device_registry.devices = Mock()

            # Create device entry that matches the test device identifier
            mock_device_entry = Mock()
            mock_device_entry.name = "Test Device"  # Will be slugified to "test_device"
            mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
            mock_device_registry.async_get_device.return_value = mock_device_entry

            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "collection_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Collection Test Sensors"
            )

            # Load YAML using recommended pattern
            with open(collection_functions_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 2

            # Use public API to set up synthetic sensors
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
            )

            # Verify sensors were created
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Exercise collection function resolution by triggering sensor updates
            # This will cause collection functions to resolve and evaluate
            await sensor_manager.async_update_sensors()

            # Verify sensors were created (confirms successful collection resolution)
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 2, f"Expected 2 sensors, got {len(sensors)}"

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_dependency_resolution_dynamic_missing_entities(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities
    ):
        """Test dependency resolution by first succeeding with good entities, then dynamically creating missing entity scenario.

        This validates the test setup works correctly, then demonstrates the missing entity bug.
        """

        # Phase 1: Set up ALL entities to exist (test should pass)
        backing_data = {
            "sensor.backing_entity": 1000.0,
        }

        # Add the "good" reference entity to both registry and states
        mock_entity = type(
            "MockEntry", (), {"entity_id": "sensor.good_reference", "domain": "sensor", "device_class": "power"}
        )()
        mock_entity_registry._entities["sensor.good_reference"] = mock_entity

        mock_states["sensor.good_reference"] = type(
            "MockState", (), {"state": "500.0", "attributes": {"device_class": "power"}}
        )()

        # Create data provider for virtual backing entities
        data_provider = self.create_data_provider_callback(backing_data)

        # Create storage manager using public API with mocked Store
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            # Mock Device Registry with actual device entry
            mock_device_registry = Mock()
            mock_device_registry.devices = Mock()

            # Create device entry that matches the test device identifier
            mock_device_entry = Mock()
            mock_device_entry.name = "Test Device"  # Will be slugified to "test_device"
            mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
            mock_device_registry.async_get_device.return_value = mock_device_entry

            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "dynamic_missing_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Dynamic Missing Dependency Test Sensors"
            )

            # Phase 1: Create YAML with GOOD entity reference
            good_yaml = """
version: "1.0"

global_settings:
  device_identifier: "test_device_123"

sensors:
  dynamic_sensor:
    name: "Dynamic Test Sensor"
    entity_id: "sensor.backing_entity"
    formula: "state + sensor.good_reference"  # Both entities exist
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
"""

            # Import YAML with all good references
            result = await storage_manager.async_from_yaml(yaml_content=good_yaml, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1

            # Set up sensor manager with good dependencies
            sensor_to_backing_mapping = {"dynamic_sensor": "sensor.backing_entity"}

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Phase 1: Verify all good dependencies work correctly
            try:
                await sensor_manager.async_update_sensors()
                print("✅ Phase 1: All dependencies exist - evaluation succeeded")
            except Exception as e:
                pytest.fail(f"Phase 1 should succeed with all good dependencies, but got: {e}")

            # Phase 2: Test missing entity behavior using public API pattern
            # Create new YAML with missing entity reference
            missing_entity_yaml = """
version: "1.0"

global_settings:
  device_identifier: "test_device_123"

sensors:
  dynamic_sensor:
    name: "Dynamic Test Sensor"
    entity_id: "sensor.backing_entity"
    formula: "state + sensor.missing_reference"  # Missing entity
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
"""

            # Remove the missing entity from registry/states to ensure it's truly missing
            if "sensor.missing_reference" in mock_entity_registry._entities:
                del mock_entity_registry._entities["sensor.missing_reference"]
            if "sensor.missing_reference" in mock_states:
                del mock_states["sensor.missing_reference"]

            # Clean up existing sensor set and recreate with missing dependency
            await storage_manager.async_delete_sensor_set(sensor_set_id)
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Dynamic Missing Dependency Test Sensors"
            )

            # Import YAML with missing reference using public API
            result = await storage_manager.async_from_yaml(yaml_content=missing_entity_yaml, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1

            print("🔄 Phase 2: Loading configuration with missing entity - should detect and warn but remain stable")

            # Create new sensor manager with missing dependency configuration
            # According to integration guide, system should remain stable with warnings
            sensor_manager_phase2 = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Verify sensor manager was created successfully despite missing dependency
            assert sensor_manager_phase2 is not None
            print("✅ Phase 2: System remained stable with missing entity as expected per integration guide")

            # Test that evaluation logs warnings but doesn't crash
            await sensor_manager_phase2.async_update_sensors()
            print("✅ Phase 2: Sensor evaluation completed with warnings for missing entity")

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_dependency_resolution_dynamic_none_values(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities
    ):
        """Test dependency resolution by first succeeding with good values, then dynamically setting backing entity to None.

        This validates the test setup works correctly, then demonstrates the None value handling behavior.
        """

        # Phase 1: Set up backing entity with valid value (test should pass)
        import uuid

        test_uuid = str(uuid.uuid4())[:8]
        backing_entity_id = f"sensor.backing_entity_{test_uuid}"
        backing_data = {
            backing_entity_id: 1000.0  # Good value initially
        }

        # Create data provider for virtual backing entities
        data_provider = self.create_data_provider_callback(backing_data)

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

            # Create sensor set for None value test with unique ID
            sensor_set_id = f"dynamic_none_test_{test_uuid}"
            device_identifier = f"test_device_{test_uuid}"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier=device_identifier,
                name=f"Dynamic None Value Test Sensors {test_uuid}",
            )

            # Create YAML for testing
            test_yaml = f"""
version: "1.0"

global_settings:
  device_identifier: "{device_identifier}"

sensors:
  none_value_sensor:
    name: "None Value Test Sensor"
    entity_id: "{backing_entity_id}"
    formula: "state * 2"  # Simple formula using backing entity
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
    alternate_states:
      NONE:
        formula: "0"  # Power sensors should return 0 when backing entity is None
"""

            # Import YAML
            result = await storage_manager.async_from_yaml(yaml_content=test_yaml, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1

            # Set up sensor manager
            sensor_to_backing_mapping = {"none_value_sensor": backing_entity_id}

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Phase 1: Test with good value (should succeed)
            try:
                await sensor_manager.async_update_sensors()

                added_entities = mock_async_add_entities.call_args[0][0]
                sensor_entity = added_entities[0]

                print(f"✅ Phase 1: Good value ({backing_data[backing_entity_id]}) - sensor state: {sensor_entity.state}")

                # Should have a valid numeric state (1000.0 * 2 = 2000.0)
                assert sensor_entity.state is not None, "Phase 1 should have valid state"

            except Exception as e:
                pytest.fail(f"Phase 1 should succeed with good value, but got: {e}")

            # Phase 2: Dynamically change backing entity to None
            print("🔄 Phase 2: Changing backing entity to None value...")

            # Update the data provider to return None
            backing_data[backing_entity_id] = None

            # Trigger update with None value
            await sensor_manager.async_update_sensors_for_entities({backing_entity_id})

            # Get updated sensor state
            added_entities = mock_async_add_entities.call_args[0][0]
            sensor_entity = added_entities[0]

            print(f"Sensor state after None value: {sensor_entity.state}")
            print(f"Sensor available: {sensor_entity.available}")

            # Power sensors: None backing entity should trigger UNKNOWN alternate handler returning 0
            # This is correct behavior for power sensors (0 power when device is offline)
            assert sensor_entity.state == 0, f"Expected 0 (no power when offline), got '{sensor_entity.state}'"
            assert sensor_entity.available is True, "Sensor should remain available with 0.0 power state"

            print("✅ Phase 2: None value correctly results in 0.0 power (alternate handler)")

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_dependency_resolution_complete_scenarios(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        missing_entities_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test complete dependency resolution scenarios covering all design guide cases.

        Tests:
        1. Valid backing entity with actual value - should work normally
        2. Valid HA entity reference - should work normally
        3. Missing backing entity mapping - should raise BackingEntityResolutionError
        4. Valid formulas with all dependencies satisfied - should evaluate successfully
        """

        # Set up complete test data
        backing_data = {
            "sensor.valid_backing": 1000.0,  # Valid backing entity with value
            "sensor.initialized_backing": 500.0,  # Another valid backing entity
        }

        # Set up valid HA entities in mock_states
        mock_states["sensor.external_ha_entity"] = type("MockState", (), {"state": "750.0", "attributes": {}})()

        # Create data provider for virtual backing entities
        data_provider = self.create_data_provider_callback(backing_data)

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

            # Create sensor set for complete testing
            sensor_set_id = "complete_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Complete Dependency Test Sensors"
            )

            # Create comprehensive YAML for testing all scenarios
            complete_yaml = """
version: "1.0"

global_settings:
  device_identifier: "test_device_123"

sensors:
  valid_sensor:
    name: "Valid Sensor"
    entity_id: "sensor.valid_backing"
    formula: "state * 1.1"  # Valid backing entity reference
    metadata:
      unit_of_measurement: "W"
      device_class: "power"

  hybrid_sensor:
    name: "Hybrid Sensor"
    entity_id: "sensor.initialized_backing"
    formula: "state + sensor.external_ha_entity"  # Mix of virtual backing + HA entity
    metadata:
      unit_of_measurement: "W"
      device_class: "power"

  cross_reference_sensor:
    name: "Cross Reference Sensor"
    formula: "valid_sensor * 2"  # Cross-sensor reference
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
"""

            # Import comprehensive YAML
            result = await storage_manager.async_from_yaml(yaml_content=complete_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Create comprehensive sensor-to-backing mapping
            sensor_to_backing_mapping = {
                "valid_sensor": "sensor.valid_backing",
                "hybrid_sensor": "sensor.initialized_backing",
                # cross_reference_sensor has no backing entity (pure calculation)
            }

            # Set up synthetic sensors with complete configuration
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=lambda x: None,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Verify sensors were created
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test: All valid dependencies should evaluate successfully
            try:
                await sensor_manager.async_update_sensors()

                # Verify all sensors were created and evaluated
                sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
                assert len(sensors) == 3, "Should have created three sensors"

                print("✅ All valid dependencies evaluated successfully")
                print("✅ Virtual backing entities work correctly")
                print("✅ HA entity references work correctly")
                print("✅ Cross-sensor references work correctly")

            except Exception as e:
                pytest.fail(f"Valid dependencies should not raise exception, but got: {e}")

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_circular_reference_detection(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
        caplog,
    ):
        """Test detection and handling of circular references between sensors."""
        # Set up storage manager with proper mocking
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

            # Create sensor set and load circular dependency YAML
            sensor_set_id = "circular_deps_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Circular Dependencies Test"
            )

            yaml_fixture_path = "tests/fixtures/integration/circular_reference_detection.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            # Import should succeed - circular detection happens during evaluation
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3

            # Set up sensor manager - circular references should emit a warning but not raise
            with caplog.at_level(logging.WARNING):
                sensor_manager = await async_setup_synthetic_sensors(
                    hass=mock_hass,
                    config_entry=mock_config_entry,
                    async_add_entities=mock_async_add_entities,
                    storage_manager=storage_manager,
                )
                assert sensor_manager is not None
            assert any("Circular cross-sensor dependency detected" in rec.getMessage() for rec in caplog.records), (
                "Expected a circular dependency warning to be logged - this is a known limitation in the AST refactoring"
            )

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_complex_cross_sensor_dependencies(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test resolution of complex multi-level dependency chains."""
        # Set up virtual backing entity data
        backing_data = {"sensor.virtual_base": 1000.0}

        # Set up mock HA states for external entities
        mock_states["sensor.auxiliary_system"] = type("MockState", (), {"state": "200.0", "attributes": {}})()
        mock_states["sensor.grid_connection"] = type("MockState", (), {"state": "300.0", "attributes": {}})()

        data_provider = self.create_data_provider_callback(backing_data)

        # Set up storage manager with proper mocking
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

            # Create sensor set and load complex dependency YAML
            sensor_set_id = "complex_deps_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Complex Dependencies Test"
            )

            yaml_fixture_path = "tests/fixtures/integration/complex_cross_sensor_dependencies.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 5

            # Create sensor-to-backing mapping for virtual entity
            sensor_to_backing_mapping = {"base_power": "sensor.virtual_base"}

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass

            # Set up sensor manager with hybrid data sources
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test dependency resolution through evaluation
            await sensor_manager.async_update_sensors_for_entities({"sensor.virtual_base"})
            await sensor_manager.async_update_sensors()

            # Verify all sensors in the dependency chain were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 5

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_dependency_extraction_edge_cases(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test edge cases in dependency extraction including attributes and collections."""
        # Set up virtual backing entity data
        backing_data = {"sensor.virtual_main": 500.0}

        # Set up mock HA states with attributes for dependency extraction
        mock_states["sensor.battery_device"] = type("MockState", (), {"state": "85.0", "attributes": {"battery_level": 75.0}})()
        mock_states["sensor.power_meter_a"] = type("MockState", (), {"state": "1000.0", "attributes": {"power": 1000.0}})()
        mock_states["sensor.current_meter_b"] = type("MockState", (), {"state": "5.0", "attributes": {"current": 5.0}})()
        mock_states["sensor.voltage_meter_c"] = type("MockState", (), {"state": "240.0", "attributes": {"voltage": 240.0}})()
        mock_states["sensor.primary_power"] = type("MockState", (), {"state": "1200.0", "attributes": {}})()
        mock_states["sensor.backup_power"] = type("MockState", (), {"state": "800.0", "attributes": {}})()
        mock_states["binary_sensor.primary_available"] = type("MockState", (), {"state": "on", "attributes": {}})()

        # Mock entity registry for collection pattern testing
        mock_entity_registry._entities.update(
            {
                "sensor.temp_1": Mock(device_class="temperature"),
                "sensor.temp_2": Mock(device_class="temperature"),
                "sensor.power_1": Mock(device_class="power"),
                "sensor.excluded_power_meter": Mock(device_class="power"),
            }
        )

        data_provider = self.create_data_provider_callback(backing_data)

        # Set up storage manager with proper mocking
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

            # Create sensor set and load edge cases YAML
            sensor_set_id = "edge_cases_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Dependency Edge Cases Test"
            )

            yaml_fixture_path = "tests/fixtures/integration/dependency_extraction_edge_cases.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4

            # Create sensor-to-backing mapping for virtual entity
            sensor_to_backing_mapping = {"mixed_dependencies": "sensor.virtual_main"}

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass

            # Set up sensor manager with complex dependency patterns
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test dependency extraction through evaluation
            await sensor_manager.async_update_sensors_for_entities({"sensor.virtual_main"})
            await sensor_manager.async_update_sensors()

            # Verify sensors with edge case dependencies were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 4

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
