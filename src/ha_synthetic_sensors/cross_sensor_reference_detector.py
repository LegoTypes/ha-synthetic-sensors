"""Cross-Sensor Reference Detection for Phase 1 of cross-sensor reference resolution.

This module implements the first phase of the cross-sensor reference system as described
in the design reference guide. It scans YAML configurations to detect sensor key
references in both main formulas and attribute formulas, building a dependency map
that will be used in later phases for entity ID resolution.

Key Features:
- Detects sensor key references in main sensor formulas
- Detects sensor key references in attribute formulas (critical for parent sensor references)
- Builds cross-sensor dependency mapping
- Supports complex formula expressions with multiple references
- Integrates with existing YAML processing pipeline
"""

import logging
from typing import Any

from .config_models import Config, SensorConfig
from .formula_utils import tokenize_formula
from .regex_helper import create_collection_function_detection_pattern

_LOGGER = logging.getLogger(__name__)


class CrossSensorReferenceDetector:
    """Detects cross-sensor references in YAML sensor configurations.

    This detector scans both main sensor formulas and attribute formulas to identify
    references to other sensors by their YAML-defined keys. This is Phase 1 of the
    cross-sensor reference resolution system.
    """

    def __init__(self) -> None:
        """Initialize the cross-sensor reference detector."""
        self._logger = _LOGGER.getChild(self.__class__.__name__)

    def scan_yaml_references(self, yaml_data: dict[str, Any]) -> dict[str, set[str]]:
        """Scan YAML configuration for cross-sensor references.

        Args:
            yaml_data: Raw YAML data dictionary

        Returns:
            Dict mapping sensor_key -> set of referenced sensor keys

        Example:
            yaml_data = {
                "sensors": {
                    "base_power": {"formula": "state * 1.0"},
                    "derived_power": {"formula": "base_power * 1.1"},
                    "efficiency": {
                        "formula": "derived_power / base_power * 100",
                        "attributes": {
                            "daily": {"formula": "derived_power * 24"}
                        }
                    }
                }
            }

            Returns:
            {
                "derived_power": {"base_power"},
                "efficiency": {"derived_power", "base_power"}
            }
        """
        if "sensors" not in yaml_data:
            return {}

        sensors_data = yaml_data["sensors"]
        if not isinstance(sensors_data, dict):
            return {}

        # Get all sensor keys for reference detection
        sensor_keys = set(sensors_data.keys())

        # Build reference mapping
        reference_map = {}

        for sensor_key, sensor_config in sensors_data.items():
            if not isinstance(sensor_config, dict):
                continue

            references = self._extract_sensor_references_from_config(sensor_config, sensor_keys)

            if references:
                reference_map[sensor_key] = references

        # Debug logging removed to reduce verbosity

        return reference_map

    def scan_config_references(self, config: Config) -> dict[str, set[str]]:
        """Scan Config object for cross-sensor references.

        Args:
            config: Parsed Config object

        Returns:
            Dict mapping sensor_key -> set of referenced sensor keys
        """
        # Get all sensor keys from the config
        sensor_keys = {sensor.unique_id for sensor in config.sensors}

        # Build reference mapping
        reference_map = {}

        for sensor in config.sensors:
            references = self._extract_sensor_references_from_sensor_config(sensor, sensor_keys)

            if references:
                reference_map[sensor.unique_id] = references

        # Debug logging removed to reduce verbosity

        return reference_map

    def _extract_sensor_references_from_config(self, sensor_config: dict[str, Any], sensor_keys: set[str]) -> set[str]:
        """Extract sensor key references from a sensor configuration dictionary.

        Args:
            sensor_config: Sensor configuration dictionary from YAML
            sensor_keys: Set of all available sensor keys

        Returns:
            Set of referenced sensor keys
        """
        references = set()

        # Check main formula
        if "formula" in sensor_config:
            main_refs = self._extract_references_from_formula(sensor_config["formula"], sensor_keys)
            references.update(main_refs)

        # Check attribute formulas
        if "attributes" in sensor_config and isinstance(sensor_config["attributes"], dict):
            for _attr_name, attr_config in sensor_config["attributes"].items():
                if isinstance(attr_config, dict) and "formula" in attr_config:
                    attr_refs = self._extract_references_from_formula(attr_config["formula"], sensor_keys)
                    references.update(attr_refs)

        return references

    def _extract_sensor_references_from_sensor_config(self, sensor_config: SensorConfig, sensor_keys: set[str]) -> set[str]:
        """Extract sensor key references from a SensorConfig object.

        Args:
            sensor_config: SensorConfig object
            sensor_keys: Set of all available sensor keys

        Returns:
            Set of referenced sensor keys
        """
        references = set()

        # Check all formulas in the sensor
        for formula_config in sensor_config.formulas:
            formula_refs = self._extract_references_from_formula(formula_config.formula, sensor_keys)
            references.update(formula_refs)

        return references

    def _extract_references_from_formula(self, formula: str, sensor_keys: set[str]) -> set[str]:
        """Extract sensor key references from a formula string.

        This method uses tokenization to identify sensor key references while avoiding
        partial word matches and false positives. It excludes identifiers that are
        inside collection function calls.

        Args:
            formula: Formula string to scan
            sensor_keys: Set of all available sensor keys

        Returns:
            Set of referenced sensor keys found in the formula

        Example:
            formula = "base_power_sensor * 1.1 + solar_power"
            sensor_keys = {"base_power_sensor", "solar_power", "efficiency"}

            Returns: {"base_power_sensor", "solar_power"}
        """
        if not formula or not sensor_keys:
            return set()

        # First, remove collection function calls to avoid false positives
        formula_without_collections = self._remove_collection_functions(formula)

        # Tokenize the cleaned formula to identify potential sensor references
        # Use word boundaries to avoid partial matches
        tokens = self._tokenize_formula(formula_without_collections)

        # Find tokens that match sensor keys
        references = set()
        for token in tokens:
            if token in sensor_keys:
                references.add(token)

        return references

    def _remove_collection_functions(self, formula: str) -> str:
        """Remove collection function calls from formula to avoid false positives.

        Args:
            formula: Original formula string

        Returns:
            Formula with collection function calls replaced by placeholders
        """
        # Use centralized collection function detection pattern from regex helper

        collection_pattern = create_collection_function_detection_pattern()

        # Replace collection functions with placeholders to avoid parsing their contents
        return collection_pattern.sub("COLLECTION_FUNC", formula)

    def _tokenize_formula(self, formula: str) -> set[str]:
        """Tokenize formula to extract potential variable/sensor references.

        This method identifies alphanumeric tokens that could be sensor references,
        while excluding operators, numbers, and other non-identifier tokens.

        Args:
            formula: Formula string to tokenize

        Returns:
            Set of potential identifier tokens
        """
        # Pattern to match valid Python identifiers (sensor keys)
        return tokenize_formula(formula)

    def analyze_dependency_order(self, reference_map: dict[str, set[str]]) -> list[str]:
        """Analyze cross-sensor dependencies to determine evaluation order.

        Uses topological sorting to determine the order in which sensors should be
        processed to respect dependencies.

        Args:
            reference_map: Dict mapping sensor_key -> set of referenced sensor keys

        Returns:
            List of sensor keys in dependency order (dependencies first)

        Raises:
            ValueError: If circular dependencies are detected
        """
        # Build reverse dependency map (who depends on whom)
        dependents: dict[str, set[str]] = {}
        all_sensors = set()

        # Collect all sensors mentioned
        for sensor_key, references in reference_map.items():
            all_sensors.add(sensor_key)
            all_sensors.update(references)

        # Initialize dependents mapping
        for sensor_key in all_sensors:
            dependents[sensor_key] = set()

        # Populate dependents mapping
        for sensor_key, references in reference_map.items():
            for ref_key in references:
                dependents[ref_key].add(sensor_key)

        # Perform topological sort using Kahn's algorithm
        # Start with sensors that have no dependencies
        in_degree = {}
        for sensor_key in all_sensors:
            in_degree[sensor_key] = len(reference_map.get(sensor_key, set()))

        # Queue of sensors with no dependencies
        queue = [sensor for sensor, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            # Process sensor with no remaining dependencies
            current = queue.pop(0)
            result.append(current)

            # Reduce in-degree for all dependents
            for dependent in dependents[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # Check for circular dependencies
        if len(result) != len(all_sensors):
            remaining = all_sensors - set(result)
            self._logger.error("Circular dependencies detected among sensors: %s", remaining)
            raise ValueError(f"Circular dependencies detected: {remaining}")

        return result

    def validate_references(self, reference_map: dict[str, set[str]], available_sensors: set[str]) -> dict[str, set[str]]:
        """Validate that all referenced sensors exist.

        Args:
            reference_map: Dict mapping sensor_key -> set of referenced sensor keys
            available_sensors: Set of all available sensor keys

        Returns:
            Dict mapping sensor_key -> set of missing referenced sensor keys

        Raises:
            ValueError: If any referenced sensors are missing
        """
        missing_references = {}

        for sensor_key, references in reference_map.items():
            missing = references - available_sensors
            if missing:
                missing_references[sensor_key] = missing

        if missing_references:
            error_msg = f"Missing sensor references: {missing_references}"
            self._logger.error(error_msg)
            raise ValueError(error_msg)

        return missing_references
