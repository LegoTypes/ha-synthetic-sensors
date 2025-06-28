"""Exception classes for ha-synthetic-sensors package.

This module defines exception classes that align with Home Assistant's
coordinator and integration patterns, similar to how other integrations
like Span Panel handle exceptions.
"""

from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError, ConfigEntryNotReady, HomeAssistantError


class SyntheticSensorsError(HomeAssistantError):
    """Base exception for all synthetic sensors errors."""


class SyntheticSensorsConfigError(ConfigEntryError):
    """Configuration-related errors that prevent setup."""


class SyntheticSensorsNotReadyError(ConfigEntryNotReady):
    """Integration not ready for operation."""


class SyntheticSensorsAuthError(ConfigEntryAuthFailed):
    """Authentication-related errors (if applicable for future features)."""


class DataValidationError(SyntheticSensorsError):
    """Fatal data validation error - indicates bad data that cannot be processed."""


# Formula evaluation errors
class FormulaEvaluationError(SyntheticSensorsError):
    """Base class for formula evaluation errors."""


class FormulaSyntaxError(FormulaEvaluationError):
    """Formula has invalid syntax."""

    def __init__(self, formula: str, details: str):
        self.formula = formula
        self.details = details
        super().__init__(f"Formula syntax error in '{formula}': {details}")


class DependencyError(FormulaEvaluationError):
    """Base class for dependency-related errors."""


class MissingDependencyError(DependencyError):
    """Required entity or variable is missing."""

    def __init__(self, dependency: str, formula_name: str | None = None):
        self.dependency = dependency
        self.formula_name = formula_name
        if formula_name:
            super().__init__(f"Missing dependency '{dependency}' in formula '{formula_name}'")
        else:
            super().__init__(f"Missing dependency '{dependency}'")


class UnavailableDependencyError(DependencyError):
    """Required entity is unavailable (temporary condition)."""

    def __init__(self, dependency: str, formula_name: str | None = None):
        self.dependency = dependency
        self.formula_name = formula_name
        if formula_name:
            super().__init__(f"Unavailable dependency '{dependency}' in formula '{formula_name}'")
        else:
            super().__init__(f"Unavailable dependency '{dependency}'")


class NonNumericStateError(DependencyError):
    """Entity state cannot be converted to numeric value."""

    def __init__(self, entity_id: str, state_value: str):
        self.entity_id = entity_id
        self.state_value = state_value
        super().__init__(f"Entity '{entity_id}' has non-numeric state '{state_value}'")


class CircularDependencyError(FormulaEvaluationError):
    """Circular dependency detected in formula chain."""

    def __init__(self, dependency_chain: list[str]):
        self.dependency_chain = dependency_chain
        chain_str = " -> ".join(dependency_chain)
        super().__init__(f"Circular dependency detected: {chain_str}")


# Collection and aggregation errors
class CollectionError(SyntheticSensorsError):
    """Base class for collection function errors."""


class InvalidCollectionPatternError(CollectionError):
    """Collection pattern is invalid or malformed."""

    def __init__(self, pattern: str, details: str):
        self.pattern = pattern
        self.details = details
        super().__init__(f"Invalid collection pattern '{pattern}': {details}")


class EmptyCollectionError(CollectionError):
    """Collection function returned no entities."""

    def __init__(self, pattern: str):
        self.pattern = pattern
        super().__init__(f"Collection pattern '{pattern}' matched no entities")


# Sensor management errors
class SensorManagementError(SyntheticSensorsError):
    """Base class for sensor management errors."""


class SensorConfigurationError(SensorManagementError):
    """Sensor configuration is invalid."""

    def __init__(self, sensor_name: str, details: str):
        self.sensor_name = sensor_name
        self.details = details
        super().__init__(f"Sensor '{sensor_name}' configuration error: {details}")


class SensorCreationError(SensorManagementError):
    """Failed to create sensor entity."""

    def __init__(self, sensor_name: str, details: str):
        self.sensor_name = sensor_name
        self.details = details
        super().__init__(f"Failed to create sensor '{sensor_name}': {details}")


class SensorUpdateError(SensorManagementError):
    """Failed to update sensor state."""

    def __init__(self, sensor_name: str, details: str):
        self.sensor_name = sensor_name
        self.details = details
        super().__init__(f"Failed to update sensor '{sensor_name}': {details}")


# Integration lifecycle errors
class IntegrationError(SyntheticSensorsError):
    """Base class for integration lifecycle errors."""


class IntegrationNotInitializedError(IntegrationError):
    """Integration has not been properly initialized."""

    def __init__(self, component: str | None = None):
        if component:
            super().__init__(f"Integration component '{component}' not initialized")
        else:
            super().__init__("Integration not initialized")


class IntegrationSetupError(IntegrationError):
    """Failed to set up integration."""

    def __init__(self, details: str):
        self.details = details
        super().__init__(f"Integration setup failed: {details}")


class IntegrationTeardownError(IntegrationError):
    """Failed to tear down integration."""

    def __init__(self, details: str):
        self.details = details
        super().__init__(f"Integration teardown failed: {details}")


# Cache and performance errors
class CacheError(SyntheticSensorsError):
    """Base class for cache-related errors."""


class CacheInvalidationError(CacheError):
    """Failed to invalidate cache."""

    def __init__(self, details: str):
        self.details = details
        super().__init__(f"Cache invalidation failed: {details}")


# Schema validation errors
class SchemaValidationError(SyntheticSensorsConfigError):
    """Schema validation failed."""

    def __init__(self, details: str, schema_path: str | None = None):
        self.details = details
        self.schema_path = schema_path
        if schema_path:
            super().__init__(f"Schema validation failed for '{schema_path}': {details}")
        else:
            super().__init__(f"Schema validation failed: {details}")


# Utility functions for exception handling
def is_retriable_error(error: Exception) -> bool:
    """Determine if an error is retriable (temporary condition).

    This follows the pattern used by Home Assistant coordinators
    to distinguish between permanent and temporary errors.
    """
    # Temporary/retriable errors
    retriable_types = (
        UnavailableDependencyError,
        SensorUpdateError,
        CacheError,
    )

    return isinstance(error, retriable_types)


def is_fatal_error(error: Exception) -> bool:
    """Determine if an error is fatal (permanent configuration issue).

    Fatal errors should trigger circuit breaker patterns and
    prevent further evaluation attempts.
    """
    # Permanent/fatal errors
    fatal_types = (
        FormulaSyntaxError,
        MissingDependencyError,
        CircularDependencyError,
        InvalidCollectionPatternError,
        SensorConfigurationError,
        SchemaValidationError,
        DataValidationError,  # Bad data is a fatal error
    )

    return isinstance(error, fatal_types)


def should_trigger_auth_failed(error: Exception) -> bool:
    """Determine if error should trigger ConfigEntryAuthFailed.

    Currently not used but reserved for future authentication features.
    """
    return isinstance(error, SyntheticSensorsAuthError)


def should_trigger_not_ready(error: Exception) -> bool:
    """Determine if error should trigger ConfigEntryNotReady."""
    return isinstance(
        error,
        (
            SyntheticSensorsNotReadyError,
            IntegrationNotInitializedError,
        ),
    )
