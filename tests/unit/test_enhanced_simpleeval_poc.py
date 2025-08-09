"""
Unit tests for Enhanced SimpleEval Proof of Concept.

This test validates that SimpleEval can be enhanced with datetime/duration functions
as specified in the simpleeval_datetime_guide.md and formula_router_architecture_redesign.md.

Tests the core functions needed for metadata integration:
- Duration creation: minutes(), hours(), days(), seconds()
- Duration calculations: minutes_between(), hours_between(), days_between()
- Current time: now(), today()
- Formatting: format_friendly(), format_date()
"""

import unittest
from datetime import datetime, date, timedelta
from simpleeval import SimpleEval, DEFAULT_FUNCTIONS


class TestEnhancedSimpleEvalPOC(unittest.TestCase):
    """Test enhanced SimpleEval with datetime/duration functions."""

    def setUp(self):
        """Set up enhanced SimpleEval instance for testing."""
        self.evaluator = self._create_enhanced_simpleeval()

    def _create_enhanced_simpleeval(self) -> SimpleEval:
        """Create enhanced SimpleEval with datetime/duration functions.

        Based on simpleeval_datetime_guide.md specification.
        """

        # Helper functions for duration calculations
        def minutes_between(start_datetime, end_datetime):
            """Calculate minutes between two datetime objects."""
            if not isinstance(start_datetime, datetime) or not isinstance(end_datetime, datetime):
                raise TypeError("Both arguments must be datetime objects")
            return (end_datetime - start_datetime).total_seconds() / 60

        def hours_between(start_datetime, end_datetime):
            """Calculate hours between two datetime objects."""
            if not isinstance(start_datetime, datetime) or not isinstance(end_datetime, datetime):
                raise TypeError("Both arguments must be datetime objects")
            return (end_datetime - start_datetime).total_seconds() / 3600

        def days_between(start_date, end_date):
            """Calculate days between two dates."""
            if not isinstance(start_date, (date, datetime)) or not isinstance(end_date, (date, datetime)):
                raise TypeError("Both arguments must be date or datetime objects")
            return (end_date - start_date).days

        def seconds_between(start_datetime, end_datetime):
            """Calculate seconds between two datetime objects."""
            if not isinstance(start_datetime, datetime) or not isinstance(end_datetime, datetime):
                raise TypeError("Both arguments must be datetime objects")
            return (end_datetime - start_datetime).total_seconds()

        def format_friendly(dt):
            """Format datetime in human-friendly format."""
            if not isinstance(dt, (date, datetime)):
                raise TypeError("dt must be a date or datetime object")
            # Check if it's specifically a datetime (not just a date)
            if isinstance(dt, datetime):
                return dt.strftime("%B %d, %Y at %I:%M %p")
            else:
                return dt.strftime("%B %d, %Y")

        def format_date(dt, format_string="%Y-%m-%d"):
            """Format datetime/date as string."""
            if not isinstance(dt, (date, datetime)):
                raise TypeError("dt must be a date or datetime object")
            return dt.strftime(format_string)

        # Create enhanced function set
        functions = DEFAULT_FUNCTIONS.copy()
        functions.update(
            {
                # Core datetime constructors
                "datetime": datetime,
                "date": date,
                "timedelta": timedelta,
                # Current time functions (essential for metadata calculations)
                "now": datetime.now,
                "today": date.today,
                # Duration creation (replaces custom Duration objects)
                "days": lambda n: timedelta(days=n),
                "hours": lambda n: timedelta(hours=n),
                "minutes": lambda n: timedelta(minutes=n),
                "seconds": lambda n: timedelta(seconds=n),
                "weeks": lambda n: timedelta(weeks=n),
                # Metadata integration functions (NEW - essential for metadata access)
                "minutes_between": minutes_between,
                "hours_between": hours_between,
                "days_between": days_between,
                "seconds_between": seconds_between,
                # Formatting functions
                "format_date": format_date,
                "format_friendly": format_friendly,
            }
        )

        # Note: This version of SimpleEval doesn't support allowed_attrs parameter
        # We'll test timedelta attributes access through our custom functions instead

        return SimpleEval(functions=functions)

    def test_duration_creation_functions(self):
        """Test duration creation functions return proper timedelta objects."""
        # Test minutes() function
        result = self.evaluator.eval("minutes(5)")
        self.assertIsInstance(result, timedelta)
        self.assertEqual(result.total_seconds(), 300)  # 5 * 60 seconds

        # Test hours() function
        result = self.evaluator.eval("hours(2)")
        self.assertIsInstance(result, timedelta)
        self.assertEqual(result.total_seconds(), 7200)  # 2 * 3600 seconds

        # Test days() function
        result = self.evaluator.eval("days(1)")
        self.assertIsInstance(result, timedelta)
        self.assertEqual(result.days, 1)

        # Test seconds() function
        result = self.evaluator.eval("seconds(30)")
        self.assertIsInstance(result, timedelta)
        self.assertEqual(result.total_seconds(), 30)

    def test_duration_arithmetic(self):
        """Test duration arithmetic operations work correctly."""
        # Test duration division (critical for metadata examples)
        result = self.evaluator.eval("minutes(5) / minutes(1)")
        self.assertEqual(result, 5.0)

        # Test duration addition
        result = self.evaluator.eval("minutes(30) + hours(1)")
        self.assertIsInstance(result, timedelta)
        self.assertEqual(result.total_seconds(), 5400)  # 30*60 + 60*60 = 5400

        # Test duration multiplication
        result = self.evaluator.eval("minutes(15) * 2")
        self.assertIsInstance(result, timedelta)
        self.assertEqual(result.total_seconds(), 1800)  # 15*60*2 = 1800

    def test_datetime_functions(self):
        """Test datetime creation and current time functions."""
        # Test datetime constructor
        result = self.evaluator.eval("datetime(2024, 1, 1, 10, 30)")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result, datetime(2024, 1, 1, 10, 30))

        # Test date constructor
        result = self.evaluator.eval("date(2024, 12, 25)")
        self.assertIsInstance(result, date)
        self.assertEqual(result, date(2024, 12, 25))

        # Test now() function (returns current time)
        result = self.evaluator.eval("now()")
        self.assertIsInstance(result, datetime)

        # Test today() function (returns current date)
        result = self.evaluator.eval("today()")
        self.assertIsInstance(result, date)

    def test_calculation_functions(self):
        """Test duration calculation functions between datetime objects."""
        # Set up test datetime objects in evaluator names
        self.evaluator.names.update(
            {
                "start_time": datetime(2024, 1, 1, 10, 0),
                "end_time": datetime(2024, 1, 1, 11, 30),
                "start_date": date(2024, 1, 1),
                "end_date": date(2024, 1, 8),
            }
        )

        # Test minutes_between
        result = self.evaluator.eval("minutes_between(start_time, end_time)")
        self.assertEqual(result, 90.0)  # 1.5 hours = 90 minutes

        # Test hours_between
        result = self.evaluator.eval("hours_between(start_time, end_time)")
        self.assertEqual(result, 1.5)  # 1.5 hours

        # Test days_between
        result = self.evaluator.eval("days_between(start_date, end_date)")
        self.assertEqual(result, 7)  # 7 days

        # Test seconds_between
        result = self.evaluator.eval("seconds_between(start_time, end_time)")
        self.assertEqual(result, 5400.0)  # 90 * 60 = 5400 seconds

    def test_formatting_functions(self):
        """Test datetime formatting functions."""
        self.evaluator.names.update(
            {
                "test_datetime": datetime(2024, 1, 1, 14, 30),
                "test_date": date(2024, 12, 25),
            }
        )

        # Test format_friendly for datetime
        result = self.evaluator.eval("format_friendly(test_datetime)")
        self.assertEqual(result, "January 01, 2024 at 02:30 PM")

        # Test format_friendly for date
        result = self.evaluator.eval("format_friendly(test_date)")
        self.assertEqual(result, "December 25, 2024")

        # Test format_date with default format
        result = self.evaluator.eval("format_date(test_date)")
        self.assertEqual(result, "2024-12-25")

    def test_metadata_integration_example(self):
        """Test real metadata integration example from metadata_access_proposal.md."""
        # Simulate metadata handler providing datetime objects
        self.evaluator.names.update(
            {
                "last_changed": datetime(2024, 1, 1, 10, 0),
                "now": datetime(2024, 1, 1, 10, 15),  # 15 minutes later
                "grace_period": 15,
            }
        )

        # Test the exact formula from metadata proposal
        result = self.evaluator.eval("minutes_between(last_changed, now)")
        self.assertEqual(result, 15.0)

        # Test grace period check
        result = self.evaluator.eval("minutes_between(last_changed, now) < grace_period")
        self.assertFalse(result)  # 15 is not < 15

        # Test with fresh data
        self.evaluator.names["now"] = datetime(2024, 1, 1, 10, 10)  # 10 minutes later
        result = self.evaluator.eval("minutes_between(last_changed, now) < grace_period")
        self.assertTrue(result)  # 10 < 15

    def test_mixed_type_operations(self):
        """Test mixed datetime/duration operations work correctly."""
        self.evaluator.names.update(
            {
                "base_time": datetime(2024, 1, 1, 10, 0),
            }
        )

        # Test datetime + timedelta
        result = self.evaluator.eval("base_time + hours(2)")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result, datetime(2024, 1, 1, 12, 0))

        # Test datetime - timedelta
        result = self.evaluator.eval("base_time - minutes(30)")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result, datetime(2024, 1, 1, 9, 30))

    def test_complex_chained_operations(self):
        """Test complex chained operations that enhanced SimpleEval should handle."""
        self.evaluator.names.update(
            {
                "start": datetime(2024, 1, 1, 9, 0),
                "end": datetime(2024, 1, 1, 17, 30),
            }
        )

        # Test complex calculation: work hours converted to minutes
        result = self.evaluator.eval("hours_between(start, end) * 60")
        self.assertEqual(result, 510.0)  # 8.5 hours * 60 = 510 minutes

        # Test conditional with calculations
        result = self.evaluator.eval("hours_between(start, end) > 8 and minutes_between(start, end) < 600")
        self.assertTrue(result)  # 8.5 > 8 and 510 < 600

    def test_yaml_integration_example(self):
        """Test the complete YAML example from simpleeval_datetime_guide.md."""
        # Simulate the context that would be provided in a real YAML evaluation
        self.evaluator.names.update(
            {
                "state": "fresh",  # Sensor state value
                "last_updated": datetime(2024, 1, 1, 10, 0),
                "now": datetime(2024, 1, 1, 10, 10),  # 10 minutes later
                "grace_period": 15,
            }
        )

        # Variable: minutes_since_update
        minutes_since = self.evaluator.eval("minutes_between(last_updated, now)")
        self.assertEqual(minutes_since, 10.0)

        # Variable: is_fresh
        self.evaluator.names["minutes_since_update"] = minutes_since
        is_fresh = self.evaluator.eval("minutes_since_update < grace_period")
        self.assertTrue(is_fresh)

        # Main formula: conditional based on freshness
        self.evaluator.names["is_fresh"] = is_fresh
        result = self.evaluator.eval("state if is_fresh else 'stale'")
        self.assertEqual(result, "fresh")

        # Attribute: format last update time
        formatted = self.evaluator.eval("format_friendly(last_updated)")
        self.assertEqual(formatted, "January 01, 2024 at 10:00 AM")

    def test_error_handling(self):
        """Test proper error handling for invalid inputs."""
        # Test minutes_between with wrong types
        with self.assertRaises(TypeError):
            self.evaluator.eval('minutes_between("not_a_datetime", now())')

        # Test hours_between with wrong types
        with self.assertRaises(TypeError):
            self.evaluator.eval("hours_between(123, now())")

        # Test format_friendly with wrong type
        with self.assertRaises(TypeError):
            self.evaluator.eval('format_friendly("not_a_datetime")')


if __name__ == "__main__":
    unittest.main()
