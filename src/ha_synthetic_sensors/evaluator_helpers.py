"""Helper utilities for the evaluator."""

import ast
import hashlib
import logging
from typing import Any

from ha_synthetic_sensors.constants_boolean_states import get_current_false_states, get_current_true_states
from ha_synthetic_sensors.constants_formula import is_ha_state_value

_LOGGER = logging.getLogger(__name__)


class EvaluatorHelpers:
    """Helper methods for the evaluator."""

    @staticmethod
    def validate_formula_syntax(formula: str, dependency_handler: Any) -> list[str]:
        """Validate formula syntax and return list of errors."""
        errors = []

        try:
            # Basic syntax validation using AST
            ast.parse(formula, mode="eval")
        except SyntaxError as err:
            errors.append(f"Syntax error: {err.msg} at position {err.offset}")
            return errors

        try:
            # Check for valid variable names and function calls
            dependencies = dependency_handler.get_formula_dependencies(formula)

            # Validate each dependency
            for dep in dependencies:
                if not dep.replace(".", "_").replace("-", "_").replace(":", "_").isidentifier():
                    errors.append(f"Invalid variable name: {dep}")

            # Note: We don't require formulas to reference entities - they can use literal values in variables

        except Exception as err:
            errors.append(f"Validation error: {err}")

        return errors

    @staticmethod
    def convert_string_to_number_if_possible(result: str) -> str | int | float:
        """Convert string result to number if it represents a numeric value."""
        # If result is a string that looks like a number, convert it to appropriate type
        try:
            # Try integer first (to avoid converting 5.0 to 5)
            if "." not in result:
                return int(result)
            # Try float
            return float(result)
        except ValueError:
            # If conversion fails, return original string
            return result

    @staticmethod
    def convert_string_to_boolean_if_possible(result: str) -> str | bool:
        """Convert HA-style boolean strings to actual boolean values for enhanced SimpleEval.

        Uses HA's own device trigger mappings for ground truth on what constitutes
        true/false states, avoiding hardcoded lists.
        """
        if isinstance(result, str):
            # Use HA's lazy-loaded boolean state mappings
            true_states = get_current_true_states()
            false_states = get_current_false_states()

            # Check against HA's official boolean state mappings
            if result in true_states or result.lower() in {str(s).lower() for s in true_states if s is not None}:
                return True
            if result in false_states or result.lower() in {str(s).lower() for s in false_states if s is not None}:
                return False

        # Return original value if not a recognized boolean string
        return result

    @staticmethod
    def preprocess_value_for_enhanced_eval(value: Any) -> Any:
        """Preprocess values for enhanced SimpleEval evaluation.

        Handles conversion of strings to appropriate types:
        - HA boolean strings ('on'/'off') to boolean values
        - Numeric strings to numbers
        """
        if isinstance(value, str):
            # Try boolean conversion first (HA state values)
            boolean_result = EvaluatorHelpers.convert_string_to_boolean_if_possible(value)
            if isinstance(boolean_result, bool):
                return boolean_result

            # Try numeric conversion if not a boolean
            return EvaluatorHelpers.convert_string_to_number_if_possible(value)

        return value

    @staticmethod
    def process_evaluation_result(result: Any) -> float | str | bool | None:
        """Process and validate evaluation result."""
        processed_result: float | str | bool | None = None

        # Handle None values - preserve them for Home Assistant to handle
        # This prevents premature conversion of None to 'unknown' string, which causes ValueError
        # for numeric sensors (energy, power, etc.) that expect numeric values or None, not strings.
        # Home Assistant will handle None appropriately by converting to STATE_UNKNOWN internally.
        if result is None:
            processed_result = None
        # Handle numeric and boolean results
        elif isinstance(result, int | float | bool):
            processed_result = result
        # Handle string results
        elif isinstance(result, str):
            # Preserve HA state strings
            if is_ha_state_value(result):
                processed_result = result
            else:
                # Use priority analyzer: boolean-first, then numeric
                coerced = EvaluatorHelpers.preprocess_value_for_enhanced_eval(result)
                processed_result = coerced if isinstance(coerced, int | float | bool) else str(coerced)
        else:
            # Handle unexpected types by converting to string
            processed_result = str(result)

        return processed_result

    @staticmethod
    def get_cache_key_id(formula_config: Any, context: dict[str, Any] | None) -> str:
        """Generate cache key ID for formula configuration."""
        if context:
            # Create a deterministic hash of context keys and values for cache keying
            context_items = sorted(context.items()) if context else []
            context_str = str(context_items)
            context_hash = hashlib.md5(context_str.encode(), usedforsecurity=False).hexdigest()[:8]
            return f"{formula_config.id}_{context_hash}"
        return str(formula_config.id)

    @staticmethod
    def should_cache_result(result: Any) -> bool:
        """Determine if a result should be cached."""
        # Only cache numeric results for now
        return isinstance(result, int | float)
