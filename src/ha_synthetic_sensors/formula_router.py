"""Formula routing system for directing formulas to appropriate evaluators."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
import re

from .shared_constants import COLLECTION_PREFIXES, DATETIME_FUNCTIONS, DURATION_FUNCTIONS, STRING_FUNCTIONS

_LOGGER = logging.getLogger(__name__)


class FormulaSyntaxError(Exception):
    """Exception raised for malformed formula syntax."""

    def __init__(self, message: str, formula: str, position: int | None = None):
        self.formula = formula
        self.position = position
        if position is not None:
            super().__init__(f"Syntax error in formula '{formula}' at position {position}: {message}")
        else:
            super().__init__(f"Syntax error in formula '{formula}': {message}")

    def __str__(self) -> str:
        if self.position is not None:
            # Show the formula with a pointer to the error position
            pointer = " " * self.position + "^"
            return f"{super().__str__()}\n{self.formula}\n{pointer}"
        return super().__str__()


class EvaluatorType(Enum):
    """Types of formula evaluators."""

    STRING = "string"
    NUMERIC = "numeric"
    DATE = "date"
    BOOLEAN = "boolean"


@dataclass
class RoutingResult:
    """Result of formula routing analysis."""

    evaluator_type: EvaluatorType
    should_cache: bool
    user_function: str | None = None
    original_formula: str | None = None


class FormulaRouter:
    """Routes formulas to appropriate evaluators based on content analysis."""

    def __init__(self) -> None:
        """Initialize the formula router."""
        self._logger = _LOGGER.getChild(self.__class__.__name__)

    def route_formula(self, formula: str) -> RoutingResult:
        """
        Route a formula to the appropriate evaluator.

        Uses three-category routing:
        1. Explicit user functions (str(), numeric(), date()) - Highest priority
        2. String literals (contains non-collection quotes) - Automatic string routing
        3. Default numeric (existing behavior) - Everything else

        Args:
            formula: The formula to analyze and route

        Returns:
            RoutingResult with evaluator type and caching decision

        Raises:
            FormulaSyntaxError: If formula contains syntax errors (malformed functions, etc.)
        """
        self._logger.debug("Routing formula: %s", formula)

        # First, validate formula syntax
        self._validate_formula_syntax(formula)

        # Category 1: Check for explicit user functions (highest priority)
        user_function_result = self._check_user_functions(formula)
        if user_function_result:
            self._logger.debug(
                "Formula routed to %s via user function: %s",
                user_function_result.evaluator_type.value,
                user_function_result.user_function,
            )
            return user_function_result

        # Category 2: Check for duration functions (automatic date routing)
        if self._contains_duration_functions(formula):
            self._logger.debug("Formula routed to date evaluator due to duration functions")
            return RoutingResult(evaluator_type=EvaluatorType.DATE, should_cache=False, original_formula=formula)

        # Category 2a: Check for datetime functions (automatic date routing)
        if self._contains_datetime_functions(formula):
            self._logger.debug("Formula routed to date evaluator due to datetime functions")
            return RoutingResult(evaluator_type=EvaluatorType.DATE, should_cache=False, original_formula=formula)

        # Category 3: Check for string literals (automatic string routing)
        if self._contains_string_literals(formula):
            self._logger.debug("Formula routed to string evaluator due to string literals")
            return RoutingResult(evaluator_type=EvaluatorType.STRING, should_cache=False, original_formula=formula)

        # Category 4: Check if formula is a quoted string literal (from variable resolution)
        if (formula.startswith('"') and formula.endswith('"')) or (formula.startswith("'") and formula.endswith("'")):
            self._logger.debug("Formula routed to string evaluator (quoted literal)")
            return RoutingResult(evaluator_type=EvaluatorType.STRING, should_cache=False, original_formula=formula)

        # Category 5: Default to numeric (existing behavior)
        self._logger.debug("Formula routed to numeric evaluator (default)")
        return RoutingResult(evaluator_type=EvaluatorType.NUMERIC, should_cache=True, original_formula=formula)

    def _check_user_functions(self, formula: str) -> RoutingResult | None:
        """
        Check for explicit user function wrappers.

        Detects: str(), numeric(), date(), bool()

        Args:
            formula: Formula to check

        Returns:
            RoutingResult if user function found, None otherwise
        """
        formula_stripped = formula.strip()

        # Check for str() function
        if formula_stripped.startswith("str(") and formula_stripped.endswith(")"):
            return RoutingResult(
                evaluator_type=EvaluatorType.STRING, should_cache=False, user_function="str", original_formula=formula
            )

        # Check for string manipulation functions
        string_function_patterns = [f"{func}(" for func in STRING_FUNCTIONS if func != "str"]
        for func_start in string_function_patterns:
            if (
                formula_stripped.startswith(func_start)
                and formula_stripped.endswith(")")
                and self._is_single_function_call(formula_stripped, func_start[:-1])
            ):
                func_name = func_start[:-1]  # Remove the '('
                return RoutingResult(
                    evaluator_type=EvaluatorType.STRING,
                    should_cache=False,
                    user_function=func_name,
                    original_formula=formula,
                )

        # Check for numeric() function
        if formula_stripped.startswith("numeric(") and formula_stripped.endswith(")"):
            return RoutingResult(
                evaluator_type=EvaluatorType.NUMERIC, should_cache=True, user_function="numeric", original_formula=formula
            )

        # Check for date() function
        if formula_stripped.startswith("date(") and formula_stripped.endswith(")"):
            return RoutingResult(
                evaluator_type=EvaluatorType.DATE, should_cache=False, user_function="date", original_formula=formula
            )

        # Check for bool() function (future)
        if formula_stripped.startswith("bool(") and formula_stripped.endswith(")"):
            return RoutingResult(
                evaluator_type=EvaluatorType.BOOLEAN, should_cache=False, user_function="bool", original_formula=formula
            )

        return None

    def _is_single_function_call(self, formula: str, function_name: str) -> bool:
        """
        Check if a formula is truly a single function call, not a complex expression.

        For example:
        - "title('device')" -> True (single function call)
        - "title('device') + ': ' + trim(name)" -> False (complex expression)

        Args:
            formula: The formula to check
            function_name: The name of the function to check for

        Returns:
            True if it's a single function call, False otherwise
        """
        # Count parentheses to find the end of the function call
        if not formula.startswith(f"{function_name}("):
            return False

        paren_count = 0
        start_pos = len(function_name) + 1  # Position after "function("

        for i, char in enumerate(formula[start_pos:], start_pos):
            if char == "(":
                paren_count += 1
            elif char == ")":
                if paren_count == 0:
                    # Found the closing parenthesis for the function
                    # Check if there's anything significant after it
                    remaining = formula[i + 1 :].strip()
                    # If there's anything other than whitespace, it's not a single function call
                    return len(remaining) == 0
                paren_count -= 1

        # If we get here, parentheses weren't balanced properly
        return False

    def _contains_string_literals(self, formula: str) -> bool:
        """
        Detect if formula contains string literals that indicate string operations.

        Looks for quoted strings but excludes collection patterns.
        Collection patterns have the form 'key:value' where key is typically
        a known pattern like 'device_class', 'state', 'attribute', etc.

        Args:
            formula: Formula to analyze

        Returns:
            True if string literals found, False otherwise
        """
        # Pattern to find quoted strings (single or double quotes)
        string_pattern = r"""(?:'[^']*'|"[^"]*")"""
        matches = re.findall(string_pattern, formula)

        for match in matches:
            # Remove the quotes to check content
            content = match[1:-1]  # Remove first and last character (quotes)

            # Check if this looks like a collection pattern
            is_collection_pattern = any(content.startswith(prefix) for prefix in COLLECTION_PREFIXES)

            if not is_collection_pattern:
                self._logger.debug("Found non-collection string literal: %s", match)
                return True

        return False

    def extract_inner_formula(self, formula: str, user_function: str) -> str:
        """
        Extract the inner formula from a user function wrapper.

        Args:
            formula: The wrapped formula (e.g., "str(state + 'W')")
            user_function: The user function name (e.g., "str")

        Returns:
            The inner formula (e.g., "state + 'W'")
        """
        formula_stripped = formula.strip()
        function_prefix = f"{user_function}("

        if formula_stripped.startswith(function_prefix) and formula_stripped.endswith(")"):
            # Extract content between function( and closing )
            inner_formula = formula_stripped[len(function_prefix) : -1]
            self._logger.debug("Extracted inner formula from %s(): %s", user_function, inner_formula)
            return inner_formula

        # If extraction fails, return original formula
        self._logger.warning("Failed to extract inner formula from %s function: %s", user_function, formula)
        return formula

    def _validate_formula_syntax(self, formula: str) -> None:
        """
        Validate formula syntax and raise FormulaSyntaxError for malformed syntax.

        Detects:
        - Malformed function calls: "str(unclosed", "str(invalid syntax +"
        - Unclosed quotes: "'unclosed string
        - Mismatched parentheses: "str(nested(unclosed"

        Args:
            formula: Formula to validate

        Raises:
            FormulaSyntaxError: If syntax errors are detected
        """
        formula = formula.strip()

        # Check for malformed function calls
        self._validate_function_calls(formula)

        # Check for unclosed quotes
        self._validate_quotes(formula)

        # Check for mismatched parentheses
        self._validate_parentheses(formula)

    def _validate_function_calls(self, formula: str) -> None:
        """Validate function call syntax."""
        # Pattern to detect potential function calls
        function_pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\("

        for match in re.finditer(function_pattern, formula):
            func_name = match.group(1)
            func_start = match.start()

            # Find the opening parenthesis
            paren_start = match.end() - 1

            # Check if this function call is properly closed
            if not self._is_function_call_closed(formula, paren_start):
                # Find where the unclosed function call ends
                remaining = formula[paren_start + 1 :]
                if "+" in remaining or "-" in remaining or "*" in remaining or "/" in remaining:
                    # Looks like an incomplete expression
                    raise FormulaSyntaxError(
                        f"Malformed function call '{func_name}()' - missing closing parenthesis or incomplete expression",
                        formula,
                        func_start,
                    )
                # Simple unclosed function
                raise FormulaSyntaxError(
                    f"Malformed function call '{func_name}()' - missing closing parenthesis", formula, func_start
                )

    def _validate_quotes(self, formula: str) -> None:
        """Validate quote matching."""
        in_single_quote = False
        in_double_quote = False
        i = 0

        while i < len(formula):
            char = formula[i]

            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif char == "\\" and (in_single_quote or in_double_quote):
                # Skip escaped character
                i += 1

            i += 1

        if in_single_quote:
            raise FormulaSyntaxError("Unclosed single quote", formula)
        if in_double_quote:
            raise FormulaSyntaxError("Unclosed double quote", formula)

    def _validate_parentheses(self, formula: str) -> None:
        """Validate parentheses matching (basic check)."""
        paren_count = 0
        in_quote = False
        quote_char = None

        for i, char in enumerate(formula):
            if char in ('"', "'") and not in_quote:
                in_quote = True
                quote_char = char
            elif char == quote_char and in_quote:
                in_quote = False
                quote_char = None
            elif not in_quote:
                if char == "(":
                    paren_count += 1
                elif char == ")":
                    paren_count -= 1
                    if paren_count < 0:
                        raise FormulaSyntaxError("Unexpected closing parenthesis", formula, i)

        if paren_count > 0:
            raise FormulaSyntaxError("Missing closing parenthesis", formula)

    def _is_function_call_closed(self, formula: str, paren_start: int) -> bool:
        """Check if a function call starting at paren_start is properly closed."""
        paren_count = 1  # We start after the opening parenthesis
        in_quote = False
        quote_char = None

        for i in range(paren_start + 1, len(formula)):
            char = formula[i]

            if char in ('"', "'") and not in_quote:
                in_quote = True
                quote_char = char
            elif char == quote_char and in_quote:
                in_quote = False
                quote_char = None
            elif not in_quote:
                if char == "(":
                    paren_count += 1
                elif char == ")":
                    paren_count -= 1
                    if paren_count == 0:
                        return True

        return False

    def _contains_duration_functions(self, formula: str) -> bool:
        """
        Detect if formula contains duration function calls.

        Looks for duration functions like days(), hours(), weeks(), etc.
        These indicate date arithmetic operations.

        Args:
            formula: Formula to analyze

        Returns:
            True if duration functions found, False otherwise
        """
        # Check for duration function patterns
        for duration_func in DURATION_FUNCTIONS:
            pattern = rf"\b{re.escape(duration_func)}\s*\("
            if re.search(pattern, formula):
                self._logger.debug("Found duration function: %s", duration_func)
                return True

        return False

    def _contains_datetime_functions(self, formula: str) -> bool:
        """
        Detect if formula contains datetime function calls.

        Looks for datetime functions like now(), today(), yesterday(), utc_now(), etc.
        These indicate datetime operations that should be routed to the date handler.

        Args:
            formula: Formula to analyze

        Returns:
            True if datetime functions found, False otherwise
        """

        # Check for datetime function patterns
        for datetime_func in DATETIME_FUNCTIONS:
            pattern = rf"\b{re.escape(datetime_func)}\s*\("
            if re.search(pattern, formula):
                self._logger.debug("Found datetime function: %s", datetime_func)
                return True

        return False
