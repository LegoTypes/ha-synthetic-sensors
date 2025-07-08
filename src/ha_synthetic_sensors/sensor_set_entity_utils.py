"""
Utility functions for entity ID changes in sensor configurations.

This module provides shared functionality to eliminate duplicate code
between SensorSet and SensorSetBulkOps classes.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config_models import FormulaConfig, SensorConfig


def apply_entity_id_changes_to_sensors_util(
    entity_id_changes: dict[str, str], sensors: dict[str, SensorConfig]
) -> dict[str, SensorConfig]:
    """
    Apply entity ID changes to sensor configurations.

    Args:
        entity_id_changes: Mapping of old entity ID to new entity ID
        sensors: Sensor configurations to update

    Returns:
        Updated sensor configurations with entity ID changes applied
    """
    updated_sensors = {}

    for unique_id, sensor in sensors.items():
        # Create a copy to avoid modifying the original
        updated_sensor = copy.deepcopy(sensor)

        # Update sensor entity_id
        if updated_sensor.entity_id and updated_sensor.entity_id in entity_id_changes:
            updated_sensor.entity_id = entity_id_changes[updated_sensor.entity_id]

        # Update formula variables
        for formula in updated_sensor.formulas:
            if formula.variables:
                update_formula_variables_for_entity_changes(formula, entity_id_changes)

        updated_sensors[unique_id] = updated_sensor

    return updated_sensors


def update_formula_variables_for_entity_changes(formula: FormulaConfig, entity_id_changes: dict[str, str]) -> None:
    """Update formula variables for entity ID changes."""
    for var_name, var_value in formula.variables.items():
        if isinstance(var_value, str) and var_value in entity_id_changes:
            formula.variables[var_name] = entity_id_changes[var_value]
