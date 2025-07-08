"""
Simple formula evaluator for basic mathematical expressions.

This module provides a lightweight evaluator for simple formulas without
the complexity of the full Evaluator class.
"""

from __future__ import annotations

import re

from simpleeval import SimpleEval


class SimpleEvaluator:
    """Simple formula evaluator for basic mathematical expressions."""

    def __init__(self) -> None:
        """Initialize the simple evaluator."""
        self._evaluator = SimpleEval()

    def evaluate(self, formula: str, context: dict[str, float | int | str] | None = None) -> float:
        """Evaluate a simple formula with optional context variables.

        Args:
            formula: Mathematical formula to evaluate
            context: Optional context variables

        Returns:
            Evaluated result as float

        Raises:
            ValueError: If formula cannot be evaluated
        """
        if context:
            self._evaluator.names = context
        else:
            self._evaluator.names = {}

        try:
            result = self._evaluator.eval(formula)
            return float(result)
        except Exception as e:
            raise ValueError(f"Failed to evaluate formula '{formula}': {e}") from e

    def extract_variables(self, formula: str) -> set[str]:
        """Extract variable names from a formula.

        Args:
            formula: Formula to analyze

        Returns:
            Set of variable names found in the formula
        """
        # Simple regex to find variable names (letters, digits, underscores)
        variables = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", formula))

        # Remove known function names and keywords
        reserved = {"abs", "min", "max", "round", "sum", "len", "int", "float", "str", "bool"}
        variables -= reserved

        return variables
