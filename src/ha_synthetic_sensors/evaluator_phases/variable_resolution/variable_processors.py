"""Variable processing helpers for variable resolution phase."""

import logging
import re
from typing import Any

from ha_synthetic_sensors.config_models import FormulaConfig
from ha_synthetic_sensors.exceptions import MissingDependencyError
from ha_synthetic_sensors.type_definitions import ContextValue, ReferenceValue
from ha_synthetic_sensors.utils_resolvers import resolve_via_data_provider_attribute, resolve_via_hass_attribute

from .attribute_reference_resolver import AttributeReferenceResolver

_LOGGER = logging.getLogger(__name__)


class VariableProcessors:
    """Helper class for variable processing operations."""

    @staticmethod
    def resolve_simple_variables_with_usage_tracking(
        formula: str, eval_context: dict[str, ContextValue]
    ) -> tuple[str, set[str]]:
        """Resolve simple variable references and track which variables were used."""
        # Pattern to match simple variable names (letters, numbers, underscores)
        # Negative look-ahead `(?!\.)` ensures we do NOT match names that are immediately
        # followed by a dot (these are part of variable.attribute token chains)
        variable_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)(?!\.)\b")

        used_variables: set[str] = set()

        def replace_variable(match: re.Match[str]) -> str:
            var_name = match.group(1)
            if var_name in eval_context:
                used_variables.add(var_name)
                value = eval_context[var_name]
                # Extract value from ReferenceValue for formula substitution
                if isinstance(value, ReferenceValue):
                    raw_value = value.value
                    # For strings, return the raw value without quotes to avoid double-quoting
                    if isinstance(raw_value, str):
                        return raw_value
                    return str(raw_value)
                # Convert to string representation for formula substitution, preserving string values
                if isinstance(value, str):
                    return value
                return str(value)
            return match.group(0)  # Keep original if not found

        resolved_formula = variable_pattern.sub(replace_variable, formula)
        return resolved_formula, used_variables

    @staticmethod
    def resolve_attribute_chains(
        formula: str, eval_context: dict[str, ContextValue], formula_config: FormulaConfig | None, dependency_handler: Any
    ) -> str:
        """Resolve complete attribute chains including attributes like 'device.battery_level'."""
        if not formula_config:
            return formula

        # Pattern to match variable.attribute patterns
        # This matches: variable_name.attribute_name where variable_name is a valid variable name
        attribute_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b")

        def replace_attribute_chain(match: re.Match[str]) -> str:
            variable_name = match.group(1)
            attribute_name = match.group(2)

            # Get the original entity ID from the formula config (not the resolved value from context)
            if variable_name not in formula_config.variables:
                return match.group(0)  # Keep original if variable not found in config

            entity_id = formula_config.variables[variable_name]
            if not isinstance(entity_id, str):
                return match.group(0)  # Keep original if not a string entity ID

            _LOGGER.debug(
                "Resolving attribute chain %s.%s where %s = %s", variable_name, attribute_name, variable_name, entity_id
            )

            # Resolve the attribute using the attribute resolver
            try:
                attribute_value = VariableProcessors._resolve_entity_attribute(dependency_handler, entity_id, attribute_name)
                _LOGGER.debug("Resolved attribute chain %s.%s to %s", variable_name, attribute_name, attribute_value)
                return str(attribute_value)
            except MissingDependencyError:
                raise  # Re-raise fatal errors per design guide
            except Exception as e:
                _LOGGER.debug("Failed to resolve attribute chain %s.%s: %s", variable_name, attribute_name, e)
                return match.group(0)  # Keep original on error

        return attribute_pattern.sub(replace_attribute_chain, formula)

    @staticmethod
    def _resolve_entity_attribute(dependency_handler: Any, entity_id: str, attribute_name: str) -> Any:
        """Resolve an entity attribute using the dependency handler."""
        if not dependency_handler:
            raise ValueError("Dependency handler not set")

        # Try data provider resolution first
        data_provider_result = resolve_via_data_provider_attribute(
            dependency_handler, entity_id, attribute_name, f"{entity_id}.{attribute_name}"
        )
        if data_provider_result is not None:
            return data_provider_result

        # Try HASS state lookup
        hass_result = resolve_via_hass_attribute(dependency_handler, entity_id, attribute_name, f"{entity_id}.{attribute_name}")
        if hass_result is not None:
            return hass_result

        raise MissingDependencyError(f"Could not resolve attribute {entity_id}.{attribute_name}")

    @staticmethod
    def resolve_variable_attribute_references(formula: str, eval_context: dict[str, ContextValue]) -> str:
        """Resolve variable.attribute references where variable is already in context."""
        # Pattern to match variable.attribute (where the variable part might already be resolved)
        var_attr_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b")

        def replace_var_attr_ref(match: re.Match[str]) -> str:
            var_name = match.group(1)
            attr_name = match.group(2)

            if var_name in eval_context:
                context_value = eval_context[var_name]

                # Handle ReferenceValue objects
                if isinstance(context_value, ReferenceValue):
                    # The reference should be an entity ID - use it for attribute resolution
                    entity_id = context_value.reference
                    _LOGGER.debug("Resolving %s.%s using ReferenceValue entity_id: %s", var_name, attr_name, entity_id)
                    try:
                        # Use the attribute reference resolver
                        resolver = AttributeReferenceResolver()
                        attribute_value = resolver.resolve(f"{entity_id}.{attr_name}", f"{entity_id}.{attr_name}", {})
                        _LOGGER.debug("Resolved %s.%s to: %s", var_name, attr_name, attribute_value)
                        return str(attribute_value)
                    except Exception as e:
                        _LOGGER.debug("Could not resolve %s.%s: %s", var_name, attr_name, e)
                        return match.group(0)  # Keep original on failure

                # Handle raw string values that look like entity IDs
                if isinstance(context_value, str) and "." in context_value:
                    entity_id = str(context_value)
                    _LOGGER.debug("Resolving %s.%s using raw entity_id: %s", var_name, attr_name, entity_id)
                    try:
                        # Use the attribute reference resolver
                        resolver = AttributeReferenceResolver()
                        attribute_value = resolver.resolve(f"{entity_id}.{attr_name}", f"{entity_id}.{attr_name}", {})
                        _LOGGER.debug("Resolved %s.%s to: %s", var_name, attr_name, attribute_value)
                        return str(attribute_value)
                    except Exception as e:
                        _LOGGER.debug("Could not resolve %s.%s: %s", var_name, attr_name, e)
                        return match.group(0)  # Keep original on failure

            # Variable not found or not suitable for attribute resolution
            return match.group(0)  # Keep original

        return var_attr_pattern.sub(replace_var_attr_ref, formula)
