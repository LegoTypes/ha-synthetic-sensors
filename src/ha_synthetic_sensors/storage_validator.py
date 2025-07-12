"""
Validation Handler for Storage Manager.

This module handles validation of sensor configurations, global settings,
and conflict detection between sensors and global variables.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .config_models import SensorConfig
from .config_types import GlobalSettingsDict
from .exceptions import SyntheticSensorsConfigError

if TYPE_CHECKING:
    from .storage_manager import StorageManager

__all__ = ["ValidationHandler"]

_LOGGER = logging.getLogger(__name__)


class ValidationHandler:
    """Handles validation operations for storage manager."""

    def __init__(self, storage_manager: StorageManager) -> None:
        """Initialize validation handler."""
        self.storage_manager = storage_manager

    def validate_no_global_conflicts(self, sensors: list[SensorConfig], global_settings: GlobalSettingsDict) -> None:
        """Validate that global variables don't conflict with sensor formulas.

        Args:
            sensors: List of sensor configurations to validate
            global_settings: Global settings containing variables

        Raises:
            SyntheticSensorsConfigError: If conflicts are found
        """
        global_variables = global_settings.get("variables", {})
        if not global_variables:
            return

        for sensor in sensors:
            self._check_formula_variable_conflicts(sensor, global_variables)

    def validate_no_attribute_variable_conflicts(self, sensors: list[SensorConfig]) -> None:
        """Validate that attribute formulas don't conflict with each other.

        Args:
            sensors: List of sensor configurations to validate

        Raises:
            SyntheticSensorsConfigError: If conflicts are found
        """
        for sensor in sensors:
            self._check_attribute_formula_conflicts(sensor)

    def validate_sensor_with_context(self, sensor_config: SensorConfig, sensor_set_id: str) -> list[str]:
        """Validate a sensor configuration within its sensor set context.

        Args:
            sensor_config: Sensor configuration to validate
            sensor_set_id: ID of the sensor set containing the sensor

        Returns:
            List of validation error messages
        """
        errors = []

        # Basic sensor validation
        sensor_errors = sensor_config.validate()
        errors.extend(sensor_errors)

        # Get global settings for context validation
        data = self.storage_manager.data
        if sensor_set_id in data["sensor_sets"]:
            global_settings = data["sensor_sets"][sensor_set_id].get("global_settings", {})

            # Validate against global settings
            global_errors = self._validate_against_global_settings(sensor_config, global_settings)
            errors.extend(global_errors)

        # Validate attribute variable conflicts within the sensor
        attribute_errors = self._validate_attribute_variable_conflicts(sensor_config)
        errors.extend(attribute_errors)

        return errors

    def _check_formula_variable_conflicts(self, sensor: SensorConfig, global_variables: dict[str, Any]) -> None:
        """Check for conflicts between formula variables and global variables."""
        for formula in sensor.formulas:
            if not formula.variables:
                continue

            for var_name in formula.variables:
                if var_name in global_variables:
                    # Determine formula type based on ID pattern
                    if formula.id == sensor.unique_id:
                        formula_desc = "main formula"
                    elif formula.id.startswith(f"{sensor.unique_id}_"):
                        attribute_name = formula.id[len(sensor.unique_id) + 1 :]
                        formula_desc = f"formula for attribute '{attribute_name}'"
                    else:
                        formula_desc = f"formula '{formula.id}'"

                    raise SyntheticSensorsConfigError(
                        f"Sensor '{sensor.unique_id}' {formula_desc} defines variable '{var_name}' "
                        f"which conflicts with global variable"
                    )

    def _check_attribute_formula_conflicts(self, sensor: SensorConfig) -> None:
        """Check for variable conflicts between attribute formulas within a sensor."""
        # Collect all variables from all formulas
        all_variables: dict[str, str] = {}  # var_name -> formula_description

        for formula in sensor.formulas:
            if not formula.variables:
                continue

            # Determine formula type based on ID pattern
            if formula.id == sensor.unique_id:
                formula_desc = "main formula"
            elif formula.id.startswith(f"{sensor.unique_id}_"):
                attribute_name = formula.id[len(sensor.unique_id) + 1 :]
                formula_desc = f"attribute '{attribute_name}'"
            else:
                formula_desc = f"formula '{formula.id}'"

            for var_name in formula.variables:
                if var_name in all_variables:
                    existing_formula_desc = all_variables[var_name]
                    raise SyntheticSensorsConfigError(
                        f"Sensor '{sensor.unique_id}' has variable '{var_name}' defined in both "
                        f"{existing_formula_desc} and {formula_desc}"
                    )
                all_variables[var_name] = formula_desc

    def _validate_against_global_settings(self, sensor: SensorConfig, global_settings: dict[str, Any]) -> list[str]:
        """Validate sensor configuration against global settings.

        Args:
            sensor: Sensor configuration to validate
            global_settings: Global settings to check against

        Returns:
            List of validation error messages
        """
        errors = []

        # Check device identifier conflicts (if global setting exists and sensor has different value)
        global_device = global_settings.get("device_identifier")
        if global_device and sensor.device_identifier and sensor.device_identifier != global_device:
            errors.append(
                f"Sensor '{sensor.unique_id}' device_identifier '{sensor.device_identifier}' "
                f"conflicts with global setting '{global_device}'"
            )

        # Check variable conflicts
        global_vars = global_settings.get("variables", {})
        if global_vars:
            for formula in sensor.formulas:
                if not formula.variables:
                    continue

                for var_name, var_value in formula.variables.items():
                    if var_name in global_vars and global_vars[var_name] != var_value:
                        # Determine formula type for error message
                        if formula.id == sensor.unique_id:
                            formula_desc = "main formula"
                        elif formula.id.startswith(f"{sensor.unique_id}_"):
                            attribute_name = formula.id[len(sensor.unique_id) + 1 :]
                            formula_desc = f"attribute '{attribute_name}'"
                        else:
                            formula_desc = f"formula '{formula.id}'"

                        errors.append(
                            f"Sensor '{sensor.unique_id}' {formula_desc} variable '{var_name}' "
                            f"value '{var_value}' conflicts with global setting '{global_vars[var_name]}'"
                        )

        return errors

    def _validate_attribute_variable_conflicts(self, sensor: SensorConfig) -> list[str]:
        """Validate that attribute variables don't conflict with sensor variables.

        Args:
            sensor: Sensor configuration to validate

        Returns:
            List of validation error messages
        """
        errors: list[str] = []

        # Find the main formula (sensor-level variables)
        main_formula = None
        attribute_formulas = []

        for formula in sensor.formulas:
            if formula.id == sensor.unique_id:
                main_formula = formula
            elif formula.id.startswith(f"{sensor.unique_id}_"):
                attribute_formulas.append(formula)

        # If no main formula or no attributes, no conflicts possible
        if not main_formula or not attribute_formulas:
            return errors

        # Get sensor-level variables
        sensor_variables = main_formula.variables or {}

        # Check each attribute formula for conflicts
        for attr_formula in attribute_formulas:
            if not attr_formula.variables:
                continue

            # Extract attribute name from formula ID
            attribute_name = attr_formula.id[len(sensor.unique_id) + 1 :]

            # Check for conflicting variables
            for var_name, var_value in attr_formula.variables.items():
                if var_name in sensor_variables and sensor_variables[var_name] != var_value:
                    errors.append(
                        f"Sensor '{sensor.unique_id}' attribute '{attribute_name}' has conflicting variable '{var_name}': "
                        f"'{var_value}' vs sensor variable '{sensor_variables[var_name]}'"
                    )

        return errors
