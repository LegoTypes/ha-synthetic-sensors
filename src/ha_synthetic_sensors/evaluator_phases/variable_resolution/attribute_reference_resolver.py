"""Attribute reference resolver for handling attribute-to-attribute references."""

import logging
import re
from typing import Any

from ...shared_constants import get_reserved_words
from ...type_definitions import ContextValue, ReferenceValue
from .base_resolver import VariableResolver

_LOGGER = logging.getLogger(__name__)


class AttributeReferenceResolver(VariableResolver):
    """Resolver for attribute-to-attribute references like 'level1' referencing another attribute."""

    def get_resolver_name(self) -> str:
        """Return the name of this resolver."""
        return "AttributeReferenceResolver"

    def can_resolve(self, variable_name: str, variable_value: str | Any) -> bool:
        """
        Determine if this resolver can handle the variable.

        This resolver handles variables that:
        1. Are attribute names (not dotted paths)
        2. Variable name and value are the same (direct attribute reference)
        """
        # Check if variable_name is a simple identifier (attribute name)
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", variable_name):
            return False

        # Check if variable_name and variable_value are the same (direct attribute reference)
        # This indicates a potential attribute-to-attribute reference
        return variable_name == variable_value

    def resolve(self, variable_name: str, variable_value: str | Any, context: dict[str, ContextValue]) -> ContextValue | None:
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
                # Handle ReferenceValue objects by extracting their value
                # Local import to avoid circular import in type-only context
                if isinstance(attribute_value, ReferenceValue):
                    _LOGGER.debug(
                        "Attribute reference resolver: '%s' -> ReferenceValue(%s)", variable_name, attribute_value.value
                    )
                    return attribute_value.value
                return attribute_value
            _LOGGER.debug("Attribute reference resolver: attribute '%s' found but None", variable_name)
            return None
        # Attribute not found in context - this is expected for variables that aren't attributes
        return None

    def resolve_references_in_formula(self, formula: str, context: dict[str, ContextValue]) -> str:
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

        resolved_formula = re.sub(pattern, replace_attribute, formula)

        if resolved_formula != formula:
            _LOGGER.debug("Attribute reference resolution: '%s' -> '%s'", formula, resolved_formula)

        return resolved_formula
