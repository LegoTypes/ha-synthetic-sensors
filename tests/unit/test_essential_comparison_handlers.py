"""Tests for essential comparison handlers."""

import pytest
from datetime import datetime

from ha_synthetic_sensors.constants_types import TypeCategory
from ha_synthetic_sensors.type_analyzer import TypeAnalyzer
from ha_synthetic_sensors.condition_parser import ConditionParser
from ha_synthetic_sensors.exceptions import ComparisonHandlerError, UnsupportedComparisonError


class TestTypeAnalyzer:
    """Test TypeAnalyzer functionality."""

    def test_categorize_basic_types(self):
        """Test basic type categorization."""
        # Boolean (must be checked before numeric)
        assert TypeAnalyzer.categorize_type(True) == TypeCategory.BOOLEAN
        assert TypeAnalyzer.categorize_type(False) == TypeCategory.BOOLEAN

        # Numeric
        assert TypeAnalyzer.categorize_type(42) == TypeCategory.NUMERIC
        assert TypeAnalyzer.categorize_type(3.14) == TypeCategory.NUMERIC
        assert TypeAnalyzer.categorize_type(0) == TypeCategory.NUMERIC
        assert TypeAnalyzer.categorize_type(-10) == TypeCategory.NUMERIC

        # Generic strings
        assert TypeAnalyzer.categorize_type("hello") == TypeCategory.STRING
        assert TypeAnalyzer.categorize_type("") == TypeCategory.STRING
        assert TypeAnalyzer.categorize_type("simple text") == TypeCategory.STRING

        # Datetime objects
        assert TypeAnalyzer.categorize_type(datetime.now()) == TypeCategory.DATETIME

    def test_categorize_datetime_strings(self):
        """Test datetime string categorization."""
        # ISO datetime formats
        assert TypeAnalyzer.categorize_type("2024-01-01") == TypeCategory.DATETIME
        assert TypeAnalyzer.categorize_type("2024-01-01T12:30:00") == TypeCategory.DATETIME
        assert TypeAnalyzer.categorize_type("2024-01-01T12:30:00Z") == TypeCategory.DATETIME
        assert TypeAnalyzer.categorize_type("2024-01-01T12:30:00+05:00") == TypeCategory.DATETIME
        # Note: 2024/01/01 format doesn't match our strict regex patterns, becomes STRING
        assert TypeAnalyzer.categorize_type("2024/01/01") == TypeCategory.STRING

    def test_categorize_version_strings(self):
        """Test version string categorization."""
        # Semantic versions (must have 'v' prefix and n.n.n format)
        assert TypeAnalyzer.categorize_type("v1.0.0") == TypeCategory.VERSION
        assert TypeAnalyzer.categorize_type("v2.1.3") == TypeCategory.VERSION
        assert TypeAnalyzer.categorize_type("v10.15.2-beta") == TypeCategory.VERSION
        # Version strings without 'v' prefix should be STRING
        assert TypeAnalyzer.categorize_type("1.0.0") == TypeCategory.STRING
        assert TypeAnalyzer.categorize_type("2.1.3") == TypeCategory.STRING
        # Two-part versions are not valid versions, should be STRING
        assert TypeAnalyzer.categorize_type("v1.2") == TypeCategory.STRING
        assert TypeAnalyzer.categorize_type("1.2") == TypeCategory.STRING

    def test_categorize_conflict_resolution(self):
        """Test handling of ambiguous strings."""
        # 2024.01.01 is a valid 3-part version with 'v' prefix
        assert TypeAnalyzer.categorize_type("v2024.01.01") == TypeCategory.VERSION
        # Without 'v' prefix, it's not a version
        assert TypeAnalyzer.categorize_type("2024.01.01") == TypeCategory.STRING
        # 2023.12 is not valid version (only 2 parts), becomes string
        assert TypeAnalyzer.categorize_type("v2023.12") == TypeCategory.STRING
        assert TypeAnalyzer.categorize_type("2023.12") == TypeCategory.STRING
        # Clear version format (3 parts with 'v' prefix)
        assert TypeAnalyzer.categorize_type("v1.2.3") == TypeCategory.VERSION
        # Without 'v' prefix, it's not a version
        assert TypeAnalyzer.categorize_type("1.2.3") == TypeCategory.STRING

    def test_categorize_none_values(self):
        """Test that None values raise appropriate error."""
        with pytest.raises(ValueError, match="Cannot categorize None values"):
            TypeAnalyzer.categorize_type(None)

    def test_categorize_unknown_types(self):
        """Test unknown type handling."""
        assert TypeAnalyzer.categorize_type(complex(1, 2)) == TypeCategory.UNKNOWN
        assert TypeAnalyzer.categorize_type([1, 2, 3]) == TypeCategory.UNKNOWN
        assert TypeAnalyzer.categorize_type({"key": "value"}) == TypeCategory.UNKNOWN


class TestSeparateComparisonHandlers:
    """Test separate comparison handler functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        from ha_synthetic_sensors.comparison_handlers import (
            NumericComparisonHandler,
            DateTimeComparisonHandler,
            StringComparisonHandler,
            VersionComparisonHandler,
        )

        self.numeric_handler = NumericComparisonHandler()
        self.datetime_handler = DateTimeComparisonHandler()
        self.string_handler = StringComparisonHandler()
        self.version_handler = VersionComparisonHandler()

    def test_can_handle_numeric_comparisons(self):
        """Test numeric comparison capability detection."""
        # Should handle numeric ordering operators
        assert self.numeric_handler.can_handle(5, 10, ">")
        assert self.numeric_handler.can_handle(3.14, 2.7, "<=")
        assert self.numeric_handler.can_handle(100, 50, ">=")
        assert self.numeric_handler.can_handle(1, 1, "<")

        # Should now handle equality (part of type-specific handlers)
        assert self.numeric_handler.can_handle(5, 10, "==")
        assert self.numeric_handler.can_handle(5, 10, "!=")

    def test_can_handle_datetime_comparisons(self):
        """Test datetime comparison capability detection."""
        dt1 = datetime(2024, 1, 1)
        dt2 = datetime(2024, 12, 31)

        # Same-type datetime comparisons
        assert self.datetime_handler.can_handle(dt1, dt2, ">")
        assert self.datetime_handler.can_handle("2024-01-01", "2023-12-31", ">=")

        # Cross-type datetime/string comparisons
        assert self.datetime_handler.can_handle(dt1, "2024-01-01", "<")
        assert self.datetime_handler.can_handle("2024-01-01T10:00:00Z", dt2, "<=")

    def test_can_handle_version_comparisons(self):
        """Test version comparison capability detection."""
        # Same-type version comparisons (require 'v' prefix)
        assert self.version_handler.can_handle("v1.0.0", "v2.0.0", "<")
        assert self.version_handler.can_handle("v2.1.0", "v1.0.0", ">")

        # Cross-type version/string comparisons (require 'v' prefix)
        assert self.version_handler.can_handle("v2.1.0", "v1.0.0", ">=")
        assert self.version_handler.can_handle("v1.0.0", "v2.0.0", "<=")

    def test_can_handle_string_comparisons(self):
        """Test string comparison capability detection."""
        # Should handle string equality and containment operators
        assert self.string_handler.can_handle("hello", "world", "==")
        assert self.string_handler.can_handle("hello", "world", "!=")
        assert self.string_handler.can_handle("Living", "Living Room", "in")
        assert self.string_handler.can_handle("Kitchen", "Living Room", "not in")

        # Should not handle ordering operators
        assert not self.string_handler.can_handle("hello", "world", ">")
        assert not self.string_handler.can_handle("hello", "world", "<=")

        # Should not handle non-string types
        assert not self.string_handler.can_handle(5, 10, "==")
        assert not self.string_handler.can_handle(datetime(2024, 1, 1), "test", "==")

    def test_can_handle_unsupported_combinations(self):
        """Test that unsupported type combinations are rejected."""
        # Numeric vs string (no conversion)
        assert not self.numeric_handler.can_handle(5, "text", ">")
        assert not self.numeric_handler.can_handle("text", 10, "<")

        # Boolean vs numeric (no conversion) - numeric handler shouldn't handle booleans
        assert not self.numeric_handler.can_handle(True, 42, ">")
        assert not self.numeric_handler.can_handle(False, 3.14, "<=")

        # None values
        assert not self.numeric_handler.can_handle(None, 5, ">")
        assert not self.numeric_handler.can_handle(5, None, "<")

    def test_compare_numeric_operations(self):
        """Test numeric comparison operations."""
        # Integer comparisons
        assert self.numeric_handler.compare(10, 5, ">") is True
        assert self.numeric_handler.compare(5, 10, ">") is False
        assert self.numeric_handler.compare(5, 5, ">=") is True
        assert self.numeric_handler.compare(5, 10, "<=") is True

        # Float comparisons
        assert self.numeric_handler.compare(3.14, 2.7, ">") is True
        assert self.numeric_handler.compare(2.0, 2.0, ">=") is True
        assert self.numeric_handler.compare(1.5, 2.5, "<") is True

        # Mixed int/float
        assert self.numeric_handler.compare(5, 4.9, ">") is True
        assert self.numeric_handler.compare(3.0, 3, ">=") is True

    def test_compare_datetime_operations(self):
        """Test datetime comparison operations."""
        dt1 = datetime(2024, 1, 1, 10, 0, 0)
        dt2 = datetime(2024, 1, 1, 12, 0, 0)

        # Datetime object comparisons
        assert self.datetime_handler.compare(dt2, dt1, ">") is True
        assert self.datetime_handler.compare(dt1, dt2, "<") is True
        assert self.datetime_handler.compare(dt1, dt1, ">=") is True

        # String datetime comparisons
        assert self.datetime_handler.compare("2024-01-02", "2024-01-01", ">") is True
        assert self.datetime_handler.compare("2024-01-01T10:00:00", "2024-01-01T12:00:00", "<") is True

        # Mixed datetime/string comparisons
        assert self.datetime_handler.compare(dt1, "2024-01-01T09:00:00", ">") is True
        assert self.datetime_handler.compare("2024-01-01T11:00:00", dt1, ">") is True

    def test_compare_string_operations(self):
        """Test string comparison operations."""
        # String equality operations
        assert self.string_handler.compare("hello", "hello", "==") is True
        assert self.string_handler.compare("hello", "world", "==") is False
        assert self.string_handler.compare("hello", "world", "!=") is True
        assert self.string_handler.compare("hello", "hello", "!=") is False

        # String containment operations
        assert self.string_handler.compare("Living", "Living Room Light", "in") is True
        assert self.string_handler.compare("Kitchen", "Living Room Light", "in") is False
        assert self.string_handler.compare("Kitchen", "Living Room Light", "not in") is True
        assert self.string_handler.compare("Living", "Living Room Light", "not in") is False

        # Edge cases
        assert self.string_handler.compare("", "any string", "in") is True  # Empty string is in any string
        assert self.string_handler.compare("exact", "exact", "in") is True  # String contains itself
        assert self.string_handler.compare("case", "CaseInsensitive", "in") is False  # Case sensitive

    def test_compare_version_operations(self):
        """Test version comparison operations."""
        # Basic semantic version comparisons (require 'v' prefix)
        assert self.version_handler.compare("v2.0.0", "v1.0.0", ">") is True
        assert self.version_handler.compare("v1.0.0", "v2.0.0", "<") is True
        assert self.version_handler.compare("v1.0.0", "v1.0.0", ">=") is True

        # Version prefixes
        assert self.version_handler.compare("v2.1.0", "v1.0.0", ">") is True
        assert self.version_handler.compare("v1.0.0", "v2.0.0", "<") is True

        # Complex versions
        assert self.version_handler.compare("v2.1.3", "v2.1.2", ">") is True
        assert self.version_handler.compare("v1.15.0", "v1.2.0", ">") is True  # 15 > 2

    def test_compare_unsupported_operations(self):
        """Test that unsupported operations raise appropriate errors."""
        # Unsupported type combinations for numeric handler
        with pytest.raises(UnsupportedComparisonError):
            self.numeric_handler.compare(5, "text", ">")

        with pytest.raises(UnsupportedComparisonError):
            self.numeric_handler.compare(True, 42, "<")

        # Invalid datetime strings for datetime handler
        with pytest.raises(UnsupportedComparisonError):
            self.datetime_handler.compare("not-a-date", "2024-01-01", ">")

        # Invalid version strings for version handler (no 'v' prefix)
        with pytest.raises(UnsupportedComparisonError):
            self.version_handler.compare("not-a-version", "v1.0.0", ">")

        # Version strings without 'v' prefix should fail
        with pytest.raises(UnsupportedComparisonError):
            self.version_handler.compare("1.0.0", "v1.0.0", ">")

        with pytest.raises(UnsupportedComparisonError):
            self.version_handler.compare("v1.0.0", "1.0.0", ">")

        # Mixed version/string comparisons should fail (strict 'v' requirement)
        with pytest.raises(UnsupportedComparisonError):
            self.version_handler.compare("v1.0.0", "2.0.0", ">")

        with pytest.raises(UnsupportedComparisonError):
            self.version_handler.compare("1.0.0", "v2.0.0", ">")

    def test_datetime_conversion_edge_cases(self):
        """Test datetime conversion edge cases."""
        # ISO format with Z suffix
        assert self.datetime_handler.compare("2024-01-01T12:00:00Z", "2024-01-01T10:00:00Z", ">") is True

        # ISO format with timezone offset
        assert self.datetime_handler.compare("2024-01-01T12:00:00+05:00", "2024-01-01T10:00:00+05:00", ">") is True

        # Date only formats
        assert self.datetime_handler.compare("2024-01-02", "2024-01-01", ">") is True

    def test_version_parsing_edge_cases(self):
        """Test version parsing edge cases."""
        # Version with 'v' prefix
        assert self.version_handler.compare("v1.2.3", "v1.2.2", ">") is True

        # Three-part versions (required format with 'v' prefix)
        assert self.version_handler.compare("v2.1.0", "v2.0.0", ">") is True

        # Version with pre-release info
        assert self.version_handler.compare("v2.0.0-beta", "v1.9.9", ">") is True


class TestConditionParserIntegration:
    """Test integration with ConditionParser."""

    def test_compare_values_numeric(self):
        """Test numeric comparisons through ConditionParser."""
        # Existing numeric functionality should still work
        assert ConditionParser.compare_values(10, ">", 5) is True
        assert ConditionParser.compare_values(5, "<=", 10) is True
        assert ConditionParser.compare_values(5, "==", 5) is True
        assert ConditionParser.compare_values(5, "!=", 10) is True

    def test_compare_values_datetime(self):
        """Test datetime comparisons through ConditionParser."""
        # New datetime functionality
        assert ConditionParser.compare_values("2024-01-02", ">", "2024-01-01") is True
        assert ConditionParser.compare_values("2024-01-01T10:00:00Z", "<", "2024-01-01T12:00:00Z") is True

        # Datetime equality
        assert ConditionParser.compare_values("2024-01-01", "==", "2024-01-01") is True
        assert ConditionParser.compare_values("2024-01-01", "!=", "2024-01-02") is True

    def test_compare_values_version(self):
        """Test version comparisons through ConditionParser."""
        # New version functionality (require 'v' prefix)
        assert ConditionParser.compare_values("v2.0.0", ">", "v1.0.0") is True
        assert ConditionParser.compare_values("v1.2.0", ">=", "v1.1.0") is True

        # Version equality
        assert ConditionParser.compare_values("v1.0.0", "==", "v1.0.0") is True
        assert ConditionParser.compare_values("v1.0.0", "!=", "v2.0.0") is True

    def test_compare_values_error_handling(self):
        """Test error handling in ConditionParser."""
        # Unsupported type combinations should raise ComparisonHandlerError
        with pytest.raises(ComparisonHandlerError):
            ConditionParser.compare_values(5, ">", "text")

        # Boolean vs numeric now converts to numeric comparison (True=1.0, 42=42.0)
        # This is a valid comparison after normalization
        result = ConditionParser.compare_values(True, "<", 42)
        assert result is True  # True (1.0) < 42 (42.0)

        # String vs numeric also converts to numeric if string is numeric
        result = ConditionParser.compare_values("10", ">", 5)
        assert result is True  # "10" (10.0) > 5 (5.0)

        # Mixed version/string comparisons should be rejected (strict 'v' requirement)
        with pytest.raises(UnsupportedComparisonError):
            ConditionParser.compare_values("v1.0.0", ">", "2.0.0")

        with pytest.raises(UnsupportedComparisonError):
            ConditionParser.compare_values("1.0.0", ">", "v2.0.0")

    def test_compare_values_equality_fallback(self):
        """Test that equality operations work with improved normalization."""
        # String equality (no ordering)
        assert ConditionParser.compare_values("hello", "==", "hello") is True
        assert ConditionParser.compare_values("hello", "!=", "world") is True

        # Boolean equality
        assert ConditionParser.compare_values(True, "==", True) is True
        assert ConditionParser.compare_values(True, "!=", False) is True

        # Numeric string vs numeric equality - now works correctly!
        assert ConditionParser.compare_values("5", "==", 5) is True  # Both become 5.0
        assert ConditionParser.compare_values("5", "!=", 5) is False  # Both become 5.0
        assert ConditionParser.compare_values("6", "!=", 5) is True  # 6.0 != 5.0

        # Boolean vs numeric equality - now works correctly!
        assert ConditionParser.compare_values(True, "==", 1) is True  # Both become 1.0
        assert ConditionParser.compare_values(False, "==", 0) is True  # Both become 0.0


class TestFormulaBasedEvaluation:
    """Test that formula-based evaluation works as the core design principle."""

    def test_numeric_reduction_priority(self):
        """Test that numeric reduction has highest priority in formula evaluation."""
        # Pure numeric comparisons work as expected
        assert ConditionParser.compare_values(85, ">=", 80) is True
        assert ConditionParser.compare_values(75, "<", 80) is True
        assert ConditionParser.compare_values(3.14, ">", 3.0) is True

        # String-to-numeric reduction enables mathematical operations
        assert ConditionParser.compare_values("85", ">=", 80) is True  # "85" → 85.0
        assert ConditionParser.compare_values("75", "<", "80") is True  # Both → numeric
        assert ConditionParser.compare_values("3.14", ">", 3) is True  # "3.14" → 3.14

        # Boolean-to-numeric reduction enables logical-mathematical operations
        assert ConditionParser.compare_values(True, "==", 1) is True  # True → 1.0
        assert ConditionParser.compare_values(False, "==", 0) is True  # False → 0.0
        assert ConditionParser.compare_values(True, ">", 0) is True  # 1.0 > 0.0

    def test_datetime_reduction_when_numeric_fails(self):
        """Test that datetime reduction works when numeric reduction not possible."""
        # Datetime string comparisons
        assert ConditionParser.compare_values("2024-01-02", ">", "2024-01-01") is True
        assert ConditionParser.compare_values("2024-01-01T10:00:00Z", "<", "2024-01-01T12:00:00Z") is True

    def test_version_reduction_when_datetime_fails(self):
        """Test that version reduction works when higher priorities fail."""
        # Version string comparisons (require 'v' prefix)
        assert ConditionParser.compare_values("v2.0.0", ">", "v1.0.0") is True
        assert ConditionParser.compare_values("v1.2.0", ">=", "v1.1.0") is True

    def test_string_fallback_when_all_reductions_fail(self):
        """Test that string fallback works when no reductions possible."""
        # Non-numeric, non-datetime, non-version strings
        assert ConditionParser.compare_values("on", "==", "on") is True
        assert ConditionParser.compare_values("off", "!=", "on") is True

    def test_formula_friendly_mixed_types(self):
        """Test that mixed types work in formula-friendly ways."""
        # These demonstrate the power of formula-based reduction
        assert ConditionParser.compare_values("5", "==", 5) is True  # String→numeric
        assert ConditionParser.compare_values("5", "!=", 5) is False  # String→numeric
        assert ConditionParser.compare_values("10", ">", 5) is True  # String→numeric
        assert ConditionParser.compare_values(True, "!=", 0) is True  # Bool→numeric (1.0 != 0.0)
        assert ConditionParser.compare_values(False, "==", 0) is True  # Bool→numeric (0.0 == 0.0)

    def test_scientific_notation_support(self):
        """Test that scientific notation works in formula evaluation."""
        # Scientific notation should reduce to numeric
        assert ConditionParser.compare_values("1e3", "==", 1000) is True  # 1e3 → 1000.0
        assert ConditionParser.compare_values("2.5e-1", "<", 1) is True  # 0.25 < 1.0


class TestTypeReductionHierarchy:
    """Test the type reduction hierarchy explicitly."""

    def test_type_reducer_numeric_priority(self):
        """Test that TypeReducer prioritizes numeric reduction."""
        from ha_synthetic_sensors.constants_types import TypeCategory
        from ha_synthetic_sensors.type_analyzer import TypeReducer

        # Numeric cases should always reduce to numeric
        cases = [
            ("5", 3),  # string-int → numeric
            ("3.14", 2.7),  # string-float → numeric
            (True, 42),  # bool-int → numeric
            ("100", "50"),  # string-string (both numeric) → numeric
        ]

        for left, right in cases:
            type_reducer = TypeReducer()
            reduced_left, reduced_right, common_type = type_reducer.reduce_pair_for_comparison(left, right)
            assert common_type == TypeCategory.NUMERIC
            assert isinstance(reduced_left, float)
            assert isinstance(reduced_right, float)

    def test_type_reducer_fallback_hierarchy(self):
        """Test that TypeReducer follows proper fallback hierarchy."""
        from ha_synthetic_sensors.constants_types import TypeCategory
        from ha_synthetic_sensors.type_analyzer import TypeReducer

        # Test datetime fallback when numeric fails
        type_reducer = TypeReducer()
        reduced_left, reduced_right, common_type = type_reducer.reduce_pair_for_comparison("2024-01-01", "2023-12-31")
        assert common_type == TypeCategory.DATETIME

        # Test version fallback when datetime fails
        reduced_left, reduced_right, common_type = type_reducer.reduce_pair_for_comparison("v2.1.0", "v1.0.0")
        assert common_type == TypeCategory.VERSION

        # Test string fallback when all else fails
        reduced_left, reduced_right, common_type = type_reducer.reduce_pair_for_comparison("hello", "world")
        assert common_type == TypeCategory.STRING
