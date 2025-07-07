"""Test to check if attribute variable conflicts are properly validated."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ha_synthetic_sensors.exceptions import SyntheticSensorsError
from src.ha_synthetic_sensors.storage_manager import StorageManager


class TestAttributeVariableConflicts:
    """Test attribute variable conflict validation."""

    @pytest.fixture
    def mock_hass(self):
        """Mock Home Assistant instance."""
        hass = MagicMock()
        hass.config.config_dir = "/tmp"
        hass.data = {}  # Storage system needs this
        return hass

    @pytest.fixture
    def storage_manager(self, mock_hass):
        """Create a StorageManager instance for testing with mocked Store."""
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store

            manager = StorageManager(mock_hass, "test_storage")
            # Set up the mock store
            manager._store = mock_store
            return manager

    async def test_attribute_vs_sensor_variable_conflict(self, storage_manager):
        """Test if attribute variables are validated against sensor variables."""

        with open("tests/yaml_fixtures/attribute_vs_sensor_variable_conflict.yaml") as f:
            yaml_content = f.read()

        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            # Test if conflicts are properly caught
            with pytest.raises(SyntheticSensorsError, match=".*conflicting variable.*"):
                await storage_manager.async_from_yaml(yaml_content, "test_set")

    async def test_attribute_vs_global_variable_conflict(self, storage_manager):
        """Test if attribute variables are validated against global variables."""

        with open("tests/yaml_fixtures/attribute_vs_global_variable_conflict.yaml") as f:
            yaml_content = f.read()

        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            # Test if conflicts are properly caught
            with pytest.raises(SyntheticSensorsError, match=".*conflict.*|.*override.*|.*different.*"):
                await storage_manager.async_from_yaml(yaml_content, "test_set")

    async def test_complex_variable_hierarchy_conflicts(self, storage_manager):
        """Test complex scenarios with multiple conflict types."""

        with open("tests/yaml_fixtures/complex_variable_hierarchy_conflicts.yaml") as f:
            yaml_content = f.read()

        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            # Test if conflicts are properly caught
            with pytest.raises(SyntheticSensorsError, match=".*conflict.*|.*override.*|.*different.*"):
                await storage_manager.async_from_yaml(yaml_content, "test_set")

    async def test_valid_attribute_variables(self, storage_manager):
        """Test that valid attribute variable usage is allowed."""

        with open("tests/yaml_fixtures/attribute_variable_conflicts_valid.yaml") as f:
            yaml_content = f.read()

        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            # This should NOT raise an error - valid configurations should work
            try:
                await storage_manager.async_from_yaml(yaml_content, "test_set")
            except SyntheticSensorsError as e:
                pytest.fail(f"Valid configuration was rejected: {e}")
