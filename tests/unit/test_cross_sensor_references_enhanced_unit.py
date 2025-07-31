"""Enhanced cross-sensor reference tests for Phase 3 features."""

import pytest
from typing import Any

from ha_synthetic_sensors.evaluator_phases.sensor_registry.sensor_registry_phase import SensorRegistryPhase
from ha_synthetic_sensors.evaluator_phases.variable_resolution.cross_sensor_resolver import CrossSensorReferenceResolver
from ha_synthetic_sensors.exceptions import CrossSensorResolutionError, DependencyValidationError, MissingDependencyError
from ha_synthetic_sensors.type_definitions import ContextValue


class TestCrossSensorReferencesEnhanced:
    """Test enhanced cross-sensor reference functionality (Phase 3)."""

    def test_enhanced_error_handling_missing_registry(self) -> None:
        """Test enhanced error handling when registry is not available."""
        resolver = CrossSensorReferenceResolver()

        with pytest.raises(MissingDependencyError) as exc_info:
            resolver.resolve("test_sensor", "test_sensor", {})

        assert "registry not available" in str(exc_info.value)

    def test_enhanced_error_handling_unregistered_sensor(self) -> None:
        """Test enhanced error handling for unregistered sensor."""
        registry = SensorRegistryPhase()
        resolver = CrossSensorReferenceResolver(registry)

        with pytest.raises(CrossSensorResolutionError) as exc_info:
            resolver.resolve("unregistered_sensor", "unregistered_sensor", {})

        assert "dependency validation failed" in str(exc_info.value)

    def test_enhanced_error_handling_registered_but_no_value(self) -> None:
        """Test enhanced error handling for registered sensor with no value."""
        registry = SensorRegistryPhase()
        resolver = CrossSensorReferenceResolver(registry)

        # Register sensor but don't set a value (will be 0.0 by default)
        registry.register_sensor("test_sensor", "sensor.test_sensor")

        # This should succeed since the default value is 0.0
        result = resolver.resolve("test_sensor", "test_sensor", {})
        assert result == 0.0

    def test_enhanced_error_handling_dependency_validation_failure(self) -> None:
        """Test enhanced error handling for dependency validation failure."""
        registry = SensorRegistryPhase()
        resolver = CrossSensorReferenceResolver(registry)

        # Register sensor with None value
        registry.register_sensor("test_sensor", "sensor.test_sensor")
        registry.update_sensor_value("test_sensor", None)  # type: ignore[arg-type]

        with pytest.raises(CrossSensorResolutionError) as exc_info:
            resolver.resolve("test_sensor", "test_sensor", {})

        assert "dependency validation failed" in str(exc_info.value)

    def test_dependency_usage_tracking(self) -> None:
        """Test dependency usage tracking functionality."""
        registry = SensorRegistryPhase()
        resolver = CrossSensorReferenceResolver(registry)

        # Register sensor with value
        registry.register_sensor("test_sensor", "sensor.test_sensor", 100.0)

        # Resolve multiple times
        resolver.resolve("test_sensor", "test_sensor", {})
        resolver.resolve("test_sensor", "test_sensor", {})
        resolver.resolve("test_sensor", "test_sensor", {})

        # Check usage stats
        stats = resolver.get_dependency_usage_stats()
        assert "test_sensor:test_sensor" in stats
        assert stats["test_sensor:test_sensor"] == 3

    def test_dependency_usage_tracking_clear(self) -> None:
        """Test clearing dependency usage tracker."""
        registry = SensorRegistryPhase()
        resolver = CrossSensorReferenceResolver(registry)

        # Register sensor with value
        registry.register_sensor("test_sensor", "sensor.test_sensor", 100.0)

        # Resolve once
        resolver.resolve("test_sensor", "test_sensor", {})

        # Check usage stats
        stats = resolver.get_dependency_usage_stats()
        assert len(stats) == 1

        # Clear tracker
        resolver.clear_dependency_usage_tracker()

        # Check stats are cleared
        stats = resolver.get_dependency_usage_stats()
        assert len(stats) == 0

    def test_dependency_validation_success(self) -> None:
        """Test successful dependency validation."""
        registry = SensorRegistryPhase()
        resolver = CrossSensorReferenceResolver(registry)

        # Register sensor with value
        registry.register_sensor("test_sensor", "sensor.test_sensor", 100.0)

        # Validate dependency availability
        assert resolver._validate_dependency_availability("test_sensor") is True

    def test_dependency_validation_failure_not_registered(self) -> None:
        """Test dependency validation failure for unregistered sensor."""
        registry = SensorRegistryPhase()
        resolver = CrossSensorReferenceResolver(registry)

        # Validate dependency availability for unregistered sensor
        assert resolver._validate_dependency_availability("unregistered_sensor") is False

    def test_dependency_validation_failure_no_value(self) -> None:
        """Test dependency validation failure for sensor with no value."""
        registry = SensorRegistryPhase()
        resolver = CrossSensorReferenceResolver(registry)

        # Register sensor but don't set a value (will be 0.0 by default)
        registry.register_sensor("test_sensor", "sensor.test_sensor")

        # Validate dependency availability (should succeed since default is 0.0)
        assert resolver._validate_dependency_availability("test_sensor") is True

    def test_dependency_validation_failure_no_registry(self) -> None:
        """Test dependency validation failure when no registry is available."""
        resolver = CrossSensorReferenceResolver()

        # Validate dependency availability without registry
        assert resolver._validate_dependency_availability("test_sensor") is False

    def test_dependency_validation_failure_none_value(self) -> None:
        """Test dependency validation failure for sensor with None value."""
        registry = SensorRegistryPhase()
        resolver = CrossSensorReferenceResolver(registry)

        # Register sensor and explicitly set None value
        registry.register_sensor("test_sensor", "sensor.test_sensor")
        registry.update_sensor_value("test_sensor", None)  # type: ignore[arg-type]

        # Validate dependency availability (should fail with None value)
        assert resolver._validate_dependency_availability("test_sensor") is False

    def test_enhanced_resolution_success(self) -> None:
        """Test successful enhanced resolution."""
        registry = SensorRegistryPhase()
        resolver = CrossSensorReferenceResolver(registry)

        # Register sensor with value
        registry.register_sensor("test_sensor", "sensor.test_sensor", 100.0)

        # Resolve successfully
        result = resolver.resolve("test_sensor", "test_sensor", {})
        assert result == 100.0

    def test_enhanced_resolution_with_different_types(self) -> None:
        """Test enhanced resolution with different data types."""
        registry = SensorRegistryPhase()
        resolver = CrossSensorReferenceResolver(registry)

        # Test string value
        registry.register_sensor("string_sensor", "sensor.string_sensor", "test_value")
        result = resolver.resolve("string_sensor", "string_sensor", {})
        assert result == "test_value"

        # Test boolean value
        registry.register_sensor("bool_sensor", "sensor.bool_sensor", True)
        result = resolver.resolve("bool_sensor", "bool_sensor", {})
        assert result is True

        # Test float value
        registry.register_sensor("float_sensor", "sensor.float_sensor", 42.5)
        result = resolver.resolve("float_sensor", "float_sensor", {})
        assert result == 42.5

    def test_enhanced_resolution_non_string_value(self) -> None:
        """Test enhanced resolution with non-string variable value."""
        registry = SensorRegistryPhase()
        resolver = CrossSensorReferenceResolver(registry)

        # Try to resolve with non-string value
        result = resolver.resolve("test_sensor", 123, {})
        assert result is None

    def test_enhanced_resolution_with_context(self) -> None:
        """Test enhanced resolution with context parameter."""
        registry = SensorRegistryPhase()
        resolver = CrossSensorReferenceResolver(registry)

        # Register sensor with value
        registry.register_sensor("test_sensor", "sensor.test_sensor", 100.0)

        # Resolve with context
        context: dict[str, ContextValue] = {"formula_name": "test_formula"}
        result = resolver.resolve("test_sensor", "test_sensor", context)
        assert result == 100.0
