"""Focused test for debugging boolean variable issue."""

import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors

_LOGGER = logging.getLogger(__name__)


class TestBooleanVariableDebug:
    """Integration tests for boolean handler through the public API."""

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

    @pytest.mark.asyncio
    async def test_boolean_variable_in_conditional(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test that boolean variables work correctly in conditional expressions."""

        # Set up mock HA states - just the one we need for the focused test
        mock_states["binary_sensor.front_door"] = Mock(
            state="off", entity_id="binary_sensor.front_door", attributes={"device_class": "door"}
        )

        # Register entity in the entity registry
        mock_entity_registry.register_entity("binary_sensor.front_door", "front_door", "binary_sensor", device_class="door")

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

            # Create sensor set and load boolean handler YAML
            sensor_set_id = "boolean_handler_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Boolean Handler Test"
            )

            # Load the focused YAML fixture
            with open("boolean_variable_debug.yaml") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1

            # Set up sensor manager to test boolean variable features
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
            )

            # Get the created sensor entities
            added_entities = mock_async_add_entities.call_args[0][0]
            assert len(added_entities) == 1

            # Get our test sensor (there's only one)
            boolean_conditional_sensor = added_entities[0]
            assert boolean_conditional_sensor.unique_id == "boolean_variable_conditional"

            # Add debug logging to trace the issue
            _LOGGER.debug("Mock state for binary_sensor.front_door: %s", mock_states['binary_sensor.front_door'].state)

            # Check the evaluator and dependency handler setup
            _LOGGER.debug("sensor_manager type: %s", type(sensor_manager))
            _LOGGER.debug("sensor_manager has _evaluator: %s", hasattr(sensor_manager, '_evaluator'))

            if hasattr(sensor_manager, "_evaluator"):
                evaluator = sensor_manager._evaluator

                if hasattr(evaluator, "dependency_handler"):
                    dep_handler = evaluator.dependency_handler
                    if hasattr(dep_handler, "hass") and hasattr(dep_handler.hass, "states"):
                        test_state = dep_handler.hass.states.get("binary_sensor.front_door")
                        if test_state:
                            pass

                # Test the variable resolution phase
                if hasattr(evaluator, "_variable_resolution_phase"):
                    var_phase = evaluator._variable_resolution_phase
                    if hasattr(var_phase, "_resolver_factory"):
                        resolver_factory = var_phase._resolver_factory

                        # Skip the direct resolver test for now - focus on the dependency handler issue

                # Check if the resolver factory has the dependency handler set
                if hasattr(evaluator, "_variable_resolution_phase"):
                    var_phase = evaluator._variable_resolution_phase
                    if hasattr(var_phase, "_resolver_factory"):
                        resolver_factory = var_phase._resolver_factory

                        # Check individual resolvers
                        if hasattr(resolver_factory, "_resolvers"):
                            for _i, resolver in enumerate(resolver_factory._resolvers):
                                if hasattr(resolver, "_dependency_handler"):
                                    pass
                                if hasattr(resolver, "_hass"):
                                    pass

            # Evaluate the sensor
            await boolean_conditional_sensor.async_update()

            # Get the attributes
            attributes = boolean_conditional_sensor.extra_state_attributes


            # The door_status should be 0.0 (converted from 'off')
            door_status_value = attributes.get("debug_door_status")

            # The conditional should evaluate to 'closed' because not door_status should be True when door_status is falsy
            conditional_result = attributes.get("debug_conditional_result")

            # This is the key test - if door_status is 0.0 (falsy), then 'not door_status' should be True
            # and the conditional should return 'closed'
            assert conditional_result == "closed", (
                f"Expected 'closed' when door_status={door_status_value} (should be falsy), got '{conditional_result}'"
            )
