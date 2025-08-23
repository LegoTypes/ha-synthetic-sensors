"""Enhanced dependency parser for synthetic sensor formulas.

This module provides robust parsing of entity dependencies from formulas,
including support for:
- Static entity references and variables
- Dynamic query patterns (regex, label, device_class, etc.)
- Dot notation attribute access
- Complex aggregation functions
"""

from __future__ import annotations

from dataclasses import dataclass, field
import keyword
import logging
import re
from re import Pattern
from typing import TYPE_CHECKING, ClassVar

from homeassistant.core import HomeAssistant

from .formula_parsing.variable_extractor import ExtractionContext, extract_variables
from .math_functions import MathFunctions
from .shared_constants import (
    BOOLEAN_LITERALS,
    BUILTIN_TYPES,
    DATETIME_FUNCTIONS,
    METADATA_FUNCTIONS,
    PYTHON_KEYWORDS,
    get_ha_domains,
)

if TYPE_CHECKING:
    from .config_models import ComputedVariable


_LOGGER = logging.getLogger(__name__)


@dataclass
class DynamicQuery:
    """Represents a dynamic query that needs runtime resolution."""

    query_type: str  # 'regex', 'label', 'device_class', 'area', 'attribute', 'state'
    pattern: str  # The actual query pattern
    function: str  # The aggregation function (sum, avg, count, etc.)
    exclusions: list[str] = field(default_factory=list)  # Patterns to exclude from results


@dataclass
class ParsedDependencies:
    """Result of dependency parsing."""

    static_dependencies: set[str] = field(default_factory=set)
    dynamic_queries: list[DynamicQuery] = field(default_factory=list)
    dot_notation_refs: set[str] = field(default_factory=set)  # entity.attribute references


class DependencyParser:
    """Enhanced parser for extracting dependencies from synthetic sensor formulas."""

    # Pattern for aggregation functions with query syntax and optional exclusions
    AGGREGATION_PATTERN = re.compile(
        r"\b(sum|avg|count|min|max|std|var)\s*\(\s*"
        r"(?:"
        r'(?P<query_quoted>["\'])(?P<query_content_quoted>[^"\']+)(?P=query_quoted)'  # Quoted main query
        r'(?:\s*,\s*(?P<exclusions>(?:!\s*["\'][^"\']+["\'](?:\s*,\s*)?)+))?|'  # Optional exclusions with !
        r"(?P<query_content_unquoted>[^),]+)"  # Unquoted main query
        r"(?:\s*,\s*(?P<exclusions_unquoted>(?:!\s*[^,)]+(?:\s*,\s*)?)+))?"  # Optional exclusions for unquoted
        r")\s*\)",
        re.IGNORECASE,
    )

    # Pattern for direct entity references (sensor.entity_name format)
    # Lazy-loaded to avoid import-time issues with HA constants
    @property
    def _entity_domains_pattern(self) -> str:
        """Get the entity domains pattern for regex compilation."""
        if self.hass is not None:
            try:
                domains = get_ha_domains(self.hass)
                if domains:
                    return "|".join(sorted(domains))
            except (ImportError, AttributeError, TypeError):
                # These are expected when HA is not fully initialized
                pass

        # Fallback to basic domains when hass is not available or fails
        return "sensor|binary_sensor|switch|light|climate|input_number|input_text|span|device_tracker|cover"

    @property
    def ENTITY_PATTERN(self) -> re.Pattern[str]:
        """Get the compiled entity pattern."""
        return re.compile(
            rf"\b((?:{self._entity_domains_pattern})\.[a-zA-Z0-9_.]+)",
            re.IGNORECASE,
        )

    # Pattern for dot notation attribute access - more specific to avoid conflicts with entity_ids
    @property
    def DOT_NOTATION_PATTERN(self) -> re.Pattern[str]:
        """Get the compiled dot notation pattern."""
        return re.compile(
            rf"\b(?!(?:{self._entity_domains_pattern})\.)([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\.(attributes\.)?([a-zA-Z0-9_]+)\b"
        )

    # Pattern for variable references (simple identifiers that aren't keywords)
    @staticmethod
    def _build_variable_pattern() -> re.Pattern[str]:
        """Build the variable pattern excluding keywords and built-in functions."""
        excluded_keywords = [
            "if",
            "else",
            "and",
            "or",
            "not",
            "in",
            "is",
            "sum",
            "avg",
            "count",
            "min",
            "max",
            "std",
            "var",
            "abs",
            "round",
            "floor",
            "ceil",
            "sqrt",
            "sin",
            "cos",
            "tan",
            "log",
            "exp",
            "pow",
            "state",
        ]
        # Add datetime functions from shared constants
        excluded_keywords.extend(DATETIME_FUNCTIONS)
        # Add metadata functions from shared constants
        excluded_keywords.extend(METADATA_FUNCTIONS)
        excluded_pattern = "|".join(excluded_keywords)
        return re.compile(rf"\b(?!(?:{excluded_pattern})\b)[a-zA-Z_][a-zA-Z0-9_]*\b")

    VARIABLE_PATTERN = _build_variable_pattern()

    # Query type patterns
    QUERY_PATTERNS: ClassVar[dict[str, re.Pattern[str]]] = {
        "regex": re.compile(r"^regex:\s*(.+)$"),
        "label": re.compile(r"^label:\s*(.+)$"),
        "device_class": re.compile(r"^device_class:\s*(.+)$"),
        "area": re.compile(r"^area:\s*(.+)$"),
        "attribute": re.compile(r"^attribute:\s*(.+)$"),
        "state": re.compile(r"^state:\s*(.+)$"),
    }

    def __init__(self, hass: HomeAssistant | None = None) -> None:
        """Initialize the parser with compiled regex patterns."""
        self.hass = hass

        # Compile patterns once for better performance
        self._entity_patterns: list[Pattern[str]] = [
            re.compile(r'entity\(["\']([^"\']+)["\']\)'),  # entity("sensor.name")
            re.compile(r'state\(["\']([^"\']+)["\']\)'),  # state("sensor.name")
            re.compile(r'states\[["\']([^"\']+)["\']\]'),  # states["sensor.name"]
        ]

        # Pattern for states.domain.entity format
        self._states_pattern = re.compile(r"states\.([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)")

        # Pattern for direct entity ID references (domain.entity_name)
        self.direct_entity_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_.]*)\b")

        # Pattern for variable names (after entity IDs are extracted)
        self._variable_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")

        # Cache excluded terms to avoid repeated lookups
        self._excluded_terms = self._build_excluded_terms()

    def _is_literal_expression(self, formula: str) -> bool:
        """Check if formula looks like a literal expression that shouldn't extract variables.

        Args:
            formula: Formula string to check

        Returns:
            True if formula looks like a literal expression, False otherwise
        """
        # Check for patterns that indicate this is a literal expression
        # Examples: "tabs[16]", "tabs [22]", "tabs [30:32]", "device_name", "custom_value"

        # If it contains brackets, check if it's a literal expression
        if "[" in formula and "]" in formula:
            # Check if it contains arithmetic operators that would make it a formula
            arithmetic_operators = ["+", "-", "*", "/", "(", ")"]
            if not any(op in formula for op in arithmetic_operators):
                # This is a literal expression with brackets (e.g., "tabs[16]", "tabs [22]")
                return True

        # If it's a simple identifier with no operators, it's a variable
        if formula.strip().replace("_", "").replace("-", "").isalnum():
            return False

        # If it contains arithmetic operators (but not brackets), it's a formula that should extract variables
        if any(op in formula for op in ["+", "-", "*", "/", "(", ")"]):
            return False

        # If it contains brackets but no arithmetic, it's a literal
        return bool("[" in formula or "]" in formula)

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
        dependencies.update(self.direct_entity_pattern.findall(formula))

        # Extract variable names (exclude keywords, functions, and entity IDs)
        all_entity_ids = self.extract_entity_references(formula)

        # Create a set of all parts of entity IDs to exclude
        entity_id_parts = set()
        for entity_id in all_entity_ids:
            entity_id_parts.update(entity_id.split("."))

        # Check if formula looks like a literal expression (e.g., "tabs[16]")
        # If it does, don't extract variables from it
        if self._is_literal_expression(formula):
            return dependencies

        variable_matches = self._variable_pattern.findall(formula)
        for var in variable_matches:
            if (
                var not in self._excluded_terms
                and not keyword.iskeyword(var)
                and var not in all_entity_ids
                and var not in entity_id_parts
                and "." not in var
            ):  # Skip parts of entity IDs  # Skip parts of entity IDs
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
        # But exclude dot notation patterns that are likely variables
        potential_entities = self.direct_entity_pattern.findall(formula)

        # Check if it's a known domain
        known_domains = get_ha_domains(self.hass) | {"input_text", "input_select", "input_datetime"}

        for entity_id in potential_entities:
            # Only add if it starts with a known domain
            domain = entity_id.split(".")[0] if "." in entity_id else ""
            if domain in known_domains:
                entities.add(entity_id)

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

        # Get all potential variables using centralized extractor for general extraction
        # Use centralized extractor but still apply dependency parser's filtering logic
        variables = set()
        centralized_variables = extract_variables(formula, context=ExtractionContext.DEPENDENCY_PARSING)
        variable_matches = list(centralized_variables)

        # SPECIAL CASE: Extract variables from within collection patterns
        # This handles formulas like sum("device_class:device_type") or avg("area:target_area", "device_class:device_type")

        # Find aggregation functions and extract all quoted strings within them
        aggregation_func_pattern = re.compile(r"\b(sum|avg|count|min|max|std|var)\s*\(([^)]+)\)", re.IGNORECASE)
        for func_match in aggregation_func_pattern.finditer(formula):
            func_args = func_match.group(2)
            # Extract all quoted strings from the function arguments
            quoted_strings = re.findall(r'["\'](.*?)["\']', func_args)

            for quoted_content in quoted_strings:
                # Check if this is a collection pattern that might contain variables
                for query_type, pattern in self.QUERY_PATTERNS.items():
                    pattern_match = pattern.match(quoted_content.strip())
                    if pattern_match:
                        # Extract variables from the pattern value
                        pattern_value = pattern_match.group(1)
                        # Add both the query type and any variables in the pattern value
                        variables.add(query_type)
                        # Extract variables from pattern value (handles device_type in device_class:device_type)
                        pattern_variables = self._variable_pattern.findall(pattern_value)
                        variables.update(pattern_variables)
                        break

        # Extract variables from dot notation first to identify attribute parts to exclude
        dot_notation_attributes = set()
        dot_matches = self.DOT_NOTATION_PATTERN.findall(formula)
        for match in dot_matches:
            entity_part = match[0]  # The part before the dot (e.g., "battery_class")
            attribute_part = match[2]  # The part after the dot (e.g., "battery_level")

            # Add the attribute part to exclusion set
            dot_notation_attributes.add(attribute_part)

            # Check if the entity part could be a variable (not an entity ID)
            if (
                entity_part not in self._excluded_terms
                and not keyword.iskeyword(entity_part)
                and entity_part not in entities
                and entity_part not in entity_id_parts
                and not any(entity_part.startswith(domain + ".") for domain in get_ha_domains(self.hass))
            ):
                variables.add(entity_part)

        # Now extract standalone variables, excluding attribute parts from dot notation
        for var in variable_matches:
            if self._is_valid_variable(var, entities, entity_id_parts, dot_notation_attributes):
                variables.add(var)

        return variables

    def _is_valid_variable(
        self,
        var: str,
        entities: set[str],
        entity_id_parts: set[str],
        dot_notation_attributes: set[str],
    ) -> bool:
        """Check if a variable name is valid for extraction.

        Args:
            var: Variable name to check
            entities: Set of known entity names
            entity_id_parts: Set of entity ID parts to exclude
            dot_notation_attributes: Set of dot notation attributes to exclude

        Returns:
            True if the variable is valid for extraction
        """
        return (
            var not in self._excluded_terms
            and not keyword.iskeyword(var)
            and var not in entities
            and var not in entity_id_parts
            and var not in dot_notation_attributes
            and "." not in var
        )

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
        return bool(self.direct_entity_pattern.search(formula))

    def _build_excluded_terms(self) -> set[str]:
        """Build set of terms to exclude from variable extraction.

        Returns:
            Set of excluded terms (keywords, functions, operators)
        """
        excluded: set[str] = set()

        # Add Python keywords, built-in types, and boolean literals from shared constants
        excluded.update(PYTHON_KEYWORDS)
        excluded.update(BUILTIN_TYPES)
        excluded.update(BOOLEAN_LITERALS)

        # Mathematical constants that might appear
        excluded.update({"pi", "e"})

        # Add all mathematical function names
        excluded.update(MathFunctions.get_function_names())

        return excluded

    def extract_static_dependencies(self, formula: str, variables: dict[str, str | int | float | ComputedVariable]) -> set[str]:
        """Extract static entity dependencies from formula and variables.

        Args:
            formula: The formula string to parse
            variables: Variable name to entity_id mappings, numeric literals, or computed variables

        Returns:
            Set of entity_ids that are static dependencies
        """
        dependencies: set[str] = set()

        # Add dependencies from variables
        for value in variables.values():
            if isinstance(value, str):
                # Simple entity_id mapping
                dependencies.add(value)
            elif hasattr(value, "dependencies") and hasattr(value, "formula"):
                # ComputedVariable object - add its dependencies
                # Note: ComputedVariable dependencies are resolved during parsing
                dependencies.update(getattr(value, "dependencies", set()))

        # Extract direct entity references (sensor.something, etc.)
        entity_matches = self.ENTITY_PATTERN.findall(formula)
        dependencies.update(entity_matches)

        # Also use the direct entity pattern for full entity IDs
        full_entity_matches = self.direct_entity_pattern.findall(formula)
        dependencies.update(full_entity_matches)

        # Extract dot notation references and convert to entity_ids
        dot_matches = self.DOT_NOTATION_PATTERN.findall(formula)
        for match in dot_matches:
            entity_part = match[0]

            # Check if this is a variable reference
            if entity_part in variables and isinstance(variables[entity_part], str):
                dependencies.add(str(variables[entity_part]))  # Cast to ensure type safety
            # Check if this looks like an entity_id
            elif "." in entity_part and any(entity_part.startswith(domain + ".") for domain in get_ha_domains(self.hass)):
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

            # Get exclusions (either quoted or unquoted)
            exclusions_raw = match.group("exclusions") or match.group("exclusions_unquoted")
            exclusions = self._parse_exclusions(exclusions_raw) if exclusions_raw else []

            if query_content:
                query_content = query_content.strip()

                # Check if this matches any of our query patterns
                for query_type, pattern in self.QUERY_PATTERNS.items():
                    type_match = pattern.match(query_content)
                    if type_match:
                        # Normalize spaces in pattern for consistent replacement later
                        # Store pattern with normalized format (no space after colon)
                        raw_pattern = type_match.group(1).strip()

                        # Check for space-separated exclusions within the pattern (e.g., "door|window !state:off")
                        pattern_parts, inline_exclusions = self._extract_inline_exclusions(raw_pattern)

                        # Normalize repeated query type prefixes (e.g., device_class:door|device_class:window -> door|window)
                        normalized_pattern = self._normalize_repeated_prefixes(query_type, pattern_parts)

                        # Combine exclusions from both sources
                        all_exclusions = exclusions + inline_exclusions

                        queries.append(
                            DynamicQuery(
                                query_type=query_type,
                                pattern=normalized_pattern,
                                function=function_name,
                                exclusions=all_exclusions,
                            )
                        )
                        break  # Only match the first pattern type

        return queries

    def _normalize_repeated_prefixes(self, query_type: str, pattern: str) -> str:
        """Normalize patterns with repeated query type prefixes.

        For example:
        - device_class:door|device_class:window|device_class:motion -> door|window|motion
        - area:kitchen|area:living_room -> kitchen|living_room
        - label:tag1|label:tag2 -> tag1|tag2

        Args:
            query_type: The query type (device_class, area, label, etc.)
            pattern: The raw pattern that may contain repeated prefixes

        Returns:
            Normalized pattern with repeated prefixes removed
        """
        if "|" not in pattern:
            # Single item, no normalization needed
            return pattern

        # Split by pipe and process each part
        parts = pattern.split("|")
        normalized_parts = []

        for part in parts:
            part = part.strip()
            # Check if this part has the query type prefix
            prefix = f"{query_type}:"
            if part.startswith(prefix):
                # Remove the prefix, keeping only the value
                normalized_part = part[len(prefix) :].strip()
                normalized_parts.append(normalized_part)
            else:
                # No prefix, keep as is
                normalized_parts.append(part)

        return "|".join(normalized_parts)

    def _extract_inline_exclusions(self, pattern: str) -> tuple[str, list[str]]:
        """Extract inline exclusions from a pattern string.

        Handles patterns like:
        - "door|window|motion !state:unavailable|unknown|off"
        - "door|window|motion !(state:unavailable|unknown|off)"

        Args:
            pattern: The raw pattern that may contain inline exclusions

        Returns:
            Tuple of (clean_pattern, exclusions_list)
        """
        # Look for space followed by ! to identify start of exclusions
        # Handle both parenthesized and non-parenthesized exclusions
        exclusion_match = re.search(r"\s+!\s*(\([^)]+\)|.+)$", pattern)
        if not exclusion_match:
            # No inline exclusions found
            return pattern, []

        # Split the pattern into main part and exclusions part
        main_pattern = pattern[: exclusion_match.start()].strip()
        exclusions_part = exclusion_match.group(1).strip()

        # Handle parentheses - remove them if present
        if exclusions_part.startswith("(") and exclusions_part.endswith(")"):
            exclusions_part = exclusions_part[1:-1].strip()

        # Parse the exclusions part - it can be like "state:unavailable|unknown|off"
        exclusions = []

        # Check if it's a typed exclusion (like state:value1|value2|value3)
        if ":" in exclusions_part:
            # Split by spaces to handle multiple exclusion types
            exclusion_groups = exclusions_part.split()
            for group in exclusion_groups:
                if ":" in group:
                    # This is a typed exclusion like "state:unavailable|unknown|off"
                    exclusion_type, values = group.split(":", 1)
                    # Split values by | and create individual exclusions
                    for value in values.split("|"):
                        exclusions.append(f"{exclusion_type}:{value.strip()}")
                else:
                    # This is a simple exclusion
                    exclusions.append(group.strip())
        else:
            # Simple exclusions separated by |
            for exclusion in exclusions_part.split("|"):
                exclusions.append(exclusion.strip())

        return main_pattern, exclusions

    def _parse_exclusions(self, exclusions_raw: str) -> list[str]:
        """Parse exclusion patterns from the raw exclusions string.

        Args:
            exclusions_raw: Raw exclusions string like "!'area:kitchen', !'sensor1'"

        Returns:
            List of exclusion patterns without the ! prefix
        """
        exclusions: list[str] = []
        if not exclusions_raw:
            return exclusions

        # Pattern to match individual exclusions: !'pattern' or !pattern
        exclusion_pattern = re.compile(r"!\s*(?:[\"']([^\"']+)[\"']|([^,)]+))")

        for match in exclusion_pattern.finditer(exclusions_raw):
            # Get either quoted or unquoted exclusion
            exclusion = (match.group(1) or match.group(2)).strip()
            if exclusion:
                exclusions.append(exclusion)

        return exclusions

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

    def parse_formula_dependencies(
        self, formula: str, variables: dict[str, str | int | float | ComputedVariable]
    ) -> ParsedDependencies:
        """Parse all types of dependencies from a formula.

        Args:
            formula: The formula string to parse
            variables: Variable name to entity_id mappings (or numeric literals)

        Returns:
            ParsedDependencies object with all dependency types
        """
        return ParsedDependencies(
            static_dependencies=self.extract_static_dependencies(formula, variables),
            dynamic_queries=self.extract_dynamic_queries(formula),
            dot_notation_refs=self._extract_dot_notation_refs(formula),
        )

    def _extract_dot_notation_refs(self, formula: str) -> set[str]:
        """Extract dot notation references for special handling."""
        refs = set()

        for match in self.DOT_NOTATION_PATTERN.finditer(formula):
            entity_part = match.group(1)
            attribute_part = match.group(3)
            full_ref = f"{entity_part}.{attribute_part}"
            refs.add(full_ref)

        return refs
