"""Tests for LazyResolver implementation."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, MagicMock

from ha_synthetic_sensors.lazy_resolver import LazyResolver
from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalContextDict
from ha_synthetic_sensors.reference_value_manager import ReferenceValue
from ha_synthetic_sensors.formula_ast_analysis_service import BindingPlan
from ha_synthetic_sensors.binding_plan_helpers import prepare_minimal_layer


class TestLazyResolver:
    """Test LazyResolver functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = Mock()
        self.mock_data_provider = Mock()
        self.lazy_resolver = LazyResolver(self.mock_hass, self.mock_data_provider)

    def test_lazy_resolver_initialization(self):
        """Test LazyResolver initializes correctly."""
        assert self.lazy_resolver._hass is self.mock_hass
        assert self.lazy_resolver._data_provider is self.mock_data_provider
        assert self.lazy_resolver._cycle_id == 0
        assert len(self.lazy_resolver._cycle_cache) == 0

    def test_start_new_cycle(self):
        """Test starting a new evaluation cycle."""
        # Add some cached data
        self.lazy_resolver._cycle_cache["test"] = "value"
        self.lazy_resolver._batch_states["sensor.test"] = "on"

        # Start new cycle
        self.lazy_resolver.start_new_cycle()

        # Verify cycle incremented and caches cleared
        assert self.lazy_resolver._cycle_id == 1
        assert len(self.lazy_resolver._cycle_cache) == 0
        assert len(self.lazy_resolver._batch_states) == 0
        assert self.lazy_resolver._batch_loaded is False

    def test_resolve_if_needed_cache_hit(self):
        """Test cache hit behavior."""
        ctx = Mock()
        ctx.get.return_value = ReferenceValue("test", "cached_value")

        # Prime the cache
        self.lazy_resolver._cycle_cache["1:test_var"] = "cached_value"
        self.lazy_resolver._cycle_id = 1

        result = self.lazy_resolver.resolve_if_needed(ctx, "test_var")

        assert result == "cached_value"
        # Should not call ctx.get since we hit cache
        ctx.get.assert_not_called()

    def test_resolve_if_needed_already_resolved(self):
        """Test behavior when ReferenceValue already has a value."""
        ctx = Mock()
        ref_value = ReferenceValue("sensor.test", "already_resolved")
        ctx.get.return_value = ref_value

        # Start a cycle to set cycle_id to 1
        self.lazy_resolver.start_new_cycle()

        result = self.lazy_resolver.resolve_if_needed(ctx, "test_var")

        assert result == "already_resolved"
        # Should cache the result
        assert self.lazy_resolver._cycle_cache["1:test_var"] == "already_resolved"

    def test_resolve_if_needed_lazy_resolution(self):
        """Test lazy resolution when value is None."""
        ctx = Mock()
        ref_value = ReferenceValue("sensor.test", None)
        ref_value._value = None  # Ensure it's truly lazy
        ctx.get.side_effect = lambda key, default=None: {"test_var": ref_value, "_strategy_test_var": "ha_state"}.get(
            key, default
        )

        # Mock HA state
        mock_state = Mock()
        mock_state.state = "resolved_value"
        self.mock_hass.states.get.return_value = mock_state

        # Start a cycle to set cycle_id to 1
        self.lazy_resolver.start_new_cycle()

        result = self.lazy_resolver.resolve_if_needed(ctx, "test_var")

        assert result == "resolved_value"
        # Should update ReferenceValue in place
        assert ref_value._value == "resolved_value"
        # Should cache the result
        assert self.lazy_resolver._cycle_cache["1:test_var"] == "resolved_value"

    def test_resolve_ha_state_success(self):
        """Test successful HA state resolution."""
        mock_state = Mock()
        mock_state.state = "on"
        self.mock_hass.states.get.return_value = mock_state

        result = self.lazy_resolver._resolve_ha_state("sensor.test")

        assert result == "on"
        self.mock_hass.states.get.assert_called_once_with("sensor.test")

    def test_resolve_ha_state_not_found(self):
        """Test HA state resolution when entity not found."""
        self.mock_hass.states.get.return_value = None

        result = self.lazy_resolver._resolve_ha_state("sensor.nonexistent")

        assert result is None

    def test_resolve_data_provider_success(self):
        """Test successful data provider resolution."""
        mock_result = Mock()
        mock_result.value = "provider_value"
        self.mock_data_provider.return_value = mock_result

        result = self.lazy_resolver._resolve_data_provider("test_var")

        assert result == "provider_value"
        self.mock_data_provider.assert_called_once_with("test_var")

    def test_resolve_data_provider_no_provider(self):
        """Test data provider resolution when no provider available."""
        resolver = LazyResolver(self.mock_hass, None)

        result = resolver._resolve_data_provider("test_var")

        assert result is None

    def test_resolve_literal(self):
        """Test literal value resolution."""
        result = self.lazy_resolver._resolve_literal("literal_value")

        assert result == "literal_value"

    def test_prepare_batch_entities(self):
        """Test batch entity preparation."""
        entity_ids = {"sensor.test1", "sensor.test2"}

        # Mock states
        mock_state1 = Mock()
        mock_state1.state = "value1"
        mock_state2 = Mock()
        mock_state2.state = "value2"

        self.mock_hass.states.get.side_effect = lambda eid: {"sensor.test1": mock_state1, "sensor.test2": mock_state2}.get(eid)

        self.lazy_resolver.prepare_batch_entities(entity_ids)

        assert self.lazy_resolver._batch_loaded is True
        assert self.lazy_resolver._batch_states["sensor.test1"] == "value1"
        assert self.lazy_resolver._batch_states["sensor.test2"] == "value2"

    def test_get_cache_stats(self):
        """Test cache statistics."""
        self.lazy_resolver._cycle_id = 5
        self.lazy_resolver._cycle_cache["test"] = "value"
        self.lazy_resolver._batch_states["sensor.test"] = "on"
        self.lazy_resolver._batch_loaded = True

        stats = self.lazy_resolver.get_cache_stats()

        assert stats["cycle_id"] == 5
        assert stats["cache_size"] == 1
        assert stats["batch_size"] == 1
        assert stats["batch_loaded"] is True


class TestBindingPlanLazyIntegration:
    """Test integration between binding plans and lazy resolution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = Mock()
        self.lazy_resolver = LazyResolver(self.mock_hass)

        # Create a mock hierarchical context
        self.ctx = Mock(spec=HierarchicalContextDict)
        self.ctx.__contains__ = Mock(return_value=False)
        self.ctx.__setitem__ = Mock()
        self.ctx.get = Mock()

    def test_prepare_minimal_layer_with_lazy_resolver(self):
        """Test prepare_minimal_layer with LazyResolver integration."""
        # Create a binding plan
        plan = BindingPlan(
            names=frozenset(["sensor.power", "temp_offset"]),
            has_metadata=False,
            has_collections=False,
            strategies={"sensor.power": "ha_state", "temp_offset": "data_provider"},
        )

        # Mock hierarchical context behavior
        self.ctx.hierarchical_context = Mock()
        self.ctx.hierarchical_context.push_layer = Mock()

        prepare_minimal_layer(self.ctx, plan, self.lazy_resolver)

        # Verify lazy resolver was stored
        self.ctx.__setitem__.assert_any_call("_lazy_resolver", self.lazy_resolver)

        # Verify binding plan was stored
        self.ctx.__setitem__.assert_any_call("_binding_plan", plan)

        # Verify strategies were stored
        self.ctx.__setitem__.assert_any_call("_strategy_sensor.power", "ha_state")
        self.ctx.__setitem__.assert_any_call("_strategy_temp_offset", "data_provider")

    def test_prepare_minimal_layer_batch_preparation(self):
        """Test that HA entities are prepared for batch loading."""
        plan = BindingPlan(
            names=frozenset(["sensor.power", "sensor.temp", "config_var"]),
            has_metadata=False,
            has_collections=False,
            strategies={"sensor.power": "ha_state", "sensor.temp": "ha_state", "config_var": "data_provider"},
        )

        # Mock the lazy resolver's prepare_batch_entities method
        self.lazy_resolver.prepare_batch_entities = Mock()

        # Mock hierarchical context
        self.ctx.hierarchical_context = Mock()
        self.ctx.hierarchical_context.push_layer = Mock()

        prepare_minimal_layer(self.ctx, plan, self.lazy_resolver)

        # Verify batch preparation was called with HA entities only
        expected_ha_entities = {"sensor.power", "sensor.temp"}
        self.lazy_resolver.prepare_batch_entities.assert_called_once_with(expected_ha_entities)


if __name__ == "__main__":
    pytest.main([__file__])
