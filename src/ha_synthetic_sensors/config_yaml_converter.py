"""YAML conversion utilities for configuration objects."""

from __future__ import annotations

from typing import Any

from .config_models import Config, FormulaConfig, SensorConfig


class ConfigYamlConverter:
    """Handles conversion between Config objects and YAML dictionaries."""

    def config_to_yaml(self, config: Config) -> dict[str, Any]:
        """Convert a Config object to a YAML-serializable dictionary.

        Args:
            config: The Config object to convert

        Returns:
            Dictionary that can be serialized to YAML
        """
        yaml_dict: dict[str, Any] = {}

        # Add version
        yaml_dict["version"] = config.version

        # Add global settings if they exist
        if config.global_settings:
            yaml_dict["global_settings"] = {}
            if config.global_settings.get("variables"):
                yaml_dict["global_settings"]["variables"] = dict(config.global_settings["variables"])
            if config.global_settings.get("device_identifier"):
                yaml_dict["global_settings"]["device_identifier"] = config.global_settings["device_identifier"]

        # Add sensors
        if config.sensors:
            yaml_dict["sensors"] = {}
            for sensor in config.sensors:
                yaml_dict["sensors"][sensor.unique_id] = self._sensor_to_yaml_dict(sensor)

        return yaml_dict

    def _sensor_to_yaml_dict(self, sensor: SensorConfig) -> dict[str, Any]:
        """Convert a SensorConfig to a YAML dictionary.

        Args:
            sensor: The SensorConfig to convert

        Returns:
            Dictionary representation of the sensor
        """
        sensor_data: dict[str, Any] = {}

        # Add formulas
        if len(sensor.formulas) == 1:
            # Single formula - use simplified format
            formula = sensor.formulas[0]
            sensor_data.update(self._formula_to_yaml_dict(formula))
        elif len(sensor.formulas) > 1:
            # Multiple formulas - use array format
            sensor_data["formulas"] = [self._formula_to_yaml_dict(f) for f in sensor.formulas]

        # Add optional fields
        self._add_optional_sensor_fields(sensor_data, sensor)

        return sensor_data

    def _add_optional_sensor_fields(self, sensor_data: dict[str, Any], sensor: SensorConfig) -> None:
        """Add optional sensor fields to the YAML dictionary.

        Args:
            sensor_data: Dictionary to add fields to
            sensor: Source sensor configuration
        """
        if sensor.entity_id:
            sensor_data["entity_id"] = sensor.entity_id
        if sensor.name:
            sensor_data["name"] = sensor.name
        if sensor.enabled is not None:
            sensor_data["enabled"] = sensor.enabled

    def _formula_to_yaml_dict(self, formula: FormulaConfig) -> dict[str, Any]:
        """Convert a FormulaConfig to a YAML dictionary.

        Args:
            formula: The FormulaConfig to convert

        Returns:
            Dictionary representation of the formula
        """
        formula_data: dict[str, Any] = {"formula": formula.formula}

        # Add optional fields
        self._add_optional_formula_fields(formula_data, formula)

        return formula_data

    def _add_optional_formula_fields(self, formula_data: dict[str, Any], formula: FormulaConfig) -> None:
        """Add optional formula fields to the YAML dictionary.

        Args:
            formula_data: Dictionary to add fields to
            formula: Source formula configuration
        """
        if formula.metadata:
            formula_data["metadata"] = dict(formula.metadata)
        if formula.attributes:
            # Attributes can be primitive values or nested formula structures
            formula_data["attributes"] = {}
            for name, attr_value in formula.attributes.items():
                if isinstance(attr_value, dict) and "formula" in attr_value:
                    # This is a nested formula structure, preserve it as-is
                    formula_data["attributes"][name] = attr_value
                else:
                    # This is a primitive value
                    formula_data["attributes"][name] = attr_value
