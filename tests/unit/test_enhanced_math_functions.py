"""
Unit tests for Enhanced Math Functions integration.

This test validates that the enhanced functions are properly integrated into
the MathFunctions class and work with the existing infrastructure.
"""

import unittest
from datetime import datetime, date, timedelta

from ha_synthetic_sensors.math_functions import MathFunctions


class TestEnhancedMathFunctions(unittest.TestCase):
    """Test enhanced math functions integration."""

    def test_enhanced_functions_available(self):
        """Test that enhanced functions are available in get_enhanced_functions()."""
        enhanced_functions = MathFunctions.get_all_functions()

        # Test duration creation functions
        self.assertIn("minutes", enhanced_functions)
        self.assertIn("hours", enhanced_functions)
        self.assertIn("days", enhanced_functions)
        self.assertIn("seconds", enhanced_functions)
        self.assertIn("weeks", enhanced_functions)

        # Test metadata integration functions
        self.assertIn("minutes_between", enhanced_functions)
        self.assertIn("hours_between", enhanced_functions)
        self.assertIn("days_between", enhanced_functions)
        self.assertIn("seconds_between", enhanced_functions)

        # Test formatting functions
        self.assertIn("format_friendly", enhanced_functions)
        self.assertIn("format_date", enhanced_functions)

        # Test datetime constructors
        self.assertIn("datetime", enhanced_functions)
        self.assertIn("date", enhanced_functions)
        self.assertIn("timedelta", enhanced_functions)

    def test_duration_creation_functions_exist(self):
        """Test that duration creation functions exist (now return actual timedelta objects)."""
        enhanced_functions = MathFunctions.get_all_functions()

        # Test that duration functions exist and return timedelta objects (Clean Slate behavior)
        from datetime import timedelta

        result = enhanced_functions["minutes"](5)
        self.assertIsInstance(result, timedelta)
        self.assertEqual(result, timedelta(minutes=5))

        result = enhanced_functions["hours"](2)
        self.assertIsInstance(result, timedelta)
        self.assertEqual(result, timedelta(hours=2))

        result = enhanced_functions["days"](1)
        self.assertIsInstance(result, timedelta)
        self.assertEqual(result, timedelta(days=1))

    def test_calculation_functions(self):
        """Test metadata integration calculation functions."""
        enhanced_functions = MathFunctions.get_all_functions()

        start_time = datetime(2024, 1, 1, 10, 0)
        end_time = datetime(2024, 1, 1, 11, 30)

        # Test minutes_between
        result = enhanced_functions["minutes_between"](start_time, end_time)
        self.assertEqual(result, 90.0)

        # Test hours_between
        result = enhanced_functions["hours_between"](start_time, end_time)
        self.assertEqual(result, 1.5)

        # Test days_between
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 8)
        result = enhanced_functions["days_between"](start_date, end_date)
        self.assertEqual(result, 7)

    def test_formatting_functions(self):
        """Test formatting functions work correctly."""
        enhanced_functions = MathFunctions.get_all_functions()

        test_datetime = datetime(2024, 1, 1, 14, 30)
        test_date = date(2024, 12, 25)

        # Test format_friendly
        result = enhanced_functions["format_friendly"](test_datetime)
        self.assertEqual(result, "January 01, 2024 at 02:30 PM")

        result = enhanced_functions["format_friendly"](test_date)
        self.assertEqual(result, "December 25, 2024")

        # Test format_date
        result = enhanced_functions["format_date"](test_date)
        self.assertEqual(result, "2024-12-25")

    def test_duration_arithmetic_compatibility(self):
        """Test that duration functions work with arithmetic operations."""
        enhanced_functions = MathFunctions.get_all_functions()

        # Create durations
        five_minutes = enhanced_functions["minutes"](5)
        one_minute = enhanced_functions["minutes"](1)

        # Test division (critical for metadata examples)
        result = five_minutes / one_minute
        self.assertEqual(result, 5.0)

        # Test addition
        two_hours = enhanced_functions["hours"](2)
        result = five_minutes + two_hours
        self.assertEqual(result.total_seconds(), 7500)  # 5*60 + 2*3600

    def test_enhanced_vs_builtin_functions(self):
        """Test that enhanced functions include all builtin functions plus new ones."""
        builtin_functions = MathFunctions.get_builtin_functions()
        enhanced_functions = MathFunctions.get_all_functions()

        # Enhanced should include all builtin functions
        for name, func in builtin_functions.items():
            self.assertIn(name, enhanced_functions)

        # Enhanced should have additional functions
        self.assertGreater(len(enhanced_functions), len(builtin_functions))

        # Check specific additions (excluding ones already in datetime registry)
        new_functions = set(enhanced_functions.keys()) - set(builtin_functions.keys())
        expected_new = {
            # These are the ones we actually added (duration creation already exists)
            "minutes_between",
            "hours_between",
            "days_between",
            "seconds_between",
            "format_friendly",
            "format_date",
            "datetime",
            "date",
            "timedelta",
        }
        self.assertTrue(expected_new.issubset(new_functions))

        # Verify duration creation functions exist (from existing datetime registry)
        existing_duration_functions = {"minutes", "hours", "days", "seconds", "weeks"}
        for func_name in existing_duration_functions:
            self.assertIn(func_name, enhanced_functions)

    def test_static_method_access(self):
        """Test that static methods can be called directly."""
        # Test direct static method calls
        start = datetime(2024, 1, 1, 10, 0)
        end = datetime(2024, 1, 1, 10, 15)

        result = MathFunctions.minutes_between(start, end)
        self.assertEqual(result, 15.0)

        result = MathFunctions.format_friendly(start)
        self.assertEqual(result, "January 01, 2024 at 10:00 AM")

    def test_error_handling(self):
        """Test proper error handling for invalid inputs."""
        # Test type errors in calculation functions
        with self.assertRaises(TypeError):
            MathFunctions.minutes_between("not_datetime", datetime.now())

        with self.assertRaises(TypeError):
            MathFunctions.format_friendly("not_datetime")


if __name__ == "__main__":
    unittest.main()
