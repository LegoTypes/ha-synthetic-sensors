"""Formula Reference Resolver for Phase 3 of cross-sensor reference resolution.

This module implements the third phase of the cross-sensor reference system as described
in the design reference guide. It replaces sensor key references in formulas with actual
HA-assigned entity IDs after all sensors have been registered.

Key Features:
- Replaces sensor key references with actual entity IDs in formulas
- Handles both sensor key references (e.g., 'my_sensor') and entity ID references (e.g., 'sensor.my_sensor')
- Uses smart tokenization to preserve entity ID integrity
- Updates stored configurations with resolved references
- Modular design with specialized resolvers for different reference types
"""

import logging
import re
from typing import Any

from .config_models import Config, FormulaConfig, SensorConfig
from .shared_constants import BOOLEAN_LITERALS, BUILTIN_TYPES, MATH_FUNCTIONS, PYTHON_KEYWORDS, STATE_KEYWORDS

_LOGGER = logging.getLogger(__name__)


class ReferencePattern:
    """Represents a detected reference pattern in a formula."""

    def __init__(self, pattern_type: str, original_text: str, start_pos: int, end_pos: int, sensor_key: str):
        self.pattern_type = pattern_type  # 'sensor_key' or 'entity_id'
        self.original_text = original_text  # The full text that matched
        self.start_pos = start_pos  # Start position in formula
        self.end_pos = end_pos  # End position in formula
        self.sensor_key = sensor_key  # The sensor key part (for mapping lookup)


class ReferencePatternDetector:
    """Detects different types of cross-sensor references in formulas."""

    def __init__(self) -> None:
        # Pattern for entity IDs: sensor.something, binary_sensor.something, etc.
        self.entity_id_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)\b")
        # Pattern for standalone sensor keys: just the identifier
        self.sensor_key_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")

    def detect_references(self, formula: str, entity_mappings: dict[str, str]) -> list[ReferencePattern]:
        """Detect all cross-sensor references in a formula.

        Args:
            formula: Formula to analyze
            entity_mappings: Available sensor key mappings

        Returns:
            List of detected reference patterns, sorted by position (reverse order for safe replacement)
        """
        patterns = []

        # First, detect entity ID references (e.g., sensor.my_sensor)
        for match in self.entity_id_pattern.finditer(formula):
            entity_id = match.group(1)
            # Extract sensor key from entity ID (part after the dot)
            if "." in entity_id:
                _, sensor_key = entity_id.split(".", 1)
                # Only consider this if we have a mapping for the sensor key
                if sensor_key in entity_mappings:
                    patterns.append(
                        ReferencePattern(
                            pattern_type="entity_id",
                            original_text=entity_id,
                            start_pos=match.start(),
                            end_pos=match.end(),
                            sensor_key=sensor_key,
                        )
                    )

        # Then, detect standalone sensor key references (e.g., my_sensor)
        # But exclude ones that are part of entity IDs we already found
        entity_id_ranges = [(p.start_pos, p.end_pos) for p in patterns]

        for match in self.sensor_key_pattern.finditer(formula):
            sensor_key = match.group(1)
            start_pos = match.start()
            end_pos = match.end()

            # Skip if this is part of an entity ID we already detected
            is_part_of_entity_id = any(
                entity_start <= start_pos < entity_end or entity_start < end_pos <= entity_end
                for entity_start, entity_end in entity_id_ranges
            )

            # Skip reserved words and non-mapped keys
            if not is_part_of_entity_id and sensor_key in entity_mappings and not self._is_reserved_word(sensor_key):
                patterns.append(
                    ReferencePattern(
                        pattern_type="sensor_key",
                        original_text=sensor_key,
                        start_pos=start_pos,
                        end_pos=end_pos,
                        sensor_key=sensor_key,
                    )
                )

        # Sort by position in reverse order for safe replacement (replace from end to start)
        patterns.sort(key=lambda p: p.start_pos, reverse=True)
        return patterns

    def _is_reserved_word(self, word: str) -> bool:
        """Check if a word is a reserved keyword or function name."""
        # Combine all reserved word sets from shared constants
        reserved_words = PYTHON_KEYWORDS | BUILTIN_TYPES | BOOLEAN_LITERALS | MATH_FUNCTIONS | STATE_KEYWORDS

        # Add additional state-related keywords specific to this module
        additional_state_keywords = {
            "states",
            "is_state",
            "is_state_attr",
            "state_attr",
            "now",
            "today",
        }

        return word in reserved_words or word in additional_state_keywords


class ReferenceReplacer:
    """Handles replacement of detected references with resolved entity IDs."""

    def replace_references(
        self,
        formula: str,
        patterns: list[ReferencePattern],
        entity_mappings: dict[str, str],
        current_sensor_key: str | None = None,
        is_attribute_formula: bool = False,
    ) -> tuple[str, dict[str, str]]:
        """Replace detected reference patterns with resolved entity IDs.

        Args:
            formula: Original formula
            patterns: Detected reference patterns (should be sorted by position, reverse order)
            entity_mappings: Mapping from sensor keys to entity IDs
            current_sensor_key: The key of the sensor containing this formula (for self-reference detection)
            is_attribute_formula: Whether this formula is in an attribute context

        Returns:
            Tuple of (resolved_formula, replacements_made)
        """
        resolved_formula = formula
        replacements_made = {}

        for pattern in patterns:
            if pattern.sensor_key in entity_mappings:
                # Check for self-reference (both main formulas and attributes per design guide)
                if current_sensor_key and pattern.sensor_key == current_sensor_key:
                    # Self-reference: always replace with 'state' token per design guide
                    # This ensures evaluation stays within the current update cycle instead of
                    # requiring HA state machine lookups, preventing stale data
                    replacement_text = "state"
                    resolved_formula = (
                        resolved_formula[: pattern.start_pos] + replacement_text + resolved_formula[pattern.end_pos :]
                    )
                    replacements_made[pattern.original_text] = replacement_text
                else:
                    # Normal cross-sensor reference: replace with entity ID
                    new_entity_id = entity_mappings[pattern.sensor_key]
                    resolved_formula = (
                        resolved_formula[: pattern.start_pos] + new_entity_id + resolved_formula[pattern.end_pos :]
                    )
                    replacements_made[pattern.original_text] = new_entity_id

        return resolved_formula, replacements_made


class FormulaReferenceResolver:
    """Resolves cross-sensor references in formulas during Phase 3.

    This resolver handles Phase 3 of the cross-sensor reference system:
    - Replacing sensor key references with actual entity IDs
    - Handling both sensor key and entity ID references
    - Using modular pattern detection and replacement
    - Maintaining formula integrity during replacement
    """

    def __init__(self) -> None:
        """Initialize the formula reference resolver."""
        self._logger = _LOGGER.getChild(self.__class__.__name__)
        self._pattern_detector = ReferencePatternDetector()
        self._reference_replacer = ReferenceReplacer()

    def resolve_all_references_in_config(self, config: Config, entity_mappings: dict[str, str]) -> Config:
        """Resolve all cross-sensor references in a config using entity mappings.

        Args:
            config: Config object with sensors containing cross-sensor references
            entity_mappings: Dict mapping sensor_key -> actual_entity_id

        Returns:
            Updated config with resolved entity IDs in formulas
        """
        if not entity_mappings:
            self._logger.debug("No entity mappings provided, skipping reference resolution")
            return config

        self._logger.info(
            "Resolving cross-sensor references in %d sensors using %d entity mappings",
            len(config.sensors),
            len(entity_mappings),
        )

        # Create a copy of the config to avoid modifying the original
        resolved_config = Config(
            version=config.version,
            global_settings=config.global_settings.copy(),
            cross_sensor_references=config.cross_sensor_references.copy(),
        )

        # Resolve references in each sensor
        for sensor in config.sensors:
            resolved_sensor = self._resolve_references_in_sensor(sensor, entity_mappings)
            resolved_config.sensors.append(resolved_sensor)

        self._logger.info("Cross-sensor reference resolution complete")
        return resolved_config

    def _resolve_references_in_sensor(self, sensor: SensorConfig, entity_mappings: dict[str, str]) -> SensorConfig:
        """Resolve cross-sensor references in a single sensor.

        Args:
            sensor: SensorConfig with potentially unresolved references
            entity_mappings: Dict mapping sensor_key -> actual_entity_id

        Returns:
            New SensorConfig with resolved references
        """
        # Update entity_id field with HA-assigned value if available
        updated_entity_id = entity_mappings.get(sensor.unique_id, sensor.entity_id)

        # Create a copy of the sensor config with updated entity_id
        resolved_sensor = SensorConfig(
            unique_id=sensor.unique_id,
            name=sensor.name,
            enabled=sensor.enabled,
            update_interval=sensor.update_interval,
            category=sensor.category,
            description=sensor.description,
            entity_id=updated_entity_id,  # Use HA-assigned entity_id per design guide
            metadata=sensor.metadata.copy(),
            device_identifier=sensor.device_identifier,
            device_name=sensor.device_name,
            device_manufacturer=sensor.device_manufacturer,
            device_model=sensor.device_model,
            device_sw_version=sensor.device_sw_version,
            device_hw_version=sensor.device_hw_version,
            suggested_area=sensor.suggested_area,
        )

        # Resolve references in all formulas
        for formula in sensor.formulas:
            resolved_formula = self._resolve_references_in_formula(formula, entity_mappings, sensor.unique_id)
            resolved_sensor.formulas.append(resolved_formula)

        return resolved_sensor

    def _resolve_references_in_formula(
        self, formula: FormulaConfig, entity_mappings: dict[str, str], current_sensor_key: str
    ) -> FormulaConfig:
        """Resolve cross-sensor references in a single formula.

        This method resolves sensor key references in ALL locations:
        - Formula strings
        - Variables (values that reference sensor keys)
        - Dependencies (sensor keys in dependency sets)
        - Attributes (values that reference sensor keys)

        Args:
            formula: FormulaConfig with potentially unresolved references
            entity_mappings: Dict mapping sensor_key -> actual_entity_id

        Returns:
            New FormulaConfig with resolved references
        """
        # Determine if this is an attribute formula (not main formula)
        is_attribute_formula = formula.id not in ("main", current_sensor_key)

        # Resolve the formula string
        resolved_formula_string = self._resolve_references_in_formula_string(
            formula.formula, entity_mappings, current_sensor_key, is_attribute_formula
        )

        # Resolve variables - replace sensor key values with entity IDs or 'state' for self-references
        resolved_variables = self._resolve_references_in_variables(formula.variables, entity_mappings, current_sensor_key)

        # Resolve dependencies - replace sensor keys with entity IDs or 'state' for self-references
        resolved_dependencies = self._resolve_references_in_dependencies(
            formula.dependencies, entity_mappings, current_sensor_key
        )

        # Resolve attributes - replace sensor key values with entity IDs
        # Note: Attributes are always in attribute context, regardless of the formula type
        resolved_attributes = self._resolve_references_in_attributes(
            formula.attributes, entity_mappings, current_sensor_key, True
        )

        # Create a copy of the formula config with all resolved references
        resolved_formula = FormulaConfig(
            id=formula.id,
            formula=resolved_formula_string,
            name=formula.name,
            metadata=formula.metadata.copy(),
            attributes=resolved_attributes,
            dependencies=resolved_dependencies,
            variables=resolved_variables,
        )

        return resolved_formula

    def _is_self_reference(self, var_value: str, current_sensor_key: str | None, entity_mappings: dict[str, str]) -> bool:
        """Check if a variable value is a self-reference."""
        if not current_sensor_key:
            return False

        # Direct sensor key match
        if var_value == current_sensor_key:
            return True

        # Entity ID format match (sensor.key -> key)
        if var_value.startswith("sensor.") and var_value[7:] == current_sensor_key:
            return True

            # Mapped entity ID match
        return var_value in entity_mappings and entity_mappings[var_value] == entity_mappings.get(current_sensor_key)

    def _resolve_references_in_variables(
        self, variables: dict[str, str | int | float], entity_mappings: dict[str, str], current_sensor_key: str | None = None
    ) -> dict[str, str | int | float]:
        """Resolve sensor key references in variables.

        Variables can have string values that reference sensor keys:
        Example: {"my_sensor": "base_power"} -> {"my_sensor": "sensor.base_power_2"}

        Args:
            variables: Original variables dict
            entity_mappings: Dict mapping sensor_key -> actual_entity_id

        Returns:
            Variables dict with resolved sensor key references
        """
        if not variables or not entity_mappings:
            return variables.copy()

        resolved_variables: dict[str, str | int | float] = {}
        replacements_made = {}

        for var_name, var_value in variables.items():
            if isinstance(var_value, str):
                # Check if this is a self-reference (either sensor key or entity ID format)
                is_self_reference = self._is_self_reference(var_value, current_sensor_key, entity_mappings)

                if is_self_reference:
                    # Self-reference: use 'state' token per design guide
                    resolved_value = "state"
                    resolved_variables[var_name] = resolved_value
                    replacements_made[var_value] = resolved_value
                elif var_value in entity_mappings:
                    # Cross-sensor reference: use HA-assigned entity_id
                    resolved_value = entity_mappings[var_value]
                    resolved_variables[var_name] = resolved_value
                    replacements_made[var_value] = resolved_value
                else:
                    # Keep original value (could be unreferenced string)
                    resolved_variables[var_name] = var_value
            else:
                # Keep original value (numeric or other types)
                resolved_variables[var_name] = var_value

        if replacements_made:
            self._logger.debug("Variable reference resolution: %s", replacements_made)

        return resolved_variables

    def _resolve_references_in_dependencies(
        self, dependencies: set[str], entity_mappings: dict[str, str], current_sensor_key: str | None = None
    ) -> set[str]:
        """Resolve sensor key references in dependencies.

        Dependencies can contain sensor keys that need to be resolved:
        Example: {"base_power", "solar_power"} -> {"sensor.base_power_2", "sensor.solar_power_3"}

        Args:
            dependencies: Original dependencies set
            entity_mappings: Dict mapping sensor_key -> actual_entity_id

        Returns:
            Dependencies set with resolved sensor key references
        """
        if not dependencies or not entity_mappings:
            return dependencies.copy()

        resolved_dependencies = set()
        replacements_made = {}

        for dependency in dependencies:
            if dependency in entity_mappings:
                # Check if this is a self-reference
                if current_sensor_key and dependency == current_sensor_key:
                    # Self-reference: use 'state' token per design guide
                    resolved_dependency = "state"
                    resolved_dependencies.add(resolved_dependency)
                    replacements_made[dependency] = resolved_dependency
                else:
                    # Cross-sensor reference: use HA-assigned entity_id
                    resolved_dependency = entity_mappings[dependency]
                    resolved_dependencies.add(resolved_dependency)
                    replacements_made[dependency] = resolved_dependency
            else:
                # Keep original dependency (could be actual entity_id or other reference)
                resolved_dependencies.add(dependency)

        if replacements_made:
            self._logger.debug("Dependency reference resolution: %s", replacements_made)

        return resolved_dependencies

    def _resolve_references_in_attributes(
        self,
        attributes: dict[str, Any],
        entity_mappings: dict[str, str],
        current_sensor_key: str | None = None,
        is_attribute_formula: bool = False,
    ) -> dict[str, Any]:
        """Resolve sensor key references in attributes.

        Attributes can have string values that reference sensor keys.
        This recursively handles nested dictionaries and lists.

        Args:
            attributes: Original attributes dict
            entity_mappings: Dict mapping sensor_key -> actual_entity_id

        Returns:
            Attributes dict with resolved sensor key references
        """
        if not attributes or not entity_mappings:
            return attributes.copy()

        def resolve_attribute_value(value: Any) -> Any:
            """Recursively resolve references in attribute values."""
            if isinstance(value, str):
                # Check if this is a self-reference (either sensor key or entity ID format)
                is_self_reference = self._is_self_reference(value, current_sensor_key, entity_mappings)

                if is_self_reference:
                    return "state"  # Replace self-reference with state token
                if value in entity_mappings:
                    return entity_mappings[value]
                # Otherwise, treat as formula string and resolve references within it
                return self._resolve_references_in_formula_string(
                    value, entity_mappings, current_sensor_key, is_attribute_formula
                )
            if isinstance(value, dict):
                # Recursively process dictionary values
                return {k: resolve_attribute_value(v) for k, v in value.items()}
            if isinstance(value, list):
                # Recursively process list items
                return [resolve_attribute_value(item) for item in value]
            # Keep original value (numbers, bools, etc.)
            return value

        resolved_attributes = {}
        original_count = self._count_sensor_keys_in_attributes(attributes, entity_mappings)

        for attr_name, attr_value in attributes.items():
            resolved_attributes[attr_name] = resolve_attribute_value(attr_value)

        resolved_count = self._count_sensor_keys_in_attributes(resolved_attributes, entity_mappings)
        replacements_made = original_count - resolved_count

        if replacements_made > 0:
            self._logger.debug("Attribute reference resolution: %d sensor key references resolved", replacements_made)

        return resolved_attributes

    def _count_sensor_keys_in_attributes(self, attributes: dict[str, Any], entity_mappings: dict[str, str]) -> int:
        """Count sensor key references in attributes for logging."""

        def count_in_value(value: Any) -> int:
            if isinstance(value, str) and value in entity_mappings:
                return 1
            if isinstance(value, dict):
                return sum(count_in_value(v) for v in value.values())
            if isinstance(value, list):
                return sum(count_in_value(item) for item in value)
            return 0

        return sum(count_in_value(v) for v in attributes.values())

    def _resolve_references_in_formula_string(
        self,
        formula: str,
        entity_mappings: dict[str, str],
        current_sensor_key: str | None = None,
        is_attribute_formula: bool = False,
    ) -> str:
        """Resolve cross-sensor references in a formula string.

        This method uses modular pattern detection to identify both sensor key references
        and entity ID references, then replaces them with actual entity IDs.

        Args:
            formula: Formula string with potential cross-sensor references
            entity_mappings: Dict mapping sensor_key -> actual_entity_id

        Returns:
            Formula string with references replaced by resolved entity IDs

        Examples:
            # Sensor key references
            formula = "my_sensor * 3 + base_power"
            entity_mappings = {"my_sensor": "sensor.my_sensor_2", "base_power": "sensor.base_power_3"}
            Returns: "sensor.my_sensor_2 * 3 + sensor.base_power_3"

            # Entity ID references
            formula = "sensor.my_sensor + 100"
            entity_mappings = {"my_sensor": "sensor.my_sensor_2"}
            Returns: "sensor.my_sensor_2 + 100"
        """
        if not formula or not entity_mappings:
            return formula

        # Detect all reference patterns in the formula
        patterns = self._pattern_detector.detect_references(formula, entity_mappings)

        if not patterns:
            return formula

        # Replace detected patterns with resolved entity IDs (or state tokens for self-references in attributes)
        resolved_formula, replacements_made = self._reference_replacer.replace_references(
            formula, patterns, entity_mappings, current_sensor_key, is_attribute_formula
        )

        # Log replacements for debugging
        if replacements_made:
            self._logger.debug(
                "Formula reference resolution: '%s' -> '%s'. Replacements: %s", formula, resolved_formula, replacements_made
            )

        return resolved_formula

    # Legacy tokenization methods removed - now using modular ReferencePatternDetector and ReferenceReplacer

    def get_replacement_summary(self, config: Config, entity_mappings: dict[str, str]) -> dict[str, Any]:
        """Get a summary of what replacements would be made without modifying the config.

        Args:
            config: Config to analyze
            entity_mappings: Entity mappings to use

        Returns:
            Dict mapping sensor_key -> {formula_id -> replacement_summary}
        """
        replacement_summary = {}

        for sensor in config.sensors:
            sensor_replacements = {}

            for formula in sensor.formulas:
                # Check what replacements would be made in this formula
                patterns = self._pattern_detector.detect_references(formula.formula, entity_mappings)

                if patterns:
                    # Determine if this is an attribute formula
                    is_attribute_formula = formula.id not in ("main", sensor.unique_id)

                    _, replacements_made = self._reference_replacer.replace_references(
                        formula.formula, patterns, entity_mappings, sensor.unique_id, is_attribute_formula
                    )

                    if replacements_made:
                        sensor_replacements[formula.id] = {
                            "original_formula": formula.formula,
                            "replacements": dict(replacements_made),
                        }

            if sensor_replacements:
                replacement_summary[sensor.unique_id] = sensor_replacements

        return replacement_summary
