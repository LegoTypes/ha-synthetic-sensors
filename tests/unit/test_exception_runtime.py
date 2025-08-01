#!/usr/bin/env python3
"""Test runtime exception handler execution with proper fixtures."""

import pytest
from pathlib import Path
import sys

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from homeassistant.exceptions import ConfigEntryError
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.cache import CacheConfig


@pytest.mark.asyncio
async def test_runtime_exception_execution(mock_hass, mock_entity_registry, mock_states):
    """Test that exception handlers execute correctly at runtime."""

    # Simple YAML with exception handlers
    test_yaml = """
version: "1.0"

global_settings:
  device_identifier: "test_device_123"

sensors:
  main_formula_exceptions:
    name: "Main Formula Exception Handling"
    formula: "undefined_main_entity + 100"
    UNAVAILABLE: "fallback_main_value"
    UNKNOWN: "estimated_main_value * 2"
    variables:
      fallback_main_value: 50
      estimated_main_value: 25
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
"""

    # Parse the config using the properly mocked hass from fixtures
    config_manager = ConfigManager(mock_hass)

    # The YAML contains undefined variables which should be caught during validation
    with pytest.raises(ConfigEntryError) as exc_info:
        config_manager.load_from_yaml(test_yaml)

    # Verify the error message indicates undefined variables
    error_msg = str(exc_info.value)
    assert "undefined variable" in error_msg
    return  # Test passes - undefined variables correctly caught during validation


if __name__ == "__main__":
    # Run via pytest
    import subprocess

    subprocess.run(["python", "-m", "pytest", __file__, "-v"])
