"""Formula processing helpers for variable resolution phase."""

import logging
import re
from typing import Any

from ha_synthetic_sensors.config_models import FormulaConfig
from ha_synthetic_sensors.constants_alternate import identify_alternate_state_value

from .resolution_types import HADependency, VariableResolutionResult

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
        resolved_formula: str,
        unavailable_dependencies: list[HADependency] | list[str],
        entity_to_value_mappings: dict[str, str],
    ) -> Any:  # Returns VariableResolutionResult or None
        """Single state optimization: detect if entire resolved formula is a single HA state value.

        This optimization bypasses formula evaluation when the entire formula resolves
        to a single alternate state (e.g. "unknown", "unavailable", "none").

        Note: Main alternate state detection happens in CoreFormulaEvaluator when
        extracting values from ReferenceValue objects.

        Returns early result that will be processed by Phase 4 alternate state handling.
        """
        # Check 1: If formula is a single entity with unavailable dependency, check for alternate states
        if unavailable_dependencies and len(unavailable_dependencies) == 1:
            # Only proceed if the resolved formula is exactly one entity token
            single_token = FormulaHelpers.get_single_entity_token(resolved_formula, entity_to_value_mappings)
            if single_token:
                dep = unavailable_dependencies[0]
                # Extract the value to check (state from HADependency, or the string itself)
                value_to_check = dep.state if isinstance(dep, HADependency) else dep

                # Check for alternate states using the centralized function
                alt_state = identify_alternate_state_value(value_to_check)
                if isinstance(alt_state, str):
                    return VariableResolutionResult(
                        resolved_formula=resolved_formula,
                        has_ha_state=True,
                        ha_state_value=alt_state,
                        unavailable_dependencies=unavailable_dependencies,
                        entity_to_value_mappings=entity_to_value_mappings,
                        early_result=alt_state,
                    )

        # Check 2: Single state detection - check if entire formula is a single alternate state
        stripped_formula = resolved_formula.strip()

        # Remove quotes if present (for string literals)
        if stripped_formula.startswith('"') and stripped_formula.endswith('"'):
            stripped_formula = stripped_formula[1:-1]

        # Use the alternate state detection logic
        alt_state = identify_alternate_state_value(stripped_formula)
        if isinstance(alt_state, str):
            _LOGGER.debug(
                "Single state optimization: Formula '%s' resolved to alternate state '%s'", resolved_formula, alt_state
            )
            return VariableResolutionResult(
                resolved_formula=resolved_formula,
                has_ha_state=True,
                ha_state_value=alt_state,
                unavailable_dependencies=unavailable_dependencies,
                entity_to_value_mappings=entity_to_value_mappings,
                early_result=alt_state,
            )

        return None

    @staticmethod
    def get_single_entity_token(resolved_formula: str, entity_to_value_mappings: dict[str, str] | None) -> str | None:
        """Return the single entity/variable token if the formula is exactly one token.

        The token may be a variable name (e.g. "state"), a dotted entity id (e.g. "sensor.foo"),
        or a simple quoted literal. Returns the stripped token string when the formula is
        exactly that token, otherwise returns None.
        """
        if not resolved_formula:
            return None

        token = resolved_formula.strip()
        # Remove surrounding quotes for string literals
        if token.startswith('"') and token.endswith('"') and len(token) >= 2:
            token = token[1:-1].strip()

        # Single-token pattern: variable, optional dotted entity id
        single_token_pattern = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)?$")
        if single_token_pattern.match(token):
            return token

        # If there is exactly one mapping and the resolved formula equals that mapping's key or value,
        # accept it as a single token (handles cases where entity_to_value_mappings uses different forms).
        if entity_to_value_mappings and len(entity_to_value_mappings) == 1:
            key, val = next(iter(entity_to_value_mappings.items()))
            if token in (key, val):
                return token

        return None
