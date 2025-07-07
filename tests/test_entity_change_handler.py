"""Tests for EntityChangeHandler."""

from unittest.mock import MagicMock, Mock

import pytest

from ha_synthetic_sensors.entity_change_handler import EntityChangeHandler


class TestEntityChangeHandler:
    """Test cases for EntityChangeHandler."""

    @pytest.fixture
    def handler(self):
        """Create an EntityChangeHandler instance for testing."""
        return EntityChangeHandler()

    @pytest.fixture
    def mock_evaluator(self):
        """Create a mock evaluator."""
        evaluator = MagicMock()
        evaluator.clear_cache = MagicMock()
        return evaluator

    @pytest.fixture
    def mock_sensor_manager(self):
        """Create a mock sensor manager."""
        return MagicMock()

    @pytest.fixture
    def mock_callback(self):
        """Create a mock callback function."""
        return Mock()

    def test_initialization(self, handler):
        """Test EntityChangeHandler initialization."""
        assert handler._evaluators == []
        assert handler._sensor_managers == []
        assert handler._integration_callbacks == []
        assert handler._logger is not None

    def test_register_evaluator(self, handler, mock_evaluator):
        """Test registering an evaluator."""
        handler.register_evaluator(mock_evaluator)

        assert mock_evaluator in handler._evaluators
        assert len(handler._evaluators) == 1

    def test_register_evaluator_duplicate(self, handler, mock_evaluator):
        """Test registering the same evaluator twice doesn't create duplicates."""
        handler.register_evaluator(mock_evaluator)
        handler.register_evaluator(mock_evaluator)

        assert len(handler._evaluators) == 1

    def test_unregister_evaluator(self, handler, mock_evaluator):
        """Test unregistering an evaluator."""
        handler.register_evaluator(mock_evaluator)
        handler.unregister_evaluator(mock_evaluator)

        assert mock_evaluator not in handler._evaluators
        assert len(handler._evaluators) == 0

    def test_unregister_evaluator_not_registered(self, handler, mock_evaluator):
        """Test unregistering an evaluator that wasn't registered."""
        # Should not raise an error
        handler.unregister_evaluator(mock_evaluator)
        assert len(handler._evaluators) == 0

    def test_register_sensor_manager(self, handler, mock_sensor_manager):
        """Test registering a sensor manager."""
        handler.register_sensor_manager(mock_sensor_manager)

        assert mock_sensor_manager in handler._sensor_managers
        assert len(handler._sensor_managers) == 1

    def test_register_sensor_manager_duplicate(self, handler, mock_sensor_manager):
        """Test registering the same sensor manager twice doesn't create duplicates."""
        handler.register_sensor_manager(mock_sensor_manager)
        handler.register_sensor_manager(mock_sensor_manager)

        assert len(handler._sensor_managers) == 1

    def test_unregister_sensor_manager(self, handler, mock_sensor_manager):
        """Test unregistering a sensor manager."""
        handler.register_sensor_manager(mock_sensor_manager)
        handler.unregister_sensor_manager(mock_sensor_manager)

        assert mock_sensor_manager not in handler._sensor_managers
        assert len(handler._sensor_managers) == 0

    def test_unregister_sensor_manager_not_registered(self, handler, mock_sensor_manager):
        """Test unregistering a sensor manager that wasn't registered."""
        # Should not raise an error
        handler.unregister_sensor_manager(mock_sensor_manager)
        assert len(handler._sensor_managers) == 0

    def test_register_integration_callback(self, handler, mock_callback):
        """Test registering an integration callback."""
        handler.register_integration_callback(mock_callback)

        assert mock_callback in handler._integration_callbacks
        assert len(handler._integration_callbacks) == 1

    def test_register_integration_callback_duplicate(self, handler, mock_callback):
        """Test registering the same callback twice doesn't create duplicates."""
        handler.register_integration_callback(mock_callback)
        handler.register_integration_callback(mock_callback)

        assert len(handler._integration_callbacks) == 1

    def test_unregister_integration_callback(self, handler, mock_callback):
        """Test unregistering an integration callback."""
        handler.register_integration_callback(mock_callback)
        handler.unregister_integration_callback(mock_callback)

        assert mock_callback not in handler._integration_callbacks
        assert len(handler._integration_callbacks) == 0

    def test_unregister_integration_callback_not_registered(self, handler, mock_callback):
        """Test unregistering a callback that wasn't registered."""
        # Should not raise an error
        handler.unregister_integration_callback(mock_callback)
        assert len(handler._integration_callbacks) == 0

    def test_handle_entity_id_change_empty_handlers(self, handler):
        """Test handling entity ID change with no registered handlers."""
        # Should not raise an error
        handler.handle_entity_id_change("sensor.old", "sensor.new")

    def test_handle_entity_id_change_with_evaluator(self, handler, mock_evaluator):
        """Test handling entity ID change with registered evaluator."""
        handler.register_evaluator(mock_evaluator)

        handler.handle_entity_id_change("sensor.old", "sensor.new")

        mock_evaluator.clear_cache.assert_called_once()

    def test_handle_entity_id_change_with_sensor_manager(self, handler, mock_sensor_manager):
        """Test handling entity ID change with registered sensor manager."""
        handler.register_sensor_manager(mock_sensor_manager)

        handler.handle_entity_id_change("sensor.old", "sensor.new")

        # Sensor manager should be notified (placeholder behavior)
        # This test verifies the loop executes without error

    def test_handle_entity_id_change_with_callback(self, handler, mock_callback):
        """Test handling entity ID change with registered callback."""
        handler.register_integration_callback(mock_callback)

        handler.handle_entity_id_change("sensor.old", "sensor.new")

        mock_callback.assert_called_once_with("sensor.old", "sensor.new")

    def test_handle_entity_id_change_with_all_handlers(self, handler, mock_evaluator, mock_sensor_manager, mock_callback):
        """Test handling entity ID change with all types of handlers registered."""
        handler.register_evaluator(mock_evaluator)
        handler.register_sensor_manager(mock_sensor_manager)
        handler.register_integration_callback(mock_callback)

        handler.handle_entity_id_change("sensor.old", "sensor.new")

        mock_evaluator.clear_cache.assert_called_once()
        mock_callback.assert_called_once_with("sensor.old", "sensor.new")

    def test_handle_entity_id_change_evaluator_error(self, handler, mock_evaluator):
        """Test handling entity ID change when evaluator clear_cache raises an error."""
        mock_evaluator.clear_cache.side_effect = Exception("Cache clear failed")
        handler.register_evaluator(mock_evaluator)

        # Should not raise an error, but log it
        handler.handle_entity_id_change("sensor.old", "sensor.new")

        mock_evaluator.clear_cache.assert_called_once()

    def test_handle_entity_id_change_callback_error(self, handler, mock_callback):
        """Test handling entity ID change when callback raises an error."""
        mock_callback.side_effect = Exception("Callback failed")
        handler.register_integration_callback(mock_callback)

        # Should not raise an error, but log it
        handler.handle_entity_id_change("sensor.old", "sensor.new")

        mock_callback.assert_called_once_with("sensor.old", "sensor.new")

    def test_handle_entity_id_change_multiple_evaluators(self, handler):
        """Test handling entity ID change with multiple evaluators."""
        evaluator1 = MagicMock()
        evaluator2 = MagicMock()
        evaluator1.clear_cache = MagicMock()
        evaluator2.clear_cache = MagicMock()

        handler.register_evaluator(evaluator1)
        handler.register_evaluator(evaluator2)

        handler.handle_entity_id_change("sensor.old", "sensor.new")

        evaluator1.clear_cache.assert_called_once()
        evaluator2.clear_cache.assert_called_once()

    def test_handle_entity_id_change_multiple_callbacks(self, handler):
        """Test handling entity ID change with multiple callbacks."""
        callback1 = Mock()
        callback2 = Mock()

        handler.register_integration_callback(callback1)
        handler.register_integration_callback(callback2)

        handler.handle_entity_id_change("sensor.old", "sensor.new")

        callback1.assert_called_once_with("sensor.old", "sensor.new")
        callback2.assert_called_once_with("sensor.old", "sensor.new")

    def test_get_stats_empty(self, handler):
        """Test get_stats with no registered handlers."""
        stats = handler.get_stats()

        expected = {
            "registered_evaluators": 0,
            "registered_sensor_managers": 0,
            "registered_integration_callbacks": 0,
        }
        assert stats == expected

    def test_get_stats_with_handlers(self, handler, mock_evaluator, mock_sensor_manager, mock_callback):
        """Test get_stats with registered handlers."""
        handler.register_evaluator(mock_evaluator)
        handler.register_sensor_manager(mock_sensor_manager)
        handler.register_integration_callback(mock_callback)

        stats = handler.get_stats()

        expected = {
            "registered_evaluators": 1,
            "registered_sensor_managers": 1,
            "registered_integration_callbacks": 1,
        }
        assert stats == expected

    def test_get_stats_multiple_handlers(self, handler):
        """Test get_stats with multiple handlers of each type."""
        # Add multiple evaluators
        for _ in range(3):
            handler.register_evaluator(MagicMock())

        # Add multiple sensor managers
        for _ in range(2):
            handler.register_sensor_manager(MagicMock())

        # Add multiple callbacks
        for _ in range(4):
            handler.register_integration_callback(Mock())

        stats = handler.get_stats()

        expected = {
            "registered_evaluators": 3,
            "registered_sensor_managers": 2,
            "registered_integration_callbacks": 4,
        }
        assert stats == expected
