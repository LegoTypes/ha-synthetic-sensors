"""Mathematical functions for synthetic sensor formulas.

This module provides a centralized collection of mathematical and utility functions
that can be used in formula evaluation, making them easily testable and maintainable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
import math
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

    @staticmethod
    def get_builtin_functions() -> dict[str, Callable[..., Any]]:
        """Get all mathematical functions available for formula evaluation.

        Returns:
            Dictionary mapping function names to callable functions
        """
        return {
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

    @staticmethod
    def get_function_names() -> set[str]:
        """Get the names of all available functions.

        Returns:
            Set of function names that should be excluded from dependency extraction
        """
        return set(MathFunctions.get_builtin_functions().keys())
