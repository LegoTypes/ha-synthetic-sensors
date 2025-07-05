"""Tests for StorageManager Phase 1 functionality."""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
import pytest

from ha_synthetic_sensors.config_manager import FormulaConfig, SensorConfig
from ha_synthetic_sensors.exceptions import SyntheticSensorsError
from ha_synthetic_sensors.storage_manager import StorageManager


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}  # Storage system needs this
    return hass


@pytest.fixture
def storage_manager(mock_hass):
    """Create a StorageManager instance for testing with mocked Store."""
    with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
        mock_store = AsyncMock()
        MockStore.return_value = mock_store

        manager = StorageManager(mock_hass, "test_storage")
        # Set up the mock store
        manager._store = mock_store
        return manager


@pytest.fixture
def storage_manager_real(mock_hass):
    """Create a StorageManager instance that tests actual save/load without mocking Store methods."""
    # Create a temporary file for storage
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as temp_file:
        temp_file_name = temp_file.name

    # Create a mock store that actually reads/writes to the file
    mock_store = AsyncMock()

    async def mock_load():
        try:
            with open(temp_file_name) as f:
                import json

                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    async def mock_save(data):
        with open(temp_file_name, "w") as f:
            import json

            json.dump(data, f, indent=2)

    mock_store.async_load = mock_load
    mock_store.async_save = mock_save

    with patch("ha_synthetic_sensors.storage_manager.Store", return_value=mock_store):
        manager = StorageManager(mock_hass, "test_storage_real")
        yield manager

    # Cleanup
    os.unlink(temp_file_name)


@pytest.fixture
def sample_sensor_config():
    """Create a sample sensor configuration."""
    formula = FormulaConfig(
        id="main",
        formula="source_value",
        variables={"source_value": "sensor.test_source"},
        unit_of_measurement="W",
        device_class="power",
        state_class="measurement",
    )

    return SensorConfig(
        unique_id="test_sensor_power",
        name="Test Sensor Power",
        formulas=[formula],
        device_identifier="test_device:123",
    )


def load_yaml_fixture(fixture_name: str) -> str:
    """Load a YAML fixture file and return its contents."""
    import os

    fixture_path = os.path.join("tests", "yaml_fixtures", fixture_name)
    with open(fixture_path) as f:
        return f.read()


@pytest.fixture
def sample_stored_sensor():
    """Create a sample stored sensor for testing."""
    return {
        "unique_id": "test_sensor_power",
        "name": "Test Sensor Power",
        "formulas": [
            {
                "id": "main",
                "formula": "source_value",
                "variables": {"source_value": "sensor.test_source"},
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
            }
        ],
        "device_identifier": "test_device:123",
        "sensor_set_id": "test_sensor_set",
    }


@pytest.fixture
def sample_sensor_set_metadata():
    """Create a sample sensor set metadata for testing."""
    return {
        "device_identifier": "test_device:123",
        "name": "Test Device Sensors",
        "description": "Test sensor set",
        "sensor_count": 1,
        "created_at": "2023-01-01T00:00:00Z",
        "updated_at": "2023-01-01T00:00:00Z",
    }


class TestStorageManager:
    """Test cases for StorageManager."""

    async def test_initialization(self, storage_manager, mock_hass):
        """Test StorageManager initialization."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            assert storage_manager._data is not None
            assert storage_manager._data["version"] == "1.0"
            assert storage_manager._data["sensors"] == {}
            assert storage_manager._data["sensor_sets"] == {}

    async def test_load_existing_data(self, storage_manager):
        """Test loading existing storage data."""
        existing_data = {
            "version": "1.0",
            "sensors": {"test_sensor": {"unique_id": "test_sensor"}},
            "sensor_sets": {"set_1": {"name": "Test Set"}},
        }

        with patch.object(storage_manager._store, "async_load", return_value=existing_data):
            await storage_manager.async_load()

            assert storage_manager._data == existing_data

    async def test_create_sensor_set(self, storage_manager):
        """Test creating a sensor set."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            sensor_set = await storage_manager.async_create_sensor_set(
                sensor_set_id="test_sensor_set",
                device_identifier="test_device:123",
                name="Test Device Sensors",
                description="Test sensor set",
            )

            # Verify the sensor set was created and is accessible
            assert sensor_set.sensor_set_id == "test_sensor_set"
            assert "test_sensor_set" in storage_manager._data["sensor_sets"]
            metadata = storage_manager._data["sensor_sets"]["test_sensor_set"]
            assert metadata["device_identifier"] == "test_device:123"
            assert metadata["name"] == "Test Device Sensors"
            assert metadata["description"] == "Test sensor set"
            assert metadata["sensor_count"] == 0

    async def test_store_sensor(self, storage_manager, sample_sensor_config):
        """Test storing a sensor configuration."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Create sensor set first
            sensor_set = await storage_manager.async_create_sensor_set(
                sensor_set_id="test_sensor_set",
                device_identifier="test_device:123",
                name="Test Device",
            )

            # Store sensor
            await storage_manager.async_store_sensor(
                sample_sensor_config,
                sensor_set.sensor_set_id,
                "test_device:123",
            )

            # Verify sensor was stored
            assert sample_sensor_config.unique_id in storage_manager._data["sensors"]
            stored_sensor = storage_manager._data["sensors"][sample_sensor_config.unique_id]
            assert stored_sensor["sensor_set_id"] == sensor_set.sensor_set_id
            assert stored_sensor["device_identifier"] == "test_device:123"

            # Verify sensor set metadata was updated
            sensor_set_metadata = storage_manager._data["sensor_sets"][sensor_set.sensor_set_id]
            assert sensor_set_metadata["sensor_count"] == 1

    async def test_store_sensors_bulk(self, storage_manager, sample_sensor_config):
        """Test storing multiple sensors in bulk."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "test_bulk_sensor_set"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device:123",
                name="Test Device",
            )

            # Create multiple sensor configs
            sensor_configs = []
            for i in range(3):
                formula = FormulaConfig(
                    id="main",
                    formula="source_value",
                    variables={"source_value": f"sensor.test_source_{i}"},
                )
                config = SensorConfig(
                    unique_id=f"test_sensor_{i}",
                    name=f"Test Sensor {i}",
                    formulas=[formula],
                    device_identifier="test_device:123",
                )
                sensor_configs.append(config)

            # Store sensors in bulk
            await storage_manager.async_store_sensors_bulk(
                sensor_configs,
                sensor_set_id,
                "test_device:123",
            )

            # Verify all sensors were stored
            for config in sensor_configs:
                assert config.unique_id in storage_manager._data["sensors"]

            # Verify sensor set metadata
            sensor_set_metadata = storage_manager._data["sensor_sets"][sensor_set_id]
            assert sensor_set_metadata["sensor_count"] == 3

    async def test_get_sensor(self, storage_manager, sample_sensor_config):
        """Test retrieving a sensor configuration."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Create sensor set and store sensor
            sensor_set_id = "test_get_sensor_set"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device:123",
                name="Test Device",
            )

            await storage_manager.async_store_sensor(
                sample_sensor_config,
                sensor_set_id,
                "test_device:123",
            )

            # Retrieve sensor
            retrieved_sensor = storage_manager.get_sensor(sample_sensor_config.unique_id)

            assert retrieved_sensor is not None
            assert retrieved_sensor.unique_id == sample_sensor_config.unique_id
            assert retrieved_sensor.name == sample_sensor_config.name
            assert len(retrieved_sensor.formulas) == 1

    async def test_list_sensors_by_device(self, storage_manager):
        """Test listing sensors filtered by device."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Create sensor sets for different devices
            device1_set = "device1_sensor_set"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=device1_set,
                device_identifier="device1:123",
                name="Device 1",
            )

            device2_set = "device2_sensor_set"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=device2_set,
                device_identifier="device2:456",
                name="Device 2",
            )

            # Create sensors for each device
            for i in range(2):
                formula = FormulaConfig(id="main", formula="source_value")

                # Device 1 sensor
                config1 = SensorConfig(
                    unique_id=f"device1_sensor_{i}",
                    name=f"Device 1 Sensor {i}",
                    formulas=[formula],
                    device_identifier="device1:123",
                )
                await storage_manager.async_store_sensor(config1, device1_set, "device1:123")

                # Device 2 sensor
                config2 = SensorConfig(
                    unique_id=f"device2_sensor_{i}",
                    name=f"Device 2 Sensor {i}",
                    formulas=[formula],
                    device_identifier="device2:456",
                )
                await storage_manager.async_store_sensor(config2, device2_set, "device2:456")

            # List sensors for device 1
            device1_sensors = storage_manager.list_sensors(device_identifier="device1:123")
            assert len(device1_sensors) == 2
            for sensor in device1_sensors:
                assert sensor.unique_id.startswith("device1_sensor_")

            # List sensors for device 2
            device2_sensors = storage_manager.list_sensors(device_identifier="device2:456")
            assert len(device2_sensors) == 2
            for sensor in device2_sensors:
                assert sensor.unique_id.startswith("device2_sensor_")

    async def test_update_sensor(self, storage_manager, sample_sensor_config):
        """Test updating an existing sensor configuration."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Create sensor set and add sensor
            sensor_set = await storage_manager.async_create_sensor_set(
                sensor_set_id="test_update_set",
                device_identifier="test_device:123",
                name="Test Device",
            )

            await storage_manager.async_store_sensor(
                sample_sensor_config,
                sensor_set.sensor_set_id,
                "test_device:123",
            )

            # Get original timestamp
            original_stored = storage_manager._data["sensors"][sample_sensor_config.unique_id]
            original_updated_at = original_stored["updated_at"]

            # Update sensor configuration
            updated_config = SensorConfig(
                unique_id=sample_sensor_config.unique_id,
                name="Updated Test Sensor Power",  # Changed name
                formulas=sample_sensor_config.formulas,
                device_identifier=sample_sensor_config.device_identifier,
            )

            success = await storage_manager.async_update_sensor(updated_config)
            assert success

            # Verify sensor was updated
            stored_sensor = storage_manager._data["sensors"][sample_sensor_config.unique_id]
            config_data = stored_sensor["config_data"]
            assert config_data["name"] == "Updated Test Sensor Power"
            assert stored_sensor["updated_at"] != original_updated_at

            # Verify sensor set metadata was updated
            sensor_set_metadata = storage_manager._data["sensor_sets"][sensor_set.sensor_set_id]
            assert sensor_set_metadata["updated_at"] != original_updated_at

    async def test_update_sensor_not_found(self, storage_manager):
        """Test updating a non-existent sensor."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            # Try to update non-existent sensor
            non_existent_config = SensorConfig(
                unique_id="non_existent_sensor",
                name="Non-existent Sensor",
                formulas=[],
            )

            success = await storage_manager.async_update_sensor(non_existent_config)
            assert not success

    async def test_delete_sensor_set(self, storage_manager, sample_sensor_config):
        """Test deleting a sensor set and all associated sensors."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Create sensor set and store sensor
            sensor_set_id = "test_delete_sensor_set"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device:123",
                name="Test Device",
            )

            await storage_manager.async_store_sensor(
                sample_sensor_config,
                sensor_set_id,
                "test_device:123",
            )

            # Verify sensor exists
            assert sample_sensor_config.unique_id in storage_manager._data["sensors"]
            assert sensor_set_id in storage_manager._data["sensor_sets"]

            # Delete sensor set
            result = await storage_manager.async_delete_sensor_set(sensor_set_id)
            assert result is True

            # Verify sensor and sensor set are deleted
            assert sample_sensor_config.unique_id not in storage_manager._data["sensors"]
            assert sensor_set_id not in storage_manager._data["sensor_sets"]

    async def test_to_config_conversion(self, storage_manager, sample_sensor_config):
        """Test converting storage data to Config object."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Store some test data
            sensor_set_id = "test_config_conversion_set"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device:123",
                name="Test Device",
            )

            await storage_manager.async_store_sensor(
                sample_sensor_config,
                sensor_set_id,
                "test_device:123",
            )

            # Convert to Config
            config = storage_manager.to_config(device_identifier="test_device:123")

            assert config.version == "1.0"
            assert len(config.sensors) == 1
            assert config.sensors[0].unique_id == sample_sensor_config.unique_id
            assert config.global_settings == {}

    async def test_get_sensor_set_metadata(self, storage_manager):
        """Test retrieving sensor set metadata."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            sensor_set_id = "test_metadata_sensor_set"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device:123",
                name="Test Device Sensors",
                description="Test description",
            )

            metadata = storage_manager.get_sensor_set_metadata(sensor_set_id)

            assert metadata is not None
            assert metadata.sensor_set_id == sensor_set_id
            assert metadata.device_identifier == "test_device:123"
            assert metadata.name == "Test Device Sensors"
            assert metadata.description == "Test description"
            assert metadata.sensor_count == 0

    async def test_list_sensor_sets_by_device(self, storage_manager):
        """Test listing sensor sets filtered by device."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Create sensor sets for different devices
            device1_set1 = "device1_set1"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=device1_set1,
                device_identifier="device1:123",
                name="Device 1 Set 1",
            )

            device1_set2 = "device1_set2"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=device1_set2,
                device_identifier="device1:123",
                name="Device 1 Set 2",
            )

            device2_set = "device2_set1"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=device2_set,
                device_identifier="device2:456",
                name="Device 2 Set",
            )

            # List sensor sets for device 1
            device1_sets = storage_manager.list_sensor_sets("device1:123")
            assert len(device1_sets) == 2
            set_ids = [s.sensor_set_id for s in device1_sets]
            assert device1_set1 in set_ids
            assert device1_set2 in set_ids

            # List sensor sets for device 2
            device2_sets = storage_manager.list_sensor_sets("device2:456")
            assert len(device2_sets) == 1
            assert device2_sets[0].sensor_set_id == device2_set

    async def test_error_handling_not_loaded(self, storage_manager):
        """Test error handling when storage is not loaded."""
        with pytest.raises(SyntheticSensorsError, match="Storage not loaded"):
            storage_manager.get_sensor("test_sensor")

    async def test_delete_sensor(self, storage_manager, sample_sensor_config):
        """Test deleting an individual sensor."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Create sensor set and store sensor
            sensor_set_id = "test_delete_individual_sensor"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device:123",
                name="Test Device",
            )

            await storage_manager.async_store_sensor(
                sample_sensor_config,
                sensor_set_id,
                "test_device:123",
            )

            # Verify sensor exists
            assert sample_sensor_config.unique_id in storage_manager._data["sensors"]
            assert storage_manager._data["sensor_sets"][sensor_set_id]["sensor_count"] == 1

            # Delete individual sensor
            result = await storage_manager.async_delete_sensor(sample_sensor_config.unique_id)
            assert result is True

            # Verify sensor is deleted but sensor set remains
            assert sample_sensor_config.unique_id not in storage_manager._data["sensors"]
            assert sensor_set_id in storage_manager._data["sensor_sets"]
            assert storage_manager._data["sensor_sets"][sensor_set_id]["sensor_count"] == 0

    async def test_delete_sensor_not_found(self, storage_manager):
        """Test deleting a non-existent sensor."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            # Try to delete non-existent sensor
            result = await storage_manager.async_delete_sensor("non_existent_sensor")
            assert result is False

    async def test_update_sensor_with_global_settings(self, storage_manager):
        """Test updating sensor when global settings are present."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Import YAML with global settings
            yaml_content = """
version: "1.0"
global_settings:
  device_identifier: "global_device:test_123"
  variables:
    global_var: "sensor.global_entity"
sensors:
  test_sensor:
    name: "Test Sensor"
    formula: "1 + 2"
"""
            sensor_set_id = await storage_manager.async_from_yaml(yaml_content, "test_global_update_set", "test_device:123")

            # Get the imported sensor
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 1
            original_sensor = sensors[0]

            # Verify global settings were applied
            assert original_sensor.device_identifier == "global_device:test_123"
            assert original_sensor.formulas[0].variables.get("global_var") == "sensor.global_entity"

            # Update the sensor with new name but keep global settings
            updated_config = SensorConfig(
                unique_id=original_sensor.unique_id,
                name="Updated Test Sensor",  # Changed name
                formulas=original_sensor.formulas,
                device_identifier="global_device:test_123",  # Keep global setting
            )

            success = await storage_manager.async_update_sensor(updated_config)
            assert success

            # Verify the updated sensor still has global settings applied
            updated_sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(updated_sensors) == 1
            updated_sensor = updated_sensors[0]

            assert updated_sensor.name == "Updated Test Sensor"
            assert updated_sensor.device_identifier == "global_device:test_123"
            assert updated_sensor.formulas[0].variables.get("global_var") == "sensor.global_entity"

    async def test_delete_sensor_with_global_settings(self, storage_manager):
        """Test deleting sensor when global settings are present."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Import YAML with global settings
            yaml_content = """
version: "1.0"
global_settings:
  device_identifier: "global_device:test_123"
  variables:
    global_var: "sensor.global_entity"
sensors:
  test_sensor_1:
    name: "Test Sensor 1"
    formula: "1 + 2"
  test_sensor_2:
    name: "Test Sensor 2"
    formula: "2 + 3"
"""
            sensor_set_id = await storage_manager.async_from_yaml(yaml_content, "test_global_delete_set", "test_device:123")

            # Verify both sensors exist with global settings
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 2

            sensor_to_delete = next(s for s in sensors if s.unique_id == "test_sensor_1")
            assert sensor_to_delete.device_identifier == "global_device:test_123"

            # Delete one sensor
            result = await storage_manager.async_delete_sensor("test_sensor_1")
            assert result is True

            # Verify remaining sensor still has global settings
            remaining_sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(remaining_sensors) == 1
            remaining_sensor = remaining_sensors[0]

            assert remaining_sensor.unique_id == "test_sensor_2"
            assert remaining_sensor.device_identifier == "global_device:test_123"
            assert remaining_sensor.formulas[0].variables.get("global_var") == "sensor.global_entity"

    async def test_export_yaml_after_update_operations(self, storage_manager):
        """Test that export YAML includes updated sensors correctly."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Import initial YAML
            yaml_content = """
version: "1.0"
global_settings:
  device_identifier: "global_device:test_123"
sensors:
  original_sensor:
    name: "Original Sensor"
    formula: "1 + 2"
"""
            sensor_set_id = await storage_manager.async_from_yaml(yaml_content, "test_export_after_update", "test_device:123")

            # Update the sensor
            updated_config = SensorConfig(
                unique_id="original_sensor",
                name="Updated Original Sensor",
                formulas=[FormulaConfig(id="original_sensor", formula="2 + 3")],
                device_identifier="global_device:test_123",
            )

            success = await storage_manager.async_update_sensor(updated_config)
            assert success

            # Export YAML and verify it contains the updated sensor
            exported_yaml = storage_manager.export_yaml(sensor_set_id)

            # Parse the exported YAML to verify content
            import yaml as yaml_lib

            exported_data = yaml_lib.safe_load(exported_yaml)

            assert "sensors" in exported_data
            assert "original_sensor" in exported_data["sensors"]
            assert exported_data["sensors"]["original_sensor"]["name"] == "Updated Original Sensor"
            assert exported_data["sensors"]["original_sensor"]["formula"] == "2 + 3"

    async def test_export_yaml_after_delete_operations(self, storage_manager):
        """Test that export YAML excludes deleted sensors correctly."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Import initial YAML with multiple sensors
            yaml_content = """
version: "1.0"
global_settings:
  device_identifier: "global_device:test_123"
sensors:
  sensor_to_keep:
    name: "Sensor to Keep"
    formula: "1 + 2"
  sensor_to_delete:
    name: "Sensor to Delete"
    formula: "3 + 4"
"""
            sensor_set_id = await storage_manager.async_from_yaml(yaml_content, "test_export_after_delete", "test_device:123")

            # Delete one sensor
            result = await storage_manager.async_delete_sensor("sensor_to_delete")
            assert result is True

            # Export YAML and verify it only contains the remaining sensor
            exported_yaml = storage_manager.export_yaml(sensor_set_id)

            # Parse the exported YAML to verify content
            import yaml as yaml_lib

            exported_data = yaml_lib.safe_load(exported_yaml)

            assert "sensors" in exported_data
            assert "sensor_to_keep" in exported_data["sensors"]
            assert "sensor_to_delete" not in exported_data["sensors"]
            assert len(exported_data["sensors"]) == 1

    async def test_crud_validation_global_conflicts(self, storage_manager):
        """Test that CRUD operations reject sensors with global setting conflicts."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Create sensor set with global settings
            sensor_set_id = "test_validation_conflicts"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device:123",
                name="Test Validation",
            )

            # Set global settings for this sensor set
            data = storage_manager._ensure_loaded()
            data["sensor_sets"][sensor_set_id]["global_settings"] = {
                "device_identifier": "global_device:test_123",
                "variables": {"global_var": "sensor.global_entity"},
            }

            # Try to add sensor with conflicting device_identifier
            conflicting_sensor = SensorConfig(
                unique_id="conflicting_sensor",
                name="Conflicting Sensor",
                formulas=[FormulaConfig(id="conflicting_sensor", formula="1 + 2")],
                device_identifier="different_device:456",  # Conflicts with global
            )

            with pytest.raises(SyntheticSensorsError, match="Sensor validation failed"):
                await storage_manager.async_store_sensor(conflicting_sensor, sensor_set_id, "test_device:123")

            # Try to add sensor with conflicting variable
            conflicting_var_sensor = SensorConfig(
                unique_id="conflicting_var_sensor",
                name="Conflicting Variable Sensor",
                formulas=[
                    FormulaConfig(
                        id="conflicting_var_sensor",
                        formula="1 + 2",
                        variables={"global_var": "sensor.different_entity"},  # Conflicts with global
                    )
                ],
            )

            with pytest.raises(SyntheticSensorsError, match="Sensor validation failed"):
                await storage_manager.async_store_sensor(conflicting_var_sensor, sensor_set_id, "test_device:123")

    async def test_crud_validation_standard_errors(self, storage_manager):
        """Test that CRUD operations reject sensors with standard validation errors."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "test_validation_standard"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device:123",
                name="Test Standard Validation",
            )

            # Try to add sensor with missing unique_id
            invalid_sensor = SensorConfig(
                unique_id="",  # Invalid: empty unique_id
                name="Invalid Sensor",
                formulas=[FormulaConfig(id="main", formula="1 + 2")],
            )

            with pytest.raises(SyntheticSensorsError, match="Sensor validation failed"):
                await storage_manager.async_store_sensor(invalid_sensor, sensor_set_id, "test_device:123")

            # Try to add sensor with no formulas
            no_formula_sensor = SensorConfig(
                unique_id="no_formula_sensor",
                name="No Formula Sensor",
                formulas=[],  # Invalid: no formulas
            )

            with pytest.raises(SyntheticSensorsError, match="Sensor validation failed"):
                await storage_manager.async_store_sensor(no_formula_sensor, sensor_set_id, "test_device:123")

    async def test_crud_validation_valid_sensors(self, storage_manager):
        """Test that CRUD operations accept valid sensors."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Create sensor set with global settings
            sensor_set_id = "test_validation_valid"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device:123",
                name="Test Valid Validation",
            )

            # Set global settings
            data = storage_manager._ensure_loaded()
            data["sensor_sets"][sensor_set_id]["global_settings"] = {
                "device_identifier": "global_device:test_123",
                "variables": {"global_var": "sensor.global_entity"},
            }

            # Add valid sensor that matches global settings
            valid_sensor = SensorConfig(
                unique_id="valid_sensor",
                name="Valid Sensor",
                formulas=[
                    FormulaConfig(
                        id="valid_sensor",
                        formula="1 + 2",
                        variables={"global_var": "sensor.global_entity"},  # Matches global
                    )
                ],
                device_identifier="global_device:test_123",  # Matches global
            )

            # This should succeed
            await storage_manager.async_store_sensor(valid_sensor, sensor_set_id, "test_device:123")

            # Verify sensor was stored
            stored_sensor = storage_manager.get_sensor("valid_sensor")
            assert stored_sensor is not None
            assert stored_sensor.unique_id == "valid_sensor"

    async def test_update_validation_with_context(self, storage_manager):
        """Test that update operations validate against global settings."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Import sensor set with global settings
            yaml_content = """
version: "1.0"
global_settings:
  device_identifier: "global_device:test_123"
  variables:
    global_var: "sensor.global_entity"
sensors:
  test_sensor:
    name: "Test Sensor"
    formula: "1 + 2"
"""
            await storage_manager.async_from_yaml(yaml_content, "test_update_validation", "test_device:123")

            # Try to update sensor with conflicting device_identifier
            conflicting_update = SensorConfig(
                unique_id="test_sensor",
                name="Updated Test Sensor",
                formulas=[FormulaConfig(id="test_sensor", formula="2 + 3")],
                device_identifier="different_device:456",  # Conflicts with global
            )

            with pytest.raises(SyntheticSensorsError, match="Sensor update validation failed"):
                await storage_manager.async_update_sensor(conflicting_update)

            # Valid update should work
            valid_update = SensorConfig(
                unique_id="test_sensor",
                name="Updated Test Sensor",
                formulas=[FormulaConfig(id="test_sensor", formula="2 + 3", variables={"global_var": "sensor.global_entity"})],
                device_identifier="global_device:test_123",
            )

            result = await storage_manager.async_update_sensor(valid_update)
            assert result is True


class TestStorageManagerIntegration:
    """Integration tests for StorageManager with real storage."""

    async def test_real_storage_persistence(self, storage_manager_real, sample_sensor_config):
        """Test that data actually persists to storage and can be reloaded."""
        # Load storage
        await storage_manager_real.async_load()

        # Create sensor set
        sensor_set_id = "integration_test_set"
        await storage_manager_real.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier="test_device:123",
            name="Integration Test Set",
            description="Testing real persistence",
        )

        # Store sensor
        await storage_manager_real.async_store_sensor(sample_sensor_config, sensor_set_id, "test_device:123")

        # Verify data is in memory
        assert sample_sensor_config.unique_id in storage_manager_real._data["sensors"]
        assert sensor_set_id in storage_manager_real._data["sensor_sets"]

        # Create a new storage manager instance with the same store
        new_manager = StorageManager(storage_manager_real.hass, "test_storage_real")
        new_manager._store = storage_manager_real._store

        # Load data - should get the persisted data
        await new_manager.async_load()

        # Verify data was actually persisted and reloaded
        assert sample_sensor_config.unique_id in new_manager._data["sensors"]
        assert sensor_set_id in new_manager._data["sensor_sets"]

        # Verify metadata is correct
        metadata = new_manager.get_sensor_set_metadata(sensor_set_id)
        assert metadata is not None
        assert metadata.name == "Integration Test Set"
        assert metadata.description == "Testing real persistence"

        # Verify sensor can be retrieved correctly
        retrieved_sensor = new_manager.get_sensor(sample_sensor_config.unique_id)
        assert retrieved_sensor is not None
        assert retrieved_sensor.unique_id == sample_sensor_config.unique_id
        assert retrieved_sensor.name == sample_sensor_config.name

    async def test_yaml_round_trip_with_real_storage(self, storage_manager_real):
        """Test YAML import/export with real storage persistence."""
        # Load YAML from fixture
        yaml_content = load_yaml_fixture("storage_integration_test.yaml")

        # Load storage
        await storage_manager_real.async_load()

        # Import YAML
        sensor_set_id = await storage_manager_real.async_from_yaml(
            yaml_content, sensor_set_id="yaml_round_trip_test", device_identifier="test_device:456"
        )

        # Verify import worked
        assert sensor_set_id in storage_manager_real._data["sensor_sets"]
        sensors = storage_manager_real.list_sensors(sensor_set_id=sensor_set_id)
        assert (
            len(sensors) == 5
        )  # test_power_sensor, test_energy_sensor, test_efficiency_sensor, test_analysis_suite, test_dynamic_collection

        # Export YAML
        exported_yaml = storage_manager_real.export_yaml(sensor_set_id)

        # Parse exported YAML
        import yaml

        exported_data = yaml.safe_load(exported_yaml)

        # Verify structure is preserved
        assert exported_data["version"] == "1.0"
        assert "sensors" in exported_data
        assert "test_power_sensor" in exported_data["sensors"]
        assert "test_energy_sensor" in exported_data["sensors"]
        assert "test_analysis_suite" in exported_data["sensors"]

        # Verify sensor details
        power_sensor = exported_data["sensors"]["test_power_sensor"]
        assert power_sensor["name"] == "Test Power Sensor"
        assert power_sensor["formula"] == "instant_power"
        assert power_sensor["unit_of_measurement"] == "W"
        assert power_sensor["device_class"] == "power"

        energy_sensor = exported_data["sensors"]["test_energy_sensor"]
        assert energy_sensor["name"] == "Test Energy Sensor"
        assert energy_sensor["formula"] == "cumulative_energy"
        assert energy_sensor["unit_of_measurement"] == "kWh"
        assert energy_sensor["device_class"] == "energy"

        # Verify multi-formula sensor with attributes
        analysis_sensor = exported_data["sensors"]["test_analysis_suite"]
        assert analysis_sensor["name"] == "Test Analysis Suite"
        assert analysis_sensor["formula"] == 'sum("device_class:primary_type")'
        assert "attributes" in analysis_sensor
        assert "secondary_consumption" in analysis_sensor["attributes"]
        assert "efficiency_rating" in analysis_sensor["attributes"]
        assert analysis_sensor["attributes"]["secondary_consumption"]["formula"] == 'sum("device_class:secondary_type")'

    async def test_save_load_cycle_integrity(self, storage_manager_real, sample_sensor_config):
        """Test that multiple save/load cycles maintain data integrity."""
        await storage_manager_real.async_load()

        # Create initial data
        sensor_set_id = "integrity_test_set"
        await storage_manager_real.async_create_sensor_set(
            sensor_set_id=sensor_set_id, device_identifier="test_device:789", name="Integrity Test"
        )

        # Store multiple sensors
        sensor_configs = []
        for i in range(5):
            formula = FormulaConfig(id="main", formula=f"test_value_{i}", variables={f"test_value_{i}": f"sensor.test_{i}"})
            config = SensorConfig(unique_id=f"integrity_sensor_{i}", name=f"Integrity Sensor {i}", formulas=[formula])
            sensor_configs.append(config)

        await storage_manager_real.async_store_sensors_bulk(sensor_configs, sensor_set_id, "test_device:789")

        # Verify initial state
        initial_sensors = storage_manager_real.list_sensors(sensor_set_id=sensor_set_id)
        assert len(initial_sensors) == 5

        # Create new manager and reload
        new_manager = StorageManager(storage_manager_real.hass, "test_storage_real")
        new_manager._store = storage_manager_real._store
        await new_manager.async_load()

        # Verify data integrity after reload
        reloaded_sensors = new_manager.list_sensors(sensor_set_id=sensor_set_id)
        assert len(reloaded_sensors) == 5

        # Verify each sensor
        for i, sensor in enumerate(reloaded_sensors):
            assert sensor.unique_id == f"integrity_sensor_{i}"
            assert sensor.name == f"Integrity Sensor {i}"
            assert len(sensor.formulas) == 1
            assert sensor.formulas[0].formula == f"test_value_{i}"

        # Modify data and save again
        # Create final storage manager to test persistence
        final_manager = StorageManager(storage_manager_real.hass, "test_storage_real")
        final_manager._store = storage_manager_real._store

        # Load and verify everything persisted
        await final_manager.async_load()

        # Verify sensor set metadata persisted correctly
        metadata = final_manager.get_sensor_set_metadata(sensor_set_id)
        assert metadata.name == "Integrity Test"
        assert metadata.sensor_count == 5

    async def test_complex_yaml_storage_persistence(self, storage_manager_real):
        """Test storage with complex YAML containing dynamic collections and attributes."""
        # Load complex YAML fixture
        yaml_content = load_yaml_fixture("storage_test_complex.yaml")

        # Load storage
        await storage_manager_real.async_load()

        # Import complex YAML
        sensor_set_id = await storage_manager_real.async_from_yaml(
            yaml_content, sensor_set_id="complex_yaml_test", device_identifier="complex_device:789"
        )

        # Verify import worked
        sensors = storage_manager_real.list_sensors(sensor_set_id=sensor_set_id)
        assert len(sensors) > 10  # Complex fixture has many sensors

        # Find a sensor with attributes
        analysis_sensor = None
        for sensor in sensors:
            if sensor.unique_id == "energy_analysis_suite":
                analysis_sensor = sensor
                break

        assert analysis_sensor is not None
        assert len(analysis_sensor.formulas) > 1  # Should have main formula + attributes

        # Verify attribute formulas
        attribute_formulas = [f for f in analysis_sensor.formulas if f.id != "main"]
        assert len(attribute_formulas) >= 3  # Should have secondary_consumption, total_consumption, etc.

        # Export and verify structure is preserved
        exported_yaml = storage_manager_real.export_yaml(sensor_set_id)

        import yaml

        exported_data = yaml.safe_load(exported_yaml)

        # Verify complex sensor structure
        assert "energy_analysis_suite" in exported_data["sensors"]
        complex_sensor = exported_data["sensors"]["energy_analysis_suite"]
        assert "attributes" in complex_sensor
        assert "secondary_consumption" in complex_sensor["attributes"]
        assert "efficiency_rating" in complex_sensor["attributes"]

        # Verify variables are preserved
        assert "variables" in complex_sensor
        assert "primary_energy_type" in complex_sensor["variables"]

    async def test_global_settings_round_trip_integration(self, storage_manager_real):
        """Test global settings functionality with dual sensor set storage and retrieval."""
        await storage_manager_real.async_load()

        # Import sensor set WITH global settings
        global_yaml_content = load_yaml_fixture("storage_test_global_settings.yaml")
        global_set_id = await storage_manager_real.async_from_yaml(
            global_yaml_content,
            sensor_set_id="global_settings_test",
            device_identifier=None,  # Should use global device_identifier
        )

        # Import sensor set WITHOUT global settings
        local_yaml_content = load_yaml_fixture("storage_test_no_globals.yaml")
        local_set_id = await storage_manager_real.async_from_yaml(
            local_yaml_content, sensor_set_id="no_globals_test", device_identifier="local_device:test_456"
        )

        # Test retrieval of global settings sensors
        global_sensors = storage_manager_real.list_sensors(sensor_set_id=global_set_id)
        assert len(global_sensors) == 4  # 4 sensors in global fixture

        # Test retrieval of non-global sensors
        local_sensors = storage_manager_real.list_sensors(sensor_set_id=local_set_id)
        assert len(local_sensors) == 2  # 2 sensors in local fixture

        # Verify global device_identifier is applied to global sensors
        for sensor in global_sensors:
            assert sensor.device_identifier == "global_device:test_123"

        # Verify local device_identifier is preserved for local sensors
        for sensor in local_sensors:
            assert sensor.device_identifier == "local_device:test_456"

        # Test specific sensor retrieval with global settings applied
        global_power_sensor = storage_manager_real.get_sensor("global_power_sensor")
        assert global_power_sensor is not None
        assert global_power_sensor.device_identifier == "global_device:test_123"

        # Verify global variables are applied
        main_formula = None
        for formula in global_power_sensor.formulas:
            if formula.id == "global_power_sensor":
                main_formula = formula
                break

        assert main_formula is not None
        assert main_formula.variables is not None
        assert "base_power_sensor" in main_formula.variables
        assert main_formula.variables["base_power_sensor"] == "sensor.test_power_meter"

        # Test mixed variables sensor (global + local variables)
        mixed_sensor = storage_manager_real.get_sensor("mixed_variables_sensor")
        assert mixed_sensor is not None
        assert mixed_sensor.device_identifier == "global_device:test_123"

        mixed_formula = None
        for formula in mixed_sensor.formulas:
            if formula.id == "mixed_variables_sensor":
                mixed_formula = formula
                break

        assert mixed_formula is not None
        assert mixed_formula.variables is not None
        # Should have both global and local variables
        assert "base_power_sensor" in mixed_formula.variables  # From global
        assert "local_adjustment" in mixed_formula.variables  # From local
        assert mixed_formula.variables["base_power_sensor"] == "sensor.test_power_meter"
        assert mixed_formula.variables["local_adjustment"] == "sensor.local_adjustment_value"

        # Test that local sensors don't get global variables
        local_power_sensor = storage_manager_real.get_sensor("local_power_sensor")
        assert local_power_sensor is not None
        assert local_power_sensor.device_identifier == "local_device:test_456"

        local_formula = None
        for formula in local_power_sensor.formulas:
            if formula.id == "local_power_sensor":
                local_formula = formula
                break

        assert local_formula is not None
        assert local_formula.variables is not None
        # Should only have local variables, no global ones
        assert "local_power_meter" in local_formula.variables
        assert "base_power_sensor" not in local_formula.variables

        # Test YAML export preserves global settings structure
        exported_global_yaml = storage_manager_real.export_yaml(global_set_id)
        exported_local_yaml = storage_manager_real.export_yaml(local_set_id)

        import yaml

        exported_global_data = yaml.safe_load(exported_global_yaml)
        exported_local_data = yaml.safe_load(exported_local_yaml)

        # Verify global settings are preserved in export
        assert "global_settings" in exported_global_data
        assert exported_global_data["global_settings"]["device_identifier"] == "global_device:test_123"
        assert "variables" in exported_global_data["global_settings"]
        assert exported_global_data["global_settings"]["variables"]["base_power_sensor"] == "sensor.test_power_meter"

        # Verify local YAML has no global settings
        assert exported_local_data.get("global_settings", {}) == {}

        # Verify sensors in exported global YAML don't have redundant device_identifier
        # (since it should be inherited from global_settings)
        global_power_exported = exported_global_data["sensors"]["global_power_sensor"]
        # Device identifier should not be in individual sensor since it's global
        assert "device_identifier" not in global_power_exported

        # Verify sensors in exported local YAML do have device_identifier
        local_power_exported = exported_local_data["sensors"]["local_power_sensor"]
        assert local_power_exported["device_identifier"] == "local_device:test_456"

    def test_get_sensor_set(self, storage_manager):
        """Test getting a SensorSet handle."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            storage_manager._data = {"version": "1.0", "sensors": {}, "sensor_sets": {}}
            storage_manager._loaded = True

            result = storage_manager.get_sensor_set("test_set")

            assert result.sensor_set_id == "test_set"
            assert result.storage_manager == storage_manager


class TestStorageManagerConvenienceMethods:
    """Test StorageManager convenience methods."""

    @pytest.mark.asyncio
    async def test_sensor_set_exists_true(self, storage_manager, sample_sensor_set_metadata):
        """Test sensor_set_exists when sensor set exists."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()
            storage_manager._data["sensor_sets"]["test_set"] = sample_sensor_set_metadata

            result = storage_manager.sensor_set_exists("test_set")

            assert result is True

    @pytest.mark.asyncio
    async def test_sensor_set_exists_false(self, storage_manager):
        """Test sensor_set_exists when sensor set doesn't exist."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            result = storage_manager.sensor_set_exists("nonexistent_set")

            assert result is False

    @pytest.mark.asyncio
    async def test_get_sensor_count_all(self, storage_manager, sample_stored_sensor):
        """Test get_sensor_count for all sensors."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()
            storage_manager._data["sensors"]["sensor1"] = sample_stored_sensor
            storage_manager._data["sensors"]["sensor2"] = {
                **sample_stored_sensor,
                "unique_id": "sensor2",
                "sensor_set_id": "different_set",
            }

            result = storage_manager.get_sensor_count()

            assert result == 2

    @pytest.mark.asyncio
    async def test_get_sensor_count_specific_set(self, storage_manager, sample_stored_sensor):
        """Test get_sensor_count for specific sensor set."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()
            storage_manager._data["sensors"]["sensor1"] = sample_stored_sensor
            storage_manager._data["sensors"]["sensor2"] = {
                **sample_stored_sensor,
                "unique_id": "sensor2",
                "sensor_set_id": "different_set",
            }

            result = storage_manager.get_sensor_count("test_sensor_set")

            assert result == 1

    @pytest.mark.asyncio
    async def test_get_sensor_count_empty(self, storage_manager):
        """Test get_sensor_count when no sensors exist."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            result = storage_manager.get_sensor_count()

            assert result == 0

    @pytest.mark.asyncio
    async def test_async_clear_all_data(self, storage_manager, sample_stored_sensor, sample_sensor_set_metadata):
        """Test clearing all data from storage."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()
            # Add some data
            storage_manager._data["sensors"]["sensor1"] = sample_stored_sensor
            storage_manager._data["sensor_sets"]["set1"] = sample_sensor_set_metadata

            # Clear all data
            await storage_manager.async_clear_all_data()

            # Verify all data is cleared
            assert len(storage_manager._data["sensors"]) == 0
            assert len(storage_manager._data["sensor_sets"]) == 0

    @pytest.mark.asyncio
    async def test_get_storage_stats(self, storage_manager, sample_stored_sensor, sample_sensor_set_metadata):
        """Test getting storage statistics."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()
            # Add test data
            storage_manager._data["sensors"]["sensor1"] = sample_stored_sensor
            storage_manager._data["sensors"]["sensor2"] = {
                **sample_stored_sensor,
                "unique_id": "sensor2",
                "sensor_set_id": "different_set",
            }
            storage_manager._data["sensor_sets"]["set1"] = sample_sensor_set_metadata

            result = storage_manager.get_storage_stats()

            expected = {
                "total_sensors": 2,
                "total_sensor_sets": 1,
                "sensor_sets": {
                    "test_sensor_set": 1,
                    "different_set": 1,
                },
            }

            assert result == expected

    @pytest.mark.asyncio
    async def test_get_storage_stats_empty(self, storage_manager):
        """Test getting storage statistics when empty."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            result = storage_manager.get_storage_stats()

            expected = {
                "total_sensors": 0,
                "total_sensor_sets": 0,
                "sensor_sets": {},
            }

            assert result == expected

    @pytest.mark.asyncio
    async def test_has_data_true_sensors(self, storage_manager, sample_stored_sensor):
        """Test has_data when storage has sensors."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()
            storage_manager._data["sensors"]["sensor1"] = sample_stored_sensor

            result = storage_manager.has_data()

            assert result is True

    @pytest.mark.asyncio
    async def test_has_data_true_sensor_sets(self, storage_manager, sample_sensor_set_metadata):
        """Test has_data when storage has sensor sets."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()
            storage_manager._data["sensor_sets"]["set1"] = sample_sensor_set_metadata

            result = storage_manager.has_data()

            assert result is True

    @pytest.mark.asyncio
    async def test_has_data_false(self, storage_manager):
        """Test has_data when storage is empty."""
        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            result = storage_manager.has_data()

            assert result is False
