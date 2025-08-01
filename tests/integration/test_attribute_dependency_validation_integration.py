"""Integration tests for attribute dependency validation behavior.

Tests the new attribute dependency validation features including:
- Cross-attribute references and dependency ordering
- Circular dependency detection
- Variable scoping and shadowing detection
- Literal attribute references
- Variable inheritance from sensor to attributes
"""

import pytest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.exceptions import ConfigEntryError
from ha_synthetic_sensors import (
    async_setup_synthetic_sensors,
    StorageManager,
    DataProviderCallback,
)


class TestAttributeDependencyValidationIntegration:
    """Integration tests for attribute dependency validation."""

    @pytest.fixture
    def mock_async_add_entities(self) -> Mock:
        """Mock the async_add_entities callback."""
        return Mock()

    @pytest.fixture
    def mock_device_entry(self) -> Mock:
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        return mock_device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry: Mock) -> Mock:
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    @pytest.fixture
    def positive_yaml_fixture_path(self) -> Path:
        """Path to positive test cases YAML fixture."""
        return Path(__file__).parent.parent / "yaml_fixtures" / "integration" / "attribute_dependency_validation.yaml"

    @pytest.fixture
    def negative_yaml_fixture_path(self) -> Path:
        """Path to negative test cases YAML fixture."""
        return Path(__file__).parent.parent / "yaml_fixtures" / "integration" / "attribute_dependency_validation_negative.yaml"

    def create_data_provider_callback(self, backing_data: dict[str, Any]) -> DataProviderCallback:
        """Create a data provider callback for virtual backing entities."""

        def data_provider(entity_id: str) -> dict[str, Any]:
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    async def test_valid_attribute_dependencies_load_and_validate(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        positive_yaml_fixture_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ) -> None:
        """Test that valid attribute dependencies load and validate correctly."""

        # Set up test data for referenced entities
        backing_data = {
            "sensor.grid_meter": 1000.0,
            "sensor.solar_inverter": 500.0,
            "sensor.primary_meter": 800.0,
            "sensor.main_power": 1200.0,
        }

        # Add global variable entities to mock states
        mock_states["sensor.efficiency_meter"] = type("MockState", (), {"state": "0.95", "attributes": {}})()

        mock_states["sensor.tax_rate"] = type("MockState", (), {"state": "0.08", "attributes": {}})()

        data_provider = self.create_data_provider_callback(backing_data)

        # Set up storage manager with proper mocking
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

            # Load YAML configuration
            sensor_set_id = "attr_dependency_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Attribute Dependency Test Sensors"
            )

            with open(positive_yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            # Import YAML - should succeed without validation errors
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3  # power_analysis_sensor, inheritance_test_sensor, dependency_chain_sensor

            # Set up synthetic sensors via public API
            sensor_to_backing_mapping = {
                "power_analysis_sensor": "sensor.grid_meter",
                "inheritance_test_sensor": "sensor.primary_meter",
                "dependency_chain_sensor": "sensor.main_power",
            }

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass  # noqa: ARG001

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Verify sensors were created successfully
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation
            await sensor_manager.async_update_sensors_for_entities({"sensor.grid_meter"})
            await sensor_manager.async_update_sensors()

            # Verify results
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_circular_dependency_detection(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        negative_yaml_fixture_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ) -> None:
        """Test that circular dependencies in attributes are detected and rejected."""

        # Set up minimal backing data
        backing_data = {
            "sensor.test_power": 1000.0,
        }

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

            sensor_set_id = "circular_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Circular Dependency Test"
            )

            with open(negative_yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            # Import should fail due to circular dependency
            with pytest.raises(ConfigEntryError, match="Circular dependency detected in attributes"):
                await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_variable_shadowing_detection(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ) -> None:
        """Test that variable shadowing is detected and rejected."""

        # Create YAML with variable shadowing
        yaml_content = """
version: "1.0"

global_settings:
  device_identifier: "test_device_123"

sensors:
  shadowing_test:
    name: "Variable Shadowing Test"
    formula: "sensor.test_power"
    variables: {}
    attributes:
      voltage: 240  # literal attribute
      power_calc:
        formula: "voltage * current"
        variables:
          voltage: 230  # SHADOWS literal attribute
          current: "sensor.current_meter"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
"""

        backing_data = {"sensor.test_power": 1000.0}
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

            sensor_set_id = "shadowing_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Variable Shadowing Test"
            )

            # Import should fail due to variable shadowing
            with pytest.raises(ConfigEntryError, match="has a naming collision with literal attribute"):
                await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_undefined_variable_detection(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ) -> None:
        """Test that undefined variables in attribute formulas are detected."""

        # Create YAML with undefined variables
        yaml_content = """
version: "1.0"

global_settings:
  device_identifier: "test_device_123"

sensors:
  undefined_test:
    name: "Undefined Variable Test"
    formula: "sensor.test_power"
    variables: {}
    attributes:
      broken_calc:
        formula: "undefined_var * missing_attr"  # Both undefined
        variables:
          defined_var: 100  # This is defined
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
"""

        backing_data = {"sensor.test_power": 1000.0}
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

            sensor_set_id = "undefined_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Undefined Variable Test"
            )

            # Import should fail due to undefined variables
            with pytest.raises(ConfigEntryError, match="Potential undefined variable"):
                await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_literal_attribute_references(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ) -> None:
        """Test that formulas can reference literal attributes without redefinition."""

        # Create YAML that references literal attributes
        yaml_content = """
version: "1.0"

global_settings:
  device_identifier: "test_device_123"

sensors:
  literal_ref_test:
    name: "Literal Attribute Reference Test"
    formula: "sensor.test_power"
    variables: {}
    attributes:
      voltage: 240  # literal attribute
      max_capacity: 5000.5  # literal attribute
      efficiency_calc:
        formula: "state / max_capacity * voltage"  # References both literals
        variables: {}  # No need to redefine literals
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
"""

        backing_data = {"sensor.test_power": 1000.0}
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

            sensor_set_id = "literal_ref_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Literal Reference Test"
            )

            # Import should succeed - formulas can reference literal attributes
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1

            # Set up and test the sensor
            sensor_to_backing_mapping = {"literal_ref_test": "sensor.test_power"}

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass  # noqa: ARG001

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
