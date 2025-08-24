"""Shared types for variable resolution to avoid duplication."""

from dataclasses import dataclass
from typing import Any


@dataclass
class VariableResolutionResult:
    """Result of variable resolution with HA state detection."""

    resolved_formula: str
    has_ha_state: bool = False
    ha_state_value: str | None = None

    unavailable_dependencies: list["HADependency"] | list[str] | None = None
    entity_to_value_mappings: dict[str, str] | None = None  # entity_reference -> resolved_value
    early_result: Any = None  # Early result that should bypass evaluation and go to Phase 4


@dataclass(frozen=True)
class HADependency:
    """Structured representation of an HA dependency detected during resolution.

    Fields:
    - var: variable name used in formula
    - entity_id: the HA entity id that produced the special state
    - state: one of 'unknown', 'unavailable', or other HA state strings
    """

    var: str
    entity_id: str
    state: str

    def __str__(self) -> str:
        return f"{self.var} ({self.entity_id}) is {self.state}"
