# AST-Driven Architecture Testing Guide

## Overview

This document provides a comprehensive testing strategy for validating the unified AST-driven architecture. It addresses gaps
identified in the main architecture document and provides concrete test implementations.

## Updated Testing Scope (Binding Plans + Lazy Context)

This guide updates the test plan to validate the plan-driven, lazy-context approach that preserves the 0–4 phase pipeline while
improving performance. The focus shifts from pre-building complete contexts to:

- Verifying binding plan construction from `FormulaASTAnalysisService`
- Ensuring only the current formula’s names are prepared per phase
- Lazy value resolution on first access with memoization for the evaluation cycle
- Preservation of boolean `False` values across phases and result consolidation
- Metadata handler injecting `_metadata_*` via the unified setter as `ReferenceValue`

### 1. **Binding Plan Data Structure**

Define a compact, immutable plan with proper typing:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, frozenset

@dataclass(frozen=True)
class BindingPlan:
    """Immutable plan describing formula requirements for minimal context population."""
    names: frozenset[str]
    has_metadata: bool
    has_collections: bool
    strategies: dict[str, Literal["ha_state", "data_provider", "literal", "computed", "cross_sensor"]]
    collection_queries: list[str] = field(default_factory=list)
    metadata_calls: list[tuple[str, str]] = field(default_factory=list)
```

### 2. **Plan Construction**

Add tests for `_infer_strategies` and plan generation:

```python
def test_build_binding_plan_simple():
    analysis = ast_service.get_formula_analysis("a + b * 2")
    plan = build_binding_plan(ast_service, "a + b * 2")
    assert plan.names == {"a", "b"}
    assert plan.has_metadata is False
    assert plan.has_collections is False
```

### 3. **Minimal Layer Preparation**

Ensure only names from the plan are prepared for a given formula and that values are lazy:

```python
def test_minimal_layer_and_lazy_resolution():
    ctx = HierarchicalContextDict("sensor_test")
    plan = build_binding_plan(ast_service, "a + b")
    _prepare_minimal_layer(ctx, plan)
    # Nothing resolved yet
    assert isinstance(ctx.get("a"), ReferenceValue)
    assert ctx.get("a").value is None
    # Access via handler triggers resolution and memoization
    _ = numeric_handler.evaluate("a + b", ctx)
    assert ctx.get("a").value is not None
    assert ctx.get("b").value is not None
```

### 4. **Missing Validation Framework**

The document mentions validation but doesn't provide implementation:

```python
class ASTContextValidator:
    """Validate AST-built context against YAML configuration."""
    # Implementation needed
```

## Comprehensive Test Suite

### Test 1: AST Parse-Once + Plan Construction

```python
import pytest
from dataclasses import dataclass
from typing import Dict, Set, List, Tuple, Any

from ha_synthetic_sensors.formula_ast_analysis_service import FormulaASTAnalysisService
from ha_synthetic_sensors.sensor_config import SensorConfig

class TestASTParseOnceAnalysis:
    """Test Component 1: AST Parse-Once Analysis"""

    def setup_method(self):
        """Setup test environment with SPAN integration YAML."""
        self.ast_service = FormulaASTAnalysisService()
        self.span_sensor_config = self._load_span_test_config()

    def _load_span_test_config(self) -> SensorConfig:
        """Load SPAN integration test configuration."""
        yaml_content = """
        sensors:
          - unique_id: air_conditioner_energy_produced_2
            formula: state
            alternate_states:
              FALLBACK:
                formula: last_valid_state if is_within_grace_period else 'unknown'
            variables:
              last_valid_state:
                formula: metadata(state, 'last_valid_state')
                alternate_states:
                  FALLBACK: unknown
              last_valid_changed:
                formula: metadata(state, 'last_valid_changed')
                alternate_states:
                  FALLBACK: unknown
              panel_status:
                formula: binary_sensor.panel_status
              panel_offline_minutes:
                formula: minutes_between(metadata(binary_sensor.panel_status, 'last_changed'), utc_now()) if not panel_status else 0
                alternate_states:
                  FALLBACK: 0
              is_within_grace_period:
                formula: last_valid_state is not None and last_valid_state != 'unknown' and last_valid_changed != 'unknown' and not panel_status and panel_offline_minutes < energy_grace_period_minutes
                alternate_states:
                  FALLBACK: false
            attributes:
              energy_grace_period_minutes_is: energy_grace_period_minutes
              grace_period_remaining:
                formula: round(max(0, energy_grace_period_minutes - panel_offline_minutes), 1) if is_within_grace_period else 0
                alternate_states:
                  FALLBACK: N/A
        variables:
          energy_grace_period_minutes: 2
        """
        return parse_yaml_to_sensor_config(yaml_content)

    def test_extract_all_sensor_formulas(self):
        """Test that all formulas are extracted from sensor configuration."""
        # This method needs to be implemented
        all_formulas = self.ast_service._extract_all_sensor_formulas(self.span_sensor_config)

        expected_formulas = {
            "main": "state",
            "main_alt_FALLBACK": "last_valid_state if is_within_grace_period else 'unknown'",
            "variable_last_valid_state": "metadata(state, 'last_valid_state')",
            "variable_last_valid_state_alt_FALLBACK": "unknown",
            "variable_last_valid_changed": "metadata(state, 'last_valid_changed')",
            "variable_last_valid_changed_alt_FALLBACK": "unknown",
            "variable_panel_status": "binary_sensor.panel_status",
            "variable_panel_offline_minutes": "minutes_between(metadata(binary_sensor.panel_status, 'last_changed'), utc_now()) if not panel_status else 0",
            "variable_panel_offline_minutes_alt_FALLBACK": "0",
            "variable_is_within_grace_period": "last_valid_state is not None and last_valid_state != 'unknown' and last_valid_changed != 'unknown' and not panel_status and panel_offline_minutes < energy_grace_period_minutes",
            "variable_is_within_grace_period_alt_FALLBACK": "false",
            "attribute_energy_grace_period_minutes_is": "energy_grace_period_minutes",
            "attribute_grace_period_remaining": "round(max(0, energy_grace_period_minutes - panel_offline_minutes), 1) if is_within_grace_period else 0",
            "attribute_grace_period_remaining_alt_FALLBACK": "N/A"
        }

        assert all_formulas == expected_formulas, f"Formula extraction mismatch. Got: {all_formulas}"

    def test_build_binding_plan_for_formulas(self):
        """Test binding plan construction for various formulas."""
        # Test main formula plan
        main_plan = self.ast_service.build_binding_plan("state")
        assert "state" in main_plan.names
        assert main_plan.strategies["state"] == "ha_state"
        assert main_plan.has_metadata is False

        # Test metadata formula plan
        metadata_plan = self.ast_service.build_binding_plan("metadata(state, 'last_valid_state')")
        assert main_plan.has_metadata is True
        assert ("state", "last_valid_state") in metadata_plan.metadata_calls

        # Test complex formula plan
        complex_plan = self.ast_service.build_binding_plan(
            "last_valid_state is not None and panel_offline_minutes < energy_grace_period_minutes"
        )
        assert "last_valid_state" in complex_plan.names
        assert "panel_offline_minutes" in complex_plan.names
        assert "energy_grace_period_minutes" in complex_plan.names

        # Verify plan caching
        plan_copy = self.ast_service.build_binding_plan("state")
        assert plan_copy is main_plan, "Plans should be cached and reused"

    def test_metadata_calls_extraction(self):
        """Test that metadata function calls are properly extracted."""
        analysis = self.ast_service.analyze_complete_sensor(self.span_sensor_config)

        expected_metadata_calls = [
            ("state", "last_valid_state"),
            ("state", "last_valid_changed"),
            ("binary_sensor.panel_status", "last_changed")
        ]

        for expected_call in expected_metadata_calls:
            assert expected_call in analysis.metadata_calls, f"Missing metadata call: {expected_call}"
```

### Test 2: Minimal Context Preparation Validation

```python
class TestMinimalContextPreparation:
    """Test Component 2: Minimal Context Preparation with Binding Plans"""

    def setup_method(self):
        """Setup test environment."""
        self.ast_service = FormulaASTAnalysisService()
        self.span_sensor_config = self._load_span_test_config()

    def test_prepare_minimal_layer(self):
        """Test minimal context layer preparation from binding plan."""
        # Create context and plan
        ctx = HierarchicalContextDict("test_sensor")
        plan = self.ast_service.build_binding_plan("sensor.power * efficiency_factor")

        # Prepare minimal layer
        _prepare_minimal_layer(ctx, plan)

        # Verify only plan names are in context
        assert "sensor.power" in ctx
        assert "efficiency_factor" in ctx
        assert len([k for k in ctx.keys() if not k.startswith("_")]) == 2

        # Verify all are lazy ReferenceValue objects
        assert isinstance(ctx.get("sensor.power"), ReferenceValue)
        assert ctx.get("sensor.power").value is None  # Lazy
        assert isinstance(ctx.get("efficiency_factor"), ReferenceValue)
        assert ctx.get("efficiency_factor").value is None  # Lazy

    def test_lazy_resolution_on_access(self):
        """Test that values are resolved lazily on first access."""
        ctx = HierarchicalContextDict("test_sensor")
        plan = BindingPlan(
            names=frozenset(["sensor.power", "literal_100"]),
            has_metadata=False,
            has_collections=False,
            strategies={
                "sensor.power": "ha_state",
                "literal_100": "literal"
            }
        )

        # Prepare minimal layer with lazy resolver
        lazy_resolver = LazyResolver(self.hass, self.data_provider)
        _prepare_minimal_layer_with_resolver(ctx, plan, lazy_resolver)

        # Before access - values are None
        assert ctx.get("sensor.power").value is None

        # First access triggers resolution
        power_value = lazy_resolver.resolve_if_needed(ctx, "sensor.power")
        assert power_value is not None
        assert ctx.get("sensor.power").value == power_value  # Now memoized

        # Second access uses memoized value
        power_value2 = lazy_resolver.resolve_if_needed(ctx, "sensor.power")
        assert power_value2 == power_value  # Same value, no re-resolution

    def test_context_layer_structure(self):
        """Test hierarchical context layer structure."""
        sensor_analysis = self.ast_service.analyze_complete_sensor(self.span_sensor_config)
        complete_context = self.context_builder.build_complete_context(sensor_analysis)

        # Verify layer names and structure
        layer_info = complete_context.get_layer_info()
        expected_layers = ["dependencies", "literals"]

        for expected_layer in expected_layers:
            assert expected_layer in layer_info, f"Missing layer: {expected_layer}"

        # Verify layer scoping (literals should override dependencies if same name)
        if "literal_unknown" in complete_context and "unknown" in complete_context:
            # Literals layer should take precedence
            assert complete_context.get("literal_unknown").value == "unknown"

    def test_context_completeness_validation(self):
        """Test that context contains all expected variables from YAML."""
        sensor_analysis = self.ast_service.analyze_complete_sensor(self.span_sensor_config)
        complete_context = self.context_builder.build_complete_context(sensor_analysis)

        # Create validator
        validator = ASTContextValidator()
        validation_result = validator.validate_context_completeness(complete_context, self.span_sensor_config)

        assert validation_result.is_valid(), f"Context validation failed: {validation_result.errors}"
        assert len(validation_result.warnings) == 0, f"Context validation warnings: {validation_result.warnings}"
```

### Test 3: Evaluation Consistency with Binding Plans

```python
class TestASTEvaluationConsistency:
    """Test Component 3: AST Evaluation Engine"""

    def setup_method(self):
        """Setup unified AST evaluation pipeline."""
        self.pipeline = UnifiedASTEvaluationPipeline()
        self.span_sensor_config = self._load_span_test_config()

    def test_unified_evaluation_pipeline(self):
        """Test complete unified AST evaluation pipeline."""
        # Mock Home Assistant state for testing
        mock_states = {
            "sensor.air_conditioner_energy_produced_2": MockState(
                entity_id="sensor.air_conditioner_energy_produced_2",
                state=None,  # Simulating offline panel
                attributes={
                    "last_valid_state": "unknown",  # No previous valid state
                    "last_valid_changed": "2025-01-01T12:00:00+00:00"
                }
            ),
            "binary_sensor.panel_status": MockState(
                entity_id="binary_sensor.panel_status",
                state="off",  # Panel offline
                attributes={
                    "last_changed": "2025-01-01T11:59:00+00:00"  # 1 minute ago
                }
            )
        }

        # Execute unified pipeline
        with mock_hass_states(mock_states):
            result = self.pipeline.evaluate_sensor_complete(self.span_sensor_config)

        # Verify main result
        assert result.main_result.success == False, "Main formula should fail with None state"

        # Verify alternate state result
        assert result.alternate_result.success == True, "Alternate state should succeed"
        assert result.alternate_result.value == "unknown", "Should return 'unknown' when grace period not active"

        # Verify attribute results
        assert "energy_grace_period_minutes_is" in result.attribute_results
        assert result.attribute_results["energy_grace_period_minutes_is"] == 2

    def test_context_inheritance_guarantee(self):
        """Test that all evaluation phases receive identical context."""
        sensor_analysis = self.pipeline.ast_service.analyze_complete_sensor(self.span_sensor_config)
        complete_context = self.pipeline.context_builder.build_complete_context(sensor_analysis)

        # Capture context at different evaluation phases
        contexts_captured = []

        # Mock evaluator to capture contexts
        original_evaluate = self.pipeline.evaluator.evaluate_with_ast_context
        def capture_context_evaluate(formula, context):
            contexts_captured.append({
                "formula": formula,
                "context_id": id(context),
                "context_keys": set(context.keys()),
                "last_valid_state_exists": "last_valid_state" in context,
                "last_valid_state_value": context.get("last_valid_state")
            })
            return original_evaluate(formula, context)

        self.pipeline.evaluator.evaluate_with_ast_context = capture_context_evaluate

        # Execute evaluation
        with mock_hass_states({}):
            result = self.pipeline.evaluate_sensor_complete(self.span_sensor_config)

        # Verify all phases received identical context
        assert len(contexts_captured) >= 2, "Should capture context from multiple evaluation phases"

        first_context_id = contexts_captured[0]["context_id"]
        for captured in contexts_captured:
            assert captured["context_id"] == first_context_id, "All phases should receive same context object"
            assert captured["last_valid_state_exists"], "All phases should have last_valid_state variable"
            assert isinstance(captured["last_valid_state_value"], ReferenceValue), "Should be ReferenceValue object"

    def test_lazy_value_resolution(self):
        """Test that values are resolved lazily when accessed."""
        sensor_analysis = self.pipeline.ast_service.analyze_complete_sensor(self.span_sensor_config)
        complete_context = self.pipeline.context_builder.build_complete_context(sensor_analysis)

        # Initially, all dependency values should be None (lazy)
        last_valid_state_ref = complete_context.get("last_valid_state")
        assert last_valid_state_ref.value is None, "Should start with lazy value (None)"

        # After evaluation, values should be resolved
        with mock_hass_states(self._get_mock_states()):
            result = self.pipeline.evaluator.evaluate_with_ast_context(
                "last_valid_state if is_within_grace_period else 'unknown'",
                complete_context
            )

        # Values should now be resolved
        last_valid_state_ref_after = complete_context.get("last_valid_state")
        assert last_valid_state_ref_after.value is not None, "Value should be resolved after evaluation"
```

### Test 4: Architecture Consistency Validation (Pipeline preserved)

```python
class TestArchitecturalConsistency:
    """Test architectural consistency and integration."""

    def test_ast_chain_integrity(self):
        """Test that AST chain is never broken: Parse-Once → Context-Once → Evaluate-Many."""
        pipeline = UnifiedASTEvaluationPipeline()

        # Verify component dependencies
        assert pipeline.context_builder.ast_service is pipeline.ast_service, "Context builder should use same AST service"
        assert pipeline.evaluator.ast_service is pipeline.ast_service, "Evaluator should use same AST service"

        # Verify no independent context creation
        with pytest.raises(ValueError, match="Context must be built from AST analysis"):
            # This should fail - no independent context creation allowed
            independent_context = HierarchicalContextDict("independent")
            pipeline.evaluator.evaluate_with_ast_context("test", independent_context)

    def test_span_integration_problem_solved(self):
        """Test that the original SPAN integration problem is solved."""
        pipeline = UnifiedASTEvaluationPipeline()
        span_config = self._load_span_test_config()

        # Simulate the original problem scenario
        mock_states = {
            "sensor.air_conditioner_energy_produced_2": MockState(
                entity_id="sensor.air_conditioner_energy_produced_2",
                state=None,  # This triggered the original problem
                attributes={
                    "last_valid_state": "3707.6",  # This should be accessible
                    "last_valid_changed": "2025-01-01T11:45:00+00:00"
                }
            ),
            "binary_sensor.panel_status": MockState(
                entity_id="binary_sensor.panel_status",
                state="off",
                attributes={"last_changed": "2025-01-01T11:59:00+00:00"}
            )
        }

        with mock_hass_states(mock_states):
            result = pipeline.evaluate_sensor_complete(span_config)

        # The original problem: last_valid_state = None in alternate state handler
        # Should now be solved: last_valid_state should be accessible
        assert result.alternate_result.success == True, "Alternate state evaluation should succeed"

        # With 1 minute offline and 2 minute grace period, should return last_valid_state
        assert result.alternate_result.value == "3707.6", "Should return last_valid_state during grace period"

    def test_performance_characteristics(self):
        """Test performance characteristics of AST-driven architecture."""
        pipeline = UnifiedASTEvaluationPipeline()
        span_config = self._load_span_test_config()

        # First evaluation - should parse and cache
        start_time = time.time()
        result1 = pipeline.evaluate_sensor_complete(span_config)
        first_eval_time = time.time() - start_time

        # Second evaluation - should use cached AST analysis
        start_time = time.time()
        result2 = pipeline.evaluate_sensor_complete(span_config)
        second_eval_time = time.time() - start_time

        # Second evaluation should be faster due to AST caching
        assert second_eval_time < first_eval_time, "Second evaluation should be faster due to AST caching"

        # Verify cache hits
        assert pipeline.ast_service._cache_hits > 0, "Should have AST cache hits"
```

### Test 5: Error Handling and Edge Cases

```python
class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge cases in AST-driven architecture."""

    def test_malformed_formula_handling(self):
        """Test handling of malformed formulas in AST analysis."""
        malformed_config = SensorConfig(
            unique_id="test_sensor",
            formula="invalid syntax +++",  # Malformed formula
            variables={"test_var": {"formula": "another bad formula ((("}}
        )

        ast_service = FormulaASTAnalysisService()

        # Should handle malformed formulas gracefully
        analysis = ast_service.analyze_complete_sensor(malformed_config)

        # Should still create analysis object with error information
        assert isinstance(analysis, CompleteSensorAnalysis)
        assert analysis.sensor_id == "test_sensor"
        # Malformed formulas should be marked as such
        assert any("error" in str(formula_analysis) for formula_analysis in analysis.analysis.values())

    def test_missing_dependencies_handling(self):
        """Test handling of missing dependencies during evaluation."""
        config_with_missing_deps = SensorConfig(
            unique_id="test_sensor",
            formula="nonexistent_variable + another_missing_var"
        )

        pipeline = UnifiedASTEvaluationPipeline()

        # Should create context with missing dependencies as ReferenceValue shells
        sensor_analysis = pipeline.ast_service.analyze_complete_sensor(config_with_missing_deps)
        complete_context = pipeline.context_builder.build_complete_context(sensor_analysis)

        # Missing dependencies should exist in context with None values
        assert "nonexistent_variable" in complete_context
        assert "another_missing_var" in complete_context
        assert complete_context.get("nonexistent_variable").value is None
        assert complete_context.get("another_missing_var").value is None

    def test_circular_dependency_detection(self):
        """Test detection of circular dependencies in variable definitions."""
        circular_config = SensorConfig(
            unique_id="test_sensor",
            formula="var_a + var_b",
            variables={
                "var_a": {"formula": "var_b + 1"},
                "var_b": {"formula": "var_a + 1"}  # Circular dependency
            }
        )

        ast_service = FormulaASTAnalysisService()

        # Should detect circular dependencies during analysis
        with pytest.raises(CircularDependencyError):
            analysis = ast_service.analyze_complete_sensor(circular_config)
```

### Test 6: Boolean False Preservation

```python
class TestBooleanFalsePreservation:
    """Test that boolean False values are preserved through evaluation pipeline."""

    def test_false_not_converted_to_none(self):
        """Test that False values are not converted to None in result processing."""
        # Create a computed variable that evaluates to False
        config = SensorConfig(
            unique_id="test_false_preservation",
            formula="state",
            variables={
                "is_within_grace": {
                    "formula": "False"  # Explicitly False
                }
            },
            attributes={
                "grace_status": {
                    "formula": "is_within_grace"  # Should be False, not None
                }
            }
        )

        # Evaluate with binding plans
        plan = self.ast_service.build_binding_plan("is_within_grace")
        ctx = HierarchicalContextDict("test")
        _prepare_minimal_layer(ctx, plan)

        # Resolve the variable
        ctx.set("is_within_grace", ReferenceValue("computed", False))

        # Evaluate attribute
        result = evaluate_attribute("grace_status", ctx)

        # Verify False is preserved
        assert result is False, "False should not be converted to None"
        assert result is not None, "False must remain False"

    def test_phase_4_preserves_false(self):
        """Test that Phase 4 result consolidation preserves False."""
        # Mock a False result from Phase 3
        phase3_result = EvaluationResult(success=True, value=False)

        # Process through Phase 4
        final_result = process_phase_4_result(phase3_result)

        # Verify False is preserved
        assert final_result.value is False
        assert final_result.value is not None
```

## Implementation Checklist

### Phase 1: Core Data Structures

- [ ] Implement `BindingPlan` dataclass with proper typing
- [ ] Add `build_binding_plan()` method to `FormulaASTAnalysisService`
- [ ] Implement `_infer_strategies()` for resolution strategy determination
- [ ] Add plan caching mechanism

### Phase 2: Minimal Context Preparation

- [ ] Implement `_prepare_minimal_layer()` function
- [ ] Create `LazyResolver` class with memoization
- [ ] Add cycle boundary management for memoization
- [ ] Ensure only plan-specified names are added to context

### Phase 3: AST Service Enhancement

- [ ] Migrate collection parsing from `DependencyParser` to AST service
- [ ] Implement collection query normalization
- [ ] Add metadata call extraction to AST analysis
- [ ] Ensure all formula analysis goes through AST service

### Phase 4: Testing Infrastructure

- [ ] Create mock Home Assistant state system
- [ ] Implement SPAN integration test fixtures
- [ ] Create performance benchmarking tests
- [ ] Add error handling test cases

### Phase 5: Integration and Validation

- [ ] Run complete test suite against SPAN integration
- [ ] Validate performance characteristics
- [ ] Verify architectural consistency
- [ ] Document any remaining gaps or issues

## Success Criteria

1. **Complete Context Guarantee**: All variables exist in context before evaluation
2. **Perfect Context Inheritance**: All evaluation phases receive identical context
3. **Zero Missing Variables**: No more `last_valid_state = None` errors
4. **Performance Improvement**: AST caching provides measurable performance gains
5. **Architectural Consistency**: Parse-Once → Context-Once → Evaluate-Many verified
6. **SPAN Integration Success**: Original problem completely resolved

This testing framework validates the plan-driven lazy approach, keeps the proven 0–4 phase pipeline, and ensures the
`False`-to-`None` regression cannot reoccur.
