"""
Unit tests for Phase 1: Enhanced SimpleEval Foundation.

This validates that the enhanced functions work correctly in the context
of the existing FormulaCompilationCache and NumericHandler.
"""

import unittest
from datetime import datetime, date, timedelta

from ha_synthetic_sensors.math_functions import MathFunctions
from ha_synthetic_sensors.formula_compilation_cache import FormulaCompilationCache


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

    def test_enhanced_vs_legacy_cache_behavior(self):
        """Test difference between enhanced and legacy cache behavior."""
        legacy_cache = FormulaCompilationCache(use_enhanced_functions=False)
        enhanced_cache = FormulaCompilationCache(use_enhanced_functions=True)

        formula = "minutes(10)"

        # Legacy should return string representation
        legacy_compiled = legacy_cache.get_compiled_formula(formula)
        legacy_result = legacy_compiled.evaluate({}, numeric_only=False)
        self.assertIsInstance(legacy_result, str)
        self.assertEqual(legacy_result, "duration:minutes:10.0")

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
        legacy_cache = FormulaCompilationCache(use_enhanced_functions=False)
        enhanced_cache = FormulaCompilationCache(use_enhanced_functions=True)

        # Test basic math - should work identically
        formula = "abs(-5) + max(1, 2, 3)"

        legacy_result = legacy_cache.get_compiled_formula(formula).evaluate({})
        enhanced_result = enhanced_cache.get_compiled_formula(formula).evaluate({})

        self.assertEqual(legacy_result, enhanced_result)
        self.assertEqual(legacy_result, 8.0)  # abs(-5) + max(1,2,3) = 5 + 3 = 8


if __name__ == "__main__":
    unittest.main()
