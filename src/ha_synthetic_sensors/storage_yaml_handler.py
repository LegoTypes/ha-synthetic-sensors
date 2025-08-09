"""
YAML Import/Export Handler for Storage Manager.

This module handles the conversion between internal sensor configurations
and YAML format for import/export operations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import yaml as yaml_lib

from .config_models import FormulaConfig, SensorConfig
from .constants_alternate import UNAVAILABLE_KEY, UNKNOWN_KEY

if TYPE_CHECKING:
    from .storage_manager import StorageManager

__all__ = ["YamlHandler"]

_LOGGER = logging.getLogger(__name__)


class YamlHandler:
    """Handles YAML import/export operations for storage manager."""

    def __init__(self, storage_manager: StorageManager) -> None:
        """Initialize YAML handler."""
        self.storage_manager = storage_manager

    def export_yaml(self, sensor_set_id: str) -> str:
        """Export sensor set to YAML format."""
        data = self.storage_manager.data

        if sensor_set_id not in data["sensor_sets"]:
            raise ValueError(f"Sensor set not found: {sensor_set_id}")

        sensor_set_data = data["sensor_sets"][sensor_set_id]
        global_settings = sensor_set_data.get("global_settings", {})

        # Get sensors for this sensor set
        sensors = [
            self.storage_manager.deserialize_sensor_config(stored_sensor["config_data"])
            for stored_sensor in data["sensors"].values()
            if stored_sensor.get("sensor_set_id") == sensor_set_id
        ]

        yaml_structure = self._build_yaml_structure(sensors, global_settings)
        return yaml_lib.dump(yaml_structure, default_flow_style=False, sort_keys=False)

    def _build_yaml_structure(self, sensors: list[SensorConfig], global_settings: dict[str, Any]) -> dict[str, Any]:
        """Build the YAML structure from sensors and global settings."""
        yaml_data: dict[str, Any] = {"version": "1.0"}

        # Add global settings if present
        if global_settings:
            yaml_data["global_settings"] = global_settings

        # Add sensors
        sensors_dict = {}
        for sensor in sensors:
            sensor_dict = self._build_sensor_dict(sensor, global_settings)
            sensors_dict[sensor.unique_id] = sensor_dict

        if sensors_dict:
            yaml_data["sensors"] = sensors_dict

        return yaml_data

    def _build_sensor_dict(self, sensor_config: SensorConfig, global_settings: dict[str, Any]) -> dict[str, Any]:
        """Build sensor dictionary for YAML export."""
        sensor_dict: dict[str, Any] = {}

        # Add device identifier if needed
        self._add_device_identifier_if_needed(sensor_dict, sensor_config, global_settings)

        # Add optional sensor fields
        self._add_optional_sensor_fields(sensor_dict, sensor_config)

        # Process formulas
        main_formula, attributes_dict = self._process_formulas(sensor_config)

        # Add main formula details
        if main_formula:
            self._add_main_formula_details(sensor_dict, main_formula)

        # Add attributes if present
        if attributes_dict:
            sensor_dict["attributes"] = attributes_dict

        return sensor_dict

    def _add_device_identifier_if_needed(
        self, sensor_dict: dict[str, Any], sensor_config: SensorConfig, global_settings: dict[str, Any]
    ) -> None:
        """Add device identifier to sensor dict if it differs from global setting."""
        global_device_identifier = global_settings.get("device_identifier")
        if sensor_config.device_identifier != global_device_identifier:
            sensor_dict["device_identifier"] = sensor_config.device_identifier

    def _add_optional_sensor_fields(self, sensor_dict: dict[str, Any], sensor_config: SensorConfig) -> None:
        """Add optional sensor fields to the sensor dictionary."""
        if sensor_config.entity_id:
            sensor_dict["entity_id"] = sensor_config.entity_id
        if sensor_config.name:
            sensor_dict["name"] = sensor_config.name

        # Add sensor-level metadata if present
        if hasattr(sensor_config, "metadata") and sensor_config.metadata:
            sensor_dict["metadata"] = sensor_config.metadata
        # Note: Formula-level metadata is handled in _add_main_formula_details

    def _process_formulas(
        self, sensor_config: SensorConfig
    ) -> tuple[FormulaConfig | None, dict[str, Any | int | float | str | bool]]:
        """Process formulas and separate main formula from attributes."""
        main_formula = None
        attributes_dict: dict[str, Any | int | float | str | bool] = {}

        for formula in sensor_config.formulas:
            # Main formula has id matching the sensor's unique_id
            # Attribute formulas have id format: {sensor_unique_id}_{attribute_name}
            if formula.id == sensor_config.unique_id:
                main_formula = formula
                # Also extract literal attributes from main formula's attributes dictionary
                if hasattr(formula, "attributes") and formula.attributes:
                    for attr_name, attr_value in formula.attributes.items():
                        attributes_dict[attr_name] = attr_value
            elif formula.id.startswith(f"{sensor_config.unique_id}_"):
                # Extract attribute name from formula id
                attribute_name = formula.id[len(sensor_config.unique_id) + 1 :]
                attributes_dict[attribute_name] = self._build_attribute_dict(formula)

        return main_formula, attributes_dict

    def _build_attribute_dict(self, formula: FormulaConfig) -> dict[str, Any] | int | float | str | bool:
        """Build attribute dictionary from formula configuration."""
        # Check if this is a literal value formula (e.g., formula="240" with no variables)
        if not formula.variables and formula.formula:
            literal_value = self._parse_literal_value(formula.formula)
            if literal_value is not None:
                # Return the literal value directly (not wrapped in a dict)
                return literal_value

        # Handle as formula object (existing behavior)
        attr_dict: dict[str, Any] = {"formula": formula.formula}

        if formula.variables:
            # Filter out ComputedVariable instances for YAML serialization
            variables_dict: dict[str, str | int | float] = {
                k: v
                for k, v in formula.variables.items()
                if not hasattr(v, "formula")  # Skip ComputedVariable instances
            }
            if variables_dict:  # Only add if there are simple variables
                attr_dict["variables"] = variables_dict

        # Add metadata if present
        metadata = self._extract_formula_metadata(formula)
        if metadata:
            attr_dict["metadata"] = metadata

        return attr_dict

    def _extract_formula_metadata(self, formula: FormulaConfig) -> dict[str, Any] | None:
        """Extract metadata from formula configuration."""
        # Add metadata if present
        if hasattr(formula, "metadata") and formula.metadata:
            return formula.metadata

        # Legacy field support - migrate to metadata format
        legacy_metadata = self._extract_legacy_formula_metadata(formula)
        return legacy_metadata if legacy_metadata else None

    def _extract_legacy_formula_metadata(self, formula: FormulaConfig) -> dict[str, Any] | None:
        """Extract legacy metadata fields from formula configuration."""
        legacy_metadata = {}

        if hasattr(formula, "unit_of_measurement") and formula.unit_of_measurement:
            legacy_metadata["unit_of_measurement"] = formula.unit_of_measurement
        if hasattr(formula, "device_class") and formula.device_class:
            legacy_metadata["device_class"] = formula.device_class
        if hasattr(formula, "state_class") and formula.state_class:
            legacy_metadata["state_class"] = formula.state_class
        if hasattr(formula, "icon") and formula.icon:
            legacy_metadata["icon"] = formula.icon

        return legacy_metadata if legacy_metadata else None

    def _parse_literal_value(self, formula: str) -> int | float | str | bool | None:
        """Parse formula as literal value if possible."""
        # Try numeric parsing first
        numeric_result = self._parse_numeric_literal(formula)
        if numeric_result is not None:
            return numeric_result

        # Try string literal parsing
        string_result = self._parse_string_literal(formula)
        if string_result is not None:
            return string_result

        # Try boolean literal parsing
        boolean_result = self._parse_boolean_literal(formula)
        if boolean_result is not None:
            return boolean_result

        # Try simple string literal parsing (no operators)
        simple_result = self._parse_simple_string_literal(formula)
        if simple_result is not None:
            return simple_result

        return None

    def _parse_numeric_literal(self, formula: str) -> int | float | None:
        """Parse numeric literal values."""
        try:
            # Integer literal
            if formula.isdigit():
                return int(formula)

            # Float literal
            if formula.replace(".", "").replace("-", "").isdigit() and formula.count(".") <= 1:
                return float(formula)
        except (ValueError, AttributeError):
            pass

        return None

    def _parse_string_literal(self, formula: str) -> str | None:
        """Parse string literal values with quotes."""
        try:
            if (formula.startswith('"') and formula.endswith('"')) or (formula.startswith("'") and formula.endswith("'")):
                return formula[1:-1]
        except (ValueError, AttributeError):
            pass
        return None

    def _parse_boolean_literal(self, formula: str) -> bool | None:
        """Parse boolean literal values."""
        try:
            if formula == "True":
                return True
            if formula == "False":
                return False
        except (ValueError, AttributeError):
            pass
        return None

    def _parse_simple_string_literal(self, formula: str) -> str | None:
        """Parse simple string literal without operators."""
        try:
            # Check if it contains any mathematical operators
            if not any(op in formula for op in ["+", "-", "*", "/", "(", ")"]):
                return formula
        except (ValueError, AttributeError):
            pass
        return None

    def _add_main_formula_details(self, sensor_dict: dict[str, Any], main_formula: FormulaConfig) -> None:
        """Add main formula details to sensor dictionary."""
        sensor_dict["formula"] = main_formula.formula

        # Add main formula alternate state handlers first (sensor level)
        if main_formula.alternate_state_handler:
            self._add_alternate_state_handlers(sensor_dict, main_formula.alternate_state_handler)

        # Add variables with proper serialization
        if main_formula.variables:
            sensor_dict["variables"] = self._serialize_variables(main_formula.variables)

        # Add metadata if present (formula-level metadata overrides sensor-level metadata)
        metadata = self._extract_formula_metadata(main_formula)
        if metadata:
            self._merge_metadata(sensor_dict, metadata)

    def _merge_metadata(self, sensor_dict: dict[str, Any], formula_metadata: dict[str, Any]) -> None:
        """Merge formula metadata with existing sensor metadata."""
        existing_metadata = sensor_dict.get("metadata", {})
        merged_metadata = {**existing_metadata, **formula_metadata}
        sensor_dict["metadata"] = merged_metadata

    def _add_alternate_state_handlers(self, sensor_dict: dict[str, Any], alternate_state_handler: Any) -> None:
        """Add alternate state handlers to sensor dictionary with proper casing."""
        if hasattr(alternate_state_handler, "unavailable") and alternate_state_handler.unavailable is not None:
            sensor_dict[UNAVAILABLE_KEY] = alternate_state_handler.unavailable
        if hasattr(alternate_state_handler, "unknown") and alternate_state_handler.unknown is not None:
            sensor_dict[UNKNOWN_KEY] = alternate_state_handler.unknown

    def _serialize_variables(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Serialize variables dictionary, converting ComputedVariable objects to YAML format."""
        serialized_variables = {}

        for name, value in variables.items():
            if hasattr(value, "formula"):  # ComputedVariable object
                var_dict = {"formula": value.formula}

                # Add alternate state handlers with proper casing
                if hasattr(value, "alternate_state_handler") and value.alternate_state_handler:
                    if (
                        hasattr(value.alternate_state_handler, "unavailable")
                        and value.alternate_state_handler.unavailable is not None
                    ):
                        var_dict[UNAVAILABLE_KEY] = value.alternate_state_handler.unavailable
                    if hasattr(value.alternate_state_handler, "unknown") and value.alternate_state_handler.unknown is not None:
                        var_dict[UNKNOWN_KEY] = value.alternate_state_handler.unknown

                serialized_variables[name] = var_dict
            else:
                # Simple variable (string, int, float)
                serialized_variables[name] = value

        return serialized_variables
