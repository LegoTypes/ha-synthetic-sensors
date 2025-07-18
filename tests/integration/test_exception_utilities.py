"""Tests for exception utility functions with low coverage."""

import pytest

from ha_synthetic_sensors.exceptions import (
    CacheError,
    CacheInvalidationError,
    CircularDependencyError,
    DataValidationError,
    EmptyCollectionError,
    FormulaSyntaxError,
    IntegrationSetupError,
    IntegrationTeardownError,
    InvalidCollectionPatternError,
    MissingDependencyError,
    NonNumericStateError,
    SensorConfigurationError,
    SensorCreationError,
    SensorUpdateError,
    SchemaValidationError,
    UnavailableDependencyError,
    is_fatal_error,
    is_retriable_error,
    should_trigger_auth_failed,
    should_trigger_not_ready,
)


class TestExceptionUtilities:
    """Test the utility functions in exceptions.py that have low coverage."""

    def test_is_retriable_error_retriable_types(self) -> None:
        """Test is_retriable_error with retriable error types."""
        # Test UnavailableDependencyError
        error = UnavailableDependencyError("test_entity")
        assert is_retriable_error(error) is True

        # Test SensorUpdateError
        error = SensorUpdateError("test_sensor", "update failed")
        assert is_retriable_error(error) is True

        # Test CacheError
        error = CacheError("cache error")
        assert is_retriable_error(error) is True

        # Test CacheInvalidationError (subclass of CacheError)
        error = CacheInvalidationError("invalidation failed")
        assert is_retriable_error(error) is True

    def test_is_retriable_error_non_retriable_types(self) -> None:
        """Test is_retriable_error with non-retriable error types."""
        # Test FormulaSyntaxError
        error = FormulaSyntaxError("invalid_formula", "syntax error")
        assert is_retriable_error(error) is False

        # Test MissingDependencyError
        error = MissingDependencyError("missing_entity")
        assert is_retriable_error(error) is False

        # Test CircularDependencyError
        error = CircularDependencyError(["a", "b", "a"])
        assert is_retriable_error(error) is False

        # Test InvalidCollectionPatternError
        error = InvalidCollectionPatternError("invalid_pattern", "pattern error")
        assert is_retriable_error(error) is False

        # Test SensorConfigurationError
        error = SensorConfigurationError("test_sensor", "config error")
        assert is_retriable_error(error) is False

        # Test SchemaValidationError
        error = SchemaValidationError("validation failed")
        assert is_retriable_error(error) is False

        # Test DataValidationError
        error = DataValidationError("data error")
        assert is_retriable_error(error) is False

    def test_is_fatal_error_fatal_types(self) -> None:
        """Test is_fatal_error with fatal error types."""
        # Test FormulaSyntaxError
        error = FormulaSyntaxError("invalid_formula", "syntax error")
        assert is_fatal_error(error) is True

        # Test MissingDependencyError
        error = MissingDependencyError("missing_entity")
        assert is_fatal_error(error) is True

        # Test CircularDependencyError
        error = CircularDependencyError(["a", "b", "a"])
        assert is_fatal_error(error) is True

        # Test InvalidCollectionPatternError
        error = InvalidCollectionPatternError("invalid_pattern", "pattern error")
        assert is_fatal_error(error) is True

        # Test SensorConfigurationError
        error = SensorConfigurationError("test_sensor", "config error")
        assert is_fatal_error(error) is True

        # Test SchemaValidationError
        error = SchemaValidationError("validation failed")
        assert is_fatal_error(error) is True

        # Test DataValidationError
        error = DataValidationError("data error")
        assert is_fatal_error(error) is True

    def test_is_fatal_error_non_fatal_types(self) -> None:
        """Test is_fatal_error with non-fatal error types."""
        # Test UnavailableDependencyError
        error = UnavailableDependencyError("test_entity")
        assert is_fatal_error(error) is False

        # Test SensorUpdateError
        error = SensorUpdateError("test_sensor", "update failed")
        assert is_fatal_error(error) is False

        # Test CacheError
        error = CacheError("cache error")
        assert is_fatal_error(error) is False

    def test_should_trigger_auth_failed(self) -> None:
        """Test should_trigger_auth_failed function."""
        # This function currently always returns False
        # Test with various error types to ensure it doesn't crash
        error = UnavailableDependencyError("test_entity")
        assert should_trigger_auth_failed(error) is False

        error = FormulaSyntaxError("invalid_formula", "syntax error")
        assert should_trigger_auth_failed(error) is False

        error = MissingDependencyError("missing_entity")
        assert should_trigger_auth_failed(error) is False

    def test_should_trigger_not_ready(self) -> None:
        """Test should_trigger_not_ready function."""
        # This function currently always returns False
        # Test with various error types to ensure it doesn't crash
        error = UnavailableDependencyError("test_entity")
        assert should_trigger_not_ready(error) is False

        error = FormulaSyntaxError("invalid_formula", "syntax error")
        assert should_trigger_not_ready(error) is False

        error = MissingDependencyError("missing_entity")
        assert should_trigger_not_ready(error) is False

    def test_exception_inheritance_hierarchy(self) -> None:
        """Test that exception inheritance hierarchy works correctly."""
        # Test that retriable errors are not fatal
        retriable_errors = [
            UnavailableDependencyError("test_entity"),
            SensorUpdateError("test_sensor", "update failed"),
            CacheError("cache error"),
            CacheInvalidationError("invalidation failed"),
        ]

        for error in retriable_errors:
            assert is_retriable_error(error) is True
            assert is_fatal_error(error) is False

        # Test that fatal errors are not retriable
        fatal_errors = [
            FormulaSyntaxError("invalid_formula", "syntax error"),
            MissingDependencyError("missing_entity"),
            CircularDependencyError(["a", "b", "a"]),
            InvalidCollectionPatternError("invalid_pattern", "pattern error"),
            SensorConfigurationError("test_sensor", "config error"),
            SchemaValidationError("validation failed"),
            DataValidationError("data error"),
        ]

        for error in fatal_errors:
            assert is_fatal_error(error) is True
            assert is_retriable_error(error) is False

    def test_exception_attributes(self) -> None:
        """Test that exceptions have the expected attributes."""
        # Test FormulaSyntaxError
        error = FormulaSyntaxError("test_formula", "syntax error")
        assert error.formula == "test_formula"
        assert error.details == "syntax error"
        assert "test_formula" in str(error)
        assert "syntax error" in str(error)

        # Test MissingDependencyError with formula_name
        error = MissingDependencyError("missing_entity", "test_formula")
        assert error.dependency == "missing_entity"
        assert error.formula_name == "test_formula"
        assert "test_formula" in str(error)

        # Test MissingDependencyError without formula_name
        error = MissingDependencyError("missing_entity")
        assert error.dependency == "missing_entity"
        assert error.formula_name is None
        assert "test_formula" not in str(error)

        # Test UnavailableDependencyError with formula_name
        error = UnavailableDependencyError("unavailable_entity", "test_formula")
        assert error.dependency == "unavailable_entity"
        assert error.formula_name == "test_formula"
        assert "test_formula" in str(error)

        # Test UnavailableDependencyError without formula_name
        error = UnavailableDependencyError("unavailable_entity")
        assert error.dependency == "unavailable_entity"
        assert error.formula_name is None
        assert "test_formula" not in str(error)

        # Test NonNumericStateError
        error = NonNumericStateError("test_entity", "unavailable")
        assert error.entity_id == "test_entity"
        assert error.state_value == "unavailable"
        assert "test_entity" in str(error)
        assert "unavailable" in str(error)

        # Test CircularDependencyError
        error = CircularDependencyError(["a", "b", "c", "a"])
        assert error.dependency_chain == ["a", "b", "c", "a"]
        assert "a -> b -> c -> a" in str(error)

        # Test InvalidCollectionPatternError
        error = InvalidCollectionPatternError("invalid_pattern", "pattern error")
        assert error.pattern == "invalid_pattern"
        assert error.details == "pattern error"
        assert "invalid_pattern" in str(error)
        assert "pattern error" in str(error)

        # Test EmptyCollectionError
        error = EmptyCollectionError("empty_pattern")
        assert error.pattern == "empty_pattern"
        assert "empty_pattern" in str(error)

        # Test SensorConfigurationError
        error = SensorConfigurationError("test_sensor", "config error")
        assert error.sensor_name == "test_sensor"
        assert error.details == "config error"
        assert "test_sensor" in str(error)
        assert "config error" in str(error)

        # Test SensorCreationError
        error = SensorCreationError("test_sensor", "creation failed")
        assert error.sensor_name == "test_sensor"
        assert error.details == "creation failed"
        assert "test_sensor" in str(error)
        assert "creation failed" in str(error)

        # Test SensorUpdateError
        error = SensorUpdateError("test_sensor", "update failed")
        assert error.sensor_name == "test_sensor"
        assert error.details == "update failed"
        assert "test_sensor" in str(error)
        assert "update failed" in str(error)

        # Test IntegrationSetupError
        error = IntegrationSetupError("setup failed")
        assert error.details == "setup failed"
        assert "setup failed" in str(error)

        # Test IntegrationTeardownError
        error = IntegrationTeardownError("teardown failed")
        assert error.details == "teardown failed"
        assert "teardown failed" in str(error)

        # Test CacheInvalidationError
        error = CacheInvalidationError("invalidation failed")
        assert error.details == "invalidation failed"
        assert "invalidation failed" in str(error)

        # Test SchemaValidationError with schema_path
        error = SchemaValidationError("validation failed", "test.schema")
        assert error.details == "validation failed"
        assert error.schema_path == "test.schema"
        assert "test.schema" in str(error)

        # Test SchemaValidationError without schema_path
        error = SchemaValidationError("validation failed")
        assert error.details == "validation failed"
        assert error.schema_path is None
        assert "test.schema" not in str(error)
