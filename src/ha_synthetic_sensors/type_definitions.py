"""Type definitions for the synthetic sensors package."""

from __future__ import annotations

from typing import Any, Callable, NotRequired, TypedDict

# Import Home Assistant types to stay aligned with their type system
from homeassistant.core import State
from homeassistant.helpers.typing import ConfigType, StateType

# Type alias for evaluation context values
# Values in formula evaluation can be:
# - Basic types: numbers, strings, booleans for entity values and variables
# - Callables: math functions that can be called in formulas
# - State objects: HA State objects for attribute access (entity_id_state)
# - Config/attribute data: uses HA's ConfigType (dict[str, Any])
# - None: for unavailable/missing values
ContextValue = StateType | Callable[..., Any] | State | ConfigType | None

# Type alias for formula evaluation results
FormulaResult = float | int | str | bool | None


# TypedDicts for data provider results
class DataProviderResult(TypedDict):
    """Result of data provider callback."""

    value: FormulaResult
    exists: bool


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
