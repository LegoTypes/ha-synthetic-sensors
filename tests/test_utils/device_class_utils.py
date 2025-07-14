"""Test utilities for device class testing."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass

from ha_synthetic_sensors.device_classes import NON_NUMERIC_SENSOR_DEVICE_CLASSES


def is_device_class_numeric(device_class: str | SensorDeviceClass | BinarySensorDeviceClass | None) -> bool:
    """Check if a device class indicates numeric sensor data.

    This is a test utility function that can distinguish between sensor and binary_sensor
    device classes when enum types are provided.

    Args:
        device_class: The device class string or enum to check

    Returns:
        True if the device class typically contains numeric data, False otherwise

    Note:
        This function can distinguish between sensor and binary_sensor device classes
        when enum types are provided. Binary sensor device classes are always non-numeric
        since they only have on/off states. When string values are provided, the function
        assumes sensor domain context for ambiguous cases (like "battery", "power").
    """
    # Handle None case - no device class specified defaults to numeric
    if device_class is None:
        return True

    # Handle enum types directly for precise classification
    # Use try/except to handle both real and mocked types
    try:
        if isinstance(device_class, BinarySensorDeviceClass):
            return False  # Binary sensors are always non-numeric
    except TypeError:
        pass  # Fall through to mock detection

    # Check for mocked BinarySensorDeviceClass - check type name and mock name
    device_class_str = str(device_class)
    type_str = str(type(device_class))

    # Check if this is a mocked BinarySensorDeviceClass
    mock_name_check = hasattr(device_class, "_mock_name") and "BinarySensorDeviceClass" in str(
        getattr(device_class, "_mock_name", "")
    )
    if "BinarySensorDeviceClass" in type_str or "BinarySensorDeviceClass" in device_class_str or mock_name_check:
        return False  # Binary sensors are always non-numeric

    try:
        if isinstance(device_class, SensorDeviceClass):
            return device_class not in NON_NUMERIC_SENSOR_DEVICE_CLASSES
    except TypeError:
        pass  # Fall through to mock detection

    # Check for mocked SensorDeviceClass or handle as string
    sensor_mock_name_check = hasattr(device_class, "_mock_name") and "SensorDeviceClass" in str(
        getattr(device_class, "_mock_name", "")
    )
    if "SensorDeviceClass" in type_str or "SensorDeviceClass" in device_class_str or sensor_mock_name_check:
        # Try to get the value from the mocked enum
        if hasattr(device_class, "value"):
            device_class_str = str(getattr(device_class, "value", device_class))
        else:
            device_class_str = str(device_class)
        sensor_non_numeric_values = {dc.value for dc in NON_NUMERIC_SENSOR_DEVICE_CLASSES}
        return device_class_str not in sensor_non_numeric_values

    # Handle string input - assume sensor domain context
    device_class_str = str(device_class)
    sensor_non_numeric_values = {dc.value for dc in NON_NUMERIC_SENSOR_DEVICE_CLASSES}
    return device_class_str not in sensor_non_numeric_values


# Domain constants for testing
ALWAYS_NUMERIC_DOMAINS = frozenset(
    {
        "input_number",  # Number input helpers
        "counter",  # Counter helpers
        "number",  # Number entities
    }
)

NEVER_NUMERIC_DOMAINS = frozenset(
    {
        "binary_sensor",  # Binary sensors (on/off, true/false)
        "switch",  # Switches (on/off)
        "input_boolean",  # Boolean input helpers
        "device_tracker",  # Device tracking (home/away/zones)
        "weather",  # Weather entities (conditions like sunny/cloudy)
        "climate",  # Climate entities (heat/cool/auto modes)
        "media_player",  # Media players (playing/paused/idle)
        "light",  # Lights (on/off, though attributes may be numeric)
        "fan",  # Fans (on/off, though attributes may be numeric)
        "cover",  # Covers (open/closed/opening/closing)
        "alarm_control_panel",  # Alarm panels (armed/disarmed/pending)
        "lock",  # Locks (locked/unlocked)
        "vacuum",  # Vacuums (cleaning/docked/returning)
    }
)


def classify_domain_numeric_expectation(domain: str) -> bool | None:
    """Classify domain's numeric expectation using centralized definitions.

    This is a test utility function.

    Args:
        domain: The Home Assistant domain to classify

    Returns:
        True: Domain always contains numeric data
        False: Domain never contains numeric data
        None: Domain requires further analysis (e.g., sensor domain)
    """
    if domain in ALWAYS_NUMERIC_DOMAINS:
        return True
    if domain in NEVER_NUMERIC_DOMAINS:
        return False
    # Domain requires further analysis (e.g., sensor domain with device_class)
    return None
