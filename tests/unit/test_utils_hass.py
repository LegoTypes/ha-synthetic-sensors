"""Unit tests for utils_hass to improve coverage."""

from unittest.mock import Mock

from src.ha_synthetic_sensors.utils_hass import get_data_provider_callback


class TestUtilsHass:
    """Test the utils_hass module."""

    def test_get_data_provider_callback_none_dependency_handler(self):
        """Test get_data_provider_callback with None dependency handler."""
        result = get_data_provider_callback(None)
        assert result is None

    def test_get_data_provider_callback_no_callback(self):
        """Test get_data_provider_callback when dependency handler has no callback."""
        mock_handler = Mock()
        mock_handler.data_provider_callback = None

        result = get_data_provider_callback(mock_handler)
        assert result is None

    def test_get_data_provider_callback_non_callable(self):
        """Test get_data_provider_callback when callback is not callable."""
        mock_handler = Mock()
        mock_handler.data_provider_callback = "not_callable"

        result = get_data_provider_callback(mock_handler)
        assert result is None

    def test_get_data_provider_callback_success(self):
        """Test get_data_provider_callback with valid callable callback."""
        mock_callback = Mock()
        mock_handler = Mock()
        mock_handler.data_provider_callback = mock_callback

        result = get_data_provider_callback(mock_handler)
        assert result == mock_callback
