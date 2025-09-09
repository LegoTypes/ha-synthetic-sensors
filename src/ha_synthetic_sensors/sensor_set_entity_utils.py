"""
Utility functions for entity ID changes in sensor configurations.

This module provides shared functionality to eliminate duplicate code
between SensorSet and SensorSetBulkOps classes.
"""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any

from .config_models import AlternateStateHandler, ComputedVariable
from .dependency_parser import DependencyParser
from .regex_helper import regex_helper, safe_entity_replacement

if TYPE_CHECKING:
    from .config_models import FormulaConfig, SensorConfig

_LOGGER = logging.getLogger(__name__)


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


def _update_formula_string(formula_str: str, entity_id_changes: dict[str, str]) -> str:
    """Update entity ID references in a formula string.

    Uses the centralized DependencyParser to extract explicit entity references
    from the formula and performs safe replacements for any entity IDs that
    are present in `entity_id_changes`. This avoids ad-hoc regexes and reuses
    existing parsing logic used across the codebase (handles metadata(),
    state(), states["..."] and other patterns).
    """
    # Early exit when nothing to do
    if not entity_id_changes or not isinstance(formula_str, str) or not formula_str:
        return formula_str

    # Use dependency parser to extract entity references

    parser = DependencyParser()

    try:
        # Ask the parser for explicit entity references within this formula
        referenced_entities = parser.extract_entity_references(formula_str)
    except Exception:
        # Fallback: if parser fails for any reason, keep original behavior of simple word-boundary replacement
        referenced_entities = set()

    updated_formula = formula_str

    # If parser found explicit entity references, only replace those
    if referenced_entities:
        for old_id, new_id in sorted(entity_id_changes.items(), key=lambda x: len(x[0]), reverse=True):
            if old_id in referenced_entities:
                _LOGGER.debug("Replacing entity id %s -> %s in formula: %s", old_id, new_id, formula_str)
                # Use centralized safe entity replacement from regex helper

                updated_formula = safe_entity_replacement(updated_formula, old_id, new_id)
    else:
        # ARCHITECTURE FIX: Use centralized regex helper for entity replacement

        for old_id, new_id in sorted(entity_id_changes.items(), key=lambda x: len(x[0]), reverse=True):
            updated_formula = regex_helper.replace_entity_references(updated_formula, old_id, new_id)

    if updated_formula != formula_str:
        _LOGGER.debug("Formula updated: '%s' -> '%s'", formula_str, updated_formula)

    return updated_formula


def _update_alternate_states(alternate_states: dict[str, Any] | Any, entity_id_changes: dict[str, str]) -> bool:
    """Update entity ID references in alternate states recursively.

    Returns True if any change was made, False otherwise.
    """
    if not alternate_states or not isinstance(alternate_states, dict):
        return False

    changes_made = False

    for state_name, state_config in alternate_states.items():
        if (isinstance(state_config, dict) and _update_alternate_state_dict(state_config, entity_id_changes)) or (
            isinstance(state_config, str)
            and _update_alternate_state_string(alternate_states, state_name, state_config, entity_id_changes)
        ):
            changes_made = True

    return changes_made


def _update_alternate_state_dict(state_config: dict[str, Any], entity_id_changes: dict[str, str]) -> bool:
    """Update entity ID references in an alternate state dictionary."""
    changes_made = False

    # Update formula in alternate state
    if "formula" in state_config:
        original_formula = state_config["formula"]
        if isinstance(original_formula, str):
            updated_formula = _update_formula_string(original_formula, entity_id_changes)
            if updated_formula != original_formula:
                state_config["formula"] = updated_formula
                changes_made = True

    # Recursively process nested structures
    if _update_nested_alternate_state_handlers(state_config, entity_id_changes):
        changes_made = True

    if _update_nested_alternate_states(state_config, entity_id_changes):
        changes_made = True

    if _update_other_nested_dicts(state_config, entity_id_changes):
        changes_made = True

    return changes_made


def _update_nested_alternate_state_handlers(state_config: dict[str, Any], entity_id_changes: dict[str, str]) -> bool:
    """Update nested alternate state handlers."""
    return "alternate_state_handler" in state_config and _update_alternate_state_handler(
        state_config["alternate_state_handler"], entity_id_changes
    )


def _update_nested_alternate_states(state_config: dict[str, Any], entity_id_changes: dict[str, str]) -> bool:
    """Update nested alternate states."""
    return "alternate_states" in state_config and _update_alternate_states(state_config["alternate_states"], entity_id_changes)


def _update_other_nested_dicts(state_config: dict[str, Any], entity_id_changes: dict[str, str]) -> bool:
    """Update other nested dictionaries that might contain formulas."""
    changes_made = False
    for key, value in state_config.items():
        if (
            key not in ["formula", "alternate_state_handler", "alternate_states"]
            and isinstance(value, dict)
            and _update_alternate_states(value, entity_id_changes)
        ):
            changes_made = True
    return changes_made


def _update_alternate_state_string(
    alternate_states: dict[str, Any], state_name: str, state_config: str, entity_id_changes: dict[str, str]
) -> bool:
    """Update entity ID references in an alternate state string."""
    # Check if it's a direct entity ID reference
    if state_config in entity_id_changes:
        alternate_states[state_name] = entity_id_changes[state_config]
        return True

    # Check if it's a formula string that needs updating
    updated_value = _update_formula_string(state_config, entity_id_changes)
    if updated_value != state_config:
        alternate_states[state_name] = updated_value
        return True

    return False


def _update_alternate_state_handler(
    alternate_state_handler: dict[str, Any] | AlternateStateHandler, entity_id_changes: dict[str, str]
) -> bool:
    """Update entity ID references in alternate_state_handler structure.

    Returns True if any change was made, False otherwise.
    """
    if not alternate_state_handler:
        return False

    if isinstance(alternate_state_handler, AlternateStateHandler):
        return _update_alternate_state_handler_object(alternate_state_handler, entity_id_changes)

    if not isinstance(alternate_state_handler, dict):
        return False

    return _update_alternate_state_handler_dict(alternate_state_handler, entity_id_changes)


def _update_alternate_state_handler_object(handler: AlternateStateHandler, entity_id_changes: dict[str, str]) -> bool:
    """Update entity ID references in AlternateStateHandler object."""
    changes_made = False
    for field_name in ["unavailable", "unknown", "none", "fallback"]:
        field_value = getattr(handler, field_name, None)
        if _update_alternate_state_handler_field(handler, field_name, field_value, entity_id_changes):
            changes_made = True
    return changes_made


def _update_alternate_state_handler_field(
    handler: AlternateStateHandler, field_name: str, field_value: Any, entity_id_changes: dict[str, str]
) -> bool:
    """Update a single field in AlternateStateHandler."""
    if isinstance(field_value, str):
        updated_value = _update_formula_string(field_value, entity_id_changes)
        if updated_value != field_value:
            setattr(handler, field_name, updated_value)
            return True
    elif isinstance(field_value, dict):
        return _update_alternate_state_handler(field_value, entity_id_changes)
    return False


def _update_alternate_state_handler_dict(handler: dict[str, Any], entity_id_changes: dict[str, str]) -> bool:
    """Update entity ID references in alternate_state_handler dictionary."""
    changes_made = False
    for field_name, field_value in handler.items():
        if _update_alternate_state_handler_dict_field(handler, field_name, field_value, entity_id_changes):
            changes_made = True
    return changes_made


def _update_alternate_state_handler_dict_field(
    handler: dict[str, Any], field_name: str, field_value: Any, entity_id_changes: dict[str, str]
) -> bool:
    """Update a single field in alternate_state_handler dictionary."""
    if isinstance(field_value, str):
        updated_value = _update_formula_string(field_value, entity_id_changes)
        if updated_value != field_value:
            handler[field_name] = updated_value
            return True
    elif isinstance(field_value, dict):
        return _update_alternate_state_handler(field_value, entity_id_changes)
    return False


def _update_attributes(attributes: dict[str, Any], entity_id_changes: dict[str, str]) -> bool:
    """Update entity ID references in attributes.

    Returns True if any change was made, False otherwise.
    """
    if not attributes:
        return False

    changes_made = False

    for attr_name, attr_value in attributes.items():
        if isinstance(attr_value, str):
            # Check if it's a direct entity ID reference
            if attr_value in entity_id_changes:
                attributes[attr_name] = entity_id_changes[attr_value]
                changes_made = True
            else:
                # Check if it's a formula string that needs updating
                updated_value = _update_formula_string(attr_value, entity_id_changes)
                if updated_value != attr_value:
                    attributes[attr_name] = updated_value
                    changes_made = True
        elif isinstance(attr_value, dict):
            if "formula" in attr_value:
                # Attribute with formula
                original_formula = attr_value["formula"]
                if isinstance(original_formula, str):
                    updated_formula = _update_formula_string(original_formula, entity_id_changes)
                    if updated_formula != original_formula:
                        attr_value["formula"] = updated_formula
                        changes_made = True

            # Check for alternate states in attributes
            if "alternate_states" in attr_value and _update_alternate_states(attr_value["alternate_states"], entity_id_changes):
                changes_made = True

            # Check for alternate_state_handler in attributes
            if "alternate_state_handler" in attr_value and _update_alternate_state_handler(
                attr_value["alternate_state_handler"], entity_id_changes
            ):
                changes_made = True

    return changes_made


def _update_metadata(metadata: dict[str, Any], entity_id_changes: dict[str, str]) -> bool:
    """Update entity ID references in formula metadata fields.

    Treat metadata like a generic nested dict of strings and dicts that may contain
    embedded formulas or entity IDs. Returns True if any change was made.
    """
    if not metadata:
        return False

    return _walk_metadata(metadata, entity_id_changes)


def _walk_metadata(obj: Any, entity_id_changes: dict[str, str]) -> bool:
    """Walk through metadata structure and update entity ID references."""
    if isinstance(obj, str):
        return _update_metadata_string(obj, entity_id_changes)
    if isinstance(obj, dict):
        return _update_metadata_dict(obj, entity_id_changes)
    if isinstance(obj, list):
        return _update_metadata_list(obj, entity_id_changes)
    return False


def _update_metadata_string(obj: str, entity_id_changes: dict[str, str]) -> bool:
    """Update entity ID references in a metadata string."""
    updated = _update_formula_string(obj, entity_id_changes)
    return updated != obj


def _update_metadata_dict(obj: dict[str, Any], entity_id_changes: dict[str, str]) -> bool:
    """Update entity ID references in a metadata dictionary."""
    local_change = False
    for k, v in list(obj.items()):
        if isinstance(v, str):
            new_v = _update_formula_string(v, entity_id_changes)
            if new_v != v:
                obj[k] = new_v
                local_change = True
        elif isinstance(v, dict | list):
            if _walk_metadata(v, entity_id_changes):
                local_change = True
    return local_change


def _update_metadata_list(obj: list[Any], entity_id_changes: dict[str, str]) -> bool:
    """Update entity ID references in a metadata list."""
    local_change = False
    for i, v in enumerate(obj):
        if isinstance(v, str):
            new_v = _update_formula_string(v, entity_id_changes)
            if new_v != v:
                obj[i] = new_v
                local_change = True
        elif isinstance(v, dict | list):
            if _walk_metadata(v, entity_id_changes):
                local_change = True
    return local_change


def _update_variable_value(
    var_name: str,
    var_value: str | int | float | ComputedVariable | dict[str, Any],
    variables: dict[str, str | int | float | ComputedVariable],
    entity_id_changes: dict[str, str],
) -> bool:
    """Update a single variable value for entity ID changes.

    Returns:
        True if any changes were made, False otherwise
    """
    if isinstance(var_value, str) and var_value in entity_id_changes:
        # Handle string variables (direct entity ID references)
        variables[var_name] = entity_id_changes[var_value]
        return True
    if isinstance(var_value, ComputedVariable):
        # Handle ComputedVariable objects - update their formula strings
        updated_formula = _update_formula_string(var_value.formula, entity_id_changes)
        if updated_formula != var_value.formula:
            var_value.formula = updated_formula
            return True
        # Also update alternate_state_handler inside ComputedVariable if present
        handler = getattr(var_value, "alternate_state_handler", None)
        if handler is not None and _update_alternate_state_handler(handler, entity_id_changes):
            return True
    elif isinstance(var_value, dict):
        return _update_dict_variable(var_value, entity_id_changes)
    return False


def _update_dict_variable(var_value: dict[str, Any], entity_id_changes: dict[str, str]) -> bool:
    """Update a dictionary variable for entity ID changes.

    Returns:
        True if any changes were made, False otherwise
    """
    changes_made = False

    if "formula" in var_value:
        # Handle ComputedVariable objects stored as dicts (from YAML parsing)
        formula_str = var_value["formula"]
        if isinstance(formula_str, str):
            updated_formula = _update_formula_string(formula_str, entity_id_changes)
            if updated_formula != formula_str:
                var_value["formula"] = updated_formula
                changes_made = True

    # Update alternate states in variables
    if "alternate_states" in var_value and _update_alternate_states(var_value["alternate_states"], entity_id_changes):
        changes_made = True

    # Update alternate_state_handler in variables
    if "alternate_state_handler" in var_value and _update_alternate_state_handler(
        var_value["alternate_state_handler"], entity_id_changes
    ):
        changes_made = True

    return changes_made


def _update_formula_main_string(formula: FormulaConfig, entity_id_changes: dict[str, str]) -> bool:
    """Update the main formula string for entity ID changes.

    Returns:
        True if any changes were made, False otherwise
    """
    if formula.formula:
        updated_main_formula = _update_formula_string(formula.formula, entity_id_changes)
        if updated_main_formula != formula.formula:
            formula.formula = updated_main_formula
            return True
    return False


def _update_formula_variables(formula: FormulaConfig, entity_id_changes: dict[str, str]) -> bool:
    """Update formula variables for entity ID changes.

    Returns:
        True if any changes were made, False otherwise
    """
    if not formula.variables:
        return False

    changes_made = False
    for var_name, var_value in formula.variables.items():
        if _update_variable_value(var_name, var_value, formula.variables, entity_id_changes):
            changes_made = True
    return changes_made


def update_formula_variables_for_entity_changes(formula: FormulaConfig, entity_id_changes: dict[str, str]) -> bool:
    """
    Update entity ID references throughout a formula configuration.

    This function updates entity IDs in ALL possible locations:
    - Main formula string
    - Variables (direct references and computed formulas)
    - Variable alternate states
    - Attributes (direct references and computed formulas)
    - Attribute alternate states
    - Formula alternate states

    Returns:
        True if any changes were made, False otherwise
    """
    if not entity_id_changes:
        return False

    changes_made = False

    # Update main formula string
    if _update_formula_main_string(formula, entity_id_changes):
        changes_made = True

    # Update variables
    if _update_formula_variables(formula, entity_id_changes):
        changes_made = True

    # Update variable-level alternate_state_handler formulas
    if _update_variable_alternate_state_handlers(formula, entity_id_changes):
        changes_made = True

    # Update formula-level alternate states
    if _update_formula_alternate_states(formula, entity_id_changes):
        changes_made = True

    # Update formula-level alternate_state_handler
    if _update_formula_alternate_state_handler(formula, entity_id_changes):
        changes_made = True

    # Update attributes
    if _update_formula_attributes(formula, entity_id_changes):
        changes_made = True

    # Update metadata
    if _update_formula_metadata(formula, entity_id_changes):
        changes_made = True

    return changes_made


def _update_variable_alternate_state_handlers(formula: FormulaConfig, entity_id_changes: dict[str, str]) -> bool:
    """Update variable-level alternate_state_handler formulas."""
    changes_made = False
    for _var_name, _var_value in (formula.variables or {}).items():
        if isinstance(_var_value, ComputedVariable):
            handler = getattr(_var_value, "alternate_state_handler", None)
            if handler is not None and _update_alternate_state_handler_instance(handler, entity_id_changes):
                changes_made = True
    return changes_made


def _update_alternate_state_handler_instance(handler: Any, entity_id_changes: dict[str, str]) -> bool:
    """Update a single alternate state handler instance."""
    changes_made = False

    # Handle dataclass instance
    if isinstance(handler, AlternateStateHandler):
        for _field in ("unavailable", "unknown", "none", "fallback"):
            _field_val = getattr(handler, _field, None)
            if isinstance(_field_val, dict) and "formula" in _field_val and isinstance(_field_val["formula"], str):
                _newf = _update_formula_string(_field_val["formula"], entity_id_changes)
                if _newf != _field_val["formula"]:
                    _field_val["formula"] = _newf
                    changes_made = True

    # Handle dict-form handlers
    elif isinstance(handler, dict):
        for k, v in list(handler.items()):
            if isinstance(v, dict) and "formula" in v and isinstance(v["formula"], str):
                _newf = _update_formula_string(v["formula"], entity_id_changes)
                if _newf != v["formula"]:
                    v["formula"] = _newf
                    changes_made = True
            elif k == "formula" and isinstance(v, str):
                _newf = _update_formula_string(v, entity_id_changes)
                if _newf != v:
                    handler[k] = _newf
                    changes_made = True

    return changes_made


def _update_formula_alternate_states(formula: FormulaConfig, entity_id_changes: dict[str, str]) -> bool:
    """Update formula-level alternate states."""
    if not hasattr(formula, "alternate_states") or not formula.alternate_states:
        return False
    if not isinstance(formula.alternate_states, dict):
        return False
    return _update_alternate_states(formula.alternate_states, entity_id_changes)


def _update_formula_alternate_state_handler(formula: FormulaConfig, entity_id_changes: dict[str, str]) -> bool:
    """Update formula-level alternate_state_handler."""
    if not hasattr(formula, "alternate_state_handler") or not formula.alternate_state_handler:
        return False
    return _update_alternate_state_handler(formula.alternate_state_handler, entity_id_changes)


def _update_formula_attributes(formula: FormulaConfig, entity_id_changes: dict[str, str]) -> bool:
    """Update formula attributes."""
    if not hasattr(formula, "attributes") or not formula.attributes:
        return False
    return _update_attributes(formula.attributes, entity_id_changes)


def _update_formula_metadata(formula: FormulaConfig, entity_id_changes: dict[str, str]) -> bool:
    """Update formula metadata."""
    if not hasattr(formula, "metadata") or not formula.metadata:
        return False
    return _update_metadata(formula.metadata, entity_id_changes)
