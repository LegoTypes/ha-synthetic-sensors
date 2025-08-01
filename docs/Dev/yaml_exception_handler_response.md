# Response to YAML Exception Handler Proposal: Computed Variables Alternative

## Executive Summary

The `exception_formula` proposal addresses a real need for declarative error handling, but conflicts with the current
system's pre-evaluation dependency management architecture. Instead, I propose **Computed Variables** - an extension to the
existing variable system that achieves the same goals while working with the current architecture.

## Analysis of Original Proposal Issues

### Architectural Conflict

The `exception_formula` proposal assumes unavailable/unknown values reach the formula evaluation context, but the current
system:

1. **Pre-filters dependencies** in `dependency_management_phase.py`
2. **Returns early** when any dependency is unavailable/unknown
3. **Never reaches simpleeval** if dependencies are problematic

```python
# Current system - happens BEFORE formula evaluation
if unavailable_deps or unknown_deps:
    if unavailable_deps:
        return self._create_unavailable_result(all_problematic_deps)  # Formula never runs
    return self._create_unknown_result(all_problematic_deps)         # Formula never runs
```

### Type Safety Issues

The proposal's examples contain errors that reveal deeper issues:

```yaml
# INCORRECT - This won't work in current system
formula: "if(leg1_energy != 'unavailable', leg1_energy + leg2_energy, 'unknown')"
```

**Problems:**

1. `leg1_energy` is a numeric value (e.g., `1500.0`), not a string `'unavailable'`
2. String comparisons `!= 'unavailable'` will always be true for numbers
3. Mixing strings and numbers breaks simpleeval's type assumptions

## Proposed Solution: Computed Variables

### Core Concept

Extend the existing `variables` system to support formula-based computed variables alongside simple entity mappings and
literals.

### Current Variables (Unchanged)

```python
variables: dict[str, str | int | float]
# str = entity_id mapping
# int/float = literal values
```

### Proposed Variables (Extended)

```python
variables: dict[str, str | int | float | ComputedVariable]
# NEW: ComputedVariable = formula-based computed value
```

## Implementation Design

### 1. Configuration Model Extension

```python
@dataclass
class ComputedVariable:
    """A variable computed from a formula during context building."""
    formula: str
    dependencies: set[str] = field(default_factory=set)

@dataclass
class FormulaConfig:
    # ... existing fields ...
    variables: dict[str, str | int | float | ComputedVariable] = field(default_factory=_default_variables)
```

### 2. YAML Syntax Options

#### Option A: Formula Prefix (Recommended)

```yaml
variables:
  leg1_energy: sensor.circuit_1_energy # Simple entity (unchanged)
  leg2_energy: sensor.circuit_2_energy # Simple entity (unchanged)
  grace_period: 15 # Literal (unchanged)
  recent_enough: "formula:((now() - state.last_changed) / 60) < grace_period" # NEW: Computed
  fallback_total: "formula:leg1_energy + leg2_energy" # NEW: Computed

formula: "if(recent_enough, state, fallback_total)"
```

#### Option B: Object Syntax

```yaml
variables:
  recent_enough:
    formula: "((now() - state.last_changed) / 60) < grace_period"
  fallback_total:
    formula: "leg1_energy + leg2_energy"
```

### 3. Evaluation Flow

```python
def build_evaluation_context(variables):
    context = {}

    # Phase 1: Resolve simple variables (entity mappings & literals)
    for name, value in variables.items():
        if isinstance(value, (str, int, float)):
            context[name] = resolve_simple_variable(value)  # Existing logic

    # Phase 2: Resolve computed variables in dependency order
    for name, value in variables.items():
        if isinstance(value, ComputedVariable):
            try:
                context[name] = evaluate_formula(value.formula, context)
            except Exception:
                # Computed variable failed - propagate unavailable state
                return create_unavailable_result([name])

    return context
```

## Solving the Original Use Cases

### 1. Energy Sensor Grace Period

**Original Problem**: Need to preserve last known values during brief outages.

**Computed Variables Solution**:

```yaml
energy_total:
  name: "Total Energy Consumption"
  formula: "if(recent_enough, state, fallback_value)"
  variables:
    main_meter: sensor.main_meter_energy
    solar_produced: sensor.solar_energy_produced
    grace_period: 15
    recent_enough: "formula:((now() - state.last_changed) / 60) < grace_period"
    fallback_value: "formula:main_meter + solar_produced"
```

**How it works**:

- If `main_meter` or `solar_produced` unavailable → sensor becomes unavailable (existing behavior)
- If all available but state is stale → `recent_enough` = `false`, use `fallback_value`
- If all available and state is recent → `recent_enough` = `true`, use `state`

### 2. Multi-Source Aggregation

**Original Problem**: Combining sensors where some may be temporarily unavailable.

**Computed Variables Solution**:

```yaml
hvac_total:
  name: "Total HVAC Power"
  formula: "if(all_hvac_available, total_hvac, partial_hvac)"
  variables:
    heating: sensor.heating_power
    cooling: sensor.cooling_power
    ventilation: sensor.ventilation_power
    all_hvac_available: "formula:heating > 0 and cooling > 0 and ventilation > 0"
    total_hvac: "formula:heating + cooling + ventilation"
    partial_hvac: "formula:if(heating > 0, heating, 0) + if(cooling > 0, cooling, 0)"
```

**Automatic behavior**:

- If ANY HVAC sensor unavailable → entire sensor becomes unavailable
- If all available → use appropriate calculation based on values

### 3. Complex Calculations with Fallbacks

**Original Problem**: Multi-step calculations needing graceful degradation.

**Computed Variables Solution**:

```yaml
efficiency_ratio:
  name: "System Efficiency"
  formula: "if(can_calculate_efficiency, current_efficiency, last_known_efficiency)"
  variables:
    output_power: sensor.system_output
    input_power: sensor.system_input
    can_calculate_efficiency: "formula:input_power > 0"
    current_efficiency: "formula:output_power / input_power * 100"
    grace_minutes: 30
    state_is_recent: "formula:((now() - state.last_changed) / 60) < grace_minutes"
    last_known_efficiency: "formula:if(state_is_recent and state > 0, state, 0)"
```

## Key Advantages Over Exception Formula

### 1. **Works with Existing Architecture**

- Leverages current dependency management
- No changes to core evaluation pipeline
- Maintains pre-evaluation error detection

### 2. **Better Separation of Concerns**

```yaml
# Clean main formula
formula: "if(recent_enough, state, fallback_total)"

# Complex logic isolated in variables
variables:
  recent_enough: "formula:((now() - state.last_changed) / 60) < grace_period"
  fallback_total: "formula:leg1_energy + leg2_energy"
```

### 3. **Composable and Reusable**

```yaml
# Variables can reference other variables
variables:
  base_consumption: "formula:heating + cooling"
  total_consumption: "formula:base_consumption + ventilation"
  efficiency: "formula:total_consumption / input_power"
```

### 4. **Type Safety Maintained**

- All computed variables resolve to numeric values before main formula
- No string/number type mixing issues
- Existing simpleeval assumptions preserved

### 5. **Testable Components**

Each computed variable can be tested independently:

```yaml
# Test computed variable in isolation
test_recent_enough:
  formula: "recent_enough" # Will be 1.0 or 0.0
  variables:
    recent_enough: "formula:((now() - state.last_changed) / 60) < 15"
```

## Implementation Feasibility

### ✅ **High Feasibility Items**

1. **YAML parsing** - Simple extension to existing config models
2. **Variable resolution** - Extends existing context building logic
3. **Dependency management** - Reuses existing dependency tracking
4. **Error propagation** - Leverages current unavailable state handling

### ⚠️ **Medium Complexity Items**

1. **Dependency ordering** - Need to resolve variables in correct order
2. **Circular dependency detection** - Prevent variable self-references
3. **Performance optimization** - Cache computed variable results

### 📋 **Implementation Plan**

#### Phase 1: Core Infrastructure

- Extend `FormulaConfig.variables` type definition
- Add `ComputedVariable` dataclass
- Implement formula prefix parsing (`"formula:..."`)
- Update variable resolution in context building

#### Phase 2: Advanced Features

- Dependency ordering for computed variables
- Circular dependency detection
- Performance optimization with caching
- Enhanced error messages for computed variable failures

#### Phase 3: Documentation & Testing

- Comprehensive test suite for computed variables
- User documentation with examples
- Migration guide for complex formulas

## Comparison Summary

| Aspect                        | Exception Formula                | Computed Variables                    |
| ----------------------------- | -------------------------------- | ------------------------------------- |
| **Architecture Impact**       | Major changes required           | Minimal changes, extends existing     |
| **Type Safety**               | Breaks (strings + numbers)       | Maintains (all numeric)               |
| **Implementation Complexity** | High (core pipeline changes)     | Medium (variable system extension)    |
| **Performance Impact**        | Higher (dual evaluation paths)   | Lower (single evaluation, cached)     |
| **Backward Compatibility**    | Requires careful handling        | Fully backward compatible             |
| **Testability**               | Complex (two formula types)      | Simple (test variables independently) |
| **Maintainability**           | Complex (mixed evaluation logic) | Clean (composable variables)          |

## Conclusion

**Computed Variables provide the same declarative benefits as the exception_formula proposal while working harmoniously with
the existing architecture.**

The solution:

- ✅ **Solves the core problem**: Clean separation of happy-path and error-handling logic
- ✅ **Maintains type safety**: All variables resolve to numbers before main formula
- ✅ **Leverages existing systems**: Works with current dependency management
- ✅ **Is backward compatible**: Existing configurations unchanged
- ✅ **Is easier to implement**: Extends rather than replaces existing logic
- ✅ **Is more flexible**: Variables can be composed and reused

This approach transforms complex, unreadable formulas:

```yaml
# Before - unreadable
formula: "if(((now() - state.last_changed) / 60) < 15, state, if(leg1 > 0 and leg2 > 0, leg1 + leg2, 0))"
```

Into clean, maintainable configurations:

```yaml
# After - readable and maintainable
formula: "if(recent_enough, state, fallback_total)"
variables:
  recent_enough: "formula:((now() - state.last_changed) / 60) < 15"
  fallback_total: "formula:if(leg1 > 0 and leg2 > 0, leg1 + leg2, 0)"
```

**Recommendation**: Implement Computed Variables as the solution to declarative error handling in synthetic sensors.
