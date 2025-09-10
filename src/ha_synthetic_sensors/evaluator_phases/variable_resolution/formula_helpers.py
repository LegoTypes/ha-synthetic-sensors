"""Formula processing helpers for variable resolution phase."""

import logging
from typing import Any

from ha_synthetic_sensors.config_models import FormulaConfig
from ha_synthetic_sensors.constants_alternate import identify_alternate_state_value

from ...regex_helper import (
    create_attribute_access_pattern,
    create_metadata_function_pattern,
    create_single_token_pattern,
    match_pattern,
)
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

        # Use centralized metadata function pattern from regex helper
        metadata_pattern = create_metadata_function_pattern()

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
    def identify_variables_for_attribute_access(
        formula: str, formula_config: FormulaConfig | None, ast_service: Any
    ) -> set[str]:
        """Identify variables that need entity IDs for attribute access patterns.

        Supports both dot notation (variable.attribute) and metadata function calls (metadata(variable, 'attribute')).
        """
        if not formula_config:
            return set()

        variables_needing_entity_ids: set[str] = set()

        # 1. Check dot notation attribute access (variable.attribute)
        attribute_pattern = create_attribute_access_pattern()

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
                        "Variable '%s' needs entity ID preservation for dot notation access: %s.%s",
                        var_name,
                        var_name,
                        attr_name,
                    )

        # 2. Check metadata function calls (metadata(variable, 'attribute'))
        # Use AST service for parse-once optimization
        metadata_calls = ast_service.extract_metadata_calls(formula)
        metadata_vars = {entity for entity, _ in metadata_calls}

        for var_name in metadata_vars:
            # Handle special case: 'state' token is always resolved to an entity ID
            if var_name == "state":
                variables_needing_entity_ids.add(var_name)
                _LOGGER.debug(
                    "Variable '%s' needs entity ID preservation for metadata function access (special token)",
                    var_name,
                )
            elif var_name in formula_config.variables:
                var_value = formula_config.variables[var_name]
                # If the variable value looks like an entity ID, this variable needs special handling
                if isinstance(var_value, str) and "." in var_value:
                    variables_needing_entity_ids.add(var_name)
                    _LOGGER.debug(
                        "Variable '%s' needs entity ID preservation for metadata function access",
                        var_name,
                    )

        return variables_needing_entity_ids

    @staticmethod
    def detect_ha_state_in_formula(
        resolved_formula: str,
        unavailable_dependencies: list[HADependency] | list[str],
        entity_to_value_mappings: dict[str, str],
        eval_context: Any,
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

        # Check 2: Single value detection - check if entire formula is a single value with alternate state
        stripped_formula = resolved_formula.strip()

        # Case 2a: Single variable/identifier - check its resolved value in context
        if stripped_formula.isidentifier():
            # Formula is a single variable name (like 'state') - check its resolved value
            resolved_value = eval_context.get(stripped_formula)
            if resolved_value is not None:
                # Extract the actual value from ReferenceValue if needed
                actual_value = resolved_value.value if hasattr(resolved_value, "value") else resolved_value
                alt_state = identify_alternate_state_value(actual_value)
                if isinstance(alt_state, str):
                    _LOGGER.debug(
                        "Single value optimization: Variable '%s' has alternate state value '%s'", stripped_formula, alt_state
                    )
                    return VariableResolutionResult(
                        resolved_formula=resolved_formula,
                        has_ha_state=True,
                        ha_state_value=alt_state,
                        unavailable_dependencies=unavailable_dependencies,
                        entity_to_value_mappings=entity_to_value_mappings,
                        early_result=alt_state,
                    )

        # Case 2b: Literal string value - check if it's an alternate state string
        # Only check if the formula is actually a simple literal (quoted string or simple unquoted literal)
        literal_check = stripped_formula
        is_quoted_literal = literal_check.startswith('"') and literal_check.endswith('"')
        is_simple_unquoted_literal = (
            not any(op in literal_check for op in ["(", ")", "+", "-", "*", "/", "<", ">", "=", ",", " "])
            and not literal_check.isidentifier()  # Already handled in Case 2a
        )

        if is_quoted_literal or is_simple_unquoted_literal:
            if is_quoted_literal:
                literal_check = literal_check[1:-1]  # Remove quotes

            # Use the alternate state detection logic on the literal string
            alt_state = identify_alternate_state_value(literal_check)
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

        # Use centralized single token pattern from regex helper
        single_token_pattern = create_single_token_pattern()
        if match_pattern(token, single_token_pattern):
            return token

        # If there is exactly one mapping and the resolved formula equals that mapping's key or value,
        # accept it as a single token (handles cases where entity_to_value_mappings uses different forms).
        if entity_to_value_mappings and len(entity_to_value_mappings) == 1:
            key, val = next(iter(entity_to_value_mappings.items()))
            if token in (key, val):
                return token

        return None
