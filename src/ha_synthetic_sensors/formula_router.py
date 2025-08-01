"""Formula routing system for directing formulas to appropriate evaluators."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
import re

_LOGGER = logging.getLogger(__name__)


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
        """
        self._logger.debug("Routing formula: %s", formula)

        # Category 1: Check for explicit user functions (highest priority)
        user_function_result = self._check_user_functions(formula)
        if user_function_result:
            self._logger.debug(
                "Formula routed to %s via user function: %s",
                user_function_result.evaluator_type.value,
                user_function_result.user_function,
            )
            return user_function_result

        # Category 2: Check for string literals (automatic string routing)
        if self._contains_string_literals(formula):
            self._logger.debug("Formula routed to string evaluator due to string literals")
            return RoutingResult(evaluator_type=EvaluatorType.STRING, should_cache=False, original_formula=formula)

        # Category 3: Default to numeric (existing behavior)
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

        # Known collection pattern prefixes
        collection_prefixes = {
            "device_class:",
            "state:",
            "attribute:",
            "entity_id:",
            "domain:",
            "area:",
            "integration:",
            "platform:",
        }

        for match in matches:
            # Remove the quotes to check content
            content = match[1:-1]  # Remove first and last character (quotes)

            # Check if this looks like a collection pattern
            is_collection_pattern = any(content.startswith(prefix) for prefix in collection_prefixes)

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
