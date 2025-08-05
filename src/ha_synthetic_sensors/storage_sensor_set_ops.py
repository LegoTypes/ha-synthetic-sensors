"""
Sensor Set Operations Handler for Storage Manager.

This module handles sensor set creation, deletion, and metadata management
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, cast

from .config_manager import ConfigManager
from .config_models import ComputedVariable, Config, FormulaConfig
from .config_types import AttributeValue, GlobalSettingsDict
from .cross_sensor_reference_reassignment import BulkYamlReassignment
from .exceptions import SyntheticSensorsError

if TYPE_CHECKING:
    from .storage_manager import SensorSetMetadata, StorageManager

__all__ = ["SensorSetOpsHandler"]

_LOGGER = logging.getLogger(__name__)


class SensorSetOpsHandler:
    """Handles sensor set operations for storage manager."""

    def __init__(self, storage_manager: StorageManager) -> None:
        """Initialize sensor set operations handler."""
        self.storage_manager = storage_manager

    async def async_create_sensor_set(
        self,
        sensor_set_id: str,
        device_identifier: str | None = None,
        name: str | None = None,
        description: str | None = None,
        global_settings: GlobalSettingsDict | None = None,
    ) -> None:
        """Create a new sensor set.

        Args:
            sensor_set_id: Unique identifier for the sensor set
            device_identifier: Optional device identifier for all sensors in the set
            name: Optional human-readable name for the sensor set
            global_settings: Optional global settings for the sensor set
        """
        data = self.storage_manager.data

        if sensor_set_id in data["sensor_sets"]:
            raise SyntheticSensorsError(f"Sensor set already exists: {sensor_set_id}")

        # Create sensor set entry
        sensor_set_data = {
            "sensor_set_id": sensor_set_id,
            "device_identifier": device_identifier,
            "name": name or sensor_set_id,
            "description": description,
            "created_at": self.storage_manager.get_current_timestamp(),
            "updated_at": self.storage_manager.get_current_timestamp(),
            "sensor_count": 0,
            "global_settings": global_settings or {},
        }

        data["sensor_sets"][sensor_set_id] = sensor_set_data
        await self.storage_manager.async_save()

        _LOGGER.debug("Created sensor set: %s", sensor_set_id)

    async def async_delete_sensor_set(self, sensor_set_id: str) -> bool:
        """Delete a sensor set and all its sensors.

        Args:
            sensor_set_id: ID of the sensor set to delete

        Returns:
            True if deleted, False if not found
        """
        data = self.storage_manager.data

        if sensor_set_id not in data["sensor_sets"]:
            _LOGGER.warning("Sensor set not found for deletion: %s", sensor_set_id)
            return False

        # Delete all sensors in the sensor set
        sensors_to_delete = [
            unique_id
            for unique_id, stored_sensor in data["sensors"].items()
            if stored_sensor.get("sensor_set_id") == sensor_set_id
        ]

        for unique_id in sensors_to_delete:
            del data["sensors"][unique_id]
            _LOGGER.debug("Deleted sensor %s from sensor set %s", unique_id, sensor_set_id)

        # Delete the sensor set
        del data["sensor_sets"][sensor_set_id]
        await self.storage_manager.async_save()

        _LOGGER.debug("Deleted sensor set %s and %d sensors", sensor_set_id, len(sensors_to_delete))
        return True

    def get_sensor_set_metadata(self, sensor_set_id: str) -> SensorSetMetadata | None:
        """Get metadata for a sensor set.

        Args:
            sensor_set_id: ID of the sensor set

        Returns:
            SensorSetMetadata if found, None otherwise
        """
        from .storage_manager import SensorSetMetadata  # pylint: disable=import-outside-toplevel

        data = self.storage_manager.data

        if sensor_set_id not in data["sensor_sets"]:
            return None

        sensor_set_data = data["sensor_sets"][sensor_set_id]

        return SensorSetMetadata(
            sensor_set_id=sensor_set_data["sensor_set_id"],
            device_identifier=sensor_set_data.get("device_identifier"),
            name=sensor_set_data.get("name", sensor_set_id),
            description=sensor_set_data.get("description"),
            created_at=sensor_set_data.get("created_at", ""),
            updated_at=sensor_set_data.get("updated_at", ""),
            sensor_count=sensor_set_data.get("sensor_count", 0),
            global_settings=sensor_set_data.get("global_settings", {}),
        )

    def list_sensor_sets(self, device_identifier: str | None = None) -> list[SensorSetMetadata]:
        """List all sensor sets, optionally filtered by device identifier.

        Args:
            device_identifier: Optional device identifier to filter by

        Returns:
            List of sensor set metadata
        """
        from .storage_manager import SensorSetMetadata  # pylint: disable=import-outside-toplevel

        data = self.storage_manager.data
        sensor_sets = []

        for sensor_set_data in data["sensor_sets"].values():
            # Filter by device identifier if specified
            if device_identifier is not None and sensor_set_data.get("device_identifier") != device_identifier:
                continue

            metadata = SensorSetMetadata(
                sensor_set_id=sensor_set_data["sensor_set_id"],
                device_identifier=sensor_set_data.get("device_identifier"),
                name=sensor_set_data.get("name", sensor_set_data["sensor_set_id"]),
                description=sensor_set_data.get("description"),
                created_at=sensor_set_data.get("created_at", ""),
                updated_at=sensor_set_data.get("updated_at", ""),
                sensor_count=sensor_set_data.get("sensor_count", 0),
                global_settings=sensor_set_data.get("global_settings", {}),
            )
            sensor_sets.append(metadata)

        # Sort by creation time (newest first), handle None/empty values
        return sorted(sensor_sets, key=lambda x: x.created_at or "", reverse=True)

    def sensor_set_exists(self, sensor_set_id: str) -> bool:
        """Check if a sensor set exists.

        Args:
            sensor_set_id: ID of the sensor set to check

        Returns:
            True if the sensor set exists, False otherwise
        """
        data = self.storage_manager.data
        return sensor_set_id in data["sensor_sets"]

    def get_sensor_count(self, sensor_set_id: str | None = None) -> int:
        """Get the number of sensors in a sensor set or total.

        Args:
            sensor_set_id: Optional sensor set ID. If None, returns total count.

        Returns:
            Number of sensors
        """
        data = self.storage_manager.data

        if sensor_set_id is None:
            return len(data["sensors"])

        if sensor_set_id not in data["sensor_sets"]:
            return 0

        return sum(1 for stored_sensor in data["sensors"].values() if stored_sensor.get("sensor_set_id") == sensor_set_id)

    def get_sensor_set_header(self, sensor_set_id: str) -> dict[str, Any]:
        """Get sensor set header data for YAML export/validation.

        Args:
            sensor_set_id: ID of the sensor set

        Returns:
            Dictionary containing sensor set header data
        """
        data = self.storage_manager.data

        if sensor_set_id not in data["sensor_sets"]:
            return {}

        sensor_set_data = data["sensor_sets"][sensor_set_id]
        global_settings = sensor_set_data.get("global_settings", {})

        # Return a copy of global settings as the header
        return dict(global_settings)

    async def async_from_yaml(
        self,
        yaml_content: str,
        sensor_set_id: str,
        device_identifier: str | None = None,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        """Import YAML content into a sensor set.

        Args:
            yaml_content: YAML content to import
            sensor_set_id: Target sensor set ID
            device_identifier: Optional device identifier override
            replace_existing: Whether to replace existing sensor set

        Returns:
            Dictionary with import results
        """
        config_manager = ConfigManager(self.storage_manager.hass)
        config = config_manager.load_from_yaml(yaml_content)

        # Step 1: Replace self-references with 'state' token before entity registration
        # This prevents self-references from being treated as cross-sensor references
        config_with_state_tokens = self._replace_self_references_with_state_token(config)

        # Step 2: Resolve cross-sensor references (entity registration + collision handling)
        resolved_config = await self._resolve_cross_sensor_references(
            config_with_state_tokens, sensor_set_id, device_identifier
        )

        # Step 3: Update global settings on all evaluators after cross-reference resolution
        # This ensures evaluators have access to current global variables for inheritance
        self.storage_manager.entity_change_handler.update_global_settings(
            cast(dict[str, Any], resolved_config.global_settings) if resolved_config.global_settings else None
        )

        # Use the existing async_from_config method to avoid code duplication
        if replace_existing and self.sensor_set_exists(sensor_set_id):
            await self.async_delete_sensor_set(sensor_set_id)

        await self.storage_manager.async_from_config(resolved_config, sensor_set_id, device_identifier)
        stored_sensors = [sensor_config.unique_id for sensor_config in config.sensors]

        return {
            "sensor_set_id": sensor_set_id,
            "sensors_imported": len(stored_sensors),
            "sensor_unique_ids": stored_sensors,
            "global_settings": config.global_settings,
        }

    def _replace_self_references_with_state_token(self, config: Config) -> Config:
        """Replace self-references in the configuration with 'state' token.

        This handles both sensor key references (e.g., 'my_sensor') and entity ID references
        (e.g., 'sensor.my_sensor') within the same sensor's formulas, variables, and attributes.

        Args:
            config: Original configuration

        Returns:
            Configuration with self-references replaced by 'state' token
        """
        updated_sensors = []

        for sensor_config in config.sensors:
            # Create a copy with empty formulas to avoid modifying the original
            updated_sensor = sensor_config.copy_with_overrides(formulas=[])

            # Process each formula
            for formula_config in sensor_config.formulas:
                updated_formula = self._replace_self_references_in_formula(
                    formula_config, sensor_config.unique_id, sensor_config.entity_id
                )
                updated_sensor.formulas.append(updated_formula)

            updated_sensors.append(updated_sensor)

        return Config(
            version=config.version,
            global_settings=config.global_settings.copy(),
            sensors=updated_sensors,
            cross_sensor_references=config.cross_sensor_references.copy(),
        )

    def _replace_self_references_in_formula(
        self, formula_config: FormulaConfig, sensor_key: str, entity_id: str | None
    ) -> FormulaConfig:
        """Replace self-references in a single formula with 'state' token.

        Args:
            formula_config: Original formula configuration
            sensor_key: The sensor's unique_id (sensor key)
            entity_id: The sensor's entity_id (if specified)

        Returns:
            Updated formula configuration with self-references replaced
        """
        self_reference_patterns = self._build_self_reference_patterns(sensor_key, entity_id)

        # Replace self-references in all components
        updated_formula = self._replace_self_references_in_text(formula_config.formula, self_reference_patterns)
        updated_variables = self._process_variables_for_self_references(formula_config.variables, self_reference_patterns)
        updated_attributes = self._process_attributes_for_self_references(formula_config.attributes, self_reference_patterns)

        return FormulaConfig(
            id=formula_config.id,
            formula=updated_formula,
            name=formula_config.name,
            metadata=formula_config.metadata.copy(),
            attributes=updated_attributes,
            dependencies=formula_config.dependencies.copy(),  # Dependencies handled separately
            variables=updated_variables,
            alternate_state_handler=formula_config.alternate_state_handler,  # Preserve alternate state handler
        )

    def _build_self_reference_patterns(self, sensor_key: str, entity_id: str | None) -> set[str]:
        """Build set of patterns that constitute self-references for a sensor."""
        self_reference_patterns = {sensor_key}
        if entity_id:
            self_reference_patterns.add(entity_id)

        # Also add the sensor.{sensor_key} format as a self-reference pattern
        # This handles cases where the sensor references itself using the full entity ID format
        sensor_dot_key = f"sensor.{sensor_key}"
        self_reference_patterns.add(sensor_dot_key)

        return self_reference_patterns

    def _process_variables_for_self_references(
        self, variables: dict[str, str | int | float | ComputedVariable], self_reference_patterns: set[str]
    ) -> dict[str, str | int | float | ComputedVariable]:
        """Process variables dictionary to replace self-references."""
        updated_variables: dict[str, str | int | float | ComputedVariable] = {}
        for var_name, var_value in variables.items():
            if isinstance(var_value, str):
                updated_variables[var_name] = self._replace_self_references_in_text(var_value, self_reference_patterns)
            else:
                updated_variables[var_name] = var_value
        return updated_variables

    def _process_attributes_for_self_references(
        self, attributes: dict[str, AttributeValue], self_reference_patterns: set[str]
    ) -> dict[str, AttributeValue]:
        """Process attributes dictionary to replace self-references."""
        updated_attributes: dict[str, AttributeValue] = {}
        for attr_name, attr_value in attributes.items():
            updated_attributes[attr_name] = self._process_single_attribute_for_self_references(
                attr_value, self_reference_patterns, attr_name
            )
        return updated_attributes

    def _process_single_attribute_for_self_references(
        self, attr_value: AttributeValue, self_reference_patterns: set[str], attr_name: str | None = None
    ) -> AttributeValue:
        """Process a single attribute value to replace self-references."""
        if isinstance(attr_value, str):
            # Simple string attribute - only replace if there's a clear sensor reference
            if not self._contains_clear_sensor_reference(attr_value, self_reference_patterns):
                _LOGGER.debug("No clear sensor reference found in attribute '%s' with value: %s", attr_name, attr_value)
                return attr_value
            _LOGGER.debug("Replacing self-references in attribute '%s' with value: %s", attr_name, attr_value)
            return self._replace_self_references_in_text(attr_value, self_reference_patterns)
        if isinstance(attr_value, dict) and "formula" in attr_value:
            # Formula-based attribute
            return self._process_formula_attribute_for_self_references(attr_value, self_reference_patterns, attr_name)
        # Non-formula attribute, keep as-is
        return attr_value

    def _contains_clear_sensor_reference(self, text: str, self_reference_patterns: set[str]) -> bool:
        """Check if text contains a clear reference to one of the sensor patterns.

        This method determines if the text contains an actual sensor reference (like 'sensor.my_sensor'
        or 'my_sensor_unique_id') rather than just literal text that happens to contain words that
        might match sensor names.

        Args:
            text: Text to check for sensor references
            self_reference_patterns: Set of patterns that constitute self-references

        Returns:
            True if text contains a clear sensor reference, False otherwise
        """
        _LOGGER.debug("Checking text '%s' for sensor references in patterns: %s", text, self_reference_patterns)

        # Build sensor keys from patterns (extract keys from entity IDs if needed)
        sensor_keys = set()
        entity_ids = set()

        for pattern in self_reference_patterns:
            if pattern.startswith("sensor."):
                entity_ids.add(pattern)
                # Extract sensor key from entity ID (part after "sensor.")
                sensor_key = pattern[7:]  # Remove "sensor." prefix
                sensor_keys.add(sensor_key)
            else:
                sensor_keys.add(pattern)

        _LOGGER.debug("Extracted sensor_keys: %s, entity_ids: %s", sensor_keys, entity_ids)

        # Check for entity ID patterns (more specific, so check first)
        for entity_id in entity_ids:
            # Pattern 1: sensor.entity_id (exact match)
            pattern1 = r"\b" + re.escape(entity_id) + r"\b"
            if re.search(pattern1, text):
                _LOGGER.debug("Found entity ID exact match for '%s' in text '%s'", entity_id, text)
                return True

            # Pattern 2: sensor.entity_id.attribute (with attribute access)
            pattern2 = r"\b" + re.escape(entity_id) + r"\.[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*"
            if re.search(pattern2, text):
                _LOGGER.debug("Found entity ID attribute access for '%s' in text '%s'", entity_id, text)
                return True

        # Check for sensor key patterns (less specific)
        for sensor_key in sensor_keys:
            # Only consider it a clear sensor reference if:
            # 1. It's the entire text (exact match), or
            # 2. It's followed by a dot and an attribute name, or
            # 3. It's part of a larger expression with operators/functions

            # Pattern 3: sensor_key as entire text
            if text.strip() == sensor_key:
                _LOGGER.debug("Found sensor key exact match: '%s' == '%s'", text.strip(), sensor_key)
                return True

            # Pattern 4: sensor_key.attribute (with attribute access)
            pattern4 = r"\b" + re.escape(sensor_key) + r"\.[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*"
            if re.search(pattern4, text):
                _LOGGER.debug("Found sensor key attribute access for '%s' in text '%s'", sensor_key, text)
                return True

            # Pattern 5: sensor_key in mathematical/logical expressions
            # Look for the sensor key surrounded by operators, parentheses, or function calls
            expression_pattern = r"(?:^|[+\-*/()=<>!&|,\s])\s*" + re.escape(sensor_key) + r"\s*(?:[+\-*/()=<>!&|,\s]|$)"
            if re.search(expression_pattern, text):
                _LOGGER.debug("Found sensor key in expression for '%s' in text '%s'", sensor_key, text)
                return True

        _LOGGER.debug("No clear sensor reference found in text '%s'", text)
        return False

    def _process_formula_attribute_for_self_references(
        self, attr_value: dict[str, Any], self_reference_patterns: set[str], attr_name: str | None = None
    ) -> dict[str, Any]:
        """Process a formula-based attribute to replace self-references."""
        updated_attr_value = attr_value.copy()

        # Update formula if present
        if isinstance(attr_value.get("formula"), str):
            # Only replace if there's a clear sensor reference
            if not self._contains_clear_sensor_reference(attr_value["formula"], self_reference_patterns):
                _LOGGER.debug(
                    "No clear sensor reference found in formula attribute '%s' with formula: %s",
                    attr_name,
                    attr_value["formula"],
                )
                updated_attr_value["formula"] = attr_value["formula"]
            else:
                _LOGGER.debug(
                    "Replacing self-references in formula attribute '%s' with formula: %s", attr_name, attr_value["formula"]
                )
                updated_attr_value["formula"] = self._replace_self_references_in_text(
                    attr_value["formula"], self_reference_patterns
                )

        # Update variables in attribute if present
        if "variables" in attr_value and isinstance(attr_value["variables"], dict):
            updated_attr_variables: dict[str, Any] = {}
            for var_name, var_val in attr_value["variables"].items():
                if isinstance(var_val, str):
                    updated_attr_variables[var_name] = self._replace_self_references_in_text(var_val, self_reference_patterns)
                else:
                    updated_attr_variables[var_name] = var_val
            updated_attr_value["variables"] = updated_attr_variables

        return updated_attr_value

    def _replace_self_references_in_text(self, text: str, self_reference_patterns: set[str]) -> str:
        """Replace self-reference patterns in text with 'state' token.

        Handles various self-reference patterns:
        - sensor_key → state
        - sensor.sensor_key → state
        - sensor_key.attribute → state.attribute
        - sensor.sensor_key.attribute → state.attribute

        Args:
            text: Text that may contain self-references
            self_reference_patterns: Set of patterns that constitute self-references

        Returns:
            Text with self-references replaced by 'state'
        """

        updated_text = text
        replacements_made = {}

        # Build sensor keys from patterns (extract keys from entity IDs if needed)
        sensor_keys = set()
        entity_ids = set()

        for pattern in self_reference_patterns:
            if pattern.startswith("sensor."):
                entity_ids.add(pattern)
                # Extract sensor key from entity ID (part after "sensor.")
                sensor_key = pattern[7:]  # Remove "sensor." prefix
                sensor_keys.add(sensor_key)
            else:
                sensor_keys.add(pattern)

        # Replace entity ID patterns first (more specific)
        for entity_id in entity_ids:
            # Pattern 1: sensor.entity_id (exact match)
            pattern1 = r"\b" + re.escape(entity_id) + r"\b"
            if re.search(pattern1, updated_text):
                updated_text = re.sub(pattern1, "state", updated_text)
                replacements_made[entity_id] = "state"

            # Pattern 2: sensor.entity_id.attribute (with attribute access)
            pattern2 = r"\b" + re.escape(entity_id) + r"(\.[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)"
            matches = re.finditer(pattern2, updated_text)
            for match in matches:
                full_match = match.group(0)
                attribute_part = match.group(1)  # The .attribute part
                replacement = "state" + attribute_part
                updated_text = updated_text.replace(full_match, replacement)
                replacements_made[full_match] = replacement

        # Replace sensor key patterns (less specific, so do after entity IDs)
        for sensor_key in sensor_keys:
            # Pattern 3: sensor_key (exact match, not part of entity ID)
            # Use negative lookbehind to avoid matching sensor_key that's part of sensor.sensor_key
            pattern3 = r"(?<!sensor\.)\b" + re.escape(sensor_key) + r"\b(?!\.[a-zA-Z_])"
            if re.search(pattern3, updated_text):
                updated_text = re.sub(pattern3, "state", updated_text)
                replacements_made[sensor_key] = "state"

            # Pattern 4: sensor_key.attribute (with attribute access, not part of entity ID)
            pattern4 = r"(?<!sensor\.)\b" + re.escape(sensor_key) + r"(\.[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)"
            matches = re.finditer(pattern4, updated_text)
            for match in matches:
                full_match = match.group(0)
                attribute_part = match.group(1)  # The .attribute part
                replacement = "state" + attribute_part
                updated_text = updated_text.replace(full_match, replacement)
                replacements_made[full_match] = replacement

        return updated_text

    async def _resolve_cross_sensor_references(
        self, config: Config, sensor_set_id: str, device_identifier: str | None
    ) -> Config:
        """Resolve cross-sensor references in configuration before storage.

        Args:
            config: Configuration with potential cross-sensor references
            sensor_set_id: Target sensor set ID
            device_identifier: Optional device identifier

        Returns:
            Configuration with resolved cross-sensor references
        """

        # Create bulk reassignment processor
        bulk_reassignment = BulkYamlReassignment(self.storage_manager.hass)

        # Create callback to collect entity IDs by registering with HA
        async def collect_entity_ids_callback(config: Config) -> dict[str, str]:
            """Register sensors with HA entity registry and collect assigned entity IDs."""
            from homeassistant.helpers import entity_registry as er  # pylint: disable=import-outside-toplevel

            entity_mappings = {}
            entity_registry = er.async_get(self.storage_manager.hass)

            # Register each sensor with HA entity registry
            for sensor_config in config.sensors:
                # Determine suggested_object_id from explicit entity_id or fallback to unique_id
                if sensor_config.entity_id:
                    # Use the object_id part from explicit entity_id (e.g., "circuit_a_power" from "sensor.circuit_a_power")
                    suggested_object_id = sensor_config.entity_id.replace("sensor.", "")
                else:
                    # Fallback to unique_id if no explicit entity_id
                    suggested_object_id = sensor_config.unique_id

                # Let HA entity registry handle collision resolution
                entry = entity_registry.async_get_or_create(
                    domain="sensor",
                    platform="synthetic_sensors",
                    unique_id=sensor_config.unique_id,
                    suggested_object_id=suggested_object_id,
                )
                entity_mappings[sensor_config.unique_id] = entry.entity_id

            return entity_mappings

        # Process with cross-reference resolution
        resolved_config = await bulk_reassignment.process_bulk_yaml(config, collect_entity_ids_callback)
        return resolved_config
