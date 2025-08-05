"""Unit tests for computed variables error handling and error messages."""

from unittest.mock import Mock
import pytest

from ha_synthetic_sensors.config_models import ComputedVariable, FormulaConfig
from ha_synthetic_sensors.exceptions import MissingDependencyError
from ha_synthetic_sensors.utils_config import resolve_config_variables, _analyze_computed_variable_error
from ha_synthetic_sensors.type_definitions import ContextValue


class TestComputedVariableErrorHandling:
    """Test enhanced error handling for computed variables."""

    def test_missing_dependency_error_analysis(self) -> None:
        """Test error analysis for missing dependencies."""
        eval_context: dict[str, ContextValue] = {"a": 10}  # b is missing
        error = NameError("name 'b' is not defined")

        analysis = _analyze_computed_variable_error("test_var", "a + b", eval_context, error)

        assert analysis["variable_name"] == "test_var"
        assert analysis["formula"] == "a + b"
        assert analysis["error_type"] == "NameError"
        assert analysis["likely_cause"] == "missing_dependencies"  # Since b is in missing_vars
        assert "b" in analysis["missing_variables"]
        assert "a" in analysis["available_variables"]
        assert analysis["context_values"]["a"] == 10
        assert "defined or resolved first" in analysis["suggestion"]

    def test_division_by_zero_error_analysis(self) -> None:
        """Test error analysis for division by zero."""
        eval_context: dict[str, ContextValue] = {"a": 10, "b": 0}
        error = ZeroDivisionError("division by zero")

        analysis = _analyze_computed_variable_error("test_var", "a / b", eval_context, error)

        assert analysis["error_type"] == "ZeroDivisionError"
        assert analysis["likely_cause"] == "division_by_zero"
        assert "division by zero" in analysis["suggestion"]
        assert "conditional checks" in analysis["suggestion"]

    def test_type_mismatch_error_analysis(self) -> None:
        """Test error analysis for type mismatches."""
        eval_context: dict[str, ContextValue] = {"a": "string", "b": 10}
        error = TypeError("unsupported operand type(s) for +: 'str' and 'int'")

        analysis = _analyze_computed_variable_error("test_var", "a + b", eval_context, error)

        assert analysis["error_type"] == "TypeError"
        assert analysis["likely_cause"] == "type_mismatch"
        assert "numeric values" in analysis["suggestion"]

    def test_circular_dependency_error_message(self) -> None:
        """Test detailed error message for circular dependencies."""
        cv1 = ComputedVariable(formula="var2 + 1")
        cv2 = ComputedVariable(formula="var1 + 1")

        config = FormulaConfig(id="test", formula="var1", variables={"var1": cv1, "var2": cv2})

        eval_context: dict[str, ContextValue] = {}

        def mock_resolver(var_name, var_value, context, sensor_config):
            if isinstance(var_value, (int, float)):
                return var_value
            return None

        with pytest.raises(MissingDependencyError) as exc_info:
            resolve_config_variables(eval_context, config, mock_resolver)

        error_message = str(exc_info.value)
        # Should contain information about the circular dependency
        assert "var1" in error_message and "var2" in error_message
        assert any(keyword in error_message.lower() for keyword in ["circular", "dependency", "iterations"])

    def test_missing_variable_reference_error_message(self) -> None:
        """Test detailed error message for missing variable references."""
        cv = ComputedVariable(formula="undefined_var + 10")

        config = FormulaConfig(id="test", formula="result", variables={"result": cv})

        eval_context: dict[str, ContextValue] = {}

        def mock_resolver(var_name, var_value, context, sensor_config):
            return None  # Always return None to simulate missing dependency

        with pytest.raises(MissingDependencyError) as exc_info:
            resolve_config_variables(eval_context, config, mock_resolver)

        error_message = str(exc_info.value)
        # Should provide helpful suggestions about missing dependencies
        assert "result" in error_message
        assert any(keyword in error_message.lower() for keyword in ["missing", "dependency", "resolve"])
        assert any(hint in error_message for hint in ["typos", "defined", "variables"])

    def test_syntax_error_analysis(self) -> None:
        """Test error analysis for syntax errors in formulas."""
        eval_context: dict[str, ContextValue] = {"a": 10}
        error = SyntaxError("invalid syntax")

        analysis = _analyze_computed_variable_error("test_var", "a + +", eval_context, error)

        assert analysis["error_type"] == "SyntaxError"
        assert analysis["likely_cause"] == "syntax_error"
        assert "syntax" in analysis["suggestion"]

    def test_complex_formula_error_with_context(self) -> None:
        """Test error analysis with complex formula showing context values."""
        eval_context: dict[str, ContextValue] = {"base_power": 1000, "efficiency": 0.9, "load_factor": 1.2}
        error = NameError("name 'missing_var' is not defined")

        analysis = _analyze_computed_variable_error(
            "total_power", "base_power * efficiency * load_factor * missing_var", eval_context, error
        )

        assert analysis["variable_name"] == "total_power"
        assert "missing_var" in analysis["missing_variables"]
        assert len(analysis["available_variables"]) == 3
        assert analysis["context_values"]["base_power"] == 1000
        assert analysis["context_values"]["efficiency"] == 0.9
        assert analysis["context_values"]["load_factor"] == 1.2

    def test_successful_error_recovery_after_dependency_resolution(self) -> None:
        """Test that errors are cleared when dependencies become available."""
        cv1 = ComputedVariable(formula="a + b")
        cv2 = ComputedVariable(formula="intermediate * 2")

        config = FormulaConfig(
            id="test",
            formula="final",
            variables={
                "a": 10,
                "b": 5,
                "intermediate": cv1,  # Will resolve first
                "final": cv2,  # Will resolve after intermediate
            },
        )

        eval_context: dict[str, ContextValue] = {}

        def mock_resolver(var_name, var_value, context, sensor_config):
            if isinstance(var_value, (int, float)):
                return var_value
            return None

        # Should not raise an error - dependencies should resolve in order
        resolve_config_variables(eval_context, config, mock_resolver)

        # With ReferenceValue architecture, check the .value property
        assert eval_context["a"].value == 10
        assert eval_context["b"].value == 5
        assert eval_context["intermediate"].value == 15.0
        assert eval_context["final"].value == 30.0

    def test_multiple_error_aggregation(self) -> None:
        """Test that multiple computed variable errors are properly aggregated."""
        cv1 = ComputedVariable(formula="undefined1 + 1")
        cv2 = ComputedVariable(formula="undefined2 / 0")
        cv3 = ComputedVariable(formula="valid_var * 2")

        config = FormulaConfig(
            id="test", formula="result", variables={"valid_var": 100, "error1": cv1, "error2": cv2, "success": cv3}
        )

        eval_context: dict[str, ContextValue] = {}

        def mock_resolver(var_name, var_value, context, sensor_config):
            if isinstance(var_value, (int, float)):
                return var_value
            return None

        with pytest.raises(MissingDependencyError) as exc_info:
            resolve_config_variables(eval_context, config, mock_resolver)

        error_message = str(exc_info.value)
        # Should mention the specific missing variable
        assert "undefined1" in error_message
        # Should mention missing dependencies
        assert any(keyword in error_message.lower() for keyword in ["missing", "dependency", "cannot be resolved"])
