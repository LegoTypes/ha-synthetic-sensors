"""
YAML Import/Export Handler for Storage Manager.

This module handles the conversion between internal sensor configurations
and YAML format for import/export operations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import entity_registry as er
import yaml as yaml_lib

from .config_models import FormulaConfig, SensorConfig
from .constants_alternate import FALLBACK_KEY, NONE_KEY, STATE_NONE_YAML, UNAVAILABLE_KEY, UNKNOWN_KEY
from .constants_metadata import (
    METADATA_PROPERTY_DEVICE_CLASS,
    METADATA_PROPERTY_ICON,
    METADATA_PROPERTY_STATE_CLASS,
    METADATA_PROPERTY_UNIT_OF_MEASUREMENT,
)

if TYPE_CHECKING:
    from .storage_manager import StorageManager

__all__ = ["YamlHandler"]

_LOGGER = logging.getLogger(__name__)


class YamlHandler:
    """Handles YAML import/export operations for storage manager."""

    def __init__(self, storage_manager: StorageManager) -> None:
        """Initialize YAML handler."""
        self.storage_manager = storage_manager

    def export_yaml(self, sensor_set_id: str) -> str:
        """Export sensor set to YAML format."""
        data = self.storage_manager.data

        if sensor_set_id not in data["sensor_sets"]:
            raise ValueError(f"Sensor set not found: {sensor_set_id}")

        sensor_set_data = data["sensor_sets"][sensor_set_id]
        global_settings = sensor_set_data.get("global_settings", {})

        # Get sensors for this sensor set
        sensors = [
            self.storage_manager.deserialize_sensor_config(stored_sensor["config_data"])
            for stored_sensor in data["sensors"].values()
            if stored_sensor.get("sensor_set_id") == sensor_set_id
        ]

        yaml_structure = self._build_yaml_structure(sensors, global_settings)
        # Clean up any sentinel objects before serialization
        cleaned_structure = self._clean_for_yaml_serialization(yaml_structure)

        try:
            return yaml_lib.dump(cleaned_structure, default_flow_style=False, sort_keys=False)
        except Exception as e:
            # Debug: Find the problematic object
            _LOGGER.error("YAML serialization failed: %s", e)
            # Try to convert everything to basic Python types as a fallback
            basic_structure = self._convert_to_basic_types(cleaned_structure)
            return yaml_lib.dump(basic_structure, default_flow_style=False, sort_keys=False)

    def _build_yaml_structure(self, sensors: list[SensorConfig], global_settings: dict[str, Any]) -> dict[str, Any]:
        """Build the YAML structure from sensors and global settings."""
        yaml_data: dict[str, Any] = {"version": "1.0"}

        # Add global settings if present
        if global_settings:
            yaml_data["global_settings"] = global_settings

        # Add sensors
        sensors_dict = {}
        for sensor in sensors:
            sensor_dict = self._build_sensor_dict(sensor, global_settings)
            sensors_dict[sensor.unique_id] = sensor_dict

        if sensors_dict:
            yaml_data["sensors"] = sensors_dict

        return yaml_data

    def _clean_for_yaml_serialization(self, obj: Any) -> Any:
        """Recursively clean an object for YAML serialization, removing sentinel objects."""
        # Check for sentinel objects first
        if self._is_sentinel_object(obj):
            return None

        # Additional sentinel checks for objects that might slip through
        if hasattr(obj, "__class__") and "sentinel" in str(obj.__class__).lower():
            return None

        if str(obj) == "sentinel.DEFAULT" or "sentinel" in str(type(obj)):
            return None

        # Handle different object types
        result = obj
        if self._is_dict_view_object(obj):
            result = [self._clean_for_yaml_serialization(item) for item in obj]
        if hasattr(obj, "__dataclass_fields__"):
            result = self._clean_dataclass_object(obj)
        if isinstance(obj, dict):
            result = self._clean_dict_object(obj)
        if isinstance(obj, list | tuple):
            result = self._clean_list_object(obj)
        return result

    def _is_sentinel_object(self, obj: Any) -> bool:
        """Check if object is a sentinel object that should be removed."""
        if hasattr(obj, "__class__"):
            class_name = obj.__class__.__name__
            if class_name in ("_MISSING_TYPE", "sentinel"):
                return True
            if hasattr(obj, "__module__") and "sentinel" in str(obj.__module__):
                return True

        return str(obj) == "sentinel.DEFAULT"

    def _is_dict_view_object(self, obj: Any) -> bool:
        """Check if object is a dict view object."""
        return hasattr(obj, "__class__") and obj.__class__.__name__ in ("dict_values", "dict_keys", "dict_items")

    def _clean_dataclass_object(self, obj: Any) -> dict[str, Any]:
        """Clean a dataclass object."""
        obj_dict = {}
        for field_name in obj.__dataclass_fields__:
            field_value = getattr(obj, field_name)
            cleaned_value = self._clean_for_yaml_serialization(field_value)
            if not self._is_sentinel_value(cleaned_value):
                obj_dict[field_name] = cleaned_value
        return obj_dict

    def _clean_dict_object(self, obj: dict[str, Any]) -> dict[str, Any]:
        """Clean a dictionary object."""
        cleaned_dict = {}
        for k, v in obj.items():
            cleaned_k = self._clean_for_yaml_serialization(k)
            cleaned_v = self._clean_for_yaml_serialization(v)
            if not self._is_sentinel_value(cleaned_k) and not self._is_sentinel_value(cleaned_v):
                cleaned_dict[cleaned_k] = cleaned_v
        return cleaned_dict

    def _clean_list_object(self, obj: list[Any] | tuple[Any, ...]) -> list[Any]:
        """Clean a list or tuple object."""
        cleaned_list = []
        for item in obj:
            cleaned_item = self._clean_for_yaml_serialization(item)
            if not self._is_sentinel_value(cleaned_item):
                cleaned_list.append(cleaned_item)
        return cleaned_list

    def _is_sentinel_value(self, obj: Any) -> bool:
        """Check if an object is a sentinel value that should be excluded from YAML."""
        if obj is None:
            return False  # None is a valid YAML value

        # Check string representation first (most reliable)
        if self._is_sentinel_string(obj):
            return True

        # Check class-based sentinel objects
        if self._is_sentinel_class(obj):
            return True

        # Check dataclass field defaults
        return bool(self._is_sentinel_dataclass_field(obj))

    def _is_sentinel_string(self, obj: Any) -> bool:
        """Check if object string representation indicates sentinel."""
        obj_str = str(obj)
        return obj_str == "sentinel.DEFAULT" or "sentinel.DEFAULT" in obj_str

    def _is_sentinel_class(self, obj: Any) -> bool:
        """Check if object class indicates sentinel."""
        if not hasattr(obj, "__class__"):
            return False

        class_name = obj.__class__.__name__
        if class_name in ("_MISSING_TYPE", "sentinel"):
            return True

        if "sentinel" in class_name.lower():
            return True

        return bool(hasattr(obj, "__module__") and obj.__module__ and "sentinel" in str(obj.__module__))

    def _is_sentinel_dataclass_field(self, obj: Any) -> bool:
        """Check if object is a sentinel dataclass field default."""
        if not hasattr(obj, "__reduce__"):
            return False

        if hasattr(obj, "__reduce__"):
            try:
                reduce_result = obj.__reduce__()
                if reduce_result and len(reduce_result) > 0:
                    func = reduce_result[0]
                    if hasattr(func, "__name__") and "sentinel" in func.__name__.lower():
                        return True
            except (TypeError, RuntimeError):
                # Some objects have __reduce__ but it fails when called
                pass

        return False

    def _convert_to_basic_types(self, obj: Any) -> Any:
        """Convert complex objects to basic Python types for YAML serialization."""
        # Check for basic types and sentinel values first
        if obj is None or isinstance(obj, str | int | float | bool):
            return obj

        if self._is_sentinel_value(obj):
            return None

        # Handle sentinel objects that might have slipped through
        if hasattr(obj, "__class__") and "sentinel" in str(obj.__class__).lower():
            return None

        # Handle any object that looks like a sentinel
        if str(obj) == "sentinel.DEFAULT" or "sentinel" in str(type(obj)):
            return None

        # Handle different object types
        result: Any = self._convert_other_to_basic_types(obj)
        if isinstance(obj, dict):
            result = self._convert_dict_to_basic_types(obj)
        if isinstance(obj, list | tuple):
            result = self._convert_list_to_basic_types(obj)
        if hasattr(obj, "__dataclass_fields__"):
            result = self._convert_dataclass_to_basic_types(obj)
        return result

    def _convert_dict_to_basic_types(self, obj: dict[str, Any]) -> dict[str, Any]:
        """Convert dictionary to basic types."""
        dict_result = {}
        for k, v in obj.items():
            converted_k = self._convert_to_basic_types(k)
            converted_v = self._convert_to_basic_types(v)
            if not self._is_sentinel_value(converted_k) and not self._is_sentinel_value(converted_v):
                dict_result[str(converted_k)] = converted_v
        return dict_result

    def _convert_list_to_basic_types(self, obj: list[Any] | tuple[Any, ...]) -> list[Any]:
        """Convert list or tuple to basic types."""
        list_result: list[Any] = []
        for item in obj:
            converted_item = self._convert_to_basic_types(item)
            if not self._is_sentinel_value(converted_item):
                list_result.append(converted_item)
        return list_result

    def _convert_dataclass_to_basic_types(self, obj: Any) -> dict[str, Any]:
        """Convert dataclass object to basic types."""
        dataclass_result = {}
        for field_name in obj.__dataclass_fields__:
            if hasattr(obj, field_name):
                field_value = getattr(obj, field_name)
                converted_value = self._convert_to_basic_types(field_value)
                if not self._is_sentinel_value(converted_value):
                    dataclass_result[field_name] = converted_value
        return dataclass_result

    def _convert_other_to_basic_types(self, obj: Any) -> str | None:
        """Convert other objects to basic types."""
        try:
            return str(obj)
        except Exception:
            return None

    def _build_sensor_dict(self, sensor_config: SensorConfig, global_settings: dict[str, Any]) -> dict[str, Any]:
        """Build sensor dictionary for YAML export."""
        sensor_dict: dict[str, Any] = {}

        # Add device identifier if needed
        self._add_device_identifier_if_needed(sensor_dict, sensor_config, global_settings)

        # Add optional sensor fields
        self._add_optional_sensor_fields(sensor_dict, sensor_config)

        # Process formulas
        main_formula, attributes_dict = self._process_formulas(sensor_config)

        # Add main formula details
        if main_formula:
            self._add_main_formula_details(sensor_dict, main_formula)

        # Add attributes if present
        if attributes_dict:
            sensor_dict["attributes"] = attributes_dict

        return sensor_dict

    def _add_device_identifier_if_needed(
        self, sensor_dict: dict[str, Any], sensor_config: SensorConfig, global_settings: dict[str, Any]
    ) -> None:
        """Add device identifier to sensor dict if it differs from global setting."""
        global_device_identifier = global_settings.get("device_identifier")
        if sensor_config.device_identifier != global_device_identifier:
            sensor_dict["device_identifier"] = sensor_config.device_identifier

    def _add_optional_sensor_fields(self, sensor_dict: dict[str, Any], sensor_config: SensorConfig) -> None:
        """Add optional sensor fields to the sensor dictionary."""
        if sensor_config.entity_id:
            sensor_dict["entity_id"] = sensor_config.entity_id
        if sensor_config.name:
            sensor_dict["name"] = sensor_config.name

        # Add sensor-level metadata if present
        if hasattr(sensor_config, "metadata") and sensor_config.metadata:
            # Create a copy of metadata to avoid modifying the original
            metadata = sensor_config.metadata.copy()

            # If the sensor has been created in HA, look up its current friendly name
            # from the entity registry instead of using the stored value
            if sensor_config.unique_id and self.storage_manager.integration_domain:
                # Try to get the entity ID for this sensor
                entity_id = self._get_entity_id_for_sensor(sensor_config.unique_id)
                if entity_id:
                    # Get the current friendly name from HA
                    current_friendly_name = self._get_friendly_name_from_registry(entity_id)
                    if current_friendly_name:
                        metadata["friendly_name"] = current_friendly_name

            sensor_dict["metadata"] = metadata
        # Note: Formula-level metadata is handled in _add_main_formula_details

    def _process_formulas(
        self, sensor_config: SensorConfig
    ) -> tuple[FormulaConfig | None, dict[str, Any | int | float | str | bool]]:
        """Process formulas and separate main formula from attributes."""
        main_formula = None
        attributes_dict: dict[str, Any | int | float | str | bool] = {}

        for formula in sensor_config.formulas:
            # Main formula has id matching the sensor's unique_id
            # Attribute formulas have id format: {sensor_unique_id}_{attribute_name}
            if formula.id == sensor_config.unique_id:
                main_formula = formula
                # Also extract literal attributes from main formula's attributes dictionary
                if hasattr(formula, "attributes") and formula.attributes:
                    for attr_name, attr_value in formula.attributes.items():
                        attributes_dict[attr_name] = attr_value
            elif formula.id.startswith(f"{sensor_config.unique_id}_"):
                # Extract attribute name from formula id
                attribute_name = formula.id[len(sensor_config.unique_id) + 1 :]
                attributes_dict[attribute_name] = self._build_attribute_dict(formula)

        return main_formula, attributes_dict

    def _build_attribute_dict(self, formula: FormulaConfig) -> dict[str, Any]:
        """Build attribute dictionary from formula configuration."""
        # Always preserve formula structure - never flatten to literals
        # If something was parsed as a FormulaConfig, it should be exported as a formula
        attr_dict: dict[str, Any] = {"formula": formula.formula}

        if formula.variables:
            # Filter out ComputedVariable instances for YAML serialization
            variables_dict: dict[str, str | int | float] = {
                k: v
                for k, v in formula.variables.items()
                if not hasattr(v, "formula")  # Skip ComputedVariable instances
            }
            if variables_dict:  # Only add if there are simple variables
                attr_dict["variables"] = variables_dict

        # Add metadata if present
        metadata = self._extract_formula_metadata(formula)
        if metadata:
            attr_dict["metadata"] = metadata

        # Add attribute-level alternate state handlers if present
        if hasattr(formula, "alternate_state_handler") and formula.alternate_state_handler:
            has_handlers = False
            alternate_states: dict[str, Any] = {}

            if (
                hasattr(formula.alternate_state_handler, "unavailable")
                and formula.alternate_state_handler.unavailable is not None
            ):
                alternate_states[UNAVAILABLE_KEY] = self._convert_python_to_yaml_value(
                    formula.alternate_state_handler.unavailable
                )
                has_handlers = True
            if hasattr(formula.alternate_state_handler, "unknown") and formula.alternate_state_handler.unknown is not None:
                alternate_states[UNKNOWN_KEY] = self._convert_python_to_yaml_value(formula.alternate_state_handler.unknown)
                has_handlers = True
            if hasattr(formula.alternate_state_handler, "none") and formula.alternate_state_handler.none is not None:
                alternate_states[NONE_KEY] = self._convert_python_to_yaml_value(formula.alternate_state_handler.none)
                has_handlers = True
            if hasattr(formula.alternate_state_handler, "fallback") and formula.alternate_state_handler.fallback is not None:
                alternate_states[FALLBACK_KEY] = self._convert_python_to_yaml_value(formula.alternate_state_handler.fallback)
                has_handlers = True

            if has_handlers:
                attr_dict["alternate_states"] = alternate_states

        return attr_dict

    def _extract_formula_metadata(self, formula: FormulaConfig) -> dict[str, Any] | None:
        """Extract metadata from formula configuration."""
        # Add metadata if present
        if hasattr(formula, "metadata") and formula.metadata:
            return formula.metadata

        # Legacy field support - migrate to metadata format
        legacy_metadata = self._extract_legacy_formula_metadata(formula)
        return legacy_metadata if legacy_metadata else None

    def _extract_legacy_formula_metadata(self, formula: FormulaConfig) -> dict[str, Any] | None:
        """Extract legacy metadata fields from formula configuration."""
        legacy_metadata = {}

        if hasattr(formula, METADATA_PROPERTY_UNIT_OF_MEASUREMENT) and getattr(formula, METADATA_PROPERTY_UNIT_OF_MEASUREMENT):
            legacy_metadata[METADATA_PROPERTY_UNIT_OF_MEASUREMENT] = getattr(formula, METADATA_PROPERTY_UNIT_OF_MEASUREMENT)
        if hasattr(formula, METADATA_PROPERTY_DEVICE_CLASS) and getattr(formula, METADATA_PROPERTY_DEVICE_CLASS):
            legacy_metadata[METADATA_PROPERTY_DEVICE_CLASS] = getattr(formula, METADATA_PROPERTY_DEVICE_CLASS)
        if hasattr(formula, METADATA_PROPERTY_STATE_CLASS) and getattr(formula, METADATA_PROPERTY_STATE_CLASS):
            legacy_metadata[METADATA_PROPERTY_STATE_CLASS] = getattr(formula, METADATA_PROPERTY_STATE_CLASS)
        if hasattr(formula, METADATA_PROPERTY_ICON) and getattr(formula, METADATA_PROPERTY_ICON):
            legacy_metadata[METADATA_PROPERTY_ICON] = getattr(formula, METADATA_PROPERTY_ICON)

        return legacy_metadata if legacy_metadata else None

    def _parse_literal_value(self, formula: str) -> int | float | str | bool | None:
        """Parse formula as literal value if possible."""
        # Try numeric parsing first
        numeric_result = self._parse_numeric_literal(formula)
        if numeric_result is not None:
            return numeric_result

        # Try string literal parsing
        string_result = self._parse_string_literal(formula)
        if string_result is not None:
            return string_result

        # Try boolean literal parsing
        boolean_result = self._parse_boolean_literal(formula)
        if boolean_result is not None:
            return boolean_result

        # Try simple string literal parsing (no operators)
        simple_result = self._parse_simple_string_literal(formula)
        if simple_result is not None:
            return simple_result

        return None

    def _parse_numeric_literal(self, formula: str) -> int | float | None:
        """Parse numeric literal values."""
        try:
            # Integer literal
            if formula.isdigit():
                return int(formula)

            # Float literal
            if formula.replace(".", "").replace("-", "").isdigit() and formula.count(".") <= 1:
                return float(formula)
        except (ValueError, AttributeError):
            pass

        return None

    def _parse_string_literal(self, formula: str) -> str | None:
        """Parse string literal values with quotes."""
        try:
            if (formula.startswith('"') and formula.endswith('"')) or (formula.startswith("'") and formula.endswith("'")):
                return formula[1:-1]
        except (ValueError, AttributeError):
            pass
        return None

    def _parse_boolean_literal(self, formula: str) -> bool | None:
        """Parse boolean literal values."""
        try:
            if formula == "True":
                return True
            if formula == "False":
                return False
        except (ValueError, AttributeError):
            pass
        return None

    def _parse_simple_string_literal(self, formula: str) -> str | None:
        """Parse simple string literal without operators.

        Only returns a value for actual string literals that are clearly not:
        - Variable references (e.g., panel_status)
        - Entity references (e.g., sensor.power_meter)
        - Function calls (e.g., state, utc_now())
        """
        try:
            # Don't treat variable names, entity IDs, or function calls as literals
            # Only treat actual quoted strings as literals here
            if (formula.startswith('"') and formula.endswith('"')) or (formula.startswith("'") and formula.endswith("'")):
                return formula[1:-1]  # Remove quotes
        except (ValueError, AttributeError):
            pass
        return None

    def _add_main_formula_details(self, sensor_dict: dict[str, Any], main_formula: FormulaConfig) -> None:
        """Add main formula details to sensor dictionary."""
        sensor_dict["formula"] = main_formula.formula

        # Add main formula alternate state handlers first (sensor level)
        if main_formula.alternate_state_handler:
            self._add_alternate_state_handlers(sensor_dict, main_formula.alternate_state_handler)

        # Add variables with proper serialization
        if main_formula.variables:
            sensor_dict["variables"] = self._serialize_variables(main_formula.variables)

        # Add metadata if present (formula-level metadata overrides sensor-level metadata)
        metadata = self._extract_formula_metadata(main_formula)
        if metadata:
            self._merge_metadata(sensor_dict, metadata)

    def _merge_metadata(self, sensor_dict: dict[str, Any], formula_metadata: dict[str, Any]) -> None:
        """Merge formula metadata with existing sensor metadata."""
        existing_metadata = sensor_dict.get("metadata", {})
        merged_metadata = {**existing_metadata, **formula_metadata}
        sensor_dict["metadata"] = merged_metadata

    def _add_alternate_state_handlers(self, sensor_dict: dict[str, Any], alternate_state_handler: Any) -> None:
        """Add alternate state handlers to sensor dictionary with proper casing."""
        # Check if any alternate state handlers exist
        has_handlers = False
        alternate_states = {}

        if hasattr(alternate_state_handler, "unavailable") and alternate_state_handler.unavailable is not None:
            alternate_states[UNAVAILABLE_KEY] = self._convert_python_to_yaml_value(alternate_state_handler.unavailable)
            has_handlers = True
        if hasattr(alternate_state_handler, "unknown") and alternate_state_handler.unknown is not None:
            alternate_states[UNKNOWN_KEY] = self._convert_python_to_yaml_value(alternate_state_handler.unknown)
            has_handlers = True
        if hasattr(alternate_state_handler, "none") and alternate_state_handler.none is not None:
            alternate_states[NONE_KEY] = self._convert_python_to_yaml_value(alternate_state_handler.none)
            has_handlers = True
        if hasattr(alternate_state_handler, "fallback") and alternate_state_handler.fallback is not None:
            alternate_states[FALLBACK_KEY] = self._convert_python_to_yaml_value(alternate_state_handler.fallback)
            has_handlers = True

        # Add alternate_states group if any handlers exist
        if has_handlers:
            sensor_dict["alternate_states"] = alternate_states

    def _convert_python_to_yaml_value(self, value: Any) -> Any:
        """Convert Python values to YAML representation.

        Specifically handles Python None → STATE_NONE for YAML readability.
        Also filters out dataclass sentinel objects that shouldn't be serialized.
        """
        # Skip dataclass sentinel objects (MISSING values)
        if hasattr(value, "__class__") and value.__class__.__name__ == "_MISSING_TYPE":
            return None

        if value is None:
            return STATE_NONE_YAML
        return value

    def _convert_yaml_to_python_value(self, value: Any) -> Any:
        """Convert YAML values to Python representation.

        Specifically handles STATE_NONE → Python None.
        """
        if isinstance(value, str) and value == STATE_NONE_YAML:
            return None
        return value

    def _serialize_variables(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Serialize variables dictionary, converting ComputedVariable objects to YAML format."""
        serialized_variables = {}

        for name, value in variables.items():
            if hasattr(value, "formula"):  # ComputedVariable object
                var_dict = {"formula": value.formula}

                # Add alternate state handlers with proper casing
                if hasattr(value, "alternate_state_handler") and value.alternate_state_handler:
                    has_handlers = False
                    alternate_states = {}

                    if (
                        hasattr(value.alternate_state_handler, "unavailable")
                        and value.alternate_state_handler.unavailable is not None
                    ):
                        alternate_states[UNAVAILABLE_KEY] = self._convert_python_to_yaml_value(
                            value.alternate_state_handler.unavailable
                        )
                        has_handlers = True
                    if hasattr(value.alternate_state_handler, "unknown") and value.alternate_state_handler.unknown is not None:
                        alternate_states[UNKNOWN_KEY] = self._convert_python_to_yaml_value(
                            value.alternate_state_handler.unknown
                        )
                        has_handlers = True
                    if hasattr(value.alternate_state_handler, "none") and value.alternate_state_handler.none is not None:
                        alternate_states[NONE_KEY] = self._convert_python_to_yaml_value(value.alternate_state_handler.none)
                        has_handlers = True
                    if (
                        hasattr(value.alternate_state_handler, "fallback")
                        and value.alternate_state_handler.fallback is not None
                    ):
                        alternate_states[FALLBACK_KEY] = self._convert_python_to_yaml_value(
                            value.alternate_state_handler.fallback
                        )
                        has_handlers = True

                    # Add alternate_states group if any handlers exist
                    if has_handlers:
                        var_dict["alternate_states"] = alternate_states

                # Add allow_unresolved_states if set
                if hasattr(value, "allow_unresolved_states") and value.allow_unresolved_states:
                    var_dict["allow_unresolved_states"] = value.allow_unresolved_states

                serialized_variables[name] = var_dict
            else:
                # Simple variable (string, int, float)
                serialized_variables[name] = value

        return serialized_variables

    def _get_entity_id_for_sensor(self, unique_id: str) -> str | None:
        """Get the entity ID for a sensor from its unique ID.

        Args:
            unique_id: The unique ID of the sensor

        Returns:
            The entity ID if found, None otherwise
        """
        # Use the integration domain from storage manager
        domain = self.storage_manager.integration_domain

        # Try to find the entity in the registry
        entity_registry = er.async_get(self.storage_manager.hass)
        entity = entity_registry.async_get_entity_id("sensor", domain, unique_id)

        return entity

    def _get_friendly_name_from_registry(self, entity_id: str) -> str | None:
        """Get the current friendly name from the entity registry.

        Args:
            entity_id: The entity ID to look up

        Returns:
            The current friendly name if found, None otherwise
        """
        entity_registry = er.async_get(self.storage_manager.hass)
        entity = entity_registry.async_get(entity_id)

        if entity and entity.name:
            return str(entity.name)

        # Fall back to checking the state
        state = self.storage_manager.hass.states.get(entity_id)
        if state and state.attributes.get("friendly_name"):
            return str(state.attributes["friendly_name"])

        return None
