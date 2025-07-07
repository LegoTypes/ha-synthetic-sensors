"""Tests for external entity ID change events and handling."""

import asyncio
from unittest.mock import Mock, patch

from homeassistant.core import Event
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED
import pytest


class TestExternalEntityIdChanges:
    """Test handling of external entity ID changes through public APIs."""

    @pytest.fixture
    def load_yaml_fixture(self):
        """Load YAML fixture content."""
        from pathlib import Path

        def _load_yaml_fixture(fixture_name: str) -> str:
            fixture_path = Path(__file__).parent / "yaml_fixtures" / f"{fixture_name}.yaml"
            if not fixture_path.exists():
                raise FileNotFoundError(f"Fixture not found: {fixture_path}")

            with open(fixture_path) as f:
                return f.read()

        return _load_yaml_fixture

    @pytest.fixture
    async def storage_manager_with_test_data(self, mock_hass, load_yaml_fixture):
        """Create StorageManager with test data loaded via public API."""
        import json
        import tempfile
        from unittest.mock import AsyncMock, Mock

        from ha_synthetic_sensors.storage_manager import StorageManager

        # Create a real temporary file for storage
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as temp_file:
            temp_file_name = temp_file.name

        # Mock the Store class to use our temp file
        async def mock_load():
            try:
                with open(temp_file_name) as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return {"version": "1.0", "sensors": {}, "sensor_sets": {}}

        async def mock_save(data):
            with open(temp_file_name, "w") as f:
                json.dump(data, f, indent=2)

        # Set up proper event bus mock with event listener tracking
        event_listeners = {}

        def mock_async_listen(event_type, callback):
            """Mock event listener registration."""
            if event_type not in event_listeners:
                event_listeners[event_type] = []
            event_listeners[event_type].append(callback)
            # Return a mock unsubscribe function
            return Mock()

        def mock_async_fire(event_type, event_data):
            """Mock event firing that actually calls registered listeners."""
            if event_type in event_listeners:
                from homeassistant.core import Event

                event = Event(event_type, event_data)
                for callback in event_listeners[event_type]:
                    # Call the callback synchronously for testing
                    callback(event)

        mock_hass.bus.async_listen = mock_async_listen
        mock_hass.bus.async_fire = mock_async_fire

        with patch("ha_synthetic_sensors.storage_manager.Store") as mock_store_class:
            mock_store = Mock()
            mock_store.async_load = AsyncMock(side_effect=mock_load)
            mock_store.async_save = AsyncMock(side_effect=mock_save)
            mock_store_class.return_value = mock_store

            # Create storage manager with entity listener enabled (default)
            manager = StorageManager(mock_hass, "test_storage")
            await manager.async_load()

            # Load test data via public API
            yaml_content = load_yaml_fixture("entity_change_events_test")
            await manager.async_from_yaml(yaml_content, "test_set", "test_device_001")

            yield manager

            # Cleanup
        import contextlib
        import os

        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_file_name)

    @pytest.fixture
    def mock_entity_states(self):
        """Mock entity states for testing."""
        return {
            "sensor.indoor_temperature": {"attributes": {}, "state": "21.0"},
            "sensor.local_power_meter": {"attributes": {}, "state": "800.0"},
            "sensor.main_power_meter": {"attributes": {}, "state": "1500.0"},
            "sensor.new_main_power_meter": {"attributes": {}, "state": "1500.0"},
            "sensor.new_local_power_meter": {"attributes": {}, "state": "800.0"},
            "sensor.outdoor_temperature": {"attributes": {}, "state": "15.0"},
            "sensor.primary_meter": {"attributes": {}, "state": "1200.0"},
            "sensor.secondary_meter": {"attributes": {}, "state": "300.0"},
            "sensor.reference_power_meter": {"attributes": {}, "state": "1000.0"},
            "sensor.new_reference_power_meter": {"attributes": {}, "state": "1000.0"},
        }

    async def test_global_variable_entity_id_change_via_event(
        self, storage_manager_with_test_data, mock_entity_states, mock_hass
    ):
        """Test external entity ID change for global variable via event system."""
        storage_manager = storage_manager_with_test_data

        # Get sensor set via public API
        sensor_set = storage_manager.get_sensor_set("test_set")

        # Verify initial state via public API
        assert sensor_set.is_entity_tracked("sensor.main_power_meter")
        initial_yaml = sensor_set.export_yaml()
        assert "sensor.main_power_meter" in initial_yaml

        # Mock entity states
        def mock_get_state(entity_id: str):
            state_data = mock_entity_states.get(entity_id, {"state": "0", "attributes": {}})
            mock_state = Mock()
            mock_state.state = state_data["state"]
            mock_state.attributes = state_data["attributes"]
            return mock_state

        mock_hass.states.get = mock_get_state

        # Create entity registry event
        event_data = {
            "action": "update",
            "changes": {"entity_id": {"old": "sensor.main_power_meter", "new": "sensor.new_main_power_meter"}},
        }
        event = Event(EVENT_ENTITY_REGISTRY_UPDATED, event_data)

        # Fire event through Home Assistant event system
        mock_hass.bus.async_fire(event.event_type, event.data)

        # Wait for async processing to complete
        await asyncio.sleep(0.1)

        # Verify changes via public API
        updated_yaml = sensor_set.export_yaml()
        assert "sensor.main_power_meter" not in updated_yaml
        assert "sensor.new_main_power_meter" in updated_yaml

        # Verify entity tracking via public API
        assert not sensor_set.is_entity_tracked("sensor.main_power_meter")
        assert sensor_set.is_entity_tracked("sensor.new_main_power_meter")

        # Verify global settings were updated
        global_settings = sensor_set.get_global_settings()
        assert global_settings["variables"]["global_power_meter"] == "sensor.new_main_power_meter"

    async def test_sensor_variable_entity_id_change_via_event(
        self, storage_manager_with_test_data, mock_entity_states, mock_hass
    ):
        """Test external entity ID change for sensor-specific variable via event system."""
        storage_manager = storage_manager_with_test_data
        sensor_set = storage_manager.get_sensor_set("test_set")

        # Verify initial state
        assert sensor_set.is_entity_tracked("sensor.local_power_meter")

        # Mock entity states
        def mock_get_state(entity_id: str):
            state_data = mock_entity_states.get(entity_id, {"state": "0", "attributes": {}})
            mock_state = Mock()
            mock_state.state = state_data["state"]
            mock_state.attributes = state_data["attributes"]
            return mock_state

        mock_hass.states.get = mock_get_state

        # Create and fire entity registry event
        event_data = {
            "action": "update",
            "changes": {"entity_id": {"old": "sensor.local_power_meter", "new": "sensor.new_local_power_meter"}},
        }
        event = Event(EVENT_ENTITY_REGISTRY_UPDATED, event_data)
        mock_hass.bus.async_fire(event.event_type, event.data)

        # Wait for processing
        await asyncio.sleep(0.1)

        # Verify changes via public API
        updated_yaml = sensor_set.export_yaml()
        assert "sensor.local_power_meter" not in updated_yaml
        assert "sensor.new_local_power_meter" in updated_yaml

        # Verify entity tracking
        assert not sensor_set.is_entity_tracked("sensor.local_power_meter")
        assert sensor_set.is_entity_tracked("sensor.new_local_power_meter")

        # Verify sensor configuration was updated
        sensor_config = sensor_set.get_sensor("local_power_analysis")
        main_formula = None
        for formula in sensor_config.formulas:
            if formula.id == "local_power_analysis":
                main_formula = formula
                break

        assert main_formula is not None
        assert main_formula.variables["local_power"] == "sensor.new_local_power_meter"

    async def test_attribute_variable_entity_id_change_via_event(
        self, storage_manager_with_test_data, mock_entity_states, mock_hass
    ):
        """Test external entity ID change for attribute-specific variable via event system."""
        storage_manager = storage_manager_with_test_data
        sensor_set = storage_manager.get_sensor_set("test_set")

        # Verify initial state
        assert sensor_set.is_entity_tracked("sensor.reference_power_meter")

        # Mock entity states
        def mock_get_state(entity_id: str):
            state_data = mock_entity_states.get(entity_id, {"state": "0", "attributes": {}})
            mock_state = Mock()
            mock_state.state = state_data["state"]
            mock_state.attributes = state_data["attributes"]
            return mock_state

        mock_hass.states.get = mock_get_state

        # Create and fire entity registry event
        event_data = {
            "action": "update",
            "changes": {"entity_id": {"old": "sensor.reference_power_meter", "new": "sensor.new_reference_power_meter"}},
        }
        event = Event(EVENT_ENTITY_REGISTRY_UPDATED, event_data)
        mock_hass.bus.async_fire(event.event_type, event.data)

        # Wait for processing
        await asyncio.sleep(0.1)

        # Verify changes via public API
        updated_yaml = sensor_set.export_yaml()
        assert "sensor.reference_power_meter" not in updated_yaml
        assert "sensor.new_reference_power_meter" in updated_yaml

        # Verify entity tracking
        assert not sensor_set.is_entity_tracked("sensor.reference_power_meter")
        assert sensor_set.is_entity_tracked("sensor.new_reference_power_meter")

        # Verify attribute configuration was updated
        sensor_config = sensor_set.get_sensor("comprehensive_analysis")
        efficiency_ratio_formula = None
        for formula in sensor_config.formulas:
            if formula.id == "comprehensive_analysis_efficiency_ratio":
                efficiency_ratio_formula = formula
                break

        assert efficiency_ratio_formula is not None
        assert efficiency_ratio_formula.variables["reference_power"] == "sensor.new_reference_power_meter"

    async def test_multiple_entity_id_changes_via_events(self, storage_manager_with_test_data, mock_entity_states, mock_hass):
        """Test multiple external entity ID changes via event system."""
        storage_manager = storage_manager_with_test_data
        sensor_set = storage_manager.get_sensor_set("test_set")

        # Define multiple entity ID changes
        entity_changes = [
            ("sensor.main_power_meter", "sensor.new_main_power_meter"),
            ("sensor.local_power_meter", "sensor.new_local_power_meter"),
            ("sensor.reference_power_meter", "sensor.new_reference_power_meter"),
        ]

        # Verify all entities are initially tracked
        for old_id, _new_id in entity_changes:
            assert sensor_set.is_entity_tracked(old_id)

        # Mock entity states
        def mock_get_state(entity_id: str):
            state_data = mock_entity_states.get(entity_id, {"state": "0", "attributes": {}})
            mock_state = Mock()
            mock_state.state = state_data["state"]
            mock_state.attributes = state_data["attributes"]
            return mock_state

        mock_hass.states.get = mock_get_state

        # Fire multiple events
        for old_entity_id, new_entity_id in entity_changes:
            event_data = {"action": "update", "changes": {"entity_id": {"old": old_entity_id, "new": new_entity_id}}}
            event = Event(EVENT_ENTITY_REGISTRY_UPDATED, event_data)
            mock_hass.bus.async_fire(event.event_type, event.data)

        # Wait for all processing to complete
        await asyncio.sleep(0.2)

        # Verify all changes were applied
        updated_yaml = sensor_set.export_yaml()

        for old_entity_id, new_entity_id in entity_changes:
            # Verify YAML updates
            assert old_entity_id not in updated_yaml
            assert new_entity_id in updated_yaml

            # Verify entity tracking
            assert not sensor_set.is_entity_tracked(old_entity_id)
            assert sensor_set.is_entity_tracked(new_entity_id)

    async def test_untracked_entity_id_change_ignored(self, storage_manager_with_test_data, mock_entity_states, mock_hass):
        """Test that untracked entity ID changes are ignored."""
        storage_manager = storage_manager_with_test_data
        sensor_set = storage_manager.get_sensor_set("test_set")

        # Get initial YAML state
        initial_yaml = sensor_set.export_yaml()

        # Fire event for untracked entity
        event_data = {
            "action": "update",
            "changes": {"entity_id": {"old": "sensor.untracked_entity", "new": "sensor.new_untracked_entity"}},
        }
        event = Event(EVENT_ENTITY_REGISTRY_UPDATED, event_data)
        mock_hass.bus.async_fire(event.event_type, event.data)

        # Wait for processing
        await asyncio.sleep(0.1)

        # Verify no changes occurred
        final_yaml = sensor_set.export_yaml()
        assert initial_yaml == final_yaml

        # Verify entities are not tracked
        assert not sensor_set.is_entity_tracked("sensor.untracked_entity")
        assert not sensor_set.is_entity_tracked("sensor.new_untracked_entity")

    async def test_entity_change_cache_invalidation(self, storage_manager_with_test_data, mock_entity_states, mock_hass):
        """Test that entity ID changes trigger cache invalidation."""
        storage_manager = storage_manager_with_test_data

        # Mock the entity change handler to verify cache invalidation
        with patch.object(storage_manager.entity_change_handler, "handle_entity_id_change") as mock_handle_change:
            # Mock entity states
            def mock_get_state(entity_id: str):
                state_data = mock_entity_states.get(entity_id, {"state": "0", "attributes": {}})
                mock_state = Mock()
                mock_state.state = state_data["state"]
                mock_state.attributes = state_data["attributes"]
                return mock_state

            mock_hass.states.get = mock_get_state

            # Fire entity registry event
            event_data = {
                "action": "update",
                "changes": {"entity_id": {"old": "sensor.main_power_meter", "new": "sensor.new_main_power_meter"}},
            }
            event = Event(EVENT_ENTITY_REGISTRY_UPDATED, event_data)
            mock_hass.bus.async_fire(event.event_type, event.data)

            # Wait for processing
            await asyncio.sleep(0.1)

            # Verify cache invalidation was triggered
            mock_handle_change.assert_called_once_with("sensor.main_power_meter", "sensor.new_main_power_meter")

    async def test_concurrent_entity_id_changes_via_events(self, storage_manager_with_test_data, mock_entity_states, mock_hass):
        """Test handling of concurrent entity ID changes via events."""
        storage_manager = storage_manager_with_test_data
        sensor_set = storage_manager.get_sensor_set("test_set")

        # Define concurrent entity changes
        entity_changes = [
            ("sensor.main_power_meter", "sensor.new_main_power_meter"),
            ("sensor.local_power_meter", "sensor.new_local_power_meter"),
            ("sensor.outdoor_temperature", "sensor.new_outdoor_temperature"),
        ]

        # Mock entity states
        def mock_get_state(entity_id: str):
            state_data = mock_entity_states.get(entity_id, {"state": "0", "attributes": {}})
            mock_state = Mock()
            mock_state.state = state_data["state"]
            mock_state.attributes = state_data["attributes"]
            return mock_state

        mock_hass.states.get = mock_get_state

        # Fire all events simultaneously
        for old_id, new_id in entity_changes:
            event_data = {"action": "update", "changes": {"entity_id": {"old": old_id, "new": new_id}}}
            event = Event(EVENT_ENTITY_REGISTRY_UPDATED, event_data)
            mock_hass.bus.async_fire(event.event_type, event.data)

        # Wait for all async processing to complete
        await asyncio.sleep(0.2)

        # Verify all changes were applied correctly
        updated_yaml = sensor_set.export_yaml()

        for old_entity_id, new_entity_id in entity_changes:
            assert old_entity_id not in updated_yaml
            assert new_entity_id in updated_yaml
            assert not sensor_set.is_entity_tracked(old_entity_id)
            assert sensor_set.is_entity_tracked(new_entity_id)

    async def test_integration_workflow_with_sensor_creation_and_entity_changes(
        self, storage_manager_with_test_data, mock_entity_states, mock_hass
    ):
        """Test complete integration workflow: create sensors, then handle entity changes."""
        storage_manager = storage_manager_with_test_data

        # Create a new sensor set via public API (like an integration would)
        sensor_set = await storage_manager.async_create_sensor_set(
            sensor_set_id="integration_test_set", device_identifier="test_device_123", name="Integration Test Device"
        )

        # Add a sensor via public API
        from ha_synthetic_sensors.config_manager import FormulaConfig, SensorConfig

        test_sensor = SensorConfig(
            unique_id="test_power_sensor",
            name="Test Power Sensor",
            formulas=[
                FormulaConfig(
                    id="test_power_sensor",
                    formula="power_meter * efficiency",
                    variables={"power_meter": "sensor.test_power_meter", "efficiency": 0.95},
                    unit_of_measurement="W",
                    device_class="power",
                    state_class="measurement",
                )
            ],
        )

        await sensor_set.async_add_sensor(test_sensor)

        # Verify sensor was created
        assert sensor_set.is_entity_tracked("sensor.test_power_meter")
        initial_yaml = sensor_set.export_yaml()
        assert "sensor.test_power_meter" in initial_yaml

        # Mock entity states
        mock_entity_states["sensor.test_power_meter"] = {"state": "1000.0", "attributes": {}}
        mock_entity_states["sensor.new_test_power_meter"] = {"state": "1000.0", "attributes": {}}

        def mock_get_state(entity_id: str):
            state_data = mock_entity_states.get(entity_id, {"state": "0", "attributes": {}})
            mock_state = Mock()
            mock_state.state = state_data["state"]
            mock_state.attributes = state_data["attributes"]
            return mock_state

        mock_hass.states.get = mock_get_state

        # Simulate entity ID change event
        event_data = {
            "action": "update",
            "changes": {"entity_id": {"old": "sensor.test_power_meter", "new": "sensor.new_test_power_meter"}},
        }
        event = Event(EVENT_ENTITY_REGISTRY_UPDATED, event_data)
        mock_hass.bus.async_fire(event.event_type, event.data)

        # Wait for processing
        await asyncio.sleep(0.1)

        # Verify the change was handled correctly
        updated_yaml = sensor_set.export_yaml()
        assert "sensor.test_power_meter" not in updated_yaml
        assert "sensor.new_test_power_meter" in updated_yaml

        # Verify entity tracking
        assert not sensor_set.is_entity_tracked("sensor.test_power_meter")
        assert sensor_set.is_entity_tracked("sensor.new_test_power_meter")

        # Verify sensor configuration was updated
        updated_sensor = sensor_set.get_sensor("test_power_sensor")
        main_formula = updated_sensor.formulas[0]
        assert main_formula.variables["power_meter"] == "sensor.new_test_power_meter"
