"""Factory functions for creating SensorSet instances.

This module provides factory functions to create SensorSet instances
without creating circular import dependencies between StorageManager and SensorSet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .sensor_set import SensorSet

if TYPE_CHECKING:
    from .storage_manager import StorageManager


def create_sensor_set(storage_manager: StorageManager, sensor_set_id: str) -> SensorSet:
    """
    Create a SensorSet instance.

    Args:
        storage_manager: StorageManager instance
        sensor_set_id: Sensor set identifier

    Returns:
        SensorSet instance
    """
    return SensorSet(storage_manager, sensor_set_id)
