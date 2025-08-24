"""Name resolution for synthetic sensor mathematical expressions.

This module provides name resolution functionality for synthetic sensor formulas,
allowing formulas to reference Home Assistant entities and resolve their values.
"""

from __future__ import annotations

import logging
import re
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant

from .device_classes import is_valid_ha_domain

_LOGGER = logging.getLogger(__name__)


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

    def validate_variables(self) -> VariableValidationResult:
        """Validate all variable mappings exist in Home Assistant.

        Returns:
            VariableValidationResult: Detailed validation results
        """
        errors = []
        missing_entities: list[str] = []
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

    def validate_entity_id(self, entity_id: str) -> bool:
        """
        Validate an entity ID format.

        Args:
            entity_id: Entity ID to validate

        Returns:
            True if valid, False otherwise
        """
        return self.is_valid_entity_id(entity_id)

    def extract_entity_type(self, entity_id: str) -> str | None:
        """
        Extract the entity type from an entity ID.

        Args:
            entity_id: Entity ID to parse

        Returns:
            The entity type (e.g., "sensor") or None if invalid format
        """
        if not self.validate_entity_id(entity_id):
            return None

        return entity_id.split(".", 1)[0]

    def validate_variable_name(self, name: str) -> bool:
        """
        Validate a variable name.

        Args:
            name: Variable name to validate

        Returns:
            True if valid, False otherwise
        """
        # Variable names must start with a letter or underscore
        # and contain only letters, numbers, and underscores
        pattern = r"^[a-zA-Z_][a-zA-Z0-9_]*$"
        return bool(re.match(pattern, name))

    def validate_sensor_config(self, sensor_config: dict[str, Any]) -> dict[str, Any]:
        """
        Validate a sensor configuration.

        Args:
            sensor_config: Sensor configuration dictionary

        Returns:
            Validation result dictionary
        """
        errors = []
        missing_entities: list[str] = []
        valid_variables = []
        entity_ids = []

        # Validate sensor key
        sensor_key = sensor_config.get("unique_id", "")
        if not sensor_key:
            errors.append("Sensor must have a unique_id")
        elif not self.validate_variable_name(sensor_key):
            errors.append(f"Invalid sensor unique_id: {sensor_key}")

        # Validate entity_id if present
        entity_id = sensor_config.get("entity_id")
        if entity_id:
            if not self.validate_entity_id(entity_id):
                errors.append(f"Invalid entity_id format: {entity_id}")
            else:
                entity_ids.append(entity_id)

        # Validate formulas
        formulas = sensor_config.get("formulas", [])
        if not formulas:
            errors.append("Sensor must have at least one formula")

        for formula_config in formulas:
            formula_id = formula_config.get("id", "")
            if not formula_id:
                errors.append("Formula must have an id")
            elif not self.validate_variable_name(formula_id):
                errors.append(f"Invalid formula id: {formula_id}")

            formula = formula_config.get("formula", "")
            if not formula:
                errors.append(f"Formula {formula_id} must have a formula expression")

        # Check for valid variables
        for var_name in self._variables:
            if self.validate_variable_name(var_name):
                valid_variables.append(var_name)

        return {
            "errors": errors,
            "missing_entities": missing_entities,
            "valid_variables": valid_variables,
            "entity_ids": entity_ids,
        }

    def resolve_entity_references(self, formula: str, variables: dict[str, str]) -> list[str]:
        """
        Resolve entity references in a formula.

        Args:
            formula: Formula string to analyze
            variables: Variable mappings

        Returns:
            List of entity IDs referenced in the formula
        """
        entity_ids = []

        # Check for direct entity references (domain.entity format)
        # Simple regex to find potential entity IDs
        pattern = r"\b[a-z_]+\.[a-z0-9_]+\b"
        matches = re.findall(pattern, formula)

        for match in matches:
            if self.validate_entity_id(match):
                entity_ids.append(match)

        # Check for variable references
        for var_name in variables:
            if var_name in formula:
                entity_id = variables.get(var_name)
                if entity_id and entity_id not in entity_ids:
                    entity_ids.append(entity_id)

        return entity_ids
