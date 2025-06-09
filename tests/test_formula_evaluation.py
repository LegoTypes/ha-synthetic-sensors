"""Tests for synthetic sensors formula evaluation and dependency resolution."""

from unittest.mock import MagicMock

import pytest


class TestFormulaEvaluation:
    """Test cases for formula evaluation functionality."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()
        return hass

    def test_enhanced_evaluator_basic_functionality(self, mock_hass):
        """Test basic formula evaluation functionality."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test simple arithmetic
        config = FormulaConfig(id="test", name="test", formula="10 + 20")
        result = evaluator.evaluate_formula(config, {})
        assert result["success"] is True
        assert result["value"] == 30

        # Test with variables
        config = FormulaConfig(id="test_vars", name="test_vars", formula="A + B")
        context = {"A": 100, "B": 50}
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 150

    def test_enhanced_evaluator_with_entity_data(
        self, mock_hass, mock_entities_with_dependencies
    ):
        """Test formula evaluation with real entity data."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Create variables from entity data
        variables = {}
        for entity_id, entity_data in mock_entities_with_dependencies.items():
            # Simple normalization for testing
            normalized_name = entity_id.replace("sensor.", "").replace("_", "")
            variables[normalized_name] = float(entity_data["state"])

        # Test HVAC total calculation
        config = FormulaConfig(
            id="hvac_total",
            name="hvac_total",
            formula="hvacupstairs + hvacdownstairs",
            dependencies={"hvacupstairs", "hvacdownstairs"},
        )
        result = evaluator.evaluate_formula(config, variables)
        assert result["success"] is True
        assert result["value"] == 2000.0  # 1200 + 800

    def test_dependency_resolution(self, mock_hass):
        """Test dependency resolution in enhanced evaluator."""
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test simple formula dependencies
        dependencies = evaluator.get_formula_dependencies("A + B + C")
        assert dependencies == {"A", "B", "C"}

        # Test complex formula dependencies
        dependencies = evaluator.get_formula_dependencies(
            "(HVAC_Upstairs + HVAC_Downstairs) / Total_Power"
        )
        assert dependencies == {"HVAC_Upstairs", "HVAC_Downstairs", "Total_Power"}

    def test_caching_mechanism(self, mock_hass):
        """Test caching mechanism in enhanced evaluator."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        variables = {"A": 10, "B": 20}
        config = FormulaConfig(id="cache_test", name="cache_test", formula="A + B + 5")

        # First evaluation should compute result
        result1 = evaluator.evaluate_formula(config, variables)
        assert result1["success"] is True
        assert result1["value"] == 35

        # Second evaluation with same inputs should use cache
        result2 = evaluator.evaluate_formula(config, variables)
        assert result2["success"] is True
        assert result2["value"] == 35
        # Note: Caching behavior may not be explicitly indicated in result dict

    def test_formula_syntax_validation(self, mock_hass):
        """Test formula syntax validation."""
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test valid formulas
        errors = evaluator.validate_formula_syntax("A + B")
        assert (
            "Formula does not reference any entities" in errors
        )  # This formula doesn't use entity() syntax

        # Test invalid formulas
        errors = evaluator.validate_formula_syntax("A + B + )")
        assert len(errors) > 0
        assert any("syntax" in error.lower() for error in errors)

        # Test balanced parentheses
        errors = evaluator.validate_formula_syntax("((A + B)")
        assert any("parentheses" in error.lower() for error in errors)

    def test_error_handling(self, mock_hass):
        """Test error handling in formula evaluation."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test division by zero
        config = FormulaConfig(
            id="division_test", name="division_test", formula="A / B"
        )
        result = evaluator.evaluate_formula(config, {"A": 10, "B": 0})
        assert result["success"] is False
        assert "error" in result

        # Test missing dependencies
        config = FormulaConfig(id="missing_deps", name="missing_deps", formula="A + B")
        # Only A is present in context, B is missing
        mock_hass.states.get.side_effect = lambda entity_id: (
            None if entity_id == "B" else MagicMock(state=10)
        )
        result = evaluator.evaluate_formula(config, {"A": 10})  # Missing B
        assert result["success"] is False
        assert "Missing dependencies" in result["error"]

    def test_complex_formulas(self, mock_hass):
        """Test complex mathematical formulas."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test mathematical functions
        config = FormulaConfig(
            id="math_test", name="math_test", formula="max(A, B) + min(C, D)"
        )
        variables = {"A": 10, "B": 20, "C": 30, "D": 5}
        result = evaluator.evaluate_formula(config, variables)
        assert result["success"] is True
        assert result["value"] == 25  # max(10, 20) + min(30, 5) = 20 + 5 = 25

        # Test absolute value
        config = FormulaConfig(
            id="abs_test", name="abs_test", formula="abs(A) + abs(B)"
        )
        variables = {"A": -10, "B": 15}
        result = evaluator.evaluate_formula(config, variables)
        assert result["success"] is True
        assert result["value"] == 25  # abs(-10) + abs(15) = 10 + 15 = 25

    def test_cache_management(self, mock_hass):
        """Test cache management functionality."""
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test cache clearing
        evaluator._evaluation_cache["test"] = ("value", None)
        evaluator._dependency_cache["test"] = {"A", "B"}

        evaluator.clear_cache()
        assert len(evaluator._evaluation_cache) == 0
        assert len(evaluator._dependency_cache) == 0

        # Test cache statistics
        stats = evaluator.get_cache_stats()
        assert isinstance(stats, dict)
        assert "total_cached_formulas" in stats
        assert "total_cached_evaluations" in stats
