"""Test to isolate the timestamp variable reference bug."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from homeassistant.const import STATE_OFF
from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


class TestTimestampVariableBug:
    """Test class to isolate the timestamp variable reference bug."""

    def create_mock_state(self, state_value, attributes=None, entity_id=None):
        """Create a mock state object with proper structure for metadata handler."""
        # Use spec to prevent Mock from creating new attributes automatically
        mock_state = Mock(spec=["state", "attributes", "entity_id", "last_changed", "last_updated"])
        mock_state.state = state_value
        mock_state.attributes = attributes or {}
        mock_state.entity_id = entity_id
        return mock_state

    @pytest.mark.asyncio
    async def test_timestamp_variable_reference_bug(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test that demonstrates the timestamp variable reference bug."""

        # Create a test with a metadata variable used in another formula - this should reproduce the bug
        yaml_content = """
version: "1.0"

global_settings:
  device_identifier: "test_timestamp_bug"

sensors:
  test_timestamp_bug:
    name: "Test Timestamp Bug"
    formula: "other_var"
    variables:
      my_timestamp:
        formula: "metadata(state, 'last_valid_changed')"
        alternate_states:
          FALLBACK: unknown
      other_var:
        formula: "my_timestamp"
        alternate_states:
          FALLBACK: null
"""

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
            sensor_set_id = "timestamp_bug_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_timestamp_bug",
                name="Timestamp Bug Test Sensors",
            )

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

            # Set hass reference and add to mock state registry
            test_sensor.hass = mock_hass

            # Create a mock state for the synthetic sensor with engine-managed attributes
            sensor_attributes = dict(test_sensor.extra_state_attributes or {})

            # Add the engine-managed attributes that should be available for metadata() calls
            # This simulates what our fix in sensor_manager.py does
            if "last_valid_changed" not in sensor_attributes:
                from datetime import datetime as dt, timezone as tz

                sensor_attributes["last_valid_changed"] = dt.now(tz.utc).isoformat()

            synthetic_sensor_state = self.create_mock_state(
                test_sensor.native_value,
                sensor_attributes,
                entity_id=test_sensor.entity_id,
            )
            mock_states[test_sensor.entity_id] = synthetic_sensor_state

            # This should trigger the bug where the timestamp gets treated as a variable reference
            await test_sensor.async_update()

            # Assert that the sensor state is the timestamp string, not None or an error
            assert test_sensor.native_value is not None, "Sensor state should not be None"
            assert isinstance(test_sensor.native_value, str), f"Expected string timestamp, got {type(test_sensor.native_value)}"
            assert "T" in test_sensor.native_value, f"Expected ISO timestamp format, got: {test_sensor.native_value}"

            print(f"✅ Test passed - Sensor state: {test_sensor.native_value}")
            print(f"✅ Test passed - Sensor attributes: {test_sensor.extra_state_attributes}")
