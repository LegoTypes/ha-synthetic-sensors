"""Centralized regex helper methods for formula parsing and dependency extraction.

This module provides all regex functionality used throughout the synthetic sensors system
in a centralized, testable format. All regex patterns are wrapped in Python methods
that can be easily tested in isolation and provide clear interfaces.

All regex usage should go through this module to ensure:
1. Patterns are centralized and maintainable
2. Methods can be tested in isolation
3. Consistent behavior across all components
4. Easy debugging and modification
5. Clear method signatures and documentation
"""

from collections.abc import Callable
import re
from typing import NamedTuple

from .shared_constants import BOOLEAN_LITERALS, PYTHON_KEYWORDS


class StringRange(NamedTuple):
    """Represents a range in a string."""

    start: int
    end: int


class RegexHelper:
    """Centralized regex helper with method-wrapped patterns."""

    def __init__(self) -> None:
        """Initialize the regex helper with compiled patterns."""
        # Cache compiled patterns for performance
        self._patterns: dict[tuple[str, str, int], re.Pattern[str]] = {}

    def _get_pattern(self, name: str, pattern: str, flags: int = 0) -> re.Pattern[str]:
        """Get a compiled pattern from cache or compile and cache it."""
        key = (name, pattern, flags)
        if key not in self._patterns:
            self._patterns[key] = re.compile(pattern, flags)
        return self._patterns[key]

    def _create_domain_based_entity_pattern(
        self, domains: list[str], include_capture_groups: bool = False, word_boundaries: bool = True
    ) -> re.Pattern[str]:
        """Create a pattern for matching entities from specific domains.

        Consolidates the common pattern creation logic used across multiple methods.

        Args:
            domains: List of domain names
            include_capture_groups: Whether to include capture groups in the pattern
            word_boundaries: Whether to include word boundaries

        Returns:
            Compiled regex pattern
        """
        if not domains:
            return self._get_pattern("no_domains", r"(?!.*)")

        domains_pattern = "|".join(re.escape(domain) for domain in domains)

        if include_capture_groups:
            if word_boundaries:
                pattern_str = rf"\b((?:{domains_pattern}))\.([a-zA-Z0-9_.]+)\b"
            else:
                pattern_str = rf"\b((?:{domains_pattern}))\.([a-zA-Z0-9_.]+)"
        else:
            if word_boundaries:
                pattern_str = rf"\b(?:{domains_pattern})\.[a-zA-Z0-9_.]+\b"
            else:
                pattern_str = rf"\b(?:{domains_pattern})\.[a-zA-Z0-9_.]+)"

        cache_key = f"domain_entity_{hash(tuple(domains))}_{include_capture_groups}_{word_boundaries}"
        return self._get_pattern(cache_key, pattern_str, re.IGNORECASE)

    def find_string_literals(self, text: str) -> list[StringRange]:
        """Find all string literal ranges in text."""
        pattern = self._get_pattern("string_literal", r"['\"]([^'\"]*)['\"]")
        ranges = []
        for match in pattern.finditer(text):
            ranges.append(StringRange(match.start(), match.end()))
        return ranges

    def extract_quoted_strings(self, text: str) -> list[str]:
        """Extract all quoted string contents from text."""
        pattern = self._get_pattern("quoted_string", r'["\'](.*?)["\']')
        return pattern.findall(text)

    def extract_identifiers(self, text: str) -> list[str]:
        """Extract all identifiers from text."""
        pattern = self._get_pattern("identifier", r"\b([a-zA-Z_][a-zA-Z0-9_.]*)\b")
        return pattern.findall(text)

    def extract_simple_identifiers(self, text: str) -> list[str]:
        """Extract simple identifiers (no dots) from text."""
        pattern = self._get_pattern("simple_identifier", r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")
        return pattern.findall(text)

    def extract_basic_entity_ids(self, text: str) -> list[str]:
        """Extract basic entity IDs (domain.entity format) from text."""
        pattern = self._get_pattern("entity_id_basic", r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_.]*)\b")
        return pattern.findall(text)

    def extract_metadata_entities(self, text: str) -> list[str]:
        """Extract entity IDs from metadata function calls."""
        pattern = self._get_pattern("metadata_function", r"metadata\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"][^'\"]+['\"]\s*\)")
        return pattern.findall(text)

    def extract_exclusions(self, exclusions_text: str) -> list[str]:
        """Extract exclusion patterns from exclusions text."""
        pattern = self._get_pattern("exclusion_pattern", r"!\s*(?:[\"']([^\"']+)[\"']|([^,)\s]+))")
        exclusions = []
        for match in pattern.finditer(exclusions_text):
            exclusion = match.group(1) or match.group(2)
            if exclusion:
                exclusions.append(exclusion.strip())
        return exclusions

    def extract_entity_ids_for_domains(self, text: str, domains: list[str]) -> list[str]:
        """Extract entity IDs for specific domains from text."""
        if not domains:
            return []

        # Use consolidated domain-based entity pattern
        pattern = self._create_domain_based_entity_pattern(domains, include_capture_groups=True, word_boundaries=False)
        return pattern.findall(text)

    def extract_variables_excluding_keywords(self, text: str, excluded_keywords: list[str] | None = None) -> list[str]:
        """Extract variables from text excluding specified keywords."""
        if excluded_keywords is None:
            excluded_keywords = []

        if not excluded_keywords:
            return self.extract_simple_identifiers(text)

        excluded_pattern = "|".join(re.escape(keyword) for keyword in excluded_keywords)
        pattern_str = rf"\b(?!(?:{excluded_pattern})\b)[a-zA-Z_][a-zA-Z0-9_]*\b"
        pattern = self._get_pattern(f"variable_excluding_{len(excluded_keywords)}", pattern_str)
        return pattern.findall(text)

    def extract_entity_function_refs(self, text: str) -> list[str]:
        """Extract entity references from entity() function calls."""
        pattern = self._get_pattern("entity_function", r'entity\(["\']([^"\']+)["\']\)')
        return pattern.findall(text)

    def extract_state_function_refs(self, text: str) -> list[str]:
        """Extract entity references from state() function calls."""
        pattern = self._get_pattern("state_function", r'state\(["\']([^"\']+)["\']\)')
        return pattern.findall(text)

    def extract_states_bracket_refs(self, text: str) -> list[str]:
        """Extract entity references from states[] bracket notation."""
        pattern = self._get_pattern("states_bracket", r'states\[["\']([^"\']+)["\']\]')
        return pattern.findall(text)

    def extract_states_dot_refs(self, text: str) -> list[str]:
        """Extract entity references from states.domain.entity notation."""
        pattern = self._get_pattern("states_dot_notation", r"states\.([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)")
        return pattern.findall(text)

    def find_exclusions_in_pattern(self, pattern: str) -> tuple[str, list[str]]:
        """Find and separate exclusions from a pattern string."""
        exclusion_search = self._get_pattern("exclusion_search", r"\s+!\s*(\([^)]+\)|.+)$")
        exclusion_match = exclusion_search.search(pattern)

        if not exclusion_match:
            return pattern, []

        # Split pattern and exclusions
        clean_pattern = pattern[: exclusion_match.start()].strip()
        exclusions_raw = exclusion_match.group(1).strip()

        # Remove outer parentheses if present
        if exclusions_raw.startswith("(") and exclusions_raw.endswith(")"):
            exclusions_raw = exclusions_raw[1:-1].strip()

        # Extract all exclusions from the raw text
        exclusions = self.extract_exclusions(exclusions_raw)
        return clean_pattern, exclusions

    # =========================================================================
    # COMMON PATTERN METHODS (HIGH REUSE POTENTIAL)
    # =========================================================================

    def extract_variable_references(self, text: str) -> list[str]:
        """Extract variable references (no dots, word boundaries).

        This is the most common pattern in the codebase: r"\\b([a-zA-Z_][a-zA-Z0-9_]*)\\b"
        Used in 15+ files for variable extraction.
        """
        pattern = self._get_pattern("variable_references", r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")
        return pattern.findall(text)

    def extract_variable_references_no_dots(self, text: str) -> list[str]:
        """Extract variable references excluding dot notation.

        Pattern: r"\\b([a-zA-Z_][a-zA-Z0-9_]*)(?!\\.)\\b"
        Used for variables that should not include attribute access.
        """
        pattern = self._get_pattern("variable_no_dots", r"\b([a-zA-Z_][a-zA-Z0-9_]*)(?!\.)\b")
        return pattern.findall(text)

    def extract_attribute_access_pairs(self, text: str) -> list[tuple[str, str]]:
        """Extract attribute access patterns (object.attribute).

        Pattern: r"\\b([a-zA-Z_][a-zA-Z0-9_]*)\\.([a-zA-Z_][a-zA-Z0-9_]*)\\b"
        Returns list of (object_name, attribute_name) tuples.
        """
        pattern = self._get_pattern("attribute_access", r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b")
        return pattern.findall(text)

    def extract_entity_ids_with_attributes(self, text: str) -> list[str]:
        """Extract entity IDs that may have attribute access.

        Pattern: r"\\b([a-zA-Z_][a-zA-Z0-9_]*\\.[a-zA-Z0-9_.]+)\\b"
        Handles entity.attribute.sub_attribute patterns.
        """
        pattern = self._get_pattern("entity_with_attrs", r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z0-9_.]+)\b")
        return pattern.findall(text)

    def is_valid_identifier(self, text: str) -> bool:
        """Check if text is a valid identifier format.

        Pattern: r"^[a-zA-Z_][a-zA-Z0-9_]*$"
        Used for validation in 10+ files.
        """
        pattern = self._get_pattern("identifier_validation", r"^[a-zA-Z_][a-zA-Z0-9_]*$")
        return bool(pattern.match(text))

    def is_valid_domain_format(self, text: str) -> bool:
        """Check if text matches Home Assistant domain format.

        Pattern: r"^[a-z][a-z0-9_]*[a-z0-9]$"
        Used for domain validation.
        """
        pattern = self._get_pattern("domain_validation", r"^[a-z][a-z0-9_]*[a-z0-9]$")
        return bool(pattern.match(text))

    def is_valid_object_id_format(self, text: str) -> bool:
        """Check if text matches Home Assistant object ID format.

        Pattern: r"^[a-z][a-z0-9_]*[a-z0-9]$"
        Used for object ID validation.
        """
        pattern = self._get_pattern("object_id_validation", r"^[a-z][a-z0-9_]*[a-z0-9]$")
        return bool(pattern.match(text))

    def extract_metadata_function_calls(self, text: str) -> list[tuple[str, str]]:
        """Extract metadata function calls with entity and attribute.

        Pattern: r"\\bmetadata\\s*\\(\\s*([^,]+)\\s*,\\s*([^)]+)\\s*\\)"
        Returns list of (entity_or_var, attribute) tuples.
        """
        pattern = self._get_pattern("metadata_calls", r"\bmetadata\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)")
        return pattern.findall(text)

    def extract_aggregation_functions(self, text: str) -> list[tuple[str, str]]:
        """Extract aggregation function calls.

        Pattern: r"\\b(sum|avg|count|min|max|std|var)\\s*\\(([^)]+)\\)"
        Returns list of (function_name, arguments) tuples.
        """
        pattern = self._get_pattern("aggregation_calls", r"\b(sum|avg|count|min|max|std|var)\s*\(([^)]+)\)", re.IGNORECASE)
        return pattern.findall(text)

    def replace_entity_references(self, text: str, old_entity: str, new_entity: str) -> str:
        """Replace entity references safely with word boundaries.

        This handles the common pattern of replacing entity IDs in formulas
        while avoiding partial matches.
        """
        # Replace in quotes (both single and double)
        text = re.sub(r"'" + re.escape(old_entity) + r"'", f"'{new_entity}'", text)
        text = re.sub(r'"' + re.escape(old_entity) + r'"', f'"{new_entity}"', text)

        # Replace with word boundaries for unquoted references
        pattern = r"\b" + re.escape(old_entity) + r"\b"
        text = re.sub(pattern, new_entity, text)

        return text

    def extract_collection_function_patterns(self, text: str) -> list[str]:
        """Extract collection function patterns.

        Pattern: r"\\b(sum|avg|count|min|max|std|var)\\s*\\([^)]+\\)"
        Used for detecting collection functions in formulas.
        """
        pattern = self._get_pattern("collection_functions", r"\b(sum|avg|count|min|max|std|var)\s*\([^)]+\)", re.IGNORECASE)
        return [match.group(0) for match in pattern.finditer(text)]

    # =========================================================================
    # STATE AND ATTRIBUTE PATTERNS
    # =========================================================================

    def extract_state_attributes_deep(self, text: str) -> list[str]:
        """Extract deep state attribute references (state.attributes.xxx).

        Pattern: r"\\bstate\\.attributes\\.([a-zA-Z0-9_.]+)\\b"
        Used for resolving nested state attributes.
        """
        pattern = self._get_pattern("state_attributes_deep", r"\bstate\.attributes\.([a-zA-Z0-9_.]+)\b")
        return pattern.findall(text)

    def extract_state_attributes_simple(self, text: str) -> list[str]:
        """Extract simple state attribute references (state.xxx).

        Pattern: r"\\bstate\\.([a-zA-Z0-9_]+)\\b"
        Used for resolving single-level state attributes.
        """
        pattern = self._get_pattern("state_attributes_simple", r"\bstate\.([a-zA-Z0-9_]+)\b")
        return pattern.findall(text)

    def has_state_token(self, text: str) -> bool:
        """Check if text contains standalone 'state' token.

        Pattern: r"\\bstate\\b"
        Used for detecting state references that need resolution.
        """
        pattern = self._get_pattern("state_token", r"\bstate\b")
        return bool(pattern.search(text))

    def substitute_state_attributes_deep(self, text: str, replacement_func: Callable[[re.Match[str]], str]) -> str:
        """Replace deep state attribute references with replacement function results.

        Args:
            text: Text to process
            replacement_func: Function that takes attribute name and returns replacement
        """
        pattern = self._get_pattern("state_attributes_deep", r"\bstate\.attributes\.([a-zA-Z0-9_.]+)\b")
        return pattern.sub(replacement_func, text)

    def substitute_state_attributes_simple(self, text: str, replacement_func: Callable[[re.Match[str]], str]) -> str:
        """Replace simple state attribute references with replacement function results.

        Args:
            text: Text to process
            replacement_func: Function that takes match and returns replacement
        """
        pattern = self._get_pattern("state_attributes_simple", r"\bstate\.([a-zA-Z0-9_]+)\b")
        return pattern.sub(replacement_func, text)

    # =========================================================================
    # VALIDATION PATTERNS
    # =========================================================================

    def is_valid_entity_id_format(self, text: str) -> bool:
        """Check if text matches entity ID format (domain.entity).

        Pattern: r"^[a-z_]+\\.[a-z0-9_.]+$"
        Used for entity ID validation.
        """
        pattern = self._get_pattern("entity_id_format", r"^[a-z_]+\.[a-z0-9_.]+$")
        return bool(pattern.match(text))

    def is_query_pattern(self, text: str) -> bool:
        """Check if text matches query pattern format (type:value).

        Pattern: r"^(device_class|area|label|regex|attribute):"
        Used for identifying query patterns.
        """
        pattern = self._get_pattern("query_pattern", r"^(device_class|area|label|regex|attribute):")
        return bool(pattern.match(text))

    def is_collection_function(self, text: str) -> bool:
        """Check if text starts with a collection function.

        Pattern: r"^(sum|avg|mean|count|min|max|std|var)\\("
        Used for identifying collection function calls.
        """
        pattern = self._get_pattern("collection_function_start", r"^(sum|avg|mean|count|min|max|std|var)\(")
        return bool(pattern.match(text))

    def has_operators(self, text: str) -> bool:
        """Check if text contains mathematical operators.

        Pattern: r"[+\\-*/()]"
        Used for detecting mathematical expressions.
        """
        pattern = self._get_pattern("math_operators", r"[+\-*/()]")
        return bool(pattern.search(text))

    def has_entity_id_pattern(self, text: str) -> bool:
        """Check if text contains entity ID pattern (dot followed by letter).

        Pattern: r"\\.[a-zA-Z]"
        Used for detecting entity IDs in expressions.
        """
        pattern = self._get_pattern("entity_id_indicator", r"\.[a-zA-Z]")
        return bool(pattern.search(text))

    # =========================================================================
    # DATETIME AND VERSION PATTERNS
    # =========================================================================

    def is_datetime_format(self, text: str) -> bool:
        """Check if text matches datetime format.

        Used for datetime validation in type analysis.
        """
        datetime_pattern = r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
        pattern = self._get_pattern("datetime_format", datetime_pattern)
        return bool(pattern.match(text))

    def is_date_format(self, text: str) -> bool:
        """Check if text matches date format.

        Used for date validation in type analysis.
        """
        date_pattern = r"^\d{4}-\d{2}-\d{2}$"
        pattern = self._get_pattern("date_format", date_pattern)
        return bool(pattern.match(text))

    def is_version_format(self, text: str) -> bool:
        """Check if text matches version format.

        Pattern: r"^v\\d+(\\.\\d+){0,2}([-+][a-zA-Z0-9\\-.]+)?$"
        Used for version validation.
        """
        pattern = self._get_pattern("version_format", r"^v\d+(\.\d+){0,2}([-+][a-zA-Z0-9\-.]+)?$")
        return bool(pattern.match(text))

    # =========================================================================
    # TEXT PROCESSING PATTERNS
    # =========================================================================

    def normalize_name_to_identifier(self, name: str) -> str:
        """Normalize a name to a valid identifier format.

        Converts non-alphanumeric characters to underscores and collapses multiple underscores.
        """
        # Replace non-alphanumeric with underscores
        normalized = self._get_pattern("non_alphanum", r"[^a-zA-Z0-9_]").sub("_", name.lower())
        # Collapse multiple underscores
        normalized = self._get_pattern("multiple_underscores", r"_+").sub("_", normalized)
        return normalized.strip("_")

    def clean_whitespace(self, text: str) -> str:
        """Clean and normalize whitespace in text."""
        pattern = self._get_pattern("whitespace_normalize", r"\s+")
        return pattern.sub(" ", str(text)).strip()

    def remove_special_chars(self, text: str) -> str:
        """Remove special characters, keeping only alphanumeric and spaces."""
        pattern = self._get_pattern("special_chars", r"[^a-zA-Z0-9\s]")
        return pattern.sub("", str(text))

    def slugify_text(self, text: str) -> str:
        """Convert text to slug format (underscores, no special chars)."""
        # Replace spaces, hyphens, and common symbols with underscores
        text = self._get_pattern("slug_chars", r"[\s\-@#!]+").sub("_", text)
        # Remove remaining special characters
        text = self._get_pattern("non_slug_chars", r"[^a-zA-Z0-9_]").sub("", text)
        return text

    # =========================================================================
    # CONDITION AND OPERATOR PATTERNS
    # =========================================================================

    def is_operator_only(self, condition: str) -> bool:
        """Check if condition contains only operators.

        Pattern: r"\\s*(<=|>=|==|!=|<|>|[=&|%*/+-])\\s*$"
        Used for condition validation.
        """
        pattern = self._get_pattern("operator_only", r"\s*(<=|>=|==|!=|<|>|[=&|%*/+-])\s*$")
        return bool(pattern.match(condition))

    def has_assignment_operator(self, condition: str) -> bool:
        """Check if condition has single equals (assignment).

        Pattern: r"\\s*[=]{1}[^=]"
        Used for detecting invalid assignment in conditions.
        """
        pattern = self._get_pattern("assignment_op", r"\s*[=]{1}[^=]")
        return bool(pattern.match(condition))

    def has_non_comparison_operators(self, condition: str) -> bool:
        """Check if condition has non-comparison operators.

        Pattern: r"[&|%*/+]"
        Used for condition validation (excluding - for dates/negative numbers).
        """
        pattern = self._get_pattern("non_comparison_ops", r"[&|%*/+]")
        return bool(pattern.search(condition))

    def has_multiple_comparison_operators(self, condition: str) -> bool:
        """Check if condition has multiple comparison operators.

        Pattern: r">{2,}|<{2,}"
        Used for detecting invalid operator sequences.
        """
        pattern = self._get_pattern("multiple_comparison", r">{2,}|<{2,}")
        return bool(pattern.search(condition))

    def extract_negation_condition(self, condition: str) -> str | None:
        """Extract condition from negation pattern.

        Pattern: r"\\s*!(?!=)\\s*(.+)"
        Returns the condition part if negation is found, None otherwise.
        """
        pattern = self._get_pattern("negation_condition", r"\s*!(?!=)\s*(.+)")
        match = pattern.match(condition)
        return match.group(1) if match else None

    def extract_comparison_condition(self, condition: str) -> tuple[str, str] | None:
        """Extract operator and operand from comparison condition.

        Pattern: r"\\s*(<=|>=|==|!=|<|>)\\s+(.+)"
        Returns (operator, operand) tuple if match found, None otherwise.
        """
        pattern = self._get_pattern("comparison_condition", r"\s*(<=|>=|==|!=|<|>)\s+(.+)")
        match = pattern.match(condition)
        return (match.group(1), match.group(2)) if match else None

    # =========================================================================
    # NUMERIC AND TYPE EXTRACTION PATTERNS
    # =========================================================================

    def extract_numeric_parts(self, value: str) -> str:
        """Extract numeric parts from a string.

        Pattern: r"[^\\d.-]"
        Used for cleaning numeric values.
        """
        pattern = self._get_pattern("non_numeric", r"[^\d.-]")
        return pattern.sub("", value)

    def extract_version_numbers(self, version: str) -> list[str]:
        """Extract version number parts.

        Pattern: r"\\d+"
        Used for version comparison.
        """
        pattern = self._get_pattern("version_numbers", r"\d+")
        return pattern.findall(version)

    def extract_tokens_from_formula(self, formula: str) -> set[str]:
        """Extract all tokens from a formula for reference analysis.

        Pattern: r"\\b([a-zA-Z_][a-zA-Z0-9_]*(?:\\.[a-zA-Z0-9_]+)?)\\b"
        Used for formula token extraction.
        """
        pattern = self._get_pattern("formula_tokens", r"\b([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)?)\b")
        return set(pattern.findall(formula))

    def extract_formula_variables_for_resolution(self, formula: str) -> list[str]:
        """Extract variables from formula that may need resolution.

        Pattern: r"\\b[a-zA-Z_][a-zA-Z0-9_]*\\b"
        Used for detecting variables in formulas that need resolution.
        This extracts simple identifiers (no dots) that could be variables.
        """
        pattern = self._get_pattern("formula_variables_resolution", r"\b[a-zA-Z_][a-zA-Z0-9_]*\b")
        return pattern.findall(formula)

    def filter_variables_needing_resolution(self, variables: list[str], known_functions: set[str] | None = None) -> list[str]:
        """Filter variables to exclude known function names and operators.

        Args:
            variables: List of variable names to filter
            known_functions: Set of known function names to exclude

        Returns:
            List of variables that need resolution (excluding known functions)
        """
        if known_functions is None:
            known_functions = {"min", "max", "abs", "round", "int", "float", "str", "len", "sum", "any", "all"}

        return [var for var in variables if var not in known_functions]

    # =========================================================================
    # ENTITY DOMAIN PATTERNS
    # =========================================================================

    def extract_entities_for_domain_list(self, text: str, domains: list[str]) -> list[str]:
        """Extract entities matching specific domains with compiled pattern.

        More efficient version of extract_entity_ids_for_domains for repeated use.
        """
        if not domains:
            return []

        # Use consolidated domain-based entity pattern
        pattern = self._create_domain_based_entity_pattern(domains, include_capture_groups=True, word_boundaries=True)
        return pattern.findall(text)

    def create_entity_pattern_for_domains(self, domains: list[str]) -> re.Pattern[str]:
        """Create a compiled pattern for matching entities in specific domains.

        Returns a compiled regex pattern for reuse.
        """
        # Use consolidated domain-based entity pattern
        return self._create_domain_based_entity_pattern(domains, include_capture_groups=True, word_boundaries=True)

    # =========================================================================
    # FORMULA PREPROCESSING PATTERNS
    # =========================================================================

    def create_collection_function_replacement_pattern(self, function: str, query_type: str, pattern: str) -> re.Pattern[str]:
        """Create a regex pattern for replacing collection function calls.

        Used for replacing patterns like: count(device_class:door|window|motion)
        with calculated values in formula preprocessing.

        Args:
            function: The collection function name (sum, count, etc.)
            query_type: The query type (device_class, area, etc.)
            pattern: The query pattern to match

        Returns:
            Compiled regex pattern for replacement
        """
        escaped_function = re.escape(function)
        escaped_query_type = re.escape(query_type)
        escaped_pattern = re.escape(pattern)

        # Create regex pattern that matches the function call with optional exclusions
        pattern_str = (
            rf"\b{escaped_function}\s*\(\s*"
            rf"(?:['\"]?{escaped_query_type}:\s*{escaped_pattern}['\"]?)"
            rf"(?:\s+!\s*\([^)]+\)|(?:\s+![^)]+))?"  # Optional exclusions
            rf"\s*\)"
        )

        return self._get_pattern(f"collection_replacement_{function}_{query_type}_{hash(pattern)}", pattern_str)

    def create_collection_normalization_pattern(self) -> re.Pattern[str]:
        """Create pattern for normalizing collection functions with repeated prefixes.

        Converts patterns like: count("device_class:door|device_class:window|device_class:motion")
        to: count("device_class:door|window|motion")
        """
        pattern_str = (
            r"\b(sum|avg|count|min|max|std|var)\s*\(\s*"
            r"[\"']?"  # Optional opening quote
            r"([a-zA-Z_]+):"  # First prefix (e.g., "device_class:")
            r"([^)\"']+)"  # Everything until the closing paren or quote
            r"[\"']?"  # Optional closing quote
            r"\)"
        )
        return self._get_pattern("collection_normalization", pattern_str, re.IGNORECASE)

    def build_variable_exclusion_pattern(self, excluded_keywords: list[str]) -> re.Pattern[str]:
        """Build a pattern for matching variables while excluding specific keywords.

        Used by dependency parser to exclude function names and keywords from variable extraction.

        Args:
            excluded_keywords: List of keywords to exclude from matching

        Returns:
            Compiled regex pattern
        """
        if not excluded_keywords:
            return self._get_pattern("variable_references", r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")

        excluded_pattern = "|".join(re.escape(keyword) for keyword in excluded_keywords)
        pattern_str = rf"\b(?!(?:{excluded_pattern})\b)[a-zA-Z_][a-zA-Z0-9_]*\b"

        # Use hash of keywords for unique caching
        cache_key = f"variable_exclusion_{hash(tuple(sorted(excluded_keywords)))}"
        return self._get_pattern(cache_key, pattern_str)

    def create_dot_notation_pattern_with_domain_exclusion(self, domains_pattern: str) -> re.Pattern[str]:
        """Create dot notation pattern that excludes entity domains.

        Used for matching variable.attribute patterns while avoiding conflicts with entity IDs.

        Args:
            domains_pattern: Pipe-separated pattern of domains to exclude

        Returns:
            Compiled regex pattern
        """
        if not domains_pattern:
            # If no domains, match any dot notation
            pattern_str = r"\b([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\.(attributes\.)?([a-zA-Z0-9_]+)\b"
        else:
            pattern_str = rf"\b(?!(?:{domains_pattern})\.)([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\.(attributes\.)?([a-zA-Z0-9_]+)\b"

        return self._get_pattern(f"dot_notation_domain_exclusion_{hash(domains_pattern)}", pattern_str)

    # =========================================================================
    # TYPE ANALYSIS PATTERNS
    # =========================================================================

    def extract_numeric_parts_advanced(self, value: str) -> str:
        """Extract numeric parts from a string, removing non-numeric characters.

        More advanced version that handles common suffixes/prefixes.
        Used in type analysis for numeric conversion.
        """
        pattern = self._get_pattern("numeric_extraction_advanced", r"[^\d.-]")
        return pattern.sub("", value)

    def is_strict_datetime_string(self, value: str) -> bool:
        """Check if string is definitely a datetime with strict validation.

        Used in type analysis to distinguish datetime strings from other formats.
        """
        datetime_pattern = (
            r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[T\s]\d{1,2}:\d{1,2}(?::\d{1,2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
        )
        pattern = self._get_pattern("strict_datetime", datetime_pattern)
        return bool(pattern.match(value))

    def is_strict_version_string(self, value: str) -> bool:
        """Check if string is definitely a version (requires 'v' prefix).

        Used in type analysis to identify version strings.
        """
        pattern = self._get_pattern("strict_version", r"^v\d+\.\d+\.\d+(?:[-+].+)?$")
        return bool(pattern.match(value))

    def extract_version_numeric_parts(self, version: str) -> list[str]:
        """Extract numeric parts from version string.

        Used in type analysis for version comparison.
        """
        pattern = self._get_pattern("version_numeric_parts", r"\d+")
        return pattern.findall(version)

    # =========================================================================
    # SCHEMA VALIDATION PATTERNS
    # =========================================================================

    def get_variable_value_pattern(self) -> str:
        """Get the comprehensive variable value pattern for schema validation.

        This pattern matches all valid variable value formats:
        - Entity IDs (domain.entity)
        - Variable references
        - Collection patterns (device_class:type)
        - Formulas and other valid formats
        """
        return (
            "^([a-z_]+\\.[a-z0-9_.]+|[a-zA-Z_][a-zA-Z0-9_]*|device_class:[a-z0-9_]+|"
            "area:[a-zA-Z0-9_\\s]+|label:[a-zA-Z0-9_\\s]+|regex:.+|attribute:[a-zA-Z0-9_.]+|"
            "state:[a-zA-Z0-9_.]+|formula:.+|\\d+(?:\\.\\d+)?|true|false|"
            "\\d{4}-\\d{2}-\\d{2}(?:[T ]\\d{2}:\\d{2}(?::\\d{2})?)?|"
            "v\\d+(?:\\.\\d+){0,2}(?:[-+][a-zA-Z0-9\\-.]+)?|"
            "[a-zA-Z0-9_\\s\\-\\.]+)$"
        )

    def get_variable_name_pattern(self) -> str:
        """Get the pattern for valid variable names."""
        return "^[a-zA-Z_][a-zA-Z0-9_]*$"

    def get_entity_id_schema_pattern(self) -> str:
        """Get the entity ID pattern for schema validation."""
        return "^[a-z_]+\\.[a-z0-9_]+$"

    def get_icon_pattern(self) -> str:
        """Get the pattern for valid Home Assistant icons."""
        return "^mdi:[a-z0-9-]+$"

    # =========================================================================
    # ENTITY REFERENCE REPLACEMENT PATTERNS
    # =========================================================================

    def replace_entity_id_with_variable(self, text: str, entity_id: str, variable_name: str) -> str:
        """Replace entity ID with variable name using word boundaries.

        Used for converting entity references to variable names in formulas.

        Args:
            text: Text to process
            entity_id: Entity ID to replace
            variable_name: Variable name to replace with

        Returns:
            Text with entity ID replaced by variable name
        """
        # Use word boundaries to avoid partial matches
        pattern = self._get_pattern(f"entity_replacement_{hash(entity_id)}", r"\b" + re.escape(entity_id) + r"\b")
        return pattern.sub(variable_name, text)

    def convert_entity_id_to_variable_name(self, entity_id: str) -> str:
        """Convert entity ID to variable name format.

        Replaces dots and dashes with underscores to create valid variable names.

        Args:
            entity_id: Entity ID to convert

        Returns:
            Variable name format
        """
        return entity_id.replace(".", "_").replace("-", "_")

    def search_and_replace_with_pattern(self, text: str, pattern: str, replacement: str) -> str:
        """Search for pattern and replace with replacement string.

        Used for generic pattern-based replacements in formulas.

        Args:
            text: Text to process
            pattern: Regex pattern to search for
            replacement: Replacement string

        Returns:
            Text with pattern replaced
        """
        compiled_pattern = self._get_pattern(f"search_replace_{hash(pattern)}", pattern)
        return compiled_pattern.sub(replacement, text)

    def check_pattern_exists(self, text: str, pattern: str) -> bool:
        """Check if a pattern exists in text.

        Args:
            text: Text to search in
            pattern: Regex pattern to search for

        Returns:
            True if pattern is found, False otherwise
        """
        compiled_pattern = self._get_pattern(f"pattern_check_{hash(pattern)}", pattern)
        return bool(compiled_pattern.search(text))

    # =========================================================================
    # AGGREGATION AND FUNCTION PATTERNS
    # =========================================================================

    def create_aggregation_function_pattern(self) -> re.Pattern[str]:
        """Create pattern for matching aggregation functions with arguments.

        Used for extracting aggregation functions from formulas.
        Pattern matches: sum(...), avg(...), count(...), etc.
        """
        pattern_str = r"\b(sum|avg|count|min|max|std|var)\s*\(([^)]+)\)"
        return self._get_pattern("aggregation_function_pattern", pattern_str, re.IGNORECASE)

    def create_aggregation_pattern_with_exclusions(self) -> re.Pattern[str]:
        """Create comprehensive aggregation pattern with query syntax and exclusions.

        Used by dependency parser for complex aggregation function parsing.
        """
        # Fix: Restructure pattern to properly handle quoted vs unquoted content
        pattern_str = (
            r"\b(sum|avg|count|min|max|std|var)\s*\(\s*"
            r"(?:"
            r'(?P<query_quoted>["\'])(?P<query_content_quoted>[^"\']+)(?P=query_quoted)'  # Quoted main query
            r'(?:\s*,\s*(?P<exclusions>(?:!\s*["\'][^"\']+["\'](?:\s*,\s*)?)+))?|'  # Optional exclusions with !
            r"(?P<query_content_unquoted>[^),]+)"  # Unquoted main query
            r"(?:\s*,\s*(?P<exclusions_unquoted>(?:!\s*[^,)]+(?:\s*,\s*)?)+))?"  # Optional exclusions for unquoted
            r")\s*\)"
        )
        return self._get_pattern("aggregation_with_exclusions", pattern_str, re.IGNORECASE)

    def extract_entity_function_calls(self, text: str) -> list[str]:
        """Extract entity IDs from entity() function calls.

        Pattern matches: entity('sensor.power'), entity("binary_sensor.door")
        """
        pattern = self._get_pattern("entity_function_calls", r'entity\(["\']([^"\']+)["\']\)')
        return pattern.findall(text)

    def create_exclusion_pattern(self) -> re.Pattern[str]:
        """Create pattern for matching exclusion syntax.

        Pattern matches: !'pattern' or !pattern
        Used for parsing exclusions in collection functions.
        """
        pattern_str = r"!\s*(?:[\"']([^\"']+)[\"']|([^,)]+))"
        return self._get_pattern("exclusion_pattern", pattern_str)

    # =========================================================================
    # VARIABLE AND IDENTIFIER PATTERNS
    # =========================================================================

    def create_identifier_pattern(self) -> re.Pattern[str]:
        """Create pattern for matching identifiers in formulas.

        Pattern matches: variable_name, sensor_power, etc.
        Used for extracting identifiers from formulas.
        """
        pattern_str = r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b"
        return self._get_pattern("identifier_pattern", pattern_str)

    def is_valid_variable_name(self, name: str) -> bool:
        """Check if a name is a valid variable name format.

        Used for validating variable names in configuration.
        """
        pattern = self._get_pattern("valid_variable_name", r"^[a-zA-Z_][a-zA-Z0-9_]*$")
        return bool(pattern.match(name))

    def extract_potential_entity_ids(self, text: str) -> list[str]:
        """Extract potential entity IDs from text.

        Pattern matches: domain.entity_name format
        Used for finding entity references in formulas.
        """
        pattern = self._get_pattern("potential_entity_ids", r"\b[a-z_]+\.[a-z0-9_]+\b")
        return pattern.findall(text)

    # =========================================================================
    # MATCH OBJECT REPLACEMENT HELPERS
    # =========================================================================

    def create_replacement_function(self, replacement_logic: Callable[[re.Match[str]], str]) -> Callable[[re.Match[str]], str]:
        """Create a replacement function that can be used with regex substitution.

        This helps eliminate the need for inline match object handling.

        Args:
            replacement_logic: Function that takes match groups and returns replacement

        Returns:
            Function suitable for use with re.sub()
        """

        def replacement_wrapper(match: re.Match[str]) -> str:
            return replacement_logic(match)

        return replacement_wrapper

    def extract_match_groups(self, text: str, pattern: str) -> list[tuple[str, ...]]:
        """Extract all match groups from text using pattern.

        Args:
            text: Text to search in
            pattern: Regex pattern with groups

        Returns:
            List of tuples containing match groups
        """
        compiled_pattern = self._get_pattern(f"match_groups_{hash(pattern)}", pattern)
        return [match.groups() for match in compiled_pattern.finditer(text)]

    def replace_with_function(self, text: str, pattern: str, replacement_func: Callable[[re.Match[str]], str]) -> str:
        """Replace pattern matches using a replacement function.

        Args:
            text: Text to process
            pattern: Regex pattern to match
            replacement_func: Function that takes match object and returns replacement

        Returns:
            Text with replacements applied
        """
        compiled_pattern = self._get_pattern(f"replace_func_{hash(pattern)}", pattern)
        return compiled_pattern.sub(replacement_func, text)

    # =========================================================================
    # VARIABLE RESOLUTION SPECIFIC PATTERNS
    # =========================================================================

    def substitute_state_attributes_with_function(self, text: str, replacement_func: Callable[[re.Match[str]], str]) -> str:
        """Replace state.attributes.xxx patterns with replacement function results.

        Used in variable resolution for handling state attribute access.
        """
        return self.substitute_state_attributes_deep(text, replacement_func)

    def substitute_simple_state_with_function(self, text: str, replacement_func: Callable[[re.Match[str]], str]) -> str:
        """Replace state.xxx patterns with replacement function results.

        Used in variable resolution for handling simple state access.
        """
        return self.substitute_state_attributes_simple(text, replacement_func)

    def create_entity_pattern_from_domains(self, domains: list[str]) -> re.Pattern[str]:
        """Create entity pattern from Home Assistant domains.

        Used in variable resolution for entity reference detection.
        """
        # Use consolidated domain-based entity pattern (captures domain only, not full entity ID)
        if not domains:
            return self._get_pattern("no_domains", r"(?!.*)")

        domains_pattern = "|".join(re.escape(domain) for domain in domains)
        pattern_str = rf"\b({domains_pattern})\.[a-zA-Z0-9_.]+\b"
        return self._get_pattern(f"entity_from_domains_{hash(tuple(domains))}", pattern_str, re.IGNORECASE)

    # =========================================================================
    # COMMONLY USED PATTERNS ACROSS MODULES
    # =========================================================================

    def create_metadata_function_pattern(self, function_name: str = "metadata") -> re.Pattern[str]:
        """Create pattern for matching metadata function calls.

        Used across multiple modules for metadata function detection.
        """
        pattern_str = rf"{re.escape(function_name)}\s*\(\s*([^)]+)\s*\)"
        return self._get_pattern(f"metadata_function_{function_name}", pattern_str, re.IGNORECASE)

    def create_simple_identifier_validation_pattern(self) -> re.Pattern[str]:
        """Create pattern for validating simple identifiers.

        Used for attribute names and variable validation.
        """
        return self._get_pattern("simple_identifier_validation", r"^[a-zA-Z_][a-zA-Z0-9_]*$")

    def create_condition_parsing_pattern(self) -> re.Pattern[str]:
        """Create pattern for parsing condition expressions.

        Used in condition parser for extracting variable, operator, and value.
        """
        pattern_str = r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*(<=|>=|==|!=|<|>)\s*(.+)$"
        return self._get_pattern("condition_parsing", pattern_str)

    def create_domain_validation_pattern(self) -> re.Pattern[str]:
        """Create pattern for validating Home Assistant domain names.

        Used in device classes and domain validation.
        """
        return self._get_pattern("domain_validation", r"^[a-z][a-z0-9_]{1,49}$")

    def create_datetime_function_pattern(self) -> re.Pattern[str]:
        """Create pattern for matching datetime function calls.

        Used in datetime handler for function detection.
        """
        return self._get_pattern("datetime_functions", r"\b(\w+)\(\s*\)")

    def create_collection_function_detection_pattern(self) -> re.Pattern[str]:
        """Create pattern for detecting collection functions.

        Used across multiple modules for collection function detection.
        """
        pattern_str = r"\b(sum|avg|count|min|max|std|var)\s*\([^)]+\)"
        return self._get_pattern("collection_function_detection", pattern_str, re.IGNORECASE)

    def create_entity_reference_pattern_from_domains(self, domains_pattern: str) -> re.Pattern[str]:
        """Create entity reference pattern from domains pattern string.

        Used in collection resolver and other modules.
        """
        pattern_str = rf"\b(?:{domains_pattern})\.[a-zA-Z0-9_.]+\b"
        return self._get_pattern(f"entity_ref_{hash(domains_pattern)}", pattern_str)

    def create_attribute_access_pattern(self) -> re.Pattern[str]:
        """Create pattern for matching dot notation attribute access (variable.attribute).

        Pattern: \\b([a-zA-Z_][a-zA-Z0-9_]*)\\s*\\.\\s*([a-zA-Z_][a-zA-Z0-9_]*)\\b
        Input: "state.last_changed" or "entity.attributes"
        Output: Groups (1=variable_name, 2=attribute_name)

        Used in: formula_helpers.identify_variables_for_attribute_access
        Purpose: Identify variables that need entity ID preservation for dot notation access
        Note: Does NOT match metadata() function calls - use extract_variable_references_from_metadata for that
        """
        pattern_str = r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\b"
        return self._get_pattern("attribute_access", pattern_str)

    def create_single_token_pattern(self) -> re.Pattern[str]:
        """Create pattern for matching single tokens (variable or entity ID).

        Used in formula helpers for token validation.
        """
        pattern_str = r"^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)?$"
        return self._get_pattern("single_token", pattern_str)

    def create_standalone_reference_pattern(self, name: str) -> re.Pattern[str]:
        """Create pattern for standalone references (not preceded/followed by dots).

        Used in circular reference validator and other modules.
        """
        pattern_str = rf"\b{re.escape(name)}\b(?!\s*\.)"
        return self._get_pattern(f"standalone_ref_{hash(name)}", pattern_str)

    def create_sensor_name_search_pattern(self, sensor_name: str) -> re.Pattern[str]:
        """Create pattern for searching sensor names in formulas.

        Used in cross-sensor dependency manager.
        """
        pattern_str = r"\b" + re.escape(sensor_name) + r"\b"
        return self._get_pattern(f"sensor_search_{hash(sensor_name)}", pattern_str)

    def create_entity_id_exact_match_pattern(self, entity_id: str) -> re.Pattern[str]:
        """Create pattern for exact entity ID matching.

        Used in storage operations for entity ID detection.
        """
        pattern_str = r"\b" + re.escape(entity_id) + r"\b"
        return self._get_pattern(f"entity_exact_{hash(entity_id)}", pattern_str)

    def create_entity_attribute_access_pattern(self, entity_id: str) -> re.Pattern[str]:
        """Create pattern for entity attribute access.

        Used in storage operations for detecting entity.attribute patterns.
        """
        pattern_str = r"\b" + re.escape(entity_id) + r"\.[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*"
        return self._get_pattern(f"entity_attr_{hash(entity_id)}", pattern_str)

    def search_pattern(self, text: str, pattern: re.Pattern[str]) -> bool:
        """Search for pattern in text and return boolean result.

        Centralized search method to avoid direct re.search calls.
        """
        return bool(pattern.search(text))

    def substitute_pattern(self, text: str, pattern: re.Pattern[str], replacement: str) -> str:
        """Substitute pattern in text with replacement.

        Centralized substitution method to avoid direct re.sub calls.
        """
        return pattern.sub(replacement, text)

    def find_all_matches(self, text: str, pattern: re.Pattern[str]) -> list[str]:
        """Find all matches of pattern in text.

        Centralized findall method to avoid direct re.findall calls.
        """
        return pattern.findall(text)

    def find_all_match_objects(self, text: str, pattern: re.Pattern[str]) -> list[re.Match[str]]:
        """Find all match objects of pattern in text.

        Centralized finditer method to avoid direct re.finditer calls.
        """
        return list(pattern.finditer(text))

    def match_pattern(self, text: str, pattern: re.Pattern[str]) -> re.Match[str] | None:
        """Match pattern against text from beginning.

        Centralized match method to avoid direct re.match calls.
        """
        return pattern.match(text)

    # =========================================================================
    # ADVANCED ENTITY AND SENSOR OPERATIONS
    # =========================================================================

    def create_entity_exact_search_pattern(self, entity_id: str) -> re.Pattern[str]:
        """Create pattern for exact entity ID search with word boundaries.

        Used in storage operations and entity replacement logic.
        """
        pattern_str = r"\b" + re.escape(entity_id) + r"\b"
        return self._get_pattern(f"entity_exact_search_{hash(entity_id)}", pattern_str)

    def create_entity_attribute_search_pattern(self, entity_id: str) -> re.Pattern[str]:
        """Create pattern for entity attribute access search.

        Matches patterns like entity_id.attribute or entity_id.nested.attribute
        """
        pattern_str = r"\b" + re.escape(entity_id) + r"\.[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*"
        return self._get_pattern(f"entity_attr_search_{hash(entity_id)}", pattern_str)

    def create_sensor_expression_pattern(self, sensor_key: str) -> re.Pattern[str]:
        """Create pattern for sensor key in mathematical/logical expressions.

        Matches sensor key surrounded by operators, parentheses, or function calls.
        """
        pattern_str = r"(?:^|[+\-*/()=<>!&|,\s])\s*" + re.escape(sensor_key) + r"\s*(?:[+\-*/()=<>!&|,\s]|$)"
        return self._get_pattern(f"sensor_expr_{hash(sensor_key)}", pattern_str)

    def create_sensor_key_no_entity_prefix_pattern(self, sensor_key: str) -> re.Pattern[str]:
        """Create pattern for sensor key that's not part of an entity ID.

        Uses negative lookbehind to avoid matching sensor_key that's part of sensor.sensor_key
        """
        pattern_str = r"(?<!sensor\.)\b" + re.escape(sensor_key) + r"\b(?!\.[a-zA-Z_])"
        return self._get_pattern(f"sensor_no_prefix_{hash(sensor_key)}", pattern_str)

    def create_sensor_attribute_no_entity_prefix_pattern(self, sensor_key: str) -> re.Pattern[str]:
        """Create pattern for sensor key attribute access not part of entity ID.

        Matches sensor_key.attribute but not sensor.sensor_key.attribute
        """
        pattern_str = r"(?<!sensor\.)\b" + re.escape(sensor_key) + r"(\.[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)"
        return self._get_pattern(f"sensor_attr_no_prefix_{hash(sensor_key)}", pattern_str)

    def create_collection_function_extraction_pattern(self) -> re.Pattern[str]:
        """Create pattern for extracting collection functions with quoted parameters.

        Used in dependency management for collection function detection.
        """
        pattern_str = r'\b(sum|avg|max|min|count)\s*\(\s*["\']([^"\']+)["\']\s*\)'
        return self._get_pattern("collection_extraction", pattern_str)

    def create_referenced_tokens_pattern(self) -> re.Pattern[str]:
        """Create pattern for extracting referenced tokens from formulas.

        Handles both simple variable names and entity IDs with dots.
        """
        pattern_str = r"\b([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)?)\b"
        return self._get_pattern("referenced_tokens", pattern_str)

    def create_query_type_patterns(self) -> dict[str, re.Pattern[str]]:
        """Create patterns for different query types used in collection resolution.

        Returns a dictionary mapping query types to their compiled patterns.
        """
        patterns = {}
        query_types = {
            "device_class": r"^device_class:\s*(.+)$",
            "area": r"^area:\s*(.+)$",
            "label": r"^label:\s*(.+)$",
            "attribute": r"^attribute:\s*(.+)$",
            "state": r"^state:\s*(.+)$",
            "regex": r"^regex:\s*(.+)$",
        }

        for query_type, pattern_str in query_types.items():
            patterns[query_type] = self._get_pattern(f"query_{query_type}", pattern_str)

        return patterns

    def create_entity_id_and_sensor_key_patterns(self) -> tuple[re.Pattern[str], re.Pattern[str]]:
        """Create patterns for entity IDs and sensor keys used in formula resolution.

        Returns tuple of (entity_id_pattern, sensor_key_pattern)
        """
        entity_pattern = self._get_pattern("formula_entity_ids", r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)\b")
        sensor_pattern = self._get_pattern("formula_sensor_keys", r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")
        return entity_pattern, sensor_pattern

    def safe_entity_replacement(self, text: str, old_entity: str, new_entity: str) -> str:
        """Safely replace entity references in text with proper escaping.

        Handles both quoted and unquoted entity references.
        """
        # Replace in quotes (both single and double) - reuse existing logic
        text = re.sub(r"'" + re.escape(old_entity) + r"'", f"'{new_entity}'", text)
        text = re.sub(r'"' + re.escape(old_entity) + r'"', f'"{new_entity}"', text)

        # Replace with word boundaries for unquoted references
        pattern = r"\b" + re.escape(old_entity) + r"\b"
        text = re.sub(pattern, new_entity, text)

        return text

    def search_entity_in_text(self, text: str, entity_id: str) -> bool:
        """Search for entity ID in text using exact match pattern."""
        pattern = self.create_entity_exact_search_pattern(entity_id)
        return self.search_pattern(text, pattern)

    def search_entity_attribute_in_text(self, text: str, entity_id: str) -> bool:
        """Search for entity attribute access in text."""
        pattern = self.create_entity_attribute_search_pattern(entity_id)
        return self.search_pattern(text, pattern)

    def replace_entity_with_state(self, text: str, entity_id: str) -> tuple[str, bool]:
        """Replace entity ID with 'state' and return updated text and whether replacement was made."""
        pattern = self.create_entity_exact_search_pattern(entity_id)
        if self.search_pattern(text, pattern):
            updated_text = self.substitute_pattern(text, pattern, "state")
            return updated_text, True
        return text, False

    def find_entity_attribute_matches(self, text: str, entity_id: str) -> list[re.Match[str]]:
        """Find all entity attribute access matches in text."""
        pattern = self.create_entity_attribute_search_pattern(entity_id)
        return self.find_all_match_objects(text, pattern)

    # =========================================================================
    # FINAL CONSOLIDATION PATTERNS
    # =========================================================================

    def create_case_insensitive_pattern(self, pattern_str: str) -> re.Pattern[str]:
        """Create case-insensitive regex pattern.

        Used for regex query resolution in collection resolver.
        """
        return self._get_pattern(f"case_insensitive_{hash(pattern_str)}", pattern_str, re.IGNORECASE)

    def create_device_validation_patterns(self) -> dict[str, re.Pattern[str]]:
        """Create device info validation patterns.

        Returns dictionary of field names to validation patterns.
        """
        patterns = {
            "device_identifier": self._get_pattern("device_identifier", r"^[a-zA-Z0-9_-]+$"),
            "device_name": self._get_pattern("device_name", r"^[a-zA-Z0-9\s_-]+$"),
            "device_manufacturer": self._get_pattern("device_manufacturer", r"^[a-zA-Z0-9\s_-]+$"),
            "device_model": self._get_pattern("device_model", r"^[a-zA-Z0-9\s_-]+$"),
            "device_sw_version": self._get_pattern("device_version", r"^[a-zA-Z0-9._-]+$"),
            "device_hw_version": self._get_pattern("device_version", r"^[a-zA-Z0-9._-]+$"),
            "suggested_area": self._get_pattern("suggested_area", r"^[a-zA-Z0-9\s_-]+$"),
        }
        return patterns

    def validate_device_field(self, field_name: str, value: str) -> bool:
        """Validate device field value against pattern.

        Args:
            field_name: Name of the device field
            value: Value to validate

        Returns:
            True if value matches pattern, False otherwise
        """
        patterns = self.create_device_validation_patterns()
        pattern = patterns.get(field_name)
        if pattern:
            return self.match_pattern(str(value), pattern) is not None
        return True  # No pattern means no validation required

    def search_case_insensitive(self, text: str, pattern_str: str) -> bool:
        """Search for pattern in text with case-insensitive matching."""
        pattern = self.create_case_insensitive_pattern(pattern_str)
        return self.search_pattern(text, pattern)

    # =========================================================================
    # DEPENDENCY PARSING DOMAIN METHODS
    # =========================================================================

    def extract_entity_function_references(self, formula: str) -> list[str]:
        """Extract entity IDs from entity() function calls.

        Finds patterns like: entity("sensor.power"), state("binary_sensor.door")
        """
        entity_ids = []
        patterns = [
            self._get_pattern("entity_function", r'entity\(["\']([^"\']+)["\']\)'),
            self._get_pattern("state_function", r'state\(["\']([^"\']+)["\']\)'),
            self._get_pattern("states_bracket", r'states\[["\']([^"\']+)["\']\]'),
            self._get_pattern("metadata_entity_ref", r'metadata\(\s*["\']([^"\']+)["\']\s*,', re.IGNORECASE),
        ]

        for pattern in patterns:
            matches = self.find_all_matches(formula, pattern)
            entity_ids.extend(matches)

        return entity_ids

    def extract_states_dot_notation_entities(self, formula: str) -> list[str]:
        """Extract entity IDs from states.domain.entity format.

        Finds patterns like: states.sensor.power_meter
        """
        pattern = self._get_pattern("states_dot_notation", r"states\.([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)")
        return self.find_all_matches(formula, pattern)

    def extract_direct_entity_references(self, formula: str) -> list[str]:
        """Extract direct entity ID references from formula.

        Finds patterns like: sensor.power_meter, binary_sensor.door_open
        """
        pattern = self._get_pattern("direct_entity_id", r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_.]*)\b")
        return self.find_all_matches(formula, pattern)

    def get_entity_function_patterns(self) -> list[re.Pattern[str]]:
        """Get compiled patterns for entity function detection.

        Returns list of patterns for dependency parsing use.
        """
        return [
            self._get_pattern("entity_function", r'entity\(["\']([^"\']+)["\']\)'),
            self._get_pattern("state_function", r'state\(["\']([^"\']+)["\']\)'),
            self._get_pattern("states_bracket", r'states\[["\']([^"\']+)["\']\]'),
            self._get_pattern("metadata_entity_ref", r'metadata\(\s*["\']([^"\']+)["\']\s*,', re.IGNORECASE),
        ]

    def get_states_dot_notation_pattern(self) -> re.Pattern[str]:
        """Get pattern for states.domain.entity format."""
        return self._get_pattern("states_dot_notation", r"states\.([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)")

    def get_direct_entity_pattern(self) -> re.Pattern[str]:
        """Get pattern for direct entity ID references."""
        return self._get_pattern("direct_entity_id", r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_.]*)\b")

    def get_variable_references_pattern(self) -> re.Pattern[str]:
        """Get pattern for variable name references."""
        return self._get_pattern("variable_references", r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")

    def get_no_match_pattern(self) -> re.Pattern[str]:
        """Get pattern that matches nothing - used when no domains are available."""
        return self._get_pattern("no_domains", r"(?!.*)", re.IGNORECASE)

    def get_state_token_pattern(self) -> re.Pattern[str]:
        """Get pattern for 'state' token with word boundaries."""
        return self._get_pattern("state_token", r"\bstate\b")

    def get_entity_lazy_resolution_pattern(self) -> re.Pattern[str]:
        """Get pattern for entity references in lazy resolution context.

        Prevents matching decimals by requiring word boundary and letter/underscore start.
        """
        return self._get_pattern(
            "entity_lazy_resolution",
            r"(?:^|(?<=\s)|(?<=\()|(?<=[+\-*/]))([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z0-9_.]+)(?=\s|$|[+\-*/)])",
        )

    def extract_variables_from_pattern_value(self, pattern_value: str) -> set[str]:
        """Extract variables from a pattern value using the variable pattern.

        Args:
            pattern_value: Pattern value string to parse

        Returns:
            Set of variable names found in the pattern value
        """
        pattern = self._get_pattern("variable_references", r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")
        variables = set()

        for match in pattern.findall(pattern_value):
            # findall returns strings directly, not match objects
            variables.add(match)

        return variables

    def extract_variable_references_from_metadata(self, formula: str) -> set[str]:
        """Extract variable references from metadata function calls.

        Args:
            formula: The formula string to analyze

        Returns:
            Set of variables referenced in metadata functions
        """
        var_refs = set()

        # Pattern to match metadata function calls with variable as first parameter
        # Captures: metadata(variable_name, 'attribute')
        metadata_pattern = r"metadata\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*,\s*['\"][^'\"]+['\"]\s*\)"

        for match in re.finditer(metadata_pattern, formula):
            variable = match.group(1)
            # Only add if it doesn't look like a quoted entity ID
            var_refs.add(variable)

        return var_refs

    def extract_variables_from_formula(self, formula: str, context: str = "general") -> set[str]:
        """Extract variable names from a formula using the variable pattern.

        Args:
            formula: Formula string to parse
            context: Context for extraction (e.g., "dependency_parsing")

        Returns:
            Set of variable names found in the formula
        """
        pattern = self._get_pattern("variable_references", r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")
        variables = set()

        for match in pattern.finditer(formula):
            var = match.group(0)
            variables.add(var)

        return variables

    def extract_dot_notation_matches(self, formula: str) -> list[tuple[str, str, str]]:
        """Extract dot notation matches from a formula.

        Args:
            formula: Formula string to parse

        Returns:
            List of tuples (entity_part, dot, attribute_part)
        """
        pattern = self.create_dot_notation_pattern_with_domain_exclusion("")
        matches = []

        for match in pattern.findall(formula):
            if len(match) == 3:
                matches.append(match)

        return matches

    def extract_aggregation_function_matches(self, formula: str) -> list[re.Match[str]]:
        """Extract aggregation function matches from a formula.

        Args:
            formula: Formula string to parse

        Returns:
            List of regex match objects for aggregation functions
        """
        pattern = self.create_aggregation_function_pattern()
        matches = []

        for match in pattern.finditer(formula):
            matches.append(match)

        return matches

    def extract_aggregation_function_matches_with_exclusions(self, formula: str) -> list[re.Match[str]]:
        """Extract aggregation function matches from a formula with full exclusion support.

        Args:
            formula: Formula string to parse

        Returns:
            List of regex match objects for aggregation functions with named groups
        """
        pattern = self.create_aggregation_pattern_with_exclusions()
        matches = []

        for match in pattern.finditer(formula):
            matches.append(match)

        return matches

    def extract_dot_notation_matches_with_iter(self, formula: str) -> list[re.Match[str]]:
        """Extract dot notation matches from a formula using finditer.

        Args:
            formula: Formula string to parse

        Returns:
            List of regex match objects for dot notation
        """
        pattern = self.create_dot_notation_pattern_with_domain_exclusion("")
        matches = []

        for match in pattern.finditer(formula):
            matches.append(match)

        return matches


# Global instance
regex_helper = RegexHelper()

# Export methods at module level
find_string_literals = regex_helper.find_string_literals
extract_quoted_strings = regex_helper.extract_quoted_strings
extract_identifiers = regex_helper.extract_identifiers
extract_simple_identifiers = regex_helper.extract_simple_identifiers
extract_basic_entity_ids = regex_helper.extract_basic_entity_ids
extract_metadata_entities = regex_helper.extract_metadata_entities
extract_exclusions = regex_helper.extract_exclusions
extract_entity_ids_for_domains = regex_helper.extract_entity_ids_for_domains
extract_variables_excluding_keywords = regex_helper.extract_variables_excluding_keywords
extract_entity_function_refs = regex_helper.extract_entity_function_refs
extract_state_function_refs = regex_helper.extract_state_function_refs
extract_states_bracket_refs = regex_helper.extract_states_bracket_refs
extract_states_dot_refs = regex_helper.extract_states_dot_refs
find_exclusions_in_pattern = regex_helper.find_exclusions_in_pattern

# Export high-reuse common pattern methods
extract_variable_references = regex_helper.extract_variable_references
extract_variable_references_no_dots = regex_helper.extract_variable_references_no_dots
extract_attribute_access_pairs = regex_helper.extract_attribute_access_pairs
extract_entity_ids_with_attributes = regex_helper.extract_entity_ids_with_attributes
is_valid_identifier = regex_helper.is_valid_identifier
is_valid_domain_format = regex_helper.is_valid_domain_format
is_valid_object_id_format = regex_helper.is_valid_object_id_format
extract_metadata_function_calls = regex_helper.extract_metadata_function_calls
extract_aggregation_functions = regex_helper.extract_aggregation_functions
replace_entity_references = regex_helper.replace_entity_references
extract_collection_function_patterns = regex_helper.extract_collection_function_patterns

# Export state and attribute patterns
extract_state_attributes_deep = regex_helper.extract_state_attributes_deep
extract_state_attributes_simple = regex_helper.extract_state_attributes_simple
has_state_token = regex_helper.has_state_token
substitute_state_attributes_deep = regex_helper.substitute_state_attributes_deep
substitute_state_attributes_simple = regex_helper.substitute_state_attributes_simple

# Export validation patterns
is_valid_entity_id_format = regex_helper.is_valid_entity_id_format
is_query_pattern = regex_helper.is_query_pattern
is_collection_function = regex_helper.is_collection_function
has_operators = regex_helper.has_operators
has_entity_id_pattern = regex_helper.has_entity_id_pattern

# Export datetime and version patterns
is_datetime_format = regex_helper.is_datetime_format
is_date_format = regex_helper.is_date_format
is_version_format = regex_helper.is_version_format

# Export text processing patterns
normalize_name_to_identifier = regex_helper.normalize_name_to_identifier
clean_whitespace = regex_helper.clean_whitespace
remove_special_chars = regex_helper.remove_special_chars
slugify_text = regex_helper.slugify_text

# Export condition and operator patterns
is_operator_only = regex_helper.is_operator_only
has_assignment_operator = regex_helper.has_assignment_operator
has_non_comparison_operators = regex_helper.has_non_comparison_operators
has_multiple_comparison_operators = regex_helper.has_multiple_comparison_operators
extract_negation_condition = regex_helper.extract_negation_condition
extract_comparison_condition = regex_helper.extract_comparison_condition

# Export numeric and type extraction patterns
extract_numeric_parts = regex_helper.extract_numeric_parts
extract_version_numbers = regex_helper.extract_version_numbers
extract_tokens_from_formula = regex_helper.extract_tokens_from_formula
extract_formula_variables_for_resolution = regex_helper.extract_formula_variables_for_resolution
filter_variables_needing_resolution = regex_helper.filter_variables_needing_resolution

# Export entity domain patterns
extract_entities_for_domain_list = regex_helper.extract_entities_for_domain_list
create_entity_pattern_for_domains = regex_helper.create_entity_pattern_for_domains

# Export formula preprocessing patterns
create_collection_function_replacement_pattern = regex_helper.create_collection_function_replacement_pattern
create_collection_normalization_pattern = regex_helper.create_collection_normalization_pattern
build_variable_exclusion_pattern = regex_helper.build_variable_exclusion_pattern
create_dot_notation_pattern_with_domain_exclusion = regex_helper.create_dot_notation_pattern_with_domain_exclusion

# Export type analysis patterns
extract_numeric_parts_advanced = regex_helper.extract_numeric_parts_advanced
is_strict_datetime_string = regex_helper.is_strict_datetime_string
is_strict_version_string = regex_helper.is_strict_version_string
extract_version_numeric_parts = regex_helper.extract_version_numeric_parts

# Export schema validation patterns
get_variable_value_pattern = regex_helper.get_variable_value_pattern
get_variable_name_pattern = regex_helper.get_variable_name_pattern
get_entity_id_schema_pattern = regex_helper.get_entity_id_schema_pattern
get_icon_pattern = regex_helper.get_icon_pattern

# Export entity reference replacement patterns
replace_entity_id_with_variable = regex_helper.replace_entity_id_with_variable
convert_entity_id_to_variable_name = regex_helper.convert_entity_id_to_variable_name
search_and_replace_with_pattern = regex_helper.search_and_replace_with_pattern
check_pattern_exists = regex_helper.check_pattern_exists

# Export aggregation and function patterns
create_aggregation_function_pattern = regex_helper.create_aggregation_function_pattern
create_aggregation_pattern_with_exclusions = regex_helper.create_aggregation_pattern_with_exclusions
extract_entity_function_calls = regex_helper.extract_entity_function_calls
create_exclusion_pattern = regex_helper.create_exclusion_pattern

# Export variable and identifier patterns
create_identifier_pattern = regex_helper.create_identifier_pattern
is_valid_variable_name = regex_helper.is_valid_variable_name
extract_potential_entity_ids = regex_helper.extract_potential_entity_ids

# Export match object replacement helpers
create_replacement_function = regex_helper.create_replacement_function
extract_match_groups = regex_helper.extract_match_groups
replace_with_function = regex_helper.replace_with_function

# Export variable resolution specific patterns
substitute_state_attributes_with_function = regex_helper.substitute_state_attributes_with_function
substitute_simple_state_with_function = regex_helper.substitute_simple_state_with_function
create_entity_pattern_from_domains = regex_helper.create_entity_pattern_from_domains

# Export commonly used patterns across modules
create_metadata_function_pattern = regex_helper.create_metadata_function_pattern
create_simple_identifier_validation_pattern = regex_helper.create_simple_identifier_validation_pattern
create_condition_parsing_pattern = regex_helper.create_condition_parsing_pattern
create_domain_validation_pattern = regex_helper.create_domain_validation_pattern
create_datetime_function_pattern = regex_helper.create_datetime_function_pattern
create_collection_function_detection_pattern = regex_helper.create_collection_function_detection_pattern
create_entity_reference_pattern_from_domains = regex_helper.create_entity_reference_pattern_from_domains
create_attribute_access_pattern = regex_helper.create_attribute_access_pattern
create_single_token_pattern = regex_helper.create_single_token_pattern
create_standalone_reference_pattern = regex_helper.create_standalone_reference_pattern
create_sensor_name_search_pattern = regex_helper.create_sensor_name_search_pattern
create_entity_id_exact_match_pattern = regex_helper.create_entity_id_exact_match_pattern
create_entity_attribute_access_pattern = regex_helper.create_entity_attribute_access_pattern

# Export centralized regex operation methods
search_pattern = regex_helper.search_pattern
substitute_pattern = regex_helper.substitute_pattern
find_all_matches = regex_helper.find_all_matches
find_all_match_objects = regex_helper.find_all_match_objects
match_pattern = regex_helper.match_pattern

# Export advanced entity and sensor operations
create_entity_exact_search_pattern = regex_helper.create_entity_exact_search_pattern
create_entity_attribute_search_pattern = regex_helper.create_entity_attribute_search_pattern
create_sensor_expression_pattern = regex_helper.create_sensor_expression_pattern
create_sensor_key_no_entity_prefix_pattern = regex_helper.create_sensor_key_no_entity_prefix_pattern
create_sensor_attribute_no_entity_prefix_pattern = regex_helper.create_sensor_attribute_no_entity_prefix_pattern
create_collection_function_extraction_pattern = regex_helper.create_collection_function_extraction_pattern
create_referenced_tokens_pattern = regex_helper.create_referenced_tokens_pattern
create_query_type_patterns = regex_helper.create_query_type_patterns
create_entity_id_and_sensor_key_patterns = regex_helper.create_entity_id_and_sensor_key_patterns
safe_entity_replacement = regex_helper.safe_entity_replacement
search_entity_in_text = regex_helper.search_entity_in_text
search_entity_attribute_in_text = regex_helper.search_entity_attribute_in_text
replace_entity_with_state = regex_helper.replace_entity_with_state
find_entity_attribute_matches = regex_helper.find_entity_attribute_matches

# Export final consolidation patterns
create_case_insensitive_pattern = regex_helper.create_case_insensitive_pattern
create_device_validation_patterns = regex_helper.create_device_validation_patterns
validate_device_field = regex_helper.validate_device_field
search_case_insensitive = regex_helper.search_case_insensitive

# Export dependency parsing domain methods
extract_entity_function_references = regex_helper.extract_entity_function_references
extract_states_dot_notation_entities = regex_helper.extract_states_dot_notation_entities
extract_direct_entity_references = regex_helper.extract_direct_entity_references
extract_variable_references = regex_helper.extract_variable_references
get_entity_function_patterns = regex_helper.get_entity_function_patterns
get_states_dot_notation_pattern = regex_helper.get_states_dot_notation_pattern
get_direct_entity_pattern = regex_helper.get_direct_entity_pattern
get_variable_references_pattern = regex_helper.get_variable_references_pattern
get_no_match_pattern = regex_helper.get_no_match_pattern
get_state_token_pattern = regex_helper.get_state_token_pattern
get_entity_lazy_resolution_pattern = regex_helper.get_entity_lazy_resolution_pattern


def extract_dependencies_safe(formula: str) -> set[str]:
    """DEPRECATED: Extract dependencies from a formula string.

    ARCHITECTURE WARNING: This function uses flawed regex-based dependency extraction
    that incorrectly splits entity IDs like 'sensor.circuit_a_power' into separate
    dependencies 'sensor' and 'circuit_a_power'.

    This function should be replaced with DependencyParser.extract_dependencies()
    which properly handles entity IDs as single dependencies.

    Args:
        formula: The formula string to analyze

    Returns:
        Set of identifier dependencies (WARNING: may split entity IDs incorrectly)
    """
    # ARCHITECTURE WARNING: This regex-based approach is flawed and splits entity IDs
    # It should be replaced with DependencyParser.extract_dependencies()

    # Find all string literals to exclude them (both in metadata and general usage)
    string_ranges = []

    # Pattern to match all string literals (single and double quotes)
    string_pattern = r"['\"]([^'\"]*)['\"]"
    for match in re.finditer(string_pattern, formula):
        string_ranges.append(match.span())

    # Python keywords and operators to exclude
    python_keywords = PYTHON_KEYWORDS | BOOLEAN_LITERALS

    # Pattern to match all identifiers
    identifier_pattern = r"\b([a-zA-Z_][a-zA-Z0-9_.]*)\b"

    dependencies = set()
    for match in re.finditer(identifier_pattern, formula):
        identifier = match.group(1)
        match_start, _ = match.span()

        # Skip if this identifier is inside a string literal
        is_in_string = any(start <= match_start < end for start, end in string_ranges)

        # Skip Python keywords
        is_keyword = identifier in python_keywords

        # Skip numeric literals (integers and floats)
        is_numeric = False
        try:
            float(identifier)
            is_numeric = True
        except ValueError:
            pass

        # Skip entity IDs (format: domain.entity_name)
        is_entity_id = (
            "." in identifier
            and len(identifier.split(".")) == 2
            and all(part.replace("_", "").replace("-", "").isalnum() for part in identifier.split("."))
        )

        if not is_in_string and not is_keyword and not is_numeric and not is_entity_id:
            dependencies.add(identifier)

    return dependencies


def extract_entity_references_from_metadata(formula: str) -> set[str]:
    """Extract entity references from metadata function calls.

    Args:
        formula: The formula string to analyze

    Returns:
        Set of entity IDs referenced in metadata functions
    """
    entity_refs = set()

    # Pattern to match metadata function calls
    # Captures: metadata('entity.id', 'attribute') or metadata(variable, 'attribute')
    metadata_pattern = r"metadata\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"][^'\"]+['\"]\s*\)"

    for match in re.finditer(metadata_pattern, formula):
        entity_id = match.group(1)
        # Only add if it looks like an entity ID (contains a dot)
        if "." in entity_id:
            entity_refs.add(entity_id)

    return entity_refs


def extract_variable_references_from_metadata(formula: str) -> set[str]:
    """Extract variable references from metadata function calls.

    Pattern: metadata\\s*\\(\\s*([a-zA-Z_][a-zA-Z0-9_]*)\\s*,\\s*['\"][^'\"]+['\"]\\s*\\)
    Input: "metadata(state, 'last_changed')" or "minutes_between(metadata(entity, 'last_updated'), now())"
    Output: Set of variable names (e.g., {'state', 'entity'})

    Used in: Should be used by formula_helpers.identify_variables_for_attribute_access
    Purpose: Identify variables in metadata() calls that need entity ID preservation
    Note: Complements create_attribute_access_pattern for dot notation

    Args:
        formula: The formula string to analyze

    Returns:
        Set of variables referenced in metadata functions
    """
    var_refs = set()

    # Pattern to match metadata function calls with variable as first parameter
    # Captures: metadata(variable_name, 'attribute')
    metadata_pattern = r"metadata\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*,\s*['\"][^'\"]+['\"]\s*\)"

    for match in re.finditer(metadata_pattern, formula):
        variable = match.group(1)
        # Only add if it doesn't look like a quoted entity ID
        var_refs.add(variable)

    return var_refs
