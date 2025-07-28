"""Integration tests for YAML parser functionality using public API."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

# Use public API imports as shown in integration guide
from ha_synthetic_sensors import (
    async_setup_synthetic_sensors,
    StorageManager,
)


class TestYAMLParserIntegration:
    """Integration tests for YAML parser through the public API."""

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback."""
        return Mock()

    @pytest.fixture
    def mock_device_registry(self):
        """Create a mock device registry."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    async def test_yaml_parser_comprehensive_features(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test YAML parser with comprehensive feature coverage."""
        # Set up mock HA states for external entities
        mock_states["sensor.device_power"] = type("MockState", (), {"state": "500.0", "attributes": {}})()

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set and load comprehensive YAML
            sensor_set_id = "yaml_parser_comprehensive_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="YAML Parser Comprehensive Test"
            )

            yaml_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "yaml_parser_edge_cases.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3

            # Set up sensor manager to test YAML parsing features
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
                allow_ha_lookups=True,  # Enable HA lookups for YAML parser tests
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test YAML parsing through evaluation
            await sensor_manager.async_update_sensors()

            # Verify YAML parser handled all features correctly
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Verify sensor with explicit entity_id override
            parser_test_sensor = next((s for s in sensors if s.unique_id == "yaml_parser_test_sensor"), None)
            assert parser_test_sensor is not None
            assert parser_test_sensor.entity_id == "sensor.custom_yaml_parser_entity"
            assert len(parser_test_sensor.formulas) >= 5  # Main + 4 attributes

            # Verify minimal sensor
            minimal_sensor = next((s for s in sensors if s.unique_id == "minimal_sensor"), None)
            assert minimal_sensor is not None

            # Verify device association sensor
            device_sensor = next((s for s in sensors if s.unique_id == "device_association_sensor"), None)
            assert device_sensor is not None
            assert device_sensor.device_identifier == "test_device_123"  # Inherited from global settings
            assert device_sensor.device_name == "Custom Test Device"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_yaml_parser_literal_value_handling(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test YAML parser handling of different literal value types."""
        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set and load literal value YAML
            sensor_set_id = "yaml_literal_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="YAML Literal Test"
            )

            yaml_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "yaml_parser_edge_cases.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3

            # Verify literal value parsing
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            parser_test_sensor = next((s for s in sensors if s.unique_id == "yaml_parser_test_sensor"), None)
            assert parser_test_sensor is not None

            # Verify literal attributes were parsed correctly
            # The parser should handle string, numeric, and boolean literals
            # Literal attributes are stored as formulas with their literal values
            all_formula_ids = [f.id for f in parser_test_sensor.formulas]

            # Check that literal attributes exist (formula IDs include sensor prefix)
            computed_formula = next(
                (f for f in parser_test_sensor.formulas if f.id == "yaml_parser_test_sensor_computed_attribute"), None
            )
            assert computed_formula is not None, f"Expected computed_attribute formula. Found: {all_formula_ids}"

            # Verify literal attributes were parsed correctly
            literal_attribute = next(
                (f for f in parser_test_sensor.formulas if f.id == "yaml_parser_test_sensor_literal_attribute"), None
            )
            numeric_literal = next(
                (f for f in parser_test_sensor.formulas if f.id == "yaml_parser_test_sensor_numeric_literal"), None
            )
            boolean_literal = next(
                (f for f in parser_test_sensor.formulas if f.id == "yaml_parser_test_sensor_boolean_literal"), None
            )
            negative_literal = next(
                (f for f in parser_test_sensor.formulas if f.id == "yaml_parser_test_sensor_negative_literal"), None
            )

            assert literal_attribute is not None, "String literal attribute should be parsed"
            assert numeric_literal is not None, "Numeric literal attribute should be parsed"
            assert boolean_literal is not None, "Boolean literal attribute should be parsed"
            assert negative_literal is not None, "Negative literal attribute should be parsed"

            # Verify we have all expected formulas: main + computed + 4 literals = 6 total
            assert len(parser_test_sensor.formulas) == 6, (
                f"Expected 6 formulas, got {len(parser_test_sensor.formulas)} with IDs: {all_formula_ids}"
            )

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)
