"""Test YAML configuration with device association fields."""

import pytest
import yaml

from ha_synthetic_sensors.config_manager import ConfigManager


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    from unittest.mock import MagicMock

    hass = MagicMock()
    hass.config = MagicMock()
    hass.config.config_dir = "/config"
    return hass


def test_parse_yaml_with_device_fields(mock_hass, load_yaml_fixture):
    """Test parsing YAML configuration with device association fields."""
    yaml_config = load_yaml_fixture("device_association")
    yaml_content = yaml.dump(yaml_config)

    manager = ConfigManager(mock_hass)
    config = manager.load_from_yaml(yaml_content)

    # Test sensor with full device configuration
    sensor_with_device = config.get_sensor_by_unique_id("test_sensor_with_device")
    assert sensor_with_device is not None
    assert sensor_with_device.device_identifier == "test_device_001"
    assert sensor_with_device.device_name == "Test Device"
    assert sensor_with_device.device_manufacturer == "Test Manufacturer"
    assert sensor_with_device.device_model == "Test Model v1"
    assert sensor_with_device.device_sw_version == "1.0.0"
    assert sensor_with_device.suggested_area == "Test Area"
    assert sensor_with_device.device_hw_version is None  # Not specified

    # Test sensor with minimal device configuration
    sensor_minimal_device = config.get_sensor_by_unique_id("test_sensor_minimal_device")
    assert sensor_minimal_device is not None
    assert sensor_minimal_device.device_identifier == "existing_device_001"
    assert sensor_minimal_device.device_name is None
    assert sensor_minimal_device.device_manufacturer is None
    assert sensor_minimal_device.device_model is None
    assert sensor_minimal_device.device_sw_version is None
    assert sensor_minimal_device.suggested_area is None

    # Test sensor without device configuration
    sensor_no_device = config.get_sensor_by_unique_id("test_sensor_no_device")
    assert sensor_no_device is not None
    assert sensor_no_device.device_identifier is None
    assert sensor_no_device.device_name is None
    assert sensor_no_device.device_manufacturer is None
    assert sensor_no_device.device_model is None
    assert sensor_no_device.device_sw_version is None
    assert sensor_no_device.suggested_area is None


def test_device_fields_backward_compatibility(mock_hass, load_yaml_fixture):
    """Test that existing configurations without device fields still work."""
    yaml_config = load_yaml_fixture("backward_compatibility")
    yaml_content = yaml.dump(yaml_config)

    manager = ConfigManager(mock_hass)
    config = manager.load_from_yaml(yaml_content)

    sensor = config.get_sensor_by_unique_id("existing_sensor")
    assert sensor is not None
    assert sensor.name == "Existing Sensor"
    assert sensor.category == "environmental"

    # All device fields should be None (not specified)
    assert sensor.device_identifier is None
    assert sensor.device_name is None
    assert sensor.device_manufacturer is None
    assert sensor.device_model is None
    assert sensor.device_sw_version is None
    assert sensor.device_hw_version is None
    assert sensor.suggested_area is None
