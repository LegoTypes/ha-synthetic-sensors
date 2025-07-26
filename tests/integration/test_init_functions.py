"""Tests for __init__.py functions with low coverage."""

import logging
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ha_synthetic_sensors import (
    async_setup_synthetic_integration_with_auto_backing,
    configure_logging,
    get_logging_info,
    test_logging,
)
from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig


class TestInitFunctions:
    """Test the functions in __init__.py that have low coverage."""

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
            unique_id="test_sensor",
            name="Test Sensor",
            formulas=[FormulaConfig(id="main", formula="100")],
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
            unique_id="test_sensor",
            name="Test Sensor",
            formulas=[FormulaConfig(id="main", formula="sum(device_class:power)")],
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
                allow_ha_lookups=True,
            )

        # Verify the setup
        assert storage_manager is not None
        assert sensor_manager is not None
        mock_storage_manager.async_create_sensor_set.assert_called_once()
        # Note: register_data_provider_entities may not be called for dynamic queries
        # This is expected behavior for sensors with dynamic queries
