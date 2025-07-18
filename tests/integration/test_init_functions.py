"""Tests for __init__.py functions with low coverage."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

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
        self,
    ) -> None:
        """Test async_setup_synthetic_integration_with_auto_backing with fresh install."""
        # Mock Home Assistant components
        mock_hass = MagicMock()
        mock_config_entry = MagicMock()
        mock_config_entry.domain = "test_domain"
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {}

        mock_add_entities = AsyncMock()

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

            assert storage_manager == mock_storage_manager
            assert sensor_manager == mock_sensor_manager

            # Verify backing entity was extracted and registered
            mock_sensor_manager.register_data_provider_entities.assert_called_once_with({"sensor.backing_entity"}, False)

    @pytest.mark.asyncio
    async def test_async_setup_synthetic_integration_with_auto_backing_existing_sensor_set(
        self,
    ) -> None:
        """Test async_setup_synthetic_integration_with_auto_backing with existing sensor set."""
        # Mock Home Assistant components
        mock_hass = MagicMock()
        mock_config_entry = MagicMock()
        mock_config_entry.domain = "test_domain"
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {}

        mock_add_entities = AsyncMock()

        # Mock storage manager with existing sensor set
        mock_storage_manager = MagicMock()
        mock_storage_manager.sensor_set_exists.return_value = True
        mock_storage_manager.async_load = AsyncMock()

        mock_sensor_set = MagicMock()
        mock_sensor_set.list_sensors.return_value = [MagicMock(unique_id="existing_sensor")]
        mock_sensor_set.async_add_sensor = AsyncMock()
        mock_storage_manager.get_sensor_set.return_value = mock_sensor_set

        # Mock sensor manager
        mock_sensor_manager = MagicMock()
        mock_sensor_manager.register_data_provider_entities = MagicMock()
        mock_sensor_manager.register_with_storage_manager = MagicMock()
        mock_sensor_manager.load_configuration = AsyncMock()

        # Create test sensor config with new unique_id
        sensor_config = SensorConfig(
            unique_id="new_sensor",
            name="New Sensor",
            entity_id="sensor.new_sensor",
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

            # Verify new sensor was added to existing sensor set
            mock_sensor_set.async_add_sensor.assert_called_once_with(sensor_config)

    @pytest.mark.asyncio
    async def test_async_setup_synthetic_integration_with_auto_backing_no_backing_entities(
        self,
    ) -> None:
        """Test async_setup_synthetic_integration_with_auto_backing with no backing entities."""
        # Mock Home Assistant components
        mock_hass = MagicMock()
        mock_config_entry = MagicMock()
        mock_config_entry.domain = "test_domain"
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {}

        mock_add_entities = AsyncMock()

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

        # Create test sensor config with no backing entities
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            entity_id="sensor.test_sensor",
            device_identifier="test_device",
            formulas=[
                FormulaConfig(
                    id="main",
                    formula="42",  # Literal value, no variables
                    variables={},
                )
            ],
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

            # Verify no backing entities were registered
            mock_sensor_manager.register_data_provider_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_setup_synthetic_integration_with_auto_backing_with_device_info(
        self,
    ) -> None:
        """Test async_setup_synthetic_integration_with_auto_backing with device info."""
        # Mock Home Assistant components
        mock_hass = MagicMock()
        mock_hass.data = {"test_domain": {"test_entry": {"device_info": {"name": "Test Device"}}}}

        mock_config_entry = MagicMock()
        mock_config_entry.domain = "test_domain"
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {}

        mock_add_entities = AsyncMock()

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

            # Verify sensor manager was created with device info
            from ha_synthetic_sensors import async_create_sensor_manager

            async_create_sensor_manager.assert_called_once()
            call_args = async_create_sensor_manager.call_args
            assert call_args[1]["device_info"] == {"name": "Test Device"}

    @pytest.mark.asyncio
    async def test_async_setup_synthetic_integration_with_auto_backing_with_ha_lookups(
        self,
    ) -> None:
        """Test async_setup_synthetic_integration_with_auto_backing with HA lookups enabled."""
        # Mock Home Assistant components
        mock_hass = MagicMock()
        mock_config_entry = MagicMock()
        mock_config_entry.domain = "test_domain"
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {}

        mock_add_entities = AsyncMock()

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
                allow_ha_lookups=True,
            )

            # Verify backing entities were registered with HA lookups enabled
            mock_sensor_manager.register_data_provider_entities.assert_called_once_with({"sensor.backing_entity"}, True)
