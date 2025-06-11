"""Optimized dependency parsing for formula expressions.

This module provides efficient parsing of formula dependencies with
compiled regex patterns and comprehensive entity reference detection.
"""

from __future__ import annotations

import keyword
import re
from re import Pattern

from .math_functions import MathFunctions


class DependencyParser:
    """High-performance parser for extracting formula dependencies."""

    def __init__(self) -> None:
        """Initialize the parser with compiled regex patterns."""
        # Compile patterns once for better performance
        self._entity_patterns: list[Pattern[str]] = [
            re.compile(r'entity\(["\']([^"\']+)["\']\)'),  # entity("sensor.name")
            re.compile(r'state\(["\']([^"\']+)["\']\)'),  # state("sensor.name")
            re.compile(r'states\[["\']([^"\']+)["\']\]'),  # states["sensor.name"]
        ]

        # Pattern for states.domain.entity format
        self._states_pattern = re.compile(r"states\.([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)")

        # Pattern for direct entity ID references (domain.entity_name)
        self._direct_entity_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)\b")

        # Pattern for variable names (after entity IDs are extracted)
        self._variable_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")

        # Cache excluded terms to avoid repeated lookups
        self._excluded_terms = self._build_excluded_terms()

    def extract_dependencies(self, formula: str) -> set[str]:
        """Extract all dependencies from a formula string.

        Args:
            formula: Formula string to parse

        Returns:
            Set of dependency names (entity IDs and variables)
        """
        dependencies = set()

        # Extract entity references from function calls
        for pattern in self._entity_patterns:
            dependencies.update(pattern.findall(formula))

        # Extract states.domain.entity references
        dependencies.update(self._states_pattern.findall(formula))

        # Extract direct entity ID references (domain.entity_name)
        dependencies.update(self._direct_entity_pattern.findall(formula))

        # Extract variable names (exclude keywords, functions, and entity IDs)
        all_entity_ids = self.extract_entity_references(formula)

        # Create a set of all parts of entity IDs to exclude
        entity_id_parts = set()
        for entity_id in all_entity_ids:
            entity_id_parts.update(entity_id.split("."))

        variable_matches = self._variable_pattern.findall(formula)
        for var in variable_matches:
            if var not in self._excluded_terms and not keyword.iskeyword(var) and var not in all_entity_ids and var not in entity_id_parts and "." not in var:  # Skip parts of entity IDs  # Skip parts of entity IDs
                dependencies.add(var)

        return dependencies

    def extract_entity_references(self, formula: str) -> set[str]:
        """Extract only explicit entity references (not variables).

        Args:
            formula: Formula string to parse

        Returns:
            Set of entity IDs referenced in the formula
        """
        entities = set()

        # Extract from entity() and state() functions
        for pattern in self._entity_patterns:
            entities.update(pattern.findall(formula))

        # Extract from states.domain.entity format
        entities.update(self._states_pattern.findall(formula))

        # Extract direct entity ID references (domain.entity_name)
        entities.update(self._direct_entity_pattern.findall(formula))

        return entities

    def extract_variables(self, formula: str) -> set[str]:
        """Extract variable names (excluding entity references).

        Args:
            formula: Formula string to parse

        Returns:
            Set of variable names used in the formula
        """
        # Get all entities first
        entities = self.extract_entity_references(formula)

        # Create a set of all parts of entity IDs to exclude
        entity_id_parts = set()
        for entity_id in entities:
            entity_id_parts.update(entity_id.split("."))

        # Get all potential variables
        variables = set()
        variable_matches = self._variable_pattern.findall(formula)

        for var in variable_matches:
            if var not in self._excluded_terms and not keyword.iskeyword(var) and var not in entities and var not in entity_id_parts and "." not in var:  # Exclude parts of entity IDs  # Skip dotted references
                variables.add(var)

        return variables

    def validate_formula_syntax(self, formula: str) -> list[str]:
        """Validate basic formula syntax.

        Args:
            formula: Formula string to validate

        Returns:
            List of syntax error messages
        """
        errors = []

        # Check for balanced parentheses
        if formula.count("(") != formula.count(")"):
            errors.append("Unbalanced parentheses")

        # Check for balanced brackets
        if formula.count("[") != formula.count("]"):
            errors.append("Unbalanced brackets")

        # Check for balanced quotes
        single_quotes = formula.count("'")
        double_quotes = formula.count('"')

        if single_quotes % 2 != 0:
            errors.append("Unbalanced single quotes")

        if double_quotes % 2 != 0:
            errors.append("Unbalanced double quotes")

        # Check for empty formula
        if not formula.strip():
            errors.append("Formula cannot be empty")

        # Check for obvious syntax issues
        if formula.strip().endswith((".", ",", "+", "-", "*", "/", "=")):
            errors.append("Formula ends with incomplete operator")

        return errors

    def has_entity_references(self, formula: str) -> bool:
        """Check if formula contains any entity references.

        Args:
            formula: Formula string to check

        Returns:
            True if formula contains entity references
        """
        # Quick check using any() for early exit
        for pattern in self._entity_patterns:
            if pattern.search(formula):
                return True

        # Check states.domain.entity format
        if self._states_pattern.search(formula):
            return True

        # Check direct entity ID references
        return bool(self._direct_entity_pattern.search(formula))

    def _build_excluded_terms(self) -> set[str]:
        """Build set of terms to exclude from variable extraction.

        Returns:
            Set of excluded terms (keywords, functions, operators)
        """
        excluded = {
            # Python keywords
            "if",
            "else",
            "and",
            "or",
            "not",
            "in",
            "is",
            "True",
            "False",
            "None",
            # Common operators and literals
            "def",
            "class",
            "import",
            "from",
            "as",
            # Built-in types
            "str",
            "int",
            "float",
            "bool",
            "list",
            "dict",
            "set",
            "tuple",
            # Mathematical constants that might appear
            "pi",
            "e",
        }

        # Add all mathematical function names
        excluded.update(MathFunctions.get_function_names())

        return excluded
