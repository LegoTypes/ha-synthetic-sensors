"""Tests for __init__.py utility functions."""

import logging
from unittest.mock import MagicMock, patch

import ha_synthetic_sensors


class TestLoggingUtilities:
    """Test cases for logging utility functions."""

    def test_configure_logging_default_level(self):
        """Test configure_logging with default level."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            ha_synthetic_sensors.configure_logging()

            # Should get the package logger first
            mock_get_logger.assert_any_call("ha_synthetic_sensors")

            # Should set level to DEBUG (default)
            mock_logger.setLevel.assert_called_with(logging.DEBUG)

            # Should set propagate to True
            assert mock_logger.propagate is True

    def test_configure_logging_custom_level(self):
        """Test configure_logging with custom level."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            ha_synthetic_sensors.configure_logging(logging.WARNING)

            # Should set level to WARNING
            mock_logger.setLevel.assert_called_with(logging.WARNING)

    def test_configure_logging_sets_child_loggers(self):
        """Test that configure_logging sets up all child module loggers."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            ha_synthetic_sensors.configure_logging(logging.INFO)

            # Should call getLogger for package and all child modules
            expected_calls = [
                "ha_synthetic_sensors",
                "ha_synthetic_sensors.evaluator",
                "ha_synthetic_sensors.service_layer",
                "ha_synthetic_sensors.collection_resolver",
                "ha_synthetic_sensors.variable_resolver",
                "ha_synthetic_sensors.config_manager",
                "ha_synthetic_sensors.sensor_manager",
                "ha_synthetic_sensors.name_resolver",
                "ha_synthetic_sensors.dependency_parser",
                "ha_synthetic_sensors.integration",
                "ha_synthetic_sensors.entity_factory",
            ]

            for logger_name in expected_calls:
                mock_get_logger.assert_any_call(logger_name)

            # Should set level on all loggers
            assert mock_logger.setLevel.call_count >= len(expected_calls)

    def test_configure_logging_logs_success_message(self):
        """Test that configure_logging logs a success message."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            ha_synthetic_sensors.configure_logging(logging.ERROR)

            # Should log a success message
            mock_logger.info.assert_called_with("Synthetic sensors logging configured at level: %s", "ERROR")

    def test_get_logging_info(self):
        """Test get_logging_info returns logger information."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_logger.getEffectiveLevel.return_value = logging.INFO
            mock_logger.handlers = []
            mock_logger.propagate = True
            mock_get_logger.return_value = mock_logger

            result = ha_synthetic_sensors.get_logging_info()

            # Should return a dictionary with logger info
            assert isinstance(result, dict)
            assert "ha_synthetic_sensors" in result
            assert "ha_synthetic_sensors.evaluator" in result
            assert "ha_synthetic_sensors.service_layer" in result
            assert "ha_synthetic_sensors.collection_resolver" in result
            assert "ha_synthetic_sensors.config_manager" in result

            # Check format of main logger info
            assert "INFO" in result["ha_synthetic_sensors"]
            assert "handlers: 0" in result["ha_synthetic_sensors"]
            assert "propagate: True" in result["ha_synthetic_sensors"]

    def test_get_logging_info_with_handlers(self):
        """Test get_logging_info with handlers present."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_logger.getEffectiveLevel.return_value = logging.DEBUG
            mock_logger.handlers = [MagicMock(), MagicMock()]  # Two handlers
            mock_logger.propagate = False
            mock_get_logger.return_value = mock_logger

            result = ha_synthetic_sensors.get_logging_info()

            # Should show handler count and propagate setting
            assert "handlers: 2" in result["ha_synthetic_sensors"]
            assert "propagate: False" in result["ha_synthetic_sensors"]

    def test_test_logging(self):
        """Test test_logging function calls loggers."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            ha_synthetic_sensors.test_logging()

            # Should call getLogger for various modules
            mock_get_logger.assert_any_call("ha_synthetic_sensors")
            mock_get_logger.assert_any_call("ha_synthetic_sensors.evaluator")
            mock_get_logger.assert_any_call("ha_synthetic_sensors.service_layer")
            mock_get_logger.assert_any_call("ha_synthetic_sensors.config_manager")

            # Should log test messages
            mock_logger.info.assert_called_with("TEST: Main package logger")
            mock_logger.debug.assert_called()

    def test_version_attribute(self):
        """Test that __version__ is defined and matches package metadata."""
        assert hasattr(ha_synthetic_sensors, "__version__")
        assert isinstance(ha_synthetic_sensors.__version__, str)
        # Version should be read from package metadata, not hardcoded
        assert ha_synthetic_sensors.__version__ != "unknown"  # Should not be fallback
        # Version should follow semantic versioning pattern
        import re

        version_pattern = r"^\d+\.\d+\.\d+.*$"
        assert re.match(version_pattern, ha_synthetic_sensors.__version__), (
            f"Version '{ha_synthetic_sensors.__version__}' should follow semver pattern"
        )

    def test_all_exports(self):
        """Test that __all__ contains expected exports."""
        expected_exports = [
            # Type definitions
            "DataProviderCallback",
            "DataProviderResult",
            # Core classes
            "FormulaConfig",
            "SensorConfig",
            "SensorSet",
            "StorageManager",
            # Utility classes
            "DeviceAssociationHelper",
            "EntityDescription",
            "EntityFactory",
            # Integration helpers
            "SyntheticSensorsIntegration",
            "async_create_sensor_manager",
            "async_reload_integration",
            "async_setup_integration",
            "async_setup_synthetic_sensors",
            "async_unload_integration",
            # Utility functions
            "configure_logging",
            "get_example_config",
            "get_integration",
            "get_logging_info",
            "test_logging",
            "validate_yaml_content",
        ]

        assert hasattr(ha_synthetic_sensors, "__all__")
        assert isinstance(ha_synthetic_sensors.__all__, list)

        for export in expected_exports:
            assert export in ha_synthetic_sensors.__all__

    def test_all_exports_available(self):
        """Test that all exports in __all__ are actually available."""
        for export_name in ha_synthetic_sensors.__all__:
            assert hasattr(ha_synthetic_sensors, export_name), f"Export {export_name} not available"

    def test_logging_integration(self):
        """Test real logging integration (not mocked)."""
        # This test uses real logging to verify the integration works

        # Configure logging
        ha_synthetic_sensors.configure_logging(logging.WARNING)

        # Get logging info
        info = ha_synthetic_sensors.get_logging_info()

        # Should have the expected loggers
        assert "ha_synthetic_sensors" in info
        assert "WARNING" in info["ha_synthetic_sensors"]

        # Test logging should work without errors
        ha_synthetic_sensors.test_logging()

    def test_configure_logging_propagation_settings(self):
        """Test that configure_logging sets propagation correctly."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_loggers = {}

            def get_logger_side_effect(name):
                if name not in mock_loggers:
                    mock_loggers[name] = MagicMock()
                return mock_loggers[name]

            mock_get_logger.side_effect = get_logger_side_effect

            ha_synthetic_sensors.configure_logging()

            # Check that all loggers have propagate set to True
            for logger_name, logger in mock_loggers.items():
                assert logger.propagate is True, f"Logger {logger_name} should have propagate=True"
