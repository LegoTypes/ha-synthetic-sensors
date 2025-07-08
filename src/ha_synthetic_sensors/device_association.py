"""
Device Association - Device identification and association utilities for synthetic sensors.

This module provides utilities for associating synthetic sensors with Home Assistant
devices, including device identification helpers, association management, and
device-based sensor organization capabilities.

Phase 1 Implementation: Basic device association for fresh installations.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

_LOGGER = logging.getLogger(__name__)


class DeviceAssociationHelper:
    """
    Utility class for managing device associations with synthetic sensors.

    Provides methods to identify devices, validate device associations,
    and manage device-based sensor organization within Home Assistant.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """
        Initialize the DeviceAssociationHelper.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass

    def get_device_identifier_from_entity(self, entity_id: str) -> str | None:
        """
        Get device identifier from an entity ID.

        Args:
            entity_id: Entity ID to look up

        Returns:
            Device identifier string or None if not found
        """
        try:
            entity_registry = er.async_get(self.hass)
            device_registry = dr.async_get(self.hass)

            # Get entity entry
            entity_entry = entity_registry.async_get(entity_id)
            if not entity_entry or not entity_entry.device_id:
                return None

            # Get device entry
            device_entry = device_registry.async_get(entity_entry.device_id)
            if not device_entry:
                return None

            # Create device identifier from device identifiers
            # Use the first identifier as the primary identifier
            if device_entry.identifiers:
                identifier_tuple = next(iter(device_entry.identifiers))
                # Format as "domain:identifier"
                return f"{identifier_tuple[0]}:{identifier_tuple[1]}"

            # Fallback to device ID if no identifiers
            return device_entry.id

        except Exception as err:
            _LOGGER.warning("Failed to get device identifier for entity %s: %s", entity_id, err)
            return None

    def get_device_info_from_identifier(self, device_identifier: str) -> dict[str, Any] | None:
        """
        Get device information from device identifier.

        Args:
            device_identifier: Device identifier string

        Returns:
            Dictionary with device information or None if not found
        """
        try:
            device_registry = dr.async_get(self.hass)

            # Parse device identifier
            if ":" in device_identifier:
                domain, identifier = device_identifier.split(":", 1)
                # Look up by domain and identifier
                device_entry = device_registry.async_get_device({(domain, identifier)})
            else:
                # Treat as device ID
                device_entry = device_registry.async_get(device_identifier)

            if not device_entry:
                return None

            return {
                "device_id": device_entry.id,
                "name": device_entry.name_by_user or device_entry.name,
                "manufacturer": device_entry.manufacturer,
                "model": device_entry.model,
                "sw_version": device_entry.sw_version,
                "hw_version": device_entry.hw_version,
                "identifiers": list(device_entry.identifiers),
                "connections": list(device_entry.connections),
                "via_device_id": device_entry.via_device_id,
                "area_id": device_entry.area_id,
                "configuration_url": device_entry.configuration_url,
                "entry_type": device_entry.entry_type,
                "disabled_by": device_entry.disabled_by,
            }

        except Exception as err:
            _LOGGER.warning("Failed to get device info for identifier %s: %s", device_identifier, err)
            return None

    def get_entities_for_device(self, device_identifier: str) -> list[str]:
        """
        Get all entity IDs associated with a device.

        Args:
            device_identifier: Device identifier string

        Returns:
            List of entity IDs
        """
        try:
            entity_registry = er.async_get(self.hass)
            device_registry = dr.async_get(self.hass)

            # Get device entry
            device_entry = None
            if ":" in device_identifier:
                domain, identifier = device_identifier.split(":", 1)
                device_entry = device_registry.async_get_device({(domain, identifier)})
            else:
                device_entry = device_registry.async_get(device_identifier)

            if not device_entry:
                return []

            # Get entities for this device
            entities = er.async_entries_for_device(entity_registry, device_entry.id)
            return [entity.entity_id for entity in entities]

        except Exception as err:
            _LOGGER.warning("Failed to get entities for device %s: %s", device_identifier, err)
            return []

    def validate_device_exists(self, device_identifier: str) -> bool:
        """
        Validate that a device exists in Home Assistant.

        Args:
            device_identifier: Device identifier to validate

        Returns:
            True if device exists, False otherwise
        """
        device_info = self.get_device_info_from_identifier(device_identifier)
        return device_info is not None

    def suggest_device_identifier(self, entity_id: str) -> str | None:
        """
        Suggest a device identifier based on an entity ID.

        Args:
            entity_id: Entity ID to base suggestion on

        Returns:
            Suggested device identifier or None
        """
        return self.get_device_identifier_from_entity(entity_id)

    def get_device_friendly_name(self, device_identifier: str) -> str:
        """
        Get a friendly name for a device.

        Args:
            device_identifier: Device identifier

        Returns:
            Friendly name for the device
        """
        device_info = self.get_device_info_from_identifier(device_identifier)
        if device_info:
            name = device_info.get("name", device_identifier)
            return str(name) if name is not None else device_identifier
        return device_identifier

    def list_all_devices(self) -> list[dict[str, Any]]:
        """
        List all devices in Home Assistant.

        Returns:
            List of device information dictionaries
        """
        try:
            device_registry = dr.async_get(self.hass)
            devices = []

            for device_entry in device_registry.devices.values():
                # Create device identifier
                device_identifier = None
                if device_entry.identifiers:
                    identifier_tuple = next(iter(device_entry.identifiers))
                    device_identifier = f"{identifier_tuple[0]}:{identifier_tuple[1]}"
                else:
                    device_identifier = device_entry.id

                devices.append(
                    {
                        "device_identifier": device_identifier,
                        "device_id": device_entry.id,
                        "name": device_entry.name_by_user or device_entry.name,
                        "manufacturer": device_entry.manufacturer,
                        "model": device_entry.model,
                        "sw_version": device_entry.sw_version,
                        "hw_version": device_entry.hw_version,
                        "area_id": device_entry.area_id,
                        "disabled": device_entry.disabled_by is not None,
                    }
                )

            return devices

        except Exception as err:
            _LOGGER.error("Failed to list devices: %s", err)
            return []

    def find_devices_by_criteria(
        self,
        manufacturer: str | None = None,
        model: str | None = None,
        name_pattern: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find devices matching specific criteria.

        Args:
            manufacturer: Manufacturer name to match
            model: Model name to match
            name_pattern: Name pattern to match (case-insensitive)

        Returns:
            List of matching device information dictionaries
        """
        all_devices = self.list_all_devices()
        matching_devices = []

        for device in all_devices:
            # Check manufacturer
            if manufacturer and device.get("manufacturer", "").lower() != manufacturer.lower():
                continue

            # Check model
            if model and device.get("model", "").lower() != model.lower():
                continue

            # Check name pattern
            if name_pattern and name_pattern.lower() not in device.get("name", "").lower():
                continue

            matching_devices.append(device)

        return matching_devices

    def get_device_area(self, device_identifier: str) -> str | None:
        """
        Get the area name for a device.

        Args:
            device_identifier: Device identifier

        Returns:
            Area name or None if not assigned to an area
        """
        try:
            device_info = self.get_device_info_from_identifier(device_identifier)
            if not device_info or not device_info.get("area_id"):
                return None

            area_registry = ar.async_get(self.hass)
            area_entry = area_registry.async_get_area(device_info["area_id"])

            return area_entry.name if area_entry else None

        except Exception as err:
            _LOGGER.warning("Failed to get area for device %s: %s", device_identifier, err)
            return None

    def create_device_identifier_from_entity_pattern(self, entity_id: str) -> str:
        """
        Create a device identifier from entity ID pattern.

        For cases where entities don't have device associations but follow
        predictable naming patterns that can be used to group them.

        Args:
            entity_id: Entity ID to analyze

        Returns:
            Generated device identifier
        """
        # Extract domain and object_id
        try:
            _, object_id = entity_id.split(".", 1)

            # Common patterns for device grouping:
            # 1. Remove sensor type suffixes (e.g., "_power", "_energy")
            # 2. Extract base device name

            common_suffixes = [
                "_power",
                "_energy",
                "_current",
                "_voltage",
                "_temperature",
                "_humidity",
                "_pressure",
                "_battery",
                "_status",
                "_state",
                "_produced",
                "_consumed",
                "_imported",
                "_exported",
            ]

            base_name = object_id
            for suffix in common_suffixes:
                if base_name.endswith(suffix):
                    base_name = base_name[: -len(suffix)]
                    break

            # Create synthetic device identifier
            return f"synthetic:{base_name}"

        except ValueError:
            # Fallback for invalid entity IDs
            return f"synthetic:{entity_id.replace('.', '_')}"

    def group_entities_by_device_pattern(self, entity_ids: list[str]) -> dict[str, list[str]]:
        """
        Group entity IDs by inferred device patterns.

        Args:
            entity_ids: List of entity IDs to group

        Returns:
            Dictionary mapping device identifiers to entity ID lists
        """
        device_groups: dict[str, list[str]] = {}

        for entity_id in entity_ids:
            # Try to get actual device identifier first
            device_identifier = self.get_device_identifier_from_entity(entity_id)

            # If no device association, create one from pattern
            if not device_identifier:
                device_identifier = self.create_device_identifier_from_entity_pattern(entity_id)

            if device_identifier not in device_groups:
                device_groups[device_identifier] = []
            device_groups[device_identifier].append(entity_id)

        return device_groups

    def validate_device_association_config(self, config: dict[str, Any]) -> list[str]:
        """
        Validate device association configuration.

        Args:
            config: Configuration dictionary with device associations

        Returns:
            List of validation errors
        """
        errors = []

        device_identifier = config.get("device_identifier")
        if device_identifier and not self.validate_device_exists(device_identifier):
            errors.append(f"Device '{device_identifier}' does not exist in Home Assistant")

        # Validate device-specific fields
        device_name = config.get("device_name")
        if device_name and not isinstance(device_name, str):
            errors.append("device_name must be a string")

        suggested_area = config.get("suggested_area")
        if suggested_area and not isinstance(suggested_area, str):
            errors.append("suggested_area must be a string")

        return errors
