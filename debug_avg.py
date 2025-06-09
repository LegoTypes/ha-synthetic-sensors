#!/usr/bin/env python3
import statistics
from typing import cast
from unittest.mock import MagicMock

from simpleeval import SimpleEval

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import ContextValue, Evaluator

print("=== Testing statistics.mean directly ===")
try:
    result = statistics.mean([10, 20, 30])
    print(f"Result: {result}")
except Exception as e:
    print(f"Error: {e}")

print("\n=== Testing simpleeval with avg ===")
evaluator = SimpleEval()
evaluator.names = {"A": 10, "B": 20, "C": 30}
evaluator.functions = {"avg": statistics.mean}

try:
    result = evaluator.eval("avg([A, B, C])")
    print(f"Result: {result}")
except Exception as e:
    print(f"Error: {e}")
    print(f"Error type: {type(e)}")

print("\n=== Testing our evaluator ===")
mock_hass = MagicMock()
evaluator = Evaluator(mock_hass)

config = FormulaConfig(id="avg_test", name="avg_test", formula="avg([A, B, C])")
context = cast(dict[str, ContextValue], {"A": 10, "B": 20, "C": 30})

print(f"Formula: {config.formula}")
print(f"Context: {context}")

dependencies = evaluator.get_formula_dependencies(config.formula)
print(f"Dependencies: {dependencies}")

result = evaluator.evaluate_formula(config, context)
print(f"Result: {result}")
if isinstance(result, dict):
    if not result.get("success", True):
        print(f"Error: {result.get('error', 'No error message')}")
    else:
        print(f"Success! Value: {result['value']}")
else:
    print(f"Success! Value: {result}")
