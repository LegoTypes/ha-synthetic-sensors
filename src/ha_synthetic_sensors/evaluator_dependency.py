"""Dependency management functionality for formula evaluation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .collection_resolver import CollectionResolver
from .dependency_parser import DependencyParser
from .exceptions import DataValidationError
from .variable_resolver import HomeAssistantResolutionStrategy

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, State

    from .config_models import FormulaConfig
    from .type_definitions import ContextValue, DataProviderCallback, DependencyValidation

_LOGGER = logging.getLogger(__name__)


class EvaluatorDependency:
    """Handles dependency parsing, validation, and resolution for formula evaluation."""

    def __init__(self, hass: HomeAssistant, data_provider_callback: DataProviderCallback | None = None) -> None:
        """Initialize dependency manager.

        Args:
            hass: Home Assistant instance
            data_provider_callback: Optional callback for getting data directly from integrations
        """
        self._hass = hass
        self._dependency_parser = DependencyParser()
        self._collection_resolver = CollectionResolver(hass)
        self._data_provider_callback = data_provider_callback
        self._registered_integration_entities: set[str] | None = None

    def update_integration_entities(self, entity_ids: set[str]) -> None:
        """Update the set of entities that the integration can provide (push-based pattern).

        Args:
            entity_ids: Set of entity IDs that the integration can provide data for
        """
        self._registered_integration_entities = entity_ids.copy()
        _LOGGER.debug("Updated integration entities: %d entities", len(entity_ids))

    def get_integration_entities(self) -> set[str]:
        """Get the current set of integration entities using the push-based pattern.

        Returns:
            Set of entity IDs that the integration can provide data for
        """
        if self._registered_integration_entities is not None:
            return self._registered_integration_entities.copy()
        return set()

    @property
    def data_provider_callback(self) -> DataProviderCallback | None:
        """Get the data provider callback."""
        return self._data_provider_callback

    @data_provider_callback.setter
    def data_provider_callback(self, value: DataProviderCallback | None) -> None:
        """Set the data provider callback."""
        self._data_provider_callback = value

    def get_formula_dependencies(self, formula: str) -> set[str]:
        """Get all dependencies for a formula (entities and variables).

        Args:
            formula: Formula string to analyze

        Returns:
            Set of entity IDs and variable names that the formula depends on
        """
        # Use the comprehensive dependency extraction method
        return self._dependency_parser.extract_dependencies(formula)

    def extract_formula_dependencies(self, config: FormulaConfig, context: dict[str, ContextValue] | None = None) -> set[str]:
        """Extract dependencies from a formula configuration, handling collection patterns.

        Args:
            config: Formula configuration
            context: Optional context for variable resolution

        Returns:
            Set of entity IDs that the formula depends on (excluding config variables)
        """
        dependencies = set()

        # Extract entity references from variables (for backward compatibility)
        if config.variables:
            for _, var_value in config.variables.items():
                if isinstance(var_value, str) and var_value.startswith(
                    ("sensor.", "binary_sensor.", "input_", "switch.", "light.", "climate.")
                ):
                    dependencies.add(var_value)

        # Extract entity references from collection patterns
        parsed_deps = self._dependency_parser.parse_formula_dependencies(config.formula, {})

        for query in parsed_deps.dynamic_queries:
            # Look for entity references within the pattern using collection resolver's pattern
            entity_refs = self._collection_resolver.entity_reference_pattern.findall(query.pattern)
            dependencies.update(entity_refs)

        # Extract regular dependencies (non-collection function entities)
        static_deps = self._dependency_parser.extract_entity_references(config.formula)
        dependencies.update(static_deps)

        return dependencies

    def extract_and_prepare_dependencies(
        self, config: FormulaConfig, context: dict[str, ContextValue] | None
    ) -> tuple[set[str], set[str]]:
        """Extract dependencies and identify collection pattern entities.

        Args:
            config: Formula configuration
            context: Optional context for variable resolution

        Returns:
            Tuple of (dependencies, collection_pattern_entities)
        """
        dependencies = self.extract_formula_dependencies(config, context)

        # Identify collection pattern entities that don't need numeric validation
        parsed_deps = self._dependency_parser.parse_formula_dependencies(config.formula, {})
        collection_pattern_entities = set()
        for query in parsed_deps.dynamic_queries:
            entity_refs = self._collection_resolver.entity_reference_pattern.findall(query.pattern)
            collection_pattern_entities.update(entity_refs)

        return dependencies, collection_pattern_entities

    def check_dependencies(
        self,
        dependencies: set[str],
        context: dict[str, ContextValue] | None = None,
        collection_pattern_entities: set[str] | None = None,
    ) -> tuple[set[str], set[str], set[str]]:
        """Check dependency availability and categorize issues.

        Args:
            dependencies: Set of entity IDs to check
            context: Optional context with pre-resolved values
            collection_pattern_entities: Entities from collection patterns (less strict validation)

        Returns:
            Tuple of (missing_dependencies, unavailable_dependencies, unknown_dependencies)
        """
        missing_deps = set()
        unavailable_deps = set()
        unknown_deps = set()
        collection_pattern_entities = collection_pattern_entities or set()

        for entity_id in dependencies:
            # Skip if already resolved in context
            if context and entity_id in context:
                continue

            status = self.check_single_entity_dependency(entity_id, collection_pattern_entities)

            if status == "missing":
                missing_deps.add(entity_id)
            elif status == "unavailable":
                unavailable_deps.add(entity_id)
            elif status == "unknown":
                unknown_deps.add(entity_id)
            # "ok" status means entity is available

        return missing_deps, unavailable_deps, unknown_deps

    def check_single_entity_dependency(self, entity_id: str, collection_pattern_entities: set[str]) -> str:
        """Check the status of a single entity dependency.

        Args:
            entity_id: Entity ID to check
            collection_pattern_entities: Entities from collection patterns

        Returns:
            Status: "ok", "missing", or "unavailable"
        """
        # Check data provider first if available
        if self._should_use_data_provider(entity_id):
            return self._check_data_provider_entity(entity_id)

        # Check Home Assistant entity
        return self._check_home_assistant_entity(entity_id, collection_pattern_entities)

    def validate_dependencies(self, dependencies: set[str]) -> DependencyValidation:
        """Validate dependencies and return validation result."""
        missing_entities = []
        unavailable_entities = []

        for entity_id in dependencies:
            status = self.check_single_entity_dependency(entity_id, set())
            if status == "missing":
                missing_entities.append(entity_id)
            elif status == "unavailable":
                unavailable_entities.append(entity_id)

        # Build issues dict with entity_id -> issue_type mapping
        issues = {}
        for entity_id in missing_entities:
            issues[entity_id] = "missing"
        for entity_id in unavailable_entities:
            issues[entity_id] = "unavailable"

        return {
            "is_valid": len(missing_entities) == 0 and len(unavailable_entities) == 0,
            "issues": issues,
            "missing_entities": missing_entities,
            "unavailable_entities": unavailable_entities,
        }

    def _build_context_dict(self, context: dict[str, ContextValue] | None, config: FormulaConfig) -> dict[str, Any]:
        """Build context dictionary for dependency parsing."""
        context_dict = {}

        # Add context variables
        if context:
            for key, value in context.items():
                if isinstance(value, (str, int, float, bool)):
                    context_dict[key] = value

        # Add config variables
        if config.variables:
            context_dict.update(config.variables)

        return context_dict

    def _should_use_data_provider(self, entity_id: str) -> bool:
        """Check if we should use the data provider for this entity."""
        if not self._data_provider_callback:
            return False

        # Use push-based pattern if available
        if self._registered_integration_entities is not None:
            return entity_id in self._registered_integration_entities

        # Fallback: assume data provider can handle any entity
        return True

    def _check_data_provider_entity(self, entity_id: str) -> str:
        """Check entity status using data provider callback.

        Args:
            entity_id: Entity ID to check

        Returns:
            Status: "ok", "missing", "unavailable", or "unknown"

        Raises:
            DataValidationError: For fatal data provider errors (None return, invalid values)
        """
        try:
            if not self._data_provider_callback:
                return "missing"

            result = self._data_provider_callback(entity_id)

            # Data provider returning None is a fatal implementation error
            if result is None:
                raise DataValidationError(f"Data provider callback returned None for {entity_id} - fatal implementation error")

            if not result["exists"]:
                return "missing"

            # Validate the value - this will raise DataValidationError for fatal cases (None, unsupported types)
            self._validate_data_provider_value(entity_id, result["value"])

            # Check for operational state strings that should be handled gracefully
            if isinstance(result["value"], str):
                value_lower = result["value"].lower()
                if value_lower == "unavailable":
                    return "unavailable"
                if value_lower == "unknown":
                    return "unknown"

            return "ok"

        except Exception as e:
            # If it's already a DataValidationError, re-raise it
            if isinstance(e, Exception) and e.__class__.__name__ == "DataValidationError":
                raise
            _LOGGER.debug("Data provider check failed for %s: %s", entity_id, e)
            return "unavailable"

    def _validate_data_provider_value(self, entity_id: str, value: Any) -> None:
        """Validate value from data provider.

        Args:
            entity_id: Entity ID
            value: Value to validate

        Raises:
            DataValidationError: If value is invalid (fatal error)
        """
        if value is None:
            # None values from data providers are always fatal - integrations should use "unknown"
            raise DataValidationError(f"Data provider returned None state value for {entity_id} - fatal error")

        # Allow numeric values, strings, and booleans (including "unknown", "unavailable" strings)
        if not isinstance(value, (int, float, str, bool)):
            raise DataValidationError(f"Data provider returned unsupported type {type(value)} for {entity_id} - fatal error")

    def _check_home_assistant_entity(self, entity_id: str, collection_pattern_entities: set[str]) -> str:
        """Check entity status in Home Assistant.

        Args:
            entity_id: Entity ID to check
            collection_pattern_entities: Entities from collection patterns

        Returns:
            Status: "ok", "missing", or "unavailable"
        """
        state = self._hass.states.get(entity_id)

        if state is None:
            return "missing"

        # Check if entity is available for evaluation
        return self._check_entity_numeric_availability(state)

    def _check_entity_numeric_availability(self, state: State) -> str:
        """Check if entity state is available for numeric evaluation.

        Args:
            state: Entity state

        Returns:
            Status: "ok", "missing" (truly fatal), "unavailable" (reflects to synthetic), or "unknown" (reflects to synthetic)
        """
        # Handle None states (startup race conditions) - should reflect as unavailable
        if state.state is None:
            return "unavailable"

        # Handle unavailable states - should reflect as unavailable
        if str(state.state).lower() == "unavailable":
            return "unavailable"

        # Handle unknown states - should reflect as unknown
        if str(state.state).lower() == "unknown":
            return "unknown"

        # Try to convert to numeric or boolean-like states
        try:
            # This will handle numeric values and boolean conversions per our variable resolver
            strategy = HomeAssistantResolutionStrategy(self._hass)
            strategy.get_numeric_state(state)
            return "ok"
        except Exception:
            # Truly non-numeric states that can't be converted - truly fatal (config error)
            return "missing"
