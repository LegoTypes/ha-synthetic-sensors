"""
Minimal test to reproduce boolean False -> None issue.
Based on test_span_panel_variable_injection.py
"""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ha_synthetic_sensors import async_setup_synthetic_sensors
from ha_synthetic_sensors.storage_manager import StorageManager


class TestBooleanFalseIssue:
    """Test that demonstrates boolean False being converted to None."""

    @pytest.fixture
    def mock_states(self):
        """Mock states."""
        return {}

    @pytest.fixture
    def mock_hass(self, mock_states):
        """Mock Home Assistant instance."""
        hass = Mock()
        hass.states = Mock()
        hass.states.get = lambda entity_id: mock_states.get(entity_id)
        hass.data = {}
        return hass

    @pytest.fixture
    def mock_device_entry(self):
        """Mock device entry."""
        device_entry = Mock()
        device_entry.id = "test_device_id"
        device_entry.identifiers = {("test_domain", "test_device")}
        device_entry.manufacturer = "Test Manufacturer"
        device_entry.model = "Test Model"
        device_entry.name = "Test Device"
        return device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Mock device registry."""
        device_registry = Mock()
        device_registry.devices = Mock()  # Add missing devices attribute
        device_registry.async_get_device.return_value = mock_device_entry
        return device_registry

    @pytest.fixture
    def mock_entity_registry(self):
        """Create a mock entity registry."""

        class DynamicMockEntityRegistry:
            def __init__(self):
                self.entities = {}
                self._next_id = 1

            def register_entity(self, entity_id, unique_id, domain):
                """Register an entity in the mock registry."""
                entity = Mock()
                entity.entity_id = entity_id
                entity.unique_id = unique_id
                entity.domain = domain
                entity.id = f"entity_{self._next_id}"
                self._next_id += 1
                self.entities[entity_id] = entity
                return entity

            def async_get(self, entity_id):
                """Get entity from registry."""
                return self.entities.get(entity_id)

            def async_get_or_create(self, domain, platform, unique_id, suggested_object_id=None, **kwargs):
                """Get or create entity in registry."""
                entity_id = f"{domain}.{suggested_object_id or unique_id}"
                if entity_id not in self.entities:
                    self.register_entity(entity_id, unique_id, domain)
                entity = self.entities[entity_id]
                entity.entity_id = entity_id
                return entity

        return DynamicMockEntityRegistry()

    @pytest.fixture
    def mock_config_entry(self):
        """Mock config entry."""
        config_entry = Mock()
        config_entry.entry_id = "test_entry_id"
        config_entry.domain = "synthetic_sensors"
        config_entry.data = {}
        config_entry.options = {}
        return config_entry

    @pytest.fixture
    def mock_async_add_entities(self):
        """Mock async_add_entities."""
        return AsyncMock()

    @pytest.fixture
    def yaml_path(self):
        """Path to test YAML file."""
        return Path(__file__).parent.parent / "yaml_fixtures" / "test_minimal_boolean_issue.yaml"

    @pytest.mark.asyncio
    async def test_boolean_false_becomes_none(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test that boolean False in computed variables becomes None."""

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
            patch("homeassistant.helpers.entity_registry.async_get") as MockEntityRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            MockDeviceRegistry.return_value = mock_device_registry
            MockEntityRegistry.return_value = mock_entity_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load YAML configuration
            sensor_set_id = "test_boolean_issue"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_boolean_issue",
                name="Test Boolean Issue",
            )

            with open(yaml_path) as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1

            # Set up synthetic sensors via public API
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
            )

            # Get the created sensor entities
            added_entities = mock_async_add_entities.call_args[0][0]
            assert len(added_entities) == 1

            test_sensor = added_entities[0]

            # Set up the mock state object for this sensor with the attributes that metadata() calls will look for
            mock_state = Mock()
            mock_state.entity_id = test_sensor.entity_id
            mock_state.state = "test"
            mock_state.attributes = {
                "last_valid_state": "3759.32",
                "last_valid_changed": "2025-01-01T11:30:00+00:00",
                "dependencies": ["test"],
                "formula": "'test'",
            }
            mock_state.last_changed = "2025-01-01T11:30:00+00:00"
            mock_state.last_updated = "2025-01-01T11:30:00+00:00"

            # Add the mock state to the mock states dict so metadata() calls can find it
            print(f"\n=== DEBUG: Setting up mock state for entity_id: {test_sensor.entity_id} ===")
            mock_states[test_sensor.entity_id] = mock_state
            print(f"Mock states now contains: {list(mock_states.keys())}")

            # Test the mock hass.states.get() method
            retrieved_state = mock_hass.states.get(test_sensor.entity_id)
            print(f"Retrieved state: {retrieved_state}")
            if retrieved_state:
                print(f"Retrieved state attributes: {retrieved_state.attributes}")
                print(f"last_valid_state attribute: {retrieved_state.attributes.get('last_valid_state')}")

            # Now evaluate the sensor
            await test_sensor.async_update()

            # Get the attributes
            attributes = test_sensor.extra_state_attributes

            print("\n=== ATTRIBUTE VALUES ===")
            print(f"last_valid_state_value: {attributes.get('last_valid_state_value')}")
            print(f"last_valid_changed_value: {attributes.get('last_valid_changed_value')}")
            print(f"direct_metadata_test: {attributes.get('direct_metadata_test')}")
            print(f"panel_status_value: {attributes.get('panel_status_value')}")
            print(f"panel_offline_minutes_value: {attributes.get('panel_offline_minutes_value')}")
            print(f"is_within_grace_period_value: {attributes.get('is_within_grace_period_value')}")
            print(f"test_result: {attributes.get('test_result')}")

            # Test the simplified boolean logic
            assert attributes.get("panel_status_value") is False
            assert attributes.get("panel_offline_minutes_value") == 20.0

            # The issue: is_within_grace_period should be False but might be None
            # The formula: not False and 20 < 15
            # Should be: True and False = False
            assert attributes.get("is_within_grace_period_value") is False, (
                f"Expected False for is_within_grace_period, got {attributes.get('is_within_grace_period_value')}"
            )

            # test_result references is_within_grace_period, so should also be False
            assert attributes.get("test_result") is False, f"Expected False, got {attributes.get('test_result')}"
