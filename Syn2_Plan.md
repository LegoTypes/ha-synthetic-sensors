# Technical Implementation Plan - HA Synthetic Sensors (Future Enhancements)

## Package Status

**Current State**: Production ready with comprehensive OR pattern support and full mathematical functions
**Test Results**: 402/402 tests passing (all features implemented)
**Feature Coverage**: Static and dynamic collection patterns, variable inheritance, mathematical functions
**Documentation**: Comprehensive examples and usage patterns documented

## Implementation Overview

This document outlines **future enhancements** for the HA Synthetic Sensors package. The core functionality is complete and
production-ready. All basic features, OR pattern support, variable inheritance, and mathematical functions are fully
implemented and tested.

## Future Enhancement Opportunities

Based on the Feature Planning document, the following areas represent potential future
improvements beyond the current comprehensive implementation:

### 1. Advanced Mathematical Functions (Medium Priority)

**Current Status**: Comprehensive mathematical library implemented with all essential functions
**Future Additions**:

- **Statistical Functions**:
  - `median()` - Median value calculations for datasets
  - `percentile()` - Percentile calculations for distribution analysis
  - `mode()` - Most frequent value in datasets
  - `quartile()` - Quartile calculations for statistical analysis

- **Advanced Mathematical Operations**:
  - `log()`, `log10()`, `log2()` - Additional logarithmic functions
  - `exp()` - Exponential function (e^x)
  - `factorial()` - Factorial calculations
  - `gcd()`, `lcm()` - Greatest common divisor and least common multiple

### 2. Enhanced Collection Pattern Syntax (Medium Priority)

**Current Status**: Full OR pattern support with pipe syntax (`device_class:door|window`)
**Future Enhancements**:

- **State-based Collection Patterns**:

  ```yaml
  formula: count("state:>20")  # Entities with state greater than 20
  formula: sum("state:!=unknown")  # Exclude unknown states
  formula: avg("state:between:10,30")  # Values within range
  ```

- **Attribute Condition Enhancements**:

  ```yaml
  formula: count("attribute:battery_level<=20")  # Currently <20 only
  formula: sum("attribute:temperature:range:18,25")  # Temperature ranges
  formula: avg("attribute:humidity:!=null")  # Non-null values only
  ```

- **Complex Query Combinations**:

  ```yaml
  formula: sum("device_class:power AND area:kitchen")  # Boolean logic
  formula: count("tags:critical OR area:security")  # Complex combinations
  ```

### 3. Time-based Functions (Low Priority)

**Current Status**: Basic mathematical functions without time calculations
**Future Additions**:

- **Time Calculation Functions**:

  ```yaml
  formula: hours_since("sensor.last_motion")
  formula: days_since("sensor.last_update") 
  formula: time_of_day_percent()  # 0-100% through the day
  formula: day_of_week_factor("weekend:0.8,weekday:1.0")
  ```

- **Historical Data Functions**:

  ```yaml
  formula: daily_average("sensor.power", 7)  # 7-day average
  formula: weekly_trend("sensor.temperature")  # Trend analysis
  formula: seasonal_adjustment("sensor.consumption")
  ```

### 4. Advanced Template Integration (Low Priority)

**Current Status**: Templates can be used as inputs to synthetic sensors
**Future Enhancements**:

- **Dynamic Formula Generation**:
  - Runtime formula modification based on conditions
  - Template-generated collection patterns
  - Conditional mathematical operations

- **Multi-step Analysis Workflows**:
  - Template sensors that build complex synthetic sensor configurations
  - Dynamic sensor creation based on discovered entities
  - Automated sensor relationship management

### 5. Performance and Optimization Features (Future)

**Current Status**: Efficient evaluation with caching and dependency resolution
**Future Optimizations**:

- **Advanced Caching Strategies**:
  - Persistent cache across Home Assistant restarts
  - Intelligent cache invalidation based on entity update patterns
  - Cross-sensor cache sharing for common calculations

- **Parallel Evaluation**:
  - Concurrent evaluation of independent sensors
  - Batch processing for collection functions
  - Optimized update ordering for large sensor networks

### 6. Integration Enhancements (Future)

**Current Status**: Full Home Assistant integration with services and entity management
**Future Enhancements**:

- **Energy Dashboard Integration**:
  - Automatic energy flow calculations
  - Solar production and consumption analytics
  - Grid import/export optimization

- **Advanced Entity Management**:
  - Automatic sensor discovery and configuration
  - Dynamic sensor grouping and categorization
  - Sensor health monitoring and diagnostics

## Implementation Priority Assessment

### Medium Priority (User-Requested Features)

1. **Statistical Functions** - Would enhance data analysis capabilities
2. **Enhanced Collection Patterns** - Would provide more flexible entity selection
3. **State-based Filtering** - Would enable more sophisticated aggregations

### Low Priority (Template Territory)

1. **Time-based Functions** - Templates already handle time logic well
2. **Complex Multi-step Analysis** - Templates are better suited for this
3. **Dynamic Formula Generation** - Templates provide this capability

### Future Considerations (Performance/Optimization)

1. **Advanced Caching** - Only needed with very large sensor networks
2. **Parallel Evaluation** - Only beneficial with hundreds of sensors
3. **Integration Enhancements** - Dependent on user demand and use cases

## Decision Framework for Future Enhancements

### Implementation Criteria

**High Priority Indicators**:

- Multiple user requests for the feature
- Cannot be easily achieved with existing template functionality
- Provides significant mathematical or aggregation capability
- Maintains the simple YAML-first design philosophy

**Low Priority Indicators**:

- Can be achieved with Home Assistant templates
- Adds significant complexity to the package
- Overlaps with existing Home Assistant functionality
- Limited use case applicability

### Current Recommendation

**Focus Areas**:

1. Monitor user feedback for most-requested mathematical functions
2. Consider statistical functions if data analysis use cases emerge
3. Evaluate enhanced collection patterns based on user complexity needs

**Avoid**:

1. Features that duplicate template sensor capabilities
2. Complex time-based logic (templates handle this better)
3. Performance optimizations until proven necessary

## Conclusion

The HA Synthetic Sensors package is feature-complete for its intended purpose. All core functionality including OR patterns,
variable inheritance, mathematical functions, and Home Assistant integration is implemented and tested.

Future enhancements should be driven by user demand and focus on mathematical capabilities that complement rather than
duplicate Home Assistant's existing template functionality.

The package provides a solid foundation that can be extended incrementally based on real-world usage patterns and user
feedback.

# Single formula (90% of use cases)

```yaml
  energy_cost_current:
    formula: "power * rate"
```

# Rich sensor with calculated attributes

```yaml
  energy_cost_analysis:
    state_formula: "power *rate"
    attributes:
      daily_projected:
        formula: "state* 24"
      monthly_projected:
        formula: "state *24* 30"

```

**Key Benefits:**

- **Simplified Entity IDs**: `sensor.syn2_energy_cost_analysis`
- **Reduced Configuration**: No nested arrays for common cases
- **Rich Data**: Multiple calculated values in single entity
- **Clean Cross-References**: Direct entity ID resolution

## Current State Analysis

### Implemented Infrastructure

1. **config_manager.py** - YAML configuration loading and sensor definition management
2. **evaluator.py** - Enhanced formula evaluation with caching, dependency resolution, and error handling
3. **name_resolver.py** - Entity name to entity ID mapping with normalization
4. **integration.py** - Main integration point that coordinates all components
5. **Test Suite** - 121 passing tests organized into 12 categories

### Test Infrastructure Status

- **Configuration Management Tests** (14/14 tests) - test_config_manager.py
- **Enhanced Evaluator Tests** (10/10 tests) - test_evaluator.py
- **Formula Evaluation Tests** (8/8 tests) - test_formula_evaluation.py
- **Integration Tests** (4/4 tests) - test_integration.py
- **Name Resolver Tests** (14/14 tests) - test_name_resolver.py
- **Service Layer Tests** (14/14 tests) - test_service_layer.py
- **Entity Management Tests** (13/13 tests) - test_entity_management.py
- **Advanced Dependencies Tests** (14/14 tests) - test_advanced_dependencies.py
- **Enhanced Evaluator Tests** (15/15 tests) - test_enhanced_evaluator.py
- **Non-Numeric States Tests** (6/6 tests) - test_non_numeric_states.py
- **YAML/Factory Tests** (9/9 tests) - test_yaml_and_factory.py
- **Schema Validation Tests** (17/17 tests) - test_schema_validation.py
- **Schema Fixtures Tests** (all fixtures validated) - test_schema_fixtures.py

### Current Status Summary

**Core Functionality:**

- Complete formula evaluation functionality
- Configuration management via YAML
- Name resolution and entity mapping
- Integration workflow functional
- Service layer complete with 7 HA services
- Entity management with dynamic lifecycle
- Advanced dependency resolution
- Comprehensive test coverage for all features

## Gap Analysis: Comparison with span/tests Syn2 Implementation

### Critical Gaps Analysis - UPDATED STATUS

Based on current implementation review, here's the status of all components:

#### 1. Service Layer Tests (COMPLETE - FULLY IMPLEMENTED)

**Current Status**: COMPLETE - 14 comprehensive service tests implemented
**Coverage**: Full Home Assistant service integration with all required services

**Implemented Services:**

- Service registration/deregistration
- YAML configuration loading via services (reload_config)
- Configuration validation services (validate_config)
- Service error handling and responses
- Service schema validation
- Dynamic sensor updates (update_sensor)
- Variable management (add_variable, remove_variable)
- Formula evaluation (evaluate_formula)
- Sensor introspection (get_sensor_info)

**Architecture Achievement**: Complete HA service layer with registration, validation, and operations

#### 2. Advanced Formula Features (COMPLETE - PHASE 1 IMPLEMENTED)

**Currently Supported:**

- Basic arithmetic operations (A + B, temp + humidity)
- Complex mathematical expressions with variables
- Entity reference resolution and dependency tracking
- Formula validation and error handling

**PHASE 1 MATHEMATICAL FUNCTIONS - COMPLETE AND TESTED**

**All Mathematical Functions Currently Available:**

```python
# Basic operations
"abs": abs,        # Absolute value
"min": min,        # Minimum of values
"max": max,        # Maximum of values
"round": round,    # Round to nearest integer
"sum": sum,        # Sum of iterable
"float": float,    # Convert to float
"int": int,        # Convert to integer

# Phase 1 Advanced Functions
"sqrt": math.sqrt,     # Square root calculations
"pow": pow,            # Power function for exponential calculations
"clamp": clamp,        # Limit sensor values within bounds
"map": map_range,      # Scale sensor values between ranges
"percent": percent,    # Percentage calculations
"avg": avg,            # Average multiple sensor values
"mean": avg,           # Alias for average
"floor": math.floor,   # Floor rounding
"ceil": math.ceil,     # Ceiling rounding
```

Status: All Phase 1 functions implemented, tested, and passing in production code.

**Statistical Functions (Phase 2):**

- median - Median of sensor values
- stdev - Standard deviation for variance analysis
- variance - Statistical variance calculations
- mode - Most common value in datasets

**Mathematical Operations (Phase 3):**

- log, log10, log2 - Logarithmic functions
- exp - Exponential function (e^x)
- trunc - Truncate to integer

**Trigonometric Functions (Phase 4):**

- sin, cos, tan - Basic trigonometry
- asin, acos, atan, atan2 - Inverse trigonometry
- degrees, radians - Angle conversions
- hypot - Hypotenuse calculations

**Time-Based Functions (Phase 5):**

- hours_since, days_since - Time calculations
- time_of_day_percent - Temporal percentages

**Home Assistant Specific Functions (Phase 6):**

- delta - Absolute difference between values
- Custom entity reference syntax improvements

## Version 2.0 Implementation Roadmap

### Phase 1: Schema and Parser Implementation

**Objective**: Implement clean v2.0 YAML schema validation

**Implementation Steps**:

1. **Schema Definition** (`schema/schema_v2.py`):
   - Clean v2.0 schema with flattened syntax
   - Support for `formula` vs `state_formula` keys
   - Add `attributes` section validation
   - Simplified key names (`unit` vs `unit_of_measurement`)

2. **ConfigManager Implementation** (`config_manager.py`):
   - Clean v2.0 config parser
   - Sensor key-based configuration handling
   - Direct formula and calculated attributes parsing
   - Validation integration

3. **Validation Service Implementation**:
   - `validate_config` service for v2.0 syntax
   - Clear error messages for syntax issues
   - Schema validation integration

### Phase 2: Calculated Attributes Support

**Objective**: Implement rich sensor data through calculated attributes

**Implementation Steps**:

1. **EntityManager Updates** (`entity_manager.py`):
   - Add attribute calculation support to sensor entities
   - Implement `state_formula` vs regular `formula` handling
   - Add attribute update cycles alongside main state updates

2. **Evaluator Enhancements** (`evaluator.py`):
   - Support for `state` variable in attribute formulas
   - Attribute-specific dependency tracking
   - Caching for attribute calculations

3. **Service Updates**:
   - Update `get_sensor_info` to include attribute information
   - Add attribute inspection capabilities
   - Support attribute updates in `update_sensor` service

### Phase 3: Clean Entity ID Implementation

**Objective**: Implement simplified entity ID generation

**Implementation Steps**:

1. **Entity ID Generation** (`integration.py`):
   - Implement clean `sensor.syn2_{sensor_key}` pattern
   - Single entity per sensor with calculated attributes
   - Smart entity ID resolution for cross-references

2. **Name Resolution Implementation** (`name_resolver.py`):
   - Clean resolution for simplified entity IDs
   - Direct sensor key to entity ID mapping
   - Cross-reference validation for hierarchical sensors

3. **Dependency Implementation** (`dependency_parser.py`):
   - Clean dependency parsing for simplified entity IDs
   - Support for direct entity ID references
   - Enhanced circular dependency detection

### Phase 4: Testing and Documentation

**Objective**: Comprehensive testing and documentation for v2.0 implementation

**Implementation Steps**:

1. **Test Suite Implementation**:
   - v2.0 syntax validation tests
   - Calculated attributes functionality tests
   - Clean entity ID implementation tests
   - Integration tests for complete v2.0 workflow

2. **Example Configurations**:
   - Comprehensive v2.0 example configurations
   - Real-world use case examples
   - Best practices documentation

3. **Service Documentation**:
   - Complete service documentation for v2.0 features
   - Implementation guide
   - Performance optimization guidelines

### Current Implementation Status

**Currently Available:**

- Basic entity references via variables mapping in YAML configuration
- Direct entity ID access for Home Assistant entities
- Mathematical expressions with variable substitution
- Dependency tracking and validation
- All Phase 1 mathematical functions (abs, min, max, sqrt, pow, clamp, map, etc.)
- **Synthetic sensors ARE proper HA sensor entities** with predictable entity IDs (`sensor.syn2_{unique_id}_{formula_id}`)
- **Variables mapping CAN reference synthetic sensors** like any other HA entity

**NOT Currently Implemented:**

- entity('sensor.xyz') function syntax for direct entity access in formulas
- Direct hierarchical references within formula expressions
- EntityReferenceHandler component
- HierarchicalEvaluator component

**Current Limitation:** While synthetic sensors can be referenced in variables mapping, true hierarchical calculations within
formulas require manual variable mapping rather than direct entity() function calls.

These features are listed in the architecture plan as future enhancements requiring additional
implementation work.

#### 3. Entity Management Tests (COMPLETE - FULLY IMPLEMENTED)

**Current Status**: COMPLETE - 13 comprehensive entity management tests implemented
**Coverage**: Full dynamic entity lifecycle management

**Implemented Features:**

- Dynamic sensor entity creation (test_dynamic_entity_creation)
- Entity registry management (test_entity_registry_integration)
- Sensor update/removal workflows (test_entity_update_workflows, test_entity_removal_cleanup)
- Entity state preservation during reloads (test_sensor_state_preservation)
- Entity relationship tracking (test_entity_relationship_tracking)
- Multiple entity operations (test_multiple_entity_operations)
- Entity factory patterns (test_entity_factory_patterns)

#### 4. Dependency Resolution Enhancement (COMPLETE - FULLY IMPLEMENTED)

**Current Status**: COMPLETE - 14 comprehensive dependency tests implemented
**Coverage**: Advanced dependency scenarios fully tested

**Implemented Features:**

- Circular dependency detection (test_circular_dependency_detection)
- Hierarchical dependency resolution (test_hierarchical_dependency_resolution)
- Update order calculation (test_update_order_calculation, test_topological_sorting)
- Cross-reference validation between Syn2 sensors (test_cross_reference_validation)
- Complex dependency scenarios (test_complex_dependency_scenarios)
- Performance testing with large graphs (test_performance_with_large_dependency_graphs)
- Dependency caching (test_dependency_caching)

#### 5. YAML Schema Validation (COMPLETE)

**Current Status**: COMPLETE - JSON Schema validation infrastructure implemented
**Test Coverage**: 17 comprehensive schema validation tests passing

**Core Implementation:**

- SchemaValidator class with JSON Schema v4.17.0 support
- ValidationError and ValidationResult structured data types for type-safe error handling
- Comprehensive v1.0 schema definition covering all YAML configuration aspects
- Integration with ConfigManager for automatic validation during YAML loading
- Enhanced validate_config service with detailed validation results

**Schema Validation Capabilities:**

- Required field validation (version, sensors, unique_id, formulas)
- Data type validation (strings, numbers, booleans, arrays, objects)
- Pattern validation (entity ID format: domain.entity_name)
- Enum validation (device_class and state_class values)
- Array constraints (minimum items, unique items)
- Additional properties rejection

**Semantic Validation:**

- Duplicate unique_id detection across sensors
- Duplicate formula id detection within sensors
- Variable usage validation in formulas
- Entity reference format validation
- Schema version compatibility checking

**Error Reporting Infrastructure:**

- JSON path-based error identification (sensors[0].formulas[1].id)
- Severity classification (error, warning, info)
- Suggested fixes for common configuration mistakes
- User-friendly error messages with context
- Suggested fixes for common issues
- Schema path references for debugging
- User-friendly error messages

**Service Integration:**

- Enhanced validate_config service with schema validation support
- validate_yaml_data() and validate_config_file() API methods
- JSON-serializable validation results for service responses
- Automatic validation during configuration loading
- File path error handling and YAML parsing error detection

**Implementation Files:**

- src/ha_synthetic_sensors/schema_validator.py - Core validation infrastructure
- tests/test_schema_validation.py - 17 comprehensive validation tests
- tests/test_schema_fixtures.py - YAML fixture validation against schema
- Enhanced ConfigManager with automatic schema validation integration

**Note**: Solar migration tests are excluded as span-panel-api extensions are not yet implemented.

## Priority Implementation Status - ALL PHASES COMPLETE

### Phase 1: Service Layer Infrastructure (COMPLETE)

**Status**: FULLY IMPLEMENTED - All 14 service tests passing

**Implemented Services:**

- synthetic_sensors.reload_config - Configuration reloading
- synthetic_sensors.update_sensor - Dynamic sensor updates
- synthetic_sensors.add_variable - Variable management
- synthetic_sensors.remove_variable - Variable cleanup
- synthetic_sensors.evaluate_formula - Formula testing
- synthetic_sensors.validate_config - Configuration validation
- synthetic_sensors.get_sensor_info - Sensor introspection

### Phase 2: Entity Management (COMPLETE)

**Status**: FULLY IMPLEMENTED - All 13 entity management tests passing
**Achievement**: Complete dynamic entity lifecycle management

**Implemented Components:**

- EntityFactory: Dynamic sensor creation
- EntityManager: Lifecycle management
- RegistryIntegration: HA entity registry handling
- StateManager: Preserve state during reloads
- Relationship tracking and error handling

### Phase 3: Advanced Dependencies (COMPLETE)

**Status**: FULLY IMPLEMENTED - All 14 dependency tests passing
**Achievement**: Enhanced dependency resolution with advanced algorithms

**Implemented Features:**

- Circular dependency detection algorithms
- Topological sorting for update order calculation
- Hierarchical dependency resolution
- Cross-reference validation between sensors
- Performance optimization for large dependency graphs
- Dependency caching and change management

### Phase 4: Advanced Formulas (COMPLETE)

**Status**: COMPLETE - Phase 1 mathematical functions implemented and tested
**Current**: All essential mathematical functions fully functional and tested
**Future**: Additional mathematical functions can be added based on user demand

### Phase 5: YAML Schema Validation (COMPLETE)

**Status**: FULLY IMPLEMENTED - Comprehensive JSON Schema validation infrastructure
**Test Coverage**: 17 schema validation tests + fixture validation tests passing
**Achievement**: Production-ready YAML configuration validation with detailed error reporting

**Implemented Features:**

- JSON Schema v4.17.0 validation with comprehensive v1.0 schema definition
- Structured validation error reporting with path-based error identification
- Semantic validation beyond schema structure (duplicates, variable usage)
- Service integration with enhanced validate_config service
- Automatic validation during configuration loading
- Type-safe ValidationError and ValidationResult data structures

**Future Enhancement Strategy for Additional Mathematical Functions:**

**Phase 2: Statistical Functions:Future**

- median - Median of sensor values
- stdev - Standard deviation for variance analysis
- variance - Statistical variance calculations
- mode - Most common value in datasets

**Phase 3: Mathematical Operations (Future)**

- log, log10, log2 - Logarithmic functions
- exp - Exponential function (e^x)
- trunc - Truncate to integer

**Phase 4: Trigonometric Functions (Future)**

- sin, cos, tan - Basic trigonometry
- asin, acos, atan, atan2 - Inverse trigonometry
- degrees, radians - Angle conversions
- hypot - Hypotenuse calculations

**Phase 5: Time-Based Functions (Future)**

- hours_since, days_since - Time calculations
- time_of_day_percent - Temporal percentages

**Phase 6: Home Assistant Specific Functions (Future)**

- delta - Absolute difference between values
- Custom entity reference syntax improvements

**Implementation Approach:**

- Current package is production-ready with Phase 1 functions complete
- Additional functions will be implemented incrementally based on user requests
- Each phase can be implemented independently as needed

## Architecture Overview

### Current Core Components (IMPLEMENTED)

```text
HA Synthetic Sensors Package
├── Configuration Layer (COMPLETE)
│   ├── ConfigManager              # YAML loading and management
│   └── Config/SensorConfig        # Data structures
│
├── Formula Engine Layer (COMPLETE)
│   ├── Evaluator                 # Math evaluation with caching
│   └── NameResolver              # Entity resolution
│
└── Integration Layer (BASIC)
    └── SyntheticSensorsIntegration # Basic integration
```

### Required Extensions (🔴 TO BE IMPLEMENTED)

```text
Enhanced Architecture
├── Service Layer (🔴 MISSING)
│   ├── ServiceProvider          # HA service registration
│   ├── ServiceHandlers          # Service implementation
│   └── ServiceSchemas           # Validation schemas
│
├── Entity Management Layer (🔴 MISSING)
│   ├── EntityFactory            # Dynamic sensor creation
│   ├── EntityManager            # Lifecycle management
│   └── RegistryIntegration      # HA registry handling
│
├── Advanced Formula Layer (🟡 PARTIAL)
│   ├── FunctionRegistry         # Mathematical functions
│   ├── EntityReferenceHandler   # entity() syntax
│   └── HierarchicalEvaluator    # Syn2-to-Syn2 references
│
└── Dependency Layer (🟡 PARTIAL)
    ├── DependencyResolver       # Circular detection
    ├── UpdateOrderCalculator    # Topological sorting
    └── CrossReferenceValidator  # Syn2 cross-references
```

## Implementation Results Summary

### Phase 1: Service Layer (COMPLETE)

**Implementation Status:** **COMPLETE** with comprehensive test coverage

**Test Implementation:**

- **14 comprehensive test methods** covering all service operations
- Service registration/unregistration workflows
- Configuration management services (reload, validate)
- Sensor manipulation services (update, add/remove variables)
- Formula evaluation service with context support
- Error handling and schema validation
- Custom domain configuration support

**Actual Services Implemented:**

- `synthetic_sensors.reload_config` - Configuration reloading
- `synthetic_sensors.update_sensor` - Dynamic sensor updates
- `synthetic_sensors.add_variable` - Variable management
- `synthetic_sensors.remove_variable` - Variable cleanup
- `synthetic_sensors.evaluate_formula` - Formula testing
- `synthetic_sensors.validate_config` - Configuration validation
- `synthetic_sensors.get_sensor_info` - Sensor introspection

### Phase 2: Entity Management (TESTS IMPLEMENTED)

**Implementation Status:** **TEST INFRASTRUCTURE COMPLETE**

**Test Implementation:**

- **15 comprehensive test methods** covering entity lifecycle
- Dynamic entity creation and removal workflows
- Entity registry integration testing
- State preservation during reloads
- Multi-entity operation handling
- Entity relationship tracking
- Error handling and edge cases
- Entity factory pattern testing

**Actual SensorManager Interface Tested:**

```python
# Core lifecycle methods
async def load_configuration(config: Config) -> None
async def reload_configuration(config: Config) -> None
async def remove_sensor(sensor_name: str) -> bool
async def create_sensors(config: Config) -> list[DynamicSensor]

# Information and statistics
def get_sensor(name: str) -> Optional[DynamicSensor]
def get_all_sensors() -> list[DynamicSensor]
def get_sensor_statistics() -> dict[str, Any]
```

### Phase 3: Advanced Dependencies (TESTS IMPLEMENTED)

**Implementation Status:** **TEST INFRASTRUCTURE COMPLETE**

**Test Implementation:**

- **15 comprehensive test methods** covering dependency scenarios
- Circular dependency detection algorithms
- Hierarchical dependency resolution
- Update order calculation (topological sorting)
- Cross-reference validation between sensors
- Complex dependency scenario handling
- Performance testing with large graphs
- Dependency change management during runtime

**Dependency Resolver Interface Tested:**

```python
# Core dependency methods
def build_dependency_graph(configs: list[SensorConfig]) -> DependencyGraph
def detect_circular_dependencies(configs: list[SensorConfig]) -> list[list[str]]
def get_update_order(configs: list[SensorConfig]) -> list[str]
def validate_dependencies(configs: list[SensorConfig]) -> bool
def resolve_entity_references(formula: str) -> set[str]
```

## Data Structures

### Enhanced Configuration Types

```python
@dataclass(frozen=True)
class AdvancedFormulaConfig:
    """Enhanced formula configuration with function support."""
    name: str
    formula: str
    variables: dict[str, str]
    functions: list[str] = field(default_factory=list)  # Required functions
    dependencies: set[str] = field(default_factory=set)  # Auto-extracted
    entity_references: set[str] = field(default_factory=set)  # entity() calls

@dataclass(frozen=True)
class ServiceConfig:
    """Configuration for service layer."""
    enabled_services: list[str] = field(default_factory=list)
    service_schemas: dict[str, dict] = field(default_factory=dict)
    error_handling: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class DependencyGraph:
    """Dependency graph for sensor relationships."""
    nodes: set[str]
    edges: dict[str, set[str]]  # node -> dependencies
    cycles: list[list[str]] = field(default_factory=list)
    update_order: list[str] = field(default_factory=list)
```

## Testing Strategy

### Test Coverage Goals

**Target Coverage:**

- Service Layer: 100% (new implementation)
- Advanced Formulas: 90% (extending existing)
- Entity Management: 100% (new implementation)
- Dependency Resolution: 90% (extending existing)

### Test Organization

```python
# Current Test Files (Complete)
tests/test_config_manager.py       # 14 tests - Configuration management
tests/test_evaluator.py   # 10 tests - Formula evaluation
tests/test_formula_evaluation.py   # 8 tests - Mathematical expressions
tests/test_integration.py          # 4 tests - Basic integration
tests/test_name_resolver.py        # 14 tests - Entity resolution

# Priority Test Files (IMPLEMENTED)
tests/test_service_layer.py        # 14 tests - Service infrastructure
tests/test_entity_management.py    # 15 tests - Dynamic entity lifecycle
tests/test_advanced_dependencies.py # 15 tests - Dependency resolution enhancement

# Future Test Files (🟡 FUTURE)
tests/test_advanced_formulas.py    # Mathematical functions & entity refs
```

### Test Implementation Priority

1. **Immediate**: Service layer tests (blocking for HA integration)
2. **Short-term**: Advanced formula tests (user-facing features)
3. **Medium-term**: Entity management tests (infrastructure)
4. **Future**: Advanced dependency tests (optimization)

## Example Usage After Enhancement

### Enhanced YAML Configuration

```yaml
# Enhanced syn2_config.yaml
version: "1.0"
global_settings:
  enable_advanced_functions: true
  enable_entity_references: true

sensors:
  # Advanced mathematical functions
  - name: "Solar Analytics"
    formulas:
      - name: "solar_sold_positive"
        formula: "abs(min(entity('sensor.grid_power'), 0))"
        unit_of_measurement: "W"
        device_class: "power"

  # Hierarchical sensor references
  - name: "Total Home Power"
    formulas:
      - name: "total_consumption"
        formula: "entity('sensor.hvac_total') + entity('sensor.lighting_total')"
        unit_of_measurement: "W"
        device_class: "power"

  # Complex mathematical expressions
  - name: "Efficiency Metrics"
    formulas:
      - name: "hvac_efficiency"
        formula: "max(0, min(100, (target_temp - actual_temp) / target_temp * 100))"
        variables:
          target_temp: "input_number.target_temperature"
          actual_temp: "sensor.current_temperature"
        unit_of_measurement: "%"
```

### Enhanced Service Usage

```yaml
# Advanced service calls
service: ha_synthetic_sensors.load_config
data:
  config: |
    sensors:
      - name: "Advanced Analytics"
        formulas:
          - name: "efficiency_index"
            formula: "round(abs(consumption / production) * 100, 2)"
            variables:
              consumption: "sensor.total_consumption"
              production: "sensor.solar_production"
  validate_before_load: true
  replace_existing: false

# Validation with detailed feedback
service: ha_synthetic_sensors.validate_config
data:
  config_file: "/config/syn2_advanced.yaml"
  check_entity_availability: true
  validate_dependencies: true
```

## Success Metrics

### Technical Metrics

1. **Service Integration** - All HA services functional and validated
2. **Formula Capabilities** - Support for mathematical functions and entity references
3. **Entity Management** - Dynamic creation/update/removal working seamlessly
4. **Performance** - Formula evaluation <10ms per sensor with functions
5. **Reliability** - Error handling covers all edge cases including function errors

### User Experience Metrics

1. **Service Responsiveness** - Service calls complete quickly with proper feedback
2. **Formula Flexibility** - Users can create complex mathematical expressions
3. **Entity Discovery** - Easy referencing of any HA entity including other Syn2 sensors
4. **Error Clarity** - Clear validation and error messages for all failure scenarios

## Future YAML Feature Exploration

### Advanced YAML Capabilities (Future Investigation)

**Schema Validation:**

- JSON Schema integration for configuration validation
- Custom validation rules for sensor configurations
- Automated schema generation from dataclasses

**Configuration Management:**

- Version-aware configuration loading
- Migration tools for configuration updates
- Configuration diffing and merging capabilities

**Template System:**

- YAML template expansion with variables
- Reusable configuration snippets
- Conditional configuration based on system state

**Advanced YAML Features:**

- YAML anchors and references for configuration reuse
- Include files for modular configuration
- Environment variable substitution
- Dynamic configuration generation

**Note**: These features will be evaluated based on user needs and complexity vs benefit analysis. The focus remains on
supporting synthetic sensor requirements rather than implementing comprehensive YAML processing.

## Recent Development Achievements (2025)

### Non-Numeric State Handling Enhancement

**Status**: COMPLETE - Enhanced error handling for non-numeric entity states
**Achievement**: Implemented intelligent error classification system

**Technical Implementation:**

- **Smart Error Classification**: Distinguishes between fatal and transitory non-numeric state errors
  - FATAL: Fundamentally non-numeric entities (binary_sensor.door returning "on"/"off")
  - TRANSITORY: Correctly configured entities with temporary non-numeric states (sensor.temperature showing "unknown" due
    to device offline)

- **Two-Tier Circuit Breaker Pattern**:
  - Tier 1: Fatal errors trigger circuit breaker to prevent resource waste
  - Tier 2: Transitory errors allow continued evaluation with proper state propagation

- **Enhanced Dependency Parser**: Fixed entity ID parsing to correctly handle direct references (sensor.temperature + 1)

- **Entity Type Analysis**: Analyzes entity domains and device_classes to determine expected numeric behavior

- **Non-Numeric State Exception**: Replaced silent failures with proper exception handling and logging

**Test Coverage**: 6 comprehensive test methods covering all scenarios

**Files Modified:**

- evaluator.py - Enhanced error handling and circuit breaker logic
- dependency_parser.py - Fixed entity ID parsing for direct references
- test_non_numeric_states.py - Comprehensive test suite

### Next Steps

The package is now ready for:

1. **Production Testing**: Validate against real Home Assistant environments
2. **Advanced Formulas**: Mathematical functions implementation (when needed)
3. **Solar Migration**: Integration with span-panel-api extensions (future)

## Type Safety and TypedDicts Plan (2024)

### Current State

- The codebase currently uses `dict[str, Any]` for YAML config parsing, formula variables, attributes, and service data structures.
- This approach is flexible but does not provide type safety or IDE support, and can lead to runtime errors if the config
  structure changes or is misused.

### Requirements from Feature Planning

- The YAML configuration and service schemas are strictly structured, with required and optional fields clearly defined.
- Variables and attributes have predictable types (e.g., `dict[str, str]` for variables,
  `dict[str, str | float | int | bool]` for attributes).
- Service interfaces expect and return well-defined data structures.

### Plan for TypedDict Adoption

- Introduce `TypedDict` classes for all configuration and service data structures:
  - `FormulaConfigDict`, `SensorConfigDict`, `ConfigDict` for YAML config
  - TypedDicts for service call schemas and results
- Refactor parsing, validation, and service handler code to use these types instead of `dict[str, Any]`.
- Update function signatures and class attributes to use explicit types and unions where appropriate.
- Update tests to use the new TypedDicts for fixtures and validation.
- Use `mypy` to enforce type safety and catch issues early.

### Rationale

- TypedDicts provide static type checking for dict-like objects, improving code safety and maintainability.
- They enable better IDE support, autocompletion, and documentation.
- They help ensure that configuration and service data structures match the documented requirements and schemas.

### Next Steps

1. Define TypedDicts for all config and service data structures in the codebase.
2. Refactor config parsing and validation code to use these types.
3. Update service layer and tests to use TypedDicts.
4. Run and fix any type errors with `mypy`.
5. Document the new types and update developer guidelines.

## Additional Type Analysis and Recommendations (2024)

Based on the requirements and code review, the following areas have been identified for type improvements beyond config and
service TypedDicts:

### 1. Formula Variables and Attributes

- **Current:** `dict[str, Any]` for variables and attributes.
- **Recommendation:**
  - Use `dict[str, str]` for formula variables (mapping variable names to entity IDs).
  - Use `dict[str, str | float | int | bool]` for attributes and global_settings.

### 2. Formula Result Types

- **Current:** `Any` for formula results and sensor state values.
- **Recommendation:**
  - Use `float | int | str | None` for formula results and Home Assistant state values.
  - For state attributes, use `dict[str, str | float | int | bool | None]`.

### 3. Entity Description and Home Assistant Patterns

- **Current:** Some entity attributes and descriptions use `Any` or are untyped.
- **Recommendation:**
  - Use explicit types for `_attr_*` attributes (e.g., `_attr_native_value: float | int | str | None`).
  - For custom entity descriptions, use dataclasses with explicit types and store direct references to custom fields in the
    entity class (see developer_attribute_readme.md best practices).

### 4. Service Layer and API Schemas

- **Current:** Service schemas and results use `dict[str, Any]`.
- **Recommendation:**
  - Use TypedDicts for all service call data and results.
  - Avoid `dict[str, Any]` in service interfaces.

### 5. General: Avoid `Any` in Public APIs

- **Current:** `Any` is used in several public APIs and function signatures.
- **Recommendation:**
  - Only use `Any` for truly dynamic, untyped data (e.g., raw YAML blobs before validation).
  - For all internal and public APIs, prefer explicit types, unions, or TypedDicts.

### 6. Testing and Validation

- **Current:** Test fixtures and service tests use untyped dicts.
- **Recommendation:**
  - Use the same TypedDicts in tests for config and service data.

---

**Refactoring Checklist:**

1. TypedDicts for config and service data structures (in progress)
2. Formula variables and attributes: use specific dict types
3. Formula result and state types: use explicit unions
4. Entity attribute and description types: follow HA best practices
5. Service schemas: TypedDicts for all service interfaces
6. Update tests to use TypedDicts and explicit types
7. Remove `Any` from public APIs wherever possible

## TypedDict Implementation Progress (2024)

### Completed

1. **Config Structure TypedDicts** - Successfully implemented FormulaConfigDict, SensorConfigDict, and ConfigDict for YAML
   parsing with proper type safety
2. **Home Assistant Mocking** - Created comprehensive mocking system for all HA imports, enabling local
   testing
3. **Service Schema TypedDicts** - Added UpdateSensorData, AddVariableData, RemoveVariableData, EvaluateFormulaData,
   and service response types
4. **Basic Type Improvements** - Updated config attributes from dict[str, Any] to dict[str, str | float | int | bool]
5. **Evaluator Context Types** - Added ContextValue type alias and updated evaluation context to use specific types
6. **Flexible Attribute Types** - Created AttributeValue type alias to handle complex attributes (lists, nested dicts)
   while maintaining type safety
7. **Entity Factory TypedDicts** - Updated entity factory to use SensorConfigDict and FormulaConfigDict, added
   EntityCreationResult and ValidationResult TypedDicts
8. **Sensor Manager Types** - Updated sensor state types and statistics return types with proper type safety
9. **Test Infrastructure** - All 121 tests passing with comprehensive TypedDict support and proper mock handling
10. **Evaluator Result Types** - Implemented EvaluationResult, CacheStats, and DependencyValidation TypedDicts for formula evaluation
11. **Service Response Types** - Added structured TypedDicts for EvaluationResponseData, ValidationResponseData,
    SensorInfoData, and AllSensorsInfoData
12. **Name Resolver Types** - Implemented VariableValidationResult, EntityReference, and FormulaDependencies TypedDicts
    for comprehensive name resolution typing
13. **Integration Layer Types** - Added IntegrationSetupResult, IntegrationStatus, ConfigValidationResult, AutoConfigDiscovery,
    and IntegrationCleanupResult TypedDicts for HA integration operations

### In Progress

1. **Documentation** - Finalizing comprehensive type safety documentation

### Remaining Tasks

1. **Type Documentation** - Update developer documentation with new TypedDict interfaces
2. **Final Validation** - Comprehensive testing of all TypedDict implementations

### Known Issues

- None currently - all tests passing with TypedDict implementations

## TypedDict Implementation Complete (2024)

### Implementation Summary

The comprehensive TypedDict implementation has successfully transformed the ha-synthetic-sensors package from loose
dict[str, Any] types to strict, well-defined data structures across all major components:

#### Core Configuration Types

- FormulaConfigDict, SensorConfigDict, ConfigDict - YAML parsing structures
- AttributeValue type alias for flexible formula metadata handling

#### Evaluation & Processing Types

- EvaluationResult - Formula evaluation results with success/error states
- CacheStats - Evaluator performance monitoring data
- DependencyValidation - Entity dependency validation results
- ContextValue type alias for evaluation contexts

#### Service Layer Types

- UpdateSensorData, AddVariableData, RemoveVariableData - Service call schemas
- EvaluationResponseData, ValidationResponseData - Service response structures
- SensorInfoData, AllSensorsInfoData - Sensor information responses

#### Entity Management Types

- EntityCreationResult, ValidationResult - Entity factory results
- EntityDescription dataclass for sensor metadata

#### Name Resolution Types

- VariableValidationResult - Variable mapping validation
- EntityReference - Entity reference information
- FormulaDependencies - Complete dependency analysis

#### Integration Layer Types

- IntegrationSetupResult, IntegrationStatus - HA integration operations
- ConfigValidationResult - YAML validation results
- AutoConfigDiscovery, IntegrationCleanupResult - Lifecycle management

### Key Benefits Achieved

1. **Type Safety**: Eliminated dict[str, Any] usage throughout the codebase
2. **IDE Support**: Enhanced autocompletion and intellisense for developers
3. **API Clarity**: Clear contracts for all public interfaces
4. **Runtime Safety**: Structured data validation at package boundaries
5. **Maintainability**: Easier refactoring with compile-time type checking

### Testing Status

- **121/121 tests passing** with all TypedDict implementations
- Comprehensive Home Assistant mocking system enables local development
- Backward compatibility maintained for existing integrations

### Next Steps

1. Document the new typed interfaces in developer guidelines
2. Validate with static type checking tools (mypy)
3. Consider migrating to Pydantic models for runtime validation (future enhancement)
