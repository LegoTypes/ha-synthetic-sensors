"""Dynamic query dataclass for collection resolution.

This module contains the DynamicQuery class used for runtime resolution
of collection patterns in formulas.
"""

from dataclasses import dataclass, field


@dataclass
class DynamicQuery:
    """Represents a dynamic query that needs runtime resolution."""

    query_type: str  # 'regex', 'label', 'device_class', 'area', 'attribute', 'state'
    pattern: str  # The actual query pattern
    function: str  # The aggregation function (sum, avg, count, etc.)
    exclusions: list[str] = field(default_factory=list)  # Patterns to exclude from results
