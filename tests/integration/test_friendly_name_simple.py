"""
Simple integration tests for the friendly name listener.

These tests verify the core functionality:
1. Storage updates when friendly names change
2. Sensor entities get updated
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from homeassistant.core import Event

from src.ha_synthetic_sensors.friendly_name_listener import FriendlyNameListener
from src.ha_synthetic_sensors.entity_change_handler import EntityChangeHandler


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = Mock()
    hass.states = Mock()
    hass.bus = Mock()
    hass.async_create_task = Mock(side_effect=lambda coro: coro)
    return hass


@pytest.fixture
def mock_storage_manager():
    """Create a mock storage manager."""
    storage_manager = Mock()
    storage_manager.data = {
        "sensors": {
            "test_sensor": {
                "config_data": {
                    "unique_id": "test_sensor",
                    "name": "Old Name Power Sensor",
                    "entity_id": "sensor.test_power",
                    "formula": "state * 1.0",
                    "variables": {"state": "sensor.test_power"},
                    "metadata": {"friendly_name": "Old Name Power Sensor"},
                },
                "sensor_set_id": "test_set",
            }
        },
        "sensor_sets": {"test_set": {"global_settings": {"name": "Old Name Device Sensors"}}},
    }
    storage_manager.async_save = AsyncMock()
    storage_manager.list_sensor_sets = Mock(return_value=[Mock(sensor_set_id="test_set")])

    # Mock sensor set
    mock_sensor_set = Mock()
    mock_sensor_set.is_entity_tracked = Mock(return_value=True)
    mock_sensor_set.get_tracked_entities = Mock(return_value={"sensor.test_power"})
    storage_manager.get_sensor_set = Mock(return_value=mock_sensor_set)

    return storage_manager


@pytest.fixture
def mock_entity_change_handler():
    """Create a mock entity change handler."""
    handler = Mock(spec=EntityChangeHandler)
    handler.handle_entity_id_change = Mock()
    return handler


@pytest.fixture
def listener(mock_hass, mock_storage_manager, mock_entity_change_handler):
    """Create a friendly name listener instance."""
    return FriendlyNameListener(mock_hass, mock_storage_manager, mock_entity_change_handler)


@pytest.mark.asyncio
async def test_friendly_name_change_updates_storage(listener, mock_storage_manager):
    """Test that friendly name changes update storage correctly."""

    # Verify initial state
    sensor_config = mock_storage_manager.data["sensors"]["test_sensor"]["config_data"]
    assert sensor_config["name"] == "Old Name Power Sensor"
    assert sensor_config["metadata"]["friendly_name"] == "Old Name Power Sensor"

    # Simulate a friendly name change
    await listener._async_process_friendly_name_change("sensor.test_power", "Old Name", "New Name")

    # Verify storage was updated
    assert sensor_config["name"] == "New Name Power Sensor"
    assert sensor_config["metadata"]["friendly_name"] == "New Name Power Sensor"

    # Verify global settings were updated
    global_settings = mock_storage_manager.data["sensor_sets"]["test_set"]["global_settings"]
    assert global_settings["name"] == "New Name Device Sensors"

    # Verify storage was saved
    mock_storage_manager.async_save.assert_called_once()


@pytest.mark.asyncio
async def test_friendly_name_change_updates_sensors(listener, mock_entity_change_handler):
    """Test that friendly name changes trigger sensor entity updates."""

    # Simulate a friendly name change
    await listener._async_process_friendly_name_change("sensor.test_power", "Old Name", "New Name")

    # Verify entity change handler was called to update sensor entities
    mock_entity_change_handler.handle_entity_id_change.assert_called_once_with("sensor.test_power", "sensor.test_power")


def test_sensor_references_entity(listener):
    """Test that sensor reference detection works correctly."""

    # Test direct entity_id reference
    sensor_config = {"entity_id": "sensor.test_power"}
    assert listener._sensor_references_entity(sensor_config, "sensor.test_power")
    assert not listener._sensor_references_entity(sensor_config, "sensor.other")

    # Test variables reference
    sensor_config = {"variables": {"power": "sensor.test_power", "other": "sensor.other"}}
    assert listener._sensor_references_entity(sensor_config, "sensor.test_power")
    assert listener._sensor_references_entity(sensor_config, "sensor.other")
    assert not listener._sensor_references_entity(sensor_config, "sensor.missing")

    # Test attributes variables reference
    sensor_config = {"attributes": {"efficiency": {"variables": {"input": "sensor.test_power"}}}}
    assert listener._sensor_references_entity(sensor_config, "sensor.test_power")
    assert not listener._sensor_references_entity(sensor_config, "sensor.other")


@pytest.mark.asyncio
async def test_listener_lifecycle(listener, mock_hass):
    """Test that the listener starts and stops correctly."""

    # Test start
    mock_hass.bus.async_listen = Mock(return_value=Mock())
    await listener.async_start()

    # Verify state change listener was registered
    mock_hass.bus.async_listen.assert_called_once_with("state_changed", listener._handle_state_changed)

    # Test stop
    await listener.async_stop()
    # Should not raise any errors


def test_get_stats(listener):
    """Test that stats are returned correctly."""
    stats = listener.get_stats()

    assert "is_listening" in stats
    assert "cached_friendly_names_count" in stats
    assert "tracked_entities" in stats
    assert isinstance(stats["cached_friendly_names_count"], int)
    assert isinstance(stats["tracked_entities"], list)
