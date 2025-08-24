"""Unit tests for computed variables functionality."""

import pytest
from unittest.mock import Mock

from ha_synthetic_sensors.config_models import ComputedVariable, FormulaConfig
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.exceptions import MissingDependencyError
from ha_synthetic_sensors.utils_config import resolve_config_variables
from ha_synthetic_sensors.type_definitions import ContextValue


class TestComputedVariable:
    """Test the ComputedVariable dataclass."""

    def test_computed_variable_creation(self):
        """Test creating a ComputedVariable instance."""
        cv = ComputedVariable(formula="a + b", dependencies={"a", "b"})
        assert cv.formula == "a + b"
        assert cv.dependencies == {"a", "b"}

    def test_computed_variable_default_dependencies(self):
        """Test ComputedVariable with default empty dependencies."""
        cv = ComputedVariable(formula="42")
        assert cv.formula == "42"
        assert cv.dependencies == set()

    def test_computed_variable_validation(self):
        """Test ComputedVariable validation."""
        # Empty formula should raise error
        with pytest.raises(ValueError, match="formula cannot be empty"):
            ComputedVariable(formula="")

        # Whitespace-only formula should raise error
        with pytest.raises(ValueError, match="formula cannot be whitespace only"):
            ComputedVariable(formula="   ")

    def test_computed_variable_valid_formulas(self):
        """Test ComputedVariable with various valid formulas."""
        # Simple arithmetic
        cv1 = ComputedVariable(formula="a + b")
        assert cv1.formula == "a + b"

        # Complex expression
        cv2 = ComputedVariable(formula="((now() - state.last_changed) / 60) < 15")
        assert cv2.formula == "((now() - state.last_changed) / 60) < 15"

        # Conditional expressions
        cv3 = ComputedVariable(formula="value1 if condition else value2")
        assert cv3.formula == "value1 if condition else value2"


class TestConfigManagerParsing:
    """Test computed variable parsing in ConfigManager."""

    @pytest.fixture
    def config_manager(self):
        """Create a ConfigManager instance for testing."""
        from pathlib import Path

        return ConfigManager(config_path=Path("/tmp/test.yaml"), hass=None)

    def test_parse_variables_simple_only(self, config_manager):
        """Test parsing variables with only simple variables."""
        variables_data = {"simple_var": "sensor.test", "literal_var": 42, "float_var": 3.14}

        parsed = config_manager._parse_variables(variables_data)

        assert parsed["simple_var"] == "sensor.test"
        assert parsed["literal_var"] == 42
        assert parsed["float_var"] == 3.14

    def test_parse_variables_computed_only(self, config_manager):
        """Test parsing variables with only computed variables."""
        variables_data = {"computed1": {"formula": "a + b"}, "computed2": {"formula": "x * y"}}

        parsed = config_manager._parse_variables(variables_data)

        assert isinstance(parsed["computed1"], ComputedVariable)
        assert parsed["computed1"].formula == "a + b"
        assert isinstance(parsed["computed2"], ComputedVariable)
        assert parsed["computed2"].formula == "x * y"

    def test_parse_variables_mixed(self, config_manager):
        """Test parsing variables with mixed simple and computed variables."""
        variables_data = {
            "simple_var": "sensor.test",
            "literal_var": 42,
            "computed_var": {"formula": "simple_var * literal_var"},
            "another_computed": {"formula": "computed_var + 100"},
        }

        parsed = config_manager._parse_variables(variables_data)

        assert parsed["simple_var"] == "sensor.test"
        assert parsed["literal_var"] == 42
        assert isinstance(parsed["computed_var"], ComputedVariable)
        assert parsed["computed_var"].formula == "simple_var * literal_var"
        assert isinstance(parsed["another_computed"], ComputedVariable)
        assert parsed["another_computed"].formula == "computed_var + 100"

    def test_parse_variables_empty_formula_error(self, config_manager):
        """Test that empty formula expressions raise errors."""
        variables_data = {
            "bad_var": {"formula": ""}  # Empty formula
        }

        with pytest.raises(ValueError, match="empty formula expression"):
            config_manager._parse_variables(variables_data)

    def test_parse_variables_whitespace_formula_error(self, config_manager):
        """Test that whitespace-only formula expressions raise errors."""
        variables_data = {
            "bad_var": {"formula": "   "}  # Whitespace-only formula
        }

        with pytest.raises(ValueError, match="empty formula expression"):
            config_manager._parse_variables(variables_data)


class TestVariableResolution:
    """Test computed variable resolution in utils_config."""

    def create_mock_resolver(self, entity_values: dict[str, any]) -> callable:
        """Create a mock resolver callback for testing."""

        def mock_resolver(var_name: str, var_value: any, context: dict, sensor_config: any) -> any:
            # Handle entity mappings
            if isinstance(var_value, str) and var_value.startswith("sensor."):
                return entity_values.get(var_value, None)
            # Handle literals
            elif isinstance(var_value, (int, float)):
                return var_value
            return None

        return mock_resolver

    def test_resolve_simple_variables_only(self):
        """Test resolving only simple variables."""
        config = FormulaConfig(id="test", formula="a + b", variables={"a": "sensor.a", "b": 42})

        eval_context: dict[str, ContextValue] = {}
        entity_values = {"sensor.a": 10.0}
        resolver = self.create_mock_resolver(entity_values)

        resolve_config_variables(eval_context, config, resolver)

        assert eval_context["a"].value == 10.0
        assert eval_context["b"].value == 42

    def test_resolve_computed_variables_simple(self):
        """Test resolving simple computed variables."""
        from unittest.mock import patch

        computed_var = ComputedVariable(formula="a + b")
        config = FormulaConfig(id="test", formula="result", variables={"a": "sensor.a", "b": 42, "result": computed_var})

        eval_context: dict[str, ContextValue] = {}
        entity_values = {"sensor.a": 10.0}
        resolver = self.create_mock_resolver(entity_values)

        # Mock the pipeline evaluation to return the expected result
        def mock_evaluate_formula_via_pipeline(
            formula, context, variables=None, bypass_dependency_management=False, allow_unresolved_states=False
        ):
            # For formula "a + b", return 52.0 (10.0 + 42)
            if formula == "a + b":
                return {"success": True, "value": 52.0}
            return {"success": False, "error": "Unknown formula"}

        with patch(
            "ha_synthetic_sensors.formula_evaluator_service.FormulaEvaluatorService.evaluate_formula_via_pipeline",
            side_effect=mock_evaluate_formula_via_pipeline,
        ):
            resolve_config_variables(eval_context, config, resolver)

        assert eval_context["a"].value == 10.0
        assert eval_context["b"].value == 42
        assert eval_context["result"].value == 52.0  # 10.0 + 42

    def test_resolve_computed_variables_dependency_chain(self):
        """Test resolving computed variables with dependency chains."""
        from unittest.mock import patch

        cv1 = ComputedVariable(formula="base * multiplier")
        cv2 = ComputedVariable(formula="intermediate + bonus")

        config = FormulaConfig(
            id="test",
            formula="final",
            variables={"base": "sensor.base", "multiplier": 2.0, "bonus": 100, "intermediate": cv1, "final": cv2},
        )

        eval_context: dict[str, ContextValue] = {}
        entity_values = {"sensor.base": 25.0}
        resolver = self.create_mock_resolver(entity_values)

        # Mock the pipeline evaluation to return expected results for dependency chain
        def mock_evaluate_formula_via_pipeline(
            formula, context, variables=None, bypass_dependency_management=False, allow_unresolved_states=False
        ):
            if formula == "base * multiplier":
                return {"success": True, "value": 50.0}  # 25.0 * 2.0
            elif formula == "intermediate + bonus":
                return {"success": True, "value": 150.0}  # 50.0 + 100
            return {"success": False, "error": "Unknown formula"}

        with patch(
            "ha_synthetic_sensors.formula_evaluator_service.FormulaEvaluatorService.evaluate_formula_via_pipeline",
            side_effect=mock_evaluate_formula_via_pipeline,
        ):
            resolve_config_variables(eval_context, config, resolver)

        assert eval_context["base"].value == 25.0
        assert eval_context["multiplier"].value == 2.0
        assert eval_context["bonus"].value == 100
        assert eval_context["intermediate"].value == 50.0  # 25.0 * 2.0
        assert eval_context["final"].value == 150.0  # 50.0 + 100

    def test_resolve_computed_variables_complex_expressions(self):
        """Test resolving computed variables with complex expressions."""
        from unittest.mock import patch

        cv1 = ComputedVariable(formula="input_power * efficiency")
        cv2 = ComputedVariable(formula="output_power * 0.8")  # 80% derate
        cv3 = ComputedVariable(formula="derated_power if derated_power > 1000 else 1000")  # Python ternary

        config = FormulaConfig(
            id="test",
            formula="final_power",
            variables={"input_power": 1500.0, "efficiency": 0.9, "output_power": cv1, "derated_power": cv2, "final_power": cv3},
        )

        eval_context: dict[str, ContextValue] = {}
        resolver = self.create_mock_resolver({})

        # Mock the pipeline evaluation for complex expressions
        def mock_evaluate_formula_via_pipeline(
            formula, context, variables=None, bypass_dependency_management=False, allow_unresolved_states=False
        ):
            if formula == "input_power * efficiency":
                return {"success": True, "value": 1350.0}  # 1500 * 0.9
            elif formula == "output_power * 0.8":
                return {"success": True, "value": 1080.0}  # 1350 * 0.8
            elif formula == "derated_power if derated_power > 1000 else 1000":
                return {"success": True, "value": 1080.0}  # max(1080, 1000)
            return {"success": False, "error": "Unknown formula"}

        with patch(
            "ha_synthetic_sensors.formula_evaluator_service.FormulaEvaluatorService.evaluate_formula_via_pipeline",
            side_effect=mock_evaluate_formula_via_pipeline,
        ):
            resolve_config_variables(eval_context, config, resolver)

        assert eval_context["input_power"].value == 1500.0
        assert eval_context["efficiency"].value == 0.9
        assert eval_context["output_power"].value == 1350.0  # 1500 * 0.9
        assert eval_context["derated_power"].value == 1080.0  # 1350 * 0.8
        assert eval_context["final_power"].value == 1080.0  # max(1080, 1000)

    def test_resolve_computed_variables_missing_dependencies(self):
        """Test handling of missing dependencies in computed variables."""
        # Clear global state that may be affected by previous tests
        from ha_synthetic_sensors.formula_evaluator_service import FormulaEvaluatorService

        FormulaEvaluatorService._core_evaluator = None
        FormulaEvaluatorService._evaluator = None
        cv = ComputedVariable(formula="missing_var + 10")
        config = FormulaConfig(id="test", formula="result", variables={"result": cv})

        eval_context: dict[str, ContextValue] = {}
        resolver = self.create_mock_resolver({})

        with pytest.raises(MissingDependencyError, match="Could not resolve computed variables"):
            resolve_config_variables(eval_context, config, resolver)

    def test_resolve_computed_variables_context_priority(self):
        """Test that existing context values have priority over config variables."""
        from unittest.mock import patch

        cv = ComputedVariable(formula="a + b")
        config = FormulaConfig(id="test", formula="result", variables={"a": "sensor.a", "b": 50, "result": cv})

        # Pre-populate context with some values
        eval_context: dict[str, ContextValue] = {"a": 999.0}  # Override sensor.a
        entity_values = {"sensor.a": 10.0}  # This should be ignored
        resolver = self.create_mock_resolver(entity_values)

        # Mock the pipeline evaluation to use existing context values
        def mock_evaluate_formula_via_pipeline(
            formula, context, variables=None, bypass_dependency_management=False, allow_unresolved_states=False
        ):
            if formula == "a + b":
                return {"success": True, "value": 1049.0}  # 999.0 + 50
            return {"success": False, "error": "Unknown formula"}

        with patch(
            "ha_synthetic_sensors.formula_evaluator_service.FormulaEvaluatorService.evaluate_formula_via_pipeline",
            side_effect=mock_evaluate_formula_via_pipeline,
        ):
            resolve_config_variables(eval_context, config, resolver)

        assert eval_context["a"] == 999.0  # Context value preserved (raw value)
        assert eval_context["b"].value == 50
        assert eval_context["result"].value == 1049.0  # 999.0 + 50

    def test_circular_dependency_detection(self):
        """Test detection of circular dependencies in computed variables."""
        # Clear global state that may be affected by previous tests
        from ha_synthetic_sensors.formula_evaluator_service import FormulaEvaluatorService

        FormulaEvaluatorService._core_evaluator = None
        FormulaEvaluatorService._evaluator = None
        cv1 = ComputedVariable(formula="var2 + 1")
        cv2 = ComputedVariable(formula="var1 + 1")

        config = FormulaConfig(id="test", formula="var1", variables={"var1": cv1, "var2": cv2})

        eval_context: dict[str, ContextValue] = {}
        resolver = self.create_mock_resolver({})

        with pytest.raises(MissingDependencyError, match="Could not resolve computed variables"):
            resolve_config_variables(eval_context, config, resolver)

    def test_max_iterations_protection(self):
        """Test that maximum iterations prevents infinite loops."""
        from unittest.mock import patch

        # Create a complex dependency chain that should resolve in a reasonable number of iterations
        variables = {}
        for i in range(20):  # Create a long chain
            if i == 0:
                variables[f"var{i}"] = 1
            else:
                variables[f"var{i}"] = ComputedVariable(formula=f"var{i - 1} + 1")

        config = FormulaConfig(id="test", formula="var19", variables=variables)

        eval_context: dict[str, ContextValue] = {}
        resolver = self.create_mock_resolver({})

        # Mock the pipeline evaluation to return sequential increments
        def mock_evaluate_formula_via_pipeline(
            formula, context, variables=None, bypass_dependency_management=False, allow_unresolved_states=False
        ):
            # Extract variable number from formula (e.g., "var0 + 1" -> 1+1=2)
            if " + 1" in formula:
                var_name = formula.split(" + 1")[0]
                if var_name.startswith("var") and var_name[3:].isdigit():
                    var_num = int(var_name[3:])
                    return {"success": True, "value": var_num + 2}  # Previous var (var_num) + 1 + 1
            return {"success": False, "error": "Unknown formula"}

        with patch(
            "ha_synthetic_sensors.formula_evaluator_service.FormulaEvaluatorService.evaluate_formula_via_pipeline",
            side_effect=mock_evaluate_formula_via_pipeline,
        ):
            # This should work - it's a valid dependency chain
            resolve_config_variables(eval_context, config, resolver)
            assert eval_context["var19"].value == 20  # 1 + 19 increments

    def test_resolve_with_mathematical_functions(self):
        """Test computed variables with mathematical functions."""
        from unittest.mock import patch

        cv1 = ComputedVariable(formula="abs(-42)")
        cv2 = ComputedVariable(formula="round(pi_val, 2)")
        cv3 = ComputedVariable(formula="max(val1, val2)")

        config = FormulaConfig(
            id="test",
            formula="result",
            variables={"pi_val": 3.14159, "val1": 100, "val2": 200, "abs_result": cv1, "round_result": cv2, "max_result": cv3},
        )

        eval_context: dict[str, ContextValue] = {}
        resolver = self.create_mock_resolver({})

        # Mock the pipeline evaluation for mathematical functions
        def mock_evaluate_formula_via_pipeline(
            formula, context, variables=None, bypass_dependency_management=False, allow_unresolved_states=False
        ):
            if formula == "abs(-42)":
                return {"success": True, "value": 42}
            elif formula == "round(pi_val, 2)":
                return {"success": True, "value": 3.14}
            elif formula == "max(val1, val2)":
                return {"success": True, "value": 200}
            return {"success": False, "error": "Unknown formula"}

        with patch(
            "ha_synthetic_sensors.formula_evaluator_service.FormulaEvaluatorService.evaluate_formula_via_pipeline",
            side_effect=mock_evaluate_formula_via_pipeline,
        ):
            resolve_config_variables(eval_context, config, resolver)

        assert eval_context["abs_result"].value == 42
        assert eval_context["round_result"].value == 3.14
        assert eval_context["max_result"].value == 200


class TestIntegrationWithExistingSystem:
    """Test integration of computed variables with existing variable system."""

    def test_computed_variables_in_formula_config(self):
        """Test that FormulaConfig properly handles computed variables."""
        cv = ComputedVariable(formula="input * 2")
        config = FormulaConfig(id="test_sensor", formula="output", variables={"input": "sensor.input", "output": cv})

        assert config.id == "test_sensor"
        assert config.formula == "output"
        assert config.variables["input"] == "sensor.input"
        assert isinstance(config.variables["output"], ComputedVariable)
        assert config.variables["output"].formula == "input * 2"

    def test_computed_variables_type_annotation_compatibility(self):
        """Test that computed variables work with FormulaConfig type annotations."""
        from typing import Union

        # This should not raise type errors
        variables: dict[str, Union[str, int, float, ComputedVariable]] = {
            "entity": "sensor.test",
            "literal": 42,
            "computed": ComputedVariable(formula="entity + literal"),
        }

        config = FormulaConfig(id="test", formula="computed", variables=variables)
        assert len(config.variables) == 3


class TestComputedVariablesInAttributes:
    """Test computed variables used within attribute formulas."""

    def test_computed_variables_in_attribute_parsing(self, mock_hass, mock_entity_registry, mock_states):
        """Test that ConfigManager correctly parses computed variables in attributes."""
        from pathlib import Path

        config_manager = ConfigManager(config_path=Path("/tmp/test.yaml"), hass=mock_hass)

        yaml_data = {
            "version": "1.0",
            "sensors": {
                "power_sensor": {
                    "name": "Power Sensor",
                    "formula": "base_power",
                    "variables": {"base_power": 1000},
                    "attributes": {
                        "efficiency": {
                            "formula": "computed_eff",
                            "variables": {"raw_eff": 0.85, "computed_eff": {"formula": "raw_eff * 100"}},
                        }
                    },
                }
            },
        }

        config = config_manager._parse_yaml_config(yaml_data)
        sensor = config.sensors[0]

        # Should have main formula + attribute formula
        assert len(sensor.formulas) == 2

        # Check attribute formula has computed variable
        attr_formula = sensor.formulas[1]  # attribute formula
        assert "computed_eff" in attr_formula.variables
        assert isinstance(attr_formula.variables["computed_eff"], ComputedVariable)
        assert attr_formula.variables["computed_eff"].formula == "raw_eff * 100"

    def test_computed_variables_in_attributes_resolution(self):
        """Test that computed variables in attributes resolve correctly."""
        from unittest.mock import patch

        cv = ComputedVariable(formula="raw_value * factor")
        attr_formula = FormulaConfig(
            id="test_sensor_voltage",
            formula="computed_voltage",
            variables={"raw_value": 120.0, "factor": 2.0, "computed_voltage": cv},
        )

        eval_context: dict[str, ContextValue] = {}

        def mock_resolver(var_name: str, var_value: any, context: dict, sensor_config: any) -> any:
            if isinstance(var_value, (int, float)):
                return var_value
            return None

        # Mock the pipeline evaluation for attribute resolution
        def mock_evaluate_formula_via_pipeline(
            formula, context, variables=None, bypass_dependency_management=False, allow_unresolved_states=False
        ):
            if formula == "raw_value * factor":
                return {"success": True, "value": 240.0}  # 120 * 2
            return {"success": False, "error": "Unknown formula"}

        with patch(
            "ha_synthetic_sensors.formula_evaluator_service.FormulaEvaluatorService.evaluate_formula_via_pipeline",
            side_effect=mock_evaluate_formula_via_pipeline,
        ):
            resolve_config_variables(eval_context, attr_formula, mock_resolver)

        # Verify computed variable was resolved correctly
        assert eval_context["raw_value"].value == 120.0
        assert eval_context["factor"].value == 2.0
        assert eval_context["computed_voltage"].value == 240.0  # 120 * 2

    def test_computed_variables_with_state_reference_in_attributes(self):
        """Test computed variables that reference 'state' within attribute formulas."""
        from unittest.mock import patch

        # This tests the critical scoping requirement:
        # state in attribute formulas (including computed variables) should refer to main sensor result
        cv = ComputedVariable(formula="state * multiplier")
        attr_formula = FormulaConfig(
            id="test_sensor_scaled", formula="scaled_result", variables={"multiplier": 1.5, "scaled_result": cv}
        )

        # Pre-populate context with 'state' representing main sensor's post-evaluation result
        eval_context: dict[str, ContextValue] = {"state": 100.0}  # Main sensor evaluated to 100

        def mock_resolver(var_name: str, var_value: any, context: dict, sensor_config: any) -> any:
            if isinstance(var_value, (int, float)):
                return var_value
            return None

        # Mock the pipeline evaluation for state reference
        def mock_evaluate_formula_via_pipeline(
            formula, context, variables=None, bypass_dependency_management=False, allow_unresolved_states=False
        ):
            if formula == "state * multiplier":
                return {"success": True, "value": 150.0}  # 100 * 1.5
            return {"success": False, "error": "Unknown formula"}

        with patch(
            "ha_synthetic_sensors.formula_evaluator_service.FormulaEvaluatorService.evaluate_formula_via_pipeline",
            side_effect=mock_evaluate_formula_via_pipeline,
        ):
            resolve_config_variables(eval_context, attr_formula, mock_resolver)

        # Verify computed variable used the state value correctly
        assert eval_context["state"] == 100.0  # Should preserve original state (raw value)
        assert eval_context["multiplier"].value == 1.5
        assert eval_context["scaled_result"].value == 150.0  # state (100) * multiplier (1.5)

    def test_complex_attribute_computed_variables_with_dependencies(self):
        """Test complex computed variable chains in attribute formulas."""
        from unittest.mock import patch

        cv1 = ComputedVariable(formula="state + offset")
        cv2 = ComputedVariable(formula="adjusted_value * scale_factor")
        cv3 = ComputedVariable(formula="scaled_value if scaled_value > threshold else threshold")

        attr_formula = FormulaConfig(
            id="test_sensor_complex_attr",
            formula="final_result",
            variables={
                "offset": 50,
                "scale_factor": 1.2,
                "threshold": 200,
                "adjusted_value": cv1,  # state + 50
                "scaled_value": cv2,  # adjusted_value * 1.2
                "final_result": cv3,  # max(scaled_value, 200)
            },
        )

        # Simulate main sensor result of 120
        eval_context: dict[str, ContextValue] = {"state": 120.0}

        def mock_resolver(var_name: str, var_value: any, context: dict, sensor_config: any) -> any:
            if isinstance(var_value, (int, float)):
                return var_value
            return None

        # Mock the pipeline evaluation for complex dependency chain
        def mock_evaluate_formula_via_pipeline(
            formula, context, variables=None, bypass_dependency_management=False, allow_unresolved_states=False
        ):
            if formula == "state + offset":
                return {"success": True, "value": 170.0}  # 120 + 50
            elif formula == "adjusted_value * scale_factor":
                return {"success": True, "value": 204.0}  # 170 * 1.2
            elif formula == "scaled_value if scaled_value > threshold else threshold":
                return {"success": True, "value": 204.0}  # max(204, 200)
            return {"success": False, "error": "Unknown formula"}

        with patch(
            "ha_synthetic_sensors.formula_evaluator_service.FormulaEvaluatorService.evaluate_formula_via_pipeline",
            side_effect=mock_evaluate_formula_via_pipeline,
        ):
            resolve_config_variables(eval_context, attr_formula, mock_resolver)

        # Verify the dependency chain resolved correctly
        assert eval_context["state"] == 120.0  # Preserved original state (raw value)
        assert eval_context["offset"].value == 50
        assert eval_context["scale_factor"].value == 1.2
        assert eval_context["threshold"].value == 200
        assert eval_context["adjusted_value"].value == 170.0  # 120 + 50
        assert eval_context["scaled_value"].value == 204.0  # 170 * 1.2
        assert eval_context["final_result"].value == 204.0  # max(204, 200)
