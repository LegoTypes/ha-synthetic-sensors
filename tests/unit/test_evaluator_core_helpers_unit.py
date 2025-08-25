"""Unit tests for evaluator_core_helpers module."""

import pytest
from unittest.mock import MagicMock, patch

from ha_synthetic_sensors.evaluator_core_helpers import (
    process_early_result,
    should_use_dependency_management,
    evaluate_formula_normally,
    evaluate_with_dependency_management,
)
from ha_synthetic_sensors.evaluator_results import EvaluatorResults
from ha_synthetic_sensors.config_models import SensorConfig, FormulaConfig


class TestEvaluatorCoreHelpers:
    """Test cases for evaluator_core_helpers module."""

    def test_process_early_result(self) -> None:
        """Test process_early_result function."""
        mock_evaluator = MagicMock()
        mock_resolution_result = MagicMock()
        mock_config = MagicMock()
        mock_sensor_config = MagicMock()
        eval_context = {"test": "value"}

        with patch("ha_synthetic_sensors.evaluator_core_helpers.process_alternate_state_result") as mock_process:
            mock_result = EvaluatorResults.create_success_from_result(100.0)
            mock_process.return_value = mock_result

            result = process_early_result(
                evaluator=mock_evaluator,
                resolution_result=mock_resolution_result,
                config=mock_config,
                eval_context=eval_context,
                sensor_config=mock_sensor_config,
            )

            assert result is mock_result
            mock_process.assert_called_once()

    def test_should_use_dependency_management_true(self) -> None:
        """Test should_use_dependency_management when conditions are met."""
        mock_evaluator = MagicMock()
        mock_evaluator.needs_dependency_resolution.return_value = True
        mock_sensor_config = MagicMock()
        mock_context = MagicMock()
        mock_config = MagicMock()

        with patch("ha_synthetic_sensors.evaluator_core_helpers.check_dependency_management_conditions") as mock_check:
            mock_check.return_value = True

            result = should_use_dependency_management(
                evaluator=mock_evaluator,
                sensor_config=mock_sensor_config,
                context=mock_context,
                bypass_dependency_management=False,
                config=mock_config,
            )

            assert result is True
            mock_evaluator.needs_dependency_resolution.assert_called_once_with(mock_config, mock_sensor_config)

    def test_should_use_dependency_management_false_conditions(self) -> None:
        """Test should_use_dependency_management when conditions are not met."""
        mock_evaluator = MagicMock()
        mock_sensor_config = MagicMock()
        mock_context = MagicMock()
        mock_config = MagicMock()

        with patch("ha_synthetic_sensors.evaluator_core_helpers.check_dependency_management_conditions") as mock_check:
            mock_check.return_value = False

            result = should_use_dependency_management(
                evaluator=mock_evaluator,
                sensor_config=mock_sensor_config,
                context=mock_context,
                bypass_dependency_management=False,
                config=mock_config,
            )

            assert result is False
            mock_evaluator.needs_dependency_resolution.assert_not_called()

    def test_evaluate_formula_normally(self) -> None:
        """Test evaluate_formula_normally function."""
        mock_evaluator = MagicMock()
        mock_evaluator.execute_formula_evaluation.return_value = 150.0
        mock_config = MagicMock()
        mock_config.id = "test_formula"
        mock_sensor_config = MagicMock()
        eval_context = {"test": "value"}
        context = {"context": "data"}
        formula_name = "test_formula"

        result = evaluate_formula_normally(
            evaluator=mock_evaluator,
            config=mock_config,
            eval_context=eval_context,
            context=context,
            sensor_config=mock_sensor_config,
            formula_name=formula_name,
        )

        # The function should return a dict with success and value
        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["value"] == 150.0
        mock_evaluator.execute_formula_evaluation.assert_called_once()
        mock_evaluator.error_handler.handle_successful_evaluation.assert_called_once_with(formula_name)
        mock_evaluator.cache_handler.cache_result.assert_called_once()

    def test_evaluate_formula_normally_string_result(self) -> None:
        """Test evaluate_formula_normally with string result (no caching)."""
        mock_evaluator = MagicMock()
        mock_evaluator.execute_formula_evaluation.return_value = "test_result"
        mock_config = MagicMock()
        mock_config.id = "test_formula"
        mock_sensor_config = MagicMock()
        eval_context = {"test": "value"}
        context = {"context": "data"}
        formula_name = "test_formula"

        result = evaluate_formula_normally(
            evaluator=mock_evaluator,
            config=mock_config,
            eval_context=eval_context,
            context=context,
            sensor_config=mock_sensor_config,
            formula_name=formula_name,
        )

        # The function should return a dict with success and value
        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["value"] == "test_result"
        mock_evaluator.cache_handler.cache_result.assert_not_called()

    def test_evaluate_with_dependency_management_success(self) -> None:
        """Test evaluate_with_dependency_management with successful evaluation."""
        mock_evaluator = MagicMock()
        mock_evaluator.generic_dependency_manager.build_evaluation_context.return_value = {"complete": "context"}
        mock_evaluator.perform_pre_evaluation_checks.return_value = (None, {"eval": "context"})
        mock_evaluator.execute_formula_evaluation.return_value = 200.0
        mock_config = MagicMock()
        mock_config.name = "test_formula"
        mock_sensor_config = MagicMock()
        context = {"base": "context"}

        result = evaluate_with_dependency_management(
            evaluator=mock_evaluator, config=mock_config, context=context, sensor_config=mock_sensor_config
        )

        # The function should return a dict with success and value
        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["value"] == 200.0
        mock_evaluator.generic_dependency_manager.build_evaluation_context.assert_called_once()
        mock_evaluator.perform_pre_evaluation_checks.assert_called_once()
        mock_evaluator.execute_formula_evaluation.assert_called_once()
        mock_evaluator.error_handler.handle_successful_evaluation.assert_called_once_with("test_formula")

    def test_evaluate_with_dependency_management_pre_eval_check_result(self) -> None:
        """Test evaluate_with_dependency_management when pre-evaluation check returns a result."""
        mock_evaluator = MagicMock()
        mock_evaluator.generic_dependency_manager.build_evaluation_context.return_value = {"complete": "context"}
        check_result = EvaluatorResults.create_error_result("test error", state="unknown")
        mock_evaluator.perform_pre_evaluation_checks.return_value = (check_result, None)
        mock_config = MagicMock()
        mock_sensor_config = MagicMock()
        context = {"base": "context"}

        result = evaluate_with_dependency_management(
            evaluator=mock_evaluator, config=mock_config, context=context, sensor_config=mock_sensor_config
        )

        # Should return the check result directly
        assert result is check_result
        mock_evaluator.execute_formula_evaluation.assert_not_called()

    def test_evaluate_with_dependency_management_no_eval_context(self) -> None:
        """Test evaluate_with_dependency_management when eval_context is None."""
        mock_evaluator = MagicMock()
        mock_evaluator.generic_dependency_manager.build_evaluation_context.return_value = {"complete": "context"}
        mock_evaluator.perform_pre_evaluation_checks.return_value = (None, None)
        mock_config = MagicMock()
        mock_sensor_config = MagicMock()
        context = {"base": "context"}

        result = evaluate_with_dependency_management(
            evaluator=mock_evaluator, config=mock_config, context=context, sensor_config=mock_sensor_config
        )

        # The function should return a dict with success and value
        assert isinstance(result, dict)
        assert result["success"] is False
        # Check if error_message exists and contains the expected text
        if "error_message" in result:
            assert "Failed to build evaluation context" in result["error_message"]
        elif "error" in result:
            assert "Failed to build evaluation context" in result["error"]
        else:
            # Print the actual result structure for debugging
            print(f"Result structure: {result}")
            assert False, "Expected error message not found in result"
        mock_evaluator.execute_formula_evaluation.assert_not_called()

    def test_evaluate_with_dependency_management_exception(self) -> None:
        """Test evaluate_with_dependency_management when an exception occurs."""
        mock_evaluator = MagicMock()
        # Set up the exception to occur after formula_name is defined
        mock_evaluator.perform_pre_evaluation_checks.side_effect = Exception("test exception")
        # Mock the fallback method to return a proper result
        fallback_result = {"success": False, "error_message": "test exception"}
        mock_evaluator.fallback_to_normal_evaluation.return_value = fallback_result
        mock_config = MagicMock()
        mock_config.name = "test_formula"  # Ensure formula_name is defined
        mock_sensor_config = MagicMock()
        context = {"base": "context"}

        result = evaluate_with_dependency_management(
            evaluator=mock_evaluator, config=mock_config, context=context, sensor_config=mock_sensor_config
        )

        # The function should return the fallback result
        assert result == fallback_result
        mock_evaluator.fallback_to_normal_evaluation.assert_called_once()
