"""Mathematical functions for synthetic sensor formulas.

This module provides a centralized collection of mathematical and utility functions
that can be used in formula evaluation, making them easily testable and maintainable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
import math
import re
from typing import Any

# Type alias for numeric values (excluding complex since it doesn't work with float())
NumericValue = int | float
IterableOrValues = NumericValue | Iterable[NumericValue]


class MathFunctions:
    """Collection of mathematical functions for formula evaluation."""

    @staticmethod
    def clamp(value: float, min_val: float, max_val: float) -> float:
        """Clamp a value between minimum and maximum bounds.

        Args:
            value: Value to clamp
            min_val: Minimum allowed value
            max_val: Maximum allowed value

        Returns:
            Clamped value
        """
        return max(min_val, min(value, max_val))

    @staticmethod
    def map_range(
        value: float,
        in_min: float,
        in_max: float,
        out_min: float,
        out_max: float,
    ) -> float:
        """Map a value from one range to another range.

        Args:
            value: Input value
            in_min: Minimum of input range
            in_max: Maximum of input range
            out_min: Minimum of output range
            out_max: Maximum of output range

        Returns:
            Mapped value in output range
        """
        if in_max == in_min:
            return out_min
        return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    @staticmethod
    def percent(part: float, whole: float) -> float:
        """Calculate percentage of part relative to whole.

        Args:
            part: The part value
            whole: The whole value

        Returns:
            Percentage (0-100), returns 0 if whole is 0
        """
        return (part / whole) * 100 if whole != 0 else 0

    @staticmethod
    def avg(*values: Any) -> float:
        """Calculate the average (mean) of values.

        Args:
            *values: Variable number of numeric values or single iterable

        Returns:
            Average value, 0.0 if no values provided
        """
        if not values:
            return 0.0

        # Handle case where a single iterable is passed
        if len(values) == 1 and hasattr(values[0], "__iter__") and not isinstance(values[0], str):
            values = tuple(values[0])

        if not values:
            return 0.0

        return sum(float(v) for v in values) / len(values)

    @staticmethod
    def mean(*values: Any) -> float:
        """Alias for avg function."""
        return MathFunctions.avg(*values)

    @staticmethod
    def safe_divide(numerator: float, denominator: float, fallback: float = 0.0) -> float:
        """Safely divide two numbers, returning fallback if denominator is zero.

        Args:
            numerator: Number to divide
            denominator: Number to divide by
            fallback: Value to return if denominator is zero

        Returns:
            Division result or fallback
        """
        return numerator / denominator if denominator != 0 else fallback

    @staticmethod
    def count(*values: Any) -> int:
        """Count the number of non-None values.

        Args:
            *values: Variable number of values or single iterable

        Returns:
            Count of non-None values
        """
        if not values:
            return 0

        # Handle case where a single iterable is passed
        if len(values) == 1 and hasattr(values[0], "__iter__") and not isinstance(values[0], str):
            values = tuple(values[0])

        return len([v for v in values if v is not None])

    @staticmethod
    def std(*values: Any) -> float:
        """Calculate standard deviation of values.

        Args:
            *values: Variable number of numeric values or single iterable

        Returns:
            Standard deviation, 0.0 if less than 2 values
        """
        if not values:
            return 0.0

        # Handle case where a single iterable is passed
        if len(values) == 1 and hasattr(values[0], "__iter__") and not isinstance(values[0], str):
            values = tuple(values[0])

        if len(values) < 2:
            return 0.0

        numeric_values = [float(v) for v in values]
        mean_val = sum(numeric_values) / len(numeric_values)
        variance = sum((x - mean_val) ** 2 for x in numeric_values) / len(numeric_values)
        return math.sqrt(variance)

    @staticmethod
    def var(*values: Any) -> float:
        """Calculate variance of values.

        Args:
            *values: Variable number of numeric values or single iterable

        Returns:
            Variance, 0.0 if less than 2 values
        """
        if not values:
            return 0.0

        # Handle case where a single iterable is passed
        if len(values) == 1 and hasattr(values[0], "__iter__") and not isinstance(values[0], str):
            values = tuple(values[0])

        if len(values) < 2:
            return 0.0

        numeric_values = [float(v) for v in values]
        mean_val = sum(numeric_values) / len(numeric_values)
        return sum((x - mean_val) ** 2 for x in numeric_values) / len(numeric_values)

    @staticmethod
    def safe_sum(*values: Any) -> float:
        """Calculate the sum of values, returning 0 for empty collections.

        Args:
            *values: Variable number of numeric values or single iterable

        Returns:
            Sum of values, 0.0 if no values provided
        """
        if not values:
            return 0.0

        # Handle case where a single iterable is passed
        if len(values) == 1 and hasattr(values[0], "__iter__") and not isinstance(values[0], str):
            values = tuple(values[0])

        if not values:
            return 0.0

        return sum(float(v) for v in values)

    @staticmethod
    def safe_min(*values: Any) -> float:
        """Calculate the minimum of values, returning 0 for empty collections.

        Args:
            *values: Variable number of numeric values or single iterable

        Returns:
            Minimum value, 0.0 if no values provided
        """
        if not values:
            return 0.0

        # Handle case where a single iterable is passed
        if len(values) == 1 and hasattr(values[0], "__iter__") and not isinstance(values[0], str):
            values = tuple(values[0])

        if not values:
            return 0.0

        return min(float(v) for v in values)

    @staticmethod
    def safe_max(*values: Any) -> float:
        """Calculate the maximum of values, returning 0 for empty collections.

        Args:
            *values: Variable number of numeric values or single iterable

        Returns:
            Maximum value, 0.0 if no values provided
        """
        if not values:
            return 0.0

        # Handle case where a single iterable is passed
        if len(values) == 1 and hasattr(values[0], "__iter__") and not isinstance(values[0], str):
            values = tuple(values[0])

        if not values:
            return 0.0

        return max(float(v) for v in values)

    # Enhanced DateTime/Duration Functions for SimpleEval Integration
    # These functions enable metadata integration and enhanced routing

    @staticmethod
    def minutes_between(start_datetime: datetime | str, end_datetime: datetime | str) -> float:
        """Calculate minutes between two datetime objects or ISO datetime strings.

        Designed for metadata formulas like:
        minutes_between(metadata(state, 'last_changed'), now())

        Args:
            start_datetime: Start datetime (datetime object or ISO string)
            end_datetime: End datetime (datetime object or ISO string)

        Returns:
            Number of minutes between the datetimes

        Raises:
            TypeError: If arguments cannot be converted to datetime objects
            ValueError: If datetime strings cannot be parsed
        """

        # Convert strings to datetime objects if needed
        if isinstance(start_datetime, str):
            try:
                # Handle both with and without timezone suffixes
                if start_datetime.endswith("Z"):
                    start_datetime = start_datetime.replace("Z", "+00:00")
                start_datetime = datetime.fromisoformat(start_datetime)
            except ValueError as e:
                raise ValueError(f"Invalid start datetime string: {start_datetime}") from e

        if isinstance(end_datetime, str):
            try:
                # Handle both with and without timezone suffixes
                if end_datetime.endswith("Z"):
                    end_datetime = end_datetime.replace("Z", "+00:00")
                end_datetime = datetime.fromisoformat(end_datetime)
            except ValueError as e:
                raise ValueError(f"Invalid end datetime string: {end_datetime}") from e

        # Handle timezone-aware vs timezone-naive datetime mismatch
        # If one is timezone-aware and the other is naive, make both timezone-aware (assume UTC)
        if start_datetime.tzinfo is None and end_datetime.tzinfo is not None:
            start_datetime = start_datetime.replace(tzinfo=UTC)
        elif start_datetime.tzinfo is not None and end_datetime.tzinfo is None:
            end_datetime = end_datetime.replace(tzinfo=UTC)

        if not isinstance(start_datetime, datetime) or not isinstance(end_datetime, datetime):
            raise TypeError("Both arguments must be datetime objects or ISO datetime strings")

        return (end_datetime - start_datetime).total_seconds() / 60

    @staticmethod
    def hours_between(start_datetime: datetime, end_datetime: datetime) -> float:
        """Calculate hours between two datetime objects.

        Designed for metadata formulas like:
        hours_between(metadata(state, 'last_updated'), now())

        Args:
            start_datetime: Start datetime
            end_datetime: End datetime

        Returns:
            Number of hours between the datetimes

        Raises:
            TypeError: If arguments are not datetime objects
        """
        if not isinstance(start_datetime, datetime) or not isinstance(end_datetime, datetime):
            raise TypeError("Both arguments must be datetime objects")
        return (end_datetime - start_datetime).total_seconds() / 3600

    @staticmethod
    def days_between(start_date: date | datetime, end_date: date | datetime) -> int:
        """Calculate days between two dates.

        Args:
            start_date: Start date or datetime
            end_date: End date or datetime

        Returns:
            Number of days between the dates

        Raises:
            TypeError: If arguments are not date or datetime objects
        """
        if not isinstance(start_date, date | datetime) or not isinstance(end_date, date | datetime):
            raise TypeError("Both arguments must be date or datetime objects")

        # Convert both to date objects for consistent subtraction
        start_dt = start_date.date() if isinstance(start_date, datetime) else start_date
        end_dt = end_date.date() if isinstance(end_date, datetime) else end_date

        return (end_dt - start_dt).days

    @staticmethod
    def seconds_between(start_datetime: datetime, end_datetime: datetime) -> float:
        """Calculate seconds between two datetime objects.

        Args:
            start_datetime: Start datetime
            end_datetime: End datetime

        Returns:
            Number of seconds between the datetimes

        Raises:
            TypeError: If arguments are not datetime objects
        """
        if not isinstance(start_datetime, datetime) or not isinstance(end_datetime, datetime):
            raise TypeError("Both arguments must be datetime objects")
        return (end_datetime - start_datetime).total_seconds()

    @staticmethod
    def format_friendly(dt: date | datetime) -> str:
        """Format datetime in human-friendly format.

        Args:
            dt: Date or datetime object to format

        Returns:
            Human-friendly formatted string

        Raises:
            TypeError: If argument is not a date or datetime object
        """
        if not isinstance(dt, date | datetime):
            raise TypeError("dt must be a date or datetime object")
        # Check if it's specifically a datetime (not just a date)
        if isinstance(dt, datetime):
            return dt.strftime("%B %d, %Y at %I:%M %p")

        return dt.strftime("%B %d, %Y")

    @staticmethod
    def format_datetime(dt: date | datetime, format_string: str = "%Y-%m-%d %H:%M:%S") -> str:
        """Format date or datetime object to string.

        Args:
            dt: Date or datetime object to format
            format_string: Format string (default: "%Y-%m-%d %H:%M:%S")

        Returns:
            Formatted string representation

        Raises:
            TypeError: If dt is not a date or datetime object
        """
        if not isinstance(dt, date | datetime):
            raise TypeError("dt must be a date or datetime object")
        return dt.strftime(format_string)

    @staticmethod
    def format_date(dt: date | datetime, format_string: str = "%Y-%m-%d") -> str:
        """Format date or datetime object to date-only string.

        Args:
            dt: Date or datetime object to format
            format_string: Format string (default: "%Y-%m-%d")

        Returns:
            Formatted date string representation

        Raises:
            TypeError: If dt is not a date or datetime object
        """
        if not isinstance(dt, date | datetime):
            raise TypeError("dt must be a date or datetime object")
        return dt.strftime(format_string)

    @staticmethod
    def as_minutes(value: timedelta | float | int) -> float:
        """Convert a timedelta to minutes, or pass through numeric values.

        Args:
            value: timedelta object or numeric value (assumed to be minutes)

        Returns:
            Value in minutes as float
        """
        if isinstance(value, timedelta):
            return value.total_seconds() / 60
        return float(value)

    @staticmethod
    def as_seconds(value: timedelta | float | int) -> float:
        """Convert a timedelta to seconds, or pass through numeric values.

        Args:
            value: timedelta object or numeric value (assumed to be seconds)

        Returns:
            Value in seconds as float
        """
        if isinstance(value, timedelta):
            return value.total_seconds()
        return float(value)

    @staticmethod
    def as_hours(value: timedelta | float | int) -> float:
        """Convert a timedelta to hours, or pass through numeric values.

        Args:
            value: timedelta object or numeric value (assumed to be hours)

        Returns:
            Value in hours as float
        """
        if isinstance(value, timedelta):
            return value.total_seconds() / 3600
        return float(value)

    @staticmethod
    def as_days(value: timedelta | float | int) -> float:
        """Convert a timedelta to days, or pass through numeric values.

        Args:
            value: timedelta object or numeric value (assumed to be days)

        Returns:
            Value in days as float
        """
        if isinstance(value, timedelta):
            return value.total_seconds() / 86400
        return float(value)

    @staticmethod
    def to_str(value: Any) -> str:
        """Convert value to string representation.

        Args:
            value: Any value to convert to string

        Returns:
            String representation of the value
        """
        return str(value)

    @staticmethod
    def upper(text: str) -> str:
        """Convert string to uppercase."""
        return str(text).upper()

    @staticmethod
    def lower(text: str) -> str:
        """Convert string to lowercase."""
        return str(text).lower()

    @staticmethod
    def title(text: str) -> str:
        """Convert string to title case."""
        return str(text).title()

    @staticmethod
    def strip(text: str) -> str:
        """Remove whitespace from both ends of string."""
        return str(text).strip()

    @staticmethod
    def startswith(text: str, prefix: str) -> bool:
        """Check if string starts with prefix."""
        return str(text).startswith(str(prefix))

    @staticmethod
    def endswith(text: str, suffix: str) -> bool:
        """Check if string ends with suffix."""
        return str(text).endswith(str(suffix))

    @staticmethod
    def replace(text: str, old: str, new: str) -> str:
        """Replace occurrences of old with new in text."""
        return str(text).replace(str(old), str(new))

    @staticmethod
    def split(text: str, separator: str | None = None) -> list[str]:
        """Split string by separator."""
        return str(text).split(separator)

    @staticmethod
    def join(items: list[str], separator: str = " ") -> str:
        """Join list items with separator."""
        return str(separator).join(str(item) for item in items)

    @staticmethod
    def contains(text: str, substring: str) -> bool:
        """Check if text contains substring."""
        return str(substring) in str(text)

    @staticmethod
    def length(text: str) -> int:
        """Get length of string (alias for len)."""
        return len(str(text))

    @staticmethod
    def isalpha(text: str) -> bool:
        """Check if string contains only alphabetic characters."""
        return str(text).isalpha()

    @staticmethod
    def isdigit(text: str) -> bool:
        """Check if string contains only digit characters."""
        return str(text).isdigit()

    @staticmethod
    def isnumeric(text: str) -> bool:
        """Check if string contains only numeric characters."""
        return str(text).isnumeric()

    @staticmethod
    def isalnum(text: str) -> bool:
        """Check if string contains only alphanumeric characters."""
        return str(text).isalnum()

    @staticmethod
    def normalize(text: str) -> str:
        """Normalize whitespace in string (multiple spaces/tabs/newlines → single space)."""
        # Replace multiple whitespace characters with single space and strip
        return re.sub(r"\s+", " ", str(text)).strip()

    @staticmethod
    def clean(text: str) -> str:
        """Remove special characters but keep alphanumeric and spaces."""
        # Keep only alphanumeric characters and spaces
        return re.sub(r"[^a-zA-Z0-9\s]", "", str(text))

    @staticmethod
    def sanitize(text: str) -> str:
        """Convert string to safe identifier format (spaces → underscores, special chars → underscores)."""
        # Replace spaces, hyphens, and common special chars with underscores
        text = str(text).strip()
        text = re.sub(r"[\s\-@#!]+", "_", text)  # spaces, hyphens, @, #, ! → underscores
        text = re.sub(r"[^a-zA-Z0-9_]", "", text)  # remove any remaining special chars
        return text

    @staticmethod
    def metadata_result(value: Any) -> Any:
        """Pass-through for pre-computed metadata results.

        The metadata handler may rewrite formulas to metadata_result(X) where X is
        either a context key (e.g., "_metadata_0") or, depending on upstream
        substitution, the literal value. To be resilient and fast, simply return
        the provided argument. SimpleEval will propagate it as-is.

        Args:
            value: Metadata payload or identifier

        Returns:
            The argument unchanged
        """
        return value

    @staticmethod
    def add_business_days(start_date: date | datetime, business_days: int) -> date | datetime:
        """Add business days (Mon-Fri) to a date."""
        if not isinstance(start_date, date | datetime):
            raise TypeError("start_date must be a date or datetime object")
        current_date = start_date
        days_added = 0
        while days_added < business_days:
            current_date += timedelta(days=1)
            if MathFunctions.is_business_day(current_date):
                days_added += 1
        return current_date

    @staticmethod
    def is_business_day(check_date: date | datetime) -> bool:
        """Check if date falls on a business day (Mon-Fri)."""
        if not isinstance(check_date, date | datetime):
            raise TypeError("check_date must be a date or datetime object")
        return check_date.weekday() < 5

    @staticmethod
    def next_business_day(from_date: datetime) -> datetime:
        """Get the next business day from given date."""
        next_day = from_date + timedelta(days=1)
        while not MathFunctions.is_business_day(next_day):
            next_day += timedelta(days=1)
        return next_day

    @staticmethod
    def previous_business_day(from_date: datetime) -> datetime:
        """Get the previous business day from given date."""
        prev_day = from_date - timedelta(days=1)
        while not MathFunctions.is_business_day(prev_day):
            prev_day -= timedelta(days=1)
        return prev_day

    @staticmethod
    def get_business_days_between(start_date: date | datetime, end_date: date | datetime) -> int:
        """Get number of business days between two dates."""
        if not isinstance(start_date, date | datetime) or not isinstance(end_date, date | datetime):
            raise TypeError("Both arguments must be date or datetime objects")
        current_date = start_date
        business_days = 0
        while current_date <= end_date:
            if MathFunctions.is_business_day(current_date):
                business_days += 1
            current_date += timedelta(days=1)
        return business_days

    @staticmethod
    def get_all_functions() -> dict[str, Callable[..., Any]]:
        """Get all available functions including enhanced duration/datetime functions.

        This is the enhanced function set that provides native Python objects
        for direct SimpleEval compatibility.

        Returns:
            Dictionary mapping function names to callable functions
        """
        # Base mathematical functions
        math_functions: dict[str, Callable[..., Any]] = {
            # Basic math
            "abs": abs,
            "min": MathFunctions.safe_min,
            "max": MathFunctions.safe_max,
            "round": round,
            "sum": MathFunctions.safe_sum,
            "float": float,
            "int": int,
            # Advanced math
            "sqrt": math.sqrt,
            "pow": pow,
            "floor": math.floor,
            "ceil": math.ceil,
            # Trigonometric functions
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            "atan2": math.atan2,
            # Hyperbolic functions
            "sinh": math.sinh,
            "cosh": math.cosh,
            "tanh": math.tanh,
            # Logarithmic functions
            "log": math.log,
            "log10": math.log10,
            "log2": math.log2,
            "exp": math.exp,
            # Statistics - using our custom implementations that handle individual args
            "mean": MathFunctions.mean,
            "count": MathFunctions.count,
            "std": MathFunctions.std,
            "var": MathFunctions.var,
            # Custom functions
            "clamp": MathFunctions.clamp,
            "map": MathFunctions.map_range,
            "percent": MathFunctions.percent,
            "avg": MathFunctions.avg,
            "safe_divide": MathFunctions.safe_divide,
        }

        # OVERRIDE duration functions to return actual timedelta objects instead of strings
        # This enables direct SimpleEval arithmetic: minutes(5) / minutes(1) -> 5.0
        enhanced_duration_functions = {
            "minutes": lambda n: timedelta(minutes=n),
            "hours": lambda n: timedelta(hours=n),
            "days": lambda n: timedelta(days=n),
            "seconds": lambda n: timedelta(seconds=n),
            "weeks": lambda n: timedelta(weeks=n),
        }

        # Override the string-based duration functions with timedelta-based ones
        math_functions.update(enhanced_duration_functions)

        # Add enhanced metadata calculation functions
        math_functions.update(
            {
                "minutes_between": MathFunctions.minutes_between,
                "hours_between": MathFunctions.hours_between,
                "days_between": MathFunctions.days_between,
                "seconds_between": MathFunctions.seconds_between,
                "format_friendly": MathFunctions.format_friendly,
                "format_date": MathFunctions.format_date,
                "datetime": datetime,
                "date": MathFunctions.smart_date,
                "timedelta": timedelta,
                # Duration functions for enhanced system
                "seconds": lambda n: timedelta(seconds=float(n)),
                "minutes": lambda n: timedelta(minutes=float(n)),
                "hours": lambda n: timedelta(hours=float(n)),
                "days": lambda n: timedelta(days=float(n)),
                "weeks": lambda n: timedelta(weeks=float(n)),
                # Legacy datetime functions for compatibility
                "now": lambda: datetime.now().isoformat(),
                "today": lambda: datetime.combine(datetime.now().date(), datetime.min.time()).isoformat(),
                "yesterday": lambda: datetime.combine(
                    (datetime.now().date() - timedelta(days=1)), datetime.min.time()
                ).isoformat(),
                "tomorrow": lambda: datetime.combine(
                    (datetime.now().date() + timedelta(days=1)), datetime.min.time()
                ).isoformat(),
                "utc_now": lambda: datetime.now(UTC).isoformat(),
                "utc_today": lambda: datetime.combine(datetime.now(UTC).date(), datetime.min.time(), UTC).isoformat(),
                "utc_yesterday": lambda: datetime.combine(
                    (datetime.now(UTC).date() - timedelta(days=1)), datetime.min.time(), UTC
                ).isoformat(),
                # Unit conversion functions for timedelta results
                "as_minutes": MathFunctions.as_minutes,
                "as_seconds": MathFunctions.as_seconds,
                "as_hours": MathFunctions.as_hours,
                "as_days": MathFunctions.as_days,
                # String functions using function-call syntax (no dot notation)
                "str": MathFunctions.to_str,
                "upper": MathFunctions.upper,
                "lower": MathFunctions.lower,
                "title": MathFunctions.title,
                "strip": MathFunctions.strip,
                "trim": MathFunctions.strip,  # Alias for strip
                "startswith": MathFunctions.startswith,
                "endswith": MathFunctions.endswith,
                "replace": MathFunctions.replace,
                "split": MathFunctions.split,
                "join": MathFunctions.join,
                "contains": MathFunctions.contains,
                "length": MathFunctions.length,  # Alias for len
                "isalpha": MathFunctions.isalpha,
                "isdigit": MathFunctions.isdigit,
                "isnumeric": MathFunctions.isnumeric,
                "isalnum": MathFunctions.isalnum,
                "normalize": MathFunctions.normalize,
                "clean": MathFunctions.clean,
                "sanitize": MathFunctions.sanitize,
                # Business logic functions (eliminating need for DateHandler)
                "add_business_days": MathFunctions.add_business_days,
                "is_business_day": MathFunctions.is_business_day,
                "next_business_day": MathFunctions.next_business_day,
                "previous_business_day": MathFunctions.previous_business_day,
                "get_business_days_between": MathFunctions.get_business_days_between,
                # Common Python built-ins that SimpleEval doesn't include by default
                "len": len,
                "abs": abs,
                "round": round,
                "min": min,
                "max": max,
                "sum": sum,
                "sorted": sorted,
                "all": all,
                "any": any,
                "bool": bool,
                "list": list,
                "tuple": tuple,
                "dict": dict,
                "set": set,
                "range": range,
                "enumerate": enumerate,
                "zip": zip,
                # Metadata result function for AST caching
                "metadata_result": MathFunctions.metadata_result,
            }
        )

        return math_functions

    @staticmethod
    def smart_date(*args):
        """Smart date function that handles both native constructor and string parsing.

        Args:
            *args: Either 3 integers (year, month, day) or 1 string (YYYY-MM-DD)

        Returns:
            For 3 int args: date object
            For 1 string arg: ISO datetime string
        """
        # Case 1: Native Python constructor - date(year, month, day)
        if len(args) == 3:
            try:
                return date(*args)  # Return native date object
            except (TypeError, ValueError) as e:
                raise ValueError(f"Invalid date constructor arguments: {e}") from e

        # Case 2: String parsing - date("2024-12-25")
        elif len(args) == 1 and isinstance(args[0], str):
            try:
                # Parse the date string (expecting YYYY-MM-DD format)
                parsed_date = datetime.strptime(args[0], "%Y-%m-%d").date()
                # Return ISO format string that represents the date object
                return datetime.combine(parsed_date, datetime.min.time()).isoformat()
            except ValueError as e:
                raise ValueError(f"Invalid date string format '{args[0]}'. Expected YYYY-MM-DD") from e
        else:
            raise ValueError("date() function requires either 3 integers (year, month, day) or 1 string (YYYY-MM-DD)")

    @staticmethod
    def get_function_names() -> set[str]:
        """Get the names of all available functions.

        Returns:
            Set of function names that should be excluded from dependency extraction
        """
        return set(MathFunctions.get_all_functions().keys())
