# Cache Behavior and Data Lifecycle

This document describes how the two-tier caching system works in the synthetic sensors package, the data lifecycle from
backing entities through sensor evaluation, and how cross-sensor resolution is affected by caching.

## Overview

The synthetic sensors system uses a **two-tier caching architecture** to optimize both formula compilation and evaluation
performance. Understanding how this caching works is critical for proper integration, testing, and troubleshooting.

## Two-Tier Cache Architecture

### Cache Layer 1: Formula Compilation Cache

**Purpose**: Caches pre-parsed `SimpleEval` AST expressions to avoid re-parsing formulas **Performance**: 5-20x faster
formula evaluation (measured 7.5-19.7x improvement) **Scope**: Per formula string (independent of context/variables)
**Invalidation**: Only when formulas change or configuration reloads

```python
# Example: Formula "a + b * 2" is parsed once, reused for all evaluations
compiled_formula = FormulaCompilationCache.get_compiled_formula("a + b * 2")
result1 = compiled_formula.evaluate({"a": 1, "b": 2})  # 5.0
result2 = compiled_formula.evaluate({"a": 10, "b": 5}) # 20.0
# Same parsed AST used for both evaluations
```

**Key Characteristics**:

- **Never cleared during update cycles** (preserves performance benefits)
- **LRU eviction** when cache size limit reached (default: 1000 entries)
- **SHA256 cache keys** based on formula text
- **Independent of evaluation context** (variables, state values)
- **Statistics available** via `get_compilation_cache_stats()`

### Cache Layer 2: Evaluation Result Cache (Cycle-Scoped)

**Purpose**: Caches formula evaluation results to prevent redundant calculations **Scope**: Per unique combination of
formula + context values **Invalidation**: Cycle-scoped behavior (disabled during updates, enabled after)

**Cycle-Scoped Behavior**:

- **During update cycles**: Cache disabled → Always fresh evaluation
- **After update cycles**: Cache enabled → Serves external consumers
- **No TTL needed**: Update cycles define cache validity, not time

```python
# During HA update cycle (integration data changes)
start_update_cycle()
result = evaluate_formula("state * 1.1", {"state": 1000})  # Fresh evaluation
end_update_cycle()

# External access (templates, automations)
result = evaluate_formula("state * 1.1", {"state": 1000})  # Cached result
```

### What Gets Cached

**Formula Compilation Cache**:

- Pre-parsed `SimpleEval` AST expressions
- Math function bindings

- Formula syntax validation results

**Evaluation Result Cache**:

- Formula evaluation results based on input values
- Cross-sensor reference results
- Backing entity state lookups
- Attribute calculations (cached independently from main formulas)

### What Does NOT Get Cached

- Raw backing entity data from integration APIs
- Home Assistant entity states (always fresh)
- Configuration data (YAML, sensor definitions)
- Dependency mappings
- Data provider callback results

## Data Lifecycle in Home Assistant

### Normal HA Update Cycle with Two-Tier Caching

```text
1. Integration updates backing entity data
   ↓
2. Integration calls async_update_sensors_for_entities()
   ↓
3. SensorManager.start_update_cycle() → Disables evaluation result cache
   ↓
4. Formula evaluation process:
   a) Compilation cache: Retrieves pre-parsed AST (fast)
   b) Evaluation cache: Bypassed (disabled) → Fresh evaluation
   ↓
5. Fresh result calculated using current backing entity data
   ↓
6. SensorManager.end_update_cycle() → Re-enables evaluation result cache
   ↓

7. Sensor state updated in HA
   ↓
8. External consumers (templates, automations) get cached results
```

### Cache Behavior During Different Phases

**Integration Update Phase** (Cache Layer 2 Disabled):

```python

# Integration updates data and triggers sensor updates
await sensor_manager.async_update_sensors_for_entities({"backing_power"})

# Inside update cycle:
start_update_cycle()  # Disables evaluation result cache

result = evaluate_formula("state * 1.1", {"state": 1500})  # Always fresh
end_update_cycle()    # Re-enables evaluation result cache
```

**External Access Phase** (Cache Layer 2 Enabled):

```python
# Template or automation requests sensor value
result = evaluate_formula("state * 1.1", {"state": 1500})  # Cached result
# Compilation cache: AST retrieved (fast)


# Evaluation cache: Result retrieved (very fast)
```

### Cache Invalidation Strategy

**Formula Compilation Cache (Layer 1)**:

- **Invalidated only when**: Formula text changes, configuration reloads
- **Never invalidated during**: Update cycles, backing entity changes
- **Cache keys**: SHA256 hash of formula string
- **Purpose**: Preserve parsing performance across all evaluations

**Evaluation Result Cache (Layer 2)**:

- **Cycle-scoped invalidation**: Disabled during updates, enabled after
- **Cache keys**: Formula text + context values + variables
- **Context-sensitive**: Different inputs = different cache entries
- **Purpose**: Prevent redundant calculations for external consumers

## Cross-Sensor Resolution and Caching

### How Cross-Sensor References Work

When `sensor_a` references `sensor_b` in a formula:

1. **Dependency tracking** ensures `sensor_a` updates when `sensor_b` changes
2. **Evaluation order** processes `sensor_b` before `sensor_a`
3. **Cache keys** for `sensor_a` include `sensor_b`'s current result
4. **Cache invalidation** occurs when `sensor_b`'s result changes

### Cross-Sensor Cache Behavior

````yaml
# Example: sensor_a references sensor_b
sensors:
  power_base:
    formula: "state * 1.1"  # Uses backing entity

  power_derived:
    formula: "power_base * 0.95"  # References power_base
1. Backing entity for `power_base` changes
2. `power_base` cache miss → recalculated
3. `power_derived` dependency triggered
4. `power_derived` cache miss (because `power_base` result changed)
5. `power_derived` recalculated with new `power_base` value

## Backing Entity Integration

### Virtual Backing Entities

Virtual backing entities (integration-provided data) work through the data provider callback:

```python
def data_provider_callback(entity_id: str) -> DataProviderResult:
    # Called on every formula evaluation
    # NOT cached at this level
    return {"value": current_api_value, "exists": True}
````

- Cache operates above this level (on formula results)

### State Token Resolution

The `state` token in formulas resolves through:

1. **Context check** (for attribute formulas)

2. **Backing entity lookup** (for main formulas with sensor-to-backing mapping)
3. **Previous value fallback** (for sensors without backing entities)

**Cache interaction:**

- Formula result using resolved state IS cached
- Cache keys include resolved state values in context

## Cache Management and Clearing

### Automatic Cache Clearing

**Formula Compilation Cache (Layer 1)**:

- **Configuration reloads**: All compiled formulas cleared
- **Formula updates**: Specific formula cleared via `force_update_formula()`
- **Integration restart**: Full cache reset

**Evaluation Result Cache (Layer 2)**:

- **Update cycles**: Automatically disabled/enabled (not cleared)
- **Configuration reloads**: All evaluation results cleared
- **Integration restart**: Full cache reset

### Manual Cache Management

**Clear Formula Compilation Cache**:

```python
# Clear all compiled formulas
sensor_manager._evaluator.clear_compiled_formulas()

# Get compilation cache statistics
stats = sensor_manager._evaluator.get_compilation_cache_stats()
print(f"Compiled formulas: {stats['total_entries']}")

print(f"Hit rate: {stats['hit_rate']:.1f}%")
```

**Clear Evaluation Result Cache**:

```python
# Clear all cached evaluation results
sensor_manager._evaluator.clear_cache()


# Get evaluation cache statistics
stats = sensor_manager._evaluator.get_cache_stats()
print(f"Cache hit rate: {stats['hit_rate']:.1f}%")

```

### Cache Statistics and Monitoring

**Formula Compilation Cache Metrics**:

- `total_entries`: Number of compiled formulas cached
- `hits`: Cache hits (formula retrieved from cache)
- `misses`: Cache misses (formula compiled and cached)

- `hit_rate`: Percentage of requests served from cache
- `max_entries`: Maximum cache size before LRU eviction

**Evaluation Result Cache Metrics**:

- `hit_rate`: Percentage of evaluations served from cache
- `cache_size`: Current number of cached results
- `total_evaluations`: Total formula evaluations performed

## Testing Implications

### Test Environment Considerations

**Modern Test Pattern (Recommended)**:

```python
# Update backing entity data AND trigger proper update flow
await hybrid_test.async_set_backing_entity_state("entity_id", new_value)

# This automatically triggers async_update_sensors_for_entities()
# which handles cycle-scoped cache behavior correctly
```

**Legacy Test Pattern (No Longer Needed)**:

```python
# Old approach that required manual cache clearing

hybrid_test.set_backing_entity_state("entity_id", new_value)
sensor_manager._evaluator.clear_cache()  # No longer needed
await hybrid_test.trigger_sensor_updates()
```

### Cache Behavior in Tests

**Formula Compilation Cache**:

- **Persists across test cases** (improves test performance)
- **Only cleared on configuration reloads**
- **No impact on test correctness** (independent of context)

**Evaluation Result Cache**:

- **Cycle-scoped behavior works in tests** when using proper APIs
- **Manual clearing only needed** for legacy test patterns

- **Tests should use** `async_set_backing_entity_state()` for realistic behavior

### Why Modern Tests Don't Need Cache Clearing

- **Proper update flow**: `async_update_sensors_for_entities()` handles cache cycles
- **Context changes**: New backing entity values create new cache keys
- **Realistic simulation**: Mirrors real integration behavior

- **Performance benefits**: Compilation cache improves test execution speed

## Troubleshooting Cache Issues

### Symptoms of Cache Problems

**Formula Compilation Issues**:

- Performance degradation over time
- Memory usage growing unexpectedly

- Identical formulas being re-parsed repeatedly

**Evaluation Result Issues**:

- Sensors showing stale values after backing entity changes
- Cross-sensor references not updating when dependencies change
- External consumers getting outdated results during updates

### Diagnostic Steps

1. **Check cache statistics**:

   ```python
   # Formula compilation cache
   comp_stats = evaluator.get_compilation_cache_stats()
   print(f"Compilation hit rate: {comp_stats['hit_rate']:.1f}%")

   # Evaluation result cache
   eval_stats = evaluator.get_cache_stats()
   print(f"Evaluation hit rate: {eval_stats['hit_rate']:.1f}%")
   ```

2. **Verify update cycle behavior**:

   ```python
   # Check if cache is properly disabled during updates


   evaluator.start_update_cycle()  # Should disable evaluation cache
   # ... perform evaluations (should be fresh)
   evaluator.end_update_cycle()    # Should re-enable evaluation cache
   ```

3. **Test with cache clearing** to isolate issues:

   ```python
   # Clear only evaluation results (preserve compilation cache)
   evaluator.clear_cache()

   # Clear only compiled formulas (preserve evaluation results)
   evaluator.clear_compiled_formulas()

   ```

### Common Cache Pitfalls

**Formula Compilation Cache**:

- **Expecting cache clearing during updates** (compilation cache persists)
- **Not accounting for memory usage** with many unique formulas
- **Modifying formulas without clearing compilation cache**

**Evaluation Result Cache**:

- **Testing without proper update cycle simulation**
- **Bypassing `async_update_sensors_for_entities()` in integrations**
- **Expecting immediate cache invalidation** (cycle-scoped, not immediate)
- **Not understanding context-sensitive cache keys**

## Performance Considerations

### Formula Compilation Cache Benefits

- **5-20x faster formula evaluation** (measured 7.5-19.7x improvement)
- **Eliminates AST parsing overhead** for repeated formula usage
- **Reduced CPU usage** for formula-heavy configurations

- **Improved startup time** for integrations with many sensors

### Evaluation Result Cache Benefits

- **Prevents redundant calculations** for external consumers
- **Improves template/automation response time**
- **Reduces sensor update lag** during high-frequency polling
- **Minimizes cross-sensor evaluation cascades**

### Memory Usage and Overhead

**Formula Compilation Cache**:

- **Memory per entry**: ~1-5KB per compiled formula
- **Default limit**: 1000 entries (~1-5MB maximum)

- **LRU eviction**: Least-used formulas removed automatically
- **Recommended monitoring**: Cache hit rate should be >90%

**Evaluation Result Cache**:

- **Memory per entry**: Varies by result size and context
- **Dynamic sizing**: Based on formula complexity and usage patterns
- **Cycle-scoped clearing**: Prevents indefinite growth
- **Overhead**: Cache key computation, context serialization

### Performance Tuning

**Formula Compilation Cache**:

```python
# Adjust cache size for formula-heavy integrations
compilation_cache = FormulaCompilationCache(max_entries=2000)


# Monitor cache effectiveness
stats = evaluator.get_compilation_cache_stats()
if stats['hit_rate'] < 80:

    print("Consider increasing cache size or optimizing formulas")

```

**Evaluation Result Cache**:

```python
# Configure cache behavior via CacheConfig
cache_config = CacheConfig(


    # Cycle-scoped behavior cannot be tuned (always optimal)
    # Focus on monitoring hit rates for external access patterns
)
```

## Integration Best Practices

### For Integration Developers

**Essential Practices**:

1. **Use proper update flow**:

   ```python

   # Correct: Triggers cycle-scoped cache behavior
   await sensor_manager.async_update_sensors_for_entities(changed_entity_ids)


   # Incorrect: Bypasses cache management
   await sensor_manager.async_update_sensors(sensor_configs)

   ```

2. **Monitor formula compilation performance**:

   ```python

   # Check compilation cache effectiveness
   stats = evaluator.get_compilation_cache_stats()
   if stats['hit_rate'] < 90:
       logger.warning("Low formula compilation cache hit rate: %s%%", stats['hit_rate'])
   ```

3. **Optimize formula design for caching**:

   ```python
   # Good: Reusable formula pattern
   formula = "state * efficiency_factor"

   # Avoid: Dynamic formula generation (defeats compilation cache)
   formula = f"state * {efficiency_factor}"  # Creates unique formulas

   ```

4. **Don't manually clear caches** during normal operation
5. **Test with realistic update patterns**

### Cache Strategy for Different Integration Types

**High-Frequency Polling (< 30 seconds)**:

- **Formula compilation cache**: Critical for performance
- **Evaluation result cache**: Reduces external access overhead
- **Monitoring**: Watch for >95% compilation hit rates

**Medium-Frequency Polling (30-300 seconds)**:

- **Balanced caching benefits**: Both layers provide value
- **External consumer efficiency**: Templates get fast responses
- **Memory usage**: Monitor evaluation cache growth

**Event-Driven Integrations**:

- **Compilation cache**: Essential for burst updates
- **Cycle-scoped cache**: Optimal for sporadic updates
- **Performance**: Focus on compilation cache hit rates

### Real-World Example - SPAN Integration

**Before Two-Tier Caching**:

```text
SPAN polling: Every 15 seconds
Issues: Re-parsing formulas, stale data during updates
Performance: Slow, inconsistent
```

**After Two-Tier Caching**:

```text
SPAN polling: Every 15 seconds
Formula compilation: 10x faster evaluation (cached ASTs)
Evaluation results:
  - During SPAN update: Fresh data (cache disabled)
  - External access: Cached results (fast templates/automations)
Result: Always fresh + 10x faster + efficient external access
```

### Troubleshooting and Monitoring

**Cache Health Monitoring**:

```python
def monitor_cache_health(evaluator):
    comp_stats = evaluator.get_compilation_cache_stats()
    eval_stats = evaluator.get_cache_stats()

    print(f"Compilation cache: {comp_stats['hit_rate']:.1f}% hit rate")
    print(f"Evaluation cache: {eval_stats['hit_rate']:.1f}% hit rate")

    if comp_stats['hit_rate'] < 80:
        print("WARNING: Low compilation cache efficiency")
    if eval_stats['hit_rate'] < 50:
        print("INFO: Low evaluation cache usage (may be normal)")
```

**Performance Testing**:

```python
# Test cache disabled vs enabled
evaluator.clear_compiled_formulas()  # Test cold start
start_time = time.perf_counter()
result1 = evaluate_formula(formula, context)
cold_time = time.perf_counter() - start_time

start_time = time.perf_counter()
result2 = evaluate_formula(formula, context)  # Should be cached
warm_time = time.perf_counter() - start_time

improvement = cold_time / warm_time
print(f"Compilation cache improvement: {improvement:.1f}x")
```

## Related Documentation

- [Evaluator Architecture](evaluator_architecture.md) - Details on fo mula evaluation
- [Cross-Sensor Dependencies](cross_sensor_dependencies.md) - Dependency management
- [Integration Guide](Synthetic_Sensors_Integration_Guide.md) - Integration patterns
- [Testing Guide](testing_guide.md) - Test environment considerations
