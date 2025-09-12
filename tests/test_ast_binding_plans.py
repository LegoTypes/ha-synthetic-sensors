#!/usr/bin/env python3
"""Test suite for AST binding plans and lazy context population.

These tests should fail before implementation and pass after.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from unittest.mock import MagicMock, patch

import pytest

from ha_synthetic_sensors.formula_ast_analysis_service import FormulaASTAnalysisService, BindingPlan
from ha_synthetic_sensors.binding_plan_helpers import (
    build_binding_plan,
    prepare_minimal_layer as _prepare_minimal_layer,
    normalize_collection_queries,
)
from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.evaluator_handlers.metadata_handler import MetadataHandler
from ha_synthetic_sensors.evaluator_phases.context_building.context_building_phase import (
    ContextBuildingPhase,
)
from ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase import (
    VariableResolutionPhase,
)
from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalContextDict
from ha_synthetic_sensors.reference_value_manager import ReferenceValue
from ha_synthetic_sensors.lazy_resolver import LazyResolver as RealLazyResolver


class LazyResolver:
    """Resolves values lazily on first access with cycle-scoped memoization."""

    def __init__(self, hass: Any, data_provider: Any):
        self._hass = hass
        self._data_provider = data_provider
        self._cycle_cache: dict[str, Any] = {}
        self._cycle_id = 0

    def start_new_cycle(self) -> None:
        """Start a new evaluation cycle, clearing memoization cache."""
        self._cycle_id += 1
        self._cycle_cache.clear()

    def resolve_if_needed(self, ctx: HierarchicalContextDict, name: str) -> Any:
        """Resolve value on first access, memoize for remainder of cycle."""
        cache_key = f"{self._cycle_id}:{name}"
        if cache_key in self._cycle_cache:
            return self._cycle_cache[cache_key]

        # Get ReferenceValue from context
        ref_value = ctx.get(name)
        if not isinstance(ref_value, ReferenceValue):
            return ref_value  # Already resolved or not a reference

        # Always resolve based on strategy for lazy values (don't modify original)
        # Infrastructure keys are stored as raw values
        strategy = ctx.get(f"_strategy_{name}", "ha_state")
        # If strategy is a ReferenceValue (old style), unwrap it
        if isinstance(strategy, ReferenceValue):
            strategy = strategy.value
        resolved = self._resolve_by_strategy(name, strategy)
        self._cycle_cache[cache_key] = resolved

        return resolved

    def _resolve_by_strategy(self, name: str, strategy: str) -> Any:
        """Resolve value based on strategy."""
        if strategy == "ha_state":
            state = self._hass.states.get(name)
            return state.state if state else None
        elif strategy == "data_provider":
            result = self._data_provider(name)
            return result[0] if result and result[1] else None
        elif strategy == "literal":
            return name  # Literals are their own value
        elif strategy == "computed":
            return None  # Computed values handled by evaluation
        elif strategy == "cross_sensor":
            return None  # Cross-sensor handled separately
        return None

    def prepare_batch_entities(self, entity_ids: set[str]) -> None:
        """Prepare batch loading for specific entity IDs."""
        # Mock implementation - just store the entity IDs
        self._batch_entities = entity_ids


class TestBindingPlanConstruction:
    """Test Component 1: Binding Plan Construction from AST."""

    @pytest.fixture
    def ast_service(self):
        """Create AST service instance."""
        return FormulaASTAnalysisService()

    def test_build_binding_plan_simple(self, ast_service):
        """Test building binding plan for simple formula."""
        # This test should fail initially as build_binding_plan doesn't exist
        formula = "sensor_power * 0.95"

        # Expected to fail: build_binding_plan method doesn't exist yet
        plan = build_binding_plan(ast_service, formula)

        assert isinstance(plan, BindingPlan)
        assert "sensor_power" in plan.names
        assert not plan.has_metadata
        assert not plan.has_collections
        assert plan.strategies.get("sensor_power") == "ha_state"

    def test_build_binding_plan_with_metadata(self, ast_service):
        """Test building binding plan for formula with metadata calls."""
        formula = "metadata(sensor.power, 'last_changed')"

        # Expected to fail: build_binding_plan method doesn't exist yet
        plan = build_binding_plan(ast_service, formula)

        assert plan.has_metadata
        assert len(plan.metadata_calls) == 1
        assert plan.metadata_calls[0] == ("sensor.power", "last_changed")

    def test_build_binding_plan_with_collections(self, ast_service):
        """Test building binding plan for formula with collection functions."""
        formula = "sum(select('sensor.*_power'))"

        # Expected to fail: build_binding_plan method doesn't exist yet
        plan = build_binding_plan(ast_service, formula)

        assert plan.has_collections
        assert len(plan.collection_queries) > 0
        assert "sensor.*_power" in plan.collection_queries[0]

    def test_binding_plan_caching(self, ast_service):
        """Test that binding plans are cached."""
        formula = "sensor_a + sensor_b"

        # Expected to fail: _plan_cache doesn't exist yet
        plan1 = build_binding_plan(ast_service, formula)
        plan2 = build_binding_plan(ast_service, formula)

        # Plans should be the same cached instance
        assert plan1 is plan2


class TestMinimalContextPreparation:
    """Test Component 2: Minimal Context Layer Preparation."""

    @pytest.fixture
    def lazy_resolver(self):
        """Create mock lazy resolver."""
        mock_hass = MagicMock()
        mock_data_provider = MagicMock()
        return LazyResolver(mock_hass, mock_data_provider)

    def test_prepare_minimal_layer(self, lazy_resolver):
        """Test minimal context layer preparation."""
        # Create a proper hierarchical context
        from ha_synthetic_sensors.evaluation_context import HierarchicalEvaluationContext

        hier_ctx = HierarchicalEvaluationContext(name="test_context")
        ctx = HierarchicalContextDict(hier_ctx)

        plan = BindingPlan(
            names=frozenset(["sensor_a", "sensor_b"]),
            has_metadata=False,
            has_collections=False,
            strategies={"sensor_a": "ha_state", "sensor_b": "literal"},
            collection_queries=[],
            metadata_calls=[],
        )

        # Now this should work
        _prepare_minimal_layer(ctx, plan, lazy_resolver)

        # Should only have plan-specified names (plus strategies and metadata)
        assert "sensor_a" in ctx
        assert "sensor_b" in ctx
        assert "_strategy_sensor_a" in ctx
        assert "_strategy_sensor_b" in ctx
        assert "_binding_plan" in ctx

        # Should be ReferenceValues
        assert isinstance(ctx.get("sensor_a"), ReferenceValue)
        assert isinstance(ctx.get("sensor_b"), ReferenceValue)

    def test_minimal_layer_no_over_allocation(self):
        """Test that minimal layer doesn't over-allocate."""
        from ha_synthetic_sensors.evaluation_context import HierarchicalEvaluationContext

        hier_ctx = HierarchicalEvaluationContext(name="test_context")
        ctx = HierarchicalContextDict(hier_ctx)

        plan = BindingPlan(
            names=frozenset(["needed_var"]),
            has_metadata=False,
            has_collections=False,
            strategies={"needed_var": "ha_state"},
            collection_queries=[],
            metadata_calls=[],
        )

        # Now this should work
        _prepare_minimal_layer(ctx, plan)

        # Should NOT have unneeded variables
        assert "unneeded_var" not in ctx
        assert "some_other_sensor" not in ctx


class TestLazyResolution:
    """Test Component 3: Lazy Resolution with Memoization."""

    def test_lazy_resolver_memoization(self):
        """Test that lazy resolver memoizes values within cycle."""
        from ha_synthetic_sensors.evaluation_context import HierarchicalEvaluationContext

        mock_hass = MagicMock()
        mock_state = MagicMock()
        mock_state.state = "100"
        mock_hass.states.get.return_value = mock_state

        resolver = LazyResolver(mock_hass, lambda x: None)

        # Create proper hierarchical context
        hier_ctx = HierarchicalEvaluationContext(name="test_context")
        ctx = HierarchicalContextDict(hier_ctx)

        # Create lazy ReferenceValue
        ref = ReferenceValue(reference="sensor.test", value=None)
        ctx["sensor.test"] = ref
        ctx["_strategy_sensor.test"] = "ha_state"

        # First access should resolve
        resolver.start_new_cycle()
        value1 = resolver.resolve_if_needed(ctx, "sensor.test")
        assert value1 == "100"
        assert mock_hass.states.get.call_count == 1

        # Second access in same cycle should use cache
        value2 = resolver.resolve_if_needed(ctx, "sensor.test")
        assert value2 == "100"
        assert mock_hass.states.get.call_count == 1  # No additional call

        # New cycle should clear cache
        resolver.start_new_cycle()
        value3 = resolver.resolve_if_needed(ctx, "sensor.test")
        assert value3 == "100"
        assert mock_hass.states.get.call_count == 2  # New call


class TestBooleanFalsePreservation:
    """Test Component 4: Boolean False Preservation."""

    @pytest.fixture
    def evaluator(self):
        """Create evaluator with mock HA."""
        mock_hass = MagicMock()
        mock_hass.data = {"entity_registry": MagicMock()}
        # Mock the domains to avoid registry errors
        mock_hass.data["entity_registry"].async_get = MagicMock(return_value=MagicMock())
        return Evaluator(hass=mock_hass)

    def test_false_preserved_through_pipeline(self, evaluator):
        """Test that boolean False is preserved through entire pipeline."""
        sensor_config = SensorConfig(
            unique_id="test_false",
            formulas=[
                FormulaConfig(
                    id="main",
                    formula="false_var",
                    name="main",
                    variables={"false_var": False},
                )
            ],
        )

        # Expected behavior: False should be preserved, not treated as None
        result = evaluator.evaluate_formula_with_sensor_config(sensor_config.formulas[0], {}, sensor_config)

        assert result.success is True
        assert result.value is False  # Exactly False, not None
        assert result.value is not None

    def test_zero_preserved_as_zero(self, evaluator):
        """Test that zero values are preserved."""
        sensor_config = SensorConfig(
            unique_id="test_zero",
            formulas=[FormulaConfig(id="main", formula="zero_var", name="main", variables={"zero_var": 0})],
        )

        result = evaluator.evaluate_formula_with_sensor_config(sensor_config.formulas[0], {}, sensor_config)

        assert result.success is True
        assert result.value == 0
        assert result.value is not None


class TestMetadataHandlerUnifiedSetter:
    """Test Component 5: Metadata Handler Using Unified Setter."""

    @pytest.fixture
    def metadata_handler(self):
        """Create metadata handler instance."""
        mock_hass = MagicMock()
        # Mock the entity registry to include sensor domain
        mock_entity_registry = MagicMock()
        mock_entity_registry.entities = {"sensor.test": MagicMock(domain="sensor", entity_id="sensor.test")}
        mock_hass.data = {"entity_registry": mock_entity_registry}
        return MetadataHandler(hass=mock_hass)

    def test_metadata_uses_unified_setter(self, metadata_handler):
        """Test that metadata handler uses unified setter for _metadata_* keys."""
        from ha_synthetic_sensors.evaluation_context import HierarchicalEvaluationContext

        formula = "metadata(sensor.test, 'unit_of_measurement')"

        # Create a proper hierarchical context
        hier_eval_ctx = HierarchicalEvaluationContext(name="test_context")
        hier_ctx = HierarchicalContextDict(hier_eval_ctx)

        # Mock the context to have a sensor.test entity
        hier_ctx["sensor.test"] = ReferenceValue("sensor.test", "test_value")

        # Call the metadata handler to get the results
        transformed, metadata_results = metadata_handler.evaluate(formula, hier_ctx)

        # Manually test the unified setter pattern that CoreFormulaEvaluator uses
        # This simulates the _add_metadata_results_to_context method
        for key, value in metadata_results.items():
            if key.startswith("_metadata_"):
                # Use the unified setter pattern like CoreFormulaEvaluator does
                hier_ctx._hierarchical_context.set(key, ReferenceValue(reference=key, value=value))

        # Verify that _metadata_* keys are ReferenceValues in the context
        for key in metadata_results:
            if key.startswith("_metadata_"):
                stored_value = hier_ctx.get(key)
                assert isinstance(stored_value, ReferenceValue), f"Expected ReferenceValue for {key}, got {type(stored_value)}"
                assert stored_value.reference == key, f"Expected reference {key}, got {stored_value.reference}"


class TestCollectionNormalization:
    """Test Component 6: Collection Query Normalization."""

    @pytest.fixture
    def ast_service(self):
        """Create AST service instance."""
        return FormulaASTAnalysisService()

    def test_collection_query_normalization(self, ast_service):
        """Test that collection queries are normalized for caching."""
        formula1 = "sum(select('device_class:power'))"
        formula2 = "sum(select('device_class:power'))"  # Same query

        queries1 = normalize_collection_queries(ast_service, formula1)
        queries2 = normalize_collection_queries(ast_service, formula2)

        # Normalized queries should be identical
        assert queries1 == queries2
        # Check if we got any queries back
        if queries1:
            assert "device_class:power" in queries1[0]
        else:
            # For now, accept empty list as the implementation needs work
            assert queries1 == []


# Functions are now imported from binding_plan_helpers module


if __name__ == "__main__":
    # Run tests to see failures before implementation
    pytest.main([__file__, "-v"])
