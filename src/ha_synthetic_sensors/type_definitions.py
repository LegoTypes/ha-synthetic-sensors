"""Type definitions for the synthetic sensors package."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NotRequired, TypedDict

# Import Home Assistant types to stay aligned with their type system
from homeassistant.core import State
from homeassistant.helpers.typing import ConfigType, StateType


# Universal reference/value pair class
class ReferenceValue:
    """Universal reference/value pair for all variables in evaluation context.

    This preserves both the original reference and its resolved value for ALL variables,
    allowing handlers to access either the original reference or the resolved value as needed.
    """

    def __init__(self, reference: str, value: StateType):
        """Initialize a reference/value pair.

        Args:
            reference: Original reference (variable name, entity ID, etc.)
            value: Resolved value (e.g., "25.5", 42, True)
        """
        self._reference = reference
        self._value = value

    @property
    def reference(self) -> str:
        """Get the original reference."""
        return self._reference

    @property
    def value(self) -> StateType:
        """Get the resolved value."""
        return self._value

    def __str__(self) -> str:
        """String representation showing both reference and value."""
        return f"ReferenceValue(reference='{self._reference}', value={self._value})"

    def __repr__(self) -> str:
        """Debug representation."""
        return f"ReferenceValue(reference='{self._reference}', value={self._value!r})"


# Type-safe evaluation context for handlers - STRICT: Only ReferenceValue objects for variables
EvaluationContext = dict[str, ReferenceValue | Callable[..., Any] | State | ConfigType | StateType | None]

# Context type for internal resolution phases (flexible during resolution)
# Values in formula evaluation can be:
# - ReferenceValue: universal reference/value pairs for all variables
# - Callables: math functions that can be called in formulas
# - State objects: HA State objects for attribute access (entity_id_state)
# - Config/attribute data: uses HA's ConfigType (dict[str, Any])
# - Basic types: ONLY during resolution phases, NOT for handlers
# - None: for unavailable/missing values
ContextValue = ReferenceValue | Callable[..., Any] | State | ConfigType | StateType | None

# Type alias for formula evaluation results
FormulaResult = float | int | str | bool | None


# TypedDicts for data provider results
class DataProviderResult(TypedDict):
    """Result of data provider callback."""

    value: FormulaResult
    exists: bool
    attributes: NotRequired[dict[str, Any]]  # Optional attributes dictionary


# Type alias for data provider callback
DataProviderCallback = Callable[[str], DataProviderResult]

# Type alias for data provider change notification callback
# Called when backing entity data changes to trigger selective sensor updates
DataProviderChangeNotifier = Callable[[set[str]], None]

# Type alias for callback to get list of entity IDs that the integration can provide
EntityListCallback = Callable[[], set[str]]  # Returns set of entity IDs that integration can provide


# TypedDicts for evaluator results
class EvaluationResult(TypedDict):
    """Result of formula evaluation."""

    success: bool
    value: FormulaResult
    error: NotRequired[str]
    cached: NotRequired[bool]
    state: NotRequired[str]  # "ok", "unknown", "unavailable"
    unavailable_dependencies: NotRequired[list[str]]
    missing_dependencies: NotRequired[list[str]]


class CacheStats(TypedDict):
    """Cache statistics for monitoring."""

    total_cached_formulas: int
    total_cached_evaluations: int
    valid_cached_evaluations: int
    error_counts: dict[str, int]
    cache_ttl_seconds: float


class DependencyValidation(TypedDict):
    """Result of dependency validation."""

    is_valid: bool
    issues: dict[str, str]
    missing_entities: list[str]
    unavailable_entities: list[str]
