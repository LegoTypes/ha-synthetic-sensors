"""Unit tests for DurationFunctions class."""

import pytest

from ha_synthetic_sensors.datetime_functions.duration_functions import DurationFunctions, Duration


class TestDuration:
    """Test Duration dataclass functionality."""

    def test_duration_creation(self):
        """Test Duration object creation."""
        duration = Duration(value=5, unit="days")
        assert duration.value == 5
        assert duration.unit == "days"

    def test_duration_to_days_conversion(self):
        """Test duration conversion to days."""
        # Test all supported units
        assert Duration(86400, "seconds").to_days() == 1.0
        assert Duration(1440, "minutes").to_days() == 1.0
        assert Duration(24, "hours").to_days() == 1.0
        assert Duration(1, "days").to_days() == 1.0
        assert Duration(1, "weeks").to_days() == 7.0
        assert Duration(1, "months").to_days() == 30.44

    def test_duration_to_seconds_conversion(self):
        """Test duration conversion to seconds."""
        # Test all supported units
        assert Duration(1, "seconds").to_seconds() == 1.0
        assert Duration(1, "minutes").to_seconds() == 60.0
        assert Duration(1, "hours").to_seconds() == 3600.0
        assert Duration(1, "days").to_seconds() == 86400.0
        assert Duration(1, "weeks").to_seconds() == 604800.0
        assert Duration(1, "months").to_seconds() == pytest.approx(2630016.0)  # 30.44 * 24 * 60 * 60

    def test_duration_to_days_with_fractional_values(self):
        """Test duration to days conversion with fractional values."""
        assert Duration(0.5, "days").to_days() == 0.5
        assert Duration(12, "hours").to_days() == 0.5
        assert Duration(30, "minutes").to_days() == 0.020833333333333332  # 30/(24*60)

    def test_duration_to_seconds_with_fractional_values(self):
        """Test duration to seconds conversion with fractional values."""
        assert Duration(0.5, "seconds").to_seconds() == 0.5
        assert Duration(0.5, "minutes").to_seconds() == 30.0
        assert Duration(0.5, "hours").to_seconds() == 1800.0

    def test_duration_invalid_unit_to_days(self):
        """Test that invalid units raise ValueError for to_days()."""
        duration = Duration(1, "invalid_unit")
        with pytest.raises(ValueError, match="Unknown duration unit: invalid_unit"):
            duration.to_days()

    def test_duration_invalid_unit_to_seconds(self):
        """Test that invalid units raise ValueError for to_seconds()."""
        duration = Duration(1, "invalid_unit")
        with pytest.raises(ValueError, match="Unknown duration unit: invalid_unit"):
            duration.to_seconds()

    def test_duration_string_representation(self):
        """Test duration string representation."""
        duration = Duration(5, "days")
        assert str(duration) == "duration:days:5"

        duration = Duration(2.5, "hours")
        assert str(duration) == "duration:hours:2.5"


class TestDurationFunctions:
    """Test DurationFunctions functionality."""

    @pytest.fixture
    def duration_functions(self):
        """Create a DurationFunctions instance for testing."""
        return DurationFunctions()

    def test_initialization(self, duration_functions):
        """Test DurationFunctions initialization."""
        assert duration_functions is not None
        assert hasattr(duration_functions, "_supported_functions")
        assert isinstance(duration_functions._supported_functions, set)

    def test_supported_functions(self, duration_functions):
        """Test that all expected functions are supported."""
        expected_functions = {"seconds", "minutes", "hours", "days", "weeks", "months"}
        assert duration_functions.get_supported_functions() == expected_functions

    def test_can_handle_function(self, duration_functions):
        """Test can_handle_function returns correct results."""
        # Test supported functions
        assert duration_functions.can_handle_function("seconds") is True
        assert duration_functions.can_handle_function("minutes") is True
        assert duration_functions.can_handle_function("hours") is True
        assert duration_functions.can_handle_function("days") is True
        assert duration_functions.can_handle_function("weeks") is True
        assert duration_functions.can_handle_function("months") is True

        # Test unsupported functions
        assert duration_functions.can_handle_function("years") is False
        assert duration_functions.can_handle_function("invalid") is False
        assert duration_functions.can_handle_function("") is False

    def test_get_handler_name(self, duration_functions):
        """Test get_handler_name returns correct name."""
        assert duration_functions.get_handler_name() == "DurationFunctions"

    def test_seconds_function(self, duration_functions):
        """Test seconds() function."""
        result = duration_functions.evaluate_function("seconds", [5])
        assert result == "duration:seconds:5.0"

        result = duration_functions.evaluate_function("seconds", [0.5])
        assert result == "duration:seconds:0.5"

    def test_minutes_function(self, duration_functions):
        """Test minutes() function."""
        result = duration_functions.evaluate_function("minutes", [30])
        assert result == "duration:minutes:30.0"

        result = duration_functions.evaluate_function("minutes", [1.5])
        assert result == "duration:minutes:1.5"

    def test_hours_function(self, duration_functions):
        """Test hours() function."""
        result = duration_functions.evaluate_function("hours", [12])
        assert result == "duration:hours:12.0"

        result = duration_functions.evaluate_function("hours", [0.5])
        assert result == "duration:hours:0.5"

    def test_days_function(self, duration_functions):
        """Test days() function."""
        result = duration_functions.evaluate_function("days", [7])
        assert result == "duration:days:7.0"

        result = duration_functions.evaluate_function("days", [1.5])
        assert result == "duration:days:1.5"

    def test_weeks_function(self, duration_functions):
        """Test weeks() function."""
        result = duration_functions.evaluate_function("weeks", [2])
        assert result == "duration:weeks:2.0"

        result = duration_functions.evaluate_function("weeks", [0.5])
        assert result == "duration:weeks:0.5"

    def test_months_function(self, duration_functions):
        """Test months() function."""
        result = duration_functions.evaluate_function("months", [3])
        assert result == "duration:months:3.0"

        result = duration_functions.evaluate_function("months", [0.5])
        assert result == "duration:months:0.5"

    def test_unsupported_function(self, duration_functions):
        """Test that unsupported functions raise ValueError."""
        with pytest.raises(ValueError, match="Duration function 'years' is not supported"):
            duration_functions.evaluate_function("years", [1])

    def test_no_arguments(self, duration_functions):
        """Test that functions with no arguments raise ValueError."""
        with pytest.raises(ValueError, match="Duration function 'days' requires exactly one numeric argument"):
            duration_functions.evaluate_function("days")

        with pytest.raises(ValueError, match="Duration function 'days' requires exactly one numeric argument"):
            duration_functions.evaluate_function("days", [])

    def test_too_many_arguments(self, duration_functions):
        """Test that functions with too many arguments raise ValueError."""
        with pytest.raises(ValueError, match="Duration function 'days' requires exactly one numeric argument"):
            duration_functions.evaluate_function("days", [1, 2])

        with pytest.raises(ValueError, match="Duration function 'hours' requires exactly one numeric argument"):
            duration_functions.evaluate_function("hours", [1, 2, 3])

    def test_non_numeric_argument(self, duration_functions):
        """Test that non-numeric arguments raise ValueError."""
        with pytest.raises(ValueError, match="Duration function 'days' requires a numeric argument, got str"):
            duration_functions.evaluate_function("days", ["invalid"])

        with pytest.raises(ValueError, match="Duration function 'hours' requires a numeric argument, got list"):
            duration_functions.evaluate_function("hours", [[]])

    def test_none_argument(self, duration_functions):
        """Test that None argument raises ValueError."""
        with pytest.raises(ValueError, match="Duration function 'days' requires a numeric argument, got NoneType"):
            duration_functions.evaluate_function("days", [None])

    def test_zero_values(self, duration_functions):
        """Test that zero values work correctly."""
        result = duration_functions.evaluate_function("days", [0])
        assert result == "duration:days:0.0"

        result = duration_functions.evaluate_function("hours", [0])
        assert result == "duration:hours:0.0"

    def test_negative_values(self, duration_functions):
        """Test that negative values work correctly."""
        result = duration_functions.evaluate_function("days", [-1])
        assert result == "duration:days:-1.0"

        result = duration_functions.evaluate_function("hours", [-2.5])
        assert result == "duration:hours:-2.5"

    def test_large_values(self, duration_functions):
        """Test that large values work correctly."""
        result = duration_functions.evaluate_function("days", [1000])
        assert result == "duration:days:1000.0"

        result = duration_functions.evaluate_function("months", [12])
        assert result == "duration:months:12.0"

    def test_fractional_values(self, duration_functions):
        """Test that fractional values work correctly."""
        result = duration_functions.evaluate_function("days", [0.5])
        assert result == "duration:days:0.5"

        result = duration_functions.evaluate_function("hours", [1.75])
        assert result == "duration:hours:1.75"

    def test_string_numeric_argument(self, duration_functions):
        """Test that string numeric arguments are converted correctly."""
        result = duration_functions.evaluate_function("days", ["5"])
        assert result == "duration:days:5.0"

        result = duration_functions.evaluate_function("hours", ["2.5"])
        assert result == "duration:hours:2.5"

    def test_invalid_string_argument(self, duration_functions):
        """Test that invalid string arguments raise ValueError."""
        with pytest.raises(ValueError, match="Duration function 'days' requires a numeric argument, got str"):
            duration_functions.evaluate_function("days", ["not_a_number"])

    def test_boolean_argument(self, duration_functions):
        """Test that boolean arguments are converted to numeric values."""
        # Boolean values are converted to numeric: True -> 1.0, False -> 0.0
        result = duration_functions.evaluate_function("days", [True])
        assert result == "duration:days:1.0"

        result = duration_functions.evaluate_function("hours", [False])
        assert result == "duration:hours:0.0"

    def test_all_supported_functions_with_integer(self, duration_functions):
        """Test all supported functions with integer values."""
        functions = ["seconds", "minutes", "hours", "days", "weeks", "months"]
        for func in functions:
            result = duration_functions.evaluate_function(func, [1])
            assert result == f"duration:{func}:1.0"

    def test_all_supported_functions_with_float(self, duration_functions):
        """Test all supported functions with float values."""
        functions = ["seconds", "minutes", "hours", "days", "weeks", "months"]
        for func in functions:
            result = duration_functions.evaluate_function(func, [1.5])
            assert result == f"duration:{func}:1.5"
