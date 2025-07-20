---
description: Comprehensive testing scenarios for synthetic sensor idioms and reference patterns
---

# Idiom Testing Scenarios

This document outlines specific testing scenarios for each idiom defined in the State and Entity Reference Guide. Each
scenario includes corresponding YAML examples in the `examples/` folder.

## Overview

The testing scenarios are designed to validate:

- **Idiom compliance**: Each idiom works as documented
- **Edge cases**: Boundary conditions and error scenarios
- **Integration patterns**: How idioms work together
- **Error handling**: Proper exception raising and error propagation

## Test Categories

### 1. Core Idiom Validation

Tests that each idiom works correctly in isolation

### 2. Integration Testing

Tests how multiple idioms work together

### 3. Error Scenario Testing

Tests error conditions and exception handling

### 4. Edge Case Testing

Tests boundary conditions and unusual configurations

## Idiom-Specific Test Scenarios

### Idiom 1: Backing Entity State Resolution

**Purpose**: Validate that `state` token resolves correctly based on backing entity presence

#### Test Scenario 1.1: With Backing Entity

- **File**: `examples/idiom_1_backing_entity.yaml`
- **Test**: Main formula uses `state` token with registered backing entity
- **Expected**: `state` resolves to backing entity's current value
- **Validation**: Formula result matches backing entity value

#### Test Scenario 1.2: Without Backing Entity

- **File**: `examples/idiom_1_no_backing_entity.yaml`
- **Test**: Main formula uses `state` token without backing entity
- **Expected**: `state` resolves to sensor's previous calculated value
- **Validation**: Formula uses recursive calculation pattern

#### Test Scenario 1.3: Missing Backing Entity Error

- **File**: `examples/idiom_1_missing_backing_entity.yaml`
- **Test**: Main formula uses `state` token but backing entity doesn't exist
- **Expected**: `BackingEntityResolutionError` is raised
- **Validation**: Exception is raised immediately, not converted to error result

### Idiom 2: Self-Reference Patterns

**Purpose**: Validate that main formulas can reference themselves in three equivalent ways

#### Test Scenario 2.1: State Token Reference

- **File**: `examples/idiom_2_state_token.yaml`
- **Test**: Main formula uses `state` token
- **Expected**: Resolves to backing entity value
- **Validation**: Result matches backing entity state

#### Test Scenario 2.2: Sensor Key Reference

- **File**: `examples/idiom_2_sensor_key.yaml`
- **Test**: Main formula uses sensor key name
- **Expected**: Resolves to backing entity value (auto-injected variable)
- **Validation**: Result matches backing entity state

#### Test Scenario 2.3: Direct Entity ID Reference

- **File**: `examples/idiom_2_entity_id.yaml`
- **Test**: Main formula uses full entity ID
- **Expected**: Resolves to backing entity value
- **Validation**: Result matches backing entity state

#### Test Scenario 2.4: Equivalence Test

- **File**: `examples/idiom_2_equivalence.yaml`
- **Test**: All three reference patterns in same sensor set
- **Expected**: All produce identical results
- **Validation**: Results are mathematically equivalent

### Idiom 3: Entity Attribute Access

**Purpose**: Validate dot notation for accessing entity attributes

#### Test Scenario 3.1: Basic Attribute Access

- **File**: `examples/idiom_3_basic_attribute.yaml`
- **Test**: Formula accesses entity attribute using dot notation
- **Expected**: Attribute value is retrieved correctly
- **Validation**: Formula result uses attribute value

#### Test Scenario 3.2: Multiple Attribute Access

- **File**: `examples/idiom_3_multiple_attributes.yaml`
- **Test**: Formula accesses multiple attributes from same entity
- **Expected**: All attributes are retrieved correctly
- **Validation**: Formula combines multiple attributes

#### Test Scenario 3.3: Nested Attribute Access

- **File**: `examples/idiom_3_nested_attributes.yaml`
- **Test**: Formula accesses nested attribute structures
- **Expected**: Nested attributes are resolved correctly
- **Validation**: Deep attribute access works

#### Test Scenario 3.4: Missing Attribute Error

- **File**: `examples/idiom_3_missing_attribute.yaml`
- **Test**: Formula references non-existent attribute
- **Expected**: `MissingDependencyError` is raised
- **Validation**: Exception is raised immediately

### Idiom 4: Attribute State Reference

**Purpose**: Validate that attributes can reference main sensor state

#### Test Scenario 4.1: State Token in Attributes

- **File**: `examples/idiom_4_state_token.yaml`
- **Test**: Attribute formula uses `state` token
- **Expected**: `state` refers to main sensor's post-evaluation result
- **Validation**: Attribute uses main sensor's calculated value

#### Test Scenario 4.2: Sensor Key in Attributes

- **File**: `examples/idiom_4_sensor_key.yaml`
- **Test**: Attribute formula uses sensor key name
- **Expected**: Resolves to main sensor's post-evaluation result
- **Validation**: Attribute uses main sensor's calculated value

#### Test Scenario 4.3: Entity ID in Attributes

- **File**: `examples/idiom_4_entity_id.yaml`
- **Test**: Attribute formula uses full entity ID
- **Expected**: Resolves to main sensor's post-evaluation result
- **Validation**: Attribute uses main sensor's calculated value

#### Test Scenario 4.4: Evaluation Order Validation

- **File**: `examples/idiom_4_evaluation_order.yaml`
- **Test**: Multiple attributes reference main sensor
- **Expected**: All attributes use same main sensor result
- **Validation**: Consistent evaluation order maintained

### Idiom 5: Attribute-to-Attribute References

**Purpose**: Validate attribute-to-attribute reference patterns

#### Test Scenario 5.1: Linear Attribute Chain

- **File**: `examples/idiom_5_linear_chain.yaml`
- **Test**: Attributes reference each other in linear sequence
- **Expected**: Attributes evaluate in dependency order
- **Validation**: Linear dependency chain works correctly

#### Test Scenario 5.2: Multiple Attribute Dependencies

- **File**: `examples/idiom_5_multiple_deps.yaml`
- **Test**: Attribute depends on multiple other attributes
- **Expected**: All dependencies are resolved before evaluation
- **Validation**: Complex dependency graphs work

#### Test Scenario 5.3: Circular Reference Detection

- **File**: `examples/idiom_5_circular_reference.yaml`
- **Test**: Attributes reference each other circularly
- **Expected**: `CircularDependencyError` is raised
- **Validation**: Circular references are detected and prevented

#### Test Scenario 5.4: Self-Reference Detection

- **File**: `examples/idiom_5_self_reference.yaml`
- **Test**: Attribute references itself
- **Expected**: `CircularDependencyError` is raised
- **Validation**: Self-references are detected and prevented

### Idiom 6: Main Formula Attribute References

**Purpose**: Validate main formulas referencing attributes (if supported)

#### Test Scenario 6.1: Main Formula State Attribute

- **File**: `examples/idiom_6_state_attribute.yaml`
- **Test**: Main formula uses `state.attribute` pattern
- **Expected**: Resolves to backing entity's attribute
- **Validation**: No circular dependency issues

#### Test Scenario 6.2: Attribute Formula State Attribute

- **File**: `examples/idiom_6_attr_state_attribute.yaml`
- **Test**: Attribute formula uses `state.attribute` pattern
- **Expected**: Resolves to main sensor's attribute
- **Validation**: Uses post-evaluation attribute value

#### Test Scenario 6.3: Complex Attribute References

- **File**: `examples/idiom_6_complex_refs.yaml`
- **Test**: Complex attribute reference patterns
- **Expected**: All references resolve correctly
- **Validation**: Evaluation order is maintained

## Integration Test Scenarios

### Integration Test 1: Multi-Idiom Sensor

**Purpose**: Test multiple idioms working together in single sensor

#### Test Scenario INT.1: Complete Idiom Integration

- **File**: `examples/integration_complete_sensor.yaml`
- **Test**: Sensor uses all idioms together
- **Expected**: All idioms work correctly in combination
- **Validation**: Complex sensor evaluates successfully

### Integration Test 2: Cross-Sensor References

**Purpose**: Test idioms across multiple sensors

#### Test Scenario INT.2: Cross-Sensor Dependencies

- **File**: `examples/integration_cross_sensor.yaml`
- **Test**: Sensors reference each other using idioms
- **Expected**: Cross-sensor references work correctly
- **Validation**: Dependency order is maintained

## Error Handling Test Scenarios

### Error Test 1: Missing Entity Resolution

**Purpose**: Validate error handling for missing entities

#### Test Scenario ERR.1: Missing Backing Entity

- **File**: `examples/error_missing_backing_entity.yaml`
- **Test**: Backing entity doesn't exist
- **Expected**: `BackingEntityResolutionError` is raised
- **Validation**: Exception is raised immediately

#### Test Scenario ERR.2: Missing Referenced Entity

- **File**: `examples/error_missing_entity.yaml`
- **Test**: Formula references non-existent entity
- **Expected**: `MissingDependencyError` is raised
- **Validation**: Exception is raised immediately

### Error Test 2: Circular Reference Detection

**Purpose**: Validate circular reference detection

#### Test Scenario ERR.3: Attribute Circular Reference

- **File**: `examples/error_circular_attributes.yaml`
- **Test**: Attributes reference each other circularly
- **Expected**: `CircularDependencyError` is raised
- **Validation**: Circular reference is detected

#### Test Scenario ERR.4: Self-Reference Detection

- **File**: `examples/error_self_reference.yaml`
- **Test**: Attribute references itself
- **Expected**: `CircularDependencyError` is raised
- **Validation**: Self-reference is detected

### Error Test 3: Data Validation

**Purpose**: Validate data validation error handling

#### Test Scenario ERR.5: Invalid Data Provider

- **File**: `examples/error_invalid_data.yaml`
- **Test**: Data provider returns invalid data
- **Expected**: `DataValidationError` is raised
- **Validation**: Invalid data is rejected

## Edge Case Test Scenarios

### Edge Case 1: Complex Dependency Chains

**Purpose**: Test complex dependency scenarios

#### Test Scenario EDGE.1: Deep Attribute Chain

- **File**: `examples/edge_deep_chain.yaml`
- **Test**: Very long chain of attribute dependencies
- **Expected**: All dependencies resolve correctly
- **Validation**: Performance remains acceptable

#### Test Scenario EDGE.2: Multiple Circular References

- **File**: `examples/edge_multiple_circular.yaml`
- **Test**: Multiple circular reference patterns
- **Expected**: All circular references are detected
- **Validation**: Clear error messages for each

### Edge Case 2: Variable Injection Edge Cases

**Purpose**: Test variable injection in complex scenarios

#### Test Scenario EDGE.3: Variable Name Conflicts

- **File**: `examples/edge_variable_conflicts.yaml`
- **Test**: Variable names conflict between levels
- **Expected**: Precedence rules are followed correctly
- **Validation**: Correct variables are used

#### Test Scenario EDGE.4: Complex Variable Inheritance

- **File**: `examples/edge_variable_inheritance.yaml`
- **Test**: Complex variable inheritance patterns
- **Expected**: Variables are inherited correctly
- **Validation**: All variables are available where expected

## Test Execution Guidelines

### Running Individual Tests

Each test scenario can be run independently:

```bash
# Run specific idiom test
poetry run python -m pytest tests/test_idioms.py::test_idiom_1_backing_entity

# Run all idiom tests
poetry run python -m pytest tests/test_idioms.py

# Run integration tests
poetry run python -m pytest tests/test_integration.py

# Run error handling tests
poetry run python -m pytest tests/test_error_handling.py
```

### Test Data Requirements

Each test requires:

- **YAML fixture**: Located in `examples/` folder
- **Test function**: Located in appropriate test file
- **Expected results**: Defined in test assertions
- **Error expectations**: Defined for error scenarios

### Validation Criteria

Each test validates:

- **Correct evaluation**: Formulas produce expected results
- **Proper error handling**: Exceptions are raised when expected
- **Performance**: Tests complete within reasonable time
- **Memory usage**: No memory leaks or excessive usage

## Test Maintenance

### Adding New Tests

When adding new tests:

1. Create YAML fixture in `examples/` folder
2. Add test function to appropriate test file
3. Update this document with new test scenario
4. Ensure test covers specific idiom or edge case

### Updating Existing Tests

When updating tests:

1. Update YAML fixture if needed
2. Modify test function to reflect changes
3. Update this document if test scenario changes
4. Ensure backward compatibility is maintained

### Test Documentation

Each test should be documented with:

- **Purpose**: What the test validates
- **Setup**: Required configuration and data
- **Expected**: Expected behavior and results
- **Validation**: How to verify the test passed
- **Edge cases**: Any special considerations
