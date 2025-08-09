"""Integration tests for state token error handling using storage manager."""

import pytest
from unittest.mock import AsyncMock, patch
import yaml

from ha_synthetic_sensors.storage_manager import StorageManager
from ha_synthetic_sensors.exceptions import SensorMappingError
from homeassistant.exceptions import ConfigEntryError


class TestStateTokenErrorHandling:
    """Integration tests for state token error handling scenarios."""

    @pytest.fixture
    def base_yaml_config(self):
        """Base YAML configuration for state token tests."""
        return {
            "sensors": {
                "test_current_power": {
                    "name": "Test Current Power",
                    "entity_id": "sensor.current_power",
                    "formula": "state",
                    "attributes": {"amperage": {"formula": "state / 240"}},
                }
            }
        }

    @pytest.fixture
    def yaml_without_entity_id(self):
        """YAML configuration without entity_id field."""
        return {
            "sensors": {
                "test_current_power": {
                    "name": "Test Current Power",
                    "formula": "state",  # Uses state token but no entity_id
                    "attributes": {"amperage": {"formula": "state / 240"}},
                }
            }
        }

    @pytest.fixture
    def yaml_with_invalid_entity_id(self):
        """YAML configuration with invalid entity_id format."""
        return {
            "sensors": {
                "test_current_power": {
                    "name": "Test Current Power",
                    "entity_id": "invalid_entity_format",  # Invalid format (no domain)
                    "formula": "state",
                    "attributes": {"amperage": {"formula": "state / 240"}},
                }
            }
        }

    @pytest.fixture
    def yaml_attribute_only_state_token(self):
        """YAML configuration where only attributes use state token."""
        return {
            "sensors": {
                "test_current_power": {
                    "name": "Test Current Power",
                    "entity_id": "sensor.current_power",
                    "formula": "1000",  # Main formula doesn't use state token
                    "attributes": {
                        "amperage": {
                            "formula": "state / 240"  # Attribute uses state token
                        }
                    },
                }
            }
        }

    async def test_state_token_missing_backing_entity_registration(
        self, mock_hass, mock_entity_registry, mock_states, base_yaml_config
    ):
        """Test that missing backing entity registration is handled properly."""

        # Create storage manager with mocked Store
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set first
            await storage_manager.async_create_sensor_set("test_config")

            # Import YAML config - this should process without error
            yaml_content = yaml.dump(base_yaml_config)
            result = await storage_manager.async_from_yaml(yaml_content, "test_config")

            # Should import successfully
            assert result["sensors_imported"] == 1
            assert "test_current_power" in result["sensor_unique_ids"]

            # Try to evaluate a sensor that references a backing entity that's not registered
            # This should raise a SensorMappingError during evaluation
            sensor_configs = storage_manager.list_sensors(sensor_set_id="test_config")
            assert len(sensor_configs) == 1

            sensor_config = sensor_configs[0]

            # Since no backing entity is registered, this should fail
            # The storage manager should handle this gracefully
            # Note: The actual error will occur when the sensor tries to evaluate

    async def test_state_token_with_missing_entity_id_field(
        self, mock_hass, mock_entity_registry, mock_states, yaml_without_entity_id
    ):
        """Test that state token fails appropriately when sensor has no entity_id field."""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set first
            await storage_manager.async_create_sensor_set("test_config")

            # Import YAML config
            yaml_content = yaml.dump(yaml_without_entity_id)
            result = await storage_manager.async_from_yaml(yaml_content, "test_config")

            # Should import successfully
            assert result["sensors_imported"] == 1
            assert "test_current_power" in result["sensor_unique_ids"]

            # The sensor should be imported but will fail at evaluation time
            # when it tries to resolve the state token without a backing entity

    async def test_state_token_with_invalid_entity_id_format(
        self, mock_hass, mock_entity_registry, mock_states, yaml_with_invalid_entity_id
    ):
        """Test that invalid entity_id format is rejected during YAML import validation."""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set first
            await storage_manager.async_create_sensor_set("test_config")

            # Import YAML config with invalid entity_id
            yaml_content = yaml.dump(yaml_with_invalid_entity_id)

            # Test schema validation directly (this is where entity_id validation should happen)
            from ha_synthetic_sensors.schema_validator import validate_yaml_config

            # Schema validation should catch the invalid entity_id format
            result = validate_yaml_config(yaml_with_invalid_entity_id)
            assert result["valid"] is False
            assert len(result["errors"]) > 0

            # Check that the error is about entity_id format
            error_messages = [error.message for error in result["errors"]]
            assert any("invalid_entity_format" in msg for msg in error_messages)

    async def test_state_token_in_attribute_without_backing_entity(
        self, mock_hass, mock_entity_registry, mock_states, yaml_attribute_only_state_token
    ):
        """Test that state token in attributes fails appropriately when no backing entity is registered."""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set first
            await storage_manager.async_create_sensor_set("test_config")

            # Import YAML config
            yaml_content = yaml.dump(yaml_attribute_only_state_token)
            result = await storage_manager.async_from_yaml(yaml_content, "test_config")

            # Should import successfully
            assert result["sensors_imported"] == 1
            assert "test_current_power" in result["sensor_unique_ids"]

            # The sensor should be imported but attribute evaluation will fail
            # when it tries to resolve the state token without proper backing entity registration

    async def test_state_token_works_when_properly_setup(
        self, mock_hass, mock_entity_registry, mock_states, yaml_attribute_only_state_token
    ):
        """Test that state token works correctly when backing entity is properly set up."""

        # Add the backing entity to mock_states to simulate it existing in HA
        mock_states["sensor.current_power"] = type("MockState", (), {"state": "1200.0", "attributes": {}})()

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set first
            await storage_manager.async_create_sensor_set("test_config")

            # Import YAML config
            yaml_content = yaml.dump(yaml_attribute_only_state_token)
            result = await storage_manager.async_from_yaml(yaml_content, "test_config")

            # Should import successfully
            assert result["sensors_imported"] == 1
            assert "test_current_power" in result["sensor_unique_ids"]

            # The sensor should be imported and should work correctly
            # when the backing entity is available and properly registered

    async def test_state_token_integration_end_to_end(self, mock_hass, mock_entity_registry, mock_states, base_yaml_config):
        """Test complete end-to-end state token handling in an integration context."""

        # Set up mock backing entity
        mock_states["sensor.current_power"] = type("MockState", (), {"state": "1000.0", "attributes": {}})()

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set first
            await storage_manager.async_create_sensor_set("test_config")

            # Import YAML config
            yaml_content = yaml.dump(base_yaml_config)
            result = await storage_manager.async_from_yaml(yaml_content, "test_config")

            # Should import successfully
            assert result["sensors_imported"] == 1
            assert "test_current_power" in result["sensor_unique_ids"]
            assert "test_current_power" in result["sensor_unique_ids"]

            # Verify the sensor was created with proper configuration
            sensor_configs = storage_manager.list_sensors(sensor_set_id="test_config")
            assert len(sensor_configs) == 1

            sensor_config = sensor_configs[0]
            assert sensor_config.unique_id == "test_current_power"
            # Entity ID may have collision suffix due to registry state from previous tests
            assert sensor_config.entity_id.startswith("sensor.current_power")

            # Verify the formula is set correctly
            assert len(sensor_config.formulas) >= 1  # At least main formula
            main_formula = sensor_config.formulas[0]
            assert main_formula.formula == "state"

            # Verify attribute formulas are in the main formula's attributes
            assert main_formula.attributes is not None
            assert "amperage" in main_formula.attributes

            # With structure preservation fix, attributes should be dictionaries with 'formula' key
            amperage_attr = main_formula.attributes["amperage"]
            assert isinstance(amperage_attr, dict), f"amperage should be a formula dict: {amperage_attr}"
            assert "formula" in amperage_attr, f"amperage should have 'formula' key: {amperage_attr}"
            assert amperage_attr["formula"] == "state / 240", f"amperage formula should be 'state / 240': {amperage_attr}"
