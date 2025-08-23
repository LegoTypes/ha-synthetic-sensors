"""Unit tests for CoreFormulaEvaluator."""

import pytest
from unittest.mock import Mock, MagicMock

from ha_synthetic_sensors.core_formula_evaluator import CoreFormulaEvaluator
from ha_synthetic_sensors.exceptions import FormulaEvaluationError, AlternateStateDetected
from ha_synthetic_sensors.type_definitions import ReferenceValue


class TestCoreFormulaEvaluator:
    """Test the CoreFormulaEvaluator component."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler_factory = Mock()
        self.enhanced_helper = Mock()
        self.evaluator = CoreFormulaEvaluator(handler_factory=self.handler_factory, enhanced_helper=self.enhanced_helper)

    def test_init(self):
        """Test CoreFormulaEvaluator initialization."""
        assert self.evaluator._handler_factory == self.handler_factory
        assert self.evaluator._enhanced_helper == self.enhanced_helper

    def test_evaluate_formula_success(self):
        """Test successful formula evaluation."""
        # Setup mocks - for enhanced simple eval path
        self.enhanced_helper.try_enhanced_eval.return_value = (True, "test_result")

        # EvaluationContext should contain ReferenceValue objects
        context = {"test_var": ReferenceValue("test", "value")}

        # Execute
        result = self.evaluator.evaluate_formula(
            resolved_formula="test_formula", original_formula="test_formula", handler_context=context
        )

        # Verify
        assert result == "test_result"
        self.enhanced_helper.try_enhanced_eval.assert_called_once()

    def test_evaluate_formula_no_handler_fallback_to_enhanced(self):
        """Test formula evaluation falls back to enhanced simple eval when no handler found."""
        # Setup mocks - no handler can handle the formula
        mock_handler = Mock()
        mock_handler.can_handle.return_value = False
        self.handler_factory.get_handler.return_value = mock_handler

        # Enhanced helper should be used as fallback
        self.enhanced_helper.try_enhanced_eval.return_value = (True, 42.0)

        # EvaluationContext should contain ReferenceValue objects
        context = {"test_var": ReferenceValue("test", "value")}

        # Execute
        result = self.evaluator.evaluate_formula(resolved_formula="1 + 1", original_formula="1 + 1", handler_context=context)

        # Verify fallback to enhanced eval
        assert result == 42.0
        self.enhanced_helper.try_enhanced_eval.assert_called_once()

    def test_evaluate_formula_enhanced_eval_failure(self):
        """Test formula evaluation when enhanced eval fails."""
        # Enhanced helper fails
        test_exception = ValueError("test error")
        self.enhanced_helper.try_enhanced_eval.return_value = (False, test_exception)

        # EvaluationContext should contain ReferenceValue objects
        context = {"test_var": ReferenceValue("test", "value")}

        # Execute and verify exception
        with pytest.raises(AlternateStateDetected) as exc_info:
            self.evaluator.evaluate_formula(
                resolved_formula="invalid_formula", original_formula="invalid_formula", handler_context=context
            )

        assert "test error" in str(exc_info.value)

    def test_evaluate_formula_metadata_path(self):
        """Test formula evaluation via metadata handler."""
        # Setup mocks for metadata path
        mock_handler = Mock()
        mock_handler.can_handle.return_value = True
        mock_handler.evaluate.return_value = ("metadata_result(_metadata_0)", {"_metadata_0": "test_value"})
        self.handler_factory.get_handler.return_value = mock_handler

        # Setup enhanced helper mock for continued evaluation after metadata processing
        self.enhanced_helper.try_enhanced_eval.return_value = (True, "test_value")

        # EvaluationContext should contain ReferenceValue objects
        context = {"test_var": ReferenceValue("test", "value")}

        # Execute with metadata formula
        result = self.evaluator.evaluate_formula(
            resolved_formula="metadata(entity, 'attr')", original_formula="metadata(entity, 'attr')", handler_context=context
        )

        # Verify metadata path was used
        assert result == "test_value"
        self.handler_factory.get_handler.assert_called_with("metadata")
        mock_handler.can_handle.assert_called_once()
        mock_handler.evaluate.assert_called_once()

    def test_evaluate_formula_empty_context(self):
        """Test formula evaluation with empty context."""
        # Setup mocks for enhanced simple eval
        self.enhanced_helper.try_enhanced_eval.return_value = (True, 42)

        # Execute with empty context
        result = self.evaluator.evaluate_formula(resolved_formula="1 + 1", original_formula="1 + 1", handler_context={})

        # Verify
        assert result == 42
        self.enhanced_helper.try_enhanced_eval.assert_called_once()
