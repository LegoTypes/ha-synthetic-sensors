# Binding Plan Architecture - Standard Implementation

## Overview

The HA Synthetic Sensors system uses AST-based binding plans and lazy context population as the **standard and only** approach
for formula evaluation. There are no backward compatibility modes, feature flags, or legacy routes.

## When Does "Parse Once" Happen?

**Parse-once happens during EVALUATION, not during YAML import.** Here's the precise flow:

### Caches Are NOT Persistent

**Binding plans and AST analysis are NOT persisted across server reboots.** They exist only in memory:

- Each server restart starts with empty caches
- First evaluation after reboot triggers fresh AST parsing
- Caches rebuild automatically as formulas are evaluated
- No disk persistence - purely in-memory optimization

### Timeline of Events

1. **YAML Import Time** (ConfigManager.load_from_yaml):
   - YAML is parsed into Python dictionaries
   - SensorConfig objects are created
   - Basic validation occurs (circular dependencies, schema validation)
   - **NO AST parsing happens here** - formulas are stored as strings

2. **First Evaluation Time** (when sensor updates):
   - Formula string is sent to evaluator
   - `build_binding_plan(formula)` is called
   - This triggers `get_formula_analysis(formula)`
   - **FIRST AND ONLY AST PARSE happens here**
   - Result is cached forever

3. **Subsequent Evaluations**:
   - Same formula string is sent to evaluator
   - `build_binding_plan(formula)` finds cached plan
   - `get_formula_analysis(formula)` returns cached analysis
   - **NO PARSING** - just cache lookup

## What is a Binding Plan?

A **Binding Plan** is a lightweight, immutable data structure that describes exactly what a formula needs to execute:

```python
@dataclass(frozen=True)
class BindingPlan:
    names: frozenset[str]          # All variable/entity names referenced
    has_metadata: bool              # Does it call metadata() function?
    has_collections: bool           # Does it use sum/avg/min/max/count?
    strategies: dict[str, str]      # How to resolve each name
    collection_queries: list[str]   # Normalized collection queries
    metadata_calls: list[tuple]     # Metadata function calls
```

### Role of the Binding Plan

1. **Describes Requirements**: Lists every name the formula will need
2. **Specifies Resolution Strategy**: How to get each value (HA state, data provider, literal, etc.)
3. **Enables Optimization**: Allows preparing only what's needed
4. **Supports Caching**: Immutable structure can be cached and reused

### Example

For formula: `sensor.power * efficiency_factor + 100`

The binding plan would be:

```python
BindingPlan(
    names={'sensor.power', 'efficiency_factor'},
    has_metadata=False,
    has_collections=False,
    strategies={
        'sensor.power': 'ha_state',
        'efficiency_factor': 'data_provider'
    }
)
```

## Binding Plan Principles

- **Single Implementation Path**: All formula evaluation uses binding plans
- **No Feature Flags**: No `_use_binding_plans` or similar flags exist
- **No Legacy Routes**: All old approaches have been removed
- **Clean Architecture**: One consistent approach throughout the codebase

### Binding Plan Architecture

Every formula evaluation follows this pattern:

```python
# 1. Build binding plan from AST analysis
plan = self._ast_service.build_binding_plan(config.formula)

# 2. Prepare minimal context layer with only required names
prepare_minimal_layer(eval_context, plan)

# 3. Store plan for use by phases
eval_context["_current_binding_plan"] = plan

# 4. Proceed with standard evaluation pipeline
resolution_result = self._variable_resolution_phase.resolve_all_references_with_ha_detection(...)
```

## Implementation Details

### BindingPlan Data Structure

```python
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

### Minimal Context Preparation

The `prepare_minimal_layer` function creates only the variables needed by the current formula:

- Creates lazy `ReferenceValue` objects with `value=None`
- Stores resolution strategies as infrastructure keys (prefixed with `_`)
- Enables lazy resolution on first access
- Reduces memory usage and object churn

## Lazy Resolution Implementation Complete ✅

The implementation now has **BOTH** stages fully working:

### Stage 1: Minimal Context (IMPLEMENTED ✅)

```python
def prepare_minimal_layer(ctx, plan, lazy_resolver=None):
    for name in plan.names:
        if name not in ctx:  # Don't override existing
            # Create ReferenceValue with value=None (lazy placeholder)
            ref_value = ReferenceValue(reference=name, value=None)
            ctx[name] = ref_value

    # Store lazy resolver for on-demand resolution
    if lazy_resolver:
        ctx["_lazy_resolver"] = lazy_resolver
        lazy_resolver.start_new_cycle()
```

This creates **minimal** context because:

- Only names in the binding plan are added
- Unused variables are not created
- Context is smaller and more efficient

### Stage 2: Lazy Resolution (FULLY IMPLEMENTED ✅)

True lazy resolution is now implemented with the LazyResolver:

```python
class LazyResolver:
    def resolve_if_needed(self, ctx, name):
        # Check cycle cache first
        cache_key = f"{self._cycle_id}:{name}"
        if cache_key in self._cycle_cache:
            return self._cycle_cache[cache_key]

        # Get ReferenceValue and resolve if needed
        ref_value = ctx.get(name)
        if ref_value.value is None:  # Lazy - needs resolution
            strategy = ctx.get(f"_strategy_{name}", "ha_state")
            resolved = self._resolve_by_strategy(name, strategy)
            ref_value._value = resolved  # Update in place
            self._cycle_cache[cache_key] = resolved

        return ref_value.value
```

**Current behavior**: Values are resolved **only when accessed** with memoization per cycle

### Lazy Resolution Benefits Achieved

1. **On-Demand Resolution**: Values resolved only when actually accessed
2. **Cycle Memoization**: Once resolved, cached for remainder of evaluation cycle
3. **Batch Optimization**: HA entities pre-loaded efficiently
4. **Memory Efficiency**: Unused variables never resolved
5. **Performance Gains**: Eliminates unnecessary state lookups

## The Complete Flow

```text
graph TD
    A[Server Start/Restart] -->|Empty caches| B[YAML Import]
    B -->|Stores formula strings| C[Sensor Creation]
    C -->|First evaluation after restart| D[build_binding_plan]
    D -->|Cache miss| E[AST Parse & Analysis]
    E -->|Cache in memory| F[Binding Plan Created]
    D -->|Cache hit (same session)| G[Return Cached Plan]
    F --> H[prepare_minimal_layer]
    G --> H
    H -->|Creates shells| I[Minimal Context with ReferenceValues]
    I -->|Currently immediate| J[Variable Resolution Phase]
    J -->|Resolves all values| K[Formula Execution]

    style E fill:#ffeb3b
    style E stroke:#f57c00
    style E stroke-width:3px

    style A fill:#ff6b6b
    style A stroke:#c92a2a
```

## Benefits of Complete Implementation

With full lazy resolution implementation, we achieve:

1. **Parse Once Per Session**: AST parsing happens once per unique formula during each server session
2. **Minimal Context**: Only required variables are prepared
3. **True Lazy Resolution**: Values resolved only when accessed with cycle memoization
4. **Batch Optimization**: HA entities pre-loaded for efficient access
5. **Clean Architecture**: No backward compatibility, single path
6. **Performance Gains**: Significant reduction in unnecessary state lookups
7. **Fast Cache Rebuild**: After restart, caches rebuild quickly as sensors evaluate

### Cache Lifecycle

- **Server Start**: All caches empty (`_analysis_cache = {}`, `_plan_cache = {}`)
- **First Evaluation**: Triggers AST parse, creates binding plan, caches both
- **During Session**: All subsequent evaluations use cached plans (microsecond lookups)
- **Server Restart**: Caches lost, process repeats
- **No Persistence Overhead**: No disk I/O, no serialization costs

## Performance Benefits

The binding plan approach provides significant performance improvements:

1. **Parse Once**: AST analysis cached per formula (eliminates redundant parsing)
2. **Minimal Context**: Only required variables are prepared (reduces memory usage)
3. **Lazy Resolution**: Values resolved only when needed with cycle memoization
4. **Batch Lookups**: HA entities pre-loaded efficiently per evaluation cycle
5. **Object Reuse**: Reduced Python object churn per cycle
6. **Cache Efficiency**: Better utilization of compilation cache
7. **Boolean Safety**: Proper `is None` checks preserve False values

## Lazy Resolution: IMPLEMENTED ✅

Lazy resolution is now **fully implemented** and provides:

- ✅ Deferred Home Assistant state lookups until needed
- ✅ Skip resolution for variables in unused conditional branches
- ✅ Reduced evaluation time for complex formulas
- ✅ Better caching strategies with cycle memoization
- ✅ Batch HA entity pre-loading for efficiency
- ✅ Memory usage optimization

The binding plan architecture with lazy resolution provides a **production-ready foundation** for efficient formula evaluation.

## Testing

All tests assume binding plans are enabled:

```python
def test_binding_plan_optimization_always_enabled(self, evaluator):
    """Test that binding plan optimization is always enabled (no backward compatibility)."""
    # Binding plans are now always used - no flag needed
    assert hasattr(evaluator, '_ast_service')
    assert evaluator._ast_service is not None
```
