"""Test configuration and fixtures for ha-synthetic-sensors."""

import asyncio
from collections.abc import Generator
import importlib.util
from pathlib import Path
import sys
from typing import Any, Optional
from unittest.mock import MagicMock, Mock

import pytest

pytest_plugins = ["pytest_asyncio"]  # enable pytest-asyncio plugin


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Provide a fresh asyncio event loop for each test."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Setup path for local package
test_dir = Path(__file__).parent
src_dir = test_dir.parent / "src"
sys.path.insert(0, str(src_dir))

# Import real Home Assistant enums before installing mock finder to avoid recursion
try:
    from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

    REAL_SENSOR_DEVICE_CLASS = SensorDeviceClass
    REAL_SENSOR_STATE_CLASS = SensorStateClass
except ImportError:
    # If Home Assistant is not installed, create basic mock enums
    from enum import Enum

    class MockDeviceClass(Enum):
        MEASUREMENT = "measurement"
        POWER = "power"
        ENERGY = "energy"

    class MockStateClass(Enum):
        MEASUREMENT = "measurement"
        TOTAL = "total"

    REAL_SENSOR_DEVICE_CLASS = MockDeviceClass
    REAL_SENSOR_STATE_CLASS = MockStateClass


# Comprehensive Home Assistant mocking
class MockHomeAssistant:
    """Mock HomeAssistant instance for testing."""

    def __init__(self):
        import tempfile

        self.states = Mock()
        self.config = Mock()
        self.config.config_dir = tempfile.mkdtemp()  # Provide a real temp directory
        self.loop = Mock()
        self.data = {}  # Add data attribute for Store support
        self.bus = Mock()  # Add bus attribute for event handling

    def get_state(self, entity_id):
        """Mock get_state method."""
        return Mock(state="mocked_state", attributes={})

    def async_create_task(self, coro):
        """Mock async_create_task method."""
        import asyncio

        return asyncio.create_task(coro)


class MockConfigEntryError(Exception):
    """Mock ConfigEntryError for testing."""

    pass


class MockState:
    """Mock State object for testing."""

    def __init__(self, entity_id: str, state: str, attributes: Optional[dict[str, Any]] = None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes if attributes is not None else {}


class MockSensorEntity:
    """Mock SensorEntity base class."""

    def __init__(self):
        self._attr_unique_id = None
        self._attr_name = None
        self._attr_native_value = None
        self._attr_available = True
        self._attr_native_unit_of_measurement = None
        self._attr_unit_of_measurement = None
        self._attr_device_class = None
        self._attr_state_class = None
        self._attr_icon = None
        self._attr_extra_state_attributes = {}

    @property
    def entity_id(self):
        """Generate entity_id from unique_id like Home Assistant does."""
        if self._attr_unique_id:
            return f"sensor.{self._attr_unique_id}"
        return "sensor.mock_entity"

    def async_write_ha_state(self):
        """Mock async_write_ha_state method."""
        pass


class MockRestoreEntity:
    """Mock RestoreEntity base class."""

    async def async_added_to_hass(self):
        """Mock async_added_to_hass method."""
        pass

    async def async_get_last_state(self):
        """Mock async_get_last_state method."""
        return None


class HomeAssistantMockFinder:
    """Custom import finder that mocks all homeassistant modules."""

    def find_spec(self, fullname, path, target=None):
        if fullname.startswith("homeassistant"):
            # Special handling for sensor module to provide real enums but mock
            # SensorEntity
            if fullname == "homeassistant.components.sensor":
                # Create a mock module with real enums but mock SensorEntity
                mock_module = MagicMock()
                mock_module.SensorDeviceClass = REAL_SENSOR_DEVICE_CLASS
                mock_module.SensorStateClass = REAL_SENSOR_STATE_CLASS
                mock_module.SensorEntity = MockSensorEntity

                # Install the mock in sys.modules
                sys.modules[fullname] = mock_module

                # Return a mock spec
                spec = MagicMock()
                spec.loader = MagicMock()
                spec.loader.create_module.return_value = mock_module
                spec.loader.exec_module.return_value = None
                return spec

            # Don't mock homeassistant.const - let it be imported normally
            if fullname == "homeassistant.const":
                return None

            # Create a comprehensive mock for any HA module
            mock_module = MagicMock()

            # Add specific mocks for known classes/functions
            if fullname == "homeassistant.core":
                mock_module.HomeAssistant = MockHomeAssistant
                mock_module.State = MockState

                # Mock the callback decorator to be a passthrough
                def callback_decorator(func):
                    return func

                mock_module.callback = callback_decorator
            elif fullname == "homeassistant.exceptions":
                mock_module.ConfigEntryError = MockConfigEntryError
            elif fullname == "homeassistant.config_entries":
                mock_module.ConfigEntry = MagicMock
            elif fullname == "homeassistant.helpers.event":
                mock_module.async_track_state_change_event = MagicMock
            elif fullname == "homeassistant.helpers.restore_state":
                mock_module.RestoreEntity = MockRestoreEntity
            elif fullname == "homeassistant.util.dt":
                # Mock datetime utilities
                from datetime import datetime

                mock_module.utcnow = MagicMock(return_value=datetime.now())

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
storage_manager_real = test_fixtures_module.storage_manager_real


@pytest.fixture
def mock_hass():
    """Provide a mock Home Assistant instance for tests."""
    return MockHomeAssistant()


@pytest.fixture
def mock_state():
    """Factory for creating mock state objects."""

    def _create_state(entity_id: str, state: str, attributes: Optional[dict[str, Any]] = None):
        return MockState(entity_id, state, attributes if attributes is not None else {})

    return _create_state


@pytest.fixture
def sample_config() -> dict[str, Any]:
    """Sample configuration for testing."""
    return {
        "version": "1.0",
        "sensors": {
            "comfort_index": {
                "name": "Comfort Index",
                "formula": "temp * 0.5 + humidity * 0.3",
                "variables": {
                    "temp": "sensor.temperature",
                    "humidity": "sensor.humidity",
                },
                "unit_of_measurement": "comfort",
                "device_class": None,
                "state_class": "measurement",
                "icon": "mdi:thermometer",
                "enabled": True,
                "update_interval": 30,
                "round_digits": 2,
            },
            "power_status": {
                "name": "Power Status",
                "formula": "if_else(power > 1000, 1, 0)",
                "variables": {
                    "power": "sensor.power_meter",
                },
                "unit_of_measurement": None,
                "device_class": "power",
                "state_class": "measurement",
                "enabled": True,
            },
        },
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
def sample_sensor_configs() -> dict[str, dict[str, Any]]:
    """Sample sensor configurations for testing."""
    return {
        "test_sensor_1": {
            "name": "Test Sensor 1",
            "formula": "temp + humidity",
            "variables": {
                "temp": "sensor.temperature",
                "humidity": "sensor.humidity",
            },
            "unit_of_measurement": "units",
            "device_class": "measurement",
            "enabled": True,
            "update_interval": 30,
        },
        "test_sensor_2": {
            "name": "Test Sensor 2",
            "formula": "power / 1000",
            "variables": {
                "power": "sensor.power_meter",
            },
            "unit_of_measurement": "kW",
            "device_class": "power",
            "state_class": "measurement",
            "enabled": True,
            "round_digits": 3,
        },
    }
