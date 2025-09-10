"""Enhanced integration tests for CoreFormulaEvaluator.

These tests focus on the core evaluation engine functionality including:
- Alternate state detection and handling
- allow_unresolved_states behavior
- Complex formula evaluation scenarios
- Error handling and edge cases
- Integration with metadata handlers
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from ha_synthetic_sensors.core_formula_evaluator import (
    CoreFormulaEvaluator,
    MissingStateError,
    AlternateStateDetectedError,
)
from ha_synthetic_sensors.exceptions import AlternateStateDetected, MissingDependencyError
from ha_synthetic_sensors.type_definitions import ReferenceValue
from ha_synthetic_sensors.constants_alternate import STATE_NONE


class TestCoreFormulaEvaluatorEnhanced:
    """Enhanced integration tests for CoreFormulaEvaluator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler_factory = Mock()
        self.enhanced_helper = Mock()
        self.evaluator = CoreFormulaEvaluator(handler_factory=self.handler_factory, enhanced_helper=self.enhanced_helper)

    def test_allow_unresolved_states_setting(self):
        """Test the allow_unresolved_states configuration."""
        # Default should be False
        assert self.evaluator._allow_unresolved_states is False

        # Test setting to True
        self.evaluator.set_allow_unresolved_states(True)
        assert self.evaluator._allow_unresolved_states is True

        # Test setting back to False
        self.evaluator.set_allow_unresolved_states(False)
        assert self.evaluator._allow_unresolved_states is False

    def test_evaluate_formula_with_alternate_states_early_detection(self):
        """Test formula evaluation with early alternate state detection (default behavior)."""
        # Set up context with alternate state values
        context = {
            "unavailable_var": ReferenceValue("sensor.missing", STATE_UNAVAILABLE),
            "unknown_var": ReferenceValue("sensor.unknown", STATE_UNKNOWN),
            "none_var": ReferenceValue("sensor.none", None),
            "valid_var": ReferenceValue("sensor.valid", 42),
        }

        # Test that alternate states are detected early and raise AlternateStateDetected
        with pytest.raises(AlternateStateDetected) as exc_info:
            self.evaluator.evaluate_formula(
                resolved_formula="unavailable_var + 10", original_formula="unavailable_var + 10", handler_context=context
            )

        assert "unavailable" in str(exc_info.value).lower()
        assert exc_info.value.alternate_state_value == STATE_UNAVAILABLE

    def test_evaluate_formula_with_alternate_states_allow_unresolved(self):
        """Test formula evaluation with allow_unresolved_states=True."""
        # Enable allow_unresolved_states
        self.evaluator.set_allow_unresolved_states(True)

        # Set up context with alternate state values
        context = {
            "unavailable_var": ReferenceValue("sensor.missing", STATE_UNAVAILABLE),
            "valid_var": ReferenceValue("sensor.valid", 42),
        }

        # Mock enhanced helper to handle the evaluation
        self.enhanced_helper.try_enhanced_eval.return_value = (False, ValueError("Cannot evaluate unavailable"))

        # Should proceed to evaluation and fail there, not in early detection
        with pytest.raises(AlternateStateDetected) as exc_info:
            self.evaluator.evaluate_formula(
                resolved_formula="unavailable_var + 10", original_formula="unavailable_var + 10", handler_context=context
            )

        # Should fail during evaluation, not early detection
        assert "Cannot evaluate unavailable" in str(exc_info.value)

    def test_evaluate_formula_missing_dependency_error(self):
        """Test formula evaluation with missing dependencies (None reference)."""
        # Set up context with missing dependency - the actual implementation
        # converts None reference to AlternateStateDetected, not MissingDependencyError
        context = {
            "missing_var": ReferenceValue(None, "some_value"),  # None reference = missing dependency
            "valid_var": ReferenceValue("sensor.valid", 42),
        }

        # Should raise AlternateStateDetected (wrapped MissingDependencyError) for None references
        with pytest.raises(AlternateStateDetected) as exc_info:
            self.evaluator.evaluate_formula(
                resolved_formula="missing_var + 10", original_formula="missing_var + 10", handler_context=context
            )

        assert "Missing dependency for variable 'missing_var'" in str(exc_info.value)
        assert exc_info.value.alternate_state_value == STATE_NONE

    def test_evaluate_formula_successful_evaluation(self):
        """Test successful formula evaluation with various data types."""
        # Set up context with valid values
        context = {
            "int_var": ReferenceValue("sensor.int", 42),
            "float_var": ReferenceValue("sensor.float", 3.14),
            "string_var": ReferenceValue("sensor.string", "hello"),
            "bool_var": ReferenceValue("sensor.bool", True),
        }

        # Mock successful evaluation
        self.enhanced_helper.try_enhanced_eval.return_value = (True, 45.14)

        result = self.evaluator.evaluate_formula(
            resolved_formula="int_var + float_var", original_formula="int_var + float_var", handler_context=context
        )

        assert result == 45.14

        # Verify enhanced helper was called with processed context
        call_args = self.enhanced_helper.try_enhanced_eval.call_args
        assert call_args[0][0] == "int_var + float_var"  # Formula
        enhanced_context = call_args[0][1]  # Context
        assert enhanced_context["int_var"] == 42
        assert enhanced_context["float_var"] == 3.14

    def test_evaluate_formula_with_metadata_functions(self):
        """Test formula evaluation with metadata function processing."""
        # Set up metadata handler mock
        mock_metadata_handler = Mock()
        mock_metadata_handler.can_handle.return_value = True
        mock_metadata_handler.evaluate.return_value = (
            "processed_formula + _metadata_0",
            {"_metadata_0": "2024-01-01T00:00:00Z"},
        )
        self.handler_factory.get_handler.return_value = mock_metadata_handler

        # Mock enhanced evaluation of processed formula
        self.enhanced_helper.try_enhanced_eval.return_value = (True, "result_with_metadata")

        # Create proper hierarchical context as required by architecture
        from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalEvaluationContext, HierarchicalContextDict

        hierarchical_context = HierarchicalEvaluationContext("test")
        hierarchical_context.set("sensor_var", ReferenceValue("sensor.test", "test_value"))
        context = HierarchicalContextDict(hierarchical_context)

        result = self.evaluator.evaluate_formula(
            resolved_formula="metadata(sensor_var, 'last_changed')",
            original_formula="metadata(sensor_var, 'last_changed')",
            handler_context=context,
        )

        assert result == "result_with_metadata"

        # Verify metadata handler was called
        self.handler_factory.get_handler.assert_called_with("metadata")
        mock_metadata_handler.can_handle.assert_called_once()
        mock_metadata_handler.evaluate.assert_called_once()

    def test_evaluate_formula_result_type_conversion(self):
        """Test formula evaluation with various result type conversions."""
        context = {"var": ReferenceValue("sensor.test", 42)}

        test_cases = [
            # (enhanced_eval_result, expected_final_result)
            (42, 42),  # int
            (3.14, 3.14),  # float
            ("hello", "hello"),  # string
            (True, True),  # bool
            (False, False),  # bool
        ]

        for enhanced_result, expected_result in test_cases:
            self.enhanced_helper.try_enhanced_eval.return_value = (True, enhanced_result)

            result = self.evaluator.evaluate_formula(resolved_formula="var", original_formula="var", handler_context=context)

            assert result == expected_result
            assert type(result) == type(expected_result)

    def test_evaluate_formula_timedelta_conversion(self):
        """Test formula evaluation with timedelta result conversion."""
        context = {"var": ReferenceValue("sensor.test", 42)}

        # Mock timedelta result
        mock_timedelta = timedelta(hours=2, minutes=30)  # 2.5 hours = 9000 seconds
        self.enhanced_helper.try_enhanced_eval.return_value = (True, mock_timedelta)

        result = self.evaluator.evaluate_formula(resolved_formula="var", original_formula="var", handler_context=context)

        assert result == 9000.0  # 2.5 hours in seconds
        assert isinstance(result, float)

    def test_evaluate_formula_datetime_conversion(self):
        """Test formula evaluation with datetime result conversion."""
        context = {"var": ReferenceValue("sensor.test", 42)}

        # Mock datetime result
        mock_datetime = datetime(2024, 1, 1, 12, 0, 0)
        self.enhanced_helper.try_enhanced_eval.return_value = (True, mock_datetime)

        result = self.evaluator.evaluate_formula(resolved_formula="var", original_formula="var", handler_context=context)

        assert result == "2024-01-01T12:00:00"
        assert isinstance(result, str)

    def test_evaluate_formula_complex_object_conversion(self):
        """Test formula evaluation with complex object result conversion."""
        context = {"var": ReferenceValue("sensor.test", 42)}

        # Mock complex object result
        class CustomObject:
            def __str__(self):
                return "custom_object_string"

        mock_object = CustomObject()
        self.enhanced_helper.try_enhanced_eval.return_value = (True, mock_object)

        result = self.evaluator.evaluate_formula(resolved_formula="var", original_formula="var", handler_context=context)

        assert result == "custom_object_string"
        assert isinstance(result, str)

    def test_evaluate_formula_result_alternate_state_detection(self):
        """Test detection of alternate states in formula results."""
        context = {"var": ReferenceValue("sensor.test", 42)}

        test_cases = [
            (STATE_UNAVAILABLE, STATE_UNAVAILABLE),
            (STATE_UNKNOWN, STATE_UNKNOWN),
            ("unavailable", STATE_UNAVAILABLE),
            ("unknown", STATE_UNKNOWN),
        ]

        for result_value, expected_alternate_state in test_cases:
            self.enhanced_helper.try_enhanced_eval.return_value = (True, result_value)

            with pytest.raises(AlternateStateDetected) as exc_info:
                self.evaluator.evaluate_formula(resolved_formula="var", original_formula="var", handler_context=context)

            assert exc_info.value.alternate_state_value == expected_alternate_state

    def test_evaluate_formula_enhanced_eval_exception_handling(self):
        """Test handling of exceptions from enhanced evaluation."""
        context = {"var": ReferenceValue("sensor.test", 42)}

        # Test with exception in enhanced eval result
        test_exception = ValueError("Division by zero")
        self.enhanced_helper.try_enhanced_eval.return_value = (False, test_exception)

        with pytest.raises(AlternateStateDetected) as exc_info:
            self.evaluator.evaluate_formula(resolved_formula="var / 0", original_formula="var / 0", handler_context=context)

        assert "Division by zero" in str(exc_info.value)
        assert exc_info.value.alternate_state_value == STATE_NONE

    def test_evaluate_formula_general_exception_handling(self):
        """Test handling of general exceptions during evaluation."""
        context = {"var": ReferenceValue("sensor.test", 42)}

        # Mock enhanced helper to raise exception
        self.enhanced_helper.try_enhanced_eval.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(AlternateStateDetected) as exc_info:
            self.evaluator.evaluate_formula(resolved_formula="var", original_formula="var", handler_context=context)

        assert "Formula evaluation failed: Unexpected error" in str(exc_info.value)
        assert exc_info.value.alternate_state_value == STATE_NONE

    def test_extract_values_for_enhanced_evaluation(self):
        """Test the _extract_values_for_enhanced_evaluation method."""
        # Set up context with various value types
        context = {
            "ref_value": ReferenceValue("sensor.test", 42),
            "string_ref": ReferenceValue("sensor.string", "hello"),
            "bool_ref": ReferenceValue("sensor.bool", True),
            "none_ref": ReferenceValue("sensor.none", None),
            "direct_value": 100,  # Non-ReferenceValue
            "function": lambda x: x * 2,  # Callable
        }

        # Mock EvaluatorHelpers.process_evaluation_result
        with patch("ha_synthetic_sensors.core_formula_evaluator.EvaluatorHelpers") as mock_helpers:
            mock_helpers.process_evaluation_result.side_effect = lambda x: x  # Return as-is

            enhanced_context = self.evaluator._extract_values_for_enhanced_evaluation(
                context, "ref_value + string_ref + bool_ref"
            )

        # Verify ReferenceValue objects were processed (only referenced variables are extracted)
        assert enhanced_context["ref_value"] == 42
        assert enhanced_context["string_ref"] == "hello"
        assert enhanced_context["bool_ref"] is True
        # none_ref is not referenced in the formula, so it's not extracted

        # Verify non-ReferenceValue objects were preserved (only referenced variables are extracted)
        # direct_value and function are not referenced in the formula, so they're not extracted

    def test_extract_values_unreferenced_variables_not_checked(self):
        """Test that unreferenced variables are not checked for alternate states."""
        # Set up context where some variables have alternate states but aren't referenced
        context = {
            "used_var": ReferenceValue("sensor.used", 42),
            "unused_unavailable": ReferenceValue("sensor.unused", STATE_UNAVAILABLE),
            "unused_unknown": ReferenceValue("sensor.unused2", STATE_UNKNOWN),
        }

        # Mock EvaluatorHelpers.process_evaluation_result
        with patch("ha_synthetic_sensors.core_formula_evaluator.EvaluatorHelpers") as mock_helpers:
            mock_helpers.process_evaluation_result.side_effect = lambda x: x

            # Should not raise AlternateStateDetected because unused variables aren't checked
            enhanced_context = self.evaluator._extract_values_for_enhanced_evaluation(
                context,
                "used_var + 10",  # Only references used_var
            )

        assert enhanced_context["used_var"] == 42
        # unused_unavailable and unused_unknown are not referenced in the formula, so they're not extracted
        assert "unused_unavailable" not in enhanced_context
        assert "unused_unknown" not in enhanced_context

    def test_extract_values_referenced_alternate_states_detected(self):
        """Test that referenced variables with alternate states are detected."""
        context = {
            "good_var": ReferenceValue("sensor.good", 42),
            "bad_var": ReferenceValue("sensor.bad", STATE_UNAVAILABLE),
        }

        # Should raise AlternateStateDetected for referenced alternate state
        with pytest.raises(AlternateStateDetected) as exc_info:
            self.evaluator._extract_values_for_enhanced_evaluation(
                context,
                "good_var + bad_var",  # References both variables
            )

        assert "bad_var" in str(exc_info.value)
        assert exc_info.value.alternate_state_value == STATE_UNAVAILABLE

    def test_get_alternate_state_identification(self):
        """Test the _get_alternate_state method."""
        test_cases = [
            # (input_value, expected_alternate_state)
            (STATE_UNAVAILABLE, STATE_UNAVAILABLE),
            (STATE_UNKNOWN, STATE_UNKNOWN),
            (None, STATE_NONE),
            ("unavailable", STATE_UNAVAILABLE),
            ("unknown", STATE_UNKNOWN),
            (42, False),  # Not an alternate state
            ("normal_string", False),  # Not an alternate state
            (True, False),  # Not an alternate state
        ]

        for input_value, expected_result in test_cases:
            result = self.evaluator._get_alternate_state(input_value)
            assert result == expected_result

    def test_evaluate_formula_empty_context(self):
        """Test formula evaluation with empty context."""
        self.enhanced_helper.try_enhanced_eval.return_value = (True, 42)

        result = self.evaluator.evaluate_formula(resolved_formula="21 + 21", original_formula="21 + 21", handler_context={})

        assert result == 42

        # Verify enhanced helper was called with empty context
        call_args = self.enhanced_helper.try_enhanced_eval.call_args
        assert call_args[0][1] == {}  # Empty enhanced context

    def test_evaluate_formula_metadata_handler_not_found(self):
        """Test formula evaluation when metadata handler is not available."""
        # Set up handler factory to return None (no metadata handler)
        self.handler_factory.get_handler.return_value = None

        # Mock enhanced evaluation
        self.enhanced_helper.try_enhanced_eval.return_value = (True, "result")

        context = {"var": ReferenceValue("sensor.test", 42)}

        result = self.evaluator.evaluate_formula(
            resolved_formula="metadata(var, 'attr')", original_formula="metadata(var, 'attr')", handler_context=context
        )

        assert result == "result"

        # Verify handler factory was called but no handler processing occurred
        self.handler_factory.get_handler.assert_called_with("metadata")

    def test_evaluate_formula_metadata_handler_cannot_handle(self):
        """Test formula evaluation when metadata handler cannot handle the formula."""
        # Set up metadata handler that cannot handle the formula
        mock_metadata_handler = Mock()
        mock_metadata_handler.can_handle.return_value = False
        self.handler_factory.get_handler.return_value = mock_metadata_handler

        # Mock enhanced evaluation
        self.enhanced_helper.try_enhanced_eval.return_value = (True, "result")

        context = {"var": ReferenceValue("sensor.test", 42)}

        result = self.evaluator.evaluate_formula(
            resolved_formula="metadata(var, 'attr')", original_formula="metadata(var, 'attr')", handler_context=context
        )

        assert result == "result"

        # Verify handler was checked but not used
        mock_metadata_handler.can_handle.assert_called_once()
        mock_metadata_handler.evaluate.assert_not_called()

    def test_evaluate_formula_complex_integration_scenario(self):
        """Test a complex integration scenario with multiple features."""
        # Set up complex context using proper hierarchical context as required by architecture
        from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalEvaluationContext, HierarchicalContextDict

        hierarchical_context = HierarchicalEvaluationContext("test")
        hierarchical_context.set("sensor_a", ReferenceValue("sensor.power_a", 100.5))
        hierarchical_context.set("sensor_b", ReferenceValue("sensor.power_b", 200.3))
        hierarchical_context.set("multiplier", ReferenceValue("input_number.multiplier", 1.2))
        hierarchical_context.set("threshold", ReferenceValue("input_number.threshold", 300))
        context = HierarchicalContextDict(hierarchical_context)

        # Set up metadata handler for complex formula
        mock_metadata_handler = Mock()
        mock_metadata_handler.can_handle.return_value = True
        mock_metadata_handler.evaluate.return_value = (
            "(sensor_a + sensor_b) * multiplier > threshold and _metadata_0 > _metadata_1",
            {"_metadata_0": "2024-01-01T12:00:00Z", "_metadata_1": "2024-01-01T10:00:00Z"},
        )
        self.handler_factory.get_handler.return_value = mock_metadata_handler

        # Mock enhanced evaluation of complex formula
        self.enhanced_helper.try_enhanced_eval.return_value = (True, True)

        result = self.evaluator.evaluate_formula(
            resolved_formula="(sensor_a + sensor_b) * multiplier > threshold and metadata(sensor_a, 'last_changed') > metadata(sensor_b, 'last_changed')",
            original_formula="(sensor_a + sensor_b) * multiplier > threshold and metadata(sensor_a, 'last_changed') > metadata(sensor_b, 'last_changed')",
            handler_context=context,
        )

        assert result is True

        # Verify all components were called correctly
        self.handler_factory.get_handler.assert_called_with("metadata")
        mock_metadata_handler.can_handle.assert_called_once()
        mock_metadata_handler.evaluate.assert_called_once()

        # Verify enhanced evaluation received the processed formula and extended context
        call_args = self.enhanced_helper.try_enhanced_eval.call_args
        processed_formula = call_args[0][0]
        enhanced_context = call_args[0][1]

        assert "_metadata_0" in enhanced_context
        assert "_metadata_1" in enhanced_context
        assert enhanced_context["sensor_a"] == 100.5
        assert enhanced_context["sensor_b"] == 200.3
