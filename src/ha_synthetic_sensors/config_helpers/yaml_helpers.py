"""YAML helper utilities extracted from ConfigManager to reduce module size."""

from __future__ import annotations

from typing import Any


def trim_yaml_keys(obj: Any) -> Any:
    """Recursively trim whitespace from dictionary keys in YAML data."""
    if isinstance(obj, dict):
        processed: dict[Any, Any] = {}
        for key, value in obj.items():
            new_key = key.strip() if isinstance(key, str) else key
            new_val = trim_yaml_keys(value)

            # Normalize formula fields parsed as non-strings
            if isinstance(new_key, str) and new_key == "formula" and new_val is not None and not isinstance(new_val, str):
                new_val = str(new_val)

            processed[new_key] = new_val
        return processed
    if isinstance(obj, list):
        return [trim_yaml_keys(item) for item in obj]
    return obj


def extract_sensor_keys_from_yaml(yaml_content: str) -> list[str]:
    """Extract top-level sensor keys from raw YAML string.

    This is a lightweight line-based parser used for Phase 0 duplicate key detection.
    """
    lines = yaml_content.split("\n")
    sensor_keys: list[str] = []
    in_sensors_section = False

    for line in lines:
        # Accept both 'sensors:' and 'sensors' to be tolerant of formatting
        if line.strip().startswith("sensors") and (line.strip() == "sensors" or line.strip().startswith("sensors:")):
            in_sensors_section = True
            continue
        if not in_sensors_section:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # End of sensors section detection: dedent to top-level
        if stripped and not line.startswith(" "):
            break
        # Sensor keys are at first indentation level (2 spaces)
        leading_spaces = len(line) - len(line.lstrip())
        if leading_spaces != 2:
            continue
        if ":" not in line:
            continue
        key = line.split(":")[0].strip()
        if key and key != "sensors":
            sensor_keys.append(key)

    return sensor_keys


def check_duplicate_sensor_keys(sensor_keys: list[str]) -> list[str]:
    """Return sorted list of duplicate sensor keys from the provided list."""
    seen = set()
    duplicates = set()
    for k in sensor_keys:
        if k in seen:
            duplicates.add(k)
        else:
            seen.add(k)
    return sorted(duplicates)
