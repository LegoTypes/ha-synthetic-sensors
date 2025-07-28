"""Cache for compiled formula expressions to improve evaluation performance."""

import hashlib
import logging
from typing import Any

from simpleeval import SimpleEval

from .math_functions import MathFunctions

_LOGGER = logging.getLogger(__name__)


class CompiledFormula:
    """A compiled formula with cached parsed AST."""

    def __init__(self, formula: str, math_functions: dict[str, Any]):
        """Initialize compiled formula.

        Args:
            formula: The formula string to compile
            math_functions: Math functions to include in evaluator
        """
        self.formula = formula
        self.evaluator = SimpleEval(functions=math_functions)
        # Pre-parse the formula AST for reuse
        self.parsed_ast = self.evaluator.parse(formula)
        self.hit_count = 0

    def evaluate(self, context: dict[str, Any]) -> float:
        """Evaluate the compiled formula with given context.

        Args:
            context: Variable context for evaluation

        Returns:
            Evaluation result
        """
        self.hit_count += 1
        self.evaluator.names = context or {}
        # Use the pre-parsed AST for fast evaluation
        result = self.evaluator.eval(self.formula, previously_parsed=self.parsed_ast)
        if isinstance(result, int | float):
            return float(result)
        raise ValueError(f"Expected numeric result, got {type(result).__name__}")


class FormulaCompilationCache:
    """Cache for compiled formula expressions.

    This cache stores compiled SimpleEval instances to avoid re-parsing
    formula strings on every evaluation, providing significant performance
    improvement for frequently used formulas.
    """

    def __init__(self, max_entries: int = 1000):
        """Initialize the compilation cache.

        Args:
            max_entries: Maximum number of compiled formulas to cache
        """
        self._cache: dict[str, CompiledFormula] = {}
        self._max_entries = max_entries
        self._math_functions = MathFunctions.get_builtin_functions()
        self._hits = 0
        self._misses = 0

    def get_compiled_formula(self, formula: str) -> CompiledFormula:
        """Get or create a compiled formula.

        Args:
            formula: Formula string to compile

        Returns:
            Compiled formula instance
        """
        cache_key = self._generate_cache_key(formula)

        if cache_key in self._cache:
            self._hits += 1
            _LOGGER.debug("Formula compilation cache hit for: %s", formula[:50])
            return self._cache[cache_key]

        # Cache miss - compile the formula
        self._misses += 1
        _LOGGER.debug("Formula compilation cache miss for: %s", formula[:50])

        # Check cache size limit
        if len(self._cache) >= self._max_entries:
            self._evict_oldest()

        # Compile and cache the formula
        compiled = CompiledFormula(formula, self._math_functions)
        self._cache[cache_key] = compiled

        return compiled

    def _generate_cache_key(self, formula: str) -> str:
        """Generate cache key for formula.

        Args:
            formula: Formula string

        Returns:
            Cache key
        """
        return hashlib.sha256(formula.encode()).hexdigest()

    def _evict_oldest(self) -> None:
        """Evict the least recently used formula from cache."""
        if not self._cache:
            return

        # Find formula with lowest hit count (simple LRU approximation)
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].hit_count)
        del self._cache[oldest_key]
        _LOGGER.debug("Evicted compiled formula from cache")

    def clear(self) -> None:
        """Clear all cached compiled formulas."""
        self._cache.clear()
        _LOGGER.debug("Cleared formula compilation cache")

    def clear_formula(self, formula: str) -> None:
        """Clear a specific compiled formula from cache.

        Args:
            formula: Formula string to remove from cache
        """
        cache_key = self._generate_cache_key(formula)
        if cache_key in self._cache:
            del self._cache[cache_key]
            _LOGGER.debug("Cleared compiled formula from cache: %s", formula[:50])

    def get_statistics(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Cache statistics dictionary
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0

        return {
            "total_entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "max_entries": self._max_entries,
        }
