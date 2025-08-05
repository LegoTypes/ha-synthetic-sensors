"""
Unit tests for Clean Slate Enhanced Routing (no fallbacks).

This validates that the clean slate routing works with only 2 paths:
1. Metadata functions → MetadataHandler
2. Everything else → Enhanced SimpleEval
"""

import unittest
from unittest.mock import Mock, patch
from datetime import datetime, date, timedelta

from homeassistant.core import HomeAssistant

from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.config_models import FormulaConfig
from ha_synthetic_sensors.type_definitions import ReferenceValue


class TestCleanSlateRouting(unittest.TestCase):
    """Test clean slate routing with no fallbacks."""

    def setUp(self):
        """Set up test fixtures."""
        self.hass = Mock(spec=HomeAssistant)
        self.hass.states = Mock()
        self.hass.states.get = Mock(return_value=None)

        # Create evaluator with clean slate routing
        self.evaluator = Evaluator(self.hass)

    def test_clean_slate_numeric_formula(self):
        """Test that numeric formulas go directly to enhanced SimpleEval."""
        config = FormulaConfig(id="test_numeric", name="Test Numeric", formula="2 + 3 * 4")

        with patch.object(self.evaluator._enhanced_helper, "try_enhanced_eval", return_value=(True, 14)) as mock_enhanced:
            result = self.evaluator._execute_with_handler(config, "2 + 3 * 4", {}, {}, None)

            # Verify enhanced evaluation was called directly
            mock_enhanced.assert_called_once()
            self.assertEqual(result, 14)

    def test_clean_slate_duration_arithmetic(self):
        """Test that duration arithmetic goes directly to enhanced SimpleEval."""
        config = FormulaConfig(id="test_duration", name="Test Duration", formula="minutes(5) / minutes(1)")

        with patch.object(self.evaluator._enhanced_helper, "try_enhanced_eval", return_value=(True, 5.0)) as mock_enhanced:
            result = self.evaluator._execute_with_handler(config, "minutes(5) / minutes(1)", {}, {}, None)

            # Verify enhanced evaluation was called directly
            mock_enhanced.assert_called_once()
            self.assertEqual(result, 5.0)

    def test_clean_slate_business_days(self):
        """Test that business day functions work in enhanced SimpleEval."""
        config = FormulaConfig(id="test_business", name="Test Business", formula="add_business_days(today(), 5)")

        expected_date = date(2024, 1, 10)  # Mock result
        with patch.object(
            self.evaluator._enhanced_helper, "try_enhanced_eval", return_value=(True, expected_date)
        ) as mock_enhanced:
            result = self.evaluator._execute_with_handler(config, "add_business_days(today(), 5)", {}, {}, None)

            # Verify enhanced evaluation was called and date converted to ISO string
            mock_enhanced.assert_called_once()
            self.assertEqual(result, "2024-01-10")  # isoformat() result

    def test_clean_slate_timedelta_conversion(self):
        """Test that timedelta results are converted to seconds."""
        config = FormulaConfig(id="test_timedelta", name="Test Timedelta", formula="hours(2) + minutes(30)")

        mock_timedelta = timedelta(hours=2, minutes=30)
        with patch.object(
            self.evaluator._enhanced_helper, "try_enhanced_eval", return_value=(True, mock_timedelta)
        ) as mock_enhanced:
            result = self.evaluator._execute_with_handler(config, "hours(2) + minutes(30)", {}, {}, None)

            # Verify enhanced evaluation was called and timedelta converted to seconds
            mock_enhanced.assert_called_once()
            expected_seconds = mock_timedelta.total_seconds()
            self.assertEqual(result, expected_seconds)
            self.assertEqual(result, 9000.0)  # 2*3600 + 30*60 = 9000 seconds

    def test_clean_slate_metadata_routing(self):
        """Test that metadata functions route to MetadataHandler."""
        config = FormulaConfig(id="test_metadata", name="Test Metadata", formula="metadata(entity, 'last_changed')")

        # Mock metadata handler
        mock_metadata_handler = Mock()
        mock_metadata_handler.can_handle.return_value = True
        mock_metadata_handler.evaluate.return_value = "2024-01-01T10:00:00"

        with patch.object(self.evaluator._handler_factory, "get_handler", return_value=mock_metadata_handler):
            result = self.evaluator._execute_with_handler(config, "metadata(entity, 'last_changed')", {}, {}, None)

            # Verify metadata handler was called
            mock_metadata_handler.can_handle.assert_called_with("metadata(entity, 'last_changed')")
            mock_metadata_handler.evaluate.assert_called_once()
            self.assertEqual(result, "2024-01-01T10:00:00")

    def test_clean_slate_enhanced_simpleeval_failure(self):
        """Test that enhanced SimpleEval failure raises clear error (no fallback)."""
        config = FormulaConfig(id="test_failure", name="Test Failure", formula="unsupported_operation()")

        with patch.object(self.evaluator._enhanced_helper, "try_enhanced_eval", return_value=(False, None)):
            with self.assertRaises(ValueError) as context:
                self.evaluator._execute_with_handler(config, "unsupported_operation()", {}, {}, None)

            # Verify clear error message about formula evaluation failure
            self.assertIn("Formula evaluation failed", str(context.exception))

    def test_clean_slate_metadata_handler_unavailable(self):
        """Test that missing metadata handler raises clear error."""
        config = FormulaConfig(id="test_metadata_missing", name="Test Metadata Missing", formula="metadata(entity, 'attr')")

        with patch.object(self.evaluator._handler_factory, "get_handler", return_value=None):
            with self.assertRaises(ValueError) as context:
                self.evaluator._execute_with_handler(config, "metadata(entity, 'attr')", {}, {}, None)

            # Verify clear error message about metadata handler
            self.assertIn("Metadata formula detected but handler not available", str(context.exception))

    def test_clean_slate_always_enabled(self):
        """Test that clean slate routing is always enabled (no disable option)."""
        config = FormulaConfig(id="test_always_enabled", name="Test Always Enabled", formula="2 + 3")

        # Enhanced routing is always enabled in clean slate design
        with patch.object(self.evaluator._enhanced_helper, "try_enhanced_eval", return_value=(True, 5)) as mock_enhanced:
            result = self.evaluator._execute_with_handler(config, "2 + 3", {}, {}, None)

            # Verify enhanced evaluation was called
            mock_enhanced.assert_called_once()
            self.assertEqual(result, 5)

    def test_clean_slate_string_operations(self):
        """Test that string operations work in enhanced SimpleEval."""
        config = FormulaConfig(id="test_string", name="Test String", formula="'Hello' + ' ' + 'World'")

        with patch.object(
            self.evaluator._enhanced_helper, "try_enhanced_eval", return_value=(True, "Hello World")
        ) as mock_enhanced:
            result = self.evaluator._execute_with_handler(config, "'Hello' + ' ' + 'World'", {}, {}, None)

            # Verify enhanced evaluation was called directly
            mock_enhanced.assert_called_once()
            self.assertEqual(result, "Hello World")

    def test_clean_slate_datetime_operations(self):
        """Test that datetime operations work in enhanced SimpleEval."""
        config = FormulaConfig(id="test_datetime", name="Test Datetime", formula="now() + days(7)")

        mock_datetime = datetime(2024, 1, 8, 10, 0, 0)
        with patch.object(
            self.evaluator._enhanced_helper, "try_enhanced_eval", return_value=(True, mock_datetime)
        ) as mock_enhanced:
            result = self.evaluator._execute_with_handler(config, "now() + days(7)", {}, {}, None)

            # Verify enhanced evaluation was called and datetime converted to ISO string
            mock_enhanced.assert_called_once()
            self.assertEqual(result, "2024-01-08T10:00:00")

    def test_clean_slate_comprehensive_enhanced_functions(self):
        """Test that all enhanced functions work without any handler routing."""
        test_cases = [
            # Duration functions
            ("minutes(30)", timedelta(minutes=30), 1800.0),  # 30*60 seconds
            ("hours(2)", timedelta(hours=2), 7200.0),  # 2*3600 seconds
            # Datetime functions
            ("datetime(2024, 1, 1)", datetime(2024, 1, 1), "2024-01-01T00:00:00"),
            ("date(2024, 1, 1)", date(2024, 1, 1), "2024-01-01"),
            # Numeric operations
            ("2 + 3 * 4", 14, 14),
            ("abs(-5)", 5, 5),
            # String operations
            ("'test'.upper()", "TEST", "TEST"),
            ("'hello' + ' world'", "hello world", "hello world"),
            # Boolean operations
            ("True and False", False, False),
            ("5 > 3", True, True),
        ]

        for formula, mock_result, expected_result in test_cases:
            with self.subTest(formula=formula):
                config = FormulaConfig(id="test", name="Test", formula=formula)

                with patch.object(self.evaluator._enhanced_helper, "try_enhanced_eval", return_value=(True, mock_result)):
                    result = self.evaluator._execute_with_handler(config, formula, {}, {}, None)
                    self.assertEqual(result, expected_result)


if __name__ == "__main__":
    unittest.main()
