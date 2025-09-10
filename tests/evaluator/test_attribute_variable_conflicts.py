"""Tests for attribute variable conflicts and validation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ha_synthetic_sensors.exceptions import SyntheticSensorsError
from ha_synthetic_sensors.storage_manager import StorageManager


class TestAttributeVariableConflicts:
    """Test attribute variable conflict validation."""

    @pytest.fixture
    def storage_manager(self, mock_hass):
        """Create a StorageManager instance for testing with mocked Store."""
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store

            manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            # Set up the mock store
            manager._store = mock_store
            return manager

    async def test_attribute_vs_sensor_variable_conflict(self, storage_manager, mock_entity_registry):
        """Test attribute variables with sensor variables (current implementation merges them)."""

        fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "attribute_vs_sensor_variable_conflict.yaml"
        with open(fixture_path) as f:
            yaml_content = f.read()

        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            # Current implementation merges attribute variables into sensor variables
            # so no conflict is detected - this test verifies the current behavior
            result = await storage_manager.async_from_yaml(yaml_content, "test_set")

            # Verify the YAML was loaded successfully
            assert result["sensor_set_id"] == "test_set"
            assert result["sensors_imported"] == 1
            assert result["sensor_unique_ids"] == ["test_sensor"]

    async def test_attribute_vs_global_variable_conflict(self, storage_manager, mock_entity_registry):
        """Test if attribute variables are validated against global variables."""

        fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "attribute_vs_global_variable_conflict.yaml"
        with open(fixture_path) as f:
            yaml_content = f.read()

        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            # Test if conflicts are properly caught
            with pytest.raises(SyntheticSensorsError, match=".*conflict.*|.*override.*|.*different.*"):
                await storage_manager.async_from_yaml(yaml_content, "test_set")

    async def test_complex_variable_hierarchy_conflicts(self, storage_manager, mock_entity_registry):
        """Test complex scenarios with multiple conflict types."""

        fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "complex_variable_hierarchy_conflicts.yaml"
        with open(fixture_path) as f:
            yaml_content = f.read()

        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            # Test if conflicts are properly caught
            with pytest.raises(SyntheticSensorsError, match=".*conflict.*|.*override.*|.*different.*"):
                await storage_manager.async_from_yaml(yaml_content, "test_set")

    async def test_valid_attribute_variables(self, storage_manager, mock_entity_registry):
        """Test that valid attribute variable usage is allowed."""

        fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "attribute_variable_conflicts_valid.yaml"
        with open(fixture_path) as f:
            yaml_content = f.read()

        with patch.object(storage_manager._store, "async_load", return_value=None):
            await storage_manager.async_load()

            # This should NOT raise an error - valid configurations should work
            try:
                await storage_manager.async_from_yaml(yaml_content, "test_set")
            except SyntheticSensorsError as e:
                pytest.fail(f"Valid configuration was rejected: {e}")
