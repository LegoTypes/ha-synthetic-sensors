"""Tests for formula compilation cache performance and functionality."""

import time
import pytest
from unittest.mock import patch

from ha_synthetic_sensors.formula_compilation_cache import FormulaCompilationCache, CompiledFormula


class TestFormulaCompilationCache:
    """Test formula compilation cache functionality."""

    def test_cache_creation(self):
        """Test cache can be created and basic operations work."""
        cache = FormulaCompilationCache()

        # Test basic formula compilation
        formula = "a + b * 2"
        compiled = cache.get_compiled_formula(formula)

        assert isinstance(compiled, CompiledFormula)
        assert compiled.formula == formula
        assert compiled.hit_count == 0

        # Test evaluation
        result = compiled.evaluate({"a": 10, "b": 5})
        assert result == 20.0  # 10 + 5 * 2
        assert compiled.hit_count == 1

    def test_cache_hits_and_misses(self):
        """Test cache hit/miss tracking."""
        cache = FormulaCompilationCache()

        # First access - cache miss
        stats_before = cache.get_statistics()
        formula1 = "x + y"
        compiled1 = cache.get_compiled_formula(formula1)
        stats_after_miss = cache.get_statistics()

        assert stats_after_miss["misses"] == stats_before["misses"] + 1
        assert stats_after_miss["hits"] == stats_before["hits"]

        # Second access - cache hit
        compiled2 = cache.get_compiled_formula(formula1)
        stats_after_hit = cache.get_statistics()

        assert compiled1 is compiled2  # Same object
        assert stats_after_hit["hits"] == stats_after_miss["hits"] + 1
        assert stats_after_hit["misses"] == stats_after_miss["misses"]

    def test_different_formulas_cached_separately(self):
        """Test that different formulas are cached as separate entries."""
        cache = FormulaCompilationCache()

        formula1 = "a + b"
        formula2 = "a * b"

        compiled1 = cache.get_compiled_formula(formula1)
        compiled2 = cache.get_compiled_formula(formula2)

        assert compiled1 is not compiled2
        assert compiled1.formula == formula1
        assert compiled2.formula == formula2

        # Both should evaluate correctly
        context = {"a": 3, "b": 4}
        assert compiled1.evaluate(context) == 7.0  # 3 + 4
        assert compiled2.evaluate(context) == 12.0  # 3 * 4

    def test_cache_size_limit(self):
        """Test cache eviction when max size is reached."""
        cache = FormulaCompilationCache(max_entries=2)

        # Fill cache to limit
        formula1 = "a + 1"
        formula2 = "a + 2"
        compiled1 = cache.get_compiled_formula(formula1)
        compiled2 = cache.get_compiled_formula(formula2)

        # Use formula1 to increase its hit count
        compiled1.evaluate({"a": 1})
        compiled1.evaluate({"a": 1})

        stats = cache.get_statistics()
        assert stats["total_entries"] == 2

        # Add third formula - should evict the least used (formula2)
        formula3 = "a + 3"
        compiled3 = cache.get_compiled_formula(formula3)

        stats = cache.get_statistics()
        assert stats["total_entries"] == 2

        # formula1 should still be cached (higher hit count)
        compiled1_again = cache.get_compiled_formula(formula1)
        assert compiled1_again is compiled1

        # formula2 should be evicted and recompiled
        compiled2_again = cache.get_compiled_formula(formula2)
        assert compiled2_again is not compiled2

    def test_cache_clear(self):
        """Test cache clearing functionality."""
        cache = FormulaCompilationCache()

        # Add some formulas
        cache.get_compiled_formula("a + b")
        cache.get_compiled_formula("a * b")

        stats_before = cache.get_statistics()
        assert stats_before["total_entries"] == 2

        # Clear cache
        cache.clear()

        stats_after = cache.get_statistics()
        assert stats_after["total_entries"] == 0

    def test_formula_specific_clear(self):
        """Test clearing specific formulas from cache."""
        cache = FormulaCompilationCache()

        formula1 = "a + b"
        formula2 = "a * b"

        cache.get_compiled_formula(formula1)
        cache.get_compiled_formula(formula2)

        assert cache.get_statistics()["total_entries"] == 2

        # Clear specific formula
        cache.clear_formula(formula1)

        assert cache.get_statistics()["total_entries"] == 1

        # formula2 should still be cached (verify with statistics)
        stats_before_hit = cache.get_statistics()
        compiled2 = cache.get_compiled_formula(formula2)
        stats_after_hit = cache.get_statistics()
        # If it was a cache hit, hits should increase
        assert stats_after_hit["hits"] > stats_before_hit["hits"]

    @pytest.mark.performance
    def test_performance_improvement(self):
        """Test that caching provides significant performance improvement."""
        cache = FormulaCompilationCache()

        # Complex formula that benefits from parsing cache
        formula = "sqrt(a**2 + b**2) * sin(c) + cos(d) * log(e) if f > 0 else 0"
        context = {"a": 3, "b": 4, "c": 1.57, "d": 0, "e": 2.71, "f": 1}

        # Time first compilation (cache miss)
        start_time = time.perf_counter()
        compiled = cache.get_compiled_formula(formula)
        first_result = compiled.evaluate(context)
        first_time = time.perf_counter() - start_time

        # Time subsequent evaluations (cache hits)
        cached_times = []
        for _ in range(10):
            start_time = time.perf_counter()
            cached_compiled = cache.get_compiled_formula(formula)
            cached_result = cached_compiled.evaluate(context)
            cached_times.append(time.perf_counter() - start_time)

            # Results should be identical
            assert abs(cached_result - first_result) < 1e-10

        avg_cached_time = sum(cached_times) / len(cached_times)

        # Cache hits should be significantly faster than first compilation
        performance_ratio = first_time / avg_cached_time
        print(f"Performance improvement: {performance_ratio:.1f}x faster")
        print(f"First compilation: {first_time * 1000:.2f}ms")
        print(f"Average cached evaluation: {avg_cached_time * 1000:.2f}ms")

        # We expect at least 2x improvement, ideally much more
        assert performance_ratio >= 2.0, f"Expected at least 2x improvement, got {performance_ratio:.1f}x"

    def test_cache_statistics(self):
        """Test cache statistics reporting."""
        cache = FormulaCompilationCache(max_entries=10)

        stats = cache.get_statistics()
        expected_keys = {"total_entries", "hits", "misses", "hit_rate", "max_entries"}
        assert set(stats.keys()) == expected_keys

        # Initial state
        assert stats["total_entries"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0.0
        assert stats["max_entries"] == 10

        # After some operations
        formula = "a + b"
        cache.get_compiled_formula(formula)  # miss
        cache.get_compiled_formula(formula)  # hit
        cache.get_compiled_formula(formula)  # hit

        stats = cache.get_statistics()
        assert stats["total_entries"] == 1
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert abs(stats["hit_rate"] - (2 / 3 * 100)) < 0.1  # 2 hits out of 3 total * 100%

    def test_math_functions_integration(self):
        """Test that math functions are properly integrated in compiled formulas."""
        cache = FormulaCompilationCache()

        # Test formula with math functions
        formula = "sqrt(a**2 + b**2)"
        compiled = cache.get_compiled_formula(formula)

        context = {"a": 3, "b": 4}
        result = compiled.evaluate(context)

        # Should calculate hypotenuse: sqrt(3^2 + 4^2) = sqrt(9 + 16) = sqrt(25) = 5
        assert abs(result - 5.0) < 1e-10


class TestCompiledFormula:
    """Test CompiledFormula class directly."""

    def test_compiled_formula_creation(self):
        """Test CompiledFormula can be created and used."""
        from ha_synthetic_sensors.math_functions import MathFunctions

        math_functions = MathFunctions.get_builtin_functions()
        formula = "a * 2 + b"

        compiled = CompiledFormula(formula, math_functions)

        assert compiled.formula == formula
        assert compiled.hit_count == 0
        assert compiled.evaluator is not None
        assert compiled.parsed_ast is not None

    def test_hit_count_tracking(self):
        """Test that hit count is properly tracked."""
        from ha_synthetic_sensors.math_functions import MathFunctions

        math_functions = MathFunctions.get_builtin_functions()
        compiled = CompiledFormula("a + b", math_functions)

        assert compiled.hit_count == 0

        compiled.evaluate({"a": 1, "b": 2})
        assert compiled.hit_count == 1

        compiled.evaluate({"a": 3, "b": 4})
        assert compiled.hit_count == 2

    def test_context_isolation(self):
        """Test that different contexts don't interfere with each other."""
        from ha_synthetic_sensors.math_functions import MathFunctions

        math_functions = MathFunctions.get_builtin_functions()
        compiled = CompiledFormula("a + b", math_functions)

        result1 = compiled.evaluate({"a": 1, "b": 2})
        result2 = compiled.evaluate({"a": 10, "b": 20})

        assert result1 == 3.0
        assert result2 == 30.0
