"""Tests for non-numeric state handling in the evaluator."""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.config_models import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.evaluator_config import CircuitBreakerConfig
from ha_synthetic_sensors.exceptions import NonNumericStateError


class TestNonNumericStateHandling:
    """Test cases for non-numeric state handling."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()
        return hass

    def test_non_numeric_state_detection(self, mock_hass):
        """Test that boolean-like states are converted to numeric values for mathematical operations."""
        evaluator = Evaluator(mock_hass)

        # Mock entity with boolean-like state
        mock_state = MagicMock()
        mock_state.state = "on"  # Boolean-like string that should convert to 1.0
        mock_state.entity_id = "switch.test"
        mock_state.attributes = {}
        mock_hass.states.get.return_value = mock_state

        config = FormulaConfig(id="test_boolean_conversion", name="test", formula="switch.test + 1")

        # Should convert "on" to 1.0 and successfully evaluate
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True  # Boolean states should be converted to numeric
        assert result.get("state") == "ok"
        assert result["value"] == 2.0  # 1.0 (from "on") + 1 = 2.0

    def test_comprehensive_boolean_conversion(self, mock_hass):
        """Test comprehensive boolean-to-numeric conversion for various device types."""
        evaluator = Evaluator(mock_hass)

        # Test cases: (state, expected_numeric_value, device_class)
        test_cases = [
            # Basic boolean states
            ("on", 1.0, None),
            ("off", 0.0, None),
            ("true", 1.0, None),
            ("false", 0.0, None),
            ("yes", 1.0, None),
            ("no", 0.0, None),
            # Door/window sensors
            ("open", 1.0, "door"),
            ("closed", 0.0, "door"),
            ("opened", 1.0, "window"),
            ("close", 0.0, "window"),
            # Presence detection
            ("home", 1.0, "presence"),
            ("away", 0.0, "presence"),
            ("present", 1.0, "occupancy"),
            ("not_home", 0.0, "presence"),
            # Motion sensors
            ("motion", 1.0, "motion"),
            ("detected", 1.0, "motion"),
            ("clear", 0.0, "motion"),
            ("no_motion", 0.0, "motion"),
            # Lock states
            ("locked", 1.0, "lock"),
            ("unlocked", 0.0, "lock"),
            # Safety sensors
            ("wet", 1.0, "moisture"),
            ("dry", 0.0, "moisture"),
            ("heat", 1.0, "heat"),
            ("cold", 0.0, "heat"),
            # Activity states
            ("active", 1.0, None),
            ("inactive", 0.0, None),
            ("running", 1.0, None),
            ("stopped", 0.0, None),
            # Connectivity
            ("connected", 1.0, "connectivity"),
            ("disconnected", 0.0, "connectivity"),
            ("online", 1.0, "connectivity"),
            ("offline", 0.0, "connectivity"),
            # Battery states
            ("charging", 1.0, "battery"),
            ("not_charging", 0.0, "battery"),
            ("low", 0.0, "battery"),
            ("normal", 1.0, "battery"),
            # Alarm states
            ("armed_home", 1.0, "safety"),
            ("disarmed", 0.0, "safety"),
        ]

        for state_value, expected_numeric, device_class in test_cases:
            # Mock entity with specific state and device class using a known domain
            entity_id = f"sensor.{state_value.replace('_', '')}"
            mock_state = MagicMock()
            mock_state.state = state_value
            mock_state.entity_id = entity_id
            mock_state.attributes = {"device_class": device_class} if device_class else {}

            # Use side_effect to return the right mock state for this specific entity_id
            def mock_states_get(requested_entity_id, current_entity_id=entity_id, current_mock_state=mock_state):
                if requested_entity_id == current_entity_id:
                    return current_mock_state
                return None

            mock_hass.states.get.side_effect = mock_states_get

            config = FormulaConfig(id=f"test_{state_value}", name=f"test_{state_value}", formula=f"{entity_id} * 10")

            result = evaluator.evaluate_formula(config)

            assert result["success"] is True, f"Failed for state '{state_value}'"
            assert result.get("state") == "ok", f"Wrong state for '{state_value}'"
            expected_result = expected_numeric * 10
            assert result["value"] == expected_result, f"Expected {expected_result} for '{state_value}', got {result['value']}"

    def test_truly_non_numeric_state_detection(self, mock_hass):
        """Test that truly non-numeric states are properly detected and handled as fatal errors."""
        evaluator = Evaluator(mock_hass)

        # Mock entity with truly non-numeric state
        mock_state = MagicMock()
        mock_state.state = "starting_up"  # Truly non-numeric string
        mock_state.entity_id = "sensor.status"
        mock_state.attributes = {}
        mock_hass.states.get.return_value = mock_state

        config = FormulaConfig(id="test_non_numeric", name="test", formula="sensor.status + 1")

        # Should detect non-numeric state and treat as fatal error
        result = evaluator.evaluate_formula(config)
        assert result["success"] is False  # Fatal error
        assert result.get("state") == "unavailable"

    def test_unavailable_state_handling(self, mock_hass):
        """Test that 'unavailable' and 'unknown' states reflect to synthetic sensor state."""
        evaluator = Evaluator(mock_hass)

        # Test unavailable state
        mock_state = MagicMock()
        mock_state.state = "unavailable"
        mock_state.entity_id = "sensor.temp"
        mock_state.attributes = {}
        mock_hass.states.get.return_value = mock_state

        config = FormulaConfig(id="test_unavailable", name="test", formula="sensor.temp + 1")

        result = evaluator.evaluate_formula(config)
        assert result["success"] is True  # Non-fatal - reflects dependency state
        assert result.get("state") == "unavailable"  # Reflects unavailable dependency
        assert "sensor.temp" in result.get("unavailable_dependencies", [])

        # Test unknown state
        mock_state.state = "unknown"
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True  # Non-fatal - reflects dependency state
        assert result.get("state") == "unknown"  # Reflects unknown dependency
        assert "sensor.temp" in result.get("unavailable_dependencies", [])

    def test_non_numeric_exception_raised(self, mock_hass):
        """Test that NonNumericStateError is raised for truly non-numeric values."""
        from ha_synthetic_sensors.validation_helper import convert_to_numeric

        # These should raise NonNumericStateError
        with pytest.raises(NonNumericStateError) as exc_info:
            convert_to_numeric("on", "switch.test")
        assert "switch.test" in str(exc_info.value)
        assert "on" in str(exc_info.value)

        with pytest.raises(NonNumericStateError):
            convert_to_numeric("running", "sensor.status")

    def test_mixed_dependencies_handling(self, mock_hass):
        """Test handling of mixed numeric and non-numeric dependencies."""
        evaluator = Evaluator(mock_hass)

        def mock_states_get(entity_id):
            """Mock state getter with mixed states."""
            if entity_id == "sensor.numeric":
                state = MagicMock()
                state.state = "42.5"
                state.entity_id = entity_id
                state.attributes = {}
                return state
            elif entity_id == "sensor.non_numeric":
                state = MagicMock()
                state.state = "unavailable"
                state.entity_id = entity_id
                state.attributes = {}
                return state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        config = FormulaConfig(id="mixed_test", name="mixed", formula="sensor.numeric + sensor.non_numeric")

        # Should reflect unavailable state due to unavailable dependency
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True
        assert result.get("state") == "unavailable"  # Reflects worst dependency state
        assert "sensor.non_numeric" in result.get("unavailable_dependencies", [])

    def test_circuit_breaker_for_non_numeric_states(self, mock_hass):
        """Test that unavailable states reflect to synthetic sensor (non-fatal)."""
        cb_config = CircuitBreakerConfig(max_fatal_errors=2, track_transitory_errors=True)
        evaluator = Evaluator(mock_hass, circuit_breaker_config=cb_config)

        # Mock entity that is temporarily unavailable
        mock_state = MagicMock()
        mock_state.state = "unavailable"  # Use unavailable state instead of truly non-numeric
        mock_state.entity_id = "sensor.temperature"
        mock_state.attributes = {"device_class": "temperature"}
        mock_hass.states.get.return_value = mock_state

        config = FormulaConfig(id="temp_test", name="temp", formula="sensor.temperature + 10")

        # Should continue trying even after many attempts (reflects dependency state)
        for _i in range(10):
            result = evaluator.evaluate_formula(config)
            assert result["success"] is True
            assert result.get("state") == "unavailable"  # Reflects unavailable dependency
            assert "sensor.temperature" in result.get("unavailable_dependencies", [])

    def test_backward_compatibility_fallback(self, mock_hass):
        """Test that convert_to_numeric properly raises exception for non-numeric states."""
        from ha_synthetic_sensors.validation_helper import convert_to_numeric

        # Should raise NonNumericStateError instead of returning 0.0
        with pytest.raises(NonNumericStateError) as exc_info:
            convert_to_numeric("unavailable", "sensor.broken")
        assert "sensor.broken" in str(exc_info.value)
        assert "unavailable" in str(exc_info.value)

    def test_missing_vs_non_numeric_entities(self, mock_hass):
        """Test distinction between missing entities (fatal) and non-numeric."""
        cb_config = CircuitBreakerConfig(max_fatal_errors=2)
        evaluator = Evaluator(mock_hass, circuit_breaker_config=cb_config)

        def mock_states_get(entity_id):
            if entity_id == "sensor.missing":
                return None  # Missing entity
            elif entity_id == "sensor.non_numeric":
                state = MagicMock()
                state.state = "unavailable"  # Use clearly transitory state
                state.entity_id = entity_id
                state.attributes = {}  # Add empty attributes dict
                return state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        # Test missing entity (should be fatal)
        missing_config = FormulaConfig(id="missing_test", name="missing", formula="sensor.missing + 1")

        result1 = evaluator.evaluate_formula(missing_config)
        assert result1["success"] is False
        assert result1.get("state") == "unavailable"

        result2 = evaluator.evaluate_formula(missing_config)
        assert result2["success"] is False

        # After max_fatal_errors, should skip evaluation
        result3 = evaluator.evaluate_formula(missing_config)
        assert result3["success"] is False
        assert "Skipping formula" in result3.get("error", "")

        # Test non-numeric entity (should be transitory)
        non_numeric_config = FormulaConfig(id="non_numeric_test", name="non_numeric", formula="sensor.non_numeric + 1")

        # Should continue evaluating even after many attempts (reflects dependency state)
        for _i in range(10):
            result = evaluator.evaluate_formula(non_numeric_config)
            assert result["success"] is True
            assert result.get("state") == "unavailable"  # Reflects unavailable dependency

    def test_startup_race_condition_none_state(self, mock_hass):
        """Test handling of startup race condition where entities exist but have None state values (reflects as unavailable)."""
        evaluator = Evaluator(mock_hass)

        # Mock entity that exists but has None state (startup race condition)
        mock_state = MagicMock()
        mock_state.state = None  # This is the key issue - entity exists but state is None
        mock_state.entity_id = "sensor.span_panel_power"
        mock_state.attributes = {"device_class": "power"}
        mock_hass.states.get.return_value = mock_state

        config = FormulaConfig(
            id="startup_race_test",
            name="startup_race",
            formula="sensor.span_panel_power + 10",
        )

        # None state should reflect as unavailable (non-fatal, can recover when entity comes online)
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True  # Non-fatal - reflects dependency state
        assert result.get("state") == "unavailable"  # Reflects unavailable dependency
        assert "sensor.span_panel_power" in result.get("unavailable_dependencies", [])

    def test_startup_race_condition_solar_formula(self, mock_hass):
        """Test the specific solar inverter formula case from the reported bug."""
        evaluator = Evaluator(mock_hass)

        def mock_states_get(entity_id):
            """Mock state getter simulating startup race condition."""
            if entity_id in [
                "sensor.span_panel_unmapped_tab_1_power",
                "sensor.span_panel_unmapped_tab_2_power",
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
                "leg1_power": "sensor.span_panel_unmapped_tab_1_power",
                "leg2_power": "sensor.span_panel_unmapped_tab_2_power",
            },
        )

        # Should handle the None states gracefully and return unavailable
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True
        assert result.get("state") == "unavailable"  # None states are treated as unavailable
        # Both legs should be identified as unavailable
        unavailable_deps = result.get("unavailable_dependencies", [])
        assert "sensor.span_panel_unmapped_tab_1_power" in unavailable_deps
        assert "sensor.span_panel_unmapped_tab_2_power" in unavailable_deps

    def test_startup_race_condition_mixed_states(self, mock_hass):
        """Test mixed scenario where some entities are ready and others have None state."""
        evaluator = Evaluator(mock_hass)

        def mock_states_get(entity_id):
            """Mock state getter with mixed availability."""
            if entity_id == "sensor.ready_entity":
                # Entity is ready with valid state
                state = MagicMock()
                state.state = "25.5"
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            elif entity_id == "sensor.startup_entity":
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
                "ready_entity": "sensor.ready_entity",
                "startup_entity": "sensor.startup_entity",
            },
        )

        # Should handle mixed states and return unavailable due to unavailable entity
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True
        assert result.get("state") == "unavailable"  # Reflects worst dependency state
        assert "sensor.startup_entity" in result.get("unavailable_dependencies", [])

    def test_none_state_value_conversion(self, mock_hass):
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

    def test_missing_entity_handling_in_evaluation(self, mock_hass):
        """Test that missing entities are properly handled in formula evaluation."""
        evaluator = Evaluator(mock_hass)

        # Mock that no entities exist
        mock_hass.states.get.return_value = None

        config = FormulaConfig(
            id="missing_entities_test", name="Missing Entities Test", formula="sensor.missing1 + sensor.missing2"
        )

        # Missing entities should result in fatal error (success=False)
        result = evaluator.evaluate_formula(config)
        assert result["success"] is False
        assert result.get("state") == "unavailable"
        missing_deps = result.get("missing_dependencies", [])
        assert "sensor.missing1" in missing_deps
        assert "sensor.missing2" in missing_deps

    def test_unavailable_and_unknown_entity_states(self, mock_hass):
        """Test comprehensive handling of 'unavailable' and 'unknown' entity states."""
        evaluator = Evaluator(mock_hass)

        def mock_states_get(entity_id):
            """Mock state getter with various unavailable states."""
            if entity_id == "sensor.unavailable_entity":
                state = MagicMock()
                state.state = "unavailable"
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            elif entity_id == "sensor.unknown_entity":
                state = MagicMock()
                state.state = "unknown"
                state.entity_id = entity_id
                state.attributes = {"device_class": "energy"}
                return state
            elif entity_id == "sensor.valid_entity":
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
            formula="sensor.unavailable_entity + 10",
        )

        result = evaluator.evaluate_formula(unavailable_config)
        assert result["success"] is True
        assert result.get("state") == "unavailable"  # Reflects unavailable dependency
        assert "sensor.unavailable_entity" in result.get("unavailable_dependencies", [])

        # Test formula with unknown entity
        unknown_config = FormulaConfig(id="unknown_test", name="Unknown Test", formula="sensor.unknown_entity + 20")

        result = evaluator.evaluate_formula(unknown_config)
        assert result["success"] is True
        assert result.get("state") == "unknown"  # Reflects unknown dependency
        assert "sensor.unknown_entity" in result.get("unavailable_dependencies", [])

        # Test formula mixing valid and unavailable entities
        mixed_config = FormulaConfig(
            id="mixed_unavailable_test",
            name="Mixed Unavailable Test",
            formula="valid_entity + unavailable_entity",
            variables={
                "valid_entity": "sensor.valid_entity",
                "unavailable_entity": "sensor.unavailable_entity",
            },
        )

        result = evaluator.evaluate_formula(mixed_config)
        assert result["success"] is True
        assert result.get("state") == "unavailable"  # Reflects worst dependency state (unavailable > unknown)
        assert "sensor.unavailable_entity" in result.get("unavailable_dependencies", [])
        # Should not include the valid entity in unavailable dependencies
        assert "sensor.valid_entity" not in result.get("unavailable_dependencies", [])

        # Test formula with both unknown and unavailable entities
        both_config = FormulaConfig(
            id="both_unavailable_test",
            name="Both Unavailable Test",
            formula="unavailable_entity + unknown_entity",
            variables={
                "unavailable_entity": "sensor.unavailable_entity",
                "unknown_entity": "sensor.unknown_entity",
            },
        )

        result = evaluator.evaluate_formula(both_config)
        assert result["success"] is True
        assert result.get("state") == "unavailable"  # Reflects worst dependency state (unavailable > unknown)
        unavailable_deps = result.get("unavailable_dependencies", [])
        assert "sensor.unavailable_entity" in unavailable_deps
        assert "sensor.unknown_entity" in unavailable_deps

    def test_startup_race_all_scenarios(self, mock_hass):
        """Test all startup race condition scenarios: None, unavailable, unknown, missing."""
        evaluator = Evaluator(mock_hass)

        def mock_states_get(entity_id):
            """Mock state getter simulating various startup conditions."""
            if entity_id == "sensor.none_state":
                state = MagicMock()
                state.state = None  # Startup race condition
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            elif entity_id == "sensor.unavailable_state":
                state = MagicMock()
                state.state = "unavailable"
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            elif entity_id == "sensor.unknown_state":
                state = MagicMock()
                state.state = "unknown"
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            elif entity_id == "sensor.missing_entity":
                return None  # Missing entity
            elif entity_id == "sensor.ready_entity":
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
                "none_val": "sensor.none_state",
                "unavailable_val": "sensor.unavailable_state",
                "unknown_val": "sensor.unknown_state",
                "ready_val": "sensor.ready_entity",
            },
        )

        result = evaluator.evaluate_formula(startup_config)
        assert result["success"] is True
        assert result.get("state") == "unavailable"  # Reflects worst dependency state

        # All problematic entities should be in unavailable_dependencies
        unavailable_deps = result.get("unavailable_dependencies", [])
        assert "sensor.none_state" in unavailable_deps
        assert "sensor.unavailable_state" in unavailable_deps
        assert "sensor.unknown_state" in unavailable_deps
        # Ready entity should not be in unavailable dependencies
        assert "sensor.ready_entity" not in unavailable_deps

        # Test missing entity (should be fatal error)
        missing_config = FormulaConfig(
            id="missing_startup_test",
            name="Missing Startup Test",
            formula="sensor.missing_entity + 10",
        )

        result = evaluator.evaluate_formula(missing_config)
        assert result["success"] is False
        assert result.get("state") == "unavailable"
        assert "sensor.missing_entity" in result.get("missing_dependencies", [])
