# Modular Architecture Guide for HA Synthetic Sensors

## Overview

This document outlines the modular architecture implemented to break apart large monolithic files into focused,
maintainable modules. The architecture follows clear separation of concerns and provides well-defined interfaces for testing.

## Core Design Principles

**Single Responsibility**: Each module handles one specific aspect of functionality
**Clear Interfaces**: Modules expose well-defined public APIs
**Dependency Injection**: Main classes delegate to handler modules
**Testability**: Modules can be tested independently with clear contracts and are segment in appropriate test module directories
**Maintainability**: Code is organized by functional area, not just size
**Implementation Lint Compliance**: Imports at the top of the file, strict type checking, mypy and pylint compliant
(tests do not need mypy or pylint compliance)
**Strict Typing**:  The implementation must use strict typing, use of Any types is heavily discouraged; use TypedDict where possible
**No Implementation Pylint Errors**: For example on protect access warnings, use a property getter
**Real YAML Fixtures**: If YAML is used in a test, reuse the existing robust YAML fixtures in tests/yaml_fixtures
**Imports relative to repo root**: yaml fixture import should be relative to the repository root for ha-synthetic-sensors
   as pytest will be run from the root
**No Dead Code**: No duplicate or dead code
**No Fallback Code**: No fallback code is allowed, deterministic behavior only
**No Backward Compatability**: This is clean slate development
**Minimum Info Logging**: Info logging should be limited to what a user would normally see for operation, not internal details
**Approriate debug Logging**: Excessive logging will be rejected by HA, Debug only on entry or setup in modules,
not loop level loggging
**Use Formatter Fixers**: For fixing whitespace and formatting use a formatter that fixes issues, don't fix white space manually
**No Anti-Test Patterns**: Tests should tests what they purport to test with meaningful results.
**Test Results Are Known**: Tests should use known results, not rely on the thing being tested - use test fixtures where possible

## Module Architecture

### Evaluator Module System

The `Evaluator` class delegates specialized functionality to focused handler modules:

#### EvaluatorDependency (`evaluator_dependency.py`)

**Responsibility**: Dependency parsing, validation, and resolution
**Interface**:

```python
class EvaluatorDependency:
    def __init__(self, hass: HomeAssistant, data_provider_callback=None)

    # Core dependency operations
    def get_formula_dependencies(self, formula: str) -> set[str]
    def extract_formula_dependencies(self,
                                     config: FormulaConfig,
                                     context: dict[str, ContextValue] | None = None) -> set[str]
    def extract_and_prepare_dependencies(self,
                                         config: FormulaConfig,
                                         context: dict[str, ContextValue] | None) -> tuple[set[str], set[str]]

    # Dependency validation
    def check_dependencies(self,
                           dependencies: set[str],
                           context: dict[str, ContextValue] | None = None,
                           collection_pattern_entities: set[str] | None = None) -> tuple[set[str], set[str]]
    def check_single_entity_dependency(self, entity_id: str, collection_pattern_entities: set[str]) -> str
    def validate_dependencies(self, dependencies: set[str]) -> DependencyValidation

    # Integration entity management
    def update_integration_entities(self, entity_ids: set[str]) -> None
    def get_integration_entities(self) -> set[str]
```

**Test Focus**:

- Dependency extraction from formulas with various patterns
- Entity availability checking (missing vs unavailable vs ok)
- Collection pattern resolution
- Integration entity push-based pattern
- Data provider callback integration

#### EvaluatorCache (`evaluator_cache.py`)

**Responsibility**: Formula result caching and cache management
**Interface**:

```python

class EvaluatorCache:
    def __init__(self, cache_config: CacheConfig | None = None)

    # Cache operations
    def check_cache(self,
                    config: FormulaConfig,
                    context: dict[str, ContextValue] | None,
                    cache_key_id: str) -> EvaluationResult | None
    def cache_result(self,
                     config: FormulaConfig,
                     context: dict[str, ContextValue] | None,
                     cache_key_id: str, result: float) -> None
    def clear_cache(self, formula_name: str | None = None) -> None

    # Cache management
    def get_cache_stats(self) -> CacheStats
    def filter_context_for_cache(self, context: dict[str, ContextValue] | None) -> dict[str, str | float | int | bool] | None
    def invalidate_cache_for_entity(self, entity_id: str) -> None
    def get_cache_size(self) -> int
    def get_cache_hit_rate(self) -> float
```

**Test Focus**:

- Cache hit/miss behavior with different contexts
- Context filtering for cacheability
- Cache invalidation strategies
- Cache statistics accuracy
- Memory management and size limits

### SensorSet Module System

The `SensorSet` class delegates specialized functionality to focused handler modules:

#### SensorSetGlobalSettings (`sensor_set_global_settings.py`)

**Responsibility**: Global settings management and validation
**Interface**:

```python
class SensorSetGlobalSettings:
    def __init__(self, storage_manager: StorageManager, sensor_set_id: str)

    # Global settings operations
    def get_global_settings(self) -> dict[str, Any]
    async def async_set_global_settings(self, global_settings: dict[str, Any], current_sensors: list[SensorConfig]) -> None
    async def async_update_global_settings(self, updates: dict[str, Any], current_sensors: list[SensorConfig]) -> None

    # Modification support
    def build_final_global_settings(self, modification_global_settings: dict[str, Any] | None) -> dict[str, Any]
    def update_global_variables_for_entity_changes(self,
                                                   variables: dict[str, Any],
                                                   entity_id_changes: dict[str, str]) -> dict[str, Any]
```

**Test Focus**:

- Global settings CRUD operations
- Conflict validation with sensor variables
- Entity ID change propagation
- Modification workflow integration

#### SensorSetEntityIndex (`sensor_set_entity_index.py`)

**Responsibility**: Entity tracking and index management
**Interface**:

```python
class SensorSetEntityIndex:
    def __init__(self, storage_manager: StorageManager, sensor_set_id: str, entity_index: EntityIndex)

    # Entity tracking
    def is_entity_tracked(self, entity_id: str) -> bool
    def get_entity_index_stats(self) -> dict[str, Any]

    # Index management
    def rebuild_entity_index(self, sensors: list[SensorConfig]) -> None
    def rebuild_entity_index_for_modification(self,
                                              final_sensors: dict[str, SensorConfig],
                                              final_global_settings: dict[str, Any]) -> None
    def populate_entity_index_from_sensors(self, final_sensors: dict[str, SensorConfig]) -> None
    def populate_entity_index_from_global_settings(self, final_global_settings: dict[str, Any]) -> None
```

**Test Focus**:

- Entity index accuracy after sensor changes
- Modification-aware index rebuilding
- Registry event storm protection
- Statistics reporting

#### SensorSetBulkOps (`sensor_set_bulk_ops.py`)

**Responsibility**: Bulk operations, validation, and modification workflows
**Interface**:

```python
class SensorSetBulkOps:
    def __init__(self, storage_manager: StorageManager, sensor_set_id: str)

    # Validation
    def validate_modification(self, modification: SensorSetModification, current_sensors: dict[str, SensorConfig]) -> None
    def validate_add_sensors(self,
                             modification: SensorSetModification,
                             current_sensors: dict[str, SensorConfig],
                             errors: list[str]) -> None
    def validate_remove_sensors(self,
                                modification: SensorSetModification,
                                current_sensors: dict[str, SensorConfig],
                                errors: list[str]) -> None
    def validate_update_sensors(self,
                                modification: SensorSetModification,
                                current_sensors: dict[str, SensorConfig],
                                errors: list[str]) -> None
    def validate_operation_conflicts(self,
                                     modification: SensorSetModification,
                                     errors: list[str]) -> None
    def validate_global_settings_changes(self,
                                         modification: SensorSetModification,
                                         current_sensors: dict[str, SensorConfig],
                                         errors: list[str]) -> None

    # Modification support
    def build_final_sensor_list(self,
                                modification: SensorSetModification,
                                current_sensors: dict[str, SensorConfig]) -> dict[str, SensorConfig]
    def apply_entity_id_changes_to_sensors(self,
                                           entity_id_changes: dict[str, str],
                                           sensors: dict[str, SensorConfig]) -> dict[str, SensorConfig]
    def validate_final_state(self,
                             final_global_settings: dict[str, Any],
                             final_sensors: dict[str, SensorConfig]) -> None
```

**Test Focus**:

- Complex modification validation (add/remove/update conflicts)
- Entity ID change propagation through formulas
- Final state validation
- Error aggregation and reporting

### Storage Module System

The `StorageManager` class delegates specialized functionality to handler modules:

#### Storage Handler Modules

- **SensorOpsHandler** (`storage_sensor_ops.py`): Individual sensor CRUD operations
- **SensorSetOpsHandler** (`storage_sensor_set_ops.py`): Sensor set operations and metadata
- **ValidationHandler** (`storage_validator.py`): Configuration validation
- **YamlHandler** (`storage_yaml_handler.py`): YAML import/export operations

### SensorSet CRUD Operations

The `SensorSet` class provides a clean CRUD interface for sensor set management:

#### SensorSet CRUD Interface

```python
class SensorSet:
    # Sensor set lifecycle
    @classmethod
    async def async_create(cls, storage_manager: StorageManager, sensor_set_id: str, **kwargs) -> SensorSet
    async def async_delete(self) -> bool

    # Sensor CRUD within set
    async def async_add_sensor(self, sensor_config: SensorConfig) -> None
    async def async_update_sensor(self, sensor_config: SensorConfig) -> bool
    async def async_remove_sensor(self, unique_id: str) -> bool
    def get_sensor(self, unique_id: str) -> SensorConfig | None
    def list_sensors(self) -> list[SensorConfig]

    # Global settings management
    async def async_set_global_settings(self, global_settings: dict[str, Any]) -> None
    async def async_update_global_settings(self, updates: dict[str, Any]) -> None
    def get_global_settings(self) -> dict[str, Any]
```

**Note**: SensorSet CRUD operations work through the StorageManager - the SensorSet class coordinates and delegates
to storage operations while maintaining the clean interface.

## Testing Strategy

### Module-Level Testing

Each handler module should have focused unit tests that verify:

1. **Interface Contracts**: All public methods work as documented
2. **Edge Cases**: Boundary conditions and error scenarios
3. **State Management**: Proper handling of internal state
4. **Error Handling**: Appropriate exceptions and error messages

### Integration Testing

Integration tests should verify:

1. **Module Coordination**: Handler modules work together correctly
2. **Data Flow**: Information passes correctly between modules
3. **State Consistency**: Changes in one module are reflected properly in others
4. **Transaction Integrity**: Complex operations maintain data integrity

### Test Organization

Tests should be organized by functional area, not by file structure:

```text
tests/
├── evaluator/
│   ├── test_dependency_management.py      # EvaluatorDependency tests
│   ├── test_cache_management.py           # EvaluatorCache tests
│   ├── test_evaluator_integration.py      # Evaluator coordination tests
│   └── advanced/                          # Advanced evaluator features
│       └── test_hierarchical_dependencies.py  # Hierarchical synthetic sensor dependencies
├── sensor_set/
│   ├── test_global_settings.py            # SensorSetGlobalSettings tests
│   ├── test_entity_index.py               # SensorSetEntityIndex tests
│   ├── test_bulk_operations.py            # SensorSetBulkOps tests
│   └── test_sensor_set_integration.py     # SensorSet coordination tests
├── storage/
|    ├── test_sensor_operations.py          # SensorOpsHandler tests
|    ├── test_sensor_set_operations.py      # SensorSetOpsHandler tests
|    ├── test_validation.py                 # ValidationHandler tests
|    ├── test_yaml_operations.py            # YamlHandler tests
|    └── test_storage_integration.py        # StorageManager coordination tests
└── integration/                            # integration level test using public API
```

## Key Testing Patterns

### 1. Handler Module Isolation

Test handler modules independently by mocking their dependencies:

```python
# Test EvaluatorDependency without full Evaluator
def test_dependency_extraction():
    hass = Mock()
    handler = EvaluatorDependency(hass)
    dependencies = handler.get_formula_dependencies("sensor.test + 5")
    assert dependencies == {"sensor.test"}
```

### 2. Integration Testing with Real Coordination

Test the main classes to ensure proper delegation:

```python
# Test that Evaluator properly delegates to handlers
def test_evaluator_uses_dependency_handler():
    evaluator = Evaluator(hass)
    # Verify that evaluator.get_formula_dependencies()
    # calls dependency_handler.get_formula_dependencies()
```

### 3. State Consistency Testing

Test that changes through one interface are reflected in others:

```python
# Test that global settings changes invalidate cache
def test_global_settings_invalidate_cache():
    sensor_set = SensorSet(storage_manager, "test_set")
    # Change global settings
    await sensor_set.async_set_global_settings({"var": "new_value"})
    # Verify cache was invalidated for affected formulas
```

### 4. Error Propagation Testing

Test that errors from handler modules are properly handled:

```python
# Test that validation errors are properly propagated
def test_validation_error_propagation():
    sensor_set = SensorSet(storage_manager, "test_set")
    with pytest.raises(SyntheticSensorsError):
        await sensor_set.async_modify(invalid_modification)
```

## Migration Guide for Existing Tests

### Step 1: Identify Test Categories

Review existing tests and categorize them:

- **Handler-specific**: Tests that focus on one functional area
- **Integration**: Tests that verify coordination between modules
- **End-to-end**: Tests that verify complete workflows

### Step 2: Refactor Handler-Specific Tests

Move tests to focus on handler module interfaces:

**Before** (testing monolithic class):

```python
def test_evaluator_dependency_extraction():
    evaluator = Evaluator(hass)
    deps = evaluator._extract_formula_dependencies(config)
    # Test implementation details
```

**After** (testing handler interface):

```python
def test_dependency_handler_extraction():
    handler = EvaluatorDependency(hass)
    deps = handler.extract_formula_dependencies(config)
    # Test public interface
```

### Step 3: Update Integration Tests

Ensure integration tests verify proper delegation:

```python
def test_evaluator_delegates_to_handlers():
    evaluator = Evaluator(hass)
    # Mock handler methods
    evaluator._dependency_handler.check_dependencies = Mock(return_value=(set(), set()))
    evaluator._cache_handler.check_cache = Mock(return_value=None)
    # Verify delegation occurs
    result = evaluator.evaluate_formula(config)
    evaluator._dependency_handler.check_dependencies.assert_called_once()
    evaluator._cache_handler.check_cache.assert_called_once()
```

### Step 4: Preserve End-to-End Tests

Keep high-level tests that verify complete workflows work correctly with the new architecture.

## Benefits of This Architecture

1. **Testability**: Each module can be tested independently
2. **Maintainability**: Changes are localized to specific functional areas
3. **Readability**: Code organization matches mental models
4. **Extensibility**: New functionality can be added as new handler modules
5. **Debugging**: Issues can be isolated to specific modules

## Implementation Notes

- Handler modules are initialized in the main class constructors
- Main classes delegate to handlers rather than implementing functionality directly
- Handler modules maintain their own state when appropriate
- Error handling is consistent across all modules
- Logging is coordinated to provide clear operational visibility
