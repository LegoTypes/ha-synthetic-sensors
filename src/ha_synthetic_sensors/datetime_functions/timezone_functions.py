"""Timezone-aware datetime functions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytz

from .base_datetime_function import BaseDateTimeFunction


class TimezoneFunctions(BaseDateTimeFunction):
    """Handler for timezone-aware datetime functions like now(), utc_now(), local_now()."""

    def _initialize_supported_functions(self) -> set[str]:
        """Initialize the set of supported function names.

        Returns:
            Set of function names this handler supports
        """
        return {"now", "local_now", "utc_now"}

    def evaluate_function(self, function_name: str, args: list[Any] | None = None) -> str:
        """Evaluate the timezone datetime function and return an ISO datetime string.

        Args:
            function_name: The name of the function to evaluate ('now', 'local_now', 'utc_now')
            args: Optional arguments (not used by these functions)

        Returns:
            ISO datetime string result

        Raises:
            ValueError: If the function is not supported or arguments are invalid
        """
        self._validate_function_name(function_name)
        self._validate_no_arguments(function_name, args)

        if function_name in ("now", "local_now"):
            return self._get_local_now()
        if function_name == "utc_now":
            return self._get_utc_now()

        # This should never be reached due to validation, but added for completeness
        raise ValueError(f"Unexpected function name: {function_name}")

    def _get_local_now(self) -> str:
        """Get current datetime in local timezone as ISO string.

        Returns:
            Current datetime in ISO 8601 format (local timezone)
        """
        return datetime.now().isoformat()

    def _get_utc_now(self) -> str:
        """Get current datetime in UTC as ISO string.

        Returns:
            Current datetime in ISO 8601 format (UTC)
        """
        return datetime.now(pytz.UTC).isoformat()

    def get_function_info(self) -> dict[str, Any]:
        """Get information about the timezone datetime functions provided.

        Returns:
            Dictionary containing function metadata
        """
        base_info = super().get_function_info()
        base_info.update(
            {
                "category": "timezone_datetime",
                "description": "Functions for getting current datetime with timezone awareness",
                "functions": {
                    "now": "Current datetime in local timezone",
                    "local_now": "Current datetime in local timezone (explicit)",
                    "utc_now": "Current datetime in UTC timezone",
                },
            }
        )
        return base_info
