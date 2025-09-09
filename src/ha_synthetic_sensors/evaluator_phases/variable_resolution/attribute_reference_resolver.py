"""Attribute reference resolver for handling attribute-to-attribute references."""

from __future__ import annotations

import logging
import re

from homeassistant.helpers.typing import StateType

from ...hierarchical_context_dict import HierarchicalContextDict
from ...regex_helper import RegexHelper, create_simple_identifier_validation_pattern, match_pattern
from ...shared_constants import get_reserved_words
from ...type_definitions import ContextValue, ReferenceValue
from .base_resolver import VariableResolver

_LOGGER = logging.getLogger(__name__)


class AttributeReferenceResolver(VariableResolver):
    """Resolver for attribute-to-attribute references like 'level1' referencing another attribute."""

    def get_resolver_name(self) -> str:
        """Return the name of this resolver."""
        return "AttributeReferenceResolver"

    def can_resolve(self, variable_name: str, variable_value: str | StateType) -> bool:
        """
        Determine if this resolver can handle the variable.

        This resolver handles variables that:
        1. Are attribute names (not dotted paths)
        2. Variable name and value are the same (direct attribute reference)
        """
        # Check if variable_name is a simple identifier (attribute name)
        pattern = create_simple_identifier_validation_pattern()
        if not match_pattern(variable_name, pattern):
            return False

        # Check if variable_name and variable_value are the same (direct attribute reference)
        # This indicates a potential attribute-to-attribute reference
        return variable_name == variable_value

    def resolve(self, variable_name: str, variable_value: str | StateType, context: HierarchicalContextDict) -> ContextValue:
        """
        Resolve attribute reference to its calculated value.

        Args:
            variable_name: The attribute name to resolve (e.g., 'level1')
            variable_value: The attribute value (same as variable_name for direct references)
            context: Evaluation context containing previously calculated attribute values

        Returns:
            The calculated value of the referenced attribute, or None if not found
        """
        # Skip reserved words and operators
        if variable_name in get_reserved_words():
            return None

        # Check if the variable exists in context (previously calculated attribute)
        if variable_name in context:
            attribute_value = context.get(variable_name)

            if attribute_value is not None:
                # Return raw values for formula substitution (resolvers return raw values)
                if isinstance(attribute_value, ReferenceValue):
                    return attribute_value  # Return ReferenceValue object to maintain type consistency
                # For non-ReferenceValue context items (callable, dict), return as-is
                # These are valid ContextValue types that don't need wrapping
                return attribute_value
            return None
        # Attribute not found in context - this is expected for variables that aren't attributes
        return None

    def resolve_references_in_formula(self, formula: str, context: HierarchicalContextDict) -> str:
        """
        Resolve attribute references in a formula string.

        This method finds attribute names that appear as standalone variables in formulas
        and replaces them with their calculated values from the context.

        Args:
            formula: The formula containing attribute references
            context: Evaluation context containing attribute values

        Returns:
            Formula with attribute references resolved to their values
        """
        # Pattern to match standalone attribute names (not part of other identifiers)
        # This matches words that:
        # 1. Start with letter or underscore
        # 2. Contain only letters, numbers, underscores
        # 3. Are word boundaries (not part of larger identifiers)
        pattern = r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b"

        def replace_attribute(match: re.Match[str]) -> str:
            attr_name = match.group(1)

            # Skip reserved words and operators
            if attr_name in get_reserved_words():
                return attr_name

            # Check if this attribute exists in context
            if attr_name in context:
                attr_value = context[attr_name]

                # Handle ReferenceValue objects by extracting their value
                if isinstance(attr_value, ReferenceValue):
                    extracted_value = attr_value.value
                    if isinstance(extracted_value, int | float):
                        _LOGGER.debug(
                            "Resolving attribute reference '%s' to %s (from ReferenceValue)", attr_name, extracted_value
                        )
                        return str(extracted_value)
                    _LOGGER.debug("Attribute '%s' ReferenceValue found but not numeric: %s", attr_name, extracted_value)
                    return attr_name
                if isinstance(attr_value, int | float):
                    _LOGGER.debug("Resolving attribute reference '%s' to %s", attr_name, attr_value)
                    return str(attr_value)
                _LOGGER.debug("Attribute '%s' found but not numeric: %s", attr_name, attr_value)
                return attr_name
            # Not an attribute reference, keep as-is
            return attr_name

        regex_helper = RegexHelper()
        resolved_formula = regex_helper.replace_with_function(formula, pattern, replace_attribute)

        if resolved_formula != formula:
            _LOGGER.debug("Attribute reference resolution: '%s' -> '%s'", formula, resolved_formula)

        return resolved_formula
