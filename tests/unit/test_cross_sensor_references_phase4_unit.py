"""Phase 4 cross-sensor reference tests for enhanced integration points."""

import pytest
from typing import Any
from unittest.mock import MagicMock

from ha_synthetic_sensors.config_models import Config, SensorConfig, FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.evaluator_phases.sensor_registry.sensor_registry_phase import SensorRegistryPhase
from ha_synthetic_sensors.exceptions import CrossSensorResolutionError, DependencyValidationError, MissingDependencyError
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.type_definitions import ContextValue


class TestCrossSensorReferencesPhase4:
    """Test Phase 4 enhanced integration points and advanced dependency analysis."""

    @pytest.fixture
    def mock_hass(self, mock_hass, mock_entity_registry, mock_states) -> MagicMock:
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states.get.return_value = None
        return hass

    @pytest.fixture
    def evaluator(self, mock_hass: MagicMock) -> Evaluator:
        """Create an evaluator with sensor registry."""
        evaluator = Evaluator(mock_hass)
        evaluator._sensor_registry_phase = SensorRegistryPhase()
        return evaluator

    @pytest.fixture
    def sensor_manager(self, mock_hass: MagicMock, evaluator: Evaluator) -> SensorManager:
        """Create a sensor manager with evaluator."""
        sensor_manager = SensorManager(
            mock_hass,
            MagicMock(),  # name_resolver
            MagicMock(),  # add_entities_callback
            SensorManagerConfig(),
        )
        sensor_manager._evaluator = evaluator
        return sensor_manager

    def test_enhanced_sensor_registration_integration(
        self, sensor_manager: SensorManager, evaluator: Evaluator, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test enhanced sensor registration with cross-sensor registry integration."""
        # Create test sensor configurations
        base_sensor = SensorConfig(
            unique_id="base_sensor", formulas=[FormulaConfig(id="main", formula="100", dependencies=set())], enabled=True
        )

        derived_sensor = SensorConfig(
            unique_id="derived_sensor",
            formulas=[FormulaConfig(id="main", formula="base_sensor * 2", dependencies={"base_sensor"})],
            enabled=True,
        )

        sensor_configs = [base_sensor, derived_sensor]

        # Test enhanced registration
        import asyncio

        asyncio.run(sensor_manager._register_sensors_in_cross_sensor_registry(sensor_configs))

        # Verify sensors are registered in cross-sensor registry
        assert evaluator._sensor_registry_phase.is_sensor_registered("base_sensor")
        assert evaluator._sensor_registry_phase.is_sensor_registered("derived_sensor")

    def test_cross_sensor_dependency_validation(
        self, sensor_manager: SensorManager, evaluator: Evaluator, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test cross-sensor dependency validation."""

        # Mock dependency management phase
        class MockDependencyPhase:
            def analyze_cross_sensor_dependencies(self, configs: list[SensorConfig]) -> dict[str, set[str]]:
                return {"sensor1": {"sensor2"}, "sensor2": set()}

            def validate_cross_sensor_dependencies(self, dependencies: dict[str, set[str]]) -> dict[str, Any]:
                return {"valid": True, "issues": []}

        evaluator._dependency_management_phase = MockDependencyPhase()  # type: ignore[assignment]

        # Create test sensor configurations
        sensor1 = SensorConfig(
            unique_id="sensor1",
            formulas=[FormulaConfig(id="main", formula="sensor2 * 2", dependencies={"sensor2"})],
            enabled=True,
        )

        sensor2 = SensorConfig(
            unique_id="sensor2", formulas=[FormulaConfig(id="main", formula="100", dependencies=set())], enabled=True
        )

        sensor_configs = [sensor1, sensor2]

        # Test dependency validation (should pass)
        sensor_manager._validate_cross_sensor_dependencies(sensor_configs)

    def test_cross_sensor_dependency_validation_failure(
        self, sensor_manager: SensorManager, evaluator: Evaluator, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test cross-sensor dependency validation failure."""

        # Mock dependency management phase that returns validation failure
        class MockDependencyPhase:
            def analyze_cross_sensor_dependencies(self, configs: list[SensorConfig]) -> dict[str, set[str]]:
                return {"sensor1": {"sensor2"}, "sensor2": {"sensor1"}}

            def validate_cross_sensor_dependencies(self, dependencies: dict[str, set[str]]) -> dict[str, Any]:
                return {
                    "valid": False,
                    "issues": ["Circular dependency detected"],
                    "circular_references": [["sensor1", "sensor2", "sensor1"]],
                }

        evaluator._dependency_management_phase = MockDependencyPhase()  # type: ignore[assignment]

        # Create test sensor configurations with circular dependency
        sensor1 = SensorConfig(
            unique_id="sensor1",
            formulas=[FormulaConfig(id="main", formula="sensor2 * 2", dependencies={"sensor2"})],
            enabled=True,
        )

        sensor2 = SensorConfig(
            unique_id="sensor2",
            formulas=[FormulaConfig(id="main", formula="sensor1 * 3", dependencies={"sensor1"})],
            enabled=True,
        )

        sensor_configs = [sensor1, sensor2]

        # Test dependency validation (should fail)
        with pytest.raises(ValueError) as exc_info:
            sensor_manager._validate_cross_sensor_dependencies(sensor_configs)

        assert "Cross-sensor dependency validation failed" in str(exc_info.value)
        assert "Circular references" in str(exc_info.value)

    def test_analyze_sensor_cross_dependencies(
        self, sensor_manager: SensorManager, evaluator: Evaluator, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test analyzing cross-sensor dependencies for a specific sensor."""

        # Mock dependency management phase
        class MockDependencyPhase:
            def analyze_cross_sensor_dependencies(self, configs: list[SensorConfig]) -> dict[str, set[str]]:
                return {"test_sensor": {"base_sensor", "other_sensor"}}

        evaluator._dependency_management_phase = MockDependencyPhase()  # type: ignore[assignment]

        # Create test sensor configuration
        test_sensor = SensorConfig(
            unique_id="test_sensor",
            formulas=[
                FormulaConfig(id="main", formula="base_sensor + other_sensor", dependencies={"base_sensor", "other_sensor"})
            ],
            enabled=True,
        )

        # Test dependency analysis
        dependencies = sensor_manager._analyze_sensor_cross_dependencies(test_sensor)

        assert dependencies == {"base_sensor", "other_sensor"}

    def test_handle_cross_sensor_error(
        self, sensor_manager: SensorManager, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test cross-sensor error handling."""
        # Test handling of different error types
        missing_error = MissingDependencyError("test_dependency")
        sensor_manager._handle_cross_sensor_error("test_sensor", missing_error)

        cross_sensor_error = CrossSensorResolutionError("test_sensor", "resolution failed")
        sensor_manager._handle_cross_sensor_error("test_sensor", cross_sensor_error)

        validation_error = DependencyValidationError("test_dependency", "validation failed")
        sensor_manager._handle_cross_sensor_error("test_sensor", validation_error)

        # Test handling of unexpected error
        unexpected_error = Exception("Unexpected error")
        sensor_manager._handle_cross_sensor_error("test_sensor", unexpected_error)

    def test_enhanced_evaluation_loop_integration(
        self, sensor_manager: SensorManager, evaluator: Evaluator, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test enhanced evaluation loop with cross-sensor dependency management."""

        # Mock sensors
        class MockSensor:
            def __init__(self, name: str, value: Any) -> None:
                self.name = name
                self._attr_native_value = value

            @property
            def native_value(self) -> Any:
                return self._attr_native_value

            async def async_update_sensor(self) -> None:
                pass

        # Add mock sensors to manager
        sensor_manager._sensors_by_unique_id = {
            "sensor1": MockSensor("sensor1", 100.0),  # type: ignore[dict-item]
            "sensor2": MockSensor("sensor2", 200.0),  # type: ignore[dict-item]
        }

        # Register sensors in cross-sensor registry first
        evaluator.register_sensor("sensor1", "sensor.sensor1", 0.0)
        evaluator.register_sensor("sensor2", "sensor.sensor2", 0.0)

        # Mock evaluation order method
        def mock_get_evaluation_order() -> list[str]:
            return ["sensor1", "sensor2"]

        sensor_manager._get_cross_sensor_evaluation_order = mock_get_evaluation_order  # type: ignore[method-assign]

        # Test enhanced evaluation loop
        import asyncio

        asyncio.run(sensor_manager.async_update_sensors())

        # Verify cross-sensor registry was updated
        assert evaluator._sensor_registry_phase.get_sensor_value("sensor1") == 100.0
        assert evaluator._sensor_registry_phase.get_sensor_value("sensor2") == 200.0

    def test_enhanced_evaluation_loop_error_handling(
        self, sensor_manager: SensorManager, evaluator: Evaluator, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test enhanced evaluation loop error handling."""

        # Mock sensor that raises an error
        class MockErrorSensor:
            def __init__(self, name: str) -> None:
                self.name = name

            async def async_update_sensor(self) -> None:
                raise CrossSensorResolutionError("test_sensor", "test error")

        # Add mock sensor to manager
        sensor_manager._sensors_by_unique_id = {
            "error_sensor": MockErrorSensor("error_sensor"),  # type: ignore[dict-item]
        }

        # Mock evaluation order method
        def mock_get_evaluation_order() -> list[str]:
            return ["error_sensor"]

        sensor_manager._get_cross_sensor_evaluation_order = mock_get_evaluation_order  # type: ignore[method-assign]

        # Test enhanced evaluation loop with error handling
        import asyncio

        # Should not raise an exception, should handle the error gracefully
        asyncio.run(sensor_manager.async_update_sensors())

    def test_no_dependency_management_phase_fallback(
        self, sensor_manager: SensorManager, evaluator: Evaluator, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test fallback behavior when dependency management phase is not available."""
        # Remove dependency management phase
        evaluator._dependency_management_phase = None  # type: ignore[assignment]

        # Create test sensor configuration
        test_sensor = SensorConfig(
            unique_id="test_sensor", formulas=[FormulaConfig(id="main", formula="100", dependencies=set())], enabled=True
        )

        # Test methods should handle missing dependency management gracefully
        sensor_manager._validate_cross_sensor_dependencies([test_sensor])
        dependencies = sensor_manager._analyze_sensor_cross_dependencies(test_sensor)
        assert dependencies == set()

    def test_no_evaluator_fallback(self, mock_hass: MagicMock, mock_entity_registry, mock_states) -> None:
        """Test fallback behavior when evaluator is not available."""
        # Create sensor manager without evaluator
        sensor_manager = SensorManager(
            mock_hass,
            MagicMock(),  # name_resolver
            MagicMock(),  # add_entities_callback
            SensorManagerConfig(),
        )
        sensor_manager._evaluator = None  # type: ignore[assignment]

        # Create test sensor configuration
        test_sensor = SensorConfig(
            unique_id="test_sensor", formulas=[FormulaConfig(id="main", formula="100", dependencies=set())], enabled=True
        )

        # Test methods should handle missing evaluator gracefully
        import asyncio

        asyncio.run(sensor_manager._register_sensors_in_cross_sensor_registry([test_sensor]))
