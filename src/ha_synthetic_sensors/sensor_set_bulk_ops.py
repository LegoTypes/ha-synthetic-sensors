"""Bulk operations and validation functionality for SensorSet."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .config_types import GlobalSettingsDict
from .exceptions import SyntheticSensorsError
from .sensor_set_entity_utils import apply_entity_id_changes_to_sensors_util, update_formula_variables_for_entity_changes

if TYPE_CHECKING:
    from .config_models import FormulaConfig, SensorConfig
    from .sensor_set import SensorSetModification
    from .storage_manager import StorageManager

_LOGGER = logging.getLogger(__name__)


class SensorSetBulkOps:
    """Handles bulk operations and validation for a sensor set."""

    def __init__(self, storage_manager: StorageManager, sensor_set_id: str) -> None:
        """Initialize bulk operations handler.

        Args:
            storage_manager: StorageManager instance
            sensor_set_id: Sensor set identifier
        """
        self.storage_manager = storage_manager
        self.sensor_set_id = sensor_set_id

    def validate_modification(self, modification: SensorSetModification, current_sensors: dict[str, SensorConfig]) -> None:
        """
        Validate a modification request before applying changes.

        Args:
            modification: Modification specification
            current_sensors: Current sensors in the set

        Raises:
            SyntheticSensorsError: If validation fails or conflicts occur
        """
        errors: list[str] = []

        # Validate individual operations
        self.validate_add_sensors(modification, current_sensors, errors)
        self.validate_remove_sensors(modification, current_sensors, errors)
        self.validate_update_sensors(modification, current_sensors, errors)

        # Validate for conflicts between operations
        self.validate_operation_conflicts(modification, errors)

        # Validate global settings changes
        self.validate_global_settings_changes(modification, current_sensors, errors)

        if errors:
            error_msg = "Modification validation failed:\n" + "\n".join(f"  - {error}" for error in errors)
            raise SyntheticSensorsError(error_msg)

    def validate_add_sensors(
        self, modification: SensorSetModification, current_sensors: dict[str, SensorConfig], errors: list[str]
    ) -> None:
        """Validate sensors to be added."""
        if not modification.add_sensors:
            return

        for sensor in modification.add_sensors:
            if sensor.unique_id in current_sensors:
                errors.append(f"Cannot add sensor '{sensor.unique_id}': already exists")

    def validate_remove_sensors(
        self, modification: SensorSetModification, current_sensors: dict[str, SensorConfig], errors: list[str]
    ) -> None:
        """Validate sensors to be removed."""
        if not modification.remove_sensors:
            return

        for unique_id in modification.remove_sensors:
            if unique_id not in current_sensors:
                errors.append(f"Cannot remove sensor '{unique_id}': does not exist")

    def validate_update_sensors(
        self, modification: SensorSetModification, current_sensors: dict[str, SensorConfig], errors: list[str]
    ) -> None:
        """Validate sensors to be updated."""
        if not modification.update_sensors:
            return

        for sensor in modification.update_sensors:
            if sensor.unique_id not in current_sensors:
                errors.append(f"Cannot update sensor '{sensor.unique_id}': does not exist")

    def validate_operation_conflicts(self, modification: SensorSetModification, errors: list[str]) -> None:
        """Validate that operations don't conflict with each other."""
        # Check for conflicts between add/remove/update operations
        add_ids = {s.unique_id for s in modification.add_sensors or []}
        remove_ids = set(modification.remove_sensors or [])
        update_ids = {s.unique_id for s in modification.update_sensors or []}

        # Check for overlaps
        add_remove_overlap = add_ids & remove_ids
        add_update_overlap = add_ids & update_ids
        remove_update_overlap = remove_ids & update_ids

        if add_remove_overlap:
            errors.append(f"Cannot both add and remove sensors: {add_remove_overlap}")
        if add_update_overlap:
            errors.append(f"Cannot both add and update sensors: {add_update_overlap}")
        if remove_update_overlap:
            errors.append(f"Cannot both remove and update sensors: {remove_update_overlap}")

    def validate_global_settings_changes(
        self, modification: SensorSetModification, current_sensors: dict[str, SensorConfig], errors: list[str]
    ) -> None:
        """Validate global settings changes."""
        if modification.global_settings is None:
            return

        # Validate that global settings don't conflict with final sensor state
        try:
            self.validate_global_settings_conflicts(modification, current_sensors)
        except SyntheticSensorsError as e:
            errors.append(f"Global settings conflict: {e}")

    def validate_global_settings_conflicts(
        self, modification: SensorSetModification, current_sensors: dict[str, SensorConfig]
    ) -> None:
        """
        Validate that global settings don't conflict with sensor variables.

        Args:
            modification: Modification specification
            current_sensors: Current sensors in the set

        Raises:
            SyntheticSensorsError: If conflicts are found
        """
        if modification.global_settings is None:
            return

        # Build final sensor list (after all modifications)
        final_sensors = self.build_final_sensor_list(modification, current_sensors)

        # Apply entity ID changes to final sensors
        if modification.entity_id_changes:
            final_sensors = self.apply_entity_id_changes_to_sensors(modification.entity_id_changes, final_sensors)

        # Build final global settings
        final_global_settings = modification.global_settings

        # Validate final state
        self.validate_final_state(final_global_settings, final_sensors)

    def build_final_sensor_list(
        self, modification: SensorSetModification, current_sensors: dict[str, SensorConfig]
    ) -> dict[str, SensorConfig]:
        """
        Build the final sensor list after applying all modifications.

        Args:
            modification: Modification specification
            current_sensors: Current sensors in the set

        Returns:
            Final sensor list after all modifications
        """
        final_sensors = current_sensors.copy()

        # Remove sensors
        if modification.remove_sensors:
            for unique_id in modification.remove_sensors:
                final_sensors.pop(unique_id, None)

        # Add new sensors
        if modification.add_sensors:
            for sensor in modification.add_sensors:
                final_sensors[sensor.unique_id] = sensor

        # Update existing sensors
        if modification.update_sensors:
            for sensor in modification.update_sensors:
                final_sensors[sensor.unique_id] = sensor

        return final_sensors

    def apply_entity_id_changes_to_sensors(
        self, entity_id_changes: dict[str, str], sensors: dict[str, SensorConfig]
    ) -> dict[str, SensorConfig]:
        """
        Apply entity ID changes to sensor configurations.

        Args:
            entity_id_changes: Mapping of old entity ID to new entity ID
            sensors: Sensor configurations to update

        Returns:
            Updated sensor configurations with entity ID changes applied
        """
        return apply_entity_id_changes_to_sensors_util(entity_id_changes, sensors)

    def update_formula_variables_for_entity_changes(self, formula: FormulaConfig, entity_id_changes: dict[str, str]) -> None:
        """Update formula variables to reflect entity ID changes."""
        update_formula_variables_for_entity_changes(formula, entity_id_changes)

    def validate_final_state(self, final_global_settings: dict[str, Any], final_sensors: dict[str, SensorConfig]) -> None:
        """
        Validate the final state after all modifications.

        Args:
            final_global_settings: Final global settings
            final_sensors: Final sensor configurations

        Raises:
            SyntheticSensorsError: If validation fails
        """
        # Use storage manager's validation
        if final_global_settings:
            # Cast to GlobalSettingsDict since it's compatible
            typed_global_settings: GlobalSettingsDict = final_global_settings  # type: ignore[assignment]
            self.storage_manager.validate_no_global_conflicts(list(final_sensors.values()), typed_global_settings)
