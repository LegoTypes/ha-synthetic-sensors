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

# Import registry mapping manager
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
try:
    from registry_mapping_manager import get_mapping_by_test_name, clear_mappings
except ImportError:
    # If not available, create dummy functions
    def get_mapping_by_test_name(test_name: str):
        return None

    def clear_mappings():
        pass


# Import incremental prefix processor for automatic preprocessing
try:
    from incremental_prefix_processor import process_test
except ImportError:
    # If not available, create dummy function
    def process_test(test_file_path: str, test_name: str) -> bool:
        return False


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
    from homeassistant.components.binary_sensor import BinarySensorDeviceClass

    REAL_SENSOR_DEVICE_CLASS = SensorDeviceClass
    REAL_SENSOR_STATE_CLASS = SensorStateClass
    REAL_BINARY_SENSOR_DEVICE_CLASS = BinarySensorDeviceClass
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

    class MockBinarySensorDeviceClass(Enum):
        MOTION = "motion"
        BATTERY = "battery"
        DOOR = "door"

    REAL_SENSOR_DEVICE_CLASS = MockDeviceClass
    REAL_SENSOR_STATE_CLASS = MockStateClass
    REAL_BINARY_SENSOR_DEVICE_CLASS = MockBinarySensorDeviceClass


# Mock entity registry for testing
def mock_async_get_entity_registry(hass):
    """Mock function to replace er.async_get for testing."""
    return hass.entity_registry


@pytest.fixture(scope="session", autouse=True)
def setup_entity_registry_mock():
    """Set up the entity registry mock for all tests."""
    import homeassistant.helpers.entity_registry as er

    original_async_get = er.async_get
    er.async_get = mock_async_get_entity_registry

    yield

    # Restore original function after tests
    er.async_get = original_async_get


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

        # Add missing attributes that tests expect
        self.hass = self  # Self-reference for compatibility
        self.loop_thread_id = None  # Required by some HA components

        # Add frame helper and other HA core attributes
        self.helpers = Mock()
        self.helpers.frame = Mock()
        self.helpers.frame._get_integration_logger = Mock(return_value=Mock())

        # Mock entity registry - will be set properly by the mock_hass fixture
        self.entity_registry = Mock()

    def get_state(self, entity_id):
        """Mock get_state method."""
        return Mock(state="mocked_state", attributes={})

    def async_create_task(self, coro):
        """Mock async_create_task method."""
        import asyncio

        return asyncio.create_task(coro)

    async def async_add_executor_job(self, func, *args):
        """Mock async_add_executor_job method."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)

    async def async_block_till_done(self):
        """Mock async_block_till_done method."""
        # Just wait a minimal amount to simulate blocking
        import asyncio

        await asyncio.sleep(0.001)

    def get_sensor_set_metadata(self, sensor_set_id: str):
        """Mock get_sensor_set_metadata method for SensorSet compatibility."""
        return {
            "name": f"Test Sensor Set {sensor_set_id}",
            "device_identifier": "test_device",
            "created_at": "2024-01-01T00:00:00Z",
            "modified_at": "2024-01-01T00:00:00Z",
        }


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

                # Prevent pytest plugin interference
                def mock_getattr_sensor(name):
                    if name in ("pytest_plugins", "pytestmark", "setUpModule", "tearDownModule", "__code__"):
                        raise AttributeError(f"'{mock_module.__class__.__name__}' object has no attribute '{name}'")
                    return MagicMock()

                mock_module.__getattr__ = mock_getattr_sensor
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

            # Special handling for binary_sensor module to provide real enums
            if fullname == "homeassistant.components.binary_sensor":
                # Create a mock module with real enums
                mock_module = MagicMock()

                # Prevent pytest plugin interference
                def mock_getattr_binary(name):
                    if name in ("pytest_plugins", "pytestmark", "setUpModule", "tearDownModule", "__code__"):
                        raise AttributeError(f"'{mock_module.__class__.__name__}' object has no attribute '{name}'")
                    return MagicMock()

                mock_module.__getattr__ = mock_getattr_binary
                mock_module.BinarySensorDeviceClass = REAL_BINARY_SENSOR_DEVICE_CLASS

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

            # Don't mock device_trigger modules - let lazy loader access real constants
            if fullname == "homeassistant.components.binary_sensor.device_trigger":
                return None
            if fullname == "homeassistant.components.sensor.device_trigger":
                return None

            # Don't mock other modules that contain constants needed by lazy loader
            if fullname.endswith(".device_trigger"):
                return None

            # Create a comprehensive mock for any HA module
            mock_module = MagicMock()

            # Prevent pytest plugin interference by configuring mock to raise AttributeError for pytest-related attributes
            def mock_getattr(name):
                if name in ("pytest_plugins", "pytestmark", "setUpModule", "tearDownModule", "__code__"):
                    raise AttributeError(f"'{mock_module.__class__.__name__}' object has no attribute '{name}'")
                return MagicMock()

            mock_module.__getattr__ = mock_getattr

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
test_fixtures_path = Path(__file__).parent / "integration" / "test_fixtures.py"
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


def pytest_runtest_setup(item):
    """Hook to detect improper test setup and provide helpful feedback."""
    # Only run this check for our test files
    if not item.nodeid.startswith("tests/"):
        return

    # Get the test function and file path
    test_func = item.function
    test_file_path = str(Path(item.fspath))
    test_name = item.name

    # DISABLED: Automatic prefixing system - tests get isolated registries per fixture
    # Check if test needs preprocessing (has entity references but no prefix)
    # try:
    #     # Check if this test file needs preprocessing
    #     if process_test(test_file_path, test_name):
    #         print(f"🔧 Auto-preprocessed test: {test_name}")
    # except Exception as e:
    #     # If preprocessing fails, continue with the test (don't fail the test)
    #     print(f"⚠️  Auto-preprocessing failed for {test_name}: {e}")

    # Check if the test function uses the common registry fixtures
    import inspect

    sig = inspect.signature(test_func)
    param_names = list(sig.parameters.keys())

    # Check if test has the common fixtures as parameters
    has_mock_hass = "mock_hass" in param_names
    has_mock_entity_registry = "mock_entity_registry" in param_names
    has_mock_states = "mock_states" in param_names

    # If test doesn't use the common fixtures, check if it might need them
    if not (has_mock_hass and has_mock_entity_registry and has_mock_states):
        # Look for signs that this test might be doing entity resolution
        test_source = inspect.getsource(test_func)
        # More specific indicators that suggest entity resolution is needed
        # Look for actual usage patterns, not just string presence
        # These patterns indicate actual entity resolution usage, not just string references
        entity_resolution_patterns = [
            "SensorManager(",  # Actual instantiation
            ".entity_registry",  # Direct usage (with dot prefix to avoid false positives)
            "states.get(",  # Method calls
            "er.async_get(",  # Method calls
            "ConfigManager(",  # Actual instantiation
            "sensor_manager =",  # Variable assignments
            "create_sensors(",  # Method calls
            "register_data_provider_entities(",  # Method calls
        ]

        if any(pattern in test_source for pattern in entity_resolution_patterns):
            pytest.fail(
                f"ERROR: Test '{item.nodeid}' MUST use the common registry fixtures!\n"
                "   This test appears to work with entity resolution but doesn't use\n"
                "   the common 'mock_hass', 'mock_entity_registry', and 'mock_states' fixtures.\n"
                "   Add these fixtures to avoid regex pattern issues:\n"
                "   def test_name(self, mock_hass, mock_entity_registry, mock_states):\n"
                "   See other working tests for examples."
            )


@pytest.fixture
def mock_hass(mock_entity_registry, mock_states):
    """Provide a mock Home Assistant instance for tests."""
    hass = MockHomeAssistant()
    hass.entity_registry = mock_entity_registry
    # Make sure the entity registry has the entities attribute that the constants_entities module expects
    if not hasattr(hass.entity_registry.entities, "values"):
        mock_entities_obj = Mock()
        mock_entities_obj.values.return_value = mock_entity_registry.entities.values()
        hass.entity_registry.entities = mock_entities_obj

    # Set up the states.get method to return states from mock_states
    mock_states_get = Mock()

    def mock_states_get_impl(entity_id):
        return mock_states.get(entity_id)

    mock_states_get.side_effect = mock_states_get_impl

    hass.states.get = mock_states_get

    # Note: async_create_task is not mocked globally to avoid breaking tests that need it to work
    # Individual tests that need to mock it should do so locally

    return hass


@pytest.fixture
def mock_state():
    """Factory for creating mock state objects."""

    def _create_state(entity_id: str, state: str, attributes: Optional[dict[str, Any]] = None):
        return MockState(entity_id, state, attributes if attributes is not None else {})

    return _create_state


@pytest.fixture
def mock_entity_registry():
    """Create a dynamic mock entity registry that behaves like the real HA registry.

    This mock automatically registers entities when they have unique_ids and go through
    the async_added_to_hass() lifecycle, similar to how the real HA registry works.
    """
    # Ensure clean state for each test
    mock_entities = {}
    # Add all attributes needed for tests
    entity_data = {
        # Basic entities from original fixture
        "sensor.circuit_a_power": {"domain": "sensor", "device_class": "power"},
        "sensor.circuit_b_power": {"domain": "sensor", "device_class": "power"},
        "sensor.kitchen_temperature": {"domain": "sensor", "device_class": "temperature"},
        "sensor.living_room_temperature": {"domain": "sensor", "device_class": "temperature"},
        # Additional entities for type coverage
        "sensor.numeric_temp": {"domain": "sensor", "device_class": "temperature"},
        "binary_sensor.opening": {"domain": "binary_sensor", "device_class": "opening"},
        "switch.switch1": {"domain": "switch", "device_class": "switch"},
        "input_text.enum1": {"domain": "input_text", "device_class": "enum"},
        "span.span1": {"domain": "span"},
        # Additional entities needed by tests
        "sensor.kitchen_temp": {"domain": "sensor", "device_class": "temperature"},
        "sensor.living_temp": {"domain": "sensor", "device_class": "temperature"},
        "sensor.temperature": {"domain": "sensor", "device_class": "temperature"},
        "sensor.humidity": {"domain": "sensor", "device_class": "humidity"},
        "sensor.temp_1": {"domain": "sensor", "device_class": "temperature"},
        "sensor.battery_device": {"domain": "sensor", "battery_level": 85},
        "sensor.low_battery_device": {"domain": "sensor", "battery_level": 15},
        # Area-based entities
        "sensor.living_room_temp": {"domain": "sensor", "area_id": "living_room", "device_class": "temperature"},
        "light.living_room_main": {"domain": "light", "area_id": "living_room"},
        "sensor.living_room_humidity": {"domain": "sensor", "area_id": "living_room", "device_class": "humidity"},
        "sensor.kitchen_temp": {"domain": "sensor", "area_id": "kitchen", "device_class": "temperature"},
        "light.kitchen_overhead": {"domain": "light", "area_id": "kitchen"},
        "sensor.kitchen_humidity": {"domain": "sensor", "area_id": "kitchen", "device_class": "humidity"},
        "sensor.master_bedroom_temp": {"domain": "sensor", "area_id": "master_bedroom", "device_class": "temperature"},
        "sensor.guest_bedroom_temp": {"domain": "sensor", "area_id": "guest_bedroom", "device_class": "temperature"},
        # Device class entities
        "binary_sensor.front_door": {"domain": "binary_sensor", "device_class": "door"},
        "binary_sensor.back_door": {"domain": "binary_sensor", "device_class": "door"},
        "binary_sensor.living_room_window": {"domain": "binary_sensor", "device_class": "window"},
        "binary_sensor.bedroom_window": {"domain": "binary_sensor", "device_class": "window"},
        "lock.front_door_lock": {"domain": "lock", "device_class": "lock"},
        "sensor.bathroom_humidity": {"domain": "sensor", "device_class": "humidity"},
        # Label-based entities
        "sensor.server_cpu": {"domain": "sensor", "labels": ["critical", "monitor"]},
        "sensor.database_status": {"domain": "sensor", "labels": ["critical", "alert"]},
        "sensor.backup_system": {"domain": "sensor", "labels": ["important", "monitor"]},
        "sensor.security_system": {"domain": "sensor", "labels": ["critical", "alert"]},
        "sensor.disk_space": {"domain": "sensor", "labels": ["important", "monitor"]},
        "sensor.network_latency": {"domain": "sensor", "labels": ["critical", "alert"]},
        "sensor.power_consumption": {"domain": "sensor", "labels": ["important"]},
        "sensor.energy_usage": {"domain": "sensor", "labels": ["monitor", "alert"]},
        # State and attribute entities
        "sensor.phone_battery": {"domain": "sensor", "online": True},
        "sensor.power_meter": {"domain": "sensor", "status": "active"},
        "sensor.high_value_sensor": {"domain": "sensor", "state": "95"},
        "sensor.warning_value_sensor": {"domain": "sensor", "state": "80"},
        # Error test entities
        "sensor.invalid_entity": {"domain": "sensor", "device_class": "power"},
        "sensor.span_panel_instantaneous_power": {"domain": "sensor", "device_class": "power"},
        "sensor.span_panel_voltage": {"domain": "sensor", "device_class": "voltage"},
        "sensor.temperature_sensor": {"domain": "sensor", "device_class": "temperature"},
        # Cross-sensor reference test entities (resolved entity IDs)
        "sensor.simple_parent_reference_2": {"domain": "sensor", "device_class": "power"},
        "sensor.base_power_2": {"domain": "sensor", "device_class": "power"},
        "sensor.solar_power_3": {"domain": "sensor", "device_class": "power"},
        "sensor.total_power_4": {"domain": "sensor", "device_class": "power"},
        # Missing entities for tests
        "sensor.missing_entity": {"domain": "sensor", "device_class": "power"},
        "sensor.missing1": {"domain": "sensor", "device_class": "power"},
        "sensor.missing2": {"domain": "sensor", "device_class": "power"},
        "switch.test": {"domain": "switch", "device_class": "switch"},
        "binary_sensor.test_on": {"domain": "binary_sensor", "device_class": "opening"},
        "binary_sensor.test_off": {"domain": "binary_sensor", "device_class": "opening"},
        "binary_sensor.test_moist": {"domain": "binary_sensor", "device_class": "moisture"},
        "binary_sensor.test_not_moist": {"domain": "binary_sensor", "device_class": "moisture"},
        # Numeric literals test entities
        "sensor.test_value": {"domain": "sensor", "device_class": "power"},
        "sensor.some_value": {"domain": "sensor", "device_class": "power"},
        "sensor.x_coordinate": {"domain": "sensor", "device_class": "measurement"},
        "sensor.y_coordinate": {"domain": "sensor", "device_class": "measurement"},
        # Idiom 3 attribute access test entities
        "sensor.backup_device": {"domain": "sensor", "device_class": "battery"},
        "sensor.outdoor_temperature": {"domain": "sensor", "device_class": "temperature"},
        "sensor.indoor_temperature": {"domain": "sensor", "device_class": "temperature"},
        # Dynamic collection variables test entities
        "sensor.circuit_main_power": {"domain": "sensor", "device_class": "power"},
        "sensor.circuit_lighting_power": {"domain": "sensor", "device_class": "power"},
        "sensor.phone_battery": {"domain": "sensor", "device_class": "battery"},
        "sensor.tablet_battery": {"domain": "sensor", "device_class": "battery"},
        "sensor.laptop_battery": {"domain": "sensor", "device_class": "battery"},
        "input_select.monitoring_device_class": {"domain": "input_select"},
        "input_select.focus_area": {"domain": "input_select"},
        "input_number.battery_alert_threshold": {"domain": "input_number"},
        "input_text.circuit_group_name": {"domain": "input_text"},
        "sensor.main_panel_power": {"domain": "sensor", "device_class": "power"},
        "input_number.power_rate_multiplier": {"domain": "input_number"},
        # Hierarchical dependencies test entities
        "sensor.circuit_1_power": {"domain": "sensor", "device_class": "power"},
        "sensor.circuit_2_power": {"domain": "sensor", "device_class": "power"},
        # Collision-causing entities for cross-sensor integration test
        "sensor.roundtrip_base_power_sensor": {
            "domain": "sensor",
            "device_class": "power",
            "unique_id": "a_collision_causing_sensor",
        },
        "sensor.roundtrip_efficiency_calc": {
            "domain": "sensor",
            "device_class": "power",
            "unique_id": "another_collision_causing_sensor",
        },
        "sensor.circuit_3_power": {"domain": "sensor", "device_class": "power"},
        "sensor.circuit_4_power": {"domain": "sensor", "device_class": "power"},
        "sensor.hvac_total_hvac_total": {"domain": "sensor", "device_class": "power"},
        "sensor.lighting_total_lighting_total": {"domain": "sensor", "device_class": "power"},
        "sensor.home_total_home_total": {"domain": "sensor", "device_class": "power"},
        "sensor.energy_analysis_efficiency": {"domain": "sensor", "device_class": "power"},
        # Hybrid data access test entities
        "sensor.grid_power": {"domain": "sensor", "device_class": "power"},
        # Reference patterns test entities
        "input_number.electricity_rate_cents_kwh": {"domain": "input_number"},
        "sensor.energy_cost_analysis": {"domain": "sensor", "device_class": "monetary"},
        "sensor.base_power_analysis": {"domain": "sensor", "device_class": "power"},
        "input_number.efficiency_factor": {"domain": "input_number"},
        "sensor.backup_power_system": {"domain": "sensor", "device_class": "power"},
        "sensor.base_power_meter": {"domain": "sensor", "device_class": "power"},
        "input_number.base_efficiency": {"domain": "input_number"},
        "sensor.comprehensive_analysis": {"domain": "sensor", "device_class": "measurement"},
        # Name resolver test entities
        "sensor.test_entity": {"domain": "sensor", "device_class": "power"},
        "sensor.direct_entity": {"domain": "sensor", "device_class": "power"},
        "sensor.missing_direct": {"domain": "sensor", "device_class": "power"},
        "sensor.solar_inverter": {"domain": "sensor", "device_class": "power"},
        "sensor.house_total_power": {"domain": "sensor", "device_class": "power"},
        "sensor.workshop_power": {"domain": "sensor", "device_class": "power"},
        "sensor.external_sensor": {"domain": "sensor", "device_class": "power"},
        "sensor.outside_temperature": {"domain": "sensor", "device_class": "temperature"},
        # Idiom 3 attribute access test entities
        "sensor.backup_device": {"domain": "sensor", "device_class": "battery"},
        "sensor.indoor_temperature": {"domain": "sensor", "device_class": "temperature"},
        "sensor.battery_system": {"domain": "sensor", "device_class": "battery"},
        "sensor.environmental_monitor": {"domain": "sensor", "device_class": "temperature"},
        # Collection resolver test entities
        "sensor.test": {"domain": "sensor", "device_class": "temperature"},
        # Additional entities for idiom tests
        "sensor.power_meter": {"domain": "sensor", "device_class": "power"},
        # Cross-sensor collision handling test entities
        "sensor.duplicate_sensor": {"domain": "sensor", "device_class": "power"},
        "sensor.duplicate_sensor_2": {"domain": "sensor", "device_class": "power"},
        "sensor.reference_sensor": {"domain": "sensor", "device_class": "power"},
        # Cross-sensor reference test entities
        "sensor.backing_entity": {"domain": "sensor", "device_class": "power"},
    }

    for entity_id, attrs in entity_data.items():
        mock_entity = Mock()
        for k, v in attrs.items():
            setattr(mock_entity, k, v)
        mock_entities[entity_id] = mock_entity

    class DynamicMockEntityRegistry:
        """Mock entity registry that supports dynamic entity registration."""

        def __init__(self):
            # Each instance gets its own entities dictionary to ensure test isolation
            self._entities = {}

            # Populate with initial test entities by copying from the fixture-level dictionary
            for entity_id, mock_entity in mock_entities.items():
                # Create a new mock entity with the same attributes
                new_mock_entity = Mock()
                new_mock_entity.entity_id = entity_id
                new_mock_entity.unique_id = entity_id.split(".", 1)[1]  # Extract entity name
                new_mock_entity.domain = getattr(mock_entity, "domain", "sensor")

                # Copy all attributes from the original mock entity
                for attr_name in dir(mock_entity):
                    if not attr_name.startswith("_") and not callable(getattr(mock_entity, attr_name)):
                        setattr(new_mock_entity, attr_name, getattr(mock_entity, attr_name))

                self._entities[entity_id] = new_mock_entity

        @property
        def entities(self):
            """Return entities object with dict-like interface."""
            entities_obj = Mock()
            entities_obj.values.return_value = self._entities.values()
            entities_obj.items.return_value = self._entities.items()
            entities_obj.keys.return_value = self._entities.keys()
            entities_obj.__iter__ = lambda self_obj: iter(self._entities.keys())
            entities_obj.__getitem__ = lambda _, key: self._entities.get(key)
            entities_obj.__contains__ = lambda _, key: key in self._entities
            return entities_obj

        async def async_get_or_create(self, domain, platform, unique_id, **kwargs):
            """Mock the async_get_or_create method that HA uses for dynamic registration.

            Simulates HA's collision handling by appending numbers for duplicates.
            """
            # Check if entity with this unique_id already exists
            existing_entities = []
            for existing_entity in self._entities.values():
                if hasattr(existing_entity, "unique_id") and existing_entity.unique_id == unique_id:
                    existing_entities.append(existing_entity)

            if existing_entities:
                # Found existing entity with same unique_id - this is a collision
                # Generate a new unique_id with suffix (_2, _3, etc.)
                counter = 2
                new_unique_id = f"{unique_id}_{counter}"

                # Keep trying until we find an unused unique_id
                while any(
                    hasattr(entity, "unique_id") and entity.unique_id == new_unique_id for entity in self._entities.values()
                ):
                    counter += 1
                    new_unique_id = f"{unique_id}_{counter}"

                print(f"🚨 Registry collision: unique_id={unique_id} → new_unique_id={new_unique_id}")
                unique_id = new_unique_id

            # Generate entity_id with collision handling (like real HA)
            suggested_object_id = kwargs.get("suggested_object_id", unique_id)
            base_entity_id = f"{domain}.{suggested_object_id}"
            entity_id = base_entity_id

            # Handle entity_id collisions by appending _2, _3, etc.
            counter = 2
            while entity_id in self._entities:
                entity_id = f"{base_entity_id}_{counter}"
                counter += 1

            # Create new mock entity as if it was registered
            mock_entity = Mock()
            mock_entity.entity_id = entity_id
            mock_entity.unique_id = unique_id
            mock_entity.domain = domain
            mock_entity.platform = platform

            # Set any additional attributes from kwargs
            for key, value in kwargs.items():
                setattr(mock_entity, key, value)

            self._entities[entity_id] = mock_entity

            if entity_id != base_entity_id:
                print(f"🚨 Registry entity_id collision: {base_entity_id} → {entity_id} (collision avoided)")
            else:
                print(f"✅ Registry: Added entity {entity_id} with unique_id={unique_id}")

            return mock_entity

        def get_entity_id(self, domain, platform, unique_id):
            """Get entity_id for a given unique_id."""
            entity_id = f"{domain}.{unique_id}"
            return entity_id if entity_id in self._entities else None

        def register_entity(self, entity_id, unique_id, domain, **attrs):
            """Helper method to manually register entities for testing."""
            if entity_id not in self._entities:
                mock_entity = Mock()
                mock_entity.entity_id = entity_id
                mock_entity.unique_id = unique_id
                mock_entity.domain = domain

                for key, value in attrs.items():
                    setattr(mock_entity, key, value)

                self._entities[entity_id] = mock_entity
                print(f"📝 Manual registry: Added entity {entity_id}")

        def async_get(self, entity_id):
            """Mock the async_get method that HA uses to retrieve entities."""
            return self._entities.get(entity_id)

    registry = DynamicMockEntityRegistry()
    return registry


@pytest.fixture
def mock_states(mock_entity_registry):
    """Create dynamic mock states that sync with entity registry.

    This fixture creates a states dictionary that can be extended dynamically
    as new entities are registered during testing.
    """
    states = {}

    # Basic entities
    states["sensor.circuit_a_power"] = Mock(
        state="150.5", entity_id="sensor.circuit_a_power", attributes={"device_class": "power"}
    )
    states["sensor.circuit_b_power"] = Mock(
        state="200.0", entity_id="sensor.circuit_b_power", attributes={"device_class": "power"}
    )
    states["sensor.kitchen_temperature"] = Mock(
        state="22.5", entity_id="sensor.kitchen_temperature", attributes={"device_class": "temperature"}
    )
    states["sensor.living_room_temperature"] = Mock(
        state="23.0", entity_id="sensor.living_room_temperature", attributes={"device_class": "temperature"}
    )
    # Additional states for test entities
    states["sensor.kitchen_temp"] = Mock(
        state="22.5", entity_id="sensor.kitchen_temp", attributes={"device_class": "temperature"}
    )
    states["sensor.living_temp"] = Mock(
        state="23.0", entity_id="sensor.living_temp", attributes={"device_class": "temperature"}
    )
    states["sensor.temperature"] = Mock(
        state="22.0", entity_id="sensor.temperature", attributes={"device_class": "temperature"}
    )
    states["sensor.humidity"] = Mock(state="45.0", entity_id="sensor.humidity", attributes={"device_class": "humidity"})
    states["sensor.temp_1"] = Mock(state="21.5", entity_id="sensor.temp_1", attributes={"device_class": "temperature"})
    states["sensor.battery_device"] = Mock(state="85", entity_id="sensor.battery_device", attributes={"battery_level": 85})
    states["sensor.low_battery_device"] = Mock(
        state="15", entity_id="sensor.low_battery_device", attributes={"battery_level": 15}
    )

    # Area-based entities
    states["sensor.living_room_temp"] = Mock(
        state="22.5", entity_id="sensor.living_room_temp", attributes={"device_class": "temperature"}
    )
    states["light.living_room_main"] = Mock(state="on", entity_id="light.living_room_main", attributes={})
    states["sensor.living_room_humidity"] = Mock(
        state="45.0", entity_id="sensor.living_room_humidity", attributes={"device_class": "humidity"}
    )
    states["sensor.kitchen_temp"] = Mock(
        state="24.0", entity_id="sensor.kitchen_temp", attributes={"device_class": "temperature"}
    )
    states["light.kitchen_overhead"] = Mock(state="off", entity_id="light.kitchen_overhead", attributes={})
    states["sensor.kitchen_humidity"] = Mock(
        state="50.0", entity_id="sensor.kitchen_humidity", attributes={"device_class": "humidity"}
    )
    states["sensor.master_bedroom_temp"] = Mock(
        state="21.0", entity_id="sensor.master_bedroom_temp", attributes={"device_class": "temperature"}
    )
    states["sensor.guest_bedroom_temp"] = Mock(
        state="20.5", entity_id="sensor.guest_bedroom_temp", attributes={"device_class": "temperature"}
    )

    # Device class entities
    states["binary_sensor.front_door"] = Mock(
        state="off", entity_id="binary_sensor.front_door", attributes={"device_class": "door"}
    )
    states["binary_sensor.back_door"] = Mock(
        state="on", entity_id="binary_sensor.back_door", attributes={"device_class": "door"}
    )
    states["binary_sensor.living_room_window"] = Mock(
        state="off", entity_id="binary_sensor.living_room_window", attributes={"device_class": "window"}
    )
    states["binary_sensor.bedroom_window"] = Mock(
        state="on", entity_id="binary_sensor.bedroom_window", attributes={"device_class": "window"}
    )
    states["lock.front_door_lock"] = Mock(state="locked", entity_id="lock.front_door_lock", attributes={"device_class": "lock"})
    states["sensor.bathroom_humidity"] = Mock(
        state="60.0", entity_id="sensor.bathroom_humidity", attributes={"device_class": "humidity"}
    )

    # Label-based entities
    states["sensor.server_cpu"] = Mock(
        state="75.0", entity_id="sensor.server_cpu", attributes={"labels": ["critical", "monitor"]}
    )
    states["sensor.database_status"] = Mock(
        state="ok", entity_id="sensor.database_status", attributes={"labels": ["critical", "alert"]}
    )
    states["sensor.backup_system"] = Mock(
        state="running", entity_id="sensor.backup_system", attributes={"labels": ["important", "monitor"]}
    )
    states["sensor.security_system"] = Mock(
        state="armed", entity_id="sensor.security_system", attributes={"labels": ["critical", "alert"]}
    )
    states["sensor.disk_space"] = Mock(
        state="85.0", entity_id="sensor.disk_space", attributes={"labels": ["important", "monitor"]}
    )
    states["sensor.network_latency"] = Mock(
        state="25.0", entity_id="sensor.network_latency", attributes={"labels": ["critical", "alert"]}
    )
    states["sensor.power_consumption"] = Mock(
        state="1200.0", entity_id="sensor.power_consumption", attributes={"labels": ["important"]}
    )
    states["sensor.energy_usage"] = Mock(
        state="850.0", entity_id="sensor.energy_usage", attributes={"labels": ["monitor", "alert"]}
    )

    # State and attribute entities
    states["sensor.phone_battery"] = Mock(state="85", entity_id="sensor.phone_battery", attributes={"online": True})
    states["sensor.power_meter"] = Mock(state="1200.0", entity_id="sensor.power_meter", attributes={"status": "active"})
    states["sensor.high_value_sensor"] = Mock(state="95", entity_id="sensor.high_value_sensor", attributes={})
    states["sensor.warning_value_sensor"] = Mock(state="80", entity_id="sensor.warning_value_sensor", attributes={})

    # Error test entities
    states["sensor.invalid_entity"] = Mock(
        state="1000.0", entity_id="sensor.invalid_entity", attributes={"device_class": "power"}
    )
    states["sensor.span_panel_instantaneous_power"] = Mock(
        state="1000.0", entity_id="sensor.span_panel_instantaneous_power", attributes={"device_class": "power"}
    )
    states["sensor.span_panel_voltage"] = Mock(
        state="240.0", entity_id="sensor.span_panel_voltage", attributes={"device_class": "voltage"}
    )
    states["sensor.temperature_sensor"] = Mock(
        state="23.5", entity_id="sensor.temperature_sensor", attributes={"device_class": "temperature"}
    )

    # Cross-sensor reference test entities (resolved entity IDs)
    states["sensor.simple_parent_reference_2"] = Mock(
        state="2000.0", entity_id="sensor.simple_parent_reference_2", attributes={"device_class": "power"}
    )
    states["sensor.base_power_2"] = Mock(state="1000.0", entity_id="sensor.base_power_2", attributes={"device_class": "power"})
    states["sensor.solar_power_3"] = Mock(state="800.0", entity_id="sensor.solar_power_3", attributes={"device_class": "power"})
    states["sensor.total_power_4"] = Mock(
        state="1800.0", entity_id="sensor.total_power_4", attributes={"device_class": "power"}
    )

    # Missing entities for tests
    states["sensor.missing_entity"] = Mock(
        state="100.0", entity_id="sensor.missing_entity", attributes={"device_class": "power"}
    )
    states["sensor.missing1"] = Mock(state="50.0", entity_id="sensor.missing1", attributes={"device_class": "power"})
    states["sensor.missing2"] = Mock(state="75.0", entity_id="sensor.missing2", attributes={"device_class": "power"})
    states["switch.test"] = Mock(state="off", entity_id="switch.test", attributes={"device_class": "switch"})
    states["binary_sensor.test_on"] = Mock(
        state="on", entity_id="binary_sensor.test_on", attributes={"device_class": "opening"}
    )
    states["binary_sensor.test_off"] = Mock(
        state="off", entity_id="binary_sensor.test_off", attributes={"device_class": "opening"}
    )
    states["binary_sensor.test_moist"] = Mock(
        state="moist", entity_id="binary_sensor.test_moist", attributes={"device_class": "moisture"}
    )
    states["binary_sensor.test_not_moist"] = Mock(
        state="not_moist", entity_id="binary_sensor.test_not_moist", attributes={"device_class": "moisture"}
    )

    # Dynamic collection variables test entities
    states["sensor.circuit_main_power"] = Mock(
        state="350.5", entity_id="sensor.circuit_main_power", attributes={"device_class": "power"}
    )
    states["sensor.circuit_lighting_power"] = Mock(
        state="125.3", entity_id="sensor.circuit_lighting_power", attributes={"device_class": "power"}
    )
    states["sensor.phone_battery"] = Mock(
        state="85", entity_id="sensor.phone_battery", attributes={"device_class": "battery", "battery_level": 85}
    )
    states["sensor.tablet_battery"] = Mock(
        state="15", entity_id="sensor.tablet_battery", attributes={"device_class": "battery", "battery_level": 15}
    )
    states["sensor.laptop_battery"] = Mock(
        state="92", entity_id="sensor.laptop_battery", attributes={"device_class": "battery", "battery_level": 92}
    )
    states["input_select.monitoring_device_class"] = Mock(
        state="power", entity_id="input_select.monitoring_device_class", attributes={}
    )
    states["input_select.focus_area"] = Mock(state="kitchen", entity_id="input_select.focus_area", attributes={})
    states["input_number.battery_alert_threshold"] = Mock(
        state="20", entity_id="input_number.battery_alert_threshold", attributes={}
    )
    states["input_text.circuit_group_name"] = Mock(state="main", entity_id="input_text.circuit_group_name", attributes={})
    states["sensor.main_panel_power"] = Mock(
        state="100.0", entity_id="sensor.main_panel_power", attributes={"device_class": "power"}
    )
    states["input_number.power_rate_multiplier"] = Mock(
        state="1.5", entity_id="input_number.power_rate_multiplier", attributes={}
    )

    # Hierarchical dependencies test entities
    states["sensor.circuit_1_power"] = Mock(
        state="100.0", entity_id="sensor.circuit_1_power", attributes={"device_class": "power"}
    )
    states["sensor.circuit_2_power"] = Mock(
        state="150.0", entity_id="sensor.circuit_2_power", attributes={"device_class": "power"}
    )
    states["sensor.circuit_3_power"] = Mock(
        state="75.0", entity_id="sensor.circuit_3_power", attributes={"device_class": "power"}
    )
    states["sensor.circuit_4_power"] = Mock(
        state="125.0", entity_id="sensor.circuit_4_power", attributes={"device_class": "power"}
    )
    states["sensor.hvac_total_hvac_total"] = Mock(
        state="250.0", entity_id="sensor.hvac_total_hvac_total", attributes={"device_class": "power"}
    )
    states["sensor.lighting_total_lighting_total"] = Mock(
        state="200.0", entity_id="sensor.lighting_total_lighting_total", attributes={"device_class": "power"}
    )
    states["sensor.home_total_home_total"] = Mock(
        state="450.0", entity_id="sensor.home_total_home_total", attributes={"device_class": "power"}
    )
    states["sensor.energy_analysis_efficiency"] = Mock(
        state="85.5", entity_id="sensor.energy_analysis_efficiency", attributes={"device_class": "power"}
    )

    # Hybrid data access test entities
    states["sensor.grid_power"] = Mock(state="1500", entity_id="sensor.grid_power", attributes={"device_class": "power"})
    states["sensor.solar_inverter"] = Mock(state="800", entity_id="sensor.solar_inverter", attributes={"device_class": "power"})
    states["sensor.house_total_power"] = Mock(
        state="2200", entity_id="sensor.house_total_power", attributes={"device_class": "power"}
    )
    states["sensor.workshop_power"] = Mock(state="300", entity_id="sensor.workshop_power", attributes={"device_class": "power"})
    states["sensor.external_sensor"] = Mock(
        state="450", entity_id="sensor.external_sensor", attributes={"device_class": "power"}
    )
    states["sensor.outside_temperature"] = Mock(
        state="22.5", entity_id="sensor.outside_temperature", attributes={"device_class": "temperature"}
    )

    # Reference patterns test states
    states["input_number.electricity_rate_cents_kwh"] = Mock(
        state="12.5", entity_id="input_number.electricity_rate_cents_kwh", attributes={}
    )
    states["sensor.energy_cost_analysis"] = Mock(
        state="31.25", entity_id="sensor.energy_cost_analysis", attributes={"device_class": "monetary"}
    )
    states["sensor.base_power_analysis"] = Mock(
        state="2000.0", entity_id="sensor.base_power_analysis", attributes={"device_class": "power"}
    )
    states["input_number.efficiency_factor"] = Mock(state="85.0", entity_id="input_number.efficiency_factor", attributes={})
    states["sensor.backup_power_system"] = Mock(
        state="500.0", entity_id="sensor.backup_power_system", attributes={"device_class": "power", "battery_level": 75}
    )
    states["sensor.base_power_meter"] = Mock(
        state="1800.0", entity_id="sensor.base_power_meter", attributes={"device_class": "power"}
    )
    states["input_number.base_efficiency"] = Mock(state="90.0", entity_id="input_number.base_efficiency", attributes={})
    states["sensor.comprehensive_analysis"] = Mock(
        state="100.0", entity_id="sensor.comprehensive_analysis", attributes={"device_class": "measurement"}
    )
    # Name resolver test states
    states["sensor.test_entity"] = Mock(
        state="100", entity_id="sensor.test_entity", attributes={"unit": "W", "device_class": "power"}
    )
    states["sensor.direct_entity"] = Mock(state="42.5", entity_id="sensor.direct_entity", attributes={"device_class": "power"})
    states["sensor.missing_direct"] = Mock(state="0", entity_id="sensor.missing_direct", attributes={"device_class": "power"})

    # Idiom 3 attribute access test states
    states["sensor.backup_device"] = Mock(
        state="85.0", entity_id="sensor.backup_device", attributes={"battery_level": 85.0, "status": "charging"}
    )
    states["sensor.indoor_temperature"] = Mock(
        state="21.5", entity_id="sensor.indoor_temperature", attributes={"device_class": "temperature"}
    )
    states["sensor.battery_system"] = Mock(
        state="75.0",
        entity_id="sensor.battery_system",
        attributes={"battery_level": 75.0, "battery_voltage": 12.6, "max_voltage": 13.2},
    )
    states["sensor.environmental_monitor"] = Mock(
        state="22.0",
        entity_id="sensor.environmental_monitor",
        attributes={"humidity": 45.0, "temperature": 22.0, "pressure": 1013.25},
    )

    # Collection resolver test states
    states["sensor.test"] = Mock(state="25.0", entity_id="sensor.test", attributes={"device_class": "temperature"})
    states["sensor.backing_entity"] = Mock(
        state="1000.0", entity_id="sensor.backing_entity", attributes={"device_class": "power"}
    )

    # Additional states for idiom tests
    states["sensor.power_meter"] = Mock(state="1200.0", entity_id="sensor.power_meter", attributes={"power_factor": 0.95})

    class DynamicMockStates(dict):
        """Dictionary-like mock states that supports dynamic registration."""

        def __init__(self, initial_states, entity_registry):
            super().__init__(initial_states)
            self._entity_registry = entity_registry

        def register_state(self, entity_id, state_value="unknown", attributes=None):
            """Register a new state for an entity."""
            if attributes is None:
                attributes = {}

            mock_state = Mock()
            mock_state.state = str(state_value)
            mock_state.entity_id = entity_id
            mock_state.attributes = attributes

            self[entity_id] = mock_state
            print(f"🔄 Dynamic states: Added state for {entity_id} = {state_value}")

        def auto_register_from_registry(self):
            """Auto-register states for any new entities in the registry."""
            for entity_id, entity in self._entity_registry._entities.items():
                if entity_id not in self:
                    # Create a default state for the new entity
                    default_state = "0" if hasattr(entity, "device_class") and entity.device_class == "power" else "unknown"
                    self.register_state(entity_id, default_state, {"device_class": getattr(entity, "device_class", None)})

    dynamic_states = DynamicMockStates(states, mock_entity_registry)
    return dynamic_states


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


@pytest.fixture
def mock_config_manager(mock_hass):
    """Create a mock config manager for service layer testing."""
    from unittest.mock import MagicMock, AsyncMock

    config_manager = MagicMock()
    config_manager.async_load_config = AsyncMock()
    config_manager.async_save_config = AsyncMock()
    config_manager.async_reload_config = AsyncMock()
    config_manager.validate_configuration = MagicMock(return_value=[])
    config_manager.get_variables = MagicMock(return_value={})
    config_manager.get_sensors = MagicMock(return_value=[])
    config_manager.get_sensor_by_name = MagicMock(return_value=None)
    config_manager.add_sensor = MagicMock()
    config_manager.update_sensor = MagicMock()
    config_manager.add_variable = MagicMock()
    config_manager.remove_variable = MagicMock()
    return config_manager


@pytest.fixture
def mock_sensor_manager(mock_hass):
    """Create a mock sensor manager for service layer testing."""
    from unittest.mock import MagicMock, AsyncMock

    sensor_manager = MagicMock()
    sensor_manager.async_update_sensors = AsyncMock()
    sensor_manager.add_sensor = AsyncMock()
    sensor_manager.update_sensor = AsyncMock()
    sensor_manager.get_sensor_by_entity_id = MagicMock(return_value=None)
    sensor_manager.get_all_sensor_entities = MagicMock(return_value=[])
    return sensor_manager


@pytest.fixture
def mock_name_resolver():
    """Create a mock name resolver for service layer testing."""
    from unittest.mock import MagicMock

    name_resolver = MagicMock()
    name_resolver.clear_mappings = MagicMock()
    name_resolver.add_entity_mapping = MagicMock()
    return name_resolver


@pytest.fixture
def mock_evaluator():
    """Create a mock evaluator for service layer testing."""
    from unittest.mock import MagicMock

    evaluator = MagicMock()
    evaluator.clear_cache = MagicMock()
    evaluator.evaluate_formula = MagicMock(return_value={"success": True, "value": 42.0})
    return evaluator


@pytest.fixture
def service_layer(mock_hass, mock_config_manager, mock_sensor_manager, mock_name_resolver, mock_evaluator):
    """Create a service layer instance with mocked dependencies."""
    from ha_synthetic_sensors.service_layer import ServiceLayer

    return ServiceLayer(
        mock_hass,
        mock_config_manager,
        mock_sensor_manager,
        mock_name_resolver,
        mock_evaluator,
    )


@pytest.fixture
def apply_entity_mappings(request, mock_entity_registry):
    """Apply entity mappings for the current test if available."""
    test_name = request.node.name

    # Get mapping for this test
    mapping = get_mapping_by_test_name(test_name)

    if mapping:
        print(f"🔧 Applying entity mappings for test: {test_name}")
        print(f"   Prefix: {mapping.prefix}")
        print(f"   Entities: {len(mapping.entity_mappings)}")

        # Apply each mapping to the registry
        for original_id, prefixed_id in mapping.entity_mappings:
            # Parse the prefixed entity ID
            if "." in prefixed_id:
                domain, name = prefixed_id.split(".", 1)
            else:
                domain, name = "sensor", prefixed_id

            # Register the prefixed entity in the registry
            mock_entity_registry.register_entity(
                entity_id=prefixed_id,
                unique_id=f"{mapping.prefix}_{name}",
                domain=domain,
                device_class=getattr(mock_entity_registry._entities.get(original_id), "device_class", None),
            )

            print(f"   ✅ Registered: {original_id} -> {prefixed_id}")

        print(f"✅ Applied {len(mapping.entity_mappings)} entity mappings")
    else:
        print(f"ℹ️  No entity mappings found for test: {test_name}")

    yield

    # Cleanup could be added here if needed


# Note: hybrid_test fixtures removed due to missing hybrid_test_base module
# Tests should use manual setup with mock_hass, mock_entity_registry, and other fixtures
