"""Debug test to verify mock setup works correctly."""

from pathlib import Path
from unittest.mock import Mock
import pytest

from ha_synthetic_sensors.utils_resolvers import resolve_via_hass_entity


class TestMockDebug:
    """Debug test to verify mock setup."""

    @pytest.mark.asyncio
    async def test_mock_states_direct_access(self, mock_hass, mock_states):
        """Test that mock states can be accessed directly."""
        
        # Set up a test entity
        mock_states["binary_sensor.test_door"] = Mock(
            state="off", entity_id="binary_sensor.test_door", attributes={"device_class": "door"}
        )
        
        # Test direct access
        state_obj = mock_hass.states.get("binary_sensor.test_door")
        print(f"Direct access - state_obj: {state_obj}")
        print(f"Direct access - state: {state_obj.state if state_obj else 'None'}")
        
        # Change the state
        mock_states["binary_sensor.test_door"].state = "on"
        
        # Test again
        state_obj2 = mock_hass.states.get("binary_sensor.test_door")
        print(f"After change - state_obj: {state_obj2}")
        print(f"After change - state: {state_obj2.state if state_obj2 else 'None'}")
        
        # Test via resolver
        class MockDependencyHandler:
            def __init__(self, hass):
                self.hass = hass
        
        handler = MockDependencyHandler(mock_hass)
        
        # Reset to off
        mock_states["binary_sensor.test_door"].state = "off"
        result1 = resolve_via_hass_entity(handler, "binary_sensor.test_door", "binary_sensor.test_door")
        print(f"Resolver with 'off': {result1}")
        print(f"Resolver value: {result1.value if result1 else 'None'}")
        
        # Change to on
        mock_states["binary_sensor.test_door"].state = "on"
        result2 = resolve_via_hass_entity(handler, "binary_sensor.test_door", "binary_sensor.test_door")
        print(f"Resolver with 'on': {result2}")
        print(f"Resolver value: {result2.value if result2 else 'None'}")
        
        # Assertions
        assert state_obj is not None
        assert state_obj2 is not None
        assert result1 is not None
        assert result2 is not None
        assert result1.value == 0.0  # "off" should convert to 0.0
        assert result2.value == 1.0  # "on" should convert to 1.0
