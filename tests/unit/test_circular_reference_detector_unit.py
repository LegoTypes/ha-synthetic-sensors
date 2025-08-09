import pytest

from ha_synthetic_sensors.evaluator_phases.dependency_management.circular_reference_detector import (
    CircularReferenceDetector,
)
from ha_synthetic_sensors.exceptions import CircularDependencyError


class TestCircularReferenceDetectorUnit:
    def setup_method(self) -> None:
        self.detector = CircularReferenceDetector()

    def test_no_cycle_returns_empty_set(self) -> None:
        context = {
            "sensor_name": "a",
            "sensor_dependencies": {
                "a": {"b"},
                "b": set(),
            },
            "sensor_registry": {},
        }
        result = self.detector.manage("circular_detection", context)
        assert result == set()

    def test_self_reference_cycle_raises(self) -> None:
        context = {
            "sensor_name": "a",
            "dependencies": {"a"},
            "sensor_registry": {},
        }
        with pytest.raises(CircularDependencyError) as exc:
            self.detector.manage("circular_detection", context)
        assert "a" in str(exc.value)

    def test_state_reference_is_not_cycle(self) -> None:
        # Attribute formulas may reference 'state' of the main sensor; this is not recursive
        context = {
            "sensor_name": "attr_sensor",
            "dependencies": {"state"},
            "sensor_registry": {},
        }
        result = self.detector.manage("circular_detection", context)
        assert result == set()

    def test_two_node_cycle_raises_with_cycle(self) -> None:
        context = {
            "sensor_name": "a",
            "sensor_dependencies": {
                "a": {"b"},
                "b": {"a"},
            },
            "sensor_registry": {},
        }
        with pytest.raises(CircularDependencyError) as exc:
            self.detector.manage("circular_detection", context)
        # Expect cycle path like ["a", "b", "a"]
        msg = str(exc.value)
        assert "a" in msg and "b" in msg

    def test_three_node_cycle_prefers_sensor_cycle(self) -> None:
        graph = {
            "a": {"b"},
            "b": {"c"},
            "c": {"a"},
            "x": set(),
        }
        context = {
            "sensor_name": "a",
            "sensor_dependencies": graph,
            "sensor_registry": {},
        }
        with pytest.raises(CircularDependencyError) as exc:
            self.detector.manage("circular_detection", context)
        msg = str(exc.value)
        assert "a" in msg and "b" in msg and "c" in msg
