"""Utility functions shared across the synthetic sensors package."""


def denormalize_entity_id(normalized_id: str) -> str | None:
    """
    Convert a normalized entity ID back to its original form.

    This is a simple reverse of the normalization process.
    In practice, we'd need to know the original entity ID.
    For now, we'll try common patterns.

    Args:
        normalized_id: Normalized entity ID (e.g., "sensor_power_meter")

    Returns:
        Original entity ID (e.g., "sensor.power_meter") or None if conversion fails
    """
    if normalized_id.startswith("sensor_"):
        return normalized_id.replace("_", ".", 1)  # Replace first underscore with dot

    if (
        normalized_id.startswith("binary_sensor_")
        or normalized_id.startswith("input_")
        or normalized_id.startswith("switch_")
        or normalized_id.startswith("light_")
        or normalized_id.startswith("climate_")
    ):
        return normalized_id.replace("_", ".", 1)
    # Add more patterns as needed
    return None
