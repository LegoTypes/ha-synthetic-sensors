"""Boolean formula handler for processing logical expressions."""

import ast
import logging
import re
from typing import TYPE_CHECKING, Any

from ..constants_handlers import (
    BOOLEAN_LITERAL_VALUES,
    BOOLEAN_OPERATORS,
    BOOLEAN_STATE_FUNCTIONS,
    ERROR_BOOLEAN_RESULT_TYPE,
    HANDLER_NAME_BOOLEAN,
)
from ..type_definitions import ContextValue
from .base_handler import FormulaHandler

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class BooleanHandler(FormulaHandler):
    """Handler for boolean formulas in the compiler-like evaluation system."""

    def can_handle(self, formula: str) -> bool:
        """Determine if a formula should be processed as a boolean formula.

        Args:
            formula: The formula to check

        Returns:
            True if the formula contains boolean operators, comparisons, or boolean literals
        """
        # Check for boolean operators
        if re.search(rf"\b({'|'.join(BOOLEAN_OPERATORS)})\b", formula, re.IGNORECASE):
            return True

        # Check for comparison operators
        if re.search(r"[<>=!]=?", formula):
            return True

        # Check for boolean literals
        if re.search(rf"\b({'|'.join(BOOLEAN_LITERAL_VALUES)})\b", formula):
            return True

        # Check for boolean state functions
        return re.search(rf"\b({'|'.join(BOOLEAN_STATE_FUNCTIONS)})\b", formula, re.IGNORECASE) is not None

    def evaluate(self, formula: str, context: dict[str, ContextValue] | None = None) -> bool:
        """Evaluate a boolean formula and return the result.

        Args:
            formula: The boolean formula to evaluate
            context: Variable context for evaluation

        Returns:
            The boolean result of the evaluation

        Raises:
            ValueError: If the result is not a boolean value
        """
        try:
            _LOGGER.debug("Evaluating boolean formula: %s", formula)

            # Delegate to expression evaluator for complex boolean expressions
            if self._expression_evaluator:
                result = self._expression_evaluator(formula, context)
            else:
                # Simple evaluation for basic boolean expressions
                result = self._safe_eval_boolean(formula, context or {})

            # Ensure result is boolean
            if not isinstance(result, bool):
                raise ValueError(ERROR_BOOLEAN_RESULT_TYPE.format(type_name=type(result).__name__, result=result))

            _LOGGER.debug("Boolean formula result: %s", result)
            return result

        except Exception as e:
            _LOGGER.warning("Boolean formula evaluation failed for '%s': %s", formula, e)
            raise

    def _safe_eval_boolean(self, formula: str, context: dict[str, Any]) -> bool:
        """Safely evaluate a boolean expression.

        Args:
            formula: The boolean formula to evaluate
            context: Variable context for evaluation

        Returns:
            The boolean result of the evaluation
        """
        # For basic boolean literals, just return them directly
        if formula.strip().lower() in ("true", "false"):
            return formula.strip().lower() == "true"

        # For simple variable lookups, check if the variable exists and is truthy
        if formula.strip() in context:
            value = context[formula.strip()]
            return bool(value)

        # Try to evaluate as a literal first (numbers, strings, simple literals)
        try:
            result = ast.literal_eval(formula)
            return bool(result)
        except (ValueError, SyntaxError):
            pass

        # For boolean expressions, try safe evaluation using compile + eval with restricted environment
        try:
            # Parse the expression to check if it's safe
            parsed = ast.parse(formula, mode="eval")

            # Check if the expression only contains safe operations
            if self._is_safe_boolean_expression(parsed):
                # Create a safe namespace with only boolean values and context variables
                safe_names = {
                    "True": True,
                    "False": False,
                    "__builtins__": {},
                }
                safe_names.update(context)

                # Compile and evaluate with restricted namespace
                compiled = compile(parsed, "<boolean_expression>", "eval")
                # pylint: disable=eval-used  # Safe usage with restricted namespace and validated AST
                result = eval(compiled, {"__builtins__": {}}, safe_names)  # nosec B307  # Safe usage with restricted namespace
                return bool(result)

            raise ValueError(f"Unsafe boolean expression: {formula}")

        except Exception as e:
            # For complex expressions, we should not reach here since they're handled
            # by the expression evaluator in the evaluate method
            raise ValueError(f"Cannot safely evaluate boolean expression without expression evaluator: {formula}") from e

    def _is_safe_boolean_expression(self, node: ast.AST) -> bool:
        """Check if an AST node represents a safe boolean expression.

        Args:
            node: The AST node to check

        Returns:
            True if the expression is safe for boolean evaluation
        """
        # Allowed node types for safe boolean expressions
        safe_node_types = (
            ast.Expression,
            ast.BoolOp,  # and, or
            ast.UnaryOp,  # not
            ast.Compare,  # ==, !=, <, >, <=, >=
            ast.Constant,  # True, False, numbers, strings
            ast.Name,  # variable names
            ast.Load,  # variable load context
            ast.And,  # and operator
            ast.Or,  # or operator
            ast.Not,  # not operator
            ast.Eq,
            ast.NotEq,
            ast.Lt,
            ast.LtE,
            ast.Gt,
            ast.GtE,  # comparison operators
            ast.IfExp,  # conditional expressions (ternary operator)
        )

        return all(isinstance(child_node, safe_node_types) for child_node in ast.walk(node))

    def get_handler_name(self) -> str:
        """Return the name of this handler."""
        return HANDLER_NAME_BOOLEAN

    def get_supported_functions(self) -> set[str]:
        """Return the set of supported function names."""
        return set(BOOLEAN_STATE_FUNCTIONS)

    def get_function_info(self) -> list[dict[str, Any]]:
        """Return information about supported functions."""
        return [
            {
                "name": function_name,
                "description": f"Returns boolean state for {function_name}",
                "parameters": [],
                "returns": {"type": "boolean", "description": "True if the condition is met"},
            }
            for function_name in BOOLEAN_STATE_FUNCTIONS
        ]
