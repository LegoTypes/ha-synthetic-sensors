"""Test configuration and fixtures for ha-synthetic-sensors."""

import importlib.util
import sys
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, Mock

import pytest

# Setup path for local package
test_dir = Path(__file__).parent
src_dir = test_dir.parent / "src"
sys.path.insert(0, str(src_dir))


# Comprehensive Home Assistant mocking
class MockHomeAssistant:
    """Mock HomeAssistant instance for testing."""

    def __init__(self):
        self.states = Mock()
        self.config = Mock()
        self.loop = Mock()

    def get_state(self, entity_id):
        """Mock get_state method."""
        return Mock(state="mocked_state", attributes={})


class MockConfigEntryError(Exception):
    """Mock ConfigEntryError for testing."""

    pass


class MockState:
    """Mock State object for testing."""

    def __init__(
        self, entity_id: str, state: str, attributes: Optional[dict[str, Any]] = None
    ):
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes if attributes is not None else {}


class MockSensorEntity:
    """Mock SensorEntity base class."""

    pass


class MockRestoreEntity:
    """Mock RestoreEntity base class."""

    pass


class HomeAssistantMockFinder:
    """Custom import finder that mocks all homeassistant modules."""

    def find_spec(self, fullname, path, target=None):
        if fullname.startswith("homeassistant"):
            # Create a comprehensive mock for any HA module
            mock_module = MagicMock()

            # Add specific mocks for known classes/functions
            if fullname == "homeassistant.core":
                mock_module.HomeAssistant = MockHomeAssistant
                mock_module.State = MockState
            elif fullname == "homeassistant.exceptions":
                mock_module.ConfigEntryError = MockConfigEntryError
            elif fullname == "homeassistant.config_entries":
                mock_module.ConfigEntry = MagicMock
            elif fullname == "homeassistant.components.sensor":
                mock_module.SensorEntity = MockSensorEntity
                mock_module.SensorDeviceClass = MagicMock
                mock_module.SensorStateClass = MagicMock
            elif fullname == "homeassistant.helpers.event":
                mock_module.async_track_state_change_event = MagicMock
            elif fullname == "homeassistant.helpers.restore_state":
                mock_module.RestoreEntity = MockRestoreEntity

            # Install the mock in sys.modules
            sys.modules[fullname] = mock_module

            # Return a mock spec
            spec = MagicMock()
            spec.loader = MagicMock()
            spec.loader.create_module.return_value = mock_module
            spec.loader.exec_module.return_value = None
            return spec

        return None


# Install the custom finder
sys.meta_path.insert(0, HomeAssistantMockFinder())


# Import all fixtures from test_fixtures.py to make them available globally
# We need to use importlib to avoid relative import issues
test_fixtures_path = Path(__file__).parent / "test_fixtures.py"
spec = importlib.util.spec_from_file_location("test_fixtures", test_fixtures_path)
if spec is not None and spec.loader is not None:
    test_fixtures_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(test_fixtures_module)
else:
    raise ImportError("Could not load test_fixtures module")

# Make the fixtures available in this module's namespace
solar_analytics_yaml = test_fixtures_module.solar_analytics_yaml
hierarchical_calculations_yaml = test_fixtures_module.hierarchical_calculations_yaml
cost_analysis_yaml = test_fixtures_module.cost_analysis_yaml
simple_test_yaml = test_fixtures_module.simple_test_yaml
entity_management_test_yaml = test_fixtures_module.entity_management_test_yaml
mock_entities_with_dependencies = test_fixtures_module.mock_entities_with_dependencies
load_yaml_fixture = test_fixtures_module.load_yaml_fixture
yaml_fixtures_dir = test_fixtures_module.yaml_fixtures_dir


@pytest.fixture
def mock_hass():
    """Provide a mock Home Assistant instance for tests."""
    return MockHomeAssistant()


@pytest.fixture
def mock_state():
    """Factory for creating mock state objects."""

    def _create_state(
        entity_id: str, state: str, attributes: Optional[dict[str, Any]] = None
    ):
        return MockState(entity_id, state, attributes if attributes is not None else {})

    return _create_state


@pytest.fixture
def sample_config() -> dict[str, Any]:
    """Sample configuration for testing."""
    return {
        "variables": [
            {
                "name": "temp",
                "entity_id": "sensor.temperature",
                "description": "Room temperature",
            },
            {
                "name": "humidity",
                "entity_id": "sensor.humidity",
                "description": "Room humidity",
            },
            {
                "name": "power",
                "entity_id": "sensor.power_meter",
                "description": "Power consumption",
            },
        ],
        "sensors": [
            {
                "name": "Comfort Index",
                "formula": "temp * 0.5 + humidity * 0.3",
                "unit_of_measurement": "comfort",
                "device_class": None,
                "state_class": "measurement",
                "icon": "mdi:thermometer",
                "enabled": True,
                "update_interval": 30,
                "round_digits": 2,
            },
            {
                "name": "Power Status",
                "formula": "if_else(power > 1000, 1, 0)",
                "unit_of_measurement": None,
                "device_class": "power",
                "state_class": "measurement",
                "enabled": True,
                "availability_formula": "power > 0",
            },
        ],
        "global_settings": {
            "default_update_interval": 30,
            "cache_ttl": 10,
            "enable_logging": True,
        },
    }


@pytest.fixture
def mock_config_entry():
    """Mock configuration entry."""
    entry = MagicMock()
    entry.data = {"name": "test_integration"}
    entry.entry_id = "test_entry_id"
    return entry


@pytest.fixture
def sample_sensor_configs() -> list[dict[str, Any]]:
    """Sample sensor configurations for testing."""
    return [
        {
            "name": "Test Sensor 1",
            "formula": "temp + humidity",
            "unit_of_measurement": "units",
            "device_class": "measurement",
            "enabled": True,
            "update_interval": 30,
        },
        {
            "name": "Test Sensor 2",
            "formula": "power / 1000",
            "unit_of_measurement": "kW",
            "device_class": "power",
            "state_class": "measurement",
            "enabled": True,
            "round_digits": 3,
        },
    ]
