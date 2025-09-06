"""Variable processing helpers for variable resolution phase."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalContextDict

from ha_synthetic_sensors.config_models import FormulaConfig
from ha_synthetic_sensors.exceptions import MissingDependencyError
from ha_synthetic_sensors.regex_helper import extract_attribute_access_pairs, extract_variable_references_no_dots, regex_helper
from ha_synthetic_sensors.type_definitions import ReferenceValue
from ha_synthetic_sensors.utils_resolvers import resolve_via_data_provider_attribute, resolve_via_hass_attribute

from .attribute_reference_resolver import AttributeReferenceResolver

_LOGGER = logging.getLogger(__name__)


class VariableProcessors:
    """Helper class for variable processing operations."""

    @staticmethod
    def resolve_simple_variables_with_usage_tracking(
        formula: str, eval_context: "HierarchicalContextDict"
    ) -> tuple[str, set[str]]:
        """Resolve simple variable references and track which variables were used."""
        # Use regex helper for variable pattern matching
        # Negative look-ahead ensures we do NOT match names that are immediately
        # followed by a dot (these are part of variable.attribute token chains)

        used_variables: set[str] = set()

        # Extract variables and replace them
        variables = extract_variable_references_no_dots(formula)
        resolved_formula = formula
        for var_name in variables:
            if var_name in eval_context:
                used_variables.add(var_name)
                value = eval_context[var_name]
                # Extract value from ReferenceValue for formula substitution
                if isinstance(value, ReferenceValue):
                    raw_value = value.value
                    # For strings, return the raw value without quotes to avoid double-quoting
                    replacement = raw_value if isinstance(raw_value, str) else str(raw_value)
                else:
                    # Convert to string representation for formula substitution, preserving string values
                    replacement = value if isinstance(value, str) else str(value)

                # Replace with word boundaries to avoid partial matches
                resolved_formula = regex_helper.replace_entity_references(resolved_formula, var_name, replacement)

        return resolved_formula, used_variables

    @staticmethod
    def resolve_attribute_chains(
        formula: str, eval_context: "HierarchicalContextDict", formula_config: FormulaConfig | None, dependency_handler: Any
    ) -> str:
        """Resolve complete attribute chains including attributes like 'device.battery_level'."""
        if not formula_config:
            return formula

        # Use regex helper for attribute pattern matching
        # This matches: variable_name.attribute_name where variable_name is a valid variable name

        # Extract attribute pairs and replace them
        attribute_pairs = extract_attribute_access_pairs(formula)
        resolved_formula = formula

        for variable_name, attribute_name in attribute_pairs:
            # Get the original entity ID from the formula config (not the resolved value from context)
            if variable_name not in formula_config.variables:
                continue  # Skip if variable not found in config

            entity_id = formula_config.variables[variable_name]
            if not isinstance(entity_id, str):
                continue  # Skip if not a string entity ID

            _LOGGER.debug(
                "Resolving attribute chain: %s.%s -> entity %s attribute %s",
                variable_name,
                attribute_name,
                entity_id,
                attribute_name,
            )

            # Use AttributeReferenceResolver to get the attribute value
            resolver = AttributeReferenceResolver()
            try:
                attribute_value = resolver.resolve(
                    f"{entity_id}.{attribute_name}", f"{entity_id}.{attribute_name}", eval_context
                )
                if attribute_value is not None:
                    # Replace the variable.attribute pattern in the formula
                    resolved_formula = regex_helper.replace_entity_references(
                        resolved_formula, f"{variable_name}.{attribute_name}", str(attribute_value)
                    )
            except MissingDependencyError:
                _LOGGER.warning("Could not resolve attribute %s.%s", variable_name, attribute_name)
                continue

        return resolved_formula

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
    def resolve_variable_attribute_references(formula: str, eval_context: "HierarchicalContextDict") -> str:
        """Resolve variable.attribute references where variable is already in context."""
        # Use regex helper for variable.attribute pattern matching

        # Extract attribute pairs and replace them
        attribute_pairs = extract_attribute_access_pairs(formula)
        resolved_formula = formula

        for var_name, attr_name in attribute_pairs:
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
                        attribute_value = resolver.resolve(f"{entity_id}.{attr_name}", f"{entity_id}.{attr_name}", eval_context)
                        _LOGGER.debug("Resolved %s.%s to: %s", var_name, attr_name, attribute_value)

                        # Replace the variable.attribute pattern in the formula
                        resolved_formula = regex_helper.replace_entity_references(
                            resolved_formula, f"{var_name}.{attr_name}", str(attribute_value)
                        )
                    except Exception as e:
                        _LOGGER.debug("Could not resolve %s.%s: %s", var_name, attr_name, e)
                        continue  # Keep original on failure

                # Handle direct entity ID strings
                elif isinstance(context_value, str) and "." in context_value:
                    # Assume it's an entity ID
                    entity_id = context_value
                    _LOGGER.debug("Resolving %s.%s using direct entity_id: %s", var_name, attr_name, entity_id)
                    try:
                        resolver = AttributeReferenceResolver()
                        attribute_value = resolver.resolve(f"{entity_id}.{attr_name}", f"{entity_id}.{attr_name}", eval_context)
                        _LOGGER.debug("Resolved %s.%s to: %s", var_name, attr_name, attribute_value)

                        # Replace the variable.attribute pattern in the formula
                        resolved_formula = regex_helper.replace_entity_references(
                            resolved_formula, f"{var_name}.{attr_name}", str(attribute_value)
                        )
                    except Exception as e:
                        _LOGGER.debug("Could not resolve %s.%s: %s", var_name, attr_name, e)
                        continue  # Keep original on failure

        return resolved_formula
