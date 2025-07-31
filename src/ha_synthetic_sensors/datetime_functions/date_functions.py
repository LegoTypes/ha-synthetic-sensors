"""Date-based datetime functions."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytz

from .base_datetime_function import BaseDateTimeFunction


class DateFunctions(BaseDateTimeFunction):
    """Handler for date-based functions like today(), yesterday(), tomorrow()."""

    def _initialize_supported_functions(self) -> set[str]:
        """Initialize the set of supported function names.

        Returns:
            Set of function names this handler supports
        """
        return {"today", "yesterday", "tomorrow", "utc_today", "utc_yesterday"}

    def evaluate_function(self, function_name: str, args: list[Any] | None = None) -> str:
        """Evaluate the date function and return an ISO datetime string.

        Args:
            function_name: The name of the function to evaluate
            args: Optional arguments (not used by these functions)

        Returns:
            ISO datetime string result (date at midnight)

        Raises:
            ValueError: If the function is not supported or arguments are invalid
        """
        self._validate_function_name(function_name)
        self._validate_no_arguments(function_name, args)

        if function_name == "today":
            return self._get_today_local()
        if function_name == "yesterday":
            return self._get_yesterday_local()
        if function_name == "tomorrow":
            return self._get_tomorrow_local()
        if function_name == "utc_today":
            return self._get_today_utc()
        if function_name == "utc_yesterday":
            return self._get_yesterday_utc()

        # This should never be reached due to validation, but added for completeness
        raise ValueError(f"Unexpected function name: {function_name}")

    def _get_today_local(self) -> str:
        """Get today's date at midnight in local timezone.

        Returns:
            Today's date at midnight in ISO format
        """
        today = datetime.now().date()
        return datetime.combine(today, datetime.min.time()).isoformat()

    def _get_yesterday_local(self) -> str:
        """Get yesterday's date at midnight in local timezone.

        Returns:
            Yesterday's date at midnight in ISO format
        """
        yesterday = datetime.now().date() - timedelta(days=1)
        return datetime.combine(yesterday, datetime.min.time()).isoformat()

    def _get_tomorrow_local(self) -> str:
        """Get tomorrow's date at midnight in local timezone.

        Returns:
            Tomorrow's date at midnight in ISO format
        """
        tomorrow = datetime.now().date() + timedelta(days=1)
        return datetime.combine(tomorrow, datetime.min.time()).isoformat()

    def _get_today_utc(self) -> str:
        """Get today's date at midnight in UTC.

        Returns:
            Today's date at midnight UTC in ISO format
        """
        today = datetime.now(pytz.UTC).date()
        return datetime.combine(today, datetime.min.time(), pytz.UTC).isoformat()

    def _get_yesterday_utc(self) -> str:
        """Get yesterday's date at midnight in UTC.

        Returns:
            Yesterday's date at midnight UTC in ISO format
        """
        yesterday = datetime.now(pytz.UTC).date() - timedelta(days=1)
        return datetime.combine(yesterday, datetime.min.time(), pytz.UTC).isoformat()

    def get_function_info(self) -> dict[str, Any]:
        """Get information about the date functions provided.

        Returns:
            Dictionary containing function metadata
        """
        base_info = super().get_function_info()
        base_info.update(
            {
                "category": "date_functions",
                "description": "Functions for getting date boundaries (midnight) with timezone awareness",
                "functions": {
                    "today": "Today's date at midnight in local timezone",
                    "yesterday": "Yesterday's date at midnight in local timezone",
                    "tomorrow": "Tomorrow's date at midnight in local timezone",
                    "utc_today": "Today's date at midnight in UTC",
                    "utc_yesterday": "Yesterday's date at midnight in UTC",
                },
            }
        )
        return base_info
