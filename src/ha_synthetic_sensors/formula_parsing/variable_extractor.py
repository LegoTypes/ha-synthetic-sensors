"""Centralized variable extraction for formula parsing using Python AST.

This module consolidates all variable extraction logic to eliminate duplicate code
and ensure consistent behavior across the codebase. Uses Python's AST module
for proper parsing instead of fragile regex patterns.
"""

import ast
from enum import Enum
import re

from ..shared_constants import BUILTIN_TYPES, METADATA_FUNCTIONS

# Standard Python keywords and built-in functions that should be excluded
PYTHON_KEYWORDS = {
    "and",
    "or",
    "not",
    "if",
    "else",
    "elif",
    "True",
    "False",
    "None",
    "def",
    "class",
    "import",
    "from",
    "return",
    "yield",
    "lambda",
    "with",
    "as",
    "try",
    "except",
    "finally",
    "raise",
    "assert",
    "global",
    "nonlocal",
    "del",
    "pass",
    "break",
    "continue",
    "for",
    "while",
    "in",
    "is",
}

BUILTIN_FUNCTIONS = {
    "abs",
    "round",
    "max",
    "min",
    "sum",
    "len",
    # Core built-in types (imported from shared_constants)
    *BUILTIN_TYPES,
    "range",
    "enumerate",
    "zip",
    "map",
    "filter",
    "any",
    "all",
    "sorted",
    "reversed",
    "avg",
    "count",
    "std",
    "var",
}

MATHEMATICAL_FUNCTIONS = {"sin", "cos", "tan", "sqrt", "log", "exp", "pow", "ceil", "floor", "pi", "e"}


class ExtractionContext(Enum):
    """Context for variable extraction to allow different behaviors."""

    VARIABLE_RESOLUTION = "variable_resolution"
    DEPENDENCY_PARSING = "dependency_parsing"
    CONFIG_VALIDATION = "config_validation"
    GENERAL = "general"


class VariableVisitor(ast.NodeVisitor):
    """AST visitor to extract variables from Python expressions."""

    def __init__(self, exclusions: set[str], allow_dot_notation: bool = False):
        self.variables: set[str] = set()
        self.exclusions = exclusions
        self.allow_dot_notation = allow_dot_notation

    def visit_Name(self, node: ast.Name) -> None:
        """Visit name nodes (simple variables)."""
        if isinstance(node.ctx, ast.Load | ast.Store) and node.id not in self.exclusions:
            self.variables.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Visit attribute nodes (dot notation like obj.attr)."""
        if self.allow_dot_notation:
            # Build the full dotted name
            parts = []
            current: ast.expr = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value

            if isinstance(current, ast.Name):
                parts.append(current.id)
                full_name = ".".join(reversed(parts))
                if current.id not in self.exclusions:
                    self.variables.add(full_name)
            else:
                # If the base is not a simple name, just add the base
                self.visit(current)
        else:
            # Only visit the base object, ignore the attribute
            self.visit(node.value)


class FormulaVariableExtractor:
    """Centralized variable extractor for formulas using AST parsing."""

    def __init__(self) -> None:
        """Initialize the variable extractor."""

    def _get_exclusions_for_context(self, context: ExtractionContext) -> set[str]:
        """Get exclusions based on context."""
        exclusions = PYTHON_KEYWORDS | BUILTIN_FUNCTIONS | MATHEMATICAL_FUNCTIONS

        # Add metadata functions from shared constants
        exclusions.update(METADATA_FUNCTIONS)

        # Add Home Assistant specific tokens that should be excluded
        exclusions.update({"state", "states", "entity", "attributes"})

        return exclusions

    def extract_variables(
        self, formula: str, context: ExtractionContext = ExtractionContext.GENERAL, allow_dot_notation: bool = False
    ) -> set[str]:
        """Extract variable names from a formula using AST parsing."""
        # Special case: Skip variable extraction for metadata functions entirely
        # They should be handled directly by their dedicated handler
        if self._is_metadata_function(formula):
            return set()

        try:
            # Parse the formula as a Python expression
            tree = ast.parse(formula, mode="eval")

            # Get exclusions for this context
            exclusions = self._get_exclusions_for_context(context)

            # Visit the AST to extract variables
            visitor = VariableVisitor(exclusions, allow_dot_notation)
            visitor.visit(tree)

            return visitor.variables

        except SyntaxError:
            # If AST parsing fails, fall back to regex-based extraction for dependency parsing
            # This handles cases where the formula isn't valid Python syntax but we still want to extract identifiers
            if context == ExtractionContext.DEPENDENCY_PARSING:
                return self._fallback_regex_extraction(formula)

            # For other contexts, return empty set to maintain strict parsing
            return set()

    def _fallback_regex_extraction(self, formula: str) -> set[str]:
        """Fallback regex-based extraction for cases where AST parsing fails."""
        # Extract identifiers using regex
        identifier_pattern = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b")
        identifiers = set(identifier_pattern.findall(formula))

        # Apply the same exclusions as AST-based extraction
        exclusions = self._get_exclusions_for_context(ExtractionContext.DEPENDENCY_PARSING)

        return identifiers - exclusions

    def _is_metadata_function(self, formula: str) -> bool:
        """Check if the formula is a metadata function call."""
        try:
            # Try to parse as an AST and check if it's a function call to metadata
            tree = ast.parse(formula.strip(), mode="eval")
            if isinstance(tree.body, ast.Call) and isinstance(tree.body.func, ast.Name) and tree.body.func.id == "metadata":
                return True
        except SyntaxError:
            pass
        return False


# Global instance for convenience
_extractor = FormulaVariableExtractor()


def extract_variables(
    formula: str, context: ExtractionContext = ExtractionContext.GENERAL, allow_dot_notation: bool = False
) -> set[str]:
    """Extract variables from a formula using the centralized extractor."""
    return _extractor.extract_variables(formula, context, allow_dot_notation)
