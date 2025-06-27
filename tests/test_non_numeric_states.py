"""Tests for non-numeric state handling in the evaluator."""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import (
    CircuitBreakerConfig,
    Evaluator,
    NonNumericStateError,
)


class TestNonNumericStateHandling:
    """Test cases for non-numeric state handling."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()
        return hass

    def test_non_numeric_state_detection(self, mock_hass):
        """Test that non-numeric states are properly detected and handled."""
        evaluator = Evaluator(mock_hass)

        # Mock entity with non-numeric state
        mock_state = MagicMock()
        mock_state.state = "on"  # Non-numeric string
        mock_state.entity_id = "switch.test"
        mock_state.attributes = {}
        mock_hass.states.get.return_value = mock_state

        config = FormulaConfig(id="test_non_numeric", name="test", formula="switch.test + 1")

        # Should detect non-numeric state and return unknown
        result = evaluator.evaluate_formula(config)
        assert result["success"] is False  # Switch is fundamentally non-numeric
        assert result.get("state") == "unavailable"
        assert "switch.test" in result.get("missing_dependencies", [])

    def test_numeric_extraction_from_units(self, mock_hass):
        """Test that numeric values can be extracted from unit strings."""
        evaluator = Evaluator(mock_hass)

        # Test the numeric conversion directly
        assert evaluator._convert_to_numeric("25.5°C", "sensor.temp") == 25.5
        assert evaluator._convert_to_numeric("100 kWh", "sensor.energy") == 100.0
        assert evaluator._convert_to_numeric("-5.2°F", "sensor.outdoor_temp") == -5.2

    def test_non_numeric_exception_raised(self, mock_hass):
        """Test that NonNumericStateError is raised for truly non-numeric values."""
        evaluator = Evaluator(mock_hass)

        # These should raise NonNumericStateError
        with pytest.raises(NonNumericStateError) as exc_info:
            evaluator._convert_to_numeric("on", "switch.test")
        assert "switch.test" in str(exc_info.value)
        assert "on" in str(exc_info.value)

        with pytest.raises(NonNumericStateError):
            evaluator._convert_to_numeric("running", "sensor.status")

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

        # Should return unknown due to non-numeric dependency
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True
        assert result.get("state") == "unknown"
        assert "sensor.non_numeric" in result.get("unavailable_dependencies", [])

    def test_circuit_breaker_for_non_numeric_states(self, mock_hass):
        """Test that non-numeric states are treated as transitory errors."""
        cb_config = CircuitBreakerConfig(max_fatal_errors=2, track_transitory_errors=True)
        evaluator = Evaluator(mock_hass, circuit_breaker_config=cb_config)

        # Mock entity that should be numeric but isn't
        mock_state = MagicMock()
        mock_state.state = "starting_up"
        mock_state.entity_id = "sensor.temperature"
        mock_state.attributes = {"device_class": "temperature"}
        mock_hass.states.get.return_value = mock_state

        config = FormulaConfig(id="temp_test", name="temp", formula="sensor.temperature + 10")

        # Should continue trying even after many attempts (transitory error)
        for _i in range(10):
            result = evaluator.evaluate_formula(config)
            assert result["success"] is True
            assert result.get("state") == "unknown"
            assert "sensor.temperature" in result.get("unavailable_dependencies", [])

    def test_backward_compatibility_fallback(self, mock_hass):
        """Test that _get_numeric_state properly raises exception for non-numeric states."""
        evaluator = Evaluator(mock_hass)

        # Mock state with non-numeric value
        mock_state = MagicMock()
        mock_state.state = "unavailable"
        mock_state.entity_id = "sensor.broken"

        # Should raise NonNumericStateError instead of returning 0.0
        with pytest.raises(NonNumericStateError) as exc_info:
            evaluator._get_numeric_state(mock_state)
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

        # Should continue evaluating even after many attempts
        for _i in range(10):
            result = evaluator.evaluate_formula(non_numeric_config)
            assert result["success"] is True
            assert result.get("state") == "unknown"

    def test_startup_race_condition_none_state(self, mock_hass):
        """Test handling of startup race condition where entities exist but have None state values."""
        evaluator = Evaluator(mock_hass)

        # Mock entity that exists but has None state (startup race condition)
        mock_state = MagicMock()
        mock_state.state = None  # This is the key issue - entity exists but state is None
        mock_state.entity_id = "sensor.span_panel_power"
        mock_state.attributes = {"device_class": "power"}
        mock_hass.states.get.return_value = mock_state

        config = FormulaConfig(id="startup_race_test", name="startup_race", formula="sensor.span_panel_power + 10")

        # Should handle None state gracefully and return unknown
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True
        assert result.get("state") == "unknown"
        assert "sensor.span_panel_power" in result.get("unavailable_dependencies", [])

    def test_startup_race_condition_solar_formula(self, mock_hass):
        """Test the specific solar inverter formula case from the reported bug."""
        evaluator = Evaluator(mock_hass)

        def mock_states_get(entity_id):
            """Mock state getter simulating startup race condition."""
            if entity_id in ["sensor.span_panel_unmapped_tab_1_power", "sensor.span_panel_unmapped_tab_2_power"]:
                # Entities exist but have None state (startup race condition)
                state = MagicMock()
                state.state = None
                state.entity_id = entity_id
                state.attributes = {"device_class": "power"}
                return state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        # This simulates the formula that was causing "NoneType + NoneType" errors
        config = FormulaConfig(id="solar_startup_test", name="Solar Inverter Instant Power", formula="leg1_power + leg2_power", variables={"leg1_power": "sensor.span_panel_unmapped_tab_1_power", "leg2_power": "sensor.span_panel_unmapped_tab_2_power"})

        # Should handle the None states gracefully and return unknown
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True
        assert result.get("state") == "unknown"
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

        config = FormulaConfig(id="mixed_startup_test", name="Mixed Startup Test", formula="ready_entity + startup_entity", variables={"ready_entity": "sensor.ready_entity", "startup_entity": "sensor.startup_entity"})

        # Should handle mixed states and return unknown due to unavailable entity
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True
        assert result.get("state") == "unknown"
        assert "sensor.startup_entity" in result.get("unavailable_dependencies", [])

    def test_none_state_value_conversion(self, mock_hass):
        """Test that None state values are properly handled in conversion methods."""
        evaluator = Evaluator(mock_hass)

        # Test _convert_to_numeric with None value
        with pytest.raises(NonNumericStateError) as exc_info:
            evaluator._convert_to_numeric(None, "sensor.test")
        assert "sensor.test" in str(exc_info.value)
        assert "None" in str(exc_info.value)

        # Test _get_numeric_state with None state value
        mock_state = MagicMock()
        mock_state.state = None
        mock_state.entity_id = "sensor.test"

        # Should raise NonNumericStateError instead of returning 0.0
        with pytest.raises(NonNumericStateError) as exc_info:
            evaluator._get_numeric_state(mock_state)
        assert "sensor.test" in str(exc_info.value)
        assert "None" in str(exc_info.value)

    def test_build_evaluation_context_missing_entities(self, mock_hass):
        """Test that _build_evaluation_context raises error for missing entities."""
        evaluator = Evaluator(mock_hass)

        # Mock that no entities exist
        mock_hass.states.get.return_value = None

        dependencies = {"sensor.missing1", "sensor.missing2"}

        # Missing entities should raise a ValueError
        with pytest.raises(ValueError, match="Entity '.*' not found and is required for formula evaluation"):
            evaluator._build_evaluation_context(dependencies)

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
        unavailable_config = FormulaConfig(id="unavailable_test", name="Unavailable Test", formula="sensor.unavailable_entity + 10")

        result = evaluator.evaluate_formula(unavailable_config)
        assert result["success"] is True
        assert result.get("state") == "unknown"
        assert "sensor.unavailable_entity" in result.get("unavailable_dependencies", [])

        # Test formula with unknown entity
        unknown_config = FormulaConfig(id="unknown_test", name="Unknown Test", formula="sensor.unknown_entity + 20")

        result = evaluator.evaluate_formula(unknown_config)
        assert result["success"] is True
        assert result.get("state") == "unknown"
        assert "sensor.unknown_entity" in result.get("unavailable_dependencies", [])

        # Test formula mixing valid and unavailable entities
        mixed_config = FormulaConfig(id="mixed_unavailable_test", name="Mixed Unavailable Test", formula="valid_entity + unavailable_entity", variables={"valid_entity": "sensor.valid_entity", "unavailable_entity": "sensor.unavailable_entity"})

        result = evaluator.evaluate_formula(mixed_config)
        assert result["success"] is True
        assert result.get("state") == "unknown"
        assert "sensor.unavailable_entity" in result.get("unavailable_dependencies", [])
        # Should not include the valid entity in unavailable dependencies
        assert "sensor.valid_entity" not in result.get("unavailable_dependencies", [])

        # Test formula with both unknown and unavailable entities
        both_config = FormulaConfig(id="both_unavailable_test", name="Both Unavailable Test", formula="unavailable_entity + unknown_entity", variables={"unavailable_entity": "sensor.unavailable_entity", "unknown_entity": "sensor.unknown_entity"})

        result = evaluator.evaluate_formula(both_config)
        assert result["success"] is True
        assert result.get("state") == "unknown"
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
        startup_config = FormulaConfig(id="comprehensive_startup_test", name="Comprehensive Startup Test", formula="none_val + unavailable_val + unknown_val + ready_val", variables={"none_val": "sensor.none_state", "unavailable_val": "sensor.unavailable_state", "unknown_val": "sensor.unknown_state", "ready_val": "sensor.ready_entity"})

        result = evaluator.evaluate_formula(startup_config)
        assert result["success"] is True
        assert result.get("state") == "unknown"

        # All problematic entities should be in unavailable_dependencies
        unavailable_deps = result.get("unavailable_dependencies", [])
        assert "sensor.none_state" in unavailable_deps
        assert "sensor.unavailable_state" in unavailable_deps
        assert "sensor.unknown_state" in unavailable_deps
        # Ready entity should not be in unavailable dependencies
        assert "sensor.ready_entity" not in unavailable_deps

        # Test missing entity (should be fatal error)
        missing_config = FormulaConfig(id="missing_startup_test", name="Missing Startup Test", formula="sensor.missing_entity + 10")

        result = evaluator.evaluate_formula(missing_config)
        assert result["success"] is False
        assert result.get("state") == "unavailable"
        assert "sensor.missing_entity" in result.get("missing_dependencies", [])
