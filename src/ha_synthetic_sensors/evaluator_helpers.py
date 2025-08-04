"""Helper utilities for the evaluator."""

import ast
import logging
from typing import Any

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
    def process_evaluation_result(result: Any) -> float | str | bool:
        """Process and validate evaluation result."""
        # Handle numeric results
        if isinstance(result, int | float):
            return result

        # Handle boolean results
        if isinstance(result, bool):
            return result

        # Handle string results
        if isinstance(result, str):
            # Check for HA state values first
            if is_ha_state_value(result):
                return result
            # Try to convert numeric strings to numbers
            return EvaluatorHelpers.convert_string_to_number_if_possible(result)

        # Handle unexpected types by converting to string
        return str(result)

    @staticmethod
    def get_cache_key_id(formula_config: Any, context: dict[str, Any] | None) -> str:
        """Generate cache key ID for formula configuration."""
        if context:
            # Create a deterministic hash of context keys and values for cache keying
            import hashlib  # pylint: disable=import-outside-toplevel

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
