"""
Tests for BulkConfigService - Comprehensive testing using actual YAML files.

This module tests the high-level bulk configuration management service,
ensuring all operations work correctly with real YAML fixtures.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from ha_synthetic_sensors.bulk_config_service import BulkConfigService
from ha_synthetic_sensors.config_manager import FormulaConfig, SensorConfig
from ha_synthetic_sensors.exceptions import SyntheticSensorsError


class TestBulkConfigService:
    """Test BulkConfigService functionality using actual YAML fixtures."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock HomeAssistant instance."""
        hass = MagicMock()
        hass.data = {}
        return hass

    @pytest.fixture
    async def bulk_service(self, mock_hass):
        """Create and initialize a BulkConfigService instance."""
        with patch("ha_synthetic_sensors.bulk_config_service.StorageManager") as MockStorageManager:
            mock_storage = AsyncMock()
            mock_storage.async_load = AsyncMock()
            MockStorageManager.return_value = mock_storage

            service = BulkConfigService(mock_hass, "test_storage")
            service.storage_manager = mock_storage
            await service.async_initialize()
            return service

    @pytest.fixture
    def yaml_fixtures_dir(self):
        """Get the path to YAML fixtures directory."""
        return Path(__file__).parent / "yaml_fixtures"

    def load_yaml_fixture(self, yaml_fixtures_dir: Path, filename: str) -> dict:
        """Load a YAML fixture file."""
        fixture_path = yaml_fixtures_dir / filename
        with open(fixture_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def load_yaml_content(self, yaml_fixtures_dir: Path, filename: str) -> str:
        """Load raw YAML content from fixture file."""
        fixture_path = yaml_fixtures_dir / filename
        with open(fixture_path, encoding="utf-8") as f:
            return f.read()

    # Initialization Tests

    def test_initialization_without_async_call(self, mock_hass):
        """Test that service raises error when not initialized."""
        service = BulkConfigService(mock_hass)

        with pytest.raises(SyntheticSensorsError, match="Service not initialized"):
            service.get_all_devices()

    async def test_async_initialize(self, bulk_service):
        """Test async initialization."""
        # Service should already be initialized by fixture
        assert bulk_service._loaded is True
        bulk_service.storage_manager.async_load.assert_called_once()

    # Device Sensor Set Management

    async def test_create_device_sensor_set(self, bulk_service):
        """Test creating a sensor set for a device."""
        bulk_service.storage_manager.async_create_sensor_set = AsyncMock()

        result = await bulk_service.async_create_device_sensor_set("test_device", "Test Device", "Test Description")

        # The result should be the generated sensor_set_id (starts with "device_")
        assert result.startswith("device_test_device_")
        # Check that async_create_sensor_set was called with sensor_set_id parameter
        call_args = bulk_service.storage_manager.async_create_sensor_set.call_args
        assert call_args[1]["sensor_set_id"] == result
        assert call_args[1]["device_identifier"] == "test_device"
        assert call_args[1]["name"] == "Test Device"
        assert call_args[1]["description"] == "Test Description"

    async def test_get_or_create_device_sensor_set_existing(self, bulk_service):
        """Test getting existing sensor set for device."""
        mock_metadata = MagicMock()
        mock_metadata.sensor_set_id = "existing_set_id"

        bulk_service.storage_manager.list_sensor_sets = MagicMock(return_value=[mock_metadata])

        result = await bulk_service.async_get_or_create_device_sensor_set("test_device")

        assert result == "existing_set_id"
        bulk_service.storage_manager.list_sensor_sets.assert_called_once_with("test_device")

    async def test_get_or_create_device_sensor_set_new(self, bulk_service):
        """Test creating new sensor set when none exists."""
        bulk_service.storage_manager.list_sensor_sets = MagicMock(return_value=[])
        bulk_service.storage_manager.async_create_sensor_set = AsyncMock()

        result = await bulk_service.async_get_or_create_device_sensor_set("test_device", "Test Device")

        # Should return a generated sensor_set_id
        assert result.startswith("device_test_device_")
        bulk_service.storage_manager.async_create_sensor_set.assert_called_once()

    async def test_delete_device_sensors(self, bulk_service):
        """Test deleting all sensors for a device."""
        mock_metadata1 = MagicMock()
        mock_metadata1.sensor_set_id = "set1"
        mock_metadata2 = MagicMock()
        mock_metadata2.sensor_set_id = "set2"

        bulk_service.storage_manager.list_sensor_sets = MagicMock(return_value=[mock_metadata1, mock_metadata2])
        bulk_service.storage_manager.async_delete_sensor_set = AsyncMock()

        result = await bulk_service.async_delete_device_sensors("test_device")

        assert result == 2
        assert bulk_service.storage_manager.async_delete_sensor_set.call_count == 2

    # Bulk Sensor Configuration

    async def test_add_sensors_to_device(self, bulk_service):
        """Test adding multiple sensors to a device."""
        # Create mock sensor configs - we'll test with just the basic structure
        sensor_configs = [
            MagicMock(unique_id="sensor1"),
            MagicMock(unique_id="sensor2"),
        ]

        bulk_service.async_get_or_create_device_sensor_set = AsyncMock(return_value="test_set_id")
        bulk_service.storage_manager.async_store_sensors_bulk = AsyncMock()

        result = await bulk_service.async_add_sensors_to_device("test_device", sensor_configs, "Test Device")

        assert result == "test_set_id"
        bulk_service.storage_manager.async_store_sensors_bulk.assert_called_once_with(
            sensor_configs, "test_set_id", "test_device"
        )

    async def test_replace_device_sensors(self, bulk_service):
        """Test replacing all sensors for a device."""
        sensor_configs = [SensorConfig(unique_id="new_sensor", formulas=[FormulaConfig(id="main", formula="1")])]

        bulk_service.async_delete_device_sensors = AsyncMock(return_value=2)
        bulk_service.async_add_sensors_to_device = AsyncMock(return_value="new_set_id")

        result = await bulk_service.async_replace_device_sensors("test_device", sensor_configs, "Test Device")

        assert result == "new_set_id"
        bulk_service.async_delete_device_sensors.assert_called_once_with("test_device")
        bulk_service.async_add_sensors_to_device.assert_called_once_with("test_device", sensor_configs, "Test Device")

    # YAML Integration Support

    async def test_import_yaml_for_device(self, bulk_service, yaml_fixtures_dir):
        """Test importing YAML configuration for a device."""
        yaml_content = self.load_yaml_content(yaml_fixtures_dir, "storage_test_basic.yaml")

        bulk_service.config_converter.convert_yaml_content_to_storage = AsyncMock(return_value="imported_set_id")

        result = await bulk_service.async_import_yaml_for_device("test_device", yaml_content, "Test Device")

        assert result == "imported_set_id"
        bulk_service.config_converter.convert_yaml_content_to_storage.assert_called_once()

    async def test_import_yaml_for_device_replace_existing(self, bulk_service, yaml_fixtures_dir):
        """Test importing YAML with replace_existing=True."""
        yaml_content = self.load_yaml_content(yaml_fixtures_dir, "storage_test_basic.yaml")

        bulk_service.async_delete_device_sensors = AsyncMock(return_value=1)
        bulk_service.config_converter.convert_yaml_content_to_storage = AsyncMock(return_value="imported_set_id")

        result = await bulk_service.async_import_yaml_for_device(
            "test_device", yaml_content, "Test Device", replace_existing=True
        )

        assert result == "imported_set_id"
        bulk_service.async_delete_device_sensors.assert_called_once_with("test_device")

    async def test_export_device_yaml(self, bulk_service):
        """Test exporting device sensors to YAML."""
        mock_config = MagicMock()
        mock_config.sensors = [SensorConfig(unique_id="sensor1", formulas=[FormulaConfig(id="main", formula="1")])]

        bulk_service.storage_manager.to_config = MagicMock(return_value=mock_config)

        with patch("ha_synthetic_sensors.config_manager.ConfigManager") as MockConfigManager:
            mock_manager = MagicMock()
            mock_manager._config_to_yaml.return_value = {"sensors": {"sensor1": {"formula": "1"}}}
            MockConfigManager.return_value = mock_manager

            result = await bulk_service.async_export_device_yaml("test_device")

            assert "sensors:" in result
            bulk_service.storage_manager.to_config.assert_called_once_with(device_identifier="test_device")

    async def test_export_device_yaml_with_file(self, bulk_service):
        """Test exporting device sensors to YAML file."""
        mock_config = MagicMock()
        mock_config.sensors = []

        bulk_service.storage_manager.to_config = MagicMock(return_value=mock_config)
        bulk_service.config_converter.export_storage_to_yaml = AsyncMock()

        with patch("ha_synthetic_sensors.config_manager.ConfigManager") as MockConfigManager:
            mock_manager = MagicMock()
            mock_manager._config_to_yaml.return_value = {"sensors": {}}
            MockConfigManager.return_value = mock_manager

            result = await bulk_service.async_export_device_yaml("test_device", "/tmp/test_export.yaml")

            assert "sensors:" in result
            bulk_service.config_converter.export_storage_to_yaml.assert_called_once_with(
                "/tmp/test_export.yaml", device_identifier="test_device"
            )

    # Query and Management

    def test_get_device_sensors(self, bulk_service):
        """Test getting all sensors for a device."""
        mock_sensors = [SensorConfig(unique_id="sensor1", formulas=[FormulaConfig(id="main", formula="1")])]

        bulk_service.storage_manager.list_sensors = MagicMock(return_value=mock_sensors)

        result = bulk_service.get_device_sensors("test_device")

        assert result == mock_sensors
        bulk_service.storage_manager.list_sensors.assert_called_once_with(device_identifier="test_device")

    def test_get_device_sensor_sets(self, bulk_service):
        """Test getting all sensor sets for a device."""
        mock_metadata = [MagicMock()]

        bulk_service.storage_manager.list_sensor_sets = MagicMock(return_value=mock_metadata)

        result = bulk_service.get_device_sensor_sets("test_device")

        assert result == mock_metadata
        bulk_service.storage_manager.list_sensor_sets.assert_called_once_with("test_device")

    def test_get_all_devices(self, bulk_service):
        """Test getting all device identifiers."""
        mock_metadata1 = MagicMock()
        mock_metadata1.device_identifier = "device1"
        mock_metadata2 = MagicMock()
        mock_metadata2.device_identifier = "device2"
        mock_metadata3 = MagicMock()
        mock_metadata3.device_identifier = None  # Should be ignored

        bulk_service.storage_manager.list_sensor_sets = MagicMock(return_value=[mock_metadata1, mock_metadata2, mock_metadata3])

        result = bulk_service.get_all_devices()

        assert set(result) == {"device1", "device2"}

    def test_get_device_summary(self, bulk_service):
        """Test getting device summary information."""
        mock_sensors = [
            SensorConfig(unique_id="sensor1", formulas=[FormulaConfig(id="main", formula="1")]),
            SensorConfig(unique_id="sensor2", formulas=[FormulaConfig(id="main", formula="2")]),
        ]

        mock_metadata = MagicMock()
        mock_metadata.sensor_set_id = "set1"
        mock_metadata.name = "Test Set"
        mock_metadata.description = "Test Description"
        mock_metadata.sensor_count = 2
        mock_metadata.created_at = "2025-01-01"
        mock_metadata.updated_at = "2025-01-02"

        bulk_service.get_device_sensors = MagicMock(return_value=mock_sensors)
        bulk_service.get_device_sensor_sets = MagicMock(return_value=[mock_metadata])

        result = bulk_service.get_device_summary("test_device")

        expected = {
            "device_identifier": "test_device",
            "sensor_count": 2,
            "sensor_set_count": 1,
            "sensor_sets": [
                {
                    "sensor_set_id": "set1",
                    "name": "Test Set",
                    "description": "Test Description",
                    "sensor_count": 2,
                    "created_at": "2025-01-01",
                    "updated_at": "2025-01-02",
                }
            ],
            "sensor_unique_ids": ["sensor1", "sensor2"],
        }

        assert result == expected

    # Batch Operations

    async def test_batch_update_sensors_update_operation(self, bulk_service):
        """Test batch update with update operations."""
        sensor_config = SensorConfig(unique_id="sensor1", formulas=[FormulaConfig(id="main", formula="1")])

        updates = [
            {"unique_id": "sensor1", "sensor_config": sensor_config, "device_identifier": "test_device", "operation": "update"}
        ]

        bulk_service.async_get_or_create_device_sensor_set = AsyncMock(return_value="test_set_id")
        bulk_service.storage_manager.async_store_sensor = AsyncMock()

        result = await bulk_service.async_batch_update_sensors(updates)

        assert result == {"sensor1": True}
        bulk_service.storage_manager.async_store_sensor.assert_called_once_with(sensor_config, "test_set_id", "test_device")

    async def test_batch_update_sensors_delete_operation(self, bulk_service):
        """Test batch update with delete operations."""
        updates = [{"unique_id": "sensor1", "operation": "delete"}]

        bulk_service.storage_manager.async_delete_sensor = AsyncMock(return_value=True)

        result = await bulk_service.async_batch_update_sensors(updates)

        assert result == {"sensor1": True}
        bulk_service.storage_manager.async_delete_sensor.assert_called_once_with("sensor1")

    async def test_batch_update_sensors_invalid_operation(self, bulk_service):
        """Test batch update with invalid operations."""
        updates = [{"unique_id": "sensor1", "operation": "invalid"}]

        result = await bulk_service.async_batch_update_sensors(updates)

        assert result == {"sensor1": False}

    async def test_batch_update_sensors_missing_unique_id(self, bulk_service):
        """Test batch update with missing unique_id."""
        updates = [{"operation": "delete"}]

        result = await bulk_service.async_batch_update_sensors(updates)

        assert result == {"unknown": False}

    async def test_batch_update_sensors_exception_handling(self, bulk_service):
        """Test batch update error handling."""
        updates = [{"unique_id": "sensor1", "operation": "delete"}]

        bulk_service.storage_manager.async_delete_sensor = AsyncMock(side_effect=Exception("Test error"))

        result = await bulk_service.async_batch_update_sensors(updates)

        assert result == {"sensor1": False}

    # Validation and Health Checks

    def test_validate_device_configuration(self, bulk_service):
        """Test device configuration validation."""
        mock_sensors = [
            SensorConfig(unique_id="sensor1", formulas=[FormulaConfig(id="main", formula="1")]),
            SensorConfig(unique_id="sensor2", formulas=[FormulaConfig(id="main", formula="2")]),
        ]

        mock_config = MagicMock()
        mock_config.validate.return_value = []  # No validation errors

        bulk_service.get_device_sensors = MagicMock(return_value=mock_sensors)
        bulk_service.storage_manager.to_config = MagicMock(return_value=mock_config)

        result = bulk_service.validate_device_configuration("test_device")

        expected = {
            "device_identifier": "test_device",
            "sensor_count": 2,
            "validation_errors": [],
            "device_errors": [],
            "is_valid": True,
        }

        assert result == expected

    def test_validate_device_configuration_with_duplicates(self, bulk_service):
        """Test device configuration validation with duplicate unique_ids."""
        mock_sensors = [
            SensorConfig(unique_id="sensor1", formulas=[FormulaConfig(id="main", formula="1")]),
            SensorConfig(unique_id="sensor1", formulas=[FormulaConfig(id="main", formula="2")]),  # Duplicate
        ]

        mock_config = MagicMock()
        mock_config.validate.return_value = []

        bulk_service.get_device_sensors = MagicMock(return_value=mock_sensors)
        bulk_service.storage_manager.to_config = MagicMock(return_value=mock_config)

        result = bulk_service.validate_device_configuration("test_device")

        assert result["is_valid"] is False
        assert "Duplicate sensor unique_ids found" in result["device_errors"]

    def test_validate_device_configuration_with_validation_errors(self, bulk_service):
        """Test device configuration validation with config validation errors."""
        mock_sensors = [SensorConfig(unique_id="sensor1", formulas=[FormulaConfig(id="main", formula="1")])]

        mock_config = MagicMock()
        mock_config.validate.return_value = ["Formula validation error"]

        bulk_service.get_device_sensors = MagicMock(return_value=mock_sensors)
        bulk_service.storage_manager.to_config = MagicMock(return_value=mock_config)

        result = bulk_service.validate_device_configuration("test_device")

        assert result["is_valid"] is False
        assert "Formula validation error" in result["validation_errors"]

    async def test_cleanup_orphaned_sensors(self, bulk_service):
        """Test cleanup of orphaned sensors (placeholder implementation)."""
        result = await bulk_service.async_cleanup_orphaned_sensors()

        expected = {
            "orphaned_sensors_found": 0,
            "orphaned_sensors_deleted": 0,
            "sensor_sets_cleaned": 0,
        }

        assert result == expected

    # Integration with Real YAML Fixtures

    async def test_bulk_operations_with_yaml_fixtures(self, bulk_service, yaml_fixtures_dir):
        """Test bulk operations using real YAML fixture files."""
        # Load complex YAML fixture
        yaml_content = self.load_yaml_content(yaml_fixtures_dir, "storage_test_complex.yaml")
        yaml_data = self.load_yaml_fixture(yaml_fixtures_dir, "storage_test_complex.yaml")

        # Mock the conversion process
        bulk_service.config_converter.convert_yaml_content_to_storage = AsyncMock(return_value="complex_set_id")

        # Import YAML for device
        result = await bulk_service.async_import_yaml_for_device("complex_device", yaml_content, "Complex Device")

        assert result == "complex_set_id"

        # Verify the YAML structure contains expected sensors
        assert "sensors" in yaml_data
        assert len(yaml_data["sensors"]) > 0

    async def test_bulk_operations_with_multi_device_yaml(self, bulk_service, yaml_fixtures_dir):
        """Test bulk operations with multi-device YAML fixture."""
        yaml_content = self.load_yaml_content(yaml_fixtures_dir, "storage_test_bulk_operations.yaml")
        yaml_data = self.load_yaml_fixture(yaml_fixtures_dir, "storage_test_bulk_operations.yaml")

        # Mock sensor set creation for multiple devices
        bulk_service.config_converter.convert_yaml_content_to_storage = AsyncMock(return_value="bulk_set_id")

        result = await bulk_service.async_import_yaml_for_device("bulk_device", yaml_content, "Bulk Device")

        assert result == "bulk_set_id"

        # Verify the YAML contains multiple sensors suitable for bulk operations
        assert "sensors" in yaml_data
        sensors = yaml_data["sensors"]
        assert len(sensors) >= 3  # Should have multiple sensors for bulk testing


class TestBulkConfigServiceErrorHandling:
    """Test error handling scenarios for BulkConfigService."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock HomeAssistant instance."""
        hass = MagicMock()
        hass.data = {}
        return hass

    async def test_service_without_initialization(self, mock_hass):
        """Test that uninitialized service raises appropriate errors."""
        service = BulkConfigService(mock_hass)

        with pytest.raises(SyntheticSensorsError, match="Service not initialized"):
            service.get_all_devices()

        with pytest.raises(SyntheticSensorsError, match="Service not initialized"):
            await service.async_create_device_sensor_set("test_device")

    async def test_batch_update_with_invalid_input_types(self, mock_hass):
        """Test batch update with invalid input types."""
        with patch("ha_synthetic_sensors.bulk_config_service.StorageManager") as MockStorageManager:
            mock_storage = AsyncMock()
            mock_storage.async_load = AsyncMock()
            MockStorageManager.return_value = mock_storage

            service = BulkConfigService(mock_hass)
            service.storage_manager = mock_storage
            await service.async_initialize()

            # Test with non-string unique_id
            updates = [
                {
                    "unique_id": 123,  # Invalid type
                    "operation": "delete",
                }
            ]

            result = await service.async_batch_update_sensors(updates)
            assert result == {"123": False}
