"""AST Analysis Service for parse-once formula optimization.

This service provides comprehensive AST-based analysis to evaluation phases
while maintaining clean architecture and phase independence.
"""

import ast
from dataclasses import dataclass, field
import logging
from typing import Any

from .constants_entities import COMMON_ENTITY_DOMAINS
from .constants_formula import FORMULA_RESERVED_WORDS
from .dynamic_query import DynamicQuery
from .formula_compilation_cache import CompiledFormula, FormulaCompilationCache
from .regex_helper import regex_helper

_LOGGER = logging.getLogger(__name__)

# Get valid query types from regex helper
_QUERY_TYPE_PATTERNS = regex_helper.create_query_type_patterns()
VALID_QUERY_TYPES = frozenset(_QUERY_TYPE_PATTERNS.keys())

# Collection/aggregation functions for AST analysis
# These are the functions that should be tracked as collection functions
AGGREGATION_FUNCTIONS = frozenset({"sum", "avg", "mean", "min", "max", "count", "median", "stdev", "std", "var"})


@dataclass
class FormulaAnalysis:
    """Complete analysis of a formula's AST."""

    variables: set[str] = field(default_factory=set)
    entity_references: set[str] = field(default_factory=set)
    dependencies: set[str] = field(default_factory=set)
    metadata_calls: list[tuple[str, str]] = field(default_factory=list)
    collection_functions: list[str] = field(default_factory=list)
    cross_sensor_refs: set[str] = field(default_factory=set)
    function_calls: list[tuple[str, list[str]]] = field(default_factory=list)
    has_state_token: bool = False
    has_self_reference: bool = False


class ComprehensiveASTVisitor(ast.NodeVisitor):
    """AST visitor that extracts all relevant information in a single pass."""

    def __init__(self) -> None:
        """Initialize the visitor."""
        self.variables: set[str] = set()
        self.entity_references: set[str] = set()
        self.dependencies: set[str] = set()
        self.metadata_calls: list[tuple[str, str]] = []
        self.collection_functions: list[str] = []
        self.cross_sensor_refs: set[str] = set()
        self.function_calls: list[tuple[str, list[str]]] = []
        self.has_state_token: bool = False
        self.has_self_reference: bool = False
        self._in_string_context = False
        self._function_names: set[str] = set()  # Track function names to exclude from variables

    def visit_Name(self, node: ast.Name) -> None:
        """Extract variable names and special tokens."""
        if isinstance(node.ctx, ast.Load) and not self._in_string_context:
            var_name = node.id

            # Check if this looks like a domain name that would be part of an entity ID
            is_likely_domain = var_name in COMMON_ENTITY_DOMAINS or var_name == "states"

            # Check for special tokens first
            if var_name == "state":
                self.has_state_token = True
                # 'state' is always treated as a variable and dependency
                self.variables.add(var_name)
                self.dependencies.add(var_name)
            elif var_name == "self":
                self.has_self_reference = True
                # 'self' is always treated as a variable and dependency
                self.variables.add(var_name)
                self.dependencies.add(var_name)
            elif var_name not in self._function_names and not is_likely_domain and not self._is_builtin_or_function(var_name):
                # Regular variables (excluding builtins like 'on', 'off')
                self.variables.add(var_name)
                self.dependencies.add(var_name)

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Extract entity.attribute patterns and attribute access."""
        if isinstance(node.value, ast.Name) and not self._in_string_context:
            base_name = node.value.id
            attr_name = node.attr

            # Check for entity ID pattern (domain.entity)
            full_ref = f"{base_name}.{attr_name}"
            if self._is_entity_id_pattern(full_ref):
                self.entity_references.add(full_ref)
                self.dependencies.add(full_ref)
                # Don't add the base name as a separate dependency if it's part of an entity ID
                return

            # Track attribute access for dependency analysis
            # Check if this looks like a domain name that would be part of an entity ID
            is_likely_domain = base_name in COMMON_ENTITY_DOMAINS or base_name == "states"

            if not is_likely_domain:
                # This is variable.attribute access - add base as variable and dependency
                self.variables.add(base_name)
                if not self._is_builtin_or_function(base_name):
                    self.dependencies.add(base_name)

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Extract function calls including metadata() and collection functions."""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id

            # Track function name to exclude from variables
            self._function_names.add(func_name)

            # Extract function arguments
            extracted_args: list[str] = []
            for arg in node.args:
                arg_value = self._extract_arg_value(arg)
                if arg_value is not None:
                    extracted_args.append(arg_value)

            self.function_calls.append((func_name, extracted_args))

            # Handle specific function types
            if func_name == "metadata" and len(extracted_args) >= 2:
                # metadata(entity, 'attribute')
                entity_arg = extracted_args[0] if extracted_args else None
                attr_arg = extracted_args[1] if len(extracted_args) > 1 else None
                if entity_arg and attr_arg:
                    self.metadata_calls.append((entity_arg, attr_arg))
                    # Add entity to dependencies if it's a variable
                    if not self._is_string_literal(node.args[0]):
                        self.dependencies.add(entity_arg)

            elif func_name in AGGREGATION_FUNCTIONS:
                # Collection/aggregation functions
                self.collection_functions.append(func_name)
                # Add all arguments as dependencies
                for arg_str in extracted_args:
                    if not arg_str.startswith(("'", '"')):
                        self.dependencies.add(arg_str)

            elif func_name == "entity":
                # entity('sensor.name') function calls
                if extracted_args and self._is_string_literal(node.args[0]):
                    entity_id = extracted_args[0].strip("'\"")
                    self.entity_references.add(entity_id)
                    self.dependencies.add(entity_id)

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        """Track when we're in a string context."""
        if isinstance(node.value, str):
            # Don't extract variables from string literals
            pass
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Extract subscript access like states['sensor.name'] but avoid treating subscript base as variable."""
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "states"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            # states['sensor.name'] pattern
            entity_id = node.slice.value
            self.entity_references.add(entity_id)
            self.dependencies.add(entity_id)
            # Don't visit the 'states' name node to avoid adding it as a variable
            self.visit(node.slice)
        else:
            # For other subscript patterns like tabs[3], don't treat the base as a variable
            # Only visit the slice part
            self.visit(node.slice)

    def _extract_arg_value(self, node: ast.AST) -> str | None:
        """Extract value from an AST node (string literal or variable name)."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            # Handle nested attributes like sensor.attribute
            return f"{node.value.id}.{node.attr}"
        return None

    def _is_string_literal(self, node: ast.AST) -> bool:
        """Check if node is a string literal."""
        return isinstance(node, ast.Constant) and isinstance(node.value, str)

    def _is_entity_id_pattern(self, text: str) -> bool:
        """Check if text matches entity_id pattern (domain.entity)."""
        if not text or not isinstance(text, str):
            return False

        parts = text.split(".")
        if len(parts) >= 2:
            # Basic entity ID validation
            domain = parts[0]
            return domain in COMMON_ENTITY_DOMAINS
        return False

    def _is_builtin_or_function(self, name: str) -> bool:
        """Check if name is a built-in constant or function."""
        # Include HA boolean constants that should not be treated as variables
        ha_boolean_constants = {"on", "off"}
        return name in FORMULA_RESERVED_WORDS or name in ha_boolean_constants


class FormulaASTAnalysisService:
    """Service that provides AST-based analysis to evaluation phases.

    This service maintains the parse-once philosophy while preserving
    phase independence and clean architecture.
    """

    def __init__(self, compilation_cache: FormulaCompilationCache | None = None):
        """Initialize the AST analysis service.

        Args:
            compilation_cache: Optional compilation cache to use.
                             If not provided, creates a new one.
        """
        self._compilation_cache = compilation_cache or FormulaCompilationCache()
        self._analysis_cache: dict[str, FormulaAnalysis] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def validate_formula_syntax(self, formula: str) -> None:
        """Validate formula syntax by attempting to parse it.

        This method is specifically for validation and will raise SyntaxError
        for invalid formulas, unlike get_formula_analysis which handles errors gracefully.

        Args:
            formula: The formula string to validate

        Raises:
            SyntaxError: If the formula has invalid syntax
        """
        try:
            self._compilation_cache.get_compiled_formula(formula)
        except SyntaxError:
            # Re-raise syntax errors for validation
            raise
        except Exception:
            # Other errors are not syntax issues, so don't raise them
            pass

    def get_formula_analysis(self, formula: str) -> FormulaAnalysis:
        """Get comprehensive analysis for a formula (cached).

        This method parses the formula once and caches the analysis
        for all subsequent requests.

        Args:
            formula: The formula string to analyze

        Returns:
            Complete analysis of the formula's AST
        """
        # Handle empty or None formulas
        if not formula or not formula.strip():
            return FormulaAnalysis()

        # Check analysis cache first
        if formula in self._analysis_cache:
            self._cache_hits += 1
            return self._analysis_cache[formula]

        self._cache_misses += 1

        # Get compiled formula (this parses and caches the AST)
        try:
            compiled = self._compilation_cache.get_compiled_formula(formula)
            analysis = self._analyze_ast(compiled)
            self._analysis_cache[formula] = analysis
            return analysis
        except Exception as e:
            _LOGGER.error("Failed to analyze formula '%s': %s", formula, e)
            # Return empty analysis on error
            return FormulaAnalysis()

    def _analyze_ast(self, compiled: CompiledFormula) -> FormulaAnalysis:
        """Extract all information from AST in one pass.

        Args:
            compiled: The compiled formula with parsed AST

        Returns:
            Complete analysis of the formula
        """
        visitor = ComprehensiveASTVisitor()

        # Visit the AST to extract all information
        if compiled.parsed_ast:
            try:
                # The parsed_ast from SimpleEval is already an AST node
                visitor.visit(compiled.parsed_ast)
            except Exception as e:
                _LOGGER.error("Failed to visit AST: %s", e)

        # Build and return the analysis
        return FormulaAnalysis(
            variables=visitor.variables,
            entity_references=visitor.entity_references,
            dependencies=visitor.dependencies,
            metadata_calls=visitor.metadata_calls,
            collection_functions=visitor.collection_functions,
            cross_sensor_refs=visitor.cross_sensor_refs,
            function_calls=visitor.function_calls,
            has_state_token=visitor.has_state_token,
            has_self_reference=visitor.has_self_reference,
        )

    def clear_cache(self) -> None:
        """Clear the analysis cache."""
        self._analysis_cache.clear()
        _LOGGER.debug("Cleared AST analysis cache")

    def get_statistics(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0.0

        return {
            "analysis_cache_entries": len(self._analysis_cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": hit_rate,
            "compilation_cache_stats": self._compilation_cache.get_statistics(),
        }

    def extract_variables(self, formula: str) -> set[str]:
        """Extract variables from formula using AST analysis.

        This is a convenience method for phases that only need variables.

        Args:
            formula: The formula to analyze

        Returns:
            Set of variable names found in the formula
        """
        analysis = self.get_formula_analysis(formula)
        return analysis.variables

    def extract_dependencies(self, formula: str) -> set[str]:
        """Extract dependencies from formula using AST analysis.

        This is a convenience method for phases that only need dependencies.

        Args:
            formula: The formula to analyze

        Returns:
            Set of dependencies found in the formula
        """
        analysis = self.get_formula_analysis(formula)
        return analysis.dependencies

    def extract_metadata_calls(self, formula: str) -> list[tuple[str, str]]:
        """Extract metadata function calls from formula.

        Args:
            formula: The formula to analyze

        Returns:
            List of (entity, attribute) tuples from metadata() calls
        """
        analysis = self.get_formula_analysis(formula)
        return analysis.metadata_calls

    def is_cross_sensor_reference(self, formula: str, sensor_name: str) -> bool:
        """Check if a sensor name is referenced as a variable in the formula.

        This properly distinguishes between:
        - Variable names that happen to contain sensor names
        - Actual cross-sensor references
        - String literals containing sensor names

        Args:
            formula: The formula to analyze
            sensor_name: The sensor name to check for

        Returns:
            True if sensor_name appears as a variable reference
        """
        analysis = self.get_formula_analysis(formula)
        # Check if the sensor name appears as a variable (not in strings)
        return sensor_name in analysis.variables

    def extract_entity_references(self, formula: str) -> set[str]:
        """Extract entity references from formula using AST analysis.

        This is a convenience method that replaces the legacy DependencyParser
        extract_entity_references method.

        Args:
            formula: The formula to analyze

        Returns:
            Set of entity references found in the formula
        """
        analysis = self.get_formula_analysis(formula)
        return analysis.entity_references

    def extract_dynamic_queries(self, formula: str) -> list[DynamicQuery]:
        """Extract dynamic queries from collection function calls.

        This method analyzes collection function calls and extracts dynamic query
        patterns that need runtime resolution. Since negation syntax like !'sensor1'
        is not valid Python syntax, we use regex-based extraction before AST parsing.

        Args:
            formula: The formula to analyze

        Returns:
            List of DynamicQuery objects representing runtime queries
        """
        queries = []

        # Use regex helper for collection function pattern matching
        aggregation_pattern = regex_helper.create_aggregation_function_pattern()

        for match in aggregation_pattern.finditer(formula):
            func_name = match.group(1).lower()
            args_str = match.group(2)

            # Parse arguments - split by comma but handle quoted strings
            args = self._parse_function_arguments(args_str)

            # Extract query pattern and exclusions
            query_pattern = None
            exclusions = []

            for arg in args:
                # arg is already unquoted by _parse_function_arguments
                arg = arg.strip()
                if arg.startswith("!"):
                    # This is an exclusion pattern
                    exclusion = arg[1:]  # Remove the '!' prefix
                    exclusions.append(exclusion)
                elif self._is_query_pattern(arg):
                    # This is the main query pattern
                    query_pattern = arg

            # Create query if we found a pattern
            if query_pattern:
                query_type, pattern = self._parse_query_pattern(query_pattern)
                if query_type and pattern:
                    queries.append(
                        DynamicQuery(
                            query_type=query_type,
                            pattern=pattern,
                            function=func_name,
                            exclusions=exclusions,
                        )
                    )

        return queries

    def _is_query_pattern(self, text: str) -> bool:
        """Check if text looks like a query pattern (e.g., 'regex:pattern', 'label:value')."""
        if not isinstance(text, str):
            return False

        # Use regex helper for query pattern detection
        return regex_helper.is_query_pattern(text)

    def _parse_query_pattern(self, text: str) -> tuple[str | None, str | None]:
        """Parse a query pattern into type and pattern.

        Args:
            text: Query pattern like 'regex:door.*' or 'label:bedroom'

        Returns:
            Tuple of (query_type, pattern) or (None, None) if not a valid pattern
        """
        if ":" not in text:
            return None, None

        parts = text.split(":", 1)
        if len(parts) != 2:
            return None, None

        query_type = parts[0].strip()
        pattern = parts[1].strip()

        # Validate query type
        if query_type not in VALID_QUERY_TYPES:
            return None, None

        return query_type, pattern

    def _parse_function_arguments(self, args_str: str) -> list[str]:
        """Parse function arguments from a string, handling quoted strings and negation syntax.

        Args:
            args_str: String containing function arguments like "'device_class:power', !'sensor1'"

        Returns:
            List of argument strings with quotes removed
        """

        # Simple approach: split by comma first, then handle each part
        raw_args = [arg.strip() for arg in args_str.split(",")]

        args = []
        for raw_arg in raw_args:
            # Remove outer quotes but preserve negation
            if raw_arg.startswith("!'") and raw_arg.endswith("'"):
                # Negated single-quoted string: !'sensor1' -> !sensor1
                args.append("!" + raw_arg[2:-1])
            elif raw_arg.startswith('!"') and raw_arg.endswith('"'):
                # Negated double-quoted string: !"sensor1" -> !sensor1
                args.append("!" + raw_arg[2:-1])
            elif raw_arg.startswith("'") and raw_arg.endswith("'"):
                # Single-quoted string: 'device_class:power' -> device_class:power
                args.append(raw_arg[1:-1])
            elif raw_arg.startswith('"') and raw_arg.endswith('"'):
                # Double-quoted string: "device_class:power" -> device_class:power
                args.append(raw_arg[1:-1])
            else:
                # Unquoted string
                args.append(raw_arg)

        return args
