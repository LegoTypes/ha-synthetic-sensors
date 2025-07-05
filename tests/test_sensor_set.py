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
                unit_of_measurement="W",
                device_class="power",
                state_class="measurement",
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
        storage_manager.get_sensor_set_metadata.assert_called_once_with("test_sensor_set")

    def test_metadata_property_not_exists(self, storage_manager):
        """Test metadata property when sensor set doesn't exist."""
        storage_manager.get_sensor_set_metadata = MagicMock(return_value=None)

        sensor_set = SensorSet(storage_manager, "nonexistent_set")
        metadata = sensor_set.metadata

        assert metadata is None
        storage_manager.get_sensor_set_metadata.assert_called_once_with("nonexistent_set")

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
        storage_manager.list_sensors.assert_called_once_with(sensor_set_id="test_sensor_set")

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
        """Test complete sensor lifecycle: import, add, update, remove, export."""
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
