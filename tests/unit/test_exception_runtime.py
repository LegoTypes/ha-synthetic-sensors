#!/usr/bin/env python3
"""Test runtime exception handler execution with proper fixtures."""

import pytest
from pathlib import Path
import sys

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

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
    config = config_manager.load_from_yaml(test_yaml)

    sensor = config.sensors[0]
    main_formula = sensor.formulas[0]

    print(f"Testing formula: {main_formula.formula}")
    print(f"Exception handler: {main_formula.exception_handler}")
    if main_formula.exception_handler:
        print(f"  UNAVAILABLE: {main_formula.exception_handler.unavailable}")
        print(f"  UNKNOWN: {main_formula.exception_handler.unknown}")

    # Create evaluator
    evaluator = Evaluator(mock_hass, cache_config=CacheConfig())

    # Test 1: Empty context (should trigger exception handling)
    print(f"\nTest 1: Empty context (should trigger UNAVAILABLE handler)")
    context = {}
    result = evaluator.evaluate_formula_with_sensor_config(main_formula, context, sensor)

    print(f"Result: {result}")
    print(f"  success: {result.get('success')}")
    print(f"  value: {result.get('value')}")
    print(f"  error: {result.get('error')}")
    print(f"  state: {result.get('state')}")

    # Test 2: Context with variables resolved (should work)
    print(f"\nTest 2: Context with variables resolved")
    context_with_vars = {"fallback_main_value": 50, "estimated_main_value": 25}
    result2 = evaluator.evaluate_formula_with_sensor_config(main_formula, context_with_vars, sensor)

    print(f"Result: {result2}")
    print(f"  success: {result2.get('success')}")
    print(f"  value: {result2.get('value')}")
    print(f"  error: {result2.get('error')}")
    print(f"  state: {result2.get('state')}")


if __name__ == "__main__":
    # Run via pytest
    import subprocess

    subprocess.run(["python", "-m", "pytest", __file__, "-v"])
