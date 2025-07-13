"""
Test suite for SensorSet class.

Tests the SensorSet interface for individual sensor set operations,
including CRUD operations, YAML import/export, and error handling.
"""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
import pytest
import yaml

from ha_synthetic_sensors.config_manager import FormulaConfig, SensorConfig
from ha_synthetic_sensors.exceptions import SyntheticSensorsError
from ha_synthetic_sensors.sensor_set import SensorSet
from ha_synthetic_sensors.storage_manager import SensorSetMetadata, StorageManager


@pytest.fixture
def mock_hass():
    """Mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
    return hass


@pytest.fixture
def storage_manager(mock_hass):
    """Create StorageManager instance with mocked storage."""
    # Mock the StorageManager without initializing it fully
    manager = MagicMock(spec=StorageManager)

    # Add the hass attribute that SensorSet needs
    manager.hass = mock_hass

    # Mock the storage data
    manager._data = {
        "version": "1.0",
        "sensors": {},
        "sensor_sets": {},
        "global_settings": {},
    }

    # Mock the methods we need
    manager.get_sensor_set_metadata = MagicMock(return_value=None)
    manager.async_store_sensor = AsyncMock()
    manager.async_update_sensor = AsyncMock(return_value=True)
    manager.async_delete_sensor = AsyncMock(return_value=True)
    manager.get_sensor = MagicMock(return_value=None)
    manager.list_sensors = MagicMock(return_value=[])
    manager.async_store_sensors_bulk = AsyncMock()
    manager.async_from_yaml = AsyncMock()
    manager.export_yaml = MagicMock(return_value="yaml_content")
    manager.async_delete_sensor_set = AsyncMock(return_value=True)

    return manager


@pytest.fixture
def sensor_set_metadata():
    """Create sample sensor set metadata."""
    return SensorSetMetadata(
        sensor_set_id="test_sensor_set",
        device_identifier="test-device-123",
        name="Test Sensor Set",
        description="Test sensor set for unit tests",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
        sensor_count=2,
    )


@pytest.fixture
def sample_sensor_config():
    """Create sample sensor configuration."""
    return SensorConfig(
        unique_id="test_sensor_1",
        name="Test Sensor 1",
        entity_id="sensor.test_device_sensor_1",
        formulas=[
            FormulaConfig(
                id="main",
                formula="source_value",
                variables={"source_value": "sensor.source_1"},
                metadata={
                    "unit_of_measurement": "W",
                    "device_class": "power",
                    "state_class": "measurement",
                },
            )
        ],
        device_identifier="test-device-123",
    )


@pytest.fixture
def yaml_fixtures():
    """Load YAML fixtures for testing."""
    with open("tests/yaml_fixtures/sensor_set_test.yaml") as f:
        return yaml.safe_load(f)


class TestSensorSetInitialization:
    """Test SensorSet initialization and properties."""

    def test_sensor_set_initialization(self, storage_manager):
        """Test SensorSet initialization."""
        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        assert sensor_set.storage_manager == storage_manager
        assert sensor_set.sensor_set_id == "test_sensor_set"

    def test_metadata_property_exists(self, storage_manager, sensor_set_metadata):
        """Test metadata property when sensor set exists."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        metadata = sensor_set.metadata

        assert metadata == sensor_set_metadata
        # SensorSet constructor calls this multiple times during entity index rebuild
        assert storage_manager.get_sensor_set_metadata.called
        storage_manager.get_sensor_set_metadata.assert_any_call("test_sensor_set")

    def test_metadata_property_not_exists(self, storage_manager):
        """Test metadata property when sensor set doesn't exist."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=None)

        sensor_set = SensorSet(storage_manager, "nonexistent_set")
        metadata = sensor_set.metadata

        assert metadata is None
        # SensorSet constructor calls this multiple times during entity index rebuild
        assert storage_manager.get_sensor_set_metadata.called
        storage_manager.get_sensor_set_metadata.assert_any_call("nonexistent_set")

    def test_exists_property_true(self, storage_manager, sensor_set_metadata):
        """Test exists property when sensor set exists."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        assert sensor_set.exists is True

    def test_exists_property_false(self, storage_manager):
        """Test exists property when sensor set doesn't exist."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=None)

        sensor_set = SensorSet(storage_manager, "nonexistent_set")

        assert sensor_set.exists is False

    def test_ensure_exists_success(self, storage_manager, sensor_set_metadata):
        """Test _ensure_exists when sensor set exists."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        # Should not raise exception
        sensor_set._ensure_exists()

    def test_ensure_exists_failure(self, storage_manager):
        """Test _ensure_exists when sensor set doesn't exist."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=None)

        sensor_set = SensorSet(storage_manager, "nonexistent_set")

        with pytest.raises(SyntheticSensorsError, match="Sensor set not found: nonexistent_set"):
            sensor_set._ensure_exists()


class TestSensorSetCRUDOperations:
    """Test SensorSet CRUD operations."""

    @pytest.mark.asyncio
    async def test_async_add_sensor_success(self, storage_manager, sensor_set_metadata, sample_sensor_config):
        """Test adding a sensor to sensor set."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.async_store_sensor = AsyncMock()

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        await sensor_set.async_add_sensor(sample_sensor_config)

        storage_manager.async_store_sensor.assert_called_once_with(
            sensor_config=sample_sensor_config,
            sensor_set_id="test_sensor_set",
            device_identifier="test-device-123",
        )

    @pytest.mark.asyncio
    async def test_async_add_sensor_no_metadata(self, storage_manager, sample_sensor_config):
        """Test adding a sensor when metadata is None."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=None)

        sensor_set = SensorSet(storage_manager, "nonexistent_set")

        with pytest.raises(SyntheticSensorsError, match="Sensor set not found: nonexistent_set"):
            await sensor_set.async_add_sensor(sample_sensor_config)

    @pytest.mark.asyncio
    async def test_async_update_sensor_success(self, storage_manager, sensor_set_metadata, sample_sensor_config):
        """Test updating a sensor in sensor set."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.async_update_sensor = AsyncMock(return_value=True)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.has_sensor = MagicMock(return_value=True)

        result = await sensor_set.async_update_sensor(sample_sensor_config)

        assert result is True
        storage_manager.async_update_sensor.assert_called_once_with(sample_sensor_config)

    @pytest.mark.asyncio
    async def test_async_update_sensor_not_in_set(self, storage_manager, sensor_set_metadata, sample_sensor_config):
        """Test updating a sensor not in the sensor set."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.has_sensor = MagicMock(return_value=False)

        with pytest.raises(SyntheticSensorsError, match="Sensor test_sensor_1 not found in sensor set test_sensor_set"):
            await sensor_set.async_update_sensor(sample_sensor_config)

    @pytest.mark.asyncio
    async def test_async_update_sensor_storage_failure(self, storage_manager, sensor_set_metadata, sample_sensor_config):
        """Test updating a sensor when storage operation fails."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.async_update_sensor = AsyncMock(return_value=False)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.has_sensor = MagicMock(return_value=True)

        result = await sensor_set.async_update_sensor(sample_sensor_config)

        assert result is False

    @pytest.mark.asyncio
    async def test_async_remove_sensor_success(self, storage_manager, sensor_set_metadata):
        """Test removing a sensor from sensor set."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.async_delete_sensor = AsyncMock(return_value=True)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.has_sensor = MagicMock(return_value=True)

        result = await sensor_set.async_remove_sensor("test_sensor_1")

        assert result is True
        storage_manager.async_delete_sensor.assert_called_once_with("test_sensor_1")

    @pytest.mark.asyncio
    async def test_async_remove_sensor_not_in_set(self, storage_manager, sensor_set_metadata):
        """Test removing a sensor not in the sensor set."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.has_sensor = MagicMock(return_value=False)

        result = await sensor_set.async_remove_sensor("nonexistent_sensor")

        assert result is False

    @pytest.mark.asyncio
    async def test_async_remove_sensor_storage_failure(self, storage_manager, sensor_set_metadata):
        """Test removing a sensor when storage operation fails."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.async_delete_sensor = AsyncMock(return_value=False)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.has_sensor = MagicMock(return_value=True)

        result = await sensor_set.async_remove_sensor("test_sensor_1")

        assert result is False

    def test_get_sensor_success(self, storage_manager, sensor_set_metadata, sample_sensor_config):
        """Test getting a sensor from sensor set."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.get_sensor = MagicMock(return_value=sample_sensor_config)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.has_sensor = MagicMock(return_value=True)

        result = sensor_set.get_sensor("test_sensor_1")

        assert result == sample_sensor_config
        storage_manager.get_sensor.assert_called_once_with("test_sensor_1")

    def test_get_sensor_not_in_set(self, storage_manager, sensor_set_metadata, sample_sensor_config):
        """Test getting a sensor not in the sensor set."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.get_sensor = MagicMock(return_value=sample_sensor_config)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.has_sensor = MagicMock(return_value=False)

        result = sensor_set.get_sensor("test_sensor_1")

        assert result is None

    def test_get_sensor_not_found(self, storage_manager, sensor_set_metadata):
        """Test getting a sensor that doesn't exist in storage."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.get_sensor = MagicMock(return_value=None)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        result = sensor_set.get_sensor("nonexistent_sensor")

        assert result is None

    def test_list_sensors_success(self, storage_manager, sensor_set_metadata, sample_sensor_config):
        """Test listing all sensors in sensor set."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.list_sensors = MagicMock(return_value=[sample_sensor_config])

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        result = sensor_set.list_sensors()

        assert result == [sample_sensor_config]
        # SensorSet constructor calls this during entity index rebuild, then test calls it again
        assert storage_manager.list_sensors.call_count >= 1
        storage_manager.list_sensors.assert_any_call(sensor_set_id="test_sensor_set")

    def test_list_sensors_empty(self, storage_manager, sensor_set_metadata):
        """Test listing sensors in empty sensor set."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.list_sensors = MagicMock(return_value=[])

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        result = sensor_set.list_sensors()

        assert result == []

    def test_has_sensor_true(self, storage_manager, sensor_set_metadata, sample_sensor_config):
        """Test has_sensor when sensor exists in set."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.list_sensors = MagicMock(return_value=[sample_sensor_config])

        result = sensor_set.has_sensor("test_sensor_1")

        assert result is True

    def test_has_sensor_false(self, storage_manager, sensor_set_metadata):
        """Test has_sensor when sensor doesn't exist in set."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.list_sensors = MagicMock(return_value=[])

        result = sensor_set.has_sensor("nonexistent_sensor")

        assert result is False


class TestSensorSetBulkOperations:
    """Test SensorSet bulk operations."""

    @pytest.mark.asyncio
    async def test_async_replace_sensors_success(self, storage_manager, sensor_set_metadata, sample_sensor_config):
        """Test replacing all sensors in sensor set."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.async_store_sensors_bulk = AsyncMock()

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_configs = [sample_sensor_config]

        await sensor_set.async_replace_sensors(sensor_configs)

        storage_manager.async_store_sensors_bulk.assert_called_once_with(
            sensor_configs=sensor_configs,
            sensor_set_id="test_sensor_set",
            device_identifier="test-device-123",
        )

    @pytest.mark.asyncio
    async def test_async_replace_sensors_no_metadata(self, storage_manager, sample_sensor_config):
        """Test replacing sensors when metadata is None."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=None)

        sensor_set = SensorSet(storage_manager, "nonexistent_set")

        with pytest.raises(SyntheticSensorsError, match="Sensor set not found: nonexistent_set"):
            await sensor_set.async_replace_sensors([sample_sensor_config])

    @pytest.mark.asyncio
    async def test_async_replace_sensors_empty_list(self, storage_manager, sensor_set_metadata):
        """Test replacing sensors with empty list."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.async_store_sensors_bulk = AsyncMock()

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        await sensor_set.async_replace_sensors([])

        storage_manager.async_store_sensors_bulk.assert_called_once_with(
            sensor_configs=[],
            sensor_set_id="test_sensor_set",
            device_identifier="test-device-123",
        )


class TestSensorSetYAMLOperations:
    """Test SensorSet YAML import/export operations."""

    @pytest.mark.asyncio
    async def test_async_import_yaml_success(self, storage_manager, sensor_set_metadata, yaml_fixtures):
        """Test importing YAML content to sensor set."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.async_from_yaml = AsyncMock()

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        yaml_content = yaml.dump(yaml_fixtures["basic_sensor_set"])

        await sensor_set.async_import_yaml(yaml_content)

        storage_manager.async_from_yaml.assert_called_once_with(
            yaml_content=yaml_content,
            sensor_set_id="test_sensor_set",
            device_identifier="test-device-123",
        )

    @pytest.mark.asyncio
    async def test_async_import_yaml_no_metadata(self, storage_manager, yaml_fixtures):
        """Test importing YAML when metadata is None."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=None)
        storage_manager.async_from_yaml = AsyncMock()

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        yaml_content = yaml.dump(yaml_fixtures["basic_sensor_set"])

        await sensor_set.async_import_yaml(yaml_content)

        storage_manager.async_from_yaml.assert_called_once_with(
            yaml_content=yaml_content,
            sensor_set_id="test_sensor_set",
            device_identifier=None,
        )

    def test_export_yaml_success(self, storage_manager, sensor_set_metadata):
        """Test exporting sensor set to YAML."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.export_yaml = MagicMock(return_value="yaml_content")

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        result = sensor_set.export_yaml()

        assert result == "yaml_content"
        storage_manager.export_yaml.assert_called_once_with("test_sensor_set")

    def test_export_yaml_not_exists(self, storage_manager):
        """Test exporting YAML when sensor set doesn't exist."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=None)

        sensor_set = SensorSet(storage_manager, "nonexistent_set")

        with pytest.raises(SyntheticSensorsError, match="Sensor set not found: nonexistent_set"):
            sensor_set.export_yaml()

    @pytest.mark.asyncio
    async def test_async_export_yaml_success(self, storage_manager, sensor_set_metadata):
        """Test async exporting sensor set to YAML."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.export_yaml = MagicMock(return_value="yaml_content")

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        result = await sensor_set.async_export_yaml()

        assert result == "yaml_content"
        storage_manager.export_yaml.assert_called_once_with("test_sensor_set")

    @pytest.mark.asyncio
    async def test_async_export_yaml_not_exists(self, storage_manager):
        """Test async exporting YAML when sensor set doesn't exist."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=None)

        sensor_set = SensorSet(storage_manager, "nonexistent_set")

        with pytest.raises(SyntheticSensorsError, match="Sensor set not found: nonexistent_set"):
            await sensor_set.async_export_yaml()


class TestSensorSetManagement:
    """Test SensorSet management operations."""

    @pytest.mark.asyncio
    async def test_async_delete_success(self, storage_manager):
        """Test deleting sensor set."""
        storage_manager.async_delete_sensor_set = AsyncMock(return_value=True)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        result = await sensor_set.async_delete()

        assert result is True
        storage_manager.async_delete_sensor_set.assert_called_once_with("test_sensor_set")

    @pytest.mark.asyncio
    async def test_async_delete_not_found(self, storage_manager):
        """Test deleting sensor set that doesn't exist."""
        storage_manager.async_delete_sensor_set = AsyncMock(return_value=False)

        sensor_set = SensorSet(storage_manager, "nonexistent_set")

        result = await sensor_set.async_delete()

        assert result is False

    def test_sensor_count_exists(self, storage_manager, sensor_set_metadata, sample_sensor_config):
        """Test sensor count when sensor set exists."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.list_sensors = MagicMock(return_value=[sample_sensor_config])

        result = sensor_set.sensor_count

        assert result == 1

    def test_sensor_count_not_exists(self, storage_manager):
        """Test sensor count when sensor set doesn't exist."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=None)

        sensor_set = SensorSet(storage_manager, "nonexistent_set")

        result = sensor_set.sensor_count

        assert result == 0

    def test_get_summary_exists(self, storage_manager, sensor_set_metadata, sample_sensor_config):
        """Test getting summary when sensor set exists."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.list_sensors = MagicMock(return_value=[sample_sensor_config])

        result = sensor_set.get_summary()

        expected = {
            "sensor_set_id": "test_sensor_set",
            "exists": True,
            "device_identifier": "test-device-123",
            "name": "Test Sensor Set",
            "description": "Test sensor set for unit tests",
            "sensor_count": 1,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "sensor_unique_ids": ["test_sensor_1"],
        }

        assert result == expected

    def test_get_summary_not_exists(self, storage_manager):
        """Test getting summary when sensor set doesn't exist."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=None)

        sensor_set = SensorSet(storage_manager, "nonexistent_set")

        result = sensor_set.get_summary()

        expected = {
            "sensor_set_id": "nonexistent_set",
            "exists": False,
        }

        assert result == expected


class TestSensorSetIntegration:
    """Test SensorSet integration scenarios."""

    @pytest.mark.asyncio
    async def test_complete_sensor_lifecycle(self, storage_manager, sensor_set_metadata, sample_sensor_config, yaml_fixtures):
        """Test complete sensor lifecycle with YAML import/export."""
        # Setup mocks
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)
        storage_manager.async_from_yaml = AsyncMock()
        storage_manager.async_store_sensor = AsyncMock()
        storage_manager.async_update_sensor = AsyncMock(return_value=True)
        storage_manager.async_delete_sensor = AsyncMock(return_value=True)
        storage_manager.export_yaml = MagicMock(return_value="exported_yaml")

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        # Import YAML
        yaml_content = yaml.dump(yaml_fixtures["basic_sensor_set"])
        await sensor_set.async_import_yaml(yaml_content)

        # Add sensor
        sensor_set.has_sensor = MagicMock(return_value=False)
        await sensor_set.async_add_sensor(sample_sensor_config)

        # Update sensor
        sensor_set.has_sensor = MagicMock(return_value=True)
        await sensor_set.async_update_sensor(sample_sensor_config)

        # Remove sensor
        await sensor_set.async_remove_sensor("test_sensor_1")

        # Export YAML
        result = sensor_set.export_yaml()

        assert result == "exported_yaml"

    @pytest.mark.asyncio
    async def test_export_yaml_includes_crud_added_sensors(self, mock_hass, yaml_fixtures):
        """Test that export YAML includes sensors added via CRUD operations."""
        from unittest.mock import AsyncMock, patch

        from ha_synthetic_sensors.config_manager import FormulaConfig, SensorConfig
        from ha_synthetic_sensors.storage_manager import StorageManager

        # Create a StorageManager with mocked Store to test actual export behavior
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_export_bug", enable_entity_listener=False)
            storage_manager._store = mock_store

            # Initialize storage with empty data
            with patch.object(storage_manager._store, "async_load", return_value=None):
                await storage_manager.async_load()

            # Create sensor set
            with patch.object(storage_manager, "async_save", new_callable=AsyncMock):
                await storage_manager.async_create_sensor_set(
                    sensor_set_id="test_export_bug", device_identifier="test-device-123", name="Test Export Bug"
                )
                sensor_set = storage_manager.get_sensor_set("test_export_bug")

                # Import initial YAML
                yaml_content = yaml.dump(yaml_fixtures["basic_sensor_set"])
                await sensor_set.async_import_yaml(yaml_content)

                # Export YAML before adding new sensor
                initial_export = sensor_set.export_yaml()

                # Add a new sensor via CRUD
                new_sensor = SensorConfig(
                    unique_id="new_crud_sensor",
                    name="New CRUD Sensor",
                    formulas=[
                        FormulaConfig(
                            id="new_crud_sensor",  # Formula ID must match sensor unique_id for main formula
                            formula="crud_value",
                            variables={"crud_value": "sensor.crud_source"},
                            metadata={
                                "unit_of_measurement": "A",
                                "device_class": "current",
                                "state_class": "measurement",
                            },
                        )
                    ],
                    enabled=True,
                    device_identifier="test-device-123",
                )

                await sensor_set.async_add_sensor(new_sensor)

                # Export YAML after adding new sensor
                final_export = sensor_set.export_yaml()

                # Parse both exports to compare
                import yaml as yaml_lib

                initial_data = yaml_lib.safe_load(initial_export)
                final_data = yaml_lib.safe_load(final_export)

                # Check that the new sensor is included in the final export
                assert "new_crud_sensor" in final_data["sensors"], (
                    f"New sensor not found in export. Final sensors: {list(final_data['sensors'].keys())}"
                )

                # Check that the new sensor has the correct properties
                new_sensor_data = final_data["sensors"]["new_crud_sensor"]
                assert new_sensor_data["name"] == "New CRUD Sensor"
                assert new_sensor_data["formula"] == "crud_value"
                assert new_sensor_data["variables"]["crud_value"] == "sensor.crud_source"
                assert new_sensor_data["metadata"]["unit_of_measurement"] == "A"
                assert new_sensor_data["metadata"]["device_class"] == "current"
                assert new_sensor_data["metadata"]["state_class"] == "measurement"

                # Verify the sensor count increased
                assert len(final_data["sensors"]) == len(initial_data["sensors"]) + 1

    @pytest.mark.asyncio
    async def test_export_yaml_reflects_crud_updated_sensors(self, mock_hass, yaml_fixtures):
        """Test that export YAML reflects sensors updated via CRUD operations."""
        from unittest.mock import AsyncMock, patch

        from ha_synthetic_sensors.config_manager import FormulaConfig, SensorConfig
        from ha_synthetic_sensors.storage_manager import StorageManager

        # Create a StorageManager with mocked Store to test actual export behavior
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_export_update", enable_entity_listener=False)
            storage_manager._store = mock_store

            # Initialize storage with empty data
            with patch.object(storage_manager._store, "async_load", return_value=None):
                await storage_manager.async_load()

            # Create sensor set
            with patch.object(storage_manager, "async_save", new_callable=AsyncMock):
                await storage_manager.async_create_sensor_set(
                    sensor_set_id="test_export_update", device_identifier="test-device-123", name="Test Export Update"
                )
                sensor_set = storage_manager.get_sensor_set("test_export_update")

                # Import initial YAML
                yaml_content = yaml.dump(yaml_fixtures["basic_sensor_set"])
                await sensor_set.async_import_yaml(yaml_content)

                # Export YAML before updating sensor
                initial_export = sensor_set.export_yaml()
                initial_data = yaml.safe_load(initial_export)

                # Verify the original sensor exists
                original_sensor_key = next(iter(initial_data["sensors"].keys()))
                original_sensor_data = initial_data["sensors"][original_sensor_key]

                # Update the sensor via CRUD
                updated_sensor = SensorConfig(
                    unique_id=original_sensor_key,
                    name="Updated Sensor Name",  # Changed name
                    formulas=[
                        FormulaConfig(
                            id=original_sensor_key,  # Formula ID must match sensor unique_id for main formula
                            formula="updated_source_value",  # Changed formula
                            variables={"updated_source_value": "sensor.updated_source"},  # Changed variables
                            metadata={
                                "unit_of_measurement": "V",  # Changed unit
                                "device_class": "voltage",  # Changed device class
                                "state_class": "measurement",
                            },
                        )
                    ],
                    enabled=True,
                    device_identifier="test-device-123",
                )

                await sensor_set.async_update_sensor(updated_sensor)

                # Export YAML after updating sensor
                final_export = sensor_set.export_yaml()
                final_data = yaml.safe_load(final_export)

                # Check that the sensor was updated in the export
                assert original_sensor_key in final_data["sensors"], (
                    f"Updated sensor not found in export. Final sensors: {list(final_data['sensors'].keys())}"
                )

                # Check that the sensor has the updated properties
                updated_sensor_data = final_data["sensors"][original_sensor_key]
                assert updated_sensor_data["name"] == "Updated Sensor Name"
                assert updated_sensor_data["formula"] == "updated_source_value"
                assert updated_sensor_data["variables"]["updated_source_value"] == "sensor.updated_source"
                assert updated_sensor_data["metadata"]["unit_of_measurement"] == "V"
                assert updated_sensor_data["metadata"]["device_class"] == "voltage"
                assert updated_sensor_data["metadata"]["state_class"] == "measurement"

                # Verify the sensor count stayed the same
                assert len(final_data["sensors"]) == len(initial_data["sensors"])

                # Verify the changes are different from original
                assert updated_sensor_data["name"] != original_sensor_data["name"]
                assert updated_sensor_data["formula"] != original_sensor_data["formula"]

    @pytest.mark.asyncio
    async def test_export_yaml_reflects_crud_deleted_sensors(self, mock_hass, yaml_fixtures):
        """Test that export YAML reflects sensors deleted via CRUD operations."""
        from unittest.mock import AsyncMock, patch

        from ha_synthetic_sensors.config_manager import FormulaConfig, SensorConfig
        from ha_synthetic_sensors.storage_manager import StorageManager

        # Create a StorageManager with mocked Store to test actual export behavior
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_export_delete", enable_entity_listener=False)
            storage_manager._store = mock_store

            # Initialize storage with empty data
            with patch.object(storage_manager._store, "async_load", return_value=None):
                await storage_manager.async_load()

            # Create sensor set
            with patch.object(storage_manager, "async_save", new_callable=AsyncMock):
                await storage_manager.async_create_sensor_set(
                    sensor_set_id="test_export_delete", device_identifier="test-device-123", name="Test Export Delete"
                )
                sensor_set = storage_manager.get_sensor_set("test_export_delete")

                # Import initial YAML with multiple sensors
                yaml_content = yaml.dump(yaml_fixtures["basic_sensor_set"])
                await sensor_set.async_import_yaml(yaml_content)

                # Add a second sensor so we have multiple to work with
                second_sensor = SensorConfig(
                    unique_id="second_sensor",
                    name="Second Sensor",
                    formulas=[
                        FormulaConfig(
                            id="second_sensor",
                            formula="second_value",
                            variables={"second_value": "sensor.second_source"},
                            metadata={
                                "unit_of_measurement": "W",
                                "device_class": "power",
                                "state_class": "measurement",
                            },
                        )
                    ],
                    enabled=True,
                    device_identifier="test-device-123",
                )
                await sensor_set.async_add_sensor(second_sensor)

                # Export YAML before deleting sensor
                initial_export = sensor_set.export_yaml()
                initial_data = yaml.safe_load(initial_export)

                # Verify we have multiple sensors
                assert len(initial_data["sensors"]) >= 2

                # Get the sensor to delete (use the first one from original import)
                original_sensor_keys = list(initial_data["sensors"].keys())
                sensor_to_delete = original_sensor_keys[0]  # Delete the first sensor
                sensor_to_keep = "second_sensor"  # Keep the second sensor

                # Delete the sensor via CRUD
                await sensor_set.async_remove_sensor(sensor_to_delete)

                # Export YAML after deleting sensor
                final_export = sensor_set.export_yaml()
                final_data = yaml.safe_load(final_export)

                # Check that the deleted sensor is NOT in the export
                assert sensor_to_delete not in final_data["sensors"], (
                    f"Deleted sensor still found in export. Final sensors: {list(final_data['sensors'].keys())}"
                )

                # Check that the remaining sensor is still in the export
                assert sensor_to_keep in final_data["sensors"], (
                    f"Remaining sensor not found in export. Final sensors: {list(final_data['sensors'].keys())}"
                )

                # Verify the sensor count decreased
                assert len(final_data["sensors"]) == len(initial_data["sensors"]) - 1

                # Verify the remaining sensor has correct properties
                remaining_sensor_data = final_data["sensors"][sensor_to_keep]
                assert remaining_sensor_data["name"] == "Second Sensor"
                assert remaining_sensor_data["formula"] == "second_value"

    @pytest.mark.asyncio
    async def test_export_yaml_reflects_multiple_crud_operations(self, mock_hass, yaml_fixtures):
        """Test that export YAML reflects multiple CRUD operations (add, update, delete) in sequence."""
        from unittest.mock import AsyncMock, patch

        from ha_synthetic_sensors.config_manager import FormulaConfig, SensorConfig
        from ha_synthetic_sensors.storage_manager import StorageManager

        # Create a StorageManager with mocked Store to test actual export behavior
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_export_multiple", enable_entity_listener=False)
            storage_manager._store = mock_store

            # Initialize storage with empty data
            with patch.object(storage_manager._store, "async_load", return_value=None):
                await storage_manager.async_load()

            # Create sensor set
            with patch.object(storage_manager, "async_save", new_callable=AsyncMock):
                await storage_manager.async_create_sensor_set(
                    sensor_set_id="test_export_multiple", device_identifier="test-device-123", name="Test Export Multiple"
                )
                sensor_set = storage_manager.get_sensor_set("test_export_multiple")

                # Import initial YAML
                yaml_content = yaml.dump(yaml_fixtures["basic_sensor_set"])
                await sensor_set.async_import_yaml(yaml_content)

                # Get initial state
                initial_export = sensor_set.export_yaml()
                initial_data = yaml.safe_load(initial_export)
                original_sensor_key = next(iter(initial_data["sensors"].keys()))

                # Step 1: Add a new sensor
                new_sensor = SensorConfig(
                    unique_id="new_sensor",
                    name="New Sensor",
                    formulas=[
                        FormulaConfig(
                            id="new_sensor",
                            formula="new_value",
                            variables={"new_value": "sensor.new_source"},
                            metadata={"unit_of_measurement": "A", "device_class": "current"},
                        )
                    ],
                    enabled=True,
                    device_identifier="test-device-123",
                )
                await sensor_set.async_add_sensor(new_sensor)

                # Step 2: Update the original sensor
                updated_original = SensorConfig(
                    unique_id=original_sensor_key,
                    name="Updated Original Sensor",
                    formulas=[
                        FormulaConfig(
                            id=original_sensor_key,
                            formula="updated_original_value",
                            variables={"updated_original_value": "sensor.updated_original_source"},
                            metadata={"unit_of_measurement": "V", "device_class": "voltage"},
                        )
                    ],
                    enabled=True,
                    device_identifier="test-device-123",
                )
                await sensor_set.async_update_sensor(updated_original)

                # Step 3: Add another sensor to delete later
                temp_sensor = SensorConfig(
                    unique_id="temp_sensor",
                    name="Temporary Sensor",
                    formulas=[
                        FormulaConfig(
                            id="temp_sensor",
                            formula="temp_value",
                            variables={"temp_value": "sensor.temp_source"},
                        )
                    ],
                    enabled=True,
                    device_identifier="test-device-123",
                )
                await sensor_set.async_add_sensor(temp_sensor)

                # Step 4: Delete the temporary sensor
                await sensor_set.async_remove_sensor("temp_sensor")

                # Export final YAML after all operations
                final_export = sensor_set.export_yaml()
                final_data = yaml.safe_load(final_export)

                # Verify final state
                # Should have initial_count + 1 new sensor (temp sensor was added and deleted)
                assert len(final_data["sensors"]) == len(initial_data["sensors"]) + 1
                assert original_sensor_key in final_data["sensors"]  # Updated original still there
                assert "new_sensor" in final_data["sensors"]  # New sensor added
                assert "temp_sensor" not in final_data["sensors"]  # Temp sensor deleted

                # Verify updated original sensor
                updated_data = final_data["sensors"][original_sensor_key]
                assert updated_data["name"] == "Updated Original Sensor"
                assert updated_data["formula"] == "updated_original_value"
                assert updated_data["metadata"]["device_class"] == "voltage"

                # Verify new sensor
                new_data = final_data["sensors"]["new_sensor"]
                assert new_data["name"] == "New Sensor"
                assert new_data["formula"] == "new_value"
                assert new_data["metadata"]["device_class"] == "current"

    @pytest.mark.asyncio
    async def test_error_handling_sensor_not_exists(self, storage_manager):
        """Test error handling when sensor set doesn't exist."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=None)

        sensor_set = SensorSet(storage_manager, "nonexistent_set")

        # All operations that require sensor set to exist should raise error
        with pytest.raises(SyntheticSensorsError):
            sensor_set.list_sensors()

        with pytest.raises(SyntheticSensorsError):
            sensor_set.get_sensor("test_sensor")

        with pytest.raises(SyntheticSensorsError):
            sensor_set.export_yaml()

    @pytest.mark.asyncio
    async def test_bulk_operations_with_yaml_fixtures(self, storage_manager, yaml_fixtures):
        """Test bulk operations using YAML fixtures."""
        # Create metadata for bulk operations
        metadata = SensorSetMetadata(
            sensor_set_id="bulk_sensor_set",
            device_identifier="bulk-device-456",
            name="Bulk Test Set",
        )

        storage_manager.get_sensor_set_metadata = MagicMock(return_value=metadata)
        storage_manager.async_from_yaml = AsyncMock()
        storage_manager.async_store_sensors_bulk = AsyncMock()
        storage_manager.export_yaml = MagicMock(return_value=yaml.dump(yaml_fixtures["bulk_operations_sensor_set"]))

        sensor_set = SensorSet(storage_manager, "bulk_sensor_set")

        # Import bulk YAML
        yaml_content = yaml.dump(yaml_fixtures["bulk_operations_sensor_set"])
        await sensor_set.async_import_yaml(yaml_content)

        # Replace sensors in bulk
        await sensor_set.async_replace_sensors([])

        # Export should work
        result = sensor_set.export_yaml()
        assert result is not None

        # Verify all operations were called
        storage_manager.async_from_yaml.assert_called_once()
        storage_manager.async_store_sensors_bulk.assert_called_once()
        storage_manager.export_yaml.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_yaml_preserves_entity_id_from_import(self, mock_hass, yaml_fixtures):
        """Test that entity_id from YAML import is preserved in export."""
        from unittest.mock import AsyncMock, patch

        from ha_synthetic_sensors.storage_manager import StorageManager

        # Create a StorageManager with mocked Store to test actual export behavior
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_entity_id_preservation", enable_entity_listener=False)
            storage_manager._store = mock_store

            # Initialize storage with empty data
            with patch.object(storage_manager._store, "async_load", return_value=None):
                await storage_manager.async_load()

            # Create sensor set
            with patch.object(storage_manager, "async_save", new_callable=AsyncMock):
                await storage_manager.async_create_sensor_set(
                    sensor_set_id="test_entity_id_preservation",
                    device_identifier="test-device-123",
                    name="Test Entity ID Preservation",
                )
                sensor_set = storage_manager.get_sensor_set("test_entity_id_preservation")

                # Import YAML with explicit entity_id
                yaml_content = yaml.dump(
                    {
                        "version": "1.0",
                        "sensors": {
                            "sensor_with_entity_id": {
                                "name": "Sensor With Custom Entity ID",
                                "entity_id": "sensor.custom_power_monitor",
                                "formula": "power_value",
                                "variables": {"power_value": "sensor.source_power"},
                                "metadata": {
                                    "unit_of_measurement": "W",
                                    "device_class": "power",
                                    "state_class": "measurement",
                                },
                            },
                            "sensor_without_entity_id": {
                                "name": "Sensor Without Custom Entity ID",
                                "formula": "energy_value",
                                "variables": {"energy_value": "sensor.source_energy"},
                                "metadata": {
                                    "unit_of_measurement": "kWh",
                                    "device_class": "energy",
                                    "state_class": "total_increasing",
                                },
                            },
                        },
                    }
                )

                await sensor_set.async_import_yaml(yaml_content)

                # Export YAML and verify entity_id is preserved
                exported_yaml = sensor_set.export_yaml()
                exported_data = yaml.safe_load(exported_yaml)

                # Check that sensor with explicit entity_id preserves it
                sensor_with_id = exported_data["sensors"]["sensor_with_entity_id"]
                assert "entity_id" in sensor_with_id
                assert sensor_with_id["entity_id"] == "sensor.custom_power_monitor"
                assert sensor_with_id["name"] == "Sensor With Custom Entity ID"

                # Check that sensor without explicit entity_id doesn't have it in export
                sensor_without_id = exported_data["sensors"]["sensor_without_entity_id"]
                assert "entity_id" not in sensor_without_id
                assert sensor_without_id["name"] == "Sensor Without Custom Entity ID"

                # Verify the sensors were stored correctly by retrieving them
                stored_with_id = sensor_set.get_sensor("sensor_with_entity_id")
                assert stored_with_id is not None
                assert stored_with_id.entity_id == "sensor.custom_power_monitor"

                stored_without_id = sensor_set.get_sensor("sensor_without_entity_id")
                assert stored_without_id is not None
                assert stored_without_id.entity_id is None


class TestSensorSetValidation:
    """Test SensorSet validation and convenience methods."""

    def test_validate_sensor_config_valid(self, storage_manager, sample_sensor_config):
        """Test validating a valid sensor configuration."""
        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        errors = sensor_set.validate_sensor_config(sample_sensor_config)

        assert errors == []

    def test_validate_sensor_config_missing_unique_id(self, storage_manager, sample_sensor_config):
        """Test validating sensor config with missing unique_id."""
        sample_sensor_config.unique_id = ""

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        errors = sensor_set.validate_sensor_config(sample_sensor_config)

        assert "Sensor unique_id is required" in errors

    def test_validate_sensor_config_no_formulas(self, storage_manager, sample_sensor_config):
        """Test validating sensor config with no formulas."""
        sample_sensor_config.formulas = []

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        errors = sensor_set.validate_sensor_config(sample_sensor_config)

        assert "Sensor must have at least one formula" in errors

    def test_validate_sensor_config_duplicate_formula_ids(self, storage_manager, sample_sensor_config):
        """Test validating sensor config with duplicate formula IDs."""
        from ha_synthetic_sensors.config_manager import FormulaConfig

        # Add duplicate formula ID
        duplicate_formula = FormulaConfig(
            id="main",  # Same ID as existing formula
            formula="duplicate_value",
            variables={"duplicate_value": "sensor.duplicate"},
        )
        sample_sensor_config.formulas.append(duplicate_formula)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        errors = sensor_set.validate_sensor_config(sample_sensor_config)

        assert "Sensor has duplicate formula IDs" in errors

    def test_validate_sensor_config_empty_formula(self, storage_manager, sample_sensor_config):
        """Test validating sensor config with empty formula expression."""
        sample_sensor_config.formulas[0].formula = ""

        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        errors = sensor_set.validate_sensor_config(sample_sensor_config)

        assert "Formula 'main' missing formula expression" in errors

    def test_get_sensor_errors_valid_sensors(self, storage_manager, sensor_set_metadata, sample_sensor_config):
        """Test getting sensor errors when all sensors are valid."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.list_sensors = MagicMock(return_value=[sample_sensor_config])

        errors = sensor_set.get_sensor_errors()

        assert errors == {}

    def test_get_sensor_errors_invalid_sensors(self, storage_manager, sensor_set_metadata, sample_sensor_config):
        """Test getting sensor errors when sensors have validation issues."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)

        # Make sensor invalid
        sample_sensor_config.unique_id = ""

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.list_sensors = MagicMock(return_value=[sample_sensor_config])

        errors = sensor_set.get_sensor_errors()

        assert "" in errors
        assert "Sensor unique_id is required" in errors[""]

    @pytest.mark.asyncio
    async def test_async_validate_import_valid_yaml(self, storage_manager, mock_hass, yaml_fixtures):
        """Test validating valid YAML import."""
        # Mock the storage_manager.hass attribute
        storage_manager.hass = mock_hass

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        yaml_content = yaml.dump(yaml_fixtures["basic_sensor_set"])

        result = await sensor_set.async_validate_import(yaml_content)

        assert result["yaml_errors"] == []
        assert result["config_errors"] == []
        # Note: sensor_errors might be empty or contain validation issues depending on fixtures

    @pytest.mark.asyncio
    async def test_async_validate_import_invalid_yaml(self, storage_manager):
        """Test validating invalid YAML import."""
        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        invalid_yaml = "{ invalid: yaml: content: }"

        result = await sensor_set.async_validate_import(invalid_yaml)

        assert len(result["yaml_errors"]) > 0

    @pytest.mark.asyncio
    async def test_async_validate_import_empty_yaml(self, storage_manager):
        """Test validating empty YAML import."""
        sensor_set = SensorSet(storage_manager, "test_sensor_set")

        result = await sensor_set.async_validate_import("")

        assert "Empty YAML content" in result["yaml_errors"]

    def test_is_valid_true(self, storage_manager, sensor_set_metadata):
        """Test is_valid when sensor set is valid."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.get_sensor_errors = MagicMock(return_value={})

        assert sensor_set.is_valid() is True

    def test_is_valid_false_not_exists(self, storage_manager):
        """Test is_valid when sensor set doesn't exist."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=None)

        sensor_set = SensorSet(storage_manager, "nonexistent_set")

        assert sensor_set.is_valid() is False

    def test_is_valid_false_has_errors(self, storage_manager, sensor_set_metadata):
        """Test is_valid when sensor set has validation errors."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=sensor_set_metadata)

        sensor_set = SensorSet(storage_manager, "test_sensor_set")
        sensor_set.get_sensor_errors = MagicMock(return_value={"sensor1": ["error"]})

        assert sensor_set.is_valid() is False
