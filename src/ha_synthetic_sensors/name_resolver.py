"""Name resolution for synthetic sensor mathematical expressions.

This module provides name resolution functionality for synthetic sensor formulas,
allowing formulas to reference Home Assistant entities and resolve their values.
"""

from __future__ import annotations

import logging
import re
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from simpleeval import NameNotDefined, simple_eval

from .device_classes import is_valid_ha_domain

_LOGGER = logging.getLogger(__name__)


# TypedDicts for name resolver results
class VariableValidationResult(TypedDict):
    """Result of variable validation."""

    is_valid: bool
    errors: list[str]
    missing_entities: list[str]
    valid_variables: list[str]


class EntityReference(TypedDict):
    """Information about an entity reference in a formula."""

    variable_name: str
    entity_id: str
    current_value: float | None
    is_available: bool
    state_string: str | None


class FormulaDependencies(TypedDict):
    """Complete dependency information for a formula."""

    entity_ids: set[str]
    variable_mappings: dict[str, str]
    direct_references: set[str]
    total_dependencies: int


class NameResolver:
    """Resolves variable names in formulas to Home Assistant entity states."""

    def __init__(self, hass: HomeAssistant, variables: dict[str, str]) -> None:
        """Initialize the name resolver.

        Args:
            hass: Home Assistant instance
            variables: Mapping of formula variable names to entity IDs
                      e.g., {"net_power": "sensor.span_panel_current_power"}
        """
        self._hass = hass
        self._variables = variables
        self._logger = _LOGGER.getChild(self.__class__.__name__)

    @property
    def variables(self) -> dict[str, str]:
        """Get the current variable mappings."""
        return self._variables.copy()

    def update_variables(self, variables: dict[str, str]) -> None:
        """Update the variable mappings.

        Args:
            variables: New variable mappings to use
        """
        self._variables = variables.copy()

    def normalize_name(self, name: str) -> str:
        """Normalize a name to a valid variable name for formulas.

        This converts names like "HVAC Upstairs" to normalized forms
        like "hvac_upstairs" that can be used as variable names in formulas.

        Args:
            name: The name to normalize

        Returns:
            str: Normalized name suitable for use as a variable in formulas
        """
        # Replace spaces, hyphens, and other special characters with underscores
        normalized = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower())

        # Remove multiple consecutive underscores
        normalized = re.sub(r"_+", "_", normalized)

        # Remove leading/trailing underscores
        normalized = normalized.strip("_")

        # Ensure it starts with a letter or underscore (valid Python identifier)
        if normalized and normalized[0].isdigit():
            normalized = f"_{normalized}"

        return normalized

    def resolve_name(self, node: Any) -> float:
        """Resolve a variable name to its numeric value from Home Assistant.

        This function is called by simpleeval for each variable in the formula.

        Args:
            node: AST node with .id attribute containing the variable name

        Returns:
            float: The numeric value of the entity state

        Raises:
            NameNotDefined: If variable name not found in variables mapping
            HomeAssistantError: If entity state cannot be resolved to a number
        """
        variable_name = node.id

        # First check if this variable is defined in our mapping
        if variable_name in self._variables:
            entity_id = self._variables[variable_name]
        # Then check if it looks like a direct entity ID (contains dot)
        elif "." in variable_name and self.is_valid_entity_id(variable_name):
            entity_id = variable_name
            self._logger.debug("Using direct entity ID reference: %s", variable_name)
        else:
            self._logger.warning(
                "Variable '%s' not in variables / not a valid entity. variables: %s",
                variable_name,
                list(self._variables.keys()),
            )
            raise NameNotDefined(
                variable_name,
                f"Variable '{variable_name}' not defined and not a valid entity ID",
            )

        # Get the entity state from Home Assistant
        entity_state = self._hass.states.get(entity_id)

        if entity_state is None:
            self._logger.error(
                "Entity '%s' (for variable '%s') not found in Home Assistant",
                entity_id,
                variable_name,
            )
            raise HomeAssistantError(f"Entity '{entity_id}' for variable '{variable_name}' not found")

        # Handle unavailable/unknown states
        if entity_state.state in ("unavailable", "unknown", "none", None):
            self._logger.warning(
                "Entity '%s' (variable '%s') is unavailable: %s",
                entity_id,
                variable_name,
                entity_state.state,
            )
            raise HomeAssistantError(f"Entity '{entity_id}' for variable '{variable_name}' is unavailable")

        # Convert state to numeric value
        try:
            numeric_value = float(entity_state.state)
            self._logger.debug(
                "Resolved %s='%s' -> %s=%s",
                variable_name,
                entity_id,
                variable_name,
                numeric_value,
            )
            return numeric_value

        except (ValueError, TypeError) as exc:
            self._logger.error(
                "Cannot convert entity '%s' state '%s' to number for variable '%s': %s",
                entity_id,
                entity_state.state,
                variable_name,
                exc,
            )
            raise HomeAssistantError(
                f"Entity '{entity_id}' state '{entity_state.state}' cannot be converted to number"
            ) from exc

    def get_static_names(self) -> dict[str, float]:
        """Get all current variable values as a static dictionary.

        This is an alternative to using the dynamic name resolver function.
        Useful for debugging or when you want to capture values at a specific moment.

        Returns:
            dict: Mapping of variable names to their current numeric values

        Raises:
            HomeAssistantError: If any entity state cannot be resolved
        """
        static_names = {}

        for variable_name, _entity_id in self._variables.items():
            # Create a mock node for the resolve_name method
            class MockNode:
                def __init__(self, name: str):
                    self.id = name

            try:
                static_names[variable_name] = self.resolve_name(MockNode(variable_name))
            except (NameNotDefined, HomeAssistantError) as exc:
                self._logger.error("Failed to resolve variable '%s': %s", variable_name, exc)
                raise

        return static_names

    def validate_variables(self) -> VariableValidationResult:
        """Validate all variable mappings exist in Home Assistant.

        Returns:
            VariableValidationResult: Detailed validation results
        """
        errors = []
        missing_entities = []
        valid_variables = []

        for var_name, entity_id in self._variables.items():
            state = self._hass.states.get(entity_id)
            if not state:
                errors.append(f"Entity '{entity_id}' for variable '{var_name}' not found")
                missing_entities.append(entity_id)
            else:
                valid_variables.append(var_name)

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "missing_entities": missing_entities,
            "valid_variables": valid_variables,
        }

    def clear_mappings(self) -> None:
        """Clear all variable mappings."""
        self._variables.clear()
        self._logger.debug("Cleared all variable mappings")

    def add_entity_mapping(self, variable_name: str, entity_id: str) -> None:
        """Add a new variable to entity mapping.

        Args:
            variable_name: Variable name to use in formulas
            entity_id: Home Assistant entity ID
        """
        self._variables[variable_name] = entity_id
        self._logger.debug("Added mapping: %s -> %s", variable_name, entity_id)

    def remove_entity_mapping(self, variable_name: str) -> bool:
        """Remove a variable mapping.

        Args:
            variable_name: Variable name to remove

        Returns:
            bool: True if mapping was removed, False if not found
        """
        if variable_name in self._variables:
            del self._variables[variable_name]
            self._logger.debug("Removed mapping for variable: %s", variable_name)
            return True
        return False

    def extract_entity_references(self, formula: str) -> set[str]:
        """Extract entity references from a formula string.

        This method looks for patterns like entity('sensor.name') in formulas
        and extracts the entity IDs.

        Args:
            formula: The formula string to analyze

        Returns:
            set: Set of entity IDs found in the formula
        """
        # Pattern to match entity('entity_id') calls
        pattern = r'entity\(["\']([^"\']+)["\']\)'
        matches = re.findall(pattern, formula)
        return set(matches)

    def get_formula_dependencies(self, formula: str) -> FormulaDependencies:
        """Get all dependencies for a formula.

        This includes both variables from the variable mapping and
        direct entity references in the formula.

        Args:
            formula: The formula string to analyze

        Returns:
            FormulaDependencies: Complete dependency information
        """
        entity_ids = set()
        variable_mappings = {}

        # Add entity IDs from variable mappings that are used in the formula
        # This is a simple check - could be enhanced with AST parsing
        for variable_name, entity_id in self._variables.items():
            if variable_name in formula:
                entity_ids.add(entity_id)
                variable_mappings[variable_name] = entity_id

        # Add direct entity references
        direct_references = self.extract_entity_references(formula)
        entity_ids.update(direct_references)

        return {
            "entity_ids": entity_ids,
            "variable_mappings": variable_mappings,
            "direct_references": direct_references,
            "total_dependencies": len(entity_ids),
        }

    def is_valid_entity_id(self, entity_id: str) -> bool:
        """Check if a string looks like a valid Home Assistant entity ID.

        Args:
            entity_id: String to validate

        Returns:
            bool: True if it looks like a valid entity ID (domain.entity)
        """
        # Basic validation: should have exactly one dot, valid domain and entity parts
        if entity_id.count(".") != 1:
            return False

        domain, entity = entity_id.split(".")

        # Basic validation of domain and entity parts
        if not (domain and entity):
            return False

        # Check domain format using centralized domain validation with HA instance
        if not is_valid_ha_domain(domain, self._hass):
            return False

        # Entity part: letters, numbers, underscores, hyphens (basic validation)
        return entity.replace("_", "").replace("-", "").isalnum()


class FormulaEvaluator:
    """Evaluates mathematical formulas with Home Assistant entity resolution."""

    def __init__(
        self,
        hass: HomeAssistant,
        formula: str,
        variables: dict[str, str],
        fallback_value: float = 0.0,
    ) -> None:
        """Initialize the formula evaluator.

        Args:
            hass: Home Assistant instance
            formula: Mathematical expression string
            variables: Mapping of formula variable names to entity IDs
            fallback_value: Value to return if evaluation fails
        """
        self._hass = hass
        self._formula = formula
        self._variables = variables
        self._fallback_value = fallback_value
        self._name_resolver = NameResolver(hass, variables)
        self._logger = _LOGGER.getChild(self.__class__.__name__)

    @property
    def formula(self) -> str:
        """Get the formula string."""
        return self._formula

    @property
    def variables(self) -> dict[str, str]:
        """Get the variable mappings."""
        return self._variables.copy()

    @property
    def fallback_value(self) -> float:
        """Get the fallback value."""
        return self._fallback_value

    def evaluate(self) -> float:
        """Evaluate the formula with current entity states.

        Returns:
            float: The calculated result or fallback_value if evaluation fails
        """
        try:
            # Use the name resolver function for dynamic entity state lookup
            result = simple_eval(self._formula, names=self._name_resolver.resolve_name)

            self._logger.debug("Formula evaluation successful: '%s' = %s", self._formula, result)

            return float(result)

        except ImportError as exc:
            self._logger.error("simpleeval library not installed: %s", exc)
            return self._fallback_value

        except (NameNotDefined, HomeAssistantError) as exc:
            self._logger.warning(
                "Formula evaluation failed: '%s' - %s, using fallback value %s",
                self._formula,
                exc,
                self._fallback_value,
            )
            return self._fallback_value

        except Exception as exc:  # pylint: disable=broad-except
            self._logger.error(
                "Unexpected error evaluating formula '%s': %s, using fallback value %s",
                self._formula,
                exc,
                self._fallback_value,
            )
            return self._fallback_value

    def validate_formula(self) -> list[str]:
        """Validate the formula and all variables.

        Returns:
            list: List of validation error messages, empty if valid
        """
        errors = []

        # Validate variables first
        validation_result = self._name_resolver.validate_variables()
        errors.extend(validation_result["errors"])

        # Test formula syntax with dummy values
        try:
            # Create dummy values for syntax testing
            dummy_names = dict.fromkeys(self._variables.keys(), 1.0)
            simple_eval(self._formula, names=dummy_names)

        except ImportError:
            errors.append("simpleeval library not installed")
        except Exception as exc:  # pylint: disable=broad-except
            errors.append(f"Formula syntax error: {exc}")

        return errors

    def get_dependencies(self) -> set[str]:
        """Get all entity dependencies for this formula.

        Returns:
            set: Set of entity IDs that this formula depends on
        """
        deps = self._name_resolver.get_formula_dependencies(self._formula)
        return deps["entity_ids"]
