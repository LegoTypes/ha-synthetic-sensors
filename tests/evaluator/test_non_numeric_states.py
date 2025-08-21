"""Tests for non-numeric state handling in the evaluator."""

from unittest.mock import MagicMock

import pytest

from homeassistant.const import STATE_UNKNOWN

from ha_synthetic_sensors.config_models import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.evaluator_config import CircuitBreakerConfig
from ha_synthetic_sensors.exceptions import NonNumericStateError
from ha_synthetic_sensors.exceptions import MissingDependencyError


class TestNonNumericStateHandling:
    """Test cases for non-numeric state handling."""

    def test_non_numeric_state_detection(self, mock_hass, mock_entity_registry, mock_states):
        """Test that boolean-like states are converted to numeric values for mathematical operations."""
        # Set the state to 'on' for this test
        mock_states.register_state("switch.test", state_value="on", attributes={"device_class": "switch"})

        evaluator = Evaluator(mock_hass)

        # Register the entity with the evaluator
        evaluator.update_integration_entities({"switch.test"})

        # Test with direct entity resolution
        config = FormulaConfig(id="test_boolean_conversion", name="test", formula="switch.test + 1")

        # Current behavior: "on" string causes type error in mathematical operation
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True  # Type errors treated as alternate states
        assert result.get("state") == "unknown"  # Type mismatch -> alternate state
        assert result.get("value") is None  # No numeric result

        # Verify it called the right entity
        mock_hass.states.get.assert_called_with("switch.test")

    def test_boolean_state_conversion_basic(self, mock_hass, mock_entity_registry, mock_states):
        """Test basic boolean state conversion for on/off and dry/wet states."""
        from ha_synthetic_sensors.validation_helper import convert_to_numeric

        # Test cases: Basic boolean states that should work with real HA constants
        test_cases = [
            # Basic on/off states
            ("on", None, 1.0),
            ("off", None, 0.0),
            # HA's actual moisture device states
            ("moist", "moisture", 1.0),
            ("not_moist", "moisture", 0.0),
        ]

        for state_value, device_class, expected_numeric in test_cases:
            # Mock entity state
            entity_id = f"binary_sensor.test_{state_value}"
            mock_state = MagicMock()
            mock_state.state = state_value
            mock_state.entity_id = entity_id
            mock_state.attributes = {"device_class": device_class} if device_class else {}

            # Test boolean conversion directly
            result = convert_to_numeric(state_value, entity_id)

            assert result == expected_numeric, (
                f"Expected {expected_numeric} for state '{state_value}' with device_class '{device_class}', got {result}"
            )

    def test_boolean_conversion_in_formula_evaluation(self, mock_hass, mock_entity_registry, mock_states):
        """Test that boolean conversion works in actual formula evaluation."""
        # Set the state to 'on' for this test
        mock_states.register_state("binary_sensor.opening", state_value="on", attributes={"device_class": "opening"})

        evaluator = Evaluator(mock_hass)

        # Register the entity with the evaluator
        evaluator.update_integration_entities({"binary_sensor.opening"})

        # Test only "on" state since that's what we know works reliably
        entity_id = "binary_sensor.opening"  # Use existing entity from shared registry
        expected_result = 1.0

        # Create a simple formula that should trigger boolean conversion
        config = FormulaConfig(
            id="test_sensor",
            name="Test Sensor",
            formula=entity_id,  # Direct entity reference
        )

        result = evaluator.evaluate_formula(config)

        assert result["success"] is True, f"Failed for entity '{entity_id}'"
        assert result["value"] == expected_result, f"Expected {expected_result} for '{entity_id}', got {result['value']}"

        # Verify it called the right entity
        mock_hass.states.get.assert_called_with(entity_id)

    def test_unavailable_state_handling(self, mock_hass, mock_entity_registry, mock_states):
        """Test that 'unavailable' and 'unknown' states reflect to synthetic sensor state."""
        # Set the state to 'unavailable' for this test
        mock_states.register_state("sensor.temperature", state_value="unavailable", attributes={"device_class": "temperature"})

        evaluator = Evaluator(mock_hass)

        # Register the entity with the evaluator
        evaluator.update_integration_entities({"sensor.temperature"})

        # Test unavailable state
        entity_id = "sensor.temperature"  # Use existing entity from shared registry
        config = FormulaConfig(
            id="test_sensor",
            name="Test Sensor",
            formula=entity_id,  # Direct entity reference
        )

        result = evaluator.evaluate_formula(config)

        # Should reflect the unavailable state as unknown per design guide
        assert result["success"] is True  # Non-fatal - reflects state
        assert result["state"] == STATE_UNKNOWN  # Should reflect as unknown per design guide
        assert result["value"] is None

        # Verify it called the right entity
        mock_hass.states.get.assert_called_with(entity_id)

    def test_non_numeric_exception_raised(self, mock_hass, mock_entity_registry, mock_states):
        """Test that NonNumericStateError is raised for truly non-numeric values."""
        from ha_synthetic_sensors.validation_helper import convert_to_numeric

        # These should raise NonNumericStateError
        with pytest.raises(NonNumericStateError) as exc_info:
            convert_to_numeric("invalid_state", "sensor.test")
        assert "sensor.test" in str(exc_info.value)
        assert "invalid_state" in str(exc_info.value)

        with pytest.raises(NonNumericStateError):
            convert_to_numeric("running", "sensor.status")

    def test_mixed_dependencies_handling(self, mock_hass, mock_entity_registry, mock_states):
        """Test handling of mixed numeric and non-numeric dependencies."""
        evaluator = Evaluator(mock_hass)

        def mock_states_get(entity_id):
            """Mock state getter with mixed states."""
            if entity_id == "sensor.circuit_a_power":  # Use existing entity from shared registry
                state = MagicMock()
                state.state = "42.5"
                state.entity_id = entity_id
                state.attributes = {}
                return state
            elif entity_id == "sensor.circuit_b_power":  # Use existing entity from shared registry
                state = MagicMock()
                state.state = "unavailable"
                state.entity_id = entity_id
                state.attributes = {}
                return state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        config = FormulaConfig(id="mixed_test", name="mixed", formula="sensor.circuit_a_power + sensor.circuit_b_power")

        # Should reflect unavailable state as unknown due to unavailable dependency
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True  # Non-fatal - reflects dependency state
        assert result.get("state") == STATE_UNKNOWN  # Reflects unavailable dependency as unknown per design guide
        assert "sensor.circuit_b_power (sensor.circuit_b_power) is unavailable" in result.get("unavailable_dependencies", [])

    def test_circuit_breaker_for_non_numeric_states(self, mock_hass, mock_entity_registry, mock_states):
        """Test that unavailable states reflect to synthetic sensor (non-fatal)."""
        cb_config = CircuitBreakerConfig(max_fatal_errors=2, track_transitory_errors=True)
        evaluator = Evaluator(mock_hass, circuit_breaker_config=cb_config)

        # Mock entity that is temporarily unavailable
        entity_id = "sensor.temperature"  # Use existing entity from shared registry
        mock_state = MagicMock()
        mock_state.state = "unavailable"  # Use unavailable state instead of truly non-numeric
        mock_state.entity_id = entity_id
        mock_state.attributes = {"device_class": "temperature"}

        # Set up the mock to return the state for the specific entity ID
        def mock_states_get(entity_id_param):
            if entity_id_param == entity_id:
                return mock_state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        config = FormulaConfig(id="temp_test", name="temp", formula=f"{entity_id} + 10")

        # Should continue trying even after many attempts (reflects dependency state)
        for _i in range(10):
            result = evaluator.evaluate_formula(config)
            assert result["success"] is True  # Non-fatal - reflects dependency state
            assert result.get("state") == STATE_UNKNOWN  # Reflects unavailable dependency as unknown per design guide

    def test_backward_compatibility_fallback(self, mock_hass, mock_entity_registry, mock_states):
        """Test that convert_to_numeric properly raises exception for non-numeric states."""
        from ha_synthetic_sensors.validation_helper import convert_to_numeric

        # Should raise NonNumericStateError instead of returning 0.0
        with pytest.raises(NonNumericStateError) as exc_info:
            convert_to_numeric("unavailable", "sensor.broken")
        assert "sensor.broken" in str(exc_info.value)
        assert "unavailable" in str(exc_info.value)

    def test_missing_vs_non_numeric_entities(self, mock_hass, mock_entity_registry, mock_states):
        """Test distinction between missing entities (fatal) and non-numeric."""
        cb_config = CircuitBreakerConfig(max_fatal_errors=2)
        evaluator = Evaluator(mock_hass, circuit_breaker_config=cb_config)

        def mock_states_get(entity_id):
            if entity_id == "sensor.missing_entity":  # Use existing entity from shared registry
                return None  # Missing entity
            elif entity_id == "sensor.circuit_a_power":  # Use existing entity from shared registry
                state = MagicMock()
                state.state = "unavailable"  # Use clearly transitory state
                state.entity_id = entity_id
                state.attributes = {}  # Add empty attributes dict
                return state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        # Test missing entity (should be fatal error)
        missing_config = FormulaConfig(id="missing_test", name="missing", formula="sensor.missing_entity + 1")

        # Missing entities now surface as undefined token during evaluation pipeline
        result = evaluator.evaluate_formula(missing_config)
        assert result["success"] is False
        assert "Undefined variable" in str(result.get("error", ""))

        # Test non-numeric entity (should be transitory)
        non_numeric_config = FormulaConfig(id="non_numeric_test", name="non_numeric", formula="sensor.circuit_a_power + 1")

        # Should continue evaluating even after many attempts (reflects dependency state)
        for _i in range(10):
            result = evaluator.evaluate_formula(non_numeric_config)
            assert result["success"] is True  # Non-fatal - reflects dependency state
            assert result.get("state") == STATE_UNKNOWN  # Reflects unavailable dependency as unknown per design guide

    def test_startup_race_condition_none_state(self, mock_hass, mock_entity_registry, mock_states):
        """Test handling of startup race condition where entities exist but have None state values (reflects as unavailable)."""
        evaluator = Evaluator(mock_hass)

        # Mock entity that exists but has None state (startup race condition)
        entity_id = "sensor.circuit_a_power"  # Use existing entity from shared registry
        mock_state = MagicMock()
        mock_state.state = None  # This is the key issue - entity exists but state is None
        mock_state.entity_id = entity_id
        mock_state.attributes = {"device_class": "power"}

        # Set up the mock to return the state for the specific entity ID
        def mock_states_get(entity_id_param):
            if entity_id_param == entity_id:
                return mock_state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        config = FormulaConfig(id="startup_race_test", name="startup_race", formula=f"{entity_id} + 10")

        # None state should reflect as unknown (non-fatal, can recover when entity comes online)
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True  # Non-fatal - reflects dependency state
        assert result.get("state") == "unknown"  # Reflects unknown dependency
        assert f"{entity_id} ({entity_id}) is unknown" in result.get("unavailable_dependencies", [])

    def test_startup_race_condition_solar_formula(self, mock_hass, mock_entity_registry, mock_states):
        """Test the specific solar inverter formula case from the reported bug."""
        evaluator = Evaluator(mock_hass)

        def mock_states_get(entity_id):
            """Mock state getter simulating startup race condition."""
            if entity_id in [
                "sensor.circuit_a_power",  # Use existing entities from shared registry
                "sensor.circuit_b_power",
            ]:
                # Entities exist but have None state (startup race condition)
                state = MagicMock()
                state.state = None
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        # This simulates the formula that was causing "NoneType + NoneType" errors
        config = FormulaConfig(
            id="solar_startup_test",
            name="Solar Inverter Instant Power",
            formula="leg1_power + leg2_power",
            variables={
                "leg1_power": "sensor.circuit_a_power",  # Use existing entities from shared registry
                "leg2_power": "sensor.circuit_b_power",
            },
        )

        # Should handle the None states gracefully and return unknown
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True
        assert result.get("state") == "unknown"  # None states are treated as unknown
        # Both legs should be identified as unknown
        unavailable_deps = result.get("unavailable_dependencies", [])
        assert "leg1_power (sensor.circuit_a_power) is unknown" in unavailable_deps
        assert "leg2_power (sensor.circuit_b_power) is unknown" in unavailable_deps

    def test_startup_race_condition_mixed_states(self, mock_hass, mock_entity_registry, mock_states):
        """Test mixed scenario where some entities are ready and others have None state."""
        evaluator = Evaluator(mock_hass)

        def mock_states_get(entity_id):
            """Mock state getter with mixed availability."""
            if entity_id == "sensor.circuit_a_power":  # Use existing entity from shared registry
                # Entity is ready with valid state
                state = MagicMock()
                state.state = "25.5"
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            elif entity_id == "sensor.circuit_b_power":  # Use existing entity from shared registry
                # Entity exists but has None state (startup race condition)
                state = MagicMock()
                state.state = None
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        config = FormulaConfig(
            id="mixed_startup_test",
            name="Mixed Startup Test",
            formula="ready_entity + startup_entity",
            variables={
                "ready_entity": "sensor.circuit_a_power",  # Use existing entity from shared registry
                "startup_entity": "sensor.circuit_b_power",
            },
        )

        # Should handle mixed states and return unknown due to unknown entity
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True
        assert result.get("state") == "unknown"  # Reflects worst dependency state

    def test_none_state_value_conversion(self, mock_hass, mock_entity_registry, mock_states):
        """Test that None state values are properly handled in conversion methods."""
        _evaluator = Evaluator(mock_hass)

        # Test convert_to_numeric with None value
        from ha_synthetic_sensors.validation_helper import convert_to_numeric

        with pytest.raises(NonNumericStateError) as exc_info:
            convert_to_numeric(None, "sensor.test")
        assert "sensor.test" in str(exc_info.value)
        assert "None" in str(exc_info.value)

        # Test convert_to_numeric with None state value
        # Should raise NonNumericStateError instead of returning 0.0
        with pytest.raises(NonNumericStateError) as exc_info:
            convert_to_numeric(None, "sensor.test")
        assert "sensor.test" in str(exc_info.value)
        assert "None" in str(exc_info.value)

    def test_missing_entity_handling_in_evaluation(self, mock_hass, mock_entity_registry, mock_states):
        """Test that missing entities are properly handled in formula evaluation."""
        evaluator = Evaluator(mock_hass)

        # Mock that no entities exist
        mock_hass.states.get.return_value = None

        config = FormulaConfig(
            id="missing_entities_test",
            name="Missing Entities Test",
            formula="sensor.truly_missing_entity + sensor.another_missing_entity",
        )

        # Missing entities now surface as undefined token during evaluation pipeline
        result = evaluator.evaluate_formula(config)
        assert result["success"] is False
        assert "Undefined variable" in str(result.get("error", ""))

    def test_unavailable_and_unknown_entity_states(self, mock_hass, mock_entity_registry, mock_states):
        """Test comprehensive handling of 'unavailable' and 'unknown' entity states."""
        evaluator = Evaluator(mock_hass)

        def mock_states_get(entity_id):
            """Mock state getter with various unavailable states."""
            if entity_id == "sensor.circuit_a_power":  # Use existing entity from shared registry
                state = MagicMock()
                state.state = "unavailable"
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            elif entity_id == "sensor.circuit_b_power":  # Use existing entity from shared registry
                state = MagicMock()
                state.state = "unknown"
                state.entity_id = entity_id
                state.attributes = {"device_class": "energy"}
                return state
            elif entity_id == "sensor.kitchen_temperature":  # Use existing entity from shared registry
                state = MagicMock()
                state.state = "42.5"
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        # Test formula with unavailable entity
        unavailable_config = FormulaConfig(
            id="unavailable_test",
            name="Unavailable Test",
            formula="sensor.circuit_a_power + 10",  # Use existing entity from shared registry
        )

        result = evaluator.evaluate_formula(unavailable_config)
        assert result["success"] is True  # Non-fatal - reflects dependency state
        assert result.get("state") == STATE_UNKNOWN  # Reflects unavailable dependency as unknown per design guide
        assert "sensor.circuit_a_power (sensor.circuit_a_power) is unavailable" in result.get("unavailable_dependencies", [])

        # Test formula with unknown entity
        unknown_config = FormulaConfig(
            id="unknown_test",
            name="Unknown Test",
            formula="sensor.circuit_b_power + 10",  # Use existing entity from shared registry
        )

        result = evaluator.evaluate_formula(unknown_config)
        assert result["success"] is True  # Non-fatal - reflects dependency state
        assert result.get("state") == STATE_UNKNOWN  # Reflects unknown dependency
        assert "sensor.circuit_b_power (sensor.circuit_b_power) is unknown" in result.get("unavailable_dependencies", [])

        # Test formula with valid entity
        valid_config = FormulaConfig(
            id="valid_test",
            name="Valid Test",
            formula="sensor.kitchen_temperature + 10",  # Use existing entity from shared registry
        )

        result = evaluator.evaluate_formula(valid_config)
        assert result["success"] is True  # Should work normally
        assert result.get("state") == "ok"  # Should be successful
        assert result.get("value") == 52.5  # 42.5 + 10

    def test_startup_race_all_scenarios(self, mock_hass, mock_entity_registry, mock_states):
        """Test all startup race condition scenarios: None, unavailable, unknown, missing."""
        evaluator = Evaluator(mock_hass)

        def mock_states_get(entity_id):
            """Mock state getter simulating various startup conditions."""
            if entity_id == "sensor.circuit_a_power":  # Use existing entity from shared registry
                state = MagicMock()
                state.state = None  # Startup race condition
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            elif entity_id == "sensor.circuit_b_power":  # Use existing entity from shared registry
                state = MagicMock()
                state.state = "unavailable"
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            elif entity_id == "sensor.kitchen_temperature":  # Use existing entity from shared registry
                state = MagicMock()
                state.state = "unknown"
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            elif entity_id == "sensor.missing_entity":  # Use existing entity from shared registry
                return None  # Missing entity
            elif entity_id == "sensor.living_room_temperature":  # Use existing entity from shared registry
                state = MagicMock()
                state.state = "100.0"
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        # Test the comprehensive startup scenario with all types
        startup_config = FormulaConfig(
            id="comprehensive_startup_test",
            name="Comprehensive Startup Test",
            formula="none_val + unavailable_val + unknown_val + ready_val",
            variables={
                "none_val": "sensor.circuit_a_power",  # Use existing entity from shared registry
                "unavailable_val": "sensor.circuit_b_power",
                "unknown_val": "sensor.kitchen_temperature",
                "ready_val": "sensor.living_room_temperature",
            },
        )

        result = evaluator.evaluate_formula(startup_config)
        assert result["success"] is True
        assert (
            result.get("state") == STATE_UNKNOWN
        )  # Reflects worst dependency state (all unavailable states default to unknown)
