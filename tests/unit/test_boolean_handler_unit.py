"""Unit tests for boolean handler functionality."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ha_synthetic_sensors.comparison_handlers.handler_boolean import BooleanComparisonHandler
from ha_synthetic_sensors.constants_types import TypeCategory
from ha_synthetic_sensors.exceptions import UnsupportedComparisonError
from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager


class TestBooleanComparisonHandler:
    """Unit tests for BooleanComparisonHandler."""

    @pytest.fixture
    def handler(self):
        """Create BooleanComparisonHandler instance for testing."""
        return BooleanComparisonHandler()

    def test_get_supported_types(self, handler):
        """Test that handler supports boolean and string types."""
        supported_types = handler.get_supported_types()
        assert TypeCategory.BOOLEAN in supported_types
        assert TypeCategory.STRING in supported_types
        assert len(supported_types) == 2

    def test_get_supported_operators(self, handler):
        """Test that handler supports equality operators."""
        supported_operators = handler.get_supported_operators()
        assert "==" in supported_operators
        assert "!=" in supported_operators
        assert len(supported_operators) == 2

    def test_get_type_info(self, handler):
        """Test type information."""
        type_info = handler.get_type_info()
        assert type_info["type_name"] == "boolean"
        assert type_info["priority"] == 30
        assert type_info["supported_operators"] == {"==", "!="}
        assert type_info["can_handle_user_types"] is False

    def test_can_handle_raw_ha_states(self, handler):
        """Test handling Home Assistant state comparisons."""
        # HA boolean states
        assert handler.can_handle_raw("on", "off", "==") is True
        assert handler.can_handle_raw("home", "away", "!=") is True
        assert handler.can_handle_raw("open", "closed", "==") is True
        assert handler.can_handle_raw("active", "inactive", "!=") is True

    def test_can_handle_raw_boolean_ha_states(self, handler):
        """Test handling boolean to HA state comparisons."""
        assert handler.can_handle_raw(True, "on", "==") is True
        assert handler.can_handle_raw(False, "off", "==") is True
        assert handler.can_handle_raw(True, "home", "==") is True
        assert handler.can_handle_raw(False, "away", "==") is True

    def test_can_handle_raw_ha_states_boolean(self, handler):
        """Test handling HA state to boolean comparisons."""
        assert handler.can_handle_raw("on", True, "==") is True
        assert handler.can_handle_raw("off", False, "==") is True
        assert handler.can_handle_raw("home", True, "==") is True
        assert handler.can_handle_raw("away", False, "==") is True

    def test_can_handle_raw_unsupported_operators(self, handler):
        """Test that unsupported operators are rejected."""
        assert handler.can_handle_raw("on", "off", ">") is False
        assert handler.can_handle_raw("home", "away", "<") is False
        assert handler.can_handle_raw("open", "closed", ">=") is False
        assert handler.can_handle_raw("active", "inactive", "<=") is False

    def test_can_handle_raw_unsupported_types(self, handler):
        """Test that unsupported types are rejected."""
        assert handler.can_handle_raw(42, "on", "==") is False
        assert handler.can_handle_raw("on", 3.14, "==") is False
        assert handler.can_handle_raw("not_ha_state", "on", "==") is False

    def test_compare_raw_ha_state_equality(self, handler):
        """Test HA state equality comparisons."""
        assert handler.compare_raw("on", "on", "==") is True
        assert handler.compare_raw("off", "off", "==") is True
        assert handler.compare_raw("home", "home", "==") is True
        assert handler.compare_raw("away", "away", "==") is True

        assert handler.compare_raw("on", "off", "==") is False
        assert handler.compare_raw("home", "away", "==") is False
        assert handler.compare_raw("open", "closed", "==") is False

    def test_compare_raw_ha_state_inequality(self, handler):
        """Test HA state inequality comparisons."""
        assert handler.compare_raw("on", "off", "!=") is True
        assert handler.compare_raw("home", "away", "!=") is True
        assert handler.compare_raw("open", "closed", "!=") is True

        assert handler.compare_raw("on", "on", "!=") is False
        assert handler.compare_raw("home", "home", "!=") is False
        assert handler.compare_raw("open", "open", "!=") is False

    def test_compare_raw_boolean_ha_state_equality(self, handler):
        """Test boolean to HA state equality comparisons."""
        # True comparisons
        assert handler.compare_raw(True, "on", "==") is True
        assert handler.compare_raw(True, "true", "==") is True
        assert handler.compare_raw(True, "yes", "==") is True
        assert handler.compare_raw(True, "1", "==") is True
        assert handler.compare_raw(True, "home", "==") is True
        assert handler.compare_raw(True, "active", "==") is True
        assert handler.compare_raw(True, "enabled", "==") is True

        # False comparisons
        assert handler.compare_raw(False, "off", "==") is True
        assert handler.compare_raw(False, "false", "==") is True
        assert handler.compare_raw(False, "no", "==") is True
        assert handler.compare_raw(False, "0", "==") is True
        assert handler.compare_raw(False, "away", "==") is True
        assert handler.compare_raw(False, "inactive", "==") is True
        assert handler.compare_raw(False, "disabled", "==") is True

    def test_compare_raw_ha_state_boolean_equality(self, handler):
        """Test HA state to boolean equality comparisons."""
        # True comparisons
        assert handler.compare_raw("on", True, "==") is True
        assert handler.compare_raw("true", True, "==") is True
        assert handler.compare_raw("yes", True, "==") is True
        assert handler.compare_raw("1", True, "==") is True
        assert handler.compare_raw("home", True, "==") is True
        assert handler.compare_raw("active", True, "==") is True
        assert handler.compare_raw("enabled", True, "==") is True

        # False comparisons
        assert handler.compare_raw("off", False, "==") is True
        assert handler.compare_raw("false", False, "==") is True
        assert handler.compare_raw("no", False, "==") is True
        assert handler.compare_raw("0", False, "==") is True
        assert handler.compare_raw("away", False, "==") is True
        assert handler.compare_raw("inactive", False, "==") is True
        assert handler.compare_raw("disabled", False, "==") is True

    def test_compare_raw_case_insensitive(self, handler):
        """Test that HA state comparisons are case insensitive."""
        assert handler.compare_raw("ON", True, "==") is True
        assert handler.compare_raw("On", True, "==") is True
        assert handler.compare_raw("on", True, "==") is True

        assert handler.compare_raw("HOME", True, "==") is True
        assert handler.compare_raw("Home", True, "==") is True
        assert handler.compare_raw("home", True, "==") is True

    def test_compare_raw_whitespace_insensitive(self, handler):
        """Test that HA state comparisons are whitespace insensitive."""
        assert handler.compare_raw(" on ", True, "==") is True
        assert handler.compare_raw("  off  ", False, "==") is True
        assert handler.compare_raw("  home  ", True, "==") is True

    def test_compare_raw_unsupported_operator(self, handler):
        """Test that unsupported operators raise UnsupportedComparisonError."""
        with pytest.raises(UnsupportedComparisonError, match="BooleanComparisonHandler cannot handle comparison"):
            handler.compare_raw("on", "off", ">")

        with pytest.raises(UnsupportedComparisonError, match="BooleanComparisonHandler cannot handle comparison"):
            handler.compare_raw("home", "away", "<")

    def test_compare_raw_unsupported_types(self, handler):
        """Test that unsupported types raise UnsupportedComparisonError."""
        with pytest.raises(UnsupportedComparisonError, match="BooleanComparisonHandler cannot handle comparison"):
            handler.compare_raw(42, "on", "==")

        with pytest.raises(UnsupportedComparisonError, match="BooleanComparisonHandler cannot handle comparison"):
            handler.compare_raw("on", 3.14, "==")

    def test_compare_raw_invalid_ha_state(self, handler):
        """Test that invalid HA states raise UnsupportedComparisonError."""
        with pytest.raises(UnsupportedComparisonError, match="BooleanComparisonHandler cannot handle comparison"):
            handler.compare_raw("not_ha_state", "on", "==")

        with pytest.raises(UnsupportedComparisonError, match="BooleanComparisonHandler cannot handle comparison"):
            handler.compare_raw("on", "invalid_state", "==")

    def test_is_boolean_string_ha_states(self, handler):
        """Test that HA states are recognized as boolean strings."""
        for state in handler.TRUE_STATES:
            assert handler._is_boolean_string(state) is True
            assert handler._is_boolean_string(state.upper()) is True
            assert handler._is_boolean_string(f" {state} ") is True

        for state in handler.FALSE_STATES:
            assert handler._is_boolean_string(state) is True
            assert handler._is_boolean_string(state.upper()) is True
            assert handler._is_boolean_string(f" {state} ") is True

    def test_is_boolean_string_invalid(self, handler):
        """Test that invalid strings are not recognized as boolean strings."""
        invalid_strings = ["not_ha_state", "maybe", "unknown", "42", "3.14", ""]
        for invalid in invalid_strings:
            assert handler._is_boolean_string(invalid) is False

    def test_to_boolean_ha_states(self, handler):
        """Test HA state to boolean conversion."""
        # True states
        for state in handler.TRUE_STATES:
            assert handler._to_boolean(state) is True
            assert handler._to_boolean(state.upper()) is True
            assert handler._to_boolean(f" {state} ") is True

        # False states
        for state in handler.FALSE_STATES:
            assert handler._to_boolean(state) is False
            assert handler._to_boolean(state.upper()) is False
            assert handler._to_boolean(f" {state} ") is False

    def test_to_boolean_numeric(self, handler):
        """Test numeric to boolean conversion."""
        assert handler._to_boolean(1) is True
        assert handler._to_boolean(0) is False
        assert handler._to_boolean(42) is True
        assert handler._to_boolean(0.0) is False
        assert handler._to_boolean(3.14) is True

    def test_to_boolean_invalid(self, handler):
        """Test that invalid values raise ValueError."""
        with pytest.raises(ValueError, match="Cannot convert"):
            handler._to_boolean("not_ha_state")

        with pytest.raises(ValueError, match="Cannot convert"):
            handler._to_boolean("")

        with pytest.raises(ValueError, match="Cannot convert"):
            handler._to_boolean(None)


class TestBooleanHandlerYAMLEvaluation:
    """Unit tests for boolean handler YAML evaluation."""

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback."""
        return Mock()

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        return mock_device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    async def test_boolean_handler_yaml_evaluation(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test that boolean handler correctly evaluates YAML fixture with HA boolean states."""

        # Set up mock HA states for boolean state entities
        mock_states["binary_sensor.test_on"] = type("MockState", (), {"state": "on", "attributes": {}})()
        mock_states["binary_sensor.test_off"] = type("MockState", (), {"state": "off", "attributes": {}})()
        mock_states["device_tracker.test_home"] = type("MockState", (), {"state": "home", "attributes": {}})()
        mock_states["device_tracker.test_away"] = type("MockState", (), {"state": "not_home", "attributes": {}})()
        mock_states["cover.test_open"] = type("MockState", (), {"state": "open", "attributes": {}})()
        mock_states["cover.test_closed"] = type("MockState", (), {"state": "closed", "attributes": {}})()
        mock_states["switch.test_active"] = type("MockState", (), {"state": "active", "attributes": {}})()
        mock_states["switch.test_inactive"] = type("MockState", (), {"state": "inactive", "attributes": {}})()

        # Register entities in the entity registry
        mock_entity_registry.register_entity("binary_sensor.test_on", "test_on", "binary_sensor", device_class="safety")
        mock_entity_registry.register_entity("binary_sensor.test_off", "test_off", "binary_sensor", device_class="safety")
        mock_entity_registry.register_entity("device_tracker.test_home", "test_home", "device_tracker")
        mock_entity_registry.register_entity("device_tracker.test_away", "test_away", "device_tracker")
        mock_entity_registry.register_entity("cover.test_open", "test_open", "cover", device_class="door")
        mock_entity_registry.register_entity("cover.test_closed", "test_closed", "cover", device_class="door")
        mock_entity_registry.register_entity("switch.test_active", "test_active", "switch", device_class="switch")
        mock_entity_registry.register_entity("switch.test_inactive", "test_inactive", "switch", device_class="switch")

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "boolean_handler_unit_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Boolean Handler Unit Test"
            )

            yaml_fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "boolean_handler_unit_test.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 11  # Updated count for new YAML

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 11

            await sensor_manager.async_update_sensors()

            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            entity_lookup = {entity.unique_id: entity for entity in all_entities}

            # Test actual sensor values after evaluation - all should be True based on our mock states
            boolean_sensors = [
                "binary_sensor_on_test",  # binary_sensor.test_on == 'on' -> True
                "binary_sensor_off_test",  # binary_sensor.test_off == 'off' -> True
                "device_tracker_home_test",  # device_tracker.test_home == 'home' -> True
                "device_tracker_away_test",  # device_tracker.test_away == 'away' -> True
                "cover_open_test",  # cover.test_open == 'open' -> True
                "cover_closed_test",  # cover.test_closed == 'closed' -> True
                "switch_active_test",  # switch.test_active == 'active' -> True
                "switch_inactive_test",  # switch.test_inactive == 'inactive' -> True
                "boolean_and_test",  # True and True -> True
                "boolean_or_test",  # True or True -> True
                "boolean_not_test",  # not (False == 'on') -> not False -> True
            ]

            # Check all sensor values and report them
            sensor_results = {}
            for sensor_id in boolean_sensors:
                entity = entity_lookup.get(sensor_id)
                if entity is not None:
                    sensor_results[sensor_id] = entity.native_value
                else:
                    sensor_results[sensor_id] = "ENTITY_NOT_FOUND"

            # Now assert - this will show us all the values before failing
            for sensor_id in boolean_sensors:
                entity = entity_lookup.get(sensor_id)
                assert entity is not None, f"Sensor '{sensor_id}' entity not found"
                assert entity.native_value is True, f"Sensor '{sensor_id}' should be True, got {entity.native_value}"

            # Verify all sensors have valid values
            for entity in all_entities:
                assert entity.native_value is not None, f"Sensor '{entity.unique_id}' has None value"
                assert str(entity.native_value) not in ["unknown", "unavailable", ""], (
                    f"Sensor '{entity.unique_id}' has invalid value: {entity.native_value}"
                )

            await storage_manager.async_delete_sensor_set(sensor_set_id)
