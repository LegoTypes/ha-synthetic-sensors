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

    def _process_formulas(self, sensor_config: SensorConfig) -> tuple[FormulaConfig | None, dict[str, Any]]:
        """Process formulas and separate main formula from attributes."""
        main_formula = None
        attributes_dict = {}

        for formula in sensor_config.formulas:
            # Main formula has id matching the sensor's unique_id
            # Attribute formulas have id format: {sensor_unique_id}_{attribute_name}
            if formula.id == sensor_config.unique_id:
                main_formula = formula
            elif formula.id.startswith(f"{sensor_config.unique_id}_"):
                # Extract attribute name from formula id
                attribute_name = formula.id[len(sensor_config.unique_id) + 1 :]
                attributes_dict[attribute_name] = self._build_attribute_dict(formula)

        return main_formula, attributes_dict

    def _build_attribute_dict(self, formula: FormulaConfig) -> dict[str, Any]:
        """Build attribute dictionary from formula configuration."""
        attr_dict: dict[str, Any] = {"formula": formula.formula}

        if formula.variables:
            variables_dict: dict[str, str | int | float] = dict(formula.variables)
            attr_dict["variables"] = variables_dict

        # Add metadata if present
        if hasattr(formula, "metadata") and formula.metadata:
            attr_dict["metadata"] = formula.metadata
        else:
            # Legacy field support - migrate to metadata format
            legacy_metadata = {}
            if hasattr(formula, "unit_of_measurement") and formula.unit_of_measurement:
                legacy_metadata["unit_of_measurement"] = formula.unit_of_measurement
            if hasattr(formula, "device_class") and formula.device_class:
                legacy_metadata["device_class"] = formula.device_class
            if hasattr(formula, "state_class") and formula.state_class:
                legacy_metadata["state_class"] = formula.state_class
            if hasattr(formula, "icon") and formula.icon:
                legacy_metadata["icon"] = formula.icon

            if legacy_metadata:
                attr_dict["metadata"] = legacy_metadata

        return attr_dict

    def _add_main_formula_details(self, sensor_dict: dict[str, Any], main_formula: FormulaConfig) -> None:
        """Add main formula details to sensor dictionary."""
        sensor_dict["formula"] = main_formula.formula

        if main_formula.variables:
            sensor_dict["variables"] = dict(main_formula.variables)

        # Add metadata if present (formula-level metadata overrides sensor-level metadata)
        if hasattr(main_formula, "metadata") and main_formula.metadata:
            # Merge with existing sensor metadata, with formula metadata taking precedence
            existing_metadata = sensor_dict.get("metadata", {})
            merged_metadata = {**existing_metadata, **main_formula.metadata}
            sensor_dict["metadata"] = merged_metadata
        else:
            # Legacy field support - migrate to metadata format
            legacy_metadata = {}
            if hasattr(main_formula, "unit_of_measurement") and main_formula.unit_of_measurement:
                legacy_metadata["unit_of_measurement"] = main_formula.unit_of_measurement
            if hasattr(main_formula, "device_class") and main_formula.device_class:
                legacy_metadata["device_class"] = main_formula.device_class
            if hasattr(main_formula, "state_class") and main_formula.state_class:
                legacy_metadata["state_class"] = main_formula.state_class
            if hasattr(main_formula, "icon") and main_formula.icon:
                legacy_metadata["icon"] = main_formula.icon

            if legacy_metadata:
                # Merge with existing sensor metadata, with formula metadata taking precedence
                existing_metadata = sensor_dict.get("metadata", {})
                merged_metadata = {**existing_metadata, **legacy_metadata}
                sensor_dict["metadata"] = merged_metadata
