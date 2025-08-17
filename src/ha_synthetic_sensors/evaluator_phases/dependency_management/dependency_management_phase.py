"""Dependency management phase for compiler-like formula evaluation."""

import logging
from typing import Any

from ...config_models import FormulaConfig, SensorConfig
from ...constants_evaluation_results import (
    RESULT_KEY_ERROR,
    RESULT_KEY_MISSING_DEPENDENCIES,
    RESULT_KEY_STATE,
    RESULT_KEY_UNAVAILABLE_DEPENDENCIES,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from ...exceptions import MissingDependencyError
from ...type_definitions import ContextValue
from .manager_factory import DependencyManagerFactory

_LOGGER = logging.getLogger(__name__)


class DependencyManagementPhase:
    """Dependency management phase for compiler-like formula evaluation.

    This phase handles the complete analysis, validation, and management of formula dependencies,
    following the compiler-like approach described in the state and entity reference guide.

    PHASE 2: Dependency Analysis and Validation
    - Extract dependencies from formulas
    - Validate dependency availability
    - Detect circular references
    - Handle missing, unavailable, and unknown dependencies
    """

    def __init__(self) -> None:
        """Initialize the dependency management phase."""
        self._manager_factory = DependencyManagerFactory()
        self._dependency_handler = None
        self._sensor_to_backing_mapping: dict[str, str] = {}
        self._sensor_registry_phase = None

    def set_evaluator_dependencies(self, dependency_handler: Any, sensor_to_backing_mapping: dict[str, str]) -> None:
        """Set evaluator dependencies for dependency management processing."""
        self._dependency_handler = dependency_handler
        self._sensor_to_backing_mapping = sensor_to_backing_mapping
        self._setup_cross_sensor_dependency_manager()

    def set_sensor_registry_phase(self, sensor_registry_phase: Any) -> None:
        """Set the sensor registry phase for cross-sensor dependency management."""
        self._sensor_registry_phase = sensor_registry_phase
        self._setup_cross_sensor_dependency_manager()

    def _setup_cross_sensor_dependency_manager(self) -> None:
        """Setup the cross-sensor dependency manager with required dependencies."""
        if self._sensor_registry_phase:
            # Find and configure the cross-sensor dependency manager
            for manager in self._manager_factory.get_all_managers():
                if manager.get_manager_name() == "CrossSensorDependencyManager":
                    manager.set_sensor_registry_phase(self._sensor_registry_phase)
                    _LOGGER.debug("Configured CrossSensorDependencyManager with sensor registry phase")
                    break

    def extract_and_prepare_dependencies(
        self, config: FormulaConfig, context: dict[str, ContextValue] | None, sensor_config: SensorConfig | None = None
    ) -> tuple[set[str], set[str]]:
        """Extract dependencies and prepare them for evaluation."""
        # Extract dependencies with state token resolution
        dependencies = self._extract_formula_dependencies(config, context, sensor_config)

        # Get collection pattern entities from dependency handler
        collection_pattern_entities = self._extract_collection_pattern_entities(config, context, sensor_config)

        return dependencies, collection_pattern_entities

    def handle_dependency_issues(
        self, missing_deps: set[str], unavailable_deps: set[str], unknown_deps: set[str], formula_name: str
    ) -> Any | None:
        """Handle missing, unavailable, and unknown dependencies with state reflection."""
        # Only missing dependencies are truly fatal
        if missing_deps:
            return self._handle_missing_dependencies(missing_deps, formula_name)

        # Handle non-fatal dependencies with state reflection
        # Priority: unavailable > unknown (unavailable is worse)
        if unavailable_deps or unknown_deps:
            all_problematic_deps = list(unavailable_deps) + list(unknown_deps)

            if unavailable_deps:
                # If any dependencies are unavailable, reflect unavailable state
                return self._create_unavailable_result(all_problematic_deps)

            # Only unknown dependencies
            return self._create_unknown_result(all_problematic_deps)

        return None

    def validate_evaluation_context(self, eval_context: dict[str, ContextValue], formula_name: str) -> Any | None:
        """Validate that evaluation context has all required variables."""
        try:
            # Allow None values to pass through to formula evaluation where alternate handlers can handle them
            none_variables = [var for var, value in eval_context.items() if value is None]
            if none_variables:
                error_msg = f"Variables with None values: {', '.join(none_variables)}"
                _LOGGER.warning(
                    "Formula '%s': %s - allowing to pass through for alternate handler processing", formula_name, error_msg
                )
            return None
        except Exception as err:
            _LOGGER.error("Formula '%s': Context validation error: %s", formula_name, err)
            return self._create_error_result(f"Context validation error: {err}", "unavailable")

    def _extract_formula_dependencies(
        self, config: FormulaConfig, context: dict[str, ContextValue] | None, sensor_config: SensorConfig | None = None
    ) -> set[str]:
        """Extract dependencies from formula config, handling entity references in collection patterns and state tokens."""
        # Use the manager factory to extract dependencies
        dependencies_result = self._manager_factory.manage_dependency(
            "extract", config=config, context=context, sensor_config=sensor_config
        )

        if dependencies_result is None or not isinstance(dependencies_result, set):
            return set()

        dependencies: set[str] = dependencies_result

        # Handle state token if sensor configuration is available
        if sensor_config and "state" in dependencies:
            # Check if this is an attribute formula (has underscore in ID and not the main formula)
            is_attribute_formula = "_" in config.id and config.id != sensor_config.unique_id

            _LOGGER.debug(
                "Dependency management: Formula '%s' (ID: %s) has state token. Is attribute: %s",
                config.formula,
                config.id,
                is_attribute_formula,
            )

            if not is_attribute_formula:
                # Main formula: handle state token based on whether there's a backing entity
                dependencies.discard("state")

                # Look up the backing entity ID using the sensor key
                backing_entity_id = self._get_backing_entity_id(sensor_config.unique_id)

                if backing_entity_id:
                    # This sensor has a backing entity - replace state token with backing entity
                    dependencies.add(backing_entity_id)
                    _LOGGER.debug("Dependency management: Replaced 'state' with backing entity '%s'", backing_entity_id)
                else:
                    # No backing entity mapping - this is a self-reference/recursive calculation
                    # Keep state as a dependency - it will be resolved from context (previous value)
                    dependencies.add("state")
                    _LOGGER.debug("Dependency management: Kept 'state' as dependency for self-reference (no backing entity)")
            else:
                # Attribute formula: state token will be provided by context, so remove it from dependencies
                # This prevents it from being treated as a missing dependency
                dependencies.discard("state")
                _LOGGER.debug("Dependency management: Removed 'state' dependency for attribute formula")

        return dependencies

    def _extract_collection_pattern_entities(
        self, config: FormulaConfig, context: dict[str, ContextValue] | None, sensor_config: SensorConfig | None = None
    ) -> set[str]:
        """Extract collection pattern entities from the formula."""
        # Use the manager factory to extract collection pattern entities
        collection_entities_result = self._manager_factory.manage_dependency(
            "collection_patterns", config=config, context=context, sensor_config=sensor_config
        )

        if collection_entities_result is None or not isinstance(collection_entities_result, set):
            return set()

        return collection_entities_result  # type: ignore[no-any-return]

    def _handle_missing_dependencies(self, missing_deps: set[str], formula_name: str) -> Any:
        """Handle missing dependencies (fatal error)."""
        error_msg = f"Missing dependencies: {', '.join(sorted(missing_deps))}"
        raise MissingDependencyError(f"Formula '{formula_name}': {error_msg}")

    def _get_backing_entity_id(self, sensor_unique_id: str) -> str | None:
        """Get the backing entity ID for a sensor from the evaluator's mapping."""
        return self._sensor_to_backing_mapping.get(sensor_unique_id)

    def _create_error_result(self, error_msg: str, state: str, missing_dependencies: list[str] | None = None) -> dict[str, Any]:
        """Create an error result (placeholder for integration)."""
        # This will be implemented when we integrate with the evaluator
        return {
            RESULT_KEY_ERROR: error_msg,
            RESULT_KEY_STATE: state,
            RESULT_KEY_MISSING_DEPENDENCIES: missing_dependencies or [],
        }

    def _create_unavailable_result(self, unavailable_dependencies: list[str]) -> dict[str, Any]:
        """Create an unavailable result (placeholder for integration)."""
        # This will be implemented when we integrate with the evaluator
        return {RESULT_KEY_STATE: STATE_UNAVAILABLE, RESULT_KEY_UNAVAILABLE_DEPENDENCIES: unavailable_dependencies}

    def _create_unknown_result(self, unknown_dependencies: list[str]) -> dict[str, Any]:
        """Create an unknown result (placeholder for integration)."""
        # This will be implemented when we integrate with the evaluator
        return {RESULT_KEY_STATE: STATE_UNKNOWN, RESULT_KEY_UNAVAILABLE_DEPENDENCIES: unknown_dependencies}

    def analyze_cross_sensor_dependencies(self, sensors: list[SensorConfig]) -> dict[str, set[str]]:
        """Analyze cross-sensor dependencies for a list of sensors.

        Args:
            sensors: List of sensor configurations to analyze

        Returns:
            Dictionary mapping sensor names to sets of their cross-sensor dependencies
        """
        if not self._sensor_registry_phase:
            _LOGGER.warning("Cannot analyze cross-sensor dependencies: sensor registry phase not available")
            return {}

        context = {
            "sensors": sensors,
            "sensor_registry": self._sensor_registry_phase.get_sensor_registry(),
        }

        result = self._manager_factory.manage_dependency("cross_sensor_analysis", context)

        if result is None or not isinstance(result, dict):
            return {}

        return result

    def get_cross_sensor_evaluation_order(self, sensor_dependencies: dict[str, set[str]]) -> list[str]:
        """Get evaluation order for sensors considering cross-sensor dependencies.

        Args:
            sensor_dependencies: Dictionary mapping sensor names to their dependencies

        Returns:
            List of sensor names in evaluation order
        """
        context = {
            "sensor_dependencies": sensor_dependencies,
            "sensor_registry": self._sensor_registry_phase.get_sensor_registry() if self._sensor_registry_phase else {},
        }

        result = self._manager_factory.manage_dependency("evaluation_order", context)

        if result is None or not isinstance(result, list):
            return []

        return result  # type: ignore[no-any-return]

    def detect_cross_sensor_circular_references(self, sensor_dependencies: dict[str, set[str]]) -> list[str]:
        """Detect circular references in cross-sensor dependencies.

        Args:
            sensor_dependencies: Dictionary mapping sensor names to their dependencies

            Returns:
            List of sensor names involved in circular references
        """
        context = {
            "sensor_dependencies": sensor_dependencies,
            "sensor_registry": self._sensor_registry_phase.get_sensor_registry() if self._sensor_registry_phase else {},
        }

        result = self._manager_factory.manage_dependency("cross_sensor_circular_detection", context)

        if result is None or not isinstance(result, list):
            return []

        return result  # type: ignore[no-any-return]

    def validate_cross_sensor_dependencies(self, sensor_dependencies: dict[str, set[str]]) -> dict[str, Any]:
        """Validate cross-sensor dependencies.

        Args:
            sensor_dependencies: Dictionary mapping sensor names to their dependencies

        Returns:
            Validation result with status and any issues found
        """
        context = {
            "sensor_dependencies": sensor_dependencies,
            "sensor_registry": self._sensor_registry_phase.get_sensor_registry() if self._sensor_registry_phase else {},
        }

        result = self._manager_factory.manage_dependency("validate_cross_sensor_deps", context)

        if result is None or not isinstance(result, dict):
            return {"valid": False, "issues": ["Validation failed"], "evaluation_order": [], "circular_references": []}

        return result  # type: ignore[no-any-return]
