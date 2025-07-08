"""Device class constants for Home Assistant entity classification.

This module centralizes device class definitions from Home Assistant's official
device class enums, making them easier to maintain and update when HA adds new
device classes.
"""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass

# Non-numeric sensor device classes
# These sensor device classes represent non-numeric data
NON_NUMERIC_SENSOR_DEVICE_CLASSES = frozenset(
    {
        SensorDeviceClass.DATE,  # Date values (datetime.date objects)
        SensorDeviceClass.ENUM,  # Enumerated text values with limited options
        SensorDeviceClass.TIMESTAMP,  # Timestamp values (datetime.datetime objects)
    }
)

# All binary sensor device classes are non-numeric by definition
# Binary sensors can only have on/off states, never numeric values
NON_NUMERIC_BINARY_SENSOR_DEVICE_CLASSES = frozenset(
    {
        BinarySensorDeviceClass.BATTERY,
        BinarySensorDeviceClass.BATTERY_CHARGING,
        BinarySensorDeviceClass.CO,
        BinarySensorDeviceClass.COLD,
        BinarySensorDeviceClass.CONNECTIVITY,
        BinarySensorDeviceClass.DOOR,
        BinarySensorDeviceClass.GARAGE_DOOR,
        BinarySensorDeviceClass.GAS,
        BinarySensorDeviceClass.HEAT,
        BinarySensorDeviceClass.LIGHT,
        BinarySensorDeviceClass.LOCK,
        BinarySensorDeviceClass.MOISTURE,
        BinarySensorDeviceClass.MOTION,
        BinarySensorDeviceClass.MOVING,
        BinarySensorDeviceClass.OCCUPANCY,
        BinarySensorDeviceClass.OPENING,
        BinarySensorDeviceClass.PLUG,
        BinarySensorDeviceClass.POWER,
        BinarySensorDeviceClass.PRESENCE,
        BinarySensorDeviceClass.PROBLEM,
        BinarySensorDeviceClass.RUNNING,
        BinarySensorDeviceClass.SAFETY,
        BinarySensorDeviceClass.SMOKE,
        BinarySensorDeviceClass.SOUND,
        BinarySensorDeviceClass.TAMPER,
        BinarySensorDeviceClass.UPDATE,
        BinarySensorDeviceClass.VIBRATION,
        BinarySensorDeviceClass.WINDOW,
    }
)

# Combined set of all non-numeric device classes
ALL_NON_NUMERIC_DEVICE_CLASSES = NON_NUMERIC_SENSOR_DEVICE_CLASSES | NON_NUMERIC_BINARY_SENSOR_DEVICE_CLASSES


def is_device_class_numeric(device_class: str) -> bool:
    """Check if a device class indicates numeric sensor data.

    Args:
        device_class: The device class string to check

    Returns:
        True if the device class typically contains numeric data, False otherwise

    Note:
        This function uses Home Assistant's official device class definitions
        to determine if a device class is expected to contain numeric data.
        Binary sensors are always considered non-numeric since they can only
        have on/off states.
    """
    return device_class not in ALL_NON_NUMERIC_DEVICE_CLASSES


# Numeric sensor device classes for reference
# These are the most common device classes that contain numeric data
def _build_numeric_sensor_device_classes() -> frozenset[SensorDeviceClass]:
    """Build the set of numeric sensor device classes, handling version differences."""
    classes = {
        SensorDeviceClass.APPARENT_POWER,
        SensorDeviceClass.AQI,
        SensorDeviceClass.AREA,
        SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        SensorDeviceClass.BATTERY,
        SensorDeviceClass.BLOOD_GLUCOSE_CONCENTRATION,
        SensorDeviceClass.CO2,
        SensorDeviceClass.CO,
        SensorDeviceClass.CONDUCTIVITY,
        SensorDeviceClass.CURRENT,
        SensorDeviceClass.DATA_RATE,
        SensorDeviceClass.DATA_SIZE,
        SensorDeviceClass.DISTANCE,
        SensorDeviceClass.DURATION,
        SensorDeviceClass.ENERGY,
        SensorDeviceClass.ENERGY_DISTANCE,
        SensorDeviceClass.ENERGY_STORAGE,
        SensorDeviceClass.FREQUENCY,
        SensorDeviceClass.GAS,
        SensorDeviceClass.HUMIDITY,
        SensorDeviceClass.ILLUMINANCE,
        SensorDeviceClass.IRRADIANCE,
        SensorDeviceClass.MOISTURE,
        SensorDeviceClass.MONETARY,
        SensorDeviceClass.NITROGEN_DIOXIDE,
        SensorDeviceClass.NITROGEN_MONOXIDE,
        SensorDeviceClass.NITROUS_OXIDE,
        SensorDeviceClass.OZONE,
        SensorDeviceClass.PH,
        SensorDeviceClass.PM1,
        SensorDeviceClass.PM25,
        SensorDeviceClass.PM10,
        SensorDeviceClass.POWER,
        SensorDeviceClass.POWER_FACTOR,
        SensorDeviceClass.PRECIPITATION,
        SensorDeviceClass.PRECIPITATION_INTENSITY,
        SensorDeviceClass.PRESSURE,
        SensorDeviceClass.REACTIVE_POWER,
        SensorDeviceClass.SIGNAL_STRENGTH,
        SensorDeviceClass.SOUND_PRESSURE,
        SensorDeviceClass.SPEED,
        SensorDeviceClass.SULPHUR_DIOXIDE,
        SensorDeviceClass.TEMPERATURE,
        SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
        SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS,
        SensorDeviceClass.VOLTAGE,
        SensorDeviceClass.VOLUME,
        SensorDeviceClass.VOLUME_FLOW_RATE,
        SensorDeviceClass.VOLUME_STORAGE,
        SensorDeviceClass.WATER,
        SensorDeviceClass.WEIGHT,
        SensorDeviceClass.WIND_DIRECTION,
        SensorDeviceClass.WIND_SPEED,
    }

    # Add REACTIVE_ENERGY if it exists (newer HA versions)
    if hasattr(SensorDeviceClass, "REACTIVE_ENERGY"):
        classes.add(SensorDeviceClass.REACTIVE_ENERGY)

    return frozenset(classes)


COMMON_NUMERIC_SENSOR_DEVICE_CLASSES = _build_numeric_sensor_device_classes()


# Home Assistant Domain Classifications
# These classifications help determine if entities from specific domains
# are expected to contain numeric or non-numeric data

# Domains that always contain numeric data
ALWAYS_NUMERIC_DOMAINS = frozenset(
    {
        "input_number",  # Number input helpers
        "counter",  # Counter helpers
        "number",  # Number entities
    }
)

# Domains that never contain numeric data
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

# All valid Home Assistant domains
# This is used for entity ID validation
VALID_HA_DOMAINS = frozenset(
    {
        # Core entity platforms
        "sensor",
        "binary_sensor",
        "switch",
        "light",
        "fan",
        "cover",
        "climate",
        "lock",
        "vacuum",
        "media_player",
        "device_tracker",
        "weather",
        "camera",
        "alarm_control_panel",
        "button",
        "number",
        "select",
        "text",
        # Input helpers
        "input_number",
        "input_boolean",
        "input_select",
        "input_text",
        "input_datetime",
        # Other built-in domains
        "counter",
        "timer",
        "automation",
        "script",
        "scene",
        "group",
        "zone",
        "person",
        "sun",
        # Additional entity platforms
        "air_quality",
        "assist_satellite",
        "calendar",
        "conversation",
        "date",
        "datetime",
        "event",
        "humidifier",
        "image",
        "lawn_mower",
        "notify",
        "remote",
        "siren",
        "speech_to_text",
        "time",
        "todo",
        "text_to_speech",
        "update",
        "valve",
        "wake_word_detection",
        "water_heater",
    }
)


def classify_domain_numeric_expectation(domain: str) -> bool | None:
    """Classify domain's numeric expectation using centralized definitions.

    Args:
        domain: The Home Assistant domain to classify

    Returns:
        True: Domain always contains numeric data
        False: Domain never contains numeric data
        None: Domain requires further analysis (e.g., sensor domain)

    Note:
        This function centralizes domain classification logic that was
        previously scattered throughout the codebase.
    """
    if domain in ALWAYS_NUMERIC_DOMAINS:
        return True
    if domain in NEVER_NUMERIC_DOMAINS:
        return False
    # Domain requires further analysis (e.g., sensor domain with device_class)
    return None


def is_valid_ha_domain(domain: str) -> bool:
    """Check if a domain is a valid Home Assistant domain.

    Args:
        domain: The domain string to validate

    Returns:
        True if the domain is a valid Home Assistant domain, False otherwise
    """
    return domain in VALID_HA_DOMAINS
