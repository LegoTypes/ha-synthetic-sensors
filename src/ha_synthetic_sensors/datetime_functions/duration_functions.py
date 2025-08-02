"""Duration functions for explicit date arithmetic operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base_datetime_function import BaseDateTimeFunction


@dataclass
class Duration:
    """Represents a time duration with a specific unit and value."""

    value: int | float
    unit: str  # 'seconds', 'minutes', 'hours', 'days', 'weeks', 'months'

    def to_days(self) -> float:
        """Convert duration to days for date arithmetic."""
        if self.unit == "seconds":
            return self.value / (24 * 60 * 60)
        if self.unit == "minutes":
            return self.value / (24 * 60)
        if self.unit == "hours":
            return self.value / 24
        if self.unit == "days":
            return float(self.value)
        if self.unit == "weeks":
            return self.value * 7
        if self.unit == "months":
            return self.value * 30.44  # Average days per month

        raise ValueError(f"Unknown duration unit: {self.unit}")

    def to_seconds(self) -> float:
        """Convert duration to seconds for precise arithmetic."""
        if self.unit == "seconds":
            return float(self.value)
        if self.unit == "minutes":
            return self.value * 60
        if self.unit == "hours":
            return self.value * 60 * 60
        if self.unit == "days":
            return self.value * 24 * 60 * 60
        if self.unit == "weeks":
            return self.value * 7 * 24 * 60 * 60
        if self.unit == "months":
            return self.value * 30.44 * 24 * 60 * 60  # Average days per month

        raise ValueError(f"Unknown duration unit: {self.unit}")

    def __str__(self) -> str:
        """Return string representation for formula processing."""
        return f"duration:{self.unit}:{self.value}"


class DurationFunctions(BaseDateTimeFunction):
    """Handler for duration functions like days(), weeks(), months(), etc."""

    def _initialize_supported_functions(self) -> set[str]:
        """Initialize the set of supported duration function names."""
        return {"seconds", "minutes", "hours", "days", "weeks", "months"}

    def evaluate_function(self, function_name: str, args: list[Any] | None = None) -> str:
        """
        Evaluate a duration function and return a duration string.

        Args:
            function_name: Name of duration function (e.g., 'days', 'hours')
            args: List containing the numeric value

        Returns:
            Duration string in format "duration:unit:value"
        """
        if not self.can_handle_function(function_name):
            raise ValueError(f"Duration function '{function_name}' is not supported")

        if not args or len(args) != 1:
            raise ValueError(f"Duration function '{function_name}' requires exactly one numeric argument")

        value = args[0]

        # Validate that the argument is numeric
        try:
            numeric_value = float(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Duration function '{function_name}' requires a numeric argument, got {type(value).__name__}"
            ) from exc

        # Create duration object and return its string representation
        duration = Duration(value=numeric_value, unit=function_name)
        return str(duration)

    def get_handler_name(self) -> str:
        """Return the name of this handler."""
        return "DurationFunctions"
