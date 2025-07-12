"""Integration tests for SensorSet CRUD operations.

Tests that the SensorSet class properly coordinates with handler modules
and storage manager to provide clean CRUD interface.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.exceptions import SyntheticSensorsError
from ha_synthetic_sensors.sensor_set import SensorSet
from ha_synthetic_sensors.storage_manager import SensorSetMetadata, StorageManager


@pytest.fixture
def mock_storage_manager():
    """Create a mock StorageManager instance."""
    manager = MagicMock(spec=StorageManager)

    # Add hass attribute for EntityIndex initialization
    manager.hass = MagicMock()

    # Mock sensor set metadata
    metadata = SensorSetMetadata(
        sensor_set_id="test_set",
        device_identifier="test_device",
        name="Test Set",
        description="Test sensor set",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
        sensor_count=0,
    )

    manager.get_sensor_set_metadata.return_value = metadata
    manager.async_store_sensor = AsyncMock()
    manager.async_update_sensor = AsyncMock(return_value=True)
    manager.async_delete_sensor = AsyncMock(return_value=True)
    manager.get_sensor = MagicMock(return_value=None)
    manager.list_sensors = MagicMock(return_value=[])

    return manager


@pytest.fixture
def sensor_set(mock_storage_manager):
    """Create SensorSet instance for testing."""
    return SensorSet(mock_storage_manager, "test_set")


@pytest.fixture
def sample_sensor_config():
    """Create sample sensor configuration."""
    return SensorConfig(
        unique_id="test_sensor",
        name="Test Sensor",
        formulas=[
            FormulaConfig(
                id="main", formula="temp + humidity", variables={"temp": "sensor.temperature", "humidity": "sensor.humidity"}
            )
        ],
        device_identifier="test_device",
    )


class TestSensorSetCRUD:
    """Test SensorSet CRUD operations."""

    @pytest.mark.asyncio
    async def test_async_add_sensor_success(self, sensor_set, sample_sensor_config):
        """Test adding a sensor through SensorSet CRUD interface."""
        await sensor_set.async_add_sensor(sample_sensor_config)

        # Verify delegation to storage manager
        sensor_set.storage_manager.async_store_sensor.assert_called_once_with(
            sensor_config=sample_sensor_config, sensor_set_id="test_set", device_identifier="test_device"
        )

    @pytest.mark.asyncio
    async def test_async_update_sensor_success(self, sensor_set, sample_sensor_config):
        """Test updating a sensor through SensorSet CRUD interface."""
        # Mock that sensor exists - both get_sensor and list_sensors need to return it
        sensor_set.storage_manager.get_sensor.return_value = sample_sensor_config
        sensor_set.storage_manager.list_sensors.return_value = [sample_sensor_config]

        result = await sensor_set.async_update_sensor(sample_sensor_config)

        assert result is True
        sensor_set.storage_manager.async_update_sensor.assert_called_once_with(sample_sensor_config)

    @pytest.mark.asyncio
    async def test_async_remove_sensor_success(self, sensor_set, sample_sensor_config):
        """Test removing a sensor through SensorSet CRUD interface."""
        # Mock that sensor exists - list_sensors needs to return it for has_sensor to work
        sensor_set.storage_manager.list_sensors.return_value = [sample_sensor_config]

        result = await sensor_set.async_remove_sensor("test_sensor")

        assert result is True
        sensor_set.storage_manager.async_delete_sensor.assert_called_once_with("test_sensor")

    def test_get_sensor_success(self, sensor_set, sample_sensor_config):
        """Test getting a sensor through SensorSet interface."""
        # Mock both get_sensor and list_sensors for has_sensor check
        sensor_set.storage_manager.get_sensor.return_value = sample_sensor_config
        sensor_set.storage_manager.list_sensors.return_value = [sample_sensor_config]

        result = sensor_set.get_sensor("test_sensor")

        assert result == sample_sensor_config
        sensor_set.storage_manager.get_sensor.assert_called_once_with("test_sensor")

    def test_list_sensors_success(self, sensor_set, sample_sensor_config):
        """Test listing sensors through SensorSet interface."""
        # Reset the call count since list_sensors might be called during initialization
        sensor_set.storage_manager.list_sensors.reset_mock()
        sensor_set.storage_manager.list_sensors.return_value = [sample_sensor_config]

        result = sensor_set.list_sensors()

        assert result == [sample_sensor_config]
        sensor_set.storage_manager.list_sensors.assert_called_once_with(sensor_set_id="test_set")

    def test_sensor_exists_alias(self, sensor_set):
        """Test that sensor_exists is an alias for has_sensor."""
        # Mock has_sensor method
        sensor_set.has_sensor = MagicMock(return_value=True)

        result = sensor_set.sensor_exists("test_sensor")

        assert result is True
        sensor_set.has_sensor.assert_called_once_with("test_sensor")


class TestSensorSetErrorHandling:
    """Test SensorSet error handling."""

    @pytest.mark.asyncio
    async def test_async_add_sensor_nonexistent_set(self, mock_storage_manager, sample_sensor_config):
        """Test adding sensor to non-existent sensor set."""
        mock_storage_manager.get_sensor_set_metadata.return_value = None

        sensor_set = SensorSet(mock_storage_manager, "nonexistent_set")

        with pytest.raises(SyntheticSensorsError):  # Should raise appropriate exception
            await sensor_set.async_add_sensor(sample_sensor_config)

    @pytest.mark.asyncio
    async def test_async_update_sensor_not_found(self, sensor_set, sample_sensor_config):
        """Test updating non-existent sensor."""
        # Mock that sensor doesn't exist - both get_sensor and list_sensors return empty
        sensor_set.storage_manager.get_sensor.return_value = None
        sensor_set.storage_manager.list_sensors.return_value = []

        # Should raise exception since sensor doesn't exist in the set
        with pytest.raises(SyntheticSensorsError):  # SyntheticSensorsError specifically
            await sensor_set.async_update_sensor(sample_sensor_config)

    @pytest.mark.asyncio
    async def test_async_remove_sensor_not_found(self, sensor_set):
        """Test removing non-existent sensor."""
        sensor_set.storage_manager.get_sensor.return_value = None

        result = await sensor_set.async_remove_sensor("nonexistent_sensor")

        assert result is False
        sensor_set.storage_manager.async_delete_sensor.assert_not_called()


class TestSensorSetDelegation:
    """Test that SensorSet properly delegates to handler modules."""

    def test_metadata_property_delegation(self, sensor_set):
        """Test that metadata property delegates to storage manager."""
        _ = sensor_set.metadata

        sensor_set.storage_manager.get_sensor_set_metadata.assert_called_with("test_set")

    def test_exists_property_delegation(self, sensor_set):
        """Test that exists property uses metadata delegation."""
        # Should call metadata property which calls storage manager
        _ = sensor_set.exists

        sensor_set.storage_manager.get_sensor_set_metadata.assert_called_with("test_set")

    @pytest.mark.asyncio
    async def test_global_settings_delegation(self, sensor_set):
        """Test that global settings operations delegate to handler."""
        # This test would verify delegation to global settings handler
        # when that functionality is implemented

        # For now, just verify the interface exists
        assert hasattr(sensor_set, "get_global_settings")
        assert hasattr(sensor_set, "async_set_global_settings")
        assert hasattr(sensor_set, "async_update_global_settings")
