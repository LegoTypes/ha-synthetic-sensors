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
from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.core import HomeAssistant

from .boolean_states import BooleanStates
from .constants_formula import ARITHMETIC_OPERATORS, FORMULA_RESERVED_WORDS
from .formula_parsing.variable_extractor import ExtractionContext, extract_variables
from .math_functions import MathFunctions
from .regex_helper import (
    create_entity_pattern_for_domains,
    create_query_type_patterns,
    extract_direct_entity_references,
    extract_entity_function_references,
    extract_states_dot_notation_entities,
    get_direct_entity_pattern,
    get_entity_function_patterns,
    get_no_match_pattern,
    get_states_dot_notation_pattern,
    get_variable_references_pattern,
    regex_helper,
)
from .shared_constants import BOOLEAN_LITERALS, BUILTIN_TYPES, METADATA_FUNCTIONS, PYTHON_KEYWORDS, get_ha_domains

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

    # Use centralized aggregation pattern from regex helper
    @property
    def AGGREGATION_PATTERN(self) -> re.Pattern[str]:
        """Get the aggregation pattern from centralized regex helper."""
        return regex_helper.create_aggregation_pattern_with_exclusions()

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

        # No fallback - domains should come from HA lazy loading or proper test setup
        # Return empty string to disable entity pattern matching when domains aren't available
        return ""

    @property
    def ENTITY_PATTERN(self) -> re.Pattern[str]:
        """Get the compiled entity pattern."""
        domains_pattern = self._entity_domains_pattern
        if not domains_pattern:
            # Return a pattern that matches nothing when no domains are available

            return get_no_match_pattern()
        return create_entity_pattern_for_domains(domains_pattern.split("|"))

    # Pattern for dot notation attribute access - more specific to avoid conflicts with entity_ids
    @property
    def DOT_NOTATION_PATTERN(self) -> re.Pattern[str]:
        """Get the compiled dot notation pattern."""
        return regex_helper.create_dot_notation_pattern_with_domain_exclusion(self._entity_domains_pattern)

    # Pattern for variable references (simple identifiers that aren't keywords)
    @staticmethod
    def _build_variable_pattern() -> re.Pattern[str]:
        """Build the variable pattern excluding keywords and built-in functions."""
        # Use centralized constants instead of hardcoded lists

        # All reserved words are now centralized in constants
        excluded_keywords = list(FORMULA_RESERVED_WORDS)

        # Use centralized pattern builder
        return regex_helper.build_variable_exclusion_pattern(excluded_keywords)

    VARIABLE_PATTERN = _build_variable_pattern()

    # Query type patterns - use centralized method from regex helper

    QUERY_PATTERNS: ClassVar[dict[str, re.Pattern[str]]] = create_query_type_patterns()

    def __init__(self, hass: HomeAssistant | None = None) -> None:
        """Initialize the parser with compiled regex patterns."""
        self.hass = hass

        # Use domain-focused methods from regex helper - no patterns in implementation

        # Get compiled patterns from centralized regex helper
        self._entity_patterns: list[re.Pattern[str]] = get_entity_function_patterns()
        self._states_pattern = get_states_dot_notation_pattern()
        self.direct_entity_pattern = get_direct_entity_pattern()
        self._variable_pattern = get_variable_references_pattern()

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
        if "[" in formula and "]" in formula and not any(op in formula for op in ARITHMETIC_OPERATORS):
            # This is a literal expression with brackets (e.g., "tabs[16]", "tabs [22]")
            return True

        # If it's a simple identifier with no operators, it's a variable
        if formula.strip().replace("_", "").replace("-", "").isalnum():
            return False

        # If it contains arithmetic operators (but not brackets), it's a formula that should extract variables
        if any(op in formula for op in ARITHMETIC_OPERATORS):
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
        dependencies.update(regex_helper.extract_entity_function_references(formula))

        # Extract states.domain.entity references
        dependencies.update(regex_helper.extract_states_dot_notation_entities(formula))

        # Extract direct entity ID references (domain.entity_name)
        dependencies.update(regex_helper.extract_direct_entity_references(formula))

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

        # : Use centralized regex helper for string literal extraction
        # Extract variables while excluding string literals (both in metadata and general usage)
        string_ranges = regex_helper.find_string_literals(formula)

        # Python keywords to exclude - use shared constant
        python_keywords = PYTHON_KEYWORDS

        variable_matches = regex_helper.extract_variables_from_formula(formula, context="dependency_parsing")
        for var in variable_matches:
            # Skip if this variable is inside a string literal
            var_positions = self._find_variable_positions(formula, var)
            is_in_string = self._check_if_variable_in_string(formula, var_positions, string_ranges)

            # Skip Python keywords
            is_keyword = var in python_keywords

            # Skip numeric literals (integers and floats)
            is_numeric = False
            try:
                float(var)
                is_numeric = True
            except ValueError:
                pass

            # Skip entity IDs (format: domain.entity_name)
            is_entity_id = (
                "." in var
                and len(var.split(".")) == 2
                and all(part.replace("_", "").replace("-", "").isalnum() for part in var.split("."))
            )

            if is_in_string or is_keyword or is_numeric or is_entity_id:
                continue
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
        # Use domain-focused extraction methods from regex helper

        # Check if it's a known domain - domains must be available
        ha_domains = get_ha_domains(self.hass)
        if ha_domains is None:
            raise RuntimeError("Home Assistant domains are not available - entity registry may not be initialized")
        known_domains = set(ha_domains) | {"input_text", "input_select", "input_datetime"}

        entities = set()

        # Extract from entity() and state() functions - these are always valid
        entities.update(extract_entity_function_references(formula))

        # Extract states.domain.entity references - these are always valid
        entities.update(extract_states_dot_notation_entities(formula))

        # Extract direct entity ID references and validate domains
        potential_entities = extract_direct_entity_references(formula)
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
        for func_match in regex_helper.extract_aggregation_function_matches(formula):
            func_args = func_match.group(2)
            # Extract all quoted strings from the function arguments
            quoted_strings = regex_helper.extract_quoted_strings(func_args)

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
                        pattern_variables = regex_helper.extract_variables_from_pattern_value(pattern_value)
                        variables.update(pattern_variables)
                        break

        # Extract variables from dot notation first to identify attribute parts to exclude
        dot_notation_attributes = set()
        dot_matches = regex_helper.extract_dot_notation_matches(formula)
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

        # Add Home Assistant boolean state constants to prevent them from being treated as dependencies
        try:
            boolean_names = BooleanStates.get_all_boolean_names()
            excluded.update(boolean_names.keys())
        except Exception as e:
            _LOGGER.debug("Could not load boolean state constants for exclusion: %s", e)
            # Add common boolean states as fallback
            excluded.update({"on", "off", "true", "false", "yes", "no"})

        # Mathematical constants that might appear
        excluded.update({"pi", "e"})

        # Add all mathematical function names
        excluded.update(MathFunctions.get_function_names())

        # Add metadata functions
        excluded.update(METADATA_FUNCTIONS)

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

        # Extract dependencies from formula using our fixed method
        formula_dependencies = self.extract_dependencies(formula)

        # For each dependency found in the formula, check if it's a variable name
        # If so, resolve it to its entity ID; otherwise keep it as is
        for dep in formula_dependencies:
            if dep in variables:
                # This is a variable name, resolve to its entity ID
                var_value = variables[dep]
                if isinstance(var_value, str):
                    dependencies.add(var_value)
                elif hasattr(var_value, "dependencies"):
                    dependencies.update(getattr(var_value, "dependencies", set()))
            else:
                # This is already an entity ID or other dependency
                dependencies.add(dep)

        # Extract dot notation references and convert to entity_ids
        dot_matches = regex_helper.extract_dot_notation_matches(formula)
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
        for match in regex_helper.extract_aggregation_function_matches_with_exclusions(formula):
            function_name = match.group(1).lower()

            # Get the query content (either quoted or unquoted)
            # Fix: Use get() method to safely access named groups that may not exist
            query_content = match.groupdict().get("query_content_quoted") or match.groupdict().get("query_content_unquoted")

            # Get exclusions (either quoted or unquoted)
            exclusions_raw = match.groupdict().get("exclusions") or match.groupdict().get("exclusions_unquoted")
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
        # : Use centralized regex helper for exclusion parsing
        main_pattern, exclusions_list = regex_helper.find_exclusions_in_pattern(pattern)
        if not exclusions_list:
            return pattern, []

        # Convert list back to the format expected by the rest of the method
        exclusions_part = " ".join(f"!{exc}" for exc in exclusions_list)

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

        # Use centralized exclusion pattern from regex helper
        exclusion_pattern = regex_helper.create_exclusion_pattern()

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
        var_matches = regex_helper.extract_variables_from_formula(formula, context="variable_references")

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

        for match in regex_helper.extract_dot_notation_matches(formula):
            entity_part = match[0]
            attribute_part = match[2]
            full_ref = f"{entity_part}.{attribute_part}"
            refs.add(full_ref)

        return refs

    def _find_variable_positions(self, formula: str, var: str) -> list[int]:
        """Find all positions where a variable appears in the formula."""
        var_positions = []
        start_pos = 0
        while True:
            pos = formula.find(var, start_pos)
            if pos == -1:
                break
            # Check if this is a whole word match (not part of another identifier)
            is_start_of_word = pos == 0 or (not formula[pos - 1].isalnum() and formula[pos - 1] != "_")
            is_end_of_word = pos + len(var) >= len(formula) or (
                not formula[pos + len(var)].isalnum() and formula[pos + len(var)] != "_"
            )
            if is_start_of_word and is_end_of_word:
                var_positions.append(pos)
            start_pos = pos + 1
        return var_positions

    def _check_if_variable_in_string(self, formula: str, var_positions: list[int], string_ranges: list[Any]) -> bool:
        """Check if any occurrence of a variable is inside a string literal."""
        for var_pos in var_positions:
            for string_range in string_ranges:
                if string_range.start <= var_pos < string_range.end and not self._is_collection_pattern_string(
                    formula, string_range
                ):
                    return True
        return False

    def _is_collection_pattern_string(self, formula: str, string_range: Any) -> bool:
        """Check if a string is part of a collection function call."""
        for func_match in regex_helper.extract_aggregation_function_matches(formula):
            func_start = func_match.start()
            func_end = func_match.end()
            # If the string is inside an aggregation function, it's a collection pattern
            if func_start < string_range.start and string_range.end < func_end:
                return True
        return False
