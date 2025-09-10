"""AST Analysis Service for parse-once formula optimization.

This service provides comprehensive AST-based analysis to evaluation phases
while maintaining clean architecture and phase independence.
"""

import ast
from dataclasses import dataclass, field
import logging
from typing import Any

from .formula_compilation_cache import CompiledFormula, FormulaCompilationCache

_LOGGER = logging.getLogger(__name__)


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

    def __init__(self):
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
            is_likely_domain = var_name in {
                "sensor",
                "binary_sensor",
                "switch",
                "light",
                "climate",
                "cover",
                "fan",
                "lock",
                "media_player",
                "automation",
                "script",
                "input_boolean",
                "input_number",
                "input_text",
                "states",  # Also exclude 'states' which is used in states['sensor.name']
            }

            # Don't add function names or domain names as variables
            if var_name not in self._function_names and not is_likely_domain:
                self.variables.add(var_name)

                # Check for special tokens
                if var_name == "state":
                    self.has_state_token = True
                    # 'state' is a special token handled by state resolver, not a dependency
                elif var_name == "self":
                    self.has_self_reference = True
                    # 'self' is a special token for self-reference, not a dependency
                else:
                    # Add to dependencies if it's not a built-in or function
                    if not self._is_builtin_or_function(var_name):
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
            # Only add base_name if it's already a known variable (not a domain name)
            if base_name in self.variables:
                # This is variable.attribute access
                self.dependencies.add(base_name)

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Extract function calls including metadata() and collection functions."""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id

            # Track function name to exclude from variables
            self._function_names.add(func_name)

            # Extract function arguments
            args = []
            for arg in node.args:
                arg_value = self._extract_arg_value(arg)
                if arg_value is not None:
                    args.append(arg_value)

            self.function_calls.append((func_name, args))

            # Handle specific function types
            if func_name == "metadata" and len(args) >= 2:
                # metadata(entity, 'attribute')
                entity_arg = args[0] if args else None
                attr_arg = args[1] if len(args) > 1 else None
                if entity_arg and attr_arg:
                    self.metadata_calls.append((entity_arg, attr_arg))
                    # Add entity to dependencies if it's a variable (but not special tokens)
                    if not self._is_string_literal(node.args[0]) and entity_arg not in ("state", "self"):
                        self.dependencies.add(entity_arg)

            elif func_name in ["mean", "sum", "min", "max", "count", "median", "stdev"]:
                # Collection/aggregation functions
                self.collection_functions.append(func_name)
                # Add all arguments as dependencies
                for arg in args:
                    if arg and not arg.startswith(("'", '"')):
                        self.dependencies.add(arg)

            elif func_name == "entity":
                # entity('sensor.name') function calls
                if args and self._is_string_literal(node.args[0]):
                    entity_id = args[0].strip("'\"")
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
        """Extract subscript access like states['sensor.name']."""
        if isinstance(node.value, ast.Name) and node.value.id == "states":
            # states['sensor.name'] pattern
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                entity_id = node.slice.value
                self.entity_references.add(entity_id)
                self.dependencies.add(entity_id)

        self.generic_visit(node)

    def _extract_arg_value(self, node: ast.AST) -> str | None:
        """Extract value from an AST node (string literal or variable name)."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            # Handle nested attributes like sensor.attribute
            if isinstance(node.value, ast.Name):
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
            # Common HA domains
            common_domains = {
                "sensor",
                "binary_sensor",
                "switch",
                "light",
                "climate",
                "cover",
                "fan",
                "lock",
                "media_player",
                "automation",
                "script",
                "input_boolean",
                "input_number",
                "input_text",
            }
            return domain in common_domains
        return False

    def _is_builtin_or_function(self, name: str) -> bool:
        """Check if name is a built-in constant or function."""
        builtins = {
            "True",
            "False",
            "None",
            "int",
            "float",
            "str",
            "bool",
            "len",
            "abs",
            "min",
            "max",
            "sum",
            "round",
            "now",
            "today",
            "yesterday",
            "tomorrow",
            "utcnow",
            # Home Assistant boolean constants
            "on",
            "off",  # These are special constants in HA formulas
            # Add common HA formula functions
            "metadata",
            "mean",
            "median",
            "stdev",
            "count",
            "entity",
            "minutes_between",
            "hours_between",
            "days_between",
            "is_number",
            "is_string",
            "is_boolean",
            "is_datetime",
            "to_number",
            "to_string",
            "to_boolean",
            "to_datetime",
        }
        return name in builtins


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
