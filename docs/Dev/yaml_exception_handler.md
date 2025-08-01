# YAML Exception Handler Feature Proposal: Formula-Level Exception Handling

## Overview

This proposal introduces declarative exception handling for synthetic sensor YAML configurations through indented exception
formulas. This provides elegant error handling when entity references become unavailable or unknown while maintaining full
backward compatibility and extending the existing variable system.

## Problem Statement

### Current Issue

When synthetic sensors reference entities that become `unavailable` or `unknown`, the entire sensor becomes unavailable, even
when graceful fallback logic could maintain functionality:

```yaml
# Current problematic scenario
formula: "leg1_energy + leg2_energy"
variables:
  leg1_energy: sensor.circuit_1_energy # Goes 'unavailable'
  leg2_energy: sensor.circuit_2_energy # Still available: 1500

# Result: Entire sensor becomes 'unavailable' immediately
# No opportunity for grace period or fallback logic
```

### Current Limitations

The existing system:

- Fails fast when any dependency is unavailable
- Provides no declarative way to handle temporary outages
- Cannot implement grace periods for maintaining sensor continuity
- Requires sensors to be completely available or completely unavailable

## Proposed Solution

### Formula-Level Exception Handling with Indentation

Extend both main formulas and variable formulas to support exception handling through indented exception formulas:

```yaml
energy_total:
  formula: "leg1_energy + leg2_energy"
    UNAVAILABLE: "if(within_grace, state, UNAVAILABLE)"

  variables:
    leg1_energy: sensor.circuit_1_energy
      UNAVAILABLE: "if(within_grace, state, UNAVAILABLE)"

    within_grace: "formula:((now() - state.last_changed) / 60) < grace_minutes"
      UNAVAILABLE: "false"

    grace_minutes: 15
```

### Evaluation Logic

Variables and formulas are resolved with exception handling at each level:

```python
def resolve_with_exceptions(formula_or_entity, exception_handlers, context):
    try:
        # Try primary resolution (entity mapping or formula evaluation)
        return resolve_primary(formula_or_entity, context)
    except UnavailableError:
        if 'UNAVAILABLE' in exception_handlers:
            return evaluate_formula(exception_handlers['UNAVAILABLE'], context)
        return 'UNAVAILABLE'
    except UnknownError:
        if 'UNKNOWN' in exception_handlers:
            return evaluate_formula(exception_handlers['UNKNOWN'], context)
        return 'UNKNOWN'
```

## Use Cases

### 1. Energy Sensor Grace Period

**Problem**: Energy sensors need to preserve last known values during brief outages to maintain statistics integrity.

```yaml
energy_total:
  name: "Total Energy Consumption"
  formula: "main_meter + solar_produced"
    UNAVAILABLE: "if(within_grace, state, UNAVAILABLE)"

  variables:
    main_meter: sensor.main_meter_energy
      UNAVAILABLE: "if(within_grace, state, UNAVAILABLE)"

    solar_produced: sensor.solar_energy_produced
      UNAVAILABLE: "if(within_grace, state, UNAVAILABLE)"

    within_grace: "formula:((now() - state.last_changed) / 60) < grace_minutes"
      UNAVAILABLE: "false"

    grace_minutes: 15
```

### 2. Multi-Source Aggregation with Partial Availability

**Problem**: Combining multiple sensors where some may be temporarily unavailable.

```yaml
hvac_total:
  name: "Total HVAC Power"
  formula: "heating + cooling + ventilation"
    UNAVAILABLE: "available_hvac_total"

  variables:
    heating: sensor.heating_power
      UNAVAILABLE: "0"

    cooling: sensor.cooling_power
      UNAVAILABLE: "0"

    ventilation: sensor.ventilation_power
      UNAVAILABLE: "0"

    available_hvac_total: "formula:heating + cooling + ventilation"
      UNAVAILABLE: "0"
```

### 3. Complex Calculations with Smart Fallbacks

**Problem**: Multi-step calculations that need graceful degradation with backup strategies.

```yaml
efficiency_ratio:
  name: "System Efficiency"
  formula: "if(can_calculate, current_efficiency, fallback_efficiency)"
    UNAVAILABLE: "if(within_grace, state, UNAVAILABLE)"

  variables:
    output_power: sensor.system_output
      UNAVAILABLE: "estimated_output"

    input_power: sensor.system_input
      UNAVAILABLE: "estimated_input"

    can_calculate: "formula:input_power > 0"
      UNAVAILABLE: "false"

    current_efficiency: "formula:output_power / input_power * 100"
      UNAVAILABLE: "0"

    fallback_efficiency: "formula:if(within_grace, state, historical_average)"
      UNAVAILABLE: "75"

    estimated_output: "formula:historical_average * 0.75"
      UNAVAILABLE: "1000"

    estimated_input: "formula:historical_average / 0.75"
      UNAVAILABLE: "1333"

    within_grace: "formula:((now() - state.last_changed) / 60) < 30"
      UNAVAILABLE: "false"

    historical_average: 75
```

## Implementation Details

### Extended Variable System

Variables can now be:

1. **Simple entity mappings** (unchanged): `variable: sensor.entity_id`
2. **Literal values** (unchanged): `variable: 42`
3. **Formula variables** (new): `variable: "formula:expression"`
4. **Any of the above with exception handling** (new)

### YAML Schema Structure

```yaml
sensors:
  sensor_name:
    name: "Sensor Display Name"

    # Main formula with optional exception handling
    formula: "main_calculation"
      UNAVAILABLE: "fallback_formula"     # Optional
      UNKNOWN: "unknown_handler"          # Optional
      "UNAVAILABLE|UNKNOWN": "combined"   # Optional

    variables:
      # Simple entity (unchanged)
      simple_var: sensor.entity_id

      # Simple literal (unchanged)
      literal_var: 42

      # Formula variable (new)
      computed_var: "formula:expression"

      # Entity with exception handling (new)
      entity_with_fallback: sensor.entity_id
        UNAVAILABLE: "fallback_expression"

      # Formula with exception handling (new)
      formula_with_fallback: "formula:complex_calculation"
        UNAVAILABLE: "simple_fallback"
        UNKNOWN: "unknown_fallback"
```

### Backward Compatibility

All existing configurations continue to work unchanged:

```yaml
# This still works exactly as before
energy_sensor:
  formula: "input_power * efficiency"
  variables:
    input_power: sensor.power_input
    efficiency: 0.85
```

### Exception Handling Context

Exception formulas receive the complete evaluation context:

- All resolved variables (including other computed variables)
- Global variables
- Built-in functions (`now()`, `if()`, etc.)
- Special tokens (`state` for last sensor value, `entity_id`)
- Special constants (`UNAVAILABLE`, `UNKNOWN` for explicit state control)

### Resolution Order and Precedence

1. **Resolve simple variables first** (entities and literals)
2. **Resolve formula variables in dependency order**
3. **Apply exception handling at each level**
4. **Build final context for main formula**
5. **Execute main formula with exception handling**

### Exception Handling Precedence

For each formula or variable:

1. **Try primary resolution** (entity lookup or formula evaluation)
2. **If unavailable and `UNAVAILABLE` handler exists**: Execute unavailable handler
3. **If unknown and `UNKNOWN` handler exists**: Execute unknown handler
4. **If unavailable/unknown and combined handler exists**: Execute combined handler
5. **Otherwise**: Propagate the unavailable/unknown state upward

## Benefits

### Clean Separation of Concerns

```yaml
# Before: Complex, unreadable mixed logic
formula: "if(((now() - state.last_changed) / 60) < 15, state, if(leg1 > 0 and leg2 > 0, leg1 + leg2, 0))"

# After: Clean separation with indented exception handling
formula: "leg1_energy + leg2_energy"
  UNAVAILABLE: "if(within_grace, state, UNAVAILABLE)"

variables:
  leg1_energy: sensor.circuit_1_energy
    UNAVAILABLE: "if(within_grace, state, UNAVAILABLE)"

  within_grace: "formula:((now() - state.last_changed) / 60) < 15"
    UNAVAILABLE: "false"
```

### Progressive Enhancement

Start simple and add complexity only where needed:

```yaml
# Phase 1: Simple sensor
formula: "input_power * efficiency"
variables:
  input_power: sensor.power_input
  efficiency: 0.85

# Phase 2: Add exception handling for critical variables
variables:
  input_power: sensor.power_input
    UNAVAILABLE: "if(within_grace, state, UNAVAILABLE)"

# Phase 3: Add computed variables for complex logic
variables:
  within_grace: "formula:((now() - state.last_changed) / 60) < grace_minutes"
    UNAVAILABLE: "false"
```

### Flexible Exception Patterns

```yaml
# Energy sensors - grace period preservation
UNAVAILABLE: "if(within_grace, state, UNAVAILABLE)"

# Optional sensors - default to zero
UNAVAILABLE: "0"

# Backup sensor strategy
UNAVAILABLE: "backup_sensor_value"

# Conservative estimates
UNAVAILABLE: "historical_average * safety_factor"

# Fail-safe for critical systems
UNAVAILABLE: "UNAVAILABLE"  # Always fail when unavailable
```

### Reusable Computed Variables

```yaml
variables:
  # Reusable time-based logic
  within_grace: "formula:((now() - state.last_changed) / 60) < grace_minutes"
  is_business_hours: "formula:now().hour >= 8 and now().hour <= 17"

  # Reusable calculations
  daily_average: "formula:total_consumption / days_in_period"
  efficiency_factor: "formula:output_power / input_power"

  # Reusable fallback strategies
  conservative_estimate: "formula:historical_average * 0.8"
  optimistic_estimate: "formula:historical_average * 1.2"
```

### Improved Maintainability

- **Readable main formulas**: Happy path logic is clear and uncluttered
- **Isolated exception handling**: Error logic doesn't interfere with main calculations
- **Consistent patterns**: Same exception handling across related sensors
- **Easy modifications**: Change exception logic without touching main formulas
- **Composable logic**: Build complex behaviors from simple, testable components
- **Independent testing**: Test main logic and exception handling separately

## Backward Compatibility

- **Fully backward compatible**: All existing configurations work unchanged
- **Optional feature**: Exception handling is completely optional
- **No breaking changes**: Current behavior preserved when exception handling not specified
- **Incremental adoption**: Can add exception handling to existing sensors without modification

```yaml
# This continues to work exactly as before
existing_sensor:
  formula: "input_power * efficiency"
  variables:
    input_power: sensor.power_input
    efficiency: 0.85
```

## Comparison with Alternative Approaches

### Alternative 1: System-Level Grace Periods

```yaml
# Rejected approach: Configuration-based grace periods
energy_total:
  formula: "leg1_energy + leg2_energy"
  grace_period:
    minutes: 15
    behavior: "preserve_last_state"
```

**Why formula-level exception handling is better**:

- More flexible - can implement any fallback logic, not just grace periods
- Granular control - different variables can have different exception handling
- Composable - can combine multiple fallback strategies
- Future-proof - extensible to new patterns without system changes

### Alternative 2: Pre-Processing Exception Detection

```yaml
# Rejected approach: Global exception formula
formula: "leg1_energy + leg2_energy"
exception_formula: "if(within_grace, state, UNAVAILABLE)"
```

**Why variable-level exception handling is better**:

- More precise - can handle individual variable failures differently
- Better performance - only processes exceptions for variables that actually fail
- Cleaner logic - exception handling stays close to the variables that might fail
- More maintainable - can modify individual variable handling without affecting others

### Alternative 3: Python Exception Handlers

```python
# Rejected approach: Custom Python functions
def energy_exception_handler(context, unavailable_vars):
    if is_within_grace_period(context):
        return context['state']
    return 'UNAVAILABLE'
```

**Why YAML exception handling is better**:

- Maintains declarative approach - no custom code required
- User-friendly - accessible to users without Python knowledge
- Consistent with package philosophy - everything configurable through YAML
- Version-controlled with configurations - exception logic tracked with sensor definitions

## Implementation Plan

### Phase 1: Extended Variable System

- Extend `FormulaConfig.variables` type definition to support computed variables
- Add parsing for `"formula:expression"` syntax in variables
- Implement variable resolution with dependency ordering
- Add support for circular dependency detection in computed variables

### Phase 2: Exception Handling Infrastructure

- Extend YAML parsing to support indented exception handlers
- Add `UNAVAILABLE`, `UNKNOWN`, and combined exception handler parsing
- Implement exception resolution logic for variables and formulas
- Add special token support (`state`, `UNAVAILABLE`, `UNKNOWN`)

### Phase 3: Integration and Context Building

- Update context building phase to handle computed variables
- Integrate exception handling into variable resolution pipeline
- Ensure proper error propagation and state management
- Add comprehensive logging for exception handling flow

### Phase 4: Testing and Documentation

- Add unit tests for computed variables and exception handling
- Add integration tests for complex exception scenarios
- Update user documentation with comprehensive examples
- Add developer documentation for extending exception patterns

### Phase 5: Advanced Features (Future)

- Global computed variable templates for reusable patterns
- Performance optimizations for computed variable caching
- Enhanced debugging tools for exception handling flow
- Advanced dependency analysis for complex variable relationships

## Testing Strategy

### Unit Tests

- Computed variable resolution with various dependencies
- Exception handler evaluation for all state types (UNAVAILABLE, UNKNOWN)
- Variable dependency ordering and circular dependency detection
- Context building with mixed simple and computed variables
- Special token resolution (`state`, `UNAVAILABLE`, `UNKNOWN`)
- Edge cases (malformed formulas, invalid exception handlers)

### Integration Tests

- Real sensor scenarios with computed variables and exception handling
- Energy sensor grace period functionality with state preservation
- Multi-sensor aggregation with partial availability handling
- Complex calculation chains with multiple fallback levels
- Performance impact of computed variables and exception detection
- Backward compatibility with existing sensor configurations

### User Acceptance Tests

- Energy sensor grace period preservation during outages
- HVAC system aggregation with optional component handling
- System efficiency calculations with smart fallback strategies
- Progressive enhancement from simple to complex configurations

## Conclusion

This proposal provides a comprehensive, declarative solution for handling unavailable entity references through:

1. **Extended Variable System**: Variables can now be computed formulas, not just entity mappings
2. **Formula-Level Exception Handling**: Any formula (main or variable) can have indented exception handlers
3. **Full Backward Compatibility**: All existing configurations continue to work unchanged
4. **Progressive Enhancement**: Start simple, add complexity only where needed

The key innovation is using **indented exception handling syntax** that:

- Keeps exception logic visually subordinate to main logic
- Works consistently across formulas and variables
- Maintains the declarative, YAML-only approach
- Provides granular control over individual variable and formula failures

This transforms complex, unmaintainable formulas:

```yaml
formula: "if(((now() - state.last_changed) / 60) < 15, state, if(leg1 > 0 and leg2 > 0, leg1 + leg2, 0))"
```

Into clean, maintainable configurations:

```yaml
formula: "leg1_energy + leg2_energy"
  UNAVAILABLE: "if(within_grace, state, UNAVAILABLE)"

variables:
  leg1_energy: sensor.circuit_1_energy
    UNAVAILABLE: "if(within_grace, state, UNAVAILABLE)"

  within_grace: "formula:((now() - state.last_changed) / 60) < grace_minutes"
    UNAVAILABLE: "false"
```

This approach directly addresses the real-world need for robust sensor behavior during entity outages while maintaining the
package's declarative philosophy and avoiding any custom code requirements.

## Implementation Task List

### Recommended Implementation Order

**Start with Computed Variables → Add Exception Handling**

**Rationale**: Exception handling depends on computed variables for complex fallback logic, but computed variables are useful
independently. This allows incremental implementation and testing.

### Phase 1: Foundation - Computed Variables (Week 1-2)

#### Task 1.1: Extend Variable Type System

- [ ] **File**: `src/ha_synthetic_sensors/config_models.py`
- [ ] Extend `FormulaConfig.variables` type annotation to support computed variables
- [ ] Create `ComputedVariable` dataclass or use union type with string detection
- [ ] Update variable validation to handle `"formula:expression"` syntax

#### Task 1.2: Variable Parser Extension

- [ ] **File**: `src/ha_synthetic_sensors/yaml_config_parser.py`
- [ ] Add detection logic for `"formula:"` prefix in variable values
- [ ] Parse computed variable expressions and validate syntax
- [ ] Ensure backward compatibility with existing simple variable parsing

#### Task 1.3: Variable Resolution Infrastructure

- [ ] **File**: `src/ha_synthetic_sensors/evaluator_phases/context_building/variable_context_builder.py`
- [ ] Implement computed variable resolution logic
- [ ] Add dependency ordering for computed variables (resolve simple vars first)
- [ ] Add circular dependency detection for computed variables
- [ ] Integration with existing context building pipeline

#### Task 1.4: Testing Computed Variables

- [ ] **File**: `tests/date_time/test_computed_variables_unit.py` (new)
- [ ] Unit tests for computed variable parsing and resolution
- [ ] Dependency ordering tests
- [ ] Circular dependency detection tests
- [ ] Integration tests with existing variable system

### Phase 2: Exception Handling Infrastructure (Week 3-4)

#### Task 2.1: YAML Schema Extension for Exception Handlers

- [ ] **File**: `src/ha_synthetic_sensors/yaml_config_parser.py`
- [ ] Add parsing support for indented `UNAVAILABLE:`, `UNKNOWN:` syntax
- [ ] Support combined exception handlers `"UNAVAILABLE|UNKNOWN"`
- [ ] Validate exception handler formula syntax

#### Task 2.2: Exception Handler Data Model

- [ ] **File**: `src/ha_synthetic_sensors/config_models.py`
- [ ] Extend `FormulaConfig` to support exception handlers
- [ ] Add exception handler fields to variable configurations
- [ ] Update serialization/deserialization for exception handlers

#### Task 2.3: Variable Resolution with Exception Handling

- [ ] **File**: `src/ha_synthetic_sensors/evaluator_phases/context_building/variable_context_builder.py`
- [ ] Implement try/catch logic for variable resolution
- [ ] Add exception handler evaluation when variables become unavailable
- [ ] Special token support (`state`, `UNAVAILABLE`, `UNKNOWN`)
- [ ] Proper error propagation and state management

#### Task 2.4: Formula-Level Exception Handling

- [ ] **File**: `src/ha_synthetic_sensors/evaluator.py`
- [ ] Extend main formula evaluation to support exception handlers
- [ ] Integration with existing evaluation pipeline
- [ ] Ensure exception handlers receive proper context

### Phase 3: Integration and Refinement (Week 5-6)

#### Task 3.1: Context Building Integration

- [ ] **File**: `src/ha_synthetic_sensors/evaluator_phases/context_building/context_building_phase.py`
- [ ] Full integration of computed variables and exception handling
- [ ] Performance optimization for context building with computed variables
- [ ] Proper error handling and logging

#### Task 3.2: Dependency Management Updates

- [ ] **File**: `src/ha_synthetic_sensors/evaluator_phases/dependency_management/dependency_management_phase.py`
- [ ] Update dependency extraction to handle computed variables
- [ ] Ensure exception handling works with dependency validation
- [ ] Update dependency ordering for computed variables

#### Task 3.3: Special Token Implementation

- [ ] **File**: `src/ha_synthetic_sensors/evaluator_phases/context_building/` (multiple files)
- [ ] Implement `state` token for accessing last sensor value
- [ ] Implement `UNAVAILABLE`/`UNKNOWN` constants in exception contexts
- [ ] Proper token resolution and validation

### Phase 4: Comprehensive Testing (Week 7)

#### Task 4.1: Unit Test Suite

- [ ] **File**: `tests/date_time/test_exception_handling_unit.py` (new)
- [ ] Exception handler parsing and evaluation tests
- [ ] Special token resolution tests
- [ ] Error propagation and state management tests
- [ ] Edge cases and malformed input handling

#### Task 4.2: Integration Test Suite

- [ ] **File**: `tests/integration/test_computed_variables_integration.py` (new)
- [ ] End-to-end tests with real sensor scenarios
- [ ] Energy sensor grace period functionality
- [ ] Multi-sensor aggregation with partial availability
- [ ] Complex calculation chains with fallbacks

#### Task 4.3: Performance Testing

- [ ] **File**: `tests/performance/test_computed_variables_performance.py` (new)
- [ ] Performance impact assessment of computed variables
- [ ] Memory usage analysis for exception handling
- [ ] Comparison with existing simple variable performance

### Phase 5: Documentation and Polish (Week 8)

#### Task 5.1: User Documentation

- [ ] **File**: `docs/user/computed_variables.md` (new)
- [ ] Comprehensive examples for computed variables
- [ ] Exception handling patterns and best practices
- [ ] Migration guide from complex formulas to computed variables

#### Task 5.2: Developer Documentation

- [ ] **File**: `docs/dev/computed_variables_architecture.md` (new)
- [ ] Architecture documentation for computed variables
- [ ] Exception handling flow diagrams
- [ ] Extension points for future enhancements

#### Task 5.3: Schema Validation Updates

- [ ] **File**: `src/ha_synthetic_sensors/schema_validator.py`
- [ ] Add validation for computed variable syntax
- [ ] Exception handler validation and error messages
- [ ] Helpful error messages for common mistakes

## Implementation Notes

### Critical Dependencies

1. **Computed Variables MUST be implemented first** - Exception handling relies on them
2. **Context building phase** - Most changes will be in context building infrastructure
3. **Backward compatibility** - Every change must maintain existing functionality

### Risk Mitigation

1. **Feature flags** - Consider adding feature flags for gradual rollout
2. **Extensive testing** - Each phase should have comprehensive test coverage
3. **Performance monitoring** - Watch for performance regressions
4. **User feedback** - Consider beta testing with complex use cases

### Success Criteria

- [ ] All existing configurations continue to work unchanged
- [ ] Energy sensor grace period use case works as specified
- [ ] Performance impact < 10% for existing sensors
- [ ] Comprehensive documentation and examples
- [ ] Test coverage > 90% for new functionality

### Optional Future Enhancements (Not in Initial Implementation)

- Global computed variable templates
- Performance optimization with caching
- Advanced debugging tools
- Visual dependency graph tools
- IDE/editor syntax highlighting support
