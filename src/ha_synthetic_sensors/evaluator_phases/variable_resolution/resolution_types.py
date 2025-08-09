"""Shared types for variable resolution to avoid duplication."""

from dataclasses import dataclass


@dataclass
class VariableResolutionResult:
    """Result of variable resolution with HA state detection."""

    resolved_formula: str
    has_ha_state: bool = False
    ha_state_value: str | None = None
    unavailable_dependencies: list[str] | None = None
    entity_to_value_mappings: dict[str, str] | None = None  # entity_reference -> resolved_value
