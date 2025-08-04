"""Formula processing helpers for variable resolution phase."""

import logging
import re
from typing import Any

from ha_synthetic_sensors.config_models import FormulaConfig
from ha_synthetic_sensors.constants_formula import is_ha_state_value, normalize_ha_state_value

from .resolution_types import VariableResolutionResult

_LOGGER = logging.getLogger(__name__)


class FormulaHelpers:
    """Helper class for formula processing operations."""

    @staticmethod
    def find_metadata_function_parameter_ranges(formula: str) -> list[tuple[int, int]]:
        """Find character ranges for metadata function parameters to preserve variable names.

        Returns list of (start_pos, end_pos) tuples for metadata function parameter regions.
        """
        protected_ranges: list[tuple[int, int]] = []

        # Pattern to match metadata function calls
        metadata_pattern = re.compile(r"\bmetadata\s*\(\s*([^,)]+)(?:\s*,\s*[^)]+)?\s*\)")

        for match in metadata_pattern.finditer(formula):
            # Get the full match span
            match_start = match.start()

            # Find the opening parenthesis after 'metadata'
            paren_start = formula.find("(", match_start)
            if paren_start == -1:
                continue

            # Find the first comma or closing parenthesis to get first parameter range
            comma_pos = formula.find(",", paren_start)
            close_paren_pos = formula.find(")", paren_start)

            if comma_pos != -1 and comma_pos < close_paren_pos:
                # Has parameters - protect first parameter
                param_start = paren_start + 1
                param_end = comma_pos

                # Trim whitespace from the range
                while param_start < param_end and formula[param_start].isspace():
                    param_start += 1
                while param_end > param_start and formula[param_end - 1].isspace():
                    param_end -= 1

                if param_start < param_end:
                    protected_ranges.append((param_start, param_end))
                    _LOGGER.debug(
                        "Protected metadata parameter range: %d-%d ('%s')",
                        param_start,
                        param_end,
                        formula[param_start:param_end],
                    )
            elif close_paren_pos != -1:
                # Single parameter - protect it
                param_start = paren_start + 1
                param_end = close_paren_pos

                # Trim whitespace from the range
                while param_start < param_end and formula[param_start].isspace():
                    param_start += 1
                while param_end > param_start and formula[param_end - 1].isspace():
                    param_end -= 1

                if param_start < param_end:
                    protected_ranges.append((param_start, param_end))
                    _LOGGER.debug(
                        "Protected metadata parameter range: %d-%d ('%s')",
                        param_start,
                        param_end,
                        formula[param_start:param_end],
                    )

        return protected_ranges

    @staticmethod
    def identify_variables_for_attribute_access(formula: str, formula_config: FormulaConfig | None) -> set[str]:
        """Identify variables that need entity IDs for .attribute access patterns."""
        if not formula_config:
            return set()

        variables_needing_entity_ids: set[str] = set()

        # Look for patterns like variable.attribute in the formula
        attribute_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\b")

        for match in attribute_pattern.finditer(formula):
            var_name = match.group(1)
            attr_name = match.group(2)

            # Only consider variables that are defined in the config and refer to entities
            if var_name in formula_config.variables:
                var_value = formula_config.variables[var_name]
                # If the variable value looks like an entity ID, this variable needs special handling
                if isinstance(var_value, str) and "." in var_value:
                    variables_needing_entity_ids.add(var_name)
                    _LOGGER.debug(
                        "Variable '%s' needs entity ID preservation for attribute access: %s.%s",
                        var_name,
                        var_name,
                        attr_name,
                    )

        return variables_needing_entity_ids

    @staticmethod
    def detect_ha_state_in_formula(
        resolved_formula: str, unavailable_dependencies: list[str], entity_to_value_mappings: dict[str, str]
    ) -> Any:  # Returns VariableResolutionResult or None
        """Detect HA state values in resolved formula and return early result if found."""

        # If any unavailable dependencies exist, escalate the final state to 'unavailable'
        unavailable = [dep for dep in (unavailable_dependencies or []) if dep.endswith("is unavailable")]
        unknown = [dep for dep in (unavailable_dependencies or []) if dep.endswith("is unknown")]
        if unavailable:
            return VariableResolutionResult(
                resolved_formula=resolved_formula,
                has_ha_state=True,
                ha_state_value="unavailable",
                unavailable_dependencies=unavailable_dependencies or [],
                entity_to_value_mappings=entity_to_value_mappings,
            )
        if unknown:
            return VariableResolutionResult(
                resolved_formula=resolved_formula,
                has_ha_state=True,
                ha_state_value="unknown",
                unavailable_dependencies=unavailable_dependencies or [],
                entity_to_value_mappings=entity_to_value_mappings,
            )

        # Check for HA state values in the resolved formula - both quoted and unquoted
        for state_value in ["unknown", "unavailable"]:
            # Check for quoted HA state values in expressions (e.g., "unavailable" + 10)
            if f'"{state_value}"' in resolved_formula:
                _LOGGER.debug("Formula contains quoted HA state '%s', returning HA state", state_value)
                return VariableResolutionResult(
                    resolved_formula=resolved_formula,
                    has_ha_state=True,
                    ha_state_value=state_value,
                    unavailable_dependencies=unavailable_dependencies or [],
                    entity_to_value_mappings=entity_to_value_mappings,
                )

            # Check for unquoted HA state values
            if state_value in resolved_formula:
                _LOGGER.debug("Formula contains unquoted HA state '%s', returning HA state", state_value)
                return VariableResolutionResult(
                    resolved_formula=resolved_formula,
                    has_ha_state=True,
                    ha_state_value=state_value,
                    unavailable_dependencies=unavailable_dependencies or [],
                    entity_to_value_mappings=entity_to_value_mappings,
                )

        # Check for other HA state values that should result in corresponding sensor states
        stripped_formula = resolved_formula.strip()
        # Handle quoted strings by removing quotes
        if stripped_formula.startswith('"') and stripped_formula.endswith('"'):
            stripped_formula = stripped_formula[1:-1]

        if is_ha_state_value(stripped_formula):
            state_value = normalize_ha_state_value(stripped_formula)
            _LOGGER.debug("Formula resolved to HA state '%s'", state_value)
            return VariableResolutionResult(
                resolved_formula=resolved_formula,
                has_ha_state=True,
                ha_state_value=state_value,
                unavailable_dependencies=unavailable_dependencies or [],
                entity_to_value_mappings=entity_to_value_mappings,
            )

        return None
