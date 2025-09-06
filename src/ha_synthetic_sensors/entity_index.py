"""Entity ID index for tracking synthetic sensor dependencies."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .config_models import FormulaConfig, SensorConfig
from .dependency_parser import DependencyParser
from .name_resolver import NameResolver

_LOGGER = logging.getLogger(__name__)


class EntityIndex:
    """
    Index of entity IDs used by synthetic sensors for efficient change tracking.

    NOTE: This index is used for filtering entity_registry_updated events and
    friendly name change detection. It does NOT track all entity references -
    only those in specific locations (see below).

    For dependency tracking (state change events), we use dynamic discovery
    during formula evaluation which captures ALL entity references including
    those in formulas, attributes, and metadata.

    This tracks:
    - Sensor entity_id fields (our own synthetic sensors)
    - Formula variable values that are entity IDs
    - Global variable values that are entity IDs
    - Entity IDs directly in formula strings (via DependencyParser)

    This does NOT track:
    - Entity IDs in attribute formulas
    - Entity IDs in metadata() function calls
    - Dynamic aggregation patterns (device_class:, regex:, tag:)
    - Collection functions that resolve at runtime
    - Attribute access patterns (variable.attribute)

    The incomplete tracking is acceptable because:
    - For entity renames: we use global string search/replace
    - For state changes: we use dynamic dependency discovery
    - This index is only for filtering registry/name change events
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """
        Initialize the EntityIndex.

        Args:
            hass: Home Assistant instance for entity validation
        """
        self._hass = hass
        self._logger = logging.getLogger(__name__)
        self._entity_ids: set[str] = set()

    def _extract_base_entity_id(self, value: str) -> str | None:
        """
        Extract the base entity ID from a value that might include attribute access.

        Examples:
        - sensor.power_meter -> sensor.power_meter
        - sensor.power_meter.state -> sensor.power_meter
        - sensor.power_meter.attributes.voltage -> sensor.power_meter
        - backup_device.battery_level -> None (invalid domain)

        Args:
            value: String value that might be an entity reference

        Returns:
            Base entity ID if valid, None otherwise
        """
        if not isinstance(value, str):
            return None

        parts = value.split(".")
        if len(parts) < 2:
            return None

        # Base entity ID is always domain.entity_name (first two parts)
        base_entity_id = f"{parts[0]}.{parts[1]}"

        # Validate using our _is_entity_id method
        if self._is_entity_id(base_entity_id):
            return base_entity_id

        return None

    def add_sensor_entities(self, sensor_config: SensorConfig) -> None:
        """
        Add all entity IDs from a sensor configuration to the index.

        Args:
            sensor_config: Sensor configuration to extract entity IDs from
        """
        entities_added: set[str] = set()

        # Add explicit sensor entity_id if present
        self._add_entity_if_valid(sensor_config.entity_id, entities_added)

        # Add entity IDs from formulas
        for formula in sensor_config.formulas:
            self._add_formula_entities(formula, entities_added)

        # Check sensor-level metadata for entity references
        parser = DependencyParser(self._hass)
        self._extract_entities_from_metadata(sensor_config.metadata, parser, entities_added)

        # Add self-reference if sensor has attribute formulas
        self._add_self_reference_if_needed(sensor_config, entities_added)

        if entities_added:
            self._logger.debug(
                "Added %d entity IDs from sensor %s: %s", len(entities_added), sensor_config.unique_id, sorted(entities_added)
            )

    def _add_entity_if_valid(self, entity_id: str | None, entities_added: set[str]) -> None:
        """Add entity ID to index if it's valid."""
        if not entity_id:
            return
        base_entity_id = self._extract_base_entity_id(entity_id)
        if base_entity_id:
            self._entity_ids.add(base_entity_id)
            entities_added.add(base_entity_id)

    def _add_formula_entities(self, formula: FormulaConfig, entities_added: set[str]) -> None:
        """Add entity IDs from a formula to the index."""
        # Add entity IDs from formula variables
        self._add_variable_entities(formula.variables, entities_added)

        # Add entity IDs from formula string and attributes
        parser = DependencyParser(self._hass)
        self._add_formula_string_entities(formula, parser, entities_added)
        self._add_attribute_entities(formula.attributes, parser, entities_added)

        # Check formula metadata for entity references
        self._extract_entities_from_metadata(formula.metadata, parser, entities_added)

    def _add_variable_entities(self, variables: dict[str, Any] | None, entities_added: set[str]) -> None:
        """Add entity IDs from formula variables."""
        if not variables:
            return
        for _var_name, var_value in variables.items():
            if isinstance(var_value, str):
                base_entity_id = self._extract_base_entity_id(var_value)
                if base_entity_id:
                    self._entity_ids.add(base_entity_id)
                    entities_added.add(base_entity_id)

    def _add_formula_string_entities(self, formula: FormulaConfig, parser: DependencyParser, entities_added: set[str]) -> None:
        """Add entity IDs from formula string."""
        formula_entities = parser.extract_entity_references(formula.formula)
        for entity_id in formula_entities:
            if self._is_entity_id(entity_id):
                self._entity_ids.add(entity_id)
                entities_added.add(entity_id)

    def _add_attribute_entities(self, attributes: dict[str, Any], parser: DependencyParser, entities_added: set[str]) -> None:
        """Add entity IDs from formula attributes."""
        for _attr_name, attr_value in attributes.items():
            if isinstance(attr_value, str):
                attr_entities = parser.extract_entity_references(attr_value)
                for entity_id in attr_entities:
                    if self._is_entity_id(entity_id):
                        self._entity_ids.add(entity_id)
                        entities_added.add(entity_id)

    def _add_self_reference_if_needed(self, sensor_config: SensorConfig, entities_added: set[str]) -> None:
        """Add self-reference if sensor has attribute formulas."""
        has_attribute_formulas = any(
            formula.id.startswith(f"{sensor_config.unique_id}_")
            for formula in sensor_config.formulas
            if formula.id != sensor_config.unique_id
        )

        if has_attribute_formulas:
            self_entity_id = f"sensor.{sensor_config.unique_id}"
            self._entity_ids.add(self_entity_id)
            entities_added.add(self_entity_id)

    def remove_sensor_entities(self, sensor_config: SensorConfig) -> None:
        """
        Remove all entity IDs from a sensor configuration from the index.

        Args:
            sensor_config: Sensor configuration to remove entity IDs from
        """
        entities_to_remove: set[str] = set()

        # Remove explicit sensor entity_id if present
        self._remove_entity_if_valid(sensor_config.entity_id, entities_to_remove)

        # Remove entity IDs from formulas
        for formula in sensor_config.formulas:
            self._remove_formula_entities(formula, entities_to_remove)

        # Check sensor-level metadata for entity references
        parser = DependencyParser(self._hass)
        self._extract_entities_from_metadata_for_removal(sensor_config.metadata, parser, entities_to_remove)

        # Remove self-reference if sensor had attribute formulas
        self._remove_self_reference_if_needed(sensor_config, entities_to_remove)

        # Remove from index
        for entity_id in entities_to_remove:
            self._entity_ids.discard(entity_id)

        if entities_to_remove:
            self._logger.debug(
                "Removed %d entity IDs from sensor %s: %s",
                len(entities_to_remove),
                sensor_config.unique_id,
                sorted(entities_to_remove),
            )

    def _remove_entity_if_valid(self, entity_id: str | None, entities_to_remove: set[str]) -> None:
        """Remove entity ID from index if it's valid."""
        if not entity_id:
            return
        base_entity_id = self._extract_base_entity_id(entity_id)
        if base_entity_id:
            entities_to_remove.add(base_entity_id)

    def _remove_formula_entities(self, formula: FormulaConfig, entities_to_remove: set[str]) -> None:
        """Remove entity IDs from a formula from the index."""
        # Remove entity IDs from formula variables
        self._remove_variable_entities(formula.variables, entities_to_remove)

        # Remove entity IDs from formula string and attributes
        parser = DependencyParser(self._hass)
        self._remove_formula_string_entities(formula, parser, entities_to_remove)
        self._remove_attribute_entities(formula.attributes, parser, entities_to_remove)

        # Check formula metadata for entity references
        self._extract_entities_from_metadata_for_removal(formula.metadata, parser, entities_to_remove)

    def _remove_variable_entities(self, variables: dict[str, Any] | None, entities_to_remove: set[str]) -> None:
        """Remove entity IDs from formula variables."""
        if not variables:
            return
        for _var_name, var_value in variables.items():
            if isinstance(var_value, str):
                base_entity_id = self._extract_base_entity_id(var_value)
                if base_entity_id:
                    entities_to_remove.add(base_entity_id)

    def _remove_formula_string_entities(
        self, formula: FormulaConfig, parser: DependencyParser, entities_to_remove: set[str]
    ) -> None:
        """Remove entity IDs from formula string."""
        formula_entities = parser.extract_entity_references(formula.formula)
        for entity_id in formula_entities:
            if self._is_entity_id(entity_id):
                entities_to_remove.add(entity_id)

    def _remove_attribute_entities(
        self, attributes: dict[str, Any], parser: DependencyParser, entities_to_remove: set[str]
    ) -> None:
        """Remove entity IDs from formula attributes."""
        for _attr_name, attr_value in attributes.items():
            if isinstance(attr_value, str):
                attr_entities = parser.extract_entity_references(attr_value)
                for entity_id in attr_entities:
                    if self._is_entity_id(entity_id):
                        entities_to_remove.add(entity_id)

    def _remove_self_reference_if_needed(self, sensor_config: SensorConfig, entities_to_remove: set[str]) -> None:
        """Remove self-reference if sensor had attribute formulas."""
        has_attribute_formulas = any(
            formula.id.startswith(f"{sensor_config.unique_id}_")
            for formula in sensor_config.formulas
            if formula.id != sensor_config.unique_id
        )

        if has_attribute_formulas:
            self_entity_id = f"sensor.{sensor_config.unique_id}"
            entities_to_remove.add(self_entity_id)

    def add_global_entities(self, global_variables: dict[str, Any]) -> None:
        """
        Add entity IDs from global variables to the index.

        Args:
            global_variables: Global variables dictionary
        """
        entities_added = set()

        for _var_name, var_value in global_variables.items():
            # Extract base entity ID from potentially complex references
            if isinstance(var_value, str):
                base_entity_id = self._extract_base_entity_id(var_value)
                if base_entity_id:
                    self._entity_ids.add(base_entity_id)
                    entities_added.add(base_entity_id)

        if entities_added:
            self._logger.debug("Added %d entity IDs from global variables: %s", len(entities_added), sorted(entities_added))

    def remove_global_entities(self, global_variables: dict[str, Any]) -> None:
        """
        Remove entity IDs from global variables from the index.

        Args:
            global_variables: Global variables dictionary
        """
        entities_to_remove = set()

        for _var_name, var_value in global_variables.items():
            # Extract base entity ID from potentially complex references
            if isinstance(var_value, str):
                base_entity_id = self._extract_base_entity_id(var_value)
                if base_entity_id:
                    entities_to_remove.add(base_entity_id)

        # Remove from index
        for entity_id in entities_to_remove:
            self._entity_ids.discard(entity_id)

        if entities_to_remove:
            self._logger.debug(
                "Removed %d entity IDs from global variables: %s", len(entities_to_remove), sorted(entities_to_remove)
            )

    def contains(self, entity_id: str) -> bool:
        """
        Check if an entity ID is tracked in the index.

        Args:
            entity_id: Entity ID to check

        Returns:
            True if entity ID is tracked, False otherwise
        """
        return entity_id in self._entity_ids

    def get_all_entities(self) -> set[str]:
        """
        Get all tracked entity IDs.

        Returns:
            Set of all tracked entity IDs
        """
        return self._entity_ids.copy()

    def clear(self) -> None:
        """Clear all tracked entity IDs."""
        count = len(self._entity_ids)
        self._entity_ids.clear()
        self._logger.debug("Cleared %d entity IDs from index", count)

    def get_stats(self) -> dict[str, Any]:
        """
        Get index statistics.

        Returns:
            Dictionary with index statistics
        """
        return {
            "total_entities": len(self._entity_ids),
            "tracked_entities": len(self._entity_ids),  # More descriptive name
        }

    def _is_entity_id(self, value: str) -> bool:
        """
        Check if a string value represents a valid Home Assistant entity ID.

        Uses NameResolver validation for consistency.

        Args:
            value: String value to check

        Returns:
            True if value represents a valid entity ID
        """
        if not isinstance(value, str):
            return False

        # Use NameResolver for validation
        temp_resolver = NameResolver(self._hass, {})
        return temp_resolver.validate_entity_id(value)

    def _extract_entities_from_metadata(
        self, metadata: dict[str, Any], parser: DependencyParser, entities_added: set[str]
    ) -> None:
        """Extract entity IDs from metadata dictionary recursively.

        Args:
            metadata: Metadata dictionary to search
            parser: DependencyParser instance for entity extraction
            entities_added: Set to add found entities to
        """
        if not metadata:
            return

        for _key, value in metadata.items():
            self._process_metadata_value(value, parser, entities_added, add_to_index=True)

    def _process_metadata_value(self, value: Any, parser: DependencyParser, entities_set: set[str], add_to_index: bool) -> None:
        """Process a single metadata value for entity extraction."""
        if isinstance(value, str):
            self._extract_entities_from_string(value, parser, entities_set, add_to_index)
        elif isinstance(value, dict):
            self._extract_entities_from_metadata(value, parser, entities_set)
        elif isinstance(value, list):
            self._extract_entities_from_list(value, parser, entities_set, add_to_index)

    def _extract_entities_from_string(
        self, value: str, parser: DependencyParser, entities_set: set[str], add_to_index: bool
    ) -> None:
        """Extract entity IDs from a string value."""
        metadata_entities = parser.extract_entity_references(value)
        for entity_id in metadata_entities:
            if self._is_entity_id(entity_id):
                if add_to_index:
                    self._entity_ids.add(entity_id)
                entities_set.add(entity_id)

    def _extract_entities_from_list(
        self, value: list[Any], parser: DependencyParser, entities_set: set[str], add_to_index: bool
    ) -> None:
        """Extract entity IDs from a list value."""
        for item in value:
            if isinstance(item, str):
                self._extract_entities_from_string(item, parser, entities_set, add_to_index)
            elif isinstance(item, dict):
                self._extract_entities_from_metadata(item, parser, entities_set)

    def _extract_entities_from_metadata_for_removal(
        self, metadata: dict[str, Any], parser: DependencyParser, entities_to_remove: set[str]
    ) -> None:
        """Extract entity IDs from metadata dictionary for removal.

        Args:
            metadata: Metadata dictionary to search
            parser: DependencyParser instance for entity extraction
            entities_to_remove: Set to add found entities to
        """
        if not metadata:
            return

        for _key, value in metadata.items():
            self._process_metadata_value(value, parser, entities_to_remove, add_to_index=False)
