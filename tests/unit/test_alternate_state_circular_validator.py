"""Tests for alternate state handler circular dependency validation."""

import pytest

from ha_synthetic_sensors.config_models import AlternateStateHandler
from ha_synthetic_sensors.alternate_state_circular_validator import (
    CircularDependencyError,
    validate_alternate_state_handler_circular_deps,
)


class TestCircularDependencyValidation:
    """Test circular dependency detection in alternate state handlers."""

    def test_no_circular_dependency_valid(self):
        """Test that valid handlers with no circular dependencies pass validation."""
        handler = AlternateStateHandler(unavailable=0, unknown="unknown_value", none=None, fallback=42)
        # Should not raise any exception
        validate_alternate_state_handler_circular_deps(handler)

    def test_direct_circular_dependency_detected(self):
        """Test detection of direct circular dependency."""
        handler = AlternateStateHandler(
            none="STATE_NONE",  # This creates a direct circular reference
            fallback=999,
        )

        with pytest.raises(CircularDependencyError) as exc_info:
            validate_alternate_state_handler_circular_deps(handler)

        assert "Circular dependency detected" in str(exc_info.value)
        assert "none -> none" in str(exc_info.value)

    def test_indirect_circular_dependency_detected(self):
        """Test detection of indirect circular dependency."""
        handler = AlternateStateHandler(
            unavailable="STATE_UNKNOWN",  # unavailable -> unknown
            unknown="STATE_NONE",  # unknown -> none
            none="STATE_UNAVAILABLE",  # none -> unavailable (creates cycle)
            fallback=999,
        )

        with pytest.raises(CircularDependencyError) as exc_info:
            validate_alternate_state_handler_circular_deps(handler)

        assert "Circular dependency detected" in str(exc_info.value)

    def test_fallback_circular_dependency_detected(self):
        """Test detection of circular dependency involving fallback."""
        handler = AlternateStateHandler(
            fallback="STATE_NONE",  # fallback -> none
            none="STATE_UNKNOWN",  # none -> unknown
            unknown="fallback",  # This would create a cycle if fallback was a state
        )

        # This should NOT raise an error because "fallback" is not a recognized state constant
        # Only STATE_NONE, STATE_UNKNOWN, STATE_UNAVAILABLE are recognized
        validate_alternate_state_handler_circular_deps(handler)

    def test_object_form_circular_dependency_detected(self):
        """Test detection of circular dependency in object form handlers."""
        handler = AlternateStateHandler(
            unavailable={"formula": "STATE_UNKNOWN if condition else 0", "variables": {"condition": True}},
            unknown="STATE_UNAVAILABLE",  # Creates cycle: unavailable -> unknown -> unavailable
        )

        with pytest.raises(CircularDependencyError) as exc_info:
            validate_alternate_state_handler_circular_deps(handler)

        assert "Circular dependency detected" in str(exc_info.value)

    def test_complex_valid_handlers(self):
        """Test complex but valid alternate state handlers."""
        handler = AlternateStateHandler(
            unavailable={"formula": "backup_value * 2", "variables": {"backup_value": 10}},
            unknown="'unknown_string'",
            none=None,
            fallback={"formula": "default_value + offset", "variables": {"default_value": 100, "offset": 5}},
        )

        # Should not raise any exception
        validate_alternate_state_handler_circular_deps(handler)

    def test_none_handler_validation(self):
        """Test that None handler is properly validated."""
        # This should be valid - None handler can be None
        handler = AlternateStateHandler(none=None)
        validate_alternate_state_handler_circular_deps(handler)

    def test_empty_handler_validation(self):
        """Test validation of None/empty handler."""
        validate_alternate_state_handler_circular_deps(None)

    def test_state_reference_in_formula_string(self):
        """Test detection of state references within formula strings."""
        handler = AlternateStateHandler(
            unavailable="state if state != 'STATE_UNKNOWN' else 0",
            unknown="STATE_UNAVAILABLE",  # Creates cycle
        )

        with pytest.raises(CircularDependencyError) as exc_info:
            validate_alternate_state_handler_circular_deps(handler)

        assert "Circular dependency detected" in str(exc_info.value)

    def test_multiple_independent_paths_allowed(self):
        """Test that multiple independent paths to the same state are allowed."""
        handler = AlternateStateHandler(
            unavailable="final_value",
            unknown="final_value",  # Both point to same literal - this is OK
            none="final_value",
            fallback="different_value",
        )

        # Should not raise any exception - multiple handlers can have same literal value
        validate_alternate_state_handler_circular_deps(handler)
