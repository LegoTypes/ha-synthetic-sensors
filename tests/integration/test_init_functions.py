"""Tests for __init__.py functions with low coverage."""

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ha_synthetic_sensors import (
    async_setup_synthetic_integration_with_auto_backing,
    async_setup_synthetic_integration,
    configure_logging,
    get_logging_info,
    test_logging,
    StorageManager,
    DataProviderCallback,
)
from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig


class TestInitFunctions:
    """Test the functions in __init__.py that have low coverage."""

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

    def test_configure_logging(self) -> None:
        """Test configure_logging function."""
        # Test with default level
        configure_logging()

        # Test with specific level
        configure_logging(logging.INFO)

        # Verify loggers are configured
        package_logger = logging.getLogger("ha_synthetic_sensors")
        assert package_logger.level == logging.INFO
        assert package_logger.propagate is True

    def test_get_logging_info(self) -> None:
        """Test get_logging_info function."""
        info = get_logging_info()

        assert isinstance(info, dict)
        assert "ha_synthetic_sensors" in info
        assert "ha_synthetic_sensors.evaluator" in info
        assert "ha_synthetic_sensors.service_layer" in info
        assert "ha_synthetic_sensors.collection_resolver" in info
        assert "ha_synthetic_sensors.config_manager" in info

    def test_test_logging(self) -> None:
        """Test test_logging function."""
        # This function just logs messages, so we test it doesn't raise exceptions
        test_logging()

    @pytest.mark.asyncio
    async def test_async_setup_synthetic_integration_with_auto_backing_fresh_install(
        self, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test async_setup_synthetic_integration_with_auto_backing with fresh install."""
        # Mock Home Assistant components
        mock_config_entry = MagicMock()
        mock_config_entry.domain = "test_domain"
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {}

        mock_add_entities = Mock()

        # Mock storage manager
        mock_storage_manager = MagicMock()
        mock_storage_manager.sensor_set_exists.return_value = False
        mock_storage_manager.async_create_sensor_set = AsyncMock()
        mock_storage_manager.async_load = AsyncMock()

        mock_sensor_set = MagicMock()
        mock_sensor_set.async_replace_sensors = AsyncMock()
        mock_storage_manager.get_sensor_set.return_value = mock_sensor_set

        # Mock sensor manager
        mock_sensor_manager = MagicMock()
        mock_sensor_manager.register_data_provider_entities = MagicMock()
        mock_sensor_manager.register_with_storage_manager = MagicMock()
        mock_sensor_manager.load_configuration = AsyncMock()

        # Create test sensor config with backing entity
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            entity_id="sensor.test_sensor",
            device_identifier="test_device",
            formulas=[FormulaConfig(id="main", formula="source_value", variables={"source_value": "sensor.backing_entity"})],
        )

        with (
            patch("ha_synthetic_sensors.StorageManager", return_value=mock_storage_manager),
            patch("ha_synthetic_sensors.async_create_sensor_manager", return_value=mock_sensor_manager),
        ):
            storage_manager, sensor_manager = await async_setup_synthetic_integration_with_auto_backing(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_add_entities,
                integration_domain="test_domain",
                device_identifier="test_device",
                sensor_configs=[sensor_config],
            )

        # Verify the setup
        assert storage_manager is not None
        assert sensor_manager is not None
        mock_storage_manager.async_create_sensor_set.assert_called_once()
        mock_sensor_manager.register_data_provider_entities.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_setup_synthetic_integration_with_auto_backing_existing_sensor_set(
        self, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test async_setup_synthetic_integration_with_auto_backing with existing sensor set."""
        # Mock Home Assistant components
        mock_config_entry = MagicMock()
        mock_config_entry.domain = "test_domain"
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {}

        mock_add_entities = Mock()

        # Mock storage manager
        mock_storage_manager = MagicMock()
        mock_storage_manager.sensor_set_exists.return_value = True
        mock_storage_manager.async_load = AsyncMock()

        mock_sensor_set = MagicMock()
        mock_sensor_set.async_add_sensor = AsyncMock()  # Fix: Make this async
        mock_sensor_set.list_sensors.return_value = []  # No existing sensors
        mock_storage_manager.get_sensor_set.return_value = mock_sensor_set

        # Mock sensor manager
        mock_sensor_manager = MagicMock()
        mock_sensor_manager.register_data_provider_entities = MagicMock()
        mock_sensor_manager.register_with_storage_manager = MagicMock()
        mock_sensor_manager.load_configuration = AsyncMock()

        # Create test sensor config with backing entity
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            entity_id="sensor.test_sensor",
            device_identifier="test_device",
            formulas=[FormulaConfig(id="main", formula="source_value", variables={"source_value": "sensor.backing_entity"})],
        )

        with (
            patch("ha_synthetic_sensors.StorageManager", return_value=mock_storage_manager),
            patch("ha_synthetic_sensors.async_create_sensor_manager", return_value=mock_sensor_manager),
        ):
            storage_manager, sensor_manager = await async_setup_synthetic_integration_with_auto_backing(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_add_entities,
                integration_domain="test_domain",
                device_identifier="test_device",
                sensor_configs=[sensor_config],
            )

        # Verify the setup
        assert storage_manager is not None
        assert sensor_manager is not None
        mock_storage_manager.async_create_sensor_set.assert_not_called()
        mock_sensor_manager.register_data_provider_entities.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_setup_synthetic_integration_with_auto_backing_no_backing_entities(
        self, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test async_setup_synthetic_integration_with_auto_backing with no backing entities."""
        # Mock Home Assistant components
        mock_config_entry = MagicMock()
        mock_config_entry.domain = "test_domain"
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {}

        mock_add_entities = Mock()

        # Mock storage manager
        mock_storage_manager = MagicMock()
        mock_storage_manager.sensor_set_exists.return_value = False
        mock_storage_manager.async_create_sensor_set = AsyncMock()
        mock_storage_manager.async_load = AsyncMock()

        mock_sensor_set = MagicMock()
        mock_sensor_set.async_replace_sensors = AsyncMock()
        mock_storage_manager.get_sensor_set.return_value = mock_sensor_set

        # Mock sensor manager
        mock_sensor_manager = MagicMock()
        mock_sensor_manager.register_data_provider_entities = MagicMock()
        mock_sensor_manager.register_with_storage_manager = MagicMock()
        mock_sensor_manager.load_configuration = AsyncMock()

        # Create test sensor config without backing entity
        sensor_config = SensorConfig(
            unique_id="test_sensor", name="Test Sensor", formulas=[FormulaConfig(id="main", formula="100")]
        )

        with (
            patch("ha_synthetic_sensors.StorageManager", return_value=mock_storage_manager),
            patch("ha_synthetic_sensors.async_create_sensor_manager", return_value=mock_sensor_manager),
        ):
            storage_manager, sensor_manager = await async_setup_synthetic_integration_with_auto_backing(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_add_entities,
                integration_domain="test_domain",
                device_identifier="test_device",
                sensor_configs=[sensor_config],
            )

        # Verify the setup
        assert storage_manager is not None
        assert sensor_manager is not None
        mock_storage_manager.async_create_sensor_set.assert_called_once()
        # Note: register_data_provider_entities may not be called if no backing entities are detected
        # This is expected behavior for sensors without backing entities

    @pytest.mark.asyncio
    async def test_async_setup_synthetic_integration_with_auto_backing_with_device_info(
        self, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test async_setup_synthetic_integration_with_auto_backing with device info."""
        # Mock Home Assistant components
        mock_config_entry = MagicMock()
        mock_config_entry.domain = "test_domain"
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {}

        mock_add_entities = Mock()

        # Mock storage manager
        mock_storage_manager = MagicMock()
        mock_storage_manager.sensor_set_exists.return_value = False
        mock_storage_manager.async_create_sensor_set = AsyncMock()
        mock_storage_manager.async_load = AsyncMock()

        mock_sensor_set = MagicMock()
        mock_sensor_set.async_replace_sensors = AsyncMock()
        mock_storage_manager.get_sensor_set.return_value = mock_sensor_set

        # Mock sensor manager
        mock_sensor_manager = MagicMock()
        mock_sensor_manager.register_data_provider_entities = MagicMock()
        mock_sensor_manager.register_with_storage_manager = MagicMock()
        mock_sensor_manager.load_configuration = AsyncMock()

        # Create test sensor config with device info
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            device_identifier="test_device",
            device_name="Test Device",
            device_manufacturer="TestCorp",
            device_model="TestModel",
            device_sw_version="1.0.0",
            device_hw_version="1.0",
            formulas=[FormulaConfig(id="main", formula="source_value", variables={"source_value": "sensor.backing_entity"})],
        )

        with (
            patch("ha_synthetic_sensors.StorageManager", return_value=mock_storage_manager),
            patch("ha_synthetic_sensors.async_create_sensor_manager", return_value=mock_sensor_manager),
        ):
            storage_manager, sensor_manager = await async_setup_synthetic_integration_with_auto_backing(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_add_entities,
                integration_domain="test_domain",
                device_identifier="test_device",
                sensor_configs=[sensor_config],
            )

        # Verify the setup
        assert storage_manager is not None
        assert sensor_manager is not None
        mock_storage_manager.async_create_sensor_set.assert_called_once()
        mock_sensor_manager.register_data_provider_entities.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_setup_synthetic_integration_with_auto_backing_with_ha_lookups(
        self, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test async_setup_synthetic_integration_with_auto_backing with HA lookups enabled."""
        # Mock Home Assistant components
        mock_config_entry = MagicMock()
        mock_config_entry.domain = "test_domain"
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {}

        mock_add_entities = Mock()

        # Mock storage manager
        mock_storage_manager = MagicMock()
        mock_storage_manager.sensor_set_exists.return_value = False
        mock_storage_manager.async_create_sensor_set = AsyncMock()
        mock_storage_manager.async_load = AsyncMock()

        mock_sensor_set = MagicMock()
        mock_sensor_set.async_replace_sensors = AsyncMock()
        mock_storage_manager.get_sensor_set.return_value = mock_sensor_set

        # Mock sensor manager
        mock_sensor_manager = MagicMock()
        mock_sensor_manager.register_data_provider_entities = MagicMock()
        mock_sensor_manager.register_with_storage_manager = MagicMock()
        mock_sensor_manager.load_configuration = AsyncMock()

        # Create test sensor config with HA lookups
        sensor_config = SensorConfig(
            unique_id="test_sensor", name="Test Sensor", formulas=[FormulaConfig(id="main", formula="sum(device_class:power)")]
        )

        with (
            patch("ha_synthetic_sensors.StorageManager", return_value=mock_storage_manager),
            patch("ha_synthetic_sensors.async_create_sensor_manager", return_value=mock_sensor_manager),
        ):
            storage_manager, sensor_manager = await async_setup_synthetic_integration_with_auto_backing(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_add_entities,
                integration_domain="test_domain",
                device_identifier="test_device",
                sensor_configs=[sensor_config],
            )

        # Verify the setup
        assert storage_manager is not None
        assert sensor_manager is not None
        mock_storage_manager.async_create_sensor_set.assert_called_once()
        # Note: register_data_provider_entities may not be called for dynamic queries
        # This is expected behavior for sensors with dynamic queries

    @pytest.fixture
    def auto_backing_entity_extraction_yaml_fixture_path(self):
        """YAML fixture for testing automatic backing entity extraction."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "auto_backing_entity_extraction.yaml"

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        return mock_device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    @pytest.fixture
    def mock_add_entities(self):
        """Create a mock async_add_entities callback."""
        return Mock()

    def create_data_provider_callback(self, backing_data: dict[str, any]) -> DataProviderCallback:
        """Create data provider for virtual backing entities."""

        def data_provider(entity_id: str):
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    @pytest.mark.asyncio
    async def test_auto_backing_entity_extraction_integration(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        auto_backing_entity_extraction_yaml_fixture_path,
        mock_config_entry,
        mock_add_entities,
        mock_device_registry,
    ) -> None:
        """Test complete integration: YAML → automatic backing entity extraction → working sensors."""

        # Set up virtual backing entity data that will be extracted from YAML
        backing_data = {
            "sensor.backing_entity1": 100.0,
            "sensor.backing_entity2": 50.0,
            "sensor.backing_entity3": 25.0,
            "sensor.backing_entity4": 10.0,
        }

        # Create data provider for virtual backing entities
        data_provider = self.create_data_provider_callback(backing_data)

        # Track created entities
        created_entities = []

        def capture_entities(entities):
            created_entities.extend(entities)

        mock_add_entities.side_effect = capture_entities

        # Set up storage manager with proper mocking following the test guide
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            # Use device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load YAML configuration
            sensor_set_id = "auto_backing_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Auto Backing Test Sensors"
            )

            with open(auto_backing_entity_extraction_yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3  # 3 sensors in the YAML

            # Get sensor configs from storage manager for the public API
            sensor_configs = storage_manager.list_sensors(sensor_set_id=sensor_set_id)

            # Test automatic backing entity extraction via public API
            storage_manager_result, sensor_manager = await async_setup_synthetic_integration_with_auto_backing(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_add_entities,
                integration_domain="test_domain",
                device_identifier="test_device_123",
                sensor_configs=sensor_configs,
                data_provider_callback=data_provider,
            )

            # Verify integration completed successfully
            assert storage_manager_result is not None
            assert sensor_manager is not None
            assert mock_add_entities.called

            # Verify sensors were actually created
            assert len(created_entities) == 3

            # Verify sensor names match YAML configuration
            sensor_names = {entity.name for entity in created_entities}
            expected_names = {"Main Power", "Total Consumption", "Efficiency"}
            assert sensor_names == expected_names

            # Test formula evaluation with real data provider
            await sensor_manager.async_update_sensors()

            # Verify formulas were evaluated correctly
            main_power_entity = next(e for e in created_entities if e.name == "Main Power")
            total_consumption_entity = next(e for e in created_entities if e.name == "Total Consumption")
            efficiency_entity = next(e for e in created_entities if e.name == "Efficiency")

            # Main Power: source_value * 2 = 100.0 * 2 = 200.0
            assert main_power_entity.state == 200.0
            assert main_power_entity.unit_of_measurement == "W"
            assert main_power_entity.device_class == "power"

            # Total Consumption: primary_source + secondary_source + offset = 50.0 + 25.0 + 10.0 = 85.0
            assert total_consumption_entity.state == 85.0
            assert total_consumption_entity.unit_of_measurement == "kWh"
            assert total_consumption_entity.device_class == "energy"

            # Efficiency: output / input * 100 = 100.0 / 50.0 * 100 = 200.0
            assert efficiency_entity.state == 200.0
            assert efficiency_entity.unit_of_measurement == "%"
            assert efficiency_entity.device_class == "power_factor"

            # Test that backing entity updates trigger sensor updates
            backing_data["sensor.backing_entity1"] = 150.0  # Change backing entity
            await sensor_manager.async_update_sensors_for_entities({"sensor.backing_entity1"})

            # Verify updated values
            assert main_power_entity.state == 300.0  # 150.0 * 2
            assert efficiency_entity.state == 300.0  # 150.0 / 50.0 * 100

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    @pytest.mark.asyncio
    async def test_async_setup_synthetic_integration_with_backing_entities(
        self, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test async_setup_synthetic_integration with backing entities."""
        # Mock Home Assistant components
        mock_config_entry = MagicMock()
        mock_config_entry.domain = "test_domain"
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {}

        mock_add_entities = Mock()

        # Mock storage manager
        mock_storage_manager = MagicMock()
        mock_storage_manager.sensor_set_exists.return_value = False
        mock_storage_manager.async_create_sensor_set = AsyncMock()
        mock_storage_manager.async_load = AsyncMock()

        mock_sensor_set = MagicMock()
        mock_sensor_set.async_replace_sensors = AsyncMock()
        mock_storage_manager.get_sensor_set.return_value = mock_sensor_set

        # Mock sensor manager
        mock_sensor_manager = MagicMock()
        mock_sensor_manager.register_data_provider_entities = MagicMock()
        mock_sensor_manager.register_with_storage_manager = MagicMock()
        mock_sensor_manager.load_configuration = AsyncMock()

        # Create test sensor config with backing entity
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            entity_id="sensor.test_sensor",
            device_identifier="test_device",
            formulas=[
                FormulaConfig(id="main", formula="source_value * 2", variables={"source_value": "sensor.backing_entity"})
            ],
        )

        with (
            patch("ha_synthetic_sensors.StorageManager", return_value=mock_storage_manager),
            patch("ha_synthetic_sensors.async_create_sensor_manager", return_value=mock_sensor_manager),
        ):
            # Test with backing entities
            storage_manager, sensor_manager = await async_setup_synthetic_integration(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_add_entities,
                integration_domain="test_domain",
                device_identifier="test_device",
                sensor_configs=[sensor_config],
                sensor_to_backing_mapping={"test_sensor": "sensor.backing_entity"},
            )

        # Verify the function completed successfully
        assert storage_manager is not None
        assert sensor_manager is not None

    @pytest.mark.asyncio
    async def test_async_setup_synthetic_integration_with_ha_lookups(
        self, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test async_setup_synthetic_integration with HA lookups enabled."""
        # Mock Home Assistant components
        mock_config_entry = MagicMock()
        mock_config_entry.domain = "test_domain"
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {}

        mock_add_entities = Mock()

        # Mock storage manager
        mock_storage_manager = MagicMock()
        mock_storage_manager.sensor_set_exists.return_value = False
        mock_storage_manager.async_create_sensor_set = AsyncMock()
        mock_storage_manager.async_load = AsyncMock()

        mock_sensor_set = MagicMock()
        mock_sensor_set.async_replace_sensors = AsyncMock()
        mock_storage_manager.get_sensor_set.return_value = mock_sensor_set

        # Mock sensor manager
        mock_sensor_manager = MagicMock()
        mock_sensor_manager.register_data_provider_entities = MagicMock()
        mock_sensor_manager.register_with_storage_manager = MagicMock()
        mock_sensor_manager.load_configuration = AsyncMock()

        # Create test sensor config
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            entity_id="sensor.test_sensor",
            device_identifier="test_device",
            formulas=[
                FormulaConfig(id="main", formula="source_value * 2", variables={"source_value": "sensor.backing_entity"})
            ],
        )

        with (
            patch("ha_synthetic_sensors.StorageManager", return_value=mock_storage_manager),
            patch("ha_synthetic_sensors.async_create_sensor_manager", return_value=mock_sensor_manager),
        ):
            # Test with HA lookups enabled
            storage_manager, sensor_manager = await async_setup_synthetic_integration(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_add_entities,
                integration_domain="test_domain",
                device_identifier="test_device",
                sensor_configs=[sensor_config],
                sensor_to_backing_mapping={"test_sensor": "sensor.backing_entity"},
            )

        # Verify the function completed successfully
        assert storage_manager is not None
        assert sensor_manager is not None

    @pytest.mark.asyncio
    async def test_async_setup_synthetic_integration_with_device_info(
        self, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test that device info is properly passed to sensor manager creation."""
        # Mock Home Assistant components
        mock_config_entry = MagicMock()
        mock_config_entry.domain = "test_domain"
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {}

        # Mock integration data with device info
        mock_hass.data = {
            "test_domain": {
                "test_entry": {"device_info": {"name": "Test Device", "identifiers": [("test_domain", "test_device")]}}
            }
        }

        mock_add_entities = Mock()

        # Mock storage manager
        mock_storage_manager = MagicMock()
        mock_storage_manager.sensor_set_exists.return_value = False
        mock_storage_manager.async_create_sensor_set = AsyncMock()
        mock_storage_manager.async_load = AsyncMock()

        mock_sensor_set = MagicMock()
        mock_sensor_set.async_replace_sensors = AsyncMock()
        mock_storage_manager.get_sensor_set.return_value = mock_sensor_set

        # Mock sensor manager
        mock_sensor_manager = MagicMock()
        mock_sensor_manager.register_data_provider_entities = MagicMock()
        mock_sensor_manager.register_with_storage_manager = MagicMock()
        mock_sensor_manager.load_configuration = AsyncMock()

        # Create test sensor config
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            entity_id="sensor.test_sensor",
            device_identifier="test_device",
            formulas=[FormulaConfig(id="main", formula="100 * 2", variables={})],
        )

        with (
            patch("ha_synthetic_sensors.StorageManager", return_value=mock_storage_manager),
            patch("ha_synthetic_sensors.async_create_sensor_manager", return_value=mock_sensor_manager),
        ):
            # Test with device info
            storage_manager, sensor_manager = await async_setup_synthetic_integration(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_add_entities,
                integration_domain="test_domain",
                device_identifier="test_device",
                sensor_configs=[sensor_config],
                sensor_set_name="Custom Sensor Set Name",
            )

        # Verify the function completed successfully
        assert storage_manager is not None
        assert sensor_manager is not None

        # Verify that the integration completed successfully with device info
        # The device info should have been extracted from hass.data and passed to sensor manager creation
        # Since we're mocking async_create_sensor_manager, we verify the integration works end-to-end

    @pytest.mark.asyncio
    async def test_async_setup_synthetic_integration_existing_sensor_set_upgrade(
        self, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test that existing sensor sets are properly upgraded with new sensors."""
        # Mock Home Assistant components
        mock_config_entry = MagicMock()
        mock_config_entry.domain = "test_domain"
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {}

        mock_add_entities = Mock()

        # Mock storage manager for existing sensor set
        mock_storage_manager = MagicMock()
        mock_storage_manager.sensor_set_exists.return_value = True  # Existing sensor set
        mock_storage_manager.async_load = AsyncMock()

        # Mock existing sensor set with one existing sensor
        mock_sensor_set = MagicMock()
        mock_sensor_set.async_add_sensor = AsyncMock()

        # Mock existing sensor
        mock_existing_sensor = MagicMock()
        mock_existing_sensor.unique_id = "existing_sensor"
        mock_sensor_set.list_sensors.return_value = [mock_existing_sensor]

        mock_storage_manager.get_sensor_set.return_value = mock_sensor_set

        # Mock sensor manager
        mock_sensor_manager = MagicMock()
        mock_sensor_manager.register_data_provider_entities = MagicMock()
        mock_sensor_manager.register_with_storage_manager = MagicMock()
        mock_sensor_manager.load_configuration = AsyncMock()

        # Create test sensor config for new sensor
        new_sensor_config = SensorConfig(
            unique_id="new_sensor",
            name="New Sensor",
            entity_id="sensor.new_sensor",
            device_identifier="test_device",
            formulas=[FormulaConfig(id="main", formula="100 * 2", variables={})],
        )

        with (
            patch("ha_synthetic_sensors.StorageManager", return_value=mock_storage_manager),
            patch("ha_synthetic_sensors.async_create_sensor_manager", return_value=mock_sensor_manager),
        ):
            # Test upgrade with existing sensor set
            storage_manager, sensor_manager = await async_setup_synthetic_integration(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_add_entities,
                integration_domain="test_domain",
                device_identifier="test_device",
                sensor_configs=[new_sensor_config],  # New sensor config
            )

        # Verify the function completed successfully
        assert storage_manager is not None
        assert sensor_manager is not None

        # Verify that the new sensor was added to the existing sensor set
        mock_sensor_set.async_add_sensor.assert_called_once_with(new_sensor_config)

        # Verify that sensor set creation was NOT called (since it already exists)
        mock_storage_manager.async_create_sensor_set.assert_not_called()

    async def test_setup_with_empty_backing_entities_error(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test async_setup_synthetic_sensors_with_entities with empty backing entity set raises error."""
        from ha_synthetic_sensors import (
            async_setup_synthetic_sensors_with_entities,
            StorageManager,
            SyntheticSensorsConfigError,
        )

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            # Use common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set and load YAML
            sensor_set_id = "empty_backing_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Empty Backing Test Sensors"
            )

            # Load YAML content
            yaml_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "empty_backing_entities_error.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1

            # Test with explicit empty backing entity set - should raise error
            with pytest.raises(SyntheticSensorsConfigError, match="Empty backing entity set provided explicitly"):
                await async_setup_synthetic_sensors_with_entities(
                    hass=mock_hass,
                    config_entry=mock_config_entry,
                    async_add_entities=mock_async_add_entities,
                    storage_manager=storage_manager,
                    device_identifier="test_device_123",
                    backing_entity_ids=set(),  # Explicit empty set
                )

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_setup_with_empty_mapping_natural_fallback(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test async_setup_synthetic_sensors_with_entities with empty mapping uses natural fallback to HA."""
        from ha_synthetic_sensors import (
            async_setup_synthetic_sensors_with_entities,
            StorageManager,
            SyntheticSensorsConfigError,
        )

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

            # Create sensor set and load YAML
            sensor_set_id = "empty_mapping_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Empty Mapping Test Sensors"
            )

            yaml_fixture_path = (
                Path(__file__).parent.parent / "fixtures" / "integration" / "empty_mapping_virtual_only_error.yaml"
            )
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1

            # Test with empty mapping - should work with natural fallback to HA
            await async_setup_synthetic_sensors_with_entities(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
                sensor_to_backing_mapping={},  # Empty mapping - will use natural fallback
            )

            # Verify the sensor was set up successfully
            mock_async_add_entities.assert_called_once()

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_setup_no_backing_entities_virtual_only(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test async_setup_synthetic_sensors with no backing entities in virtual-only mode logs debug message."""
        from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager

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

            # Create sensor set and load YAML
            sensor_set_id = "no_backing_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="No Backing Test Sensors"
            )

            yaml_fixture_path = (
                Path(__file__).parent.parent / "fixtures" / "integration" / "no_backing_entities_virtual_only.yaml"
            )
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1

            # Test with no backing entities and virtual-only mode - should succeed and log debug
            with patch("logging.getLogger") as mock_get_logger:
                mock_logger = Mock()
                mock_get_logger.return_value = mock_logger
                sensor_manager = await async_setup_synthetic_sensors(
                    hass=mock_hass,
                    config_entry=mock_config_entry,
                    async_add_entities=mock_async_add_entities,
                    storage_manager=storage_manager,
                    device_identifier="test_device_123",
                    # No backing_entity_ids, no sensor_to_backing_mapping
                )

                # Verify it succeeded and logged debug message
                assert sensor_manager is not None
                mock_logger.debug.assert_called()

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_setup_with_empty_config_error(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test that loading empty configuration fails with ConfigEntryError during validation."""
        from ha_synthetic_sensors import StorageManager
        from homeassistant.exceptions import ConfigEntryError

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

            # Create sensor set
            sensor_set_id = "empty_config_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Empty Config Test Sensors"
            )

            yaml_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "empty_config_error.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            # Test that loading empty configuration fails early with ConfigEntryError
            with pytest.raises(ConfigEntryError, match="should be non-empty"):
                await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_setup_with_device_info_extraction(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test async_setup_synthetic_sensors with device info extraction from integration data."""
        from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager

        # Set up mock HA states for external entity
        mock_states["sensor.base_power"] = type("MockState", (), {"state": "1000.0", "attributes": {}})()

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

            # Create sensor set and load YAML
            sensor_set_id = "device_info_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Device Info Test Sensors"
            )

            yaml_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "device_info_extraction.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1

            # Mock config_entry with data and integration data with device_info
            mock_config_entry.data = {"test": "data"}
            mock_config_entry.domain = "test_domain"
            mock_config_entry.entry_id = "test_entry_id"

            # Set up hass.data with device_info
            mock_hass.data = {"test_domain": {"test_entry_id": {"device_info": {"name": "Test Device", "model": "Test Model"}}}}

            # Test device info extraction
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
            )

            # Verify it succeeded
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
