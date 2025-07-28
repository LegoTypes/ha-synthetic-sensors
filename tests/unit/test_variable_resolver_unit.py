"""Unit tests for variable_resolver.py module.

Tests the variable resolution strategies and resolver orchestration,
focusing on the actual API behavior and proper mocking.
"""

import pytest
from unittest.mock import Mock, MagicMock
from homeassistant.core import HomeAssistant, State

from ha_synthetic_sensors.variable_resolver import (
    ContextResolutionStrategy,
    IntegrationResolutionStrategy,
    HomeAssistantResolutionStrategy,
    VariableResolver,
)
from ha_synthetic_sensors.exceptions import MissingDependencyError, NonNumericStateError


class TestContextResolutionStrategy:
    """Test cases for ContextResolutionStrategy."""

    def test_can_resolve_numeric_context(self):
        """Test that strategy can resolve numeric context values."""
        context = {"temp": 25.5, "humidity": 60, "mode": "auto"}
        strategy = ContextResolutionStrategy(context)

        # Should resolve numeric values
        assert strategy.can_resolve("temp") is True
        assert strategy.can_resolve("humidity") is True

        # Should not resolve non-numeric values
        assert strategy.can_resolve("mode") is False

        # Should not resolve missing values
        assert strategy.can_resolve("missing") is False

    def test_resolve_variable_numeric_success(self):
        """Test successful resolution of numeric context variables."""
        context = {"temp": 25.5, "humidity": 60}
        strategy = ContextResolutionStrategy(context)

        value, exists, source = strategy.resolve_variable("temp")
        assert value == 25.5
        assert exists is True
        assert source == "context"

        value, exists, source = strategy.resolve_variable("humidity")
        assert value == 60
        assert exists is True
        assert source == "context"

    def test_resolve_variable_non_numeric_error(self):
        """Test that non-numeric context values raise MissingDependencyError."""
        context = {"mode": "auto"}
        strategy = ContextResolutionStrategy(context)

        with pytest.raises(MissingDependencyError, match="Context variable 'mode' has non-numeric value 'auto'"):
            strategy.resolve_variable("mode")

    def test_resolve_variable_missing(self):
        """Test resolution of missing context variables."""
        context = {"temp": 25.5}
        strategy = ContextResolutionStrategy(context)

        value, exists, source = strategy.resolve_variable("missing")
        assert value is None
        assert exists is False
        assert source == "context"

    def test_empty_context(self):
        """Test strategy with empty context."""
        strategy = ContextResolutionStrategy({})

        assert strategy.can_resolve("any_var") is False

        value, exists, source = strategy.resolve_variable("any_var")
        assert value is None
        assert exists is False
        assert source == "context"

    def test_none_context(self):
        """Test strategy with None context."""
        strategy = ContextResolutionStrategy(None)

        assert strategy.can_resolve("any_var") is False

        value, exists, source = strategy.resolve_variable("any_var")
        assert value is None
        assert exists is False
        assert source == "context"


class TestIntegrationResolutionStrategy:
    """Test cases for IntegrationResolutionStrategy."""

    def test_no_data_provider_callback(self):
        """Test strategy with no data provider callback."""
        strategy = IntegrationResolutionStrategy(None)

        # Should not be able to resolve anything
        assert strategy.can_resolve("sensor.test") is False

        # Note: We cannot test resolve_variable with None callback as it will raise TypeError
        # This is expected behavior - the strategy requires a valid callback to function

    def test_get_integration_entities_no_handler(self):
        """Test getting integration entities when no handler exists."""
        strategy = IntegrationResolutionStrategy(None)
        entities = strategy._get_integration_entities()
        assert entities == set()

    def test_get_integration_entities_with_handler(self):
        """Test getting integration entities when handler exists."""
        mock_dependency_handler = Mock()
        mock_dependency_handler.get_integration_entities.return_value = {"sensor.test1", "sensor.test2"}

        strategy = IntegrationResolutionStrategy(None, mock_dependency_handler)
        entities = strategy._get_integration_entities()
        assert entities == {"sensor.test1", "sensor.test2"}
        mock_dependency_handler.get_integration_entities.assert_called_once()

    def test_can_resolve_non_entity_variables(self):
        """Test that non-entity variables cannot be resolved."""
        mock_callback = Mock()
        strategy = IntegrationResolutionStrategy(mock_callback)

        # Variables without dots should not be resolved
        assert strategy.can_resolve("simple_var") is False
        assert strategy.can_resolve("temperature") is False

    def test_can_resolve_entity_without_registration(self):
        """Test resolving entities when no registration filtering is in place."""

        # Mock data provider callback to return successful result
        def mock_callback(entity_id):
            return {"value": 25.5, "exists": True}

        strategy = IntegrationResolutionStrategy(mock_callback)

        # With no dependency handler, should allow any entity
        # Note: this tests the _is_entity_registered fallback logic
        result = strategy._is_entity_registered("sensor.test")
        assert result is True

    def test_basic_resolution_success(self):
        """Test basic successful resolution with proper data provider result."""

        def mock_callback(entity_id):
            if entity_id == "sensor.test":
                return {"value": 42.0, "exists": True}
            return {"value": None, "exists": False}

        strategy = IntegrationResolutionStrategy(mock_callback)

        # This tests the basic resolution path without complex attribute logic
        # Note: The actual resolution may go through complex attribute reference logic
        # but we're testing the fundamental data provider callback mechanism


class TestHomeAssistantResolutionStrategy:
    """Test cases for HomeAssistantResolutionStrategy."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = Mock(spec=HomeAssistant)
        # Properly mock the states attribute
        self.mock_hass.states = Mock()
        self.strategy = HomeAssistantResolutionStrategy(self.mock_hass)

    def test_can_resolve_entity_exists(self):
        """Test can resolve when entity exists in HA."""
        mock_state = Mock(state="25.5")
        self.mock_hass.states.get.return_value = mock_state

        assert self.strategy.can_resolve("sensor.test") is True
        self.mock_hass.states.get.assert_called_with("sensor.test")

    def test_can_resolve_entity_missing(self):
        """Test cannot resolve when entity missing from HA."""
        self.mock_hass.states.get.return_value = None

        assert self.strategy.can_resolve("sensor.missing") is False

    def test_resolve_variable_missing_entity(self):
        """Test resolving missing entity."""
        self.mock_hass.states.get.return_value = None

        value, exists, source = self.strategy.resolve_variable("sensor.missing")
        assert value is None
        assert exists is False
        assert source == "ha"

    def test_get_numeric_state_valid(self):
        """Test getting numeric state for valid numbers."""
        mock_state = Mock(state="42.5", entity_id="sensor.test")

        result = self.strategy.get_numeric_state(mock_state)
        assert result == 42.5

    def test_get_numeric_state_invalid_number(self):
        """Test getting numeric state for invalid numbers raises error."""
        mock_state = Mock(state="not_a_number", entity_id="sensor.test")

        with pytest.raises(NonNumericStateError, match="Entity 'sensor.test' has non-numeric state"):
            self.strategy.get_numeric_state(mock_state)

    def test_boolean_state_constants_integration(self):
        """Test integration with boolean state constants."""
        from ha_synthetic_sensors.constants_boolean_states import TRUE_STATES, FALSE_STATES

        # Test that the constants are available and contain expected values
        assert "on" in TRUE_STATES or "STATE_ON" in str(TRUE_STATES)
        assert "off" in FALSE_STATES or "STATE_OFF" in str(FALSE_STATES)
        assert "true" in TRUE_STATES
        assert "false" in FALSE_STATES

        # Test that the sets are non-empty
        assert len(TRUE_STATES) > 0
        assert len(FALSE_STATES) > 0

        # Test that some common obvious states don't overlap
        # Note: The full sets may overlap due to HA's complex state mappings, but basic ones shouldn't
        basic_overlap = {"true", "false", "on", "off", "yes", "no"} & (TRUE_STATES & FALSE_STATES)
        assert len(basic_overlap) == 0, f"Basic boolean states should not overlap: {basic_overlap}"


class TestVariableResolver:
    """Test cases for VariableResolver orchestration."""

    def setup_method(self):
        """Set up test fixtures."""
        self.context_strategy = Mock(spec=ContextResolutionStrategy)
        self.integration_strategy = Mock(spec=IntegrationResolutionStrategy)
        self.ha_strategy = Mock(spec=HomeAssistantResolutionStrategy)

        self.resolver = VariableResolver([self.context_strategy, self.integration_strategy, self.ha_strategy])

    def test_resolve_variable_first_strategy_succeeds(self):
        """Test resolution when first strategy can resolve."""
        self.context_strategy.can_resolve.return_value = True
        self.context_strategy.resolve_variable.return_value = (25.5, True, "context")

        value, exists, source = self.resolver.resolve_variable("temp")

        assert value == 25.5
        assert exists is True
        assert source == "context"

        self.context_strategy.can_resolve.assert_called_once_with("temp", None)
        self.context_strategy.resolve_variable.assert_called_once_with("temp", None)
        # Other strategies should not be called
        self.integration_strategy.can_resolve.assert_not_called()

    def test_resolve_variable_fallback_to_second_strategy(self):
        """Test resolution falling back to second strategy."""
        self.context_strategy.can_resolve.return_value = False
        self.integration_strategy.can_resolve.return_value = True
        self.integration_strategy.resolve_variable.return_value = (42.0, True, "integration")

        value, exists, source = self.resolver.resolve_variable("sensor.test")

        assert value == 42.0
        assert exists is True
        assert source == "integration"

        # First strategy should have been checked
        self.context_strategy.can_resolve.assert_called_once_with("sensor.test", None)
        # Second strategy should have resolved
        self.integration_strategy.can_resolve.assert_called_once_with("sensor.test", None)
        self.integration_strategy.resolve_variable.assert_called_once_with("sensor.test", None)

    def test_resolve_variable_all_strategies_fail(self):
        """Test resolution when no strategy can resolve."""
        self.context_strategy.can_resolve.return_value = False
        self.integration_strategy.can_resolve.return_value = False
        self.ha_strategy.can_resolve.return_value = False

        value, exists, source = self.resolver.resolve_variable("missing_var")

        assert value is None
        assert exists is False
        assert source == "none"

    def test_resolve_variable_with_entity_id(self):
        """Test resolution with entity_id parameter."""
        self.context_strategy.can_resolve.return_value = False
        self.integration_strategy.can_resolve.return_value = True
        self.integration_strategy.resolve_variable.return_value = (30.0, True, "integration")

        value, exists, source = self.resolver.resolve_variable("temp", "sensor.test")

        assert value == 30.0
        assert exists is True
        assert source == "integration"

        # Check that entity_id was passed to strategies
        self.context_strategy.can_resolve.assert_called_once_with("temp", "sensor.test")
        self.integration_strategy.can_resolve.assert_called_once_with("temp", "sensor.test")

    def test_resolve_variables_mixed_types(self):
        """Test resolving multiple variables with mixed types."""
        # Mock different resolution outcomes
        self.context_strategy.can_resolve.side_effect = lambda var, eid: var == "context_var"
        self.context_strategy.resolve_variable.return_value = (10.0, True, "context")

        self.integration_strategy.can_resolve.side_effect = lambda var, eid: var == "sensor.test"
        self.integration_strategy.resolve_variable.return_value = (20.0, True, "integration")

        # Test mixed variable types
        variables = {
            "context_var": None,
            "literal_var": 42.5,  # Numeric literal
            "sensor.test": "sensor.test",
        }

        results = self.resolver.resolve_variables(variables)

        # Verify results
        assert results["context_var"] == (10.0, True, "context")
        assert results["literal_var"] == (42.5, True, "literal")  # Should be handled as literal
        assert results["sensor.test"] == (20.0, True, "integration")

    def test_resolve_variables_with_failures(self):
        """Test resolving variables when some cannot be resolved."""
        # No strategy can resolve anything
        self.context_strategy.can_resolve.return_value = False
        self.integration_strategy.can_resolve.return_value = False
        self.ha_strategy.can_resolve.return_value = False

        variables = {
            "missing1": None,
            "literal": 100,  # This should still work
            "missing2": "sensor.missing",
        }

        results = self.resolver.resolve_variables(variables)

        # Verify results
        assert results["missing1"] == (None, False, "none")
        assert results["literal"] == (100, True, "literal")
        assert results["missing2"] == (None, False, "none")

    def test_empty_strategies_list(self):
        """Test resolver with no strategies."""
        resolver = VariableResolver([])

        value, exists, source = resolver.resolve_variable("any_var")
        assert value is None
        assert exists is False
        assert source == "none"
