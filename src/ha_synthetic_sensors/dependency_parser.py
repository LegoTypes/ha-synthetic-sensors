"""Enhanced dependency parser for synthetic sensor formulas.

This module provides robust parsing of entity dependencies from formulas,
including support for:
- Static entity references and variables
- Dynamic query patterns (regex, tags, device_class, etc.)
- Dot notation attribute access
- Complex aggregation functions
"""

from __future__ import annotations

from dataclasses import dataclass, field
import keyword
import logging
import re
from re import Pattern
from typing import ClassVar

from .math_functions import MathFunctions

_LOGGER = logging.getLogger(__name__)


@dataclass
class DynamicQuery:
    """Represents a dynamic query that needs runtime resolution."""

    query_type: str  # 'regex', 'tags', 'device_class', 'area', 'attribute', 'state'
    pattern: str  # The actual query pattern
    function: str  # The aggregation function (sum, avg, count, etc.)


@dataclass
class ParsedDependencies:
    """Result of dependency parsing."""

    static_dependencies: set[str] = field(default_factory=set)
    dynamic_queries: list[DynamicQuery] = field(default_factory=list)
    dot_notation_refs: set[str] = field(default_factory=set)  # entity.attribute references


class DependencyParser:
    """Enhanced parser for extracting dependencies from synthetic sensor formulas."""

    # Pattern for aggregation functions with query syntax
    AGGREGATION_PATTERN = re.compile(
        r"\b(sum|avg|count|min|max|std|var)\s*\(\s*"
        r"(?:"
        r'(?P<query_quoted>["\'])(?P<query_content_quoted>[^"\']+)(?P=query_quoted)|'  # Quoted queries
        r"(?P<query_content_unquoted>[^)]+)"  # Unquoted queries
        r")\s*\)",
        re.IGNORECASE,
    )

    # Pattern for direct entity references (sensor.entity_name format)
    ENTITY_PATTERN = re.compile(r"\b((?:sensor|binary_sensor|input_number|input_boolean|switch|light|climate|cover|fan|lock|alarm_control_panel|vacuum|media_player|camera|weather|device_tracker|person|zone|automation|script|scene|group|timer|counter|sun)\.[a-zA-Z0-9_.]+)", re.IGNORECASE)

    # Pattern for dot notation attribute access - more specific to avoid conflicts with entity_ids
    DOT_NOTATION_PATTERN = re.compile(r"\b(?!(?:sensor|binary_sensor|input_number|input_boolean|switch|light|climate|cover|fan|lock|alarm_control_panel|vacuum|media_player|camera|weather|device_tracker|person|zone|automation|script|scene|group|timer|counter|sun)\.)([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\.(attributes\.)?([a-zA-Z0-9_]+)\b")

    # Pattern for variable references (simple identifiers that aren't keywords)
    VARIABLE_PATTERN = re.compile(r"\b(?!(?:if|else|and|or|not|in|is|sum|avg|count|min|max|std|var|abs|round|floor|ceil|sqrt|sin|cos|tan|log|exp|pow|state)\b)[a-zA-Z_][a-zA-Z0-9_]*\b")

    # Query type patterns
    QUERY_PATTERNS: ClassVar[dict[str, re.Pattern[str]]] = {
        "regex": re.compile(r"^regex:\s*(.+)$"),
        "tags": re.compile(r"^tags:\s*(.+)$"),
        "device_class": re.compile(r"^device_class:\s*(.+)$"),
        "area": re.compile(r"^area:\s*(.+)$"),
        "attribute": re.compile(r"^attribute:\s*(.+)$"),
        "state": re.compile(r"^state:\s*(.+)$"),
    }

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
        self._direct_entity_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_.]*)\b")

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

    def extract_static_dependencies(self, formula: str, variables: dict[str, str]) -> set[str]:
        """Extract static entity dependencies from formula and variables.

        Args:
            formula: The formula string to parse
            variables: Variable name to entity_id mappings

        Returns:
            Set of entity_ids that are static dependencies
        """
        dependencies: set[str] = set()

        # Add all variable entity_ids
        dependencies.update(variables.values())

        # Extract direct entity references (sensor.something, etc.)
        entity_matches = self.ENTITY_PATTERN.findall(formula)
        dependencies.update(entity_matches)

        # Also use the direct entity pattern for full entity IDs
        full_entity_matches = self._direct_entity_pattern.findall(formula)
        dependencies.update(full_entity_matches)

        # Extract dot notation references and convert to entity_ids
        dot_matches = self.DOT_NOTATION_PATTERN.findall(formula)
        for match in dot_matches:
            entity_part = match[0]

            # Check if this is a variable reference
            if entity_part in variables:
                dependencies.add(variables[entity_part])
            # Check if this looks like an entity_id
            elif "." in entity_part and any(entity_part.startswith(domain + ".") for domain in ["sensor", "binary_sensor", "input_number", "input_boolean", "switch", "light", "climate", "cover", "fan", "lock", "alarm_control_panel"]):
                dependencies.add(entity_part)

        return dependencies

    def extract_dynamic_queries(self, formula: str) -> list[DynamicQuery]:
        """Extract dynamic query patterns from formula.

        Args:
            formula: The formula string to parse

        Returns:
            List of DynamicQuery objects representing runtime queries
        """
        queries = []

        # Find all aggregation function calls
        for match in self.AGGREGATION_PATTERN.finditer(formula):
            function_name = match.group(1).lower()

            # Get the query content (either quoted or unquoted)
            query_content = match.group("query_content_quoted") or match.group("query_content_unquoted")

            if query_content:
                query_content = query_content.strip()

                # Check if this matches any of our query patterns
                for query_type, pattern in self.QUERY_PATTERNS.items():
                    type_match = pattern.match(query_content)
                    if type_match:
                        # Normalize spaces in pattern for consistent replacement later
                        # Store pattern with normalized format (no space after colon)
                        normalized_pattern = type_match.group(1).strip()
                        queries.append(DynamicQuery(query_type=query_type, pattern=normalized_pattern, function=function_name))
                        break

        return queries

    def extract_variable_references(self, formula: str, variables: dict[str, str]) -> set[str]:
        """Extract variable names referenced in the formula.

        Args:
            formula: The formula string to parse
            variables: Available variable definitions

        Returns:
            Set of variable names actually used in the formula
        """
        used_variables = set()

        # Find all potential variable references
        var_matches = self.VARIABLE_PATTERN.findall(formula)

        for var_name in var_matches:
            if var_name in variables:
                used_variables.add(var_name)

        return used_variables

    def parse_formula_dependencies(self, formula: str, variables: dict[str, str]) -> ParsedDependencies:
        """Parse all types of dependencies from a formula.

        Args:
            formula: The formula string to parse
            variables: Variable name to entity_id mappings

        Returns:
            ParsedDependencies object with all dependency types
        """
        return ParsedDependencies(static_dependencies=self.extract_static_dependencies(formula, variables), dynamic_queries=self.extract_dynamic_queries(formula), dot_notation_refs=self._extract_dot_notation_refs(formula))

    def _extract_dot_notation_refs(self, formula: str) -> set[str]:
        """Extract dot notation references for special handling."""
        refs = set()

        for match in self.DOT_NOTATION_PATTERN.finditer(formula):
            entity_part = match.group(1)
            attribute_part = match.group(3)
            full_ref = f"{entity_part}.{attribute_part}"
            refs.add(full_ref)

        return refs
