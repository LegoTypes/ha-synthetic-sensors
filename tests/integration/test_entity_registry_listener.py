"""Tests for EntityRegistryListener."""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from homeassistant.core import Event
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED

from ha_synthetic_sensors.entity_change_handler import EntityChangeHandler
from ha_synthetic_sensors.entity_registry_listener import EntityRegistryListener


class TestEntityRegistryListener:
    """Test cases for EntityRegistryListener."""

    @pytest.fixture
    def mock_storage_manager(self):
        """Create a mock storage manager."""
        storage_manager = MagicMock()
        storage_manager.list_sensor_sets = MagicMock(return_value=[])
        storage_manager.get_sensor_set = MagicMock()
        storage_manager._ensure_loaded = MagicMock(return_value={"sensors": {}, "sensor_sets": {}})
        storage_manager._deserialize_sensor_config = MagicMock()
        storage_manager._serialize_sensor_config = MagicMock()
        storage_manager._get_timestamp = MagicMock(return_value="2024-01-01T00:00:00Z")
        storage_manager.async_save = AsyncMock()
        return storage_manager

    @pytest.fixture
    def mock_entity_change_handler(self):
        """Create a mock entity change handler."""
        handler = MagicMock(spec=EntityChangeHandler)
        handler.register_integration_callback = MagicMock()
        handler.unregister_integration_callback = MagicMock()
        handler.handle_entity_id_change = MagicMock()
        handler.get_stats = MagicMock(return_value={})
        return handler

    @pytest.fixture
    def listener(self, mock_hass, mock_storage_manager, mock_entity_change_handler):
        """Create an EntityRegistryListener instance for testing."""
        return EntityRegistryListener(mock_hass, mock_storage_manager, mock_entity_change_handler)

    def test_initialization(
        self, mock_hass, mock_entity_registry, mock_states, listener, mock_storage_manager, mock_entity_change_handler
    ):
        """Test EntityRegistryListener initialization."""
        assert listener.hass == mock_hass
        assert listener.storage_manager == mock_storage_manager
        assert listener.entity_change_handler == mock_entity_change_handler
        assert listener._unsub_registry is None
        assert listener._logger is not None

    async def test_async_start(self, mock_hass, mock_entity_registry, mock_states, listener):
        """Test starting the entity registry listener."""
        await listener.async_start()

        mock_hass.bus.async_listen.assert_called_once_with(
            EVENT_ENTITY_REGISTRY_UPDATED, listener._handle_entity_registry_updated
        )
        assert listener._unsub_registry is not None

    async def test_async_start_already_started(self, mock_hass, mock_entity_registry, mock_states, listener):
        """Test starting the listener when it's already started."""
        await listener.async_start()
        mock_hass.bus.async_listen.reset_mock()

        # Start again - should log warning and not re-register
        await listener.async_start()
        mock_hass.bus.async_listen.assert_not_called()

    async def test_async_stop(self, mock_hass, mock_entity_registry, mock_states, listener):
        """Test stopping the entity registry listener."""
        # Start first
        await listener.async_start()
        unsub_mock = listener._unsub_registry

        # Now stop
        await listener.async_stop()

        unsub_mock.assert_called_once()
        assert listener._unsub_registry is None

    async def test_async_stop_not_started(self, mock_hass, mock_entity_registry, mock_states, listener):
        """Test stopping the listener when it's not started."""
        # Should not raise an error
        await listener.async_stop()
        assert listener._unsub_registry is None

    def test_add_entity_change_callback(
        self, mock_hass, mock_entity_registry, mock_states, listener, mock_entity_change_handler
    ):
        """Test adding an entity change callback."""
        callback = Mock()

        listener.add_entity_change_callback(callback)

        mock_entity_change_handler.register_integration_callback.assert_called_once_with(callback)

    def test_remove_entity_change_callback(
        self, mock_hass, mock_entity_registry, mock_states, listener, mock_entity_change_handler
    ):
        """Test removing an entity change callback."""
        callback = Mock()

        listener.remove_entity_change_callback(callback)

        mock_entity_change_handler.unregister_integration_callback.assert_called_once_with(callback)

    def test_handle_entity_registry_updated_non_update_action(self, mock_hass, mock_entity_registry, mock_states, listener):
        """Test handling entity registry event with non-update action."""

        # Mock async_create_task to properly handle coroutines
        def mock_async_create_task(coro):
            if hasattr(coro, "close"):
                coro.close()
            return Mock()

        with patch.object(listener.hass, "async_create_task", side_effect=mock_async_create_task) as mock_create_task:
            event = Event("entity_registry_updated", {"action": "create"})

            # Should return early and not process
            listener._handle_entity_registry_updated(event)

            # No task should be created
            mock_create_task.assert_not_called()

    def test_handle_entity_registry_updated_no_entity_id_change(self, mock_hass, mock_entity_registry, mock_states, listener):
        """Test handling entity registry event with no entity_id change."""

        # Mock async_create_task to properly handle coroutines
        def mock_async_create_task(coro):
            if hasattr(coro, "close"):
                coro.close()
            return Mock()

        with patch.object(listener.hass, "async_create_task", side_effect=mock_async_create_task) as mock_create_task:
            event = Event(
                "entity_registry_updated", {"action": "update", "changes": {"name": {"old": "Old Name", "new": "New Name"}}}
            )

            # Should return early and not process
            listener._handle_entity_registry_updated(event)

            # No task should be created
            mock_create_task.assert_not_called()

    def test_handle_entity_registry_updated_entity_not_tracked(
        self, mock_hass, mock_entity_registry, mock_states, listener, mock_storage_manager
    ):
        """Test handling entity registry event for entity that's not tracked."""

        # Mock async_create_task to properly handle coroutines
        def mock_async_create_task(coro):
            if hasattr(coro, "close"):
                coro.close()
            return Mock()

        with patch.object(listener.hass, "async_create_task", side_effect=mock_async_create_task) as mock_create_task:
            # Setup mock to return no tracked entities
            mock_sensor_set_metadata = MagicMock()
            mock_sensor_set_metadata.sensor_set_id = "test_set"
            mock_storage_manager.list_sensor_sets.return_value = [mock_sensor_set_metadata]

            mock_sensor_set = MagicMock()
            mock_sensor_set.is_entity_tracked.return_value = False
            mock_storage_manager.get_sensor_set.return_value = mock_sensor_set

            event = Event(
                "entity_registry_updated",
                {"action": "update", "changes": {"entity_id": {"old": "sensor.old", "new": "sensor.new"}}},
            )

            listener._handle_entity_registry_updated(event)

            # No task should be created since entity is not tracked
            mock_create_task.assert_not_called()

    def test_handle_entity_registry_updated_entity_tracked(
        self, mock_hass, mock_entity_registry, mock_states, listener, mock_storage_manager
    ):
        """Test handling entity registry event for tracked entity."""

        # Mock async_create_task to properly handle coroutines
        def mock_async_create_task(coro):
            if hasattr(coro, "close"):
                coro.close()
            return Mock()

        with patch.object(listener.hass, "async_create_task", side_effect=mock_async_create_task) as mock_create_task:
            # Setup mock to return tracked entity
            mock_sensor_set_metadata = MagicMock()
            mock_sensor_set_metadata.sensor_set_id = "test_set"
            mock_storage_manager.list_sensor_sets.return_value = [mock_sensor_set_metadata]

            mock_sensor_set = MagicMock()
            mock_sensor_set.is_entity_tracked.return_value = True
            mock_storage_manager.get_sensor_set.return_value = mock_sensor_set

            event = Event(
                "entity_registry_updated",
                {"action": "update", "changes": {"entity_id": {"old": "sensor.old", "new": "sensor.new"}}},
            )

            listener._handle_entity_registry_updated(event)

            # Task should be created to process the change
            mock_create_task.assert_called_once()

    def test_handle_entity_registry_updated_exception(self, mock_hass, mock_entity_registry, mock_states, listener):
        """Test handling entity registry event when an exception occurs."""

        # Mock async_create_task to properly handle coroutines to avoid RuntimeWarning
        def mock_async_create_task(coro):
            # If it's a coroutine, close it to avoid the warning
            if hasattr(coro, "close"):
                coro.close()
            # Return a mock task
            mock_task = Mock()
            mock_task.done.return_value = True
            mock_task.cancelled.return_value = False
            mock_task.exception.return_value = None
            return mock_task

        with patch.object(listener.hass, "async_create_task", side_effect=mock_async_create_task) as mock_create_task:
            # Mock _is_entity_tracked to raise an exception BEFORE it gets to async_create_task
            with patch.object(listener, "_is_entity_tracked", side_effect=Exception("Test exception")):
                # Create valid event data that will trigger the _is_entity_tracked call
                event = Event(
                    "entity_registry_updated",
                    {"action": "update", "changes": {"entity_id": {"old": "sensor.old", "new": "sensor.new"}}},
                )

                # Should not raise an error, but log it and not create any async tasks
                listener._handle_entity_registry_updated(event)

                # No task should be created because the exception should be caught
                mock_create_task.assert_not_called()

    async def test_async_process_entity_id_change_success(
        self, mock_hass, mock_entity_registry, mock_states, listener, mock_entity_change_handler
    ):
        """Test successful processing of entity ID change."""
        with patch.object(listener, "_update_storage_entity_ids", new_callable=AsyncMock) as mock_update:
            await listener._async_process_entity_id_change("sensor.old", "sensor.new")

            mock_update.assert_called_once_with("sensor.old", "sensor.new")
            mock_entity_change_handler.handle_entity_id_change.assert_called_once_with("sensor.old", "sensor.new")

    async def test_async_process_entity_id_change_exception(self, mock_hass, mock_entity_registry, mock_states, listener):
        """Test processing entity ID change when an exception occurs."""
        with patch.object(listener, "_update_storage_entity_ids", new_callable=AsyncMock) as mock_update:
            mock_update.side_effect = Exception("Storage update failed")

            # Should not raise an error, but log it
            await listener._async_process_entity_id_change("sensor.old", "sensor.new")

            mock_update.assert_called_once_with("sensor.old", "sensor.new")

    async def test_update_storage_entity_ids_no_changes(
        self, mock_hass, mock_entity_registry, mock_states, listener, mock_storage_manager
    ):
        """Test updating storage when no changes are needed."""
        # Setup empty storage data
        mock_storage_manager.data = {"sensors": {}, "sensor_sets": {}}

        await listener._update_storage_entity_ids("sensor.old", "sensor.new")

        # No save should be called
        mock_storage_manager.async_save.assert_not_called()

    async def test_update_storage_entity_ids_sensor_entity_id_change(
        self, mock_hass, mock_entity_registry, mock_states, listener, mock_storage_manager
    ):
        """Test updating storage when sensor entity_id changes."""
        # Setup storage data with sensor config in the format the method actually processes
        storage_data = {
            "sensors": {"test_sensor": {"config_data": {"entity_id": "sensor.old", "formulas": []}}},
            "sensor_sets": {},
        }
        mock_storage_manager.data = storage_data

        await listener._update_storage_entity_ids("sensor.old", "sensor.new")

        # Verify entity_id was updated in the storage data
        assert storage_data["sensors"]["test_sensor"]["config_data"]["entity_id"] == "sensor.new"

        # Verify save was called
        mock_storage_manager.async_save.assert_called_once()

    async def test_update_storage_entity_ids_formula_variable_change(
        self, mock_hass, mock_entity_registry, mock_states, listener, mock_storage_manager
    ):
        """Test updating storage when formula variable changes."""
        # Setup storage data with sensor config containing formula variables in the format the method actually processes
        storage_data = {
            "sensors": {
                "test_sensor": {
                    "config_data": {"entity_id": "sensor.different", "formulas": [{"variables": {"power_meter": "sensor.old"}}]}
                }
            },
            "sensor_sets": {},
        }
        mock_storage_manager.data = storage_data

        await listener._update_storage_entity_ids("sensor.old", "sensor.new")

        # Verify variable was updated in the storage data
        assert storage_data["sensors"]["test_sensor"]["config_data"]["formulas"][0]["variables"]["power_meter"] == "sensor.new"

        # Verify save was called
        mock_storage_manager.async_save.assert_called_once()

    async def test_update_storage_entity_ids_global_variable_change(
        self, mock_hass, mock_entity_registry, mock_states, listener, mock_storage_manager
    ):
        """Test updating storage when global variable changes."""
        # Setup storage data with global variable
        storage_data = {
            "sensors": {},
            "sensor_sets": {"test_set": {"global_settings": {"variables": {"power_meter": "sensor.old"}}}},
        }
        mock_storage_manager.data = storage_data

        await listener._update_storage_entity_ids("sensor.old", "sensor.new")

        # Verify global variable was updated
        assert storage_data["sensor_sets"]["test_set"]["global_settings"]["variables"]["power_meter"] == "sensor.new"

        # Verify save was called
        mock_storage_manager.async_save.assert_called_once()

    async def test_update_storage_entity_ids_rebuild_indexes(
        self, mock_hass, mock_entity_registry, mock_states, listener, mock_storage_manager
    ):
        """Test that entity indexes are rebuilt after storage updates."""
        # Setup mock sensor set that tracks the entity
        mock_sensor_set_metadata = MagicMock()
        mock_sensor_set_metadata.sensor_set_id = "test_set"
        mock_storage_manager.list_sensor_sets.return_value = [mock_sensor_set_metadata]

        mock_sensor_set = MagicMock()
        mock_sensor_set.is_entity_tracked.side_effect = lambda entity_id: entity_id in ["sensor.old", "sensor.new"]
        mock_sensor_set.async_rebuild_entity_index = AsyncMock()
        mock_storage_manager.get_sensor_set.return_value = mock_sensor_set

        # Setup storage data with change
        storage_data = {
            "sensors": {},
            "sensor_sets": {"test_set": {"global_settings": {"variables": {"power_meter": "sensor.old"}}}},
        }
        mock_storage_manager.data = storage_data

        await listener._update_storage_entity_ids("sensor.old", "sensor.new")

        # Verify entity index was rebuilt
        mock_sensor_set.async_rebuild_entity_index.assert_called_once()

    def test_get_stats_no_sensor_sets(self, mock_hass, mock_entity_registry, mock_states, listener, mock_storage_manager):
        """Test get_stats with no sensor sets."""
        mock_storage_manager.list_sensor_sets.return_value = []

        stats = listener.get_stats()

        expected = {
            "known_domains_count": 0,
            "known_domains": [],
            "is_listening": False,
        }
        assert stats == expected

    def test_get_stats_with_sensor_sets(
        self, mock_hass, mock_entity_registry, mock_states, listener, mock_storage_manager, mock_entity_change_handler
    ):
        """Test get_stats with sensor sets."""
        # The actual implementation doesn't depend on sensor sets for stats
        # It only returns known domains and listening status
        stats = listener.get_stats()

        expected = {
            "known_domains_count": 0,
            "known_domains": [],
            "is_listening": False,
        }
        assert stats == expected

    async def test_get_stats_active_listener(self, mock_hass, mock_entity_registry, mock_states, listener):
        """Test get_stats when listener is active."""
        await listener.async_start()

        stats = listener.get_stats()

        assert stats["is_listening"] is True
