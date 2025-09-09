"""Centralized variable extraction for formula parsing using Python AST.

This module consolidates all variable extraction logic to eliminate duplicate code
and ensure consistent behavior across the codebase. Uses Python's AST module
for proper parsing instead of fragile regex patterns.
"""

import ast
from enum import Enum

from ..constants_boolean_states import get_core_false_states, get_core_true_states
from ..constants_formula import FORMULA_RESERVED_WORDS
from ..regex_helper import create_identifier_pattern, find_all_matches
from ..shared_constants import METADATA_FUNCTIONS

# Use centralized constants instead of hardcoded lists
# Additional built-in functions not in the main constants
ADDITIONAL_BUILTIN_FUNCTIONS = {"range", "enumerate", "zip", "map", "filter", "any", "all", "sorted", "reversed", "pi", "e"}


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
        # Use centralized formula reserved words instead of separate lists
        exclusions = set(FORMULA_RESERVED_WORDS | ADDITIONAL_BUILTIN_FUNCTIONS)

        # Add metadata functions from shared constants
        exclusions.update(METADATA_FUNCTIONS)

        # Add Home Assistant specific tokens that should be excluded
        exclusions.update({"state", "states", "entity", "attributes"})

        # Add Home Assistant boolean state constants (on, off, home, not_home, etc.)
        # These should not be treated as variables in computed variable validation
        boolean_states: set[str] = set()
        # Convert to strings to handle both string and constant values
        boolean_states.update(str(state) for state in get_core_true_states())
        boolean_states.update(str(state) for state in get_core_false_states())
        exclusions.update(boolean_states)

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
        # Use centralized identifier pattern from regex helper

        identifier_pattern = create_identifier_pattern()
        identifiers = set(find_all_matches(formula, identifier_pattern))

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
