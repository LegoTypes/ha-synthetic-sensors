"""Formula preprocessing and collection function resolution."""

import logging
import re

from homeassistant.core import HomeAssistant

from .collection_resolver import CollectionResolver
from .config_models import FormulaConfig, SensorConfig
from .constants_entities import get_ha_entity_domains
from .dependency_parser import DependencyParser, DynamicQuery
from .type_definitions import ContextValue

_LOGGER = logging.getLogger(__name__)


class FormulaPreprocessor:
    """Handles formula preprocessing for evaluation."""

    def __init__(self, collection_resolver: CollectionResolver, hass: HomeAssistant):
        """Initialize the formula preprocessor."""
        if hass is None:
            raise ValueError("FormulaPreprocessor requires a valid Home Assistant instance, got None")
        self._collection_resolver = collection_resolver
        self._dependency_parser = DependencyParser()
        self._hass = hass

    def preprocess_formula_for_evaluation(
        self,
        formula: str,
        eval_context: dict[str, ContextValue] | None = None,
        sensor_config: SensorConfig | None = None,
        formula_config: FormulaConfig | None = None,
        sensor_to_backing_mapping: dict[str, str] | None = None,
    ) -> str:
        """Preprocess formula for evaluation by resolving special tokens and collection functions.

        Args:
            formula: The formula string to preprocess
            eval_context: Evaluation context with resolved variables
            sensor_config: Optional sensor configuration for state token resolution
            formula_config: Optional formula configuration for state token resolution
            sensor_to_backing_mapping: Optional mapping from sensor keys to backing entity IDs

        Returns:
            Preprocessed formula string ready for evaluation
        """
        processed_formula = formula

        # Handle state token resolution
        if "state" in processed_formula and sensor_config:
            processed_formula = self._resolve_state_token(
                processed_formula, sensor_config, formula_config, sensor_to_backing_mapping
            )

        # Handle collection functions
        processed_formula = self._resolve_collection_functions(processed_formula)

        # Convert direct entity references to variable names
        processed_formula = self._convert_entity_references_to_variables(processed_formula)

        return processed_formula

    def _resolve_state_token(
        self,
        formula: str,
        sensor_config: SensorConfig,
        formula_config: FormulaConfig | None = None,
        sensor_to_backing_mapping: dict[str, str] | None = None,
    ) -> str:
        """Resolve state token to backing entity ID or leave as 'state' for attribute formulas or sensors without backing entities."""
        # Check if this is an attribute formula (has underscore in ID and not the main formula)
        is_attribute_formula = formula_config and "_" in formula_config.id and formula_config.id != sensor_config.unique_id

        if is_attribute_formula:
            # For attribute formulas, leave "state" as is - it will be resolved from context
            _LOGGER.debug("Formula preprocessor: Leaving 'state' token for attribute formula")
            return formula

        # For main formulas, check if there's a resolvable backing entity
        sensor_key = sensor_config.unique_id

        # Check if there's a backing entity configured
        has_backing_entity = sensor_config.entity_id is not None or (
            sensor_to_backing_mapping and sensor_key in sensor_to_backing_mapping
        )

        if has_backing_entity:
            # There's a backing entity - but we need to check if the formula contains attribute references
            # If the formula contains "state.attribute", we should leave "state" as is
            # and let the variable resolver handle the attribute access
            if "." in formula and "state." in formula:
                # Formula contains attribute references - leave "state" as is
                _LOGGER.debug("Formula preprocessor: Leaving 'state' token for attribute references")
                return formula

            # No attribute references - resolve state token to backing entity ID
            if sensor_to_backing_mapping and sensor_key in sensor_to_backing_mapping:
                backing_entity_id = sensor_to_backing_mapping[sensor_key]
            else:
                # Fallback to the old behavior for backward compatibility
                backing_entity_id = f"sensor.{sensor_key}_backing"

            _LOGGER.debug("Formula preprocessor: Converting 'state' to backing entity '%s'", backing_entity_id)
            return formula.replace("state", backing_entity_id)

        # No backing entity - leave "state" as is (refers to sensor's pre-evaluation state)
        _LOGGER.debug("Formula preprocessor: Leaving 'state' token for sensor without backing entity")
        return formula

    def _convert_entity_references_to_variables(self, formula: str) -> str:
        """Convert direct entity references in formulas to variable names.

        Args:
            formula: Formula string that may contain direct entity references

        Returns:
            Formula with entity references converted to variable names
        """
        # Pattern to match entity references like sensor.temperature, binary_sensor.door, etc.
        # But NOT attribute references like state.voltage (which should be handled by variable resolver)
        entity_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z0-9_.]+)\b")

        def replace_entity_ref(match: re.Match[str]) -> str:
            """Replace entity reference with variable name."""
            entity_id = match.group(1)

            # Skip attribute references (they should be handled by variable resolver)
            # Attribute references are typically in the form "base.attribute" where base is a simple name
            if "." in entity_id:
                parts = entity_id.split(".", 1)
                base = parts[0]
                # Get HA entity domain prefixes from registry - these should be converted to variables
                known_domains = get_ha_entity_domains(self._hass)
                # If base is NOT a known HA domain, it's likely an attribute reference
                if base not in known_domains:
                    # This looks like an attribute reference, don't convert it
                    return entity_id

            # Convert entity_id to variable name (replace dots and dashes with underscores)
            var_name = entity_id.replace(".", "_").replace("-", "_")
            return var_name

        return entity_pattern.sub(replace_entity_ref, formula)

    def _normalize_formula_patterns(self, formula: str) -> str:
        """Normalize collection function patterns in the formula to handle repeated prefixes.

        This converts patterns like:
        count(device_class:door|device_class:window|device_class:motion)
        to:
        count(device_class:door|window|motion)

        Args:
            formula: Original formula string

        Returns:
            Formula with normalized patterns
        """
        # Pattern to match collection functions with repeated prefixes
        # Matches: function(prefix:value1|prefix:value2|prefix:value3...)
        pattern = re.compile(
            r"\b(sum|avg|count|min|max|std|var)\s*\(\s*"
            r"([a-zA-Z_]+):"  # First prefix (e.g., "device_class:")
            r"([^)]+)"  # Everything until the closing paren
            r"\)",
            re.IGNORECASE,
        )

        def normalize_match(match: re.Match[str]) -> str:
            function = match.group(1)
            prefix = match.group(2)
            content = match.group(3)

            # Split by pipe and normalize each part
            parts = content.split("|")
            normalized_parts = []

            for part in parts:
                part = part.strip()
                # Check if this part has the same prefix
                if part.startswith(f"{prefix}:"):
                    # Remove the prefix, keeping only the value
                    normalized_part = part[len(prefix) + 1 :].strip()
                    normalized_parts.append(normalized_part)
                else:
                    # No prefix or different prefix, keep as is
                    normalized_parts.append(part)

            # Reconstruct the function call with normalized pattern
            normalized_content = "|".join(normalized_parts)
            return f"{function}({prefix}:{normalized_content})"

        return pattern.sub(normalize_match, formula)

    def _resolve_collection_functions(self, formula: str, exclude_entity_ids: set[str] | None = None) -> str:
        """Resolve collection functions in the formula.

        Args:
            formula: Formula string to process
            exclude_entity_ids: Optional set of entity IDs to exclude from collection results

        Returns:
            Formula with collection functions resolved
        """
        try:
            # First normalize the formula to handle repeated prefixes
            normalized_formula = self._normalize_formula_patterns(formula)

            # Extract dynamic queries from the normalized formula using the dependency parser
            dynamic_queries = self._dependency_parser.extract_dynamic_queries(normalized_formula)

            if not dynamic_queries:
                return normalized_formula  # No collection functions to resolve

            resolved_formula = normalized_formula

            for query in dynamic_queries:
                resolved_formula = self._resolve_single_collection_query(resolved_formula, query, exclude_entity_ids)

            return resolved_formula

        except Exception as e:
            _LOGGER.error("Error resolving collection functions in formula '%s': %s", formula, e)
            return formula  # Return original formula if resolution fails

    def _resolve_single_collection_query(
        self, formula: str, query: DynamicQuery, exclude_entity_ids: set[str] | None = None
    ) -> str:
        """Resolve a single collection query and replace it in the formula.

        Args:
            formula: Formula string
            query: Collection query object
            exclude_entity_ids: Optional set of entity IDs to exclude from collection results

        Returns:
            Formula with query replaced by result
        """
        try:
            # Resolve the collection
            result = self._collection_resolver.resolve_collection(query, exclude_entity_ids)
            if result is None:
                return self._replace_with_default_value(formula, query, "No entities found")

            # Get numeric values for the entities
            values = self._collection_resolver.get_entity_values(result)

            if not values:
                return self._replace_with_default_value(formula, query, "No numeric values found")

            # Calculate the result based on the function
            calculated_result = self._calculate_collection_result(query.function, values)

            # Replace the pattern in the formula
            return self._replace_collection_pattern(formula, query, str(calculated_result))

        except Exception as e:
            _LOGGER.warning("Failed to resolve collection query %s:%s: %s", query.query_type, query.pattern, e)
            return self._replace_with_default_value(formula, query, f"Resolution error: {e}")

    def _replace_with_default_value(self, formula: str, query: DynamicQuery, reason: str) -> str:
        """Replace a collection pattern with a default value when resolution fails.

        Args:
            formula: Formula string
            query: Query object
            reason: Reason for replacement

        Returns:
            Formula with pattern replaced by default value
        """
        # Build a regex pattern that matches the function call with optional exclusions
        escaped_function = re.escape(query.function)
        escaped_query_type = re.escape(query.query_type)
        escaped_pattern = re.escape(query.pattern)

        # Create regex pattern that matches the function call with optional exclusions
        regex_pattern = (
            rf"\b{escaped_function}\s*\(\s*"
            rf"(?:['\"]?{escaped_query_type}:\s*{escaped_pattern}['\"]?)"
            rf"(?:\s+!\s*\([^)]+\)|(?:\s+![^)]+))?"  # Optional exclusions
            rf"\s*\)"
        )

        # Try to replace using regex
        if re.search(regex_pattern, formula):
            return re.sub(regex_pattern, "0", formula)

        # Fallback to exact pattern matching (original behavior)
        patterns_to_try = [
            f"{query.function}('{query.query_type}: {query.pattern}')",
            f'{query.function}("{query.query_type}: {query.pattern}")',
            f"{query.function}('{query.query_type}:{query.pattern}')",
            f'{query.function}("{query.query_type}:{query.pattern}")',
            f"{query.function}({query.query_type}: {query.pattern})",  # Unquoted with space
            f"{query.function}({query.query_type}:{query.pattern})",  # Unquoted without space
        ]

        # Replace with 0 as default value (as specified in README)
        for pattern in patterns_to_try:
            if pattern in formula:
                return formula.replace(pattern, "0")

        _LOGGER.warning("Could not find pattern to replace for %s:%s: %s", query.query_type, query.pattern, reason)
        return formula

    def _calculate_collection_result(self, function: str, values: list[float]) -> float | int:
        """Calculate the result of a collection function.

        Args:
            function: Function name (sum, count, avg, etc.)
            values: List of numeric values

        Returns:
            Calculated result
        """
        if not values:
            return 0

        # Try basic arithmetic functions first
        basic_result = self._try_basic_arithmetic(function, values)
        if basic_result is not None:
            return basic_result

        # Try statistical functions
        statistical_result = self._try_statistical_functions(function, values)
        if statistical_result is not None:
            return statistical_result

        # Default to sum for unknown functions
        _LOGGER.warning("Unknown collection function: %s, defaulting to sum", function)
        return sum(values)

    def _try_basic_arithmetic(self, function: str, values: list[float]) -> float | int | None:
        """Try to calculate basic arithmetic functions.

        Args:
            function: Function name
            values: List of numeric values

        Returns:
            Calculated result or None if function not handled
        """
        if function == "sum":
            return sum(values)
        if function == "count":
            return len(values)
        if function == "max":
            return max(values) if values else 0
        if function == "min":
            return min(values) if values else 0
        if function in ("avg", "average", "mean"):
            return sum(values) / len(values) if values else 0

        return None

    def _try_statistical_functions(self, function: str, values: list[float]) -> float | None:
        """Try to calculate statistical functions.

        Args:
            function: Function name
            values: List of numeric values

        Returns:
            Calculated result or None if function not handled
        """
        if function in ("std", "var"):
            return self._calculate_statistical_function(function, values)

        return None

    def _calculate_statistical_function(self, function: str, values: list[float]) -> float:
        """Calculate statistical functions (std, var).

        Args:
            function: Statistical function name
            values: List of numeric values

        Returns:
            Calculated statistical result
        """
        if len(values) <= 1:
            return 0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)

        if function == "var":
            return float(variance)
        if function == "std":
            return float(variance**0.5)

        return 0  # Fallback

    def _replace_collection_pattern(self, formula: str, query: DynamicQuery, replacement: str) -> str:
        """Replace collection pattern in formula with replacement value.

        Args:
            formula: Current formula string
            query: DynamicQuery object
            replacement: Value to replace the pattern with

        Returns:
            Formula with pattern replaced
        """
        # Build a regex pattern that matches the function call with optional exclusions
        # This handles patterns like:
        # - count(device_class:door|window|motion)
        # - count(device_class:door|window|motion !(state:unavailable|unknown|off))
        # - count(device_class:door|window|motion !state:unavailable|unknown|off)

        escaped_function = re.escape(query.function)
        escaped_query_type = re.escape(query.query_type)
        escaped_pattern = re.escape(query.pattern)

        # Create regex pattern that matches the function call with optional exclusions
        regex_pattern = (
            rf"\b{escaped_function}\s*\(\s*"
            rf"(?:['\"]?{escaped_query_type}:\s*{escaped_pattern}['\"]?)"
            rf"(?:\s+!\s*\([^)]+\)|(?:\s+![^)]+))?"  # Optional exclusions
            rf"\s*\)"
        )

        # Try to replace using regex
        if re.search(regex_pattern, formula):
            return re.sub(regex_pattern, replacement, formula)

        # Fallback to exact pattern matching (original behavior)
        patterns_to_try = [
            f"{query.function}('{query.query_type}: {query.pattern}')",
            f'{query.function}("{query.query_type}: {query.pattern}")',
            f"{query.function}('{query.query_type}:{query.pattern}')",
            f'{query.function}("{query.query_type}:{query.pattern}")',
            f"{query.function}({query.query_type}: {query.pattern})",  # Unquoted with space
            f"{query.function}({query.query_type}:{query.pattern})",  # Unquoted without space
        ]

        # Replace whichever pattern exists in the formula
        for pattern in patterns_to_try:
            if pattern in formula:
                return formula.replace(pattern, replacement)

        _LOGGER.warning("Could not find pattern to replace for %s:%s", query.query_type, query.pattern)
        return formula
