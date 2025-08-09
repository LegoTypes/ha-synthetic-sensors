"""Tests for SensorSetGlobalSettings handler module.

Tests global settings management and validation functionality
in isolation from the main SensorSet class.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.sensor_set_global_settings import SensorSetGlobalSettings
from ha_synthetic_sensors.storage_manager import StorageManager


@pytest.fixture
def mock_storage_manager():
    """Create a mock StorageManager instance."""
    manager = MagicMock(spec=StorageManager)
    manager.data = {
        "sensor_sets": {
            "test_set": {"global_settings": {"variables": {"global_temp": "sensor.temperature"}, "device_class": "power"}},
            "empty_set": {},
        }
    }
    manager.async_save = AsyncMock()
    manager.validate_no_global_conflicts = MagicMock()
    return manager


@pytest.fixture
def global_settings_handler(mock_storage_manager):
    """Create SensorSetGlobalSettings handler instance."""
    return SensorSetGlobalSettings(mock_storage_manager, "test_set")


@pytest.fixture
def sample_sensors():
    """Create sample sensor configurations for testing."""
    return [
        SensorConfig(
            unique_id="sensor1",
            name="Sensor 1",
            formulas=[FormulaConfig(id="main", formula="local_var + global_temp", variables={"local_var": "sensor.local"})],
        ),
        SensorConfig(
            unique_id="sensor2",
            name="Sensor 2",
            formulas=[FormulaConfig(id="main", formula="other_var * 2", variables={"other_var": "sensor.other"})],
        ),
    ]


class TestGlobalSettingsRetrieval:
    """Test global settings retrieval operations."""

    def test_get_global_settings_exists(self, global_settings_handler):
        """Test getting global settings when they exist."""
        settings = global_settings_handler.get_global_settings()

        assert settings == {"variables": {"global_temp": "sensor.temperature"}, "device_class": "power"}

    def test_get_global_settings_empty(self, mock_storage_manager):
        """Test getting global settings when they don't exist."""
        handler = SensorSetGlobalSettings(mock_storage_manager, "empty_set")
        settings = handler.get_global_settings()

        assert settings == {}

    def test_get_global_settings_missing_sensor_set(self, mock_storage_manager):
        """Test getting global settings for non-existent sensor set."""
        handler = SensorSetGlobalSettings(mock_storage_manager, "missing_set")
        settings = handler.get_global_settings()

        assert settings == {}


class TestGlobalSettingsModification:
    """Test global settings modification operations."""

    @pytest.mark.asyncio
    async def test_async_set_global_settings_success(self, global_settings_handler, sample_sensors):
        """Test setting global settings successfully."""
        new_settings = {"variables": {"new_global": "sensor.new"}, "unit_of_measurement": "W"}

        await global_settings_handler.async_set_global_settings(new_settings, sample_sensors)

        # Verify validation was called
        global_settings_handler.storage_manager.validate_no_global_conflicts.assert_called_once_with(
            sample_sensors, new_settings
        )

        # Verify storage was updated
        assert global_settings_handler.storage_manager.data["sensor_sets"]["test_set"]["global_settings"] == new_settings
        global_settings_handler.storage_manager.async_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_set_global_settings_empty(self, global_settings_handler, sample_sensors):
        """Test setting empty global settings."""
        await global_settings_handler.async_set_global_settings({}, sample_sensors)

        # Should not call validation for empty settings
        global_settings_handler.storage_manager.validate_no_global_conflicts.assert_not_called()

        # Verify storage was updated
        assert global_settings_handler.storage_manager.data["sensor_sets"]["test_set"]["global_settings"] == {}
        global_settings_handler.storage_manager.async_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_set_global_settings_validation_error(self, global_settings_handler, sample_sensors):
        """Test setting global settings with validation error."""
        from ha_synthetic_sensors.exceptions import SyntheticSensorsError

        new_settings = {"variables": {"conflicting_var": "sensor.conflict"}}

        # Mock validation to raise error
        global_settings_handler.storage_manager.validate_no_global_conflicts.side_effect = SyntheticSensorsError("Conflict")

        with pytest.raises(SyntheticSensorsError):
            await global_settings_handler.async_set_global_settings(new_settings, sample_sensors)

        # Verify save was not called
        global_settings_handler.storage_manager.async_save.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_update_global_settings_merge(self, global_settings_handler, sample_sensors):
        """Test updating global settings merges with existing."""
        updates = {"unit_of_measurement": "kW"}

        await global_settings_handler.async_update_global_settings(updates, sample_sensors)

        # Verify merged settings
        expected_settings = {
            "variables": {"global_temp": "sensor.temperature"},
            "device_class": "power",
            "unit_of_measurement": "kW",
        }

        global_settings_handler.storage_manager.validate_no_global_conflicts.assert_called_once_with(
            sample_sensors, expected_settings
        )

        assert global_settings_handler.storage_manager.data["sensor_sets"]["test_set"]["global_settings"] == expected_settings

    @pytest.mark.asyncio
    async def test_async_update_global_settings_override(self, global_settings_handler, sample_sensors):
        """Test updating global settings overrides existing values."""
        updates = {"device_class": "energy"}

        await global_settings_handler.async_update_global_settings(updates, sample_sensors)

        # Verify override occurred
        expected_settings = {
            "variables": {"global_temp": "sensor.temperature"},
            "device_class": "energy",  # Overridden
        }

        assert global_settings_handler.storage_manager.data["sensor_sets"]["test_set"]["global_settings"] == expected_settings

    @pytest.mark.asyncio
    async def test_update_global_settings_nonexistent_sensor_set(self, mock_storage_manager, sample_sensors):
        """Test updating global settings for non-existent sensor set."""
        handler = SensorSetGlobalSettings(mock_storage_manager, "missing_set")

        with pytest.raises(ValueError, match="Sensor set missing_set does not exist"):
            await handler._update_global_settings({"test": "value"})


class TestModificationSupport:
    """Test modification workflow support methods."""

    def test_build_final_global_settings_no_change(self, global_settings_handler):
        """Test building final global settings with no modifications."""
        final_settings = global_settings_handler.build_final_global_settings(None)

        assert final_settings == {"variables": {"global_temp": "sensor.temperature"}, "device_class": "power"}

    def test_build_final_global_settings_with_modifications(self, global_settings_handler):
        """Test building final global settings with modifications."""
        modification_settings = {"variables": {"new_var": "sensor.new"}, "unit_of_measurement": "W"}

        final_settings = global_settings_handler.build_final_global_settings(modification_settings)

        expected_settings = {
            "variables": {"new_var": "sensor.new"},
            "device_class": "power",  # From existing global settings
            "unit_of_measurement": "W",
        }
        assert final_settings == expected_settings

    def test_update_global_variables_for_entity_changes(self, global_settings_handler):
        """Test updating global variables for entity ID changes."""
        variables = {"temp": "sensor.old_temperature", "humidity": "sensor.humidity", "pressure": "sensor.pressure"}

        entity_changes = {"sensor.old_temperature": "sensor.new_temperature", "sensor.pressure": "sensor.new_pressure"}

        updated_variables = global_settings_handler.update_global_variables_for_entity_changes(variables, entity_changes)

        expected = {
            "temp": "sensor.new_temperature",  # Changed
            "humidity": "sensor.humidity",  # Unchanged
            "pressure": "sensor.new_pressure",  # Changed
        }

        assert updated_variables == expected

    def test_update_global_variables_no_changes(self, global_settings_handler):
        """Test updating global variables with no entity changes."""
        variables = {"temp": "sensor.temperature", "humidity": "sensor.humidity"}

        updated_variables = global_settings_handler.update_global_variables_for_entity_changes(variables, {})

        assert updated_variables == variables

    def test_update_global_variables_non_entity_values(self, global_settings_handler):
        """Test updating global variables with non-entity values."""
        variables = {"temp": "sensor.temperature", "constant": 42, "factor": 1.5, "flag": True}

        entity_changes = {"sensor.temperature": "sensor.new_temp"}

        updated_variables = global_settings_handler.update_global_variables_for_entity_changes(variables, entity_changes)

        expected = {
            "temp": "sensor.new_temp",  # Changed
            "constant": 42,  # Unchanged
            "factor": 1.5,  # Unchanged
            "flag": True,  # Unchanged
        }

        assert updated_variables == expected


class TestStorageIntegration:
    """Test storage integration and data consistency."""

    @pytest.mark.asyncio
    async def test_storage_data_structure_consistency(self, global_settings_handler, sample_sensors):
        """Test that storage data structure is maintained correctly."""
        new_settings = {"variables": {"test": "sensor.test"}}

        await global_settings_handler.async_set_global_settings(new_settings, sample_sensors)

        # Verify data structure integrity
        sensor_set_data = global_settings_handler.storage_manager.data["sensor_sets"]["test_set"]
        assert "global_settings" in sensor_set_data
        assert sensor_set_data["global_settings"] == new_settings

    def test_handler_isolation(self, mock_storage_manager):
        """Test that handlers for different sensor sets are isolated."""
        handler1 = SensorSetGlobalSettings(mock_storage_manager, "test_set")
        handler2 = SensorSetGlobalSettings(mock_storage_manager, "empty_set")

        settings1 = handler1.get_global_settings()
        settings2 = handler2.get_global_settings()

        # Should be different
        assert settings1 != settings2
        assert len(settings1) > 0
        assert len(settings2) == 0

    @pytest.mark.asyncio
    async def test_concurrent_modifications(self, mock_storage_manager, sample_sensors):
        """Test handling of concurrent modifications to global settings."""
        handler1 = SensorSetGlobalSettings(mock_storage_manager, "test_set")
        handler2 = SensorSetGlobalSettings(mock_storage_manager, "test_set")

        # Both handlers should see the same initial state
        initial1 = handler1.get_global_settings()
        initial2 = handler2.get_global_settings()
        assert initial1 == initial2

        # Modify through one handler
        await handler1.async_set_global_settings({"new": "value"}, sample_sensors)

        # Other handler should see the change (since they share storage)
        updated2 = handler2.get_global_settings()
        assert updated2 == {"new": "value"}


class TestErrorHandling:
    """Test error handling in global settings operations."""

    def test_get_global_settings_corrupted_data(self, mock_storage_manager):
        """Test getting global settings with corrupted data structure."""
        # Corrupt the data structure
        mock_storage_manager.data["sensor_sets"]["test_set"] = "not_a_dict"

        handler = SensorSetGlobalSettings(mock_storage_manager, "test_set")

        # Should handle gracefully and return empty dict
        with pytest.raises(AttributeError):
            handler.get_global_settings()

    @pytest.mark.asyncio
    async def test_async_save_failure(self, global_settings_handler, sample_sensors):
        """Test handling of save failures."""
        global_settings_handler.storage_manager.async_save.side_effect = Exception("Save failed")

        with pytest.raises(Exception, match="Save failed"):
            await global_settings_handler.async_set_global_settings({"test": "value"}, sample_sensors)

    @pytest.mark.asyncio
    async def test_validation_with_none_sensors(self, global_settings_handler):
        """Test validation with None sensors list."""
        import pytest

        # Mock the validation to raise an error when called with None
        global_settings_handler.storage_manager.validate_no_global_conflicts.side_effect = TypeError(
            "Cannot validate with None sensors"
        )

        with pytest.raises(TypeError, match="Cannot validate with None sensors"):
            await global_settings_handler.async_set_global_settings({"test": "value"}, None)
