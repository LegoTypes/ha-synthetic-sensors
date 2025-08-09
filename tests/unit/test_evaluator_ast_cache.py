"""
Unit tests for Enhanced SimpleEval Foundation with AST Caching.

This validates that the enhanced functions work correctly in the context
of the existing FormulaCompilationCache and NumericHandler, and that
the EnhancedSimpleEvalHelper properly uses AST caching.
"""

import unittest
from datetime import datetime, date, timedelta

from ha_synthetic_sensors.math_functions import MathFunctions
from ha_synthetic_sensors.formula_compilation_cache import FormulaCompilationCache
from ha_synthetic_sensors.enhanced_formula_evaluation import EnhancedSimpleEvalHelper


class TestEnhancedFunctionsPhase1(unittest.TestCase):
    """Test Phase 1 enhanced SimpleEval foundation."""

    def test_enhanced_vs_builtin_duration_functions(self):
        """Test that enhanced functions return timedelta objects vs strings."""
        builtin_functions = MathFunctions.get_builtin_functions()
        enhanced_functions = MathFunctions.get_all_functions()

        # Test builtin (legacy) duration functions return strings
        builtin_minutes = builtin_functions["minutes"](5)
        self.assertIsInstance(builtin_minutes, str)
        self.assertEqual(builtin_minutes, "duration:minutes:5.0")

        # Test enhanced duration functions return timedelta objects
        enhanced_minutes = enhanced_functions["minutes"](5)
        self.assertIsInstance(enhanced_minutes, timedelta)
        self.assertEqual(enhanced_minutes.total_seconds(), 300)  # 5 minutes = 300 seconds

    def test_enhanced_duration_arithmetic(self):
        """Test that enhanced duration functions enable arithmetic operations."""
        enhanced_functions = MathFunctions.get_all_functions()

        five_minutes = enhanced_functions["minutes"](5)
        one_minute = enhanced_functions["minutes"](1)

        # This is the key test: minutes(5) / minutes(1) should work and return 5.0
        result = five_minutes / one_minute
        self.assertEqual(result, 5.0)

        # Test other arithmetic
        result = five_minutes + enhanced_functions["hours"](1)
        self.assertEqual(result.total_seconds(), 3900)  # 5*60 + 60*60

    def test_enhanced_compilation_cache(self):
        """Test FormulaCompilationCache with enhanced functions."""
        # Create enhanced cache
        enhanced_cache = FormulaCompilationCache(use_enhanced_functions=True)

        # Test duration arithmetic formula
        formula = "minutes(5) / minutes(1)"
        compiled = enhanced_cache.get_compiled_formula(formula)

        # Should evaluate successfully and return 5.0
        result = compiled.evaluate({}, numeric_only=False)
        self.assertEqual(result, 5.0)

    def test_enhanced_vs_standard_cache_behavior(self):
        """Test difference between enhanced and standard cache behavior."""
        standard_cache = FormulaCompilationCache(use_enhanced_functions=False)
        enhanced_cache = FormulaCompilationCache(use_enhanced_functions=True)

        formula = "minutes(10)"

        # Standard should return string representation
        standard_compiled = standard_cache.get_compiled_formula(formula)
        standard_result = standard_compiled.evaluate({}, numeric_only=False)
        self.assertIsInstance(standard_result, str)
        self.assertEqual(standard_result, "duration:minutes:10.0")

        # Enhanced should return timedelta object
        enhanced_compiled = enhanced_cache.get_compiled_formula(formula)
        enhanced_result = enhanced_compiled.evaluate({}, numeric_only=False)
        self.assertIsInstance(enhanced_result, timedelta)
        self.assertEqual(enhanced_result.total_seconds(), 600)

    def test_metadata_calculation_functions(self):
        """Test that metadata calculation functions are available."""
        enhanced_functions = MathFunctions.get_all_functions()

        # Test metadata calculation functions exist
        self.assertIn("minutes_between", enhanced_functions)
        self.assertIn("hours_between", enhanced_functions)
        self.assertIn("format_friendly", enhanced_functions)

        # Test they work correctly
        start = datetime(2024, 1, 1, 10, 0)
        end = datetime(2024, 1, 1, 10, 15)

        result = enhanced_functions["minutes_between"](start, end)
        self.assertEqual(result, 15.0)

        result = enhanced_functions["format_friendly"](start)
        self.assertEqual(result, "January 01, 2024 at 10:00 AM")

    def test_complex_enhanced_formula(self):
        """Test complex formula using enhanced functions in compilation cache."""
        enhanced_cache = FormulaCompilationCache(use_enhanced_functions=True)

        # Complex duration arithmetic that should work in enhanced SimpleEval
        formula = "hours(2) + minutes(30) + seconds(45)"
        compiled = enhanced_cache.get_compiled_formula(formula)

        result = compiled.evaluate({}, numeric_only=False)
        self.assertIsInstance(result, timedelta)
        expected_seconds = 2 * 3600 + 30 * 60 + 45  # 2 hours + 30 minutes + 45 seconds
        self.assertEqual(result.total_seconds(), expected_seconds)

    def test_datetime_constructor_functions(self):
        """Test that datetime constructor functions work in enhanced cache."""
        enhanced_cache = FormulaCompilationCache(use_enhanced_functions=True)

        # Test datetime constructor
        formula = "datetime(2024, 1, 1, 10, 30)"
        compiled = enhanced_cache.get_compiled_formula(formula)
        result = compiled.evaluate({}, numeric_only=False)
        self.assertEqual(result, datetime(2024, 1, 1, 10, 30))

        # Test date constructor
        formula = "date(2024, 12, 25)"
        compiled = enhanced_cache.get_compiled_formula(formula)
        result = compiled.evaluate({}, numeric_only=False)
        self.assertEqual(result, date(2024, 12, 25))

    def test_backward_compatibility(self):
        """Test that non-duration functions work the same in both modes."""
        standard_cache = FormulaCompilationCache(use_enhanced_functions=False)
        enhanced_cache = FormulaCompilationCache(use_enhanced_functions=True)

        # Test basic math - should work identically
        formula = "abs(-5) + max(1, 2, 3)"

        standard_result = standard_cache.get_compiled_formula(formula).evaluate({})
        enhanced_result = enhanced_cache.get_compiled_formula(formula).evaluate({})

        self.assertEqual(standard_result, enhanced_result)
        self.assertEqual(standard_result, 8.0)  # abs(-5) + max(1,2,3) = 5 + 3 = 8

    def test_enhanced_helper_uses_ast_caching(self):
        """Test that EnhancedSimpleEvalHelper uses AST caching for performance."""
        helper = EnhancedSimpleEvalHelper()
        formula = "minutes(5) + hours(2)"
        context = {}

        # Get initial cache stats
        initial_stats = helper.get_compilation_cache_stats()
        initial_misses = initial_stats["misses"]

        # First evaluation should cause cache miss (AST compiled)
        success1, result1 = helper.try_enhanced_eval(formula, context)
        self.assertTrue(success1)
        self.assertIsInstance(result1, timedelta)
        self.assertEqual(result1.total_seconds(), 7500)  # 5 min + 2 hours = 300 + 7200

        # Check that we had a cache miss
        stats_after_first = helper.get_compilation_cache_stats()
        self.assertEqual(stats_after_first["misses"], initial_misses + 1)
        self.assertEqual(stats_after_first["total_entries"], 1)

        # Second evaluation should use cached AST (cache hit)
        success2, result2 = helper.try_enhanced_eval(formula, context)
        self.assertTrue(success2)
        self.assertEqual(result2, result1)

        # Check that we had a cache hit (misses unchanged, hits increased)
        stats_after_second = helper.get_compilation_cache_stats()
        self.assertEqual(stats_after_second["misses"], initial_misses + 1)  # No additional miss
        self.assertEqual(stats_after_second["hits"], stats_after_first["hits"] + 1)  # One additional hit
        self.assertGreater(stats_after_second["hit_rate"], 0)  # Hit rate should be > 0%

    def test_enhanced_helper_ast_cache_performance(self):
        """Test that AST caching provides performance benefits in EnhancedSimpleEvalHelper."""
        helper = EnhancedSimpleEvalHelper()

        # Clear cache to start fresh
        helper.clear_compiled_formulas()
        initial_stats = helper.get_compilation_cache_stats()
        self.assertEqual(initial_stats["total_entries"], 0)

        # Test multiple different formulas to verify cache functionality
        formulas = ["minutes(10) / minutes(2)", "hours(1) + minutes(30)", "abs(-5) * max(1, 2, 3)", "sin(0) + cos(0)"]

        for formula in formulas:
            # First evaluation (should be cache miss)
            success, result = helper.try_enhanced_eval(formula, {})
            self.assertTrue(success, f"Formula failed: {formula}")

        # Verify all formulas are cached
        final_stats = helper.get_compilation_cache_stats()
        self.assertEqual(final_stats["total_entries"], len(formulas))
        self.assertEqual(final_stats["misses"], len(formulas))

        # Re-evaluate all formulas (should be cache hits)
        for formula in formulas:
            success, result = helper.try_enhanced_eval(formula, {})
            self.assertTrue(success, f"Formula failed on second evaluation: {formula}")

        # Verify cache hits
        hit_stats = helper.get_compilation_cache_stats()
        self.assertEqual(hit_stats["hits"], len(formulas))  # Should have hits equal to number of formulas
        self.assertEqual(hit_stats["misses"], len(formulas))  # Misses should remain the same
        expected_hit_rate = (len(formulas) / (len(formulas) * 2)) * 100  # 50% hit rate expected
        self.assertAlmostEqual(hit_stats["hit_rate"], expected_hit_rate, places=1)

    def test_enhanced_helper_statistics_tracking(self):
        """Test that EnhancedSimpleEvalHelper tracks enhancement statistics correctly."""
        helper = EnhancedSimpleEvalHelper()

        # Get initial stats
        initial_stats = helper.get_enhancement_stats()
        initial_enhanced = initial_stats["enhanced_eval_count"]
        initial_fallback = initial_stats["fallback_count"]

        # Successful evaluation
        success, result = helper.try_enhanced_eval("minutes(5)", {})
        self.assertTrue(success)

        # Check enhanced count increased
        stats_after_success = helper.get_enhancement_stats()
        self.assertEqual(stats_after_success["enhanced_eval_count"], initial_enhanced + 1)
        self.assertEqual(stats_after_success["fallback_count"], initial_fallback)

        # Failed evaluation (invalid formula)
        success, result = helper.try_enhanced_eval("invalid_function()", {})
        self.assertFalse(success)

        # Check fallback count increased
        stats_after_failure = helper.get_enhancement_stats()
        self.assertEqual(stats_after_failure["enhanced_eval_count"], initial_enhanced + 1)
        self.assertEqual(stats_after_failure["fallback_count"], initial_fallback + 1)

        # Verify total evaluations
        total_expected = stats_after_failure["enhanced_eval_count"] + stats_after_failure["fallback_count"]
        self.assertEqual(stats_after_failure["total_evaluations"], total_expected)

    def test_enhanced_helper_cache_clearing(self):
        """Test that cache clearing works correctly in EnhancedSimpleEvalHelper."""
        helper = EnhancedSimpleEvalHelper()

        # Evaluate some formulas to populate cache
        formulas = ["minutes(5)", "hours(2)", "days(1)"]
        for formula in formulas:
            helper.try_enhanced_eval(formula, {})

        # Verify cache has entries
        stats_before_clear = helper.get_compilation_cache_stats()
        self.assertEqual(stats_before_clear["total_entries"], len(formulas))

        # Clear cache
        helper.clear_compiled_formulas()

        # Verify cache is empty
        stats_after_clear = helper.get_compilation_cache_stats()
        self.assertEqual(stats_after_clear["total_entries"], 0)
        # Note: hits/misses counters are preserved across cache clears


if __name__ == "__main__":
    unittest.main()
