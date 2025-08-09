"""Unit tests for FormulaEvaluatorService."""

import pytest
from unittest.mock import Mock

from src.ha_synthetic_sensors.formula_evaluator_service import FormulaEvaluatorService
from src.ha_synthetic_sensors.core_formula_evaluator import CoreFormulaEvaluator
from src.ha_synthetic_sensors.type_definitions import ReferenceValue


class TestFormulaEvaluatorService:
    """Test the FormulaEvaluatorService component."""

    def setup_method(self):
        """Set up test fixtures."""
        # Reset the service state before each test
        FormulaEvaluatorService._core_evaluator = None

    def teardown_method(self):
        """Clean up after each test."""
        # Reset the service state after each test
        FormulaEvaluatorService._core_evaluator = None

    def test_initialize(self):
        """Test service initialization."""
        mock_core_evaluator = Mock(spec=CoreFormulaEvaluator)

        # Test initialization
        FormulaEvaluatorService.initialize(mock_core_evaluator)

        # Verify state
        assert FormulaEvaluatorService._core_evaluator == mock_core_evaluator
        assert FormulaEvaluatorService.is_initialized() is True

    def test_is_initialized_false(self):
        """Test is_initialized returns False when not initialized."""
        assert FormulaEvaluatorService.is_initialized() is False

    def test_is_initialized_true(self):
        """Test is_initialized returns True when initialized."""
        mock_core_evaluator = Mock(spec=CoreFormulaEvaluator)
        FormulaEvaluatorService._core_evaluator = mock_core_evaluator

        assert FormulaEvaluatorService.is_initialized() is True

    def test_evaluate_formula_success(self):
        """Test successful formula evaluation."""
        # Setup
        mock_core_evaluator = Mock(spec=CoreFormulaEvaluator)
        mock_core_evaluator.evaluate_formula.return_value = "test_result"
        FormulaEvaluatorService._core_evaluator = mock_core_evaluator

        context = {"var": ReferenceValue("test", "value")}

        # Execute
        result = FormulaEvaluatorService.evaluate_formula(
            resolved_formula="test_formula", original_formula="test_formula", context=context
        )

        # Verify
        assert result == "test_result"
        mock_core_evaluator.evaluate_formula.assert_called_once_with("test_formula", "test_formula", context)

    def test_evaluate_formula_not_initialized(self):
        """Test formula evaluation when service not initialized."""
        context = {"var": ReferenceValue("test", "value")}

        # Should raise RuntimeError when not initialized
        with pytest.raises(RuntimeError) as exc_info:
            FormulaEvaluatorService.evaluate_formula(
                resolved_formula="test_formula", original_formula="test_formula", context=context
            )

        assert "FormulaEvaluatorService not initialized" in str(exc_info.value)

    def test_evaluate_formula_propagates_exceptions(self):
        """Test that formula evaluation propagates exceptions from core evaluator."""
        # Setup
        mock_core_evaluator = Mock(spec=CoreFormulaEvaluator)
        test_exception = ValueError("core error")
        mock_core_evaluator.evaluate_formula.side_effect = test_exception
        FormulaEvaluatorService._core_evaluator = mock_core_evaluator

        context = {"var": ReferenceValue("test", "value")}

        # Execute and verify exception propagation
        with pytest.raises(ValueError) as exc_info:
            FormulaEvaluatorService.evaluate_formula(
                resolved_formula="test_formula", original_formula="test_formula", context=context
            )

        assert str(exc_info.value) == "core error"

    def test_evaluate_formula_empty_context(self):
        """Test formula evaluation with empty context."""
        # Setup
        mock_core_evaluator = Mock(spec=CoreFormulaEvaluator)
        mock_core_evaluator.evaluate_formula.return_value = 42
        FormulaEvaluatorService._core_evaluator = mock_core_evaluator

        # Execute
        result = FormulaEvaluatorService.evaluate_formula(resolved_formula="1 + 1", original_formula="1 + 1", context={})

        # Verify
        assert result == 42
        mock_core_evaluator.evaluate_formula.assert_called_once_with("1 + 1", "1 + 1", {})

    def test_singleton_behavior(self):
        """Test that the service behaves as a singleton."""
        mock_core_evaluator1 = Mock(spec=CoreFormulaEvaluator)
        mock_core_evaluator2 = Mock(spec=CoreFormulaEvaluator)

        # Initialize with first evaluator
        FormulaEvaluatorService.initialize(mock_core_evaluator1)
        assert FormulaEvaluatorService._core_evaluator == mock_core_evaluator1

        # Re-initialize with second evaluator (should replace)
        FormulaEvaluatorService.initialize(mock_core_evaluator2)
        assert FormulaEvaluatorService._core_evaluator == mock_core_evaluator2
