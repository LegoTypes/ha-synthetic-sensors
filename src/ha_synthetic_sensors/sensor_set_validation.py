"""
Validation operations for sensor sets.

This module provides methods for validating sensor configurations
and YAML content for sensor sets.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import yaml as yaml_lib

from .config_manager import ConfigManager
from .config_models import SensorConfig

if TYPE_CHECKING:
    from .sensor_set import SensorSet

_LOGGER = logging.getLogger(__name__)


class SensorSetValidation:
    """Handles validation operations for sensor sets."""

    def __init__(self, sensor_set: SensorSet) -> None:
        """Initialize validation handler.

        Args:
            sensor_set: SensorSet instance to operate on
        """
        self.sensor_set = sensor_set

    def validate_sensor_config(self, sensor_config: SensorConfig) -> list[str]:
        """
        Validate a sensor configuration.

        Args:
            sensor_config: Sensor configuration to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Basic sensor validation
        if not sensor_config.unique_id:
            errors.append("Sensor unique_id is required")

        if not sensor_config.formulas:
            errors.append("Sensor must have at least one formula")

        # Check for duplicate formula IDs
        formula_ids = [f.id for f in sensor_config.formulas]
        if len(formula_ids) != len(set(formula_ids)):
            errors.append("Sensor has duplicate formula IDs")

        # Validate each formula has required fields
        for formula in sensor_config.formulas:
            if not formula.formula:
                errors.append(f"Formula '{formula.id}' missing formula expression")

        return errors

    def get_sensor_errors(self) -> dict[str, list[str]]:
        """
        Get validation errors for all sensors in this sensor set.

        Returns:
            Dictionary mapping sensor unique_id to list of errors
        """
        self.sensor_set.ensure_exists()

        errors = {}
        sensors = self.sensor_set.list_sensors()

        for sensor in sensors:
            sensor_errors = self.validate_sensor_config(sensor)
            if sensor_errors:
                errors[sensor.unique_id] = sensor_errors

        return errors

    async def async_validate_import(self, yaml_content: str) -> dict[str, Any]:
        """
        Validate YAML content before importing without actually importing.

        Args:
            yaml_content: YAML content to validate

        Returns:
            Dictionary with validation results:
            - "yaml_errors": YAML parsing errors
            - "config_errors": Configuration validation errors
            - "sensor_errors": Per-sensor validation errors
        """
        validation_results: dict[str, Any] = {
            "yaml_errors": [],
            "config_errors": [],
            "sensor_errors": {},
        }

        try:
            # Parse YAML
            yaml_data = yaml_lib.safe_load(yaml_content)
            if not yaml_data:
                validation_results["yaml_errors"].append("Empty YAML content")
                return validation_results

        except yaml_lib.YAMLError as e:
            validation_results["yaml_errors"].append(f"YAML parsing error: {e}")
            return validation_results

        try:
            # Validate configuration structure
            config_manager = ConfigManager(self.sensor_set.storage_manager.hass)
            config = config_manager.load_from_dict(yaml_data)

            # Validate overall config
            config_errors = config.validate()
            validation_results["config_errors"] = config_errors

            # Validate individual sensors
            for sensor in config.sensors:
                sensor_errors = self.validate_sensor_config(sensor)
                if sensor_errors:
                    validation_results["sensor_errors"][sensor.unique_id] = sensor_errors

        except Exception as e:
            validation_results["config_errors"].append(f"Configuration validation error: {e}")

        return validation_results

    def is_valid(self) -> bool:
        """
        Check if this sensor set and all its sensors are valid.

        Returns:
            True if all sensors are valid, False otherwise
        """
        if not self.sensor_set.exists:
            return False

        errors = self.get_sensor_errors()
        return len(errors) == 0
