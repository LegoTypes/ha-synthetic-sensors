#!/usr/bin/env python3
"""Performance baseline measurement for AST-driven architecture changes.

Run this before implementing changes to establish baseline metrics.
"""

from __future__ import annotations

import gc
import json
import time
import tracemalloc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from ha_synthetic_sensors.config_models import SensorConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.reference_value_manager import ReferenceValue


@dataclass
class PerformanceMetrics:
    """Container for performance baseline metrics."""

    evaluation_times: list[float] = field(default_factory=list)
    reference_value_counts: list[int] = field(default_factory=list)
    cache_hit_rates: dict[str, float] = field(default_factory=dict)
    memory_usage_kb: list[float] = field(default_factory=list)
    context_sizes: list[int] = field(default_factory=list)
    object_creation_counts: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize metrics to JSON."""
        return json.dumps(
            {
                "avg_evaluation_time_ms": sum(self.evaluation_times) / len(self.evaluation_times) * 1000
                if self.evaluation_times
                else 0,
                "avg_reference_values_per_cycle": sum(self.reference_value_counts) / len(self.reference_value_counts)
                if self.reference_value_counts
                else 0,
                "cache_hit_rates": self.cache_hit_rates,
                "avg_memory_kb": sum(self.memory_usage_kb) / len(self.memory_usage_kb) if self.memory_usage_kb else 0,
                "avg_context_size": sum(self.context_sizes) / len(self.context_sizes) if self.context_sizes else 0,
                "total_object_creations": self.object_creation_counts,
            },
            indent=2,
        )


class PerformanceBaseline:
    """Measure performance baseline for SPAN sensor evaluation."""

    def __init__(self, test_yaml_path: str):
        """Initialize with test YAML configuration."""
        self.test_yaml_path = Path(test_yaml_path)
        self.metrics = PerformanceMetrics()
        self.evaluator = None
        self.sensor_configs = []

    def load_test_config(self) -> None:
        """Load SPAN test configuration."""
        from ha_synthetic_sensors.config_models import FormulaConfig

        # Create a few test sensor configs directly
        self.sensor_configs = [
            SensorConfig(
                unique_id="test_sensor_1",
                name="Test Sensor 1",
                formulas=[FormulaConfig(id="main", formula="state", name="main")],
                metadata={"unit_of_measurement": "W"},
            ),
            SensorConfig(
                unique_id="test_sensor_2",
                name="Test Sensor with Metadata",
                formulas=[
                    FormulaConfig(
                        id="main",
                        formula="metadata(state, 'last_changed')",
                        name="main",
                        variables={"state": "sensor.span_panel_instantaneous_power"},
                    )
                ],
            ),
            SensorConfig(
                unique_id="test_sensor_3",
                name="Test Sensor with Computation",
                formulas=[
                    FormulaConfig(
                        id="main",
                        formula="sensor_power * efficiency_factor",
                        name="main",
                        variables={"sensor_power": "sensor.span_panel_instantaneous_power", "efficiency_factor": 0.95},
                    )
                ],
            ),
        ]

    def setup_evaluator(self, hass_mock) -> None:
        """Set up evaluator with mocked Home Assistant."""
        self.evaluator = Evaluator(hass=hass_mock, data_provider_callback=lambda x: None)

    def measure_evaluation_cycle(self, sensor_config: SensorConfig) -> None:
        """Measure a single evaluation cycle."""
        # Start memory tracking
        tracemalloc.start()
        gc.collect()
        start_memory = tracemalloc.get_traced_memory()[0] / 1024  # KB

        # Count ReferenceValue objects before
        ref_values_before = len([obj for obj in gc.get_objects() if isinstance(obj, ReferenceValue)])

        # Measure evaluation time
        start_time = time.perf_counter()

        # Create evaluation context
        eval_context = {}

        # Evaluate main formula (first formula in list)
        if sensor_config.formulas:
            main_formula = sensor_config.formulas[0]
            result = self.evaluator.evaluate_formula_with_sensor_config(main_formula, eval_context, sensor_config)

        end_time = time.perf_counter()

        # Count ReferenceValue objects after
        gc.collect()
        ref_values_after = len([obj for obj in gc.get_objects() if isinstance(obj, ReferenceValue)])

        # Get memory usage
        end_memory = tracemalloc.get_traced_memory()[0] / 1024  # KB
        tracemalloc.stop()

        # Record metrics
        self.metrics.evaluation_times.append(end_time - start_time)
        self.metrics.reference_value_counts.append(ref_values_after - ref_values_before)
        self.metrics.memory_usage_kb.append(end_memory - start_memory)
        self.metrics.context_sizes.append(len(eval_context))

    def measure_cache_performance(self) -> None:
        """Measure cache hit rates."""
        if hasattr(self.evaluator, "_compilation_cache"):
            cache_stats = self.evaluator._compilation_cache.get_stats()
            self.metrics.cache_hit_rates["compilation"] = cache_stats.get("hit_rate", 0)

        if hasattr(self.evaluator, "_ast_service") and hasattr(self.evaluator._ast_service, "_cache"):
            ast_cache = self.evaluator._ast_service._cache
            total = sum(1 for _ in ast_cache.values())
            if total > 0:
                # Approximate hit rate based on cache size
                self.metrics.cache_hit_rates["ast_analysis"] = min(len(ast_cache) / (total * 2), 1.0)

    def count_object_creations(self) -> None:
        """Count object creations during evaluation."""
        gc.collect()

        # Count specific object types
        object_counts = {}
        for obj in gc.get_objects():
            obj_type = type(obj).__name__
            if obj_type in ["ReferenceValue", "HierarchicalContextDict", "FormulaConfig", "EvaluationResult"]:
                object_counts[obj_type] = object_counts.get(obj_type, 0) + 1

        self.metrics.object_creation_counts = object_counts

    def run_baseline_measurements(self, num_cycles: int = 10) -> None:
        """Run baseline measurements for specified number of cycles."""
        print(f"Running {num_cycles} evaluation cycles for baseline...")

        for i in range(num_cycles):
            for sensor_config in self.sensor_configs[:5]:  # Test first 5 sensors
                self.measure_evaluation_cycle(sensor_config)

            if i == 0:
                # Measure cache and object counts after warm-up
                self.measure_cache_performance()
                self.count_object_creations()

        print("Baseline measurements complete.")

    def save_baseline(self, output_path: str = "performance_baseline.json") -> None:
        """Save baseline metrics to file."""
        output_file = Path(output_path)
        output_file.write_text(self.metrics.to_json())
        print(f"Baseline saved to {output_file}")

        # Also print summary
        print("\n=== Performance Baseline Summary ===")
        print(self.metrics.to_json())


def create_mock_hass():
    """Create mock Home Assistant for testing."""

    class MockState:
        def __init__(self, entity_id, state, attributes=None):
            self.entity_id = entity_id
            self.state = state
            self.attributes = attributes or {}
            self.last_changed = "2025-01-01T12:00:00+00:00"
            self.last_updated = "2025-01-01T12:00:00+00:00"

    class MockHass:
        def __init__(self):
            self.states = MockStates()
            self.data = {}  # Add data attribute for registry

    class MockStates:
        def __init__(self):
            self._states = {
                "sensor.span_panel_instantaneous_power": MockState("sensor.span_panel_instantaneous_power", "1500.0"),
                "binary_sensor.panel_status": MockState("binary_sensor.panel_status", "on"),
                "sensor.air_conditioner_energy_produced_2": MockState(
                    "sensor.air_conditioner_energy_produced_2",
                    None,
                    {"last_valid_state": "3707.6", "last_valid_changed": "2025-01-01T11:45:00+00:00"},
                ),
            }

        def get(self, entity_id):
            return self._states.get(entity_id)

    return MockHass()


@pytest.fixture
def mock_hass():
    """Mock Home Assistant fixture for pytest."""
    return create_mock_hass()


def test_performance_baseline(mock_hass):
    """Test to establish performance baseline."""
    # Use SPAN test YAML
    test_yaml = "tests/fixtures/integration/span_panel_variable_injection_test.yaml"

    baseline = PerformanceBaseline(test_yaml)
    baseline.load_test_config()
    baseline.setup_evaluator(mock_hass)
    baseline.run_baseline_measurements(num_cycles=5)
    baseline.save_baseline("tests/performance_baseline.json")


if __name__ == "__main__":
    # Run standalone
    import sys

    if len(sys.argv) > 1:
        test_yaml = sys.argv[1]
    else:
        test_yaml = "tests/fixtures/integration/span_panel_variable_injection_test.yaml"

    mock = create_mock_hass()
    baseline = PerformanceBaseline(test_yaml)
    baseline.load_test_config()
    baseline.setup_evaluator(mock)
    baseline.run_baseline_measurements(num_cycles=10)
    baseline.save_baseline("performance_baseline.json")
