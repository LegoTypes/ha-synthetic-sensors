# Comparison Handler Design

## Overview

The condition parser in the synthetic sensors integration uses a preprocessing + hierarchical comparison architecture.
User-defined comparison handlers can preprocess operands (unit conversion, normalization, etc.) and return built-in type
operands, which then flow through the existing hierarchical built-in comparison logic. This design provides extensibility
while maintaining type safety and leveraging proven comparison logic.

## Current Architecture

### Simple Pipeline: Extension Check → Built-in Comparison

The comparison system uses a straightforward two-step pipeline:

1. **Extension Selection**: Check if YAML configuration defines a user extension for these operand types
2. **Built-in Processing**: Built-in comparison operates directly on operands without requiring metadata

This approach provides:

- **Simplicity**: No complex metadata extraction or fallback logic
- **Type Safety**: User extensions return built-in types that flow through proven comparison logic
- **Clear Separation**: Extension selection is separate from built-in comparison logic
- **Deterministic Behavior**: Either user extension runs first, or built-in comparison runs directly

### Current Implementation

The system uses a simple two-phase pipeline:

1. **Extension Registration Check**: The `MetadataExtractor.extract_all_metadata` method currently returns empty metadata for
   all non-UserType objects since no extension registration system exists yet
2. **Handler Selection**: A future `_extract_handler_from_metadata` method will check if YAML configuration defines a handler
   for the operand types
3. **Built-in Comparison**: When no user extension is found, built-in comparison logic operates directly on the operands
   without requiring metadata

**Current Reality**: Today, no extension registration system exists, so the handler extraction always returns None and
built-in comparison proceeds immediately.

**Future Vision**: When YAML-based extension registration is implemented, user extensions will preprocess operands and return
built-in types for standard comparison.

**Key Design Point**: Metadata is used solely to determine if user extensions should handle operand types. Built-in
comparisons operate directly on operands and don't require metadata.

### Handler Interface

The system defines a simple handler interface for future extensions:

**User Extension Handlers (Future):**

- `can_handle()`: Checks if this handler can process the given operand types based on YAML configuration
- `preprocess()`: Takes two operands and returns a tuple of built-in type operands for standard comparison

**Built-in Comparison Logic:**

- Operates directly on operands without requiring metadata
- Uses Python's built-in comparison semantics where appropriate
- Handles type-specific comparison logic for essential operations

### Example: Future Energy Value Comparison Flow

This example demonstrates how the future extension system will work:

**Current State**: No extension registration exists, so built-in comparison proceeds directly

**Future State** (when YAML extension registration is implemented):

1. **YAML Configuration**: Define energy extension in YAML configuration
2. **Handler Registration**: Register EnergyComparisonHandler for energy operand types
3. **Extension Check**: System checks if operands match registered extension types
4. **Preprocessing**: If match found, energy handler converts units and returns built-in float values
5. **Built-in Comparison**: Standard comparison logic handles the resulting float operands

**Key Benefits:**

- **No Complex Metadata**: No metadata extraction until extension system exists
- **Simple Pipeline**: Either extension runs first, or built-in comparison runs directly
- **YAML-Driven**: Extensions configured declaratively, not through complex metadata analysis
- **Efficient**: No unnecessary metadata processing when no extensions are configured

## Current Handlers

### NumericComparisonHandler

Handles numeric comparisons with operators: `<`, `>`, `<=`, `>=`

- Validates that both operands are numeric types (int, float)
- Supports all comparison operators for numeric values
- Uses Python's built-in numeric comparison semantics

## Recommendations for Extension

### 1. String Comparison Handler

Add support for string comparisons with lexicographic ordering:

- Validates that both operands are strings
- Supports operators: `<`, `>`, `<=`, `>=`
- Uses Python's lexicographic string ordering
- Handles Unicode string comparisons properly

**Use Cases:**

- Device name filtering: `"attribute:name>='Living'"`
- State ordering: `"state:>='active'"`

### 2. Boolean Comparison Handler

Add support for boolean comparisons with logical ordering:

- Validates that both operands are boolean values
- Supports operators: `<`, `>`, `<=`, `>=`
- Uses logical ordering where False < True
- Converts booleans to integers for comparison (False=0, True=1)

**Use Cases:**

- Flag comparisons: `"attribute:enabled>=True"`
- State filtering: `"state:>='on'"`

### 3. DateTime Comparison Handler

Add support for temporal comparisons:

- Validates that operands are datetime objects or ISO datetime strings
- Supports all comparison operators for temporal ordering
- Handles timezone-aware comparisons
- Converts string representations to datetime objects

**Use Cases:**

- Time-based filtering: `"attribute:last_seen>='2024-01-01T00:00:00Z'"`
- Age-based filtering: `"state:updated_at>=yesterday"`

### 4. Version Comparison Handler

Add support for semantic version comparisons:

- Validates that operands are semantic version strings
- Supports all comparison operators for version ordering
- Handles version prefixes (e.g., "v2.1.0")
- Uses semantic version logic (not lexicographic)

**Use Cases:**

- Firmware filtering: `"attribute:firmware_version>='2.1.0'"`
- Software compatibility: `"attribute:app_version<'3.0.0'"`

## Handler Selection Algorithm

The comparison system uses a sophisticated type analysis and handler selection algorithm:

### Type Hierarchy and Conversion Rules

The system categorizes types into distinct categories:

- **NUMERIC**: int, float, Decimal
- **STRING**: str
- **BOOLEAN**: bool
- **DATETIME**: datetime objects and ISO strings
- **VERSION**: semantic version strings
- **UNKNOWN**: unrecognized types

### Type Analysis Process

The type analyzer:

1. Checks for None values and raises explicit errors
2. Identifies boolean values first (since bool is a subclass of int in Python)
3. Categorizes numeric types
4. Analyzes strings for datetime and version patterns
5. Detects datetime objects
6. Returns UNKNOWN for unrecognized types

### String Type Detection

For string values, the system uses pattern matching to identify:

- **Datetime strings**: ISO format detection with timezone support
- **Version strings**: Semantic version pattern matching
- **Generic strings**: Default category for non-specialized strings

### Conflict Resolution

When strings match multiple patterns (e.g., "2024.01.01" could be datetime or version):

1. Applies stricter validation for each pattern
2. Prioritizes datetime over version for ambiguous cases
3. Falls back to generic string if neither pattern is definitive

### Handler Selection Matrix

The system maintains a compatibility matrix that defines:

- **Same-type comparisons**: Direct handler assignment
- **Mixed-type conversions**: Explicit conversion paths with handler preferences
- **Forbidden combinations**: Type pairs that cannot be compared

### Operator Validation

Each type category supports specific operators:

- **Essential operators** (Phase 1): Focus on commonly needed comparisons
- **Full operators** (future phases): Complete operator support for all types

### Handler Selection Process

1. Validates that the operator is a comparison operator
2. Categorizes both operand types
3. Checks for unknown types and raises errors
4. Validates operator compatibility with detected types
5. Looks up handler preferences in the compatibility matrix
6. Tries handlers in preference order
7. Raises detailed error if no handler can process the comparison

## Shared Infrastructure for Future Operation Systems

### Operation Context Framework

The system defines operation contexts for different types of operations:

- **COMPARISON**: ==, !=, <, <=, >, >=
- **ARITHMETIC**: +, -, \*, /, %
- **STRING_OPS**: concatenation, formatting
- **LOGICAL**: and, or, not
- **BITWISE**: &, |, ^, <<, >>

### Base Operation Selector

Provides shared functionality for operation-specific selectors:

- Determines operation context for operators
- Defines base handler selection interface
- Enables extensibility to future operation systems

### Future Formula Operation System

The architecture supports future formula operations through:

- Shared type analysis components
- Consistent operator validation patterns
- Extensible handler selection framework
- Common error handling infrastructure

## Handler Registration System

### Registration Interface

The system provides methods to:

- Register comparison handlers with unique names
- Retrieve all registered handlers
- Initialize default handlers automatically
- Support custom handler registration

### Default Handler Registration

The system automatically registers these default handlers:

- Numeric comparison handler
- String comparison handler
- Boolean comparison handler
- DateTime comparison handler
- Version comparison handler

### Handler Discovery

The system uses hierarchical selection to find appropriate handlers:

1. Gets all available handlers
2. Uses the handler selector to find the best match
3. Returns the selected handler for comparison

## Python Semantics vs Custom Handlers

### What Python Handles Well

The system leverages Python's built-in comparison semantics for:

- Numeric comparisons across all numeric types
- String equality comparisons
- Boolean equality comparisons
- Mixed type equality where Python provides sensible results

### What Needs Custom Handlers

The system implements custom handlers for:

1. **String-to-DateTime comparisons**: Essential for time-based filtering
2. **Version comparisons**: Semantic version logic vs lexicographic ordering
3. **Type validation**: Explicit errors instead of Python TypeErrors
4. **HA state value handling**: Home Assistant-specific state comparisons

### Phase 1 Essential Handlers Priority

1. **Type Safety and Validation**: Prevents invalid cross-type comparisons
2. **Datetime Comparisons**: Essential for time-based filtering in HA
3. **Version Comparisons**: Essential for firmware/software version filtering
4. **Numeric Comparisons**: Minimal wrapper around Python numeric comparisons

### What to Defer

Lower priority comparisons that can wait:

- String lexicographic ordering (rare in HA)
- Boolean ordering (rarely useful in practice)
- Complex type conversions (risky automatic conversions)

## Phase 1 Implementation Strategy

### Simplified Approach

The Phase 1 implementation uses a single essential comparison handler that:

1. Analyzes operand types using the type analyzer
2. Handles essential cases only (datetime, version, same-type comparisons)
3. Uses Python semantics for same-type numeric/string/boolean comparisons
4. Raises explicit errors for all other combinations
5. Focuses on actionable sensor use cases

### Benefits of Phase 1 Approach

1. **Minimal Implementation**: Single handler vs complex handler system
2. **Leverage Python**: Use built-in semantics where they work well
3. **Focus on Value**: Implement only what's needed for actionable sensors
4. **Clear Errors**: Explicit failures for invalid operations
5. **Fast Development**: Can be implemented and tested quickly

## Phase 1 Essential Operations Summary

| Operation Type             | Phase 1 Support    | Rationale                       | Example Use Cases           |
| -------------------------- | ------------------ | ------------------------------- | --------------------------- |
| **Numeric ==, !=**         | ✅ Full Support    | Essential for thresholds        | `battery_level >= 80`       |
| **Numeric <, <=, >, >=**   | ✅ Full Support    | Essential for ranges            | `temperature > 25`          |
| **String ==, !=**          | ✅ Full Support    | Essential for state matching    | `state == "on"`             |
| **String <, <=, >, >=**    | ❌ Deferred        | Rare in HA; Python handles well | `device_name > "Living"`    |
| **Boolean ==, !=**         | ✅ Full Support    | Essential for flags             | `enabled == True`           |
| **Boolean <, <=, >, >=**   | ❌ Deferred        | Rarely useful in practice       | `True > False`              |
| **DateTime All Ops**       | ✅ Full Support    | Essential for time filtering    | `last_seen >= "2024-01-01"` |
| **Version All Ops**        | ✅ Full Support    | Essential for compatibility     | `firmware >= "2.1.0"`       |
| **Cross-Type Conversions** | ❌ Explicit Errors | Type safety critical            | `5 > "text"` → Error        |

### What Phase 1 Enables

All these patterns work with Phase 1:

- Numeric thresholds: `count("attribute:battery_level>=80")`
- State matching: `count("state:=='on'")`
- Time-based filtering: `count("attribute:last_seen>='2024-01-01'")`
- Version constraints: `count("attribute:firmware_version>='2.1.0'")`

### What Phase 1 Defers

These patterns require Phase 2+:

- String ordering: `count("attribute:name>='Living'")` (out of scope, not supported)
- Boolean ordering: `count("attribute:enabled>=True")` (out of scope, use == instead)

## Advanced Type Conversion Scenarios

### Type Detection Hierarchy

The system uses a specific order of precedence for type detection:

1. **bool**: Checked first since bool is subclass of int in Python
2. **numeric**: int, float
3. **datetime string**: ISO format detection
4. **version string**: Semantic version detection
5. **generic string**: Default for non-specialized strings
6. **datetime object**: Direct datetime objects
7. **unknown**: Raises error

### Examples of Type Detection

- `True` → BOOLEAN
- `42` → NUMERIC
- `"2024-01-01"` → DATETIME (detected from string)
- `"2.1.0"` → VERSION (detected from string)
- `"hello"` → STRING

## Comparison Handler Testing Strategy

### Algorithm Validation Matrix

The testing strategy validates every combination of types and operators to ensure deterministic behavior:

### Unit Tests for Each Handler

Each handler requires comprehensive unit tests covering:

- `can_handle` method validation
- `compare` method functionality
- Edge cases and error conditions
- Type validation and conversion

### Integration Tests

Integration tests validate:

- Collection patterns with string comparisons
- Mixed type comparison error handling
- Real HA entity integration
- Performance impact on sensor evaluation

## Implementation Task List

The following task list implements the comparison handler design using the compiler-like phased approach outlined in the
state and entity design guide. This modular implementation ensures seamless integration with the existing `evaluator_phases`
architecture.

### Phase 1: Essential Comparison Operations (MVP)

**Objective**: Implement only the essential comparison operations needed for actionable sensor evaluations, leveraging Python
semantics where appropriate

#### Task 1.1: Create essential comparison infrastructure

Create minimal infrastructure for Phase 1 essential comparisons:

- Essential comparison handling phase
- Single handler for MVP
- Shared type analyzer component
- Comparison-specific exceptions

#### Task 1.2: Implement essential comparison handler (MVP)

- Create single essential comparison handler for all Phase 1 operations
- Implement datetime string parsing and comparison
- Implement semantic version comparison logic
- Add type validation with clear error messages
- Leverage Python semantics for same-type numeric/string/boolean equality
- Focus on actionable sensor use cases only

### Phase 2: Handler-Based Architecture with Registration System

**Objective**: Implement extensible handler registration following the design guide's layered architecture principles

#### Task 2.1: Create type analysis and handler selection system

- Implement type analyzer with conflict resolution for ambiguous strings
- Create base operation selector for extensibility to future operation systems
- Implement comparison handler selector with comprehensive type compatibility matrix
- Add comparison operator validation per type category
- Implement deterministic type conversion rules and strict hierarchy
- Add comprehensive error handling with detailed error messages
- Design operation context framework for future formula operations

#### Task 2.2: Implement base handler interface

- Define base comparison handler abstract class
- Establish common handler methods and type validation
- Create deterministic error handling patterns for handlers
- Implement handler metadata and priority attributes
- Define exception hierarchy for comparison failures

### Phase 3: Integration with ConditionParser

**Objective**: Integrate essential comparison handler with existing ConditionParser

#### Task 3.1: Replace existing comparison logic

- Replace numeric comparison handler with essential comparison handler
- Remove complex handler selection logic (use single handler)
- Simplify dispatch comparison method
- Maintain all existing functionality

#### Task 3.2: Update ConditionParser integration

- Modify ConditionParser to use the new comparison handling phase
- Replace warning-based fallbacks with explicit exceptions
- Ensure backward compatibility for existing collection patterns
- Add comprehensive error handling

### Phase 4: Implement StringComparisonHandler

**Objective**: Add lexicographic string comparison support

#### Task 4.1: Create string comparison handler

- Implement lexicographic ordering for string comparisons
- Support operators: `<`, `>`, `<=`, `>=`
- Handle Unicode string comparisons properly
- Add string normalization options (case sensitivity, whitespace)

#### Task 4.2: Integrate with collection patterns

- Enable string state comparisons in collection patterns
- Support attribute string comparisons
- Add validation for string comparison use cases
- Test with HA entity state values

### Phase 5: Implement BooleanComparisonHandler

**Objective**: Add logical boolean comparison support

#### Task 5.1: Create boolean comparison handler

- Implement logical ordering (False < True)
- Support operators: `<`, `>`, `<=`, `>=`
- Handle boolean conversion and validation
- Integrate with HA boolean state values

#### Task 5.2: Test boolean logic integration

- Validate boolean comparisons in formulas
- Test with HA on/off states
- Ensure proper type coercion
- Test edge cases and error conditions

### Phase 6: Implement DateTimeComparisonHandler

**Objective**: Add temporal comparison support for date/time values

#### Task 6.1: Create datetime comparison handler

- Support datetime object comparisons
- Handle ISO string datetime parsing
- Support timezone-aware comparisons
- Implement datetime validation and conversion

#### Task 6.2: Integrate with HA timestamps

- Support HA entity timestamp attributes
- Handle `last_seen`, `last_updated` attributes
- Add relative time comparisons (yesterday, today)
- Test with collection pattern time filtering

### Phase 7: Implement VersionComparisonHandler

**Objective**: Add semantic version comparison support

#### Task 7.1: Create version comparison handler

- Implement semantic version parsing (x.y.z)
- Support version comparison operators
- Handle version normalization and validation
- Support extended version formats

#### Task 7.2: Integrate with device versioning

- Support firmware version comparisons
- Handle software version attributes
- Test with HA device version information
- Validate version string formats

### Phase 8: Integration with ConditionParser Dispatch System

**Objective**: Seamlessly integrate all handlers with the existing condition parsing system

#### Task 8.1: Update dispatch mechanism

- Modify dispatch comparison to use handler factory
- Implement deterministic handler selection algorithm
- Replace fallback behavior with explicit error handling
- Add comprehensive logging for successful operations and clear error messages for failures

#### Task 8.2: Type analysis and handler selection

- Implement type categorization for all operand types
- Create type compatibility matrix for conversion rules
- Handle mixed-type scenarios with explicit conversion paths
- Ensure deterministic failure for unsupported type combinations

### Phase 9: Comprehensive Test Suite

**Objective**: Create thorough test coverage following the project's testing standards with algorithm validation matrix

#### Task 9.1: Algorithm validation matrix

- Implement type detection test matrix for all type categories
- Test conflict resolution for ambiguous strings (datetime vs version)
- Test edge cases and error conditions (None, unknown types)
- Test pattern matching performance and efficiency

#### Task 9.2: Handler selection validation

- Test all valid same-type combinations (5 types × 6 operators = 30 tests)
- Test all valid mixed-type combinations (4 valid conversions × 6 operators = 24 tests)
- Test all forbidden combinations (16 forbidden pairs × 6 operators = 96 tests)
- Test invalid operators for each type (5 types × 8 invalid operators = 40 tests)

#### Task 9.3: Handler interface and integration testing

- Test handler registration system and custom handler addition
- Test `can_handle` method consistency with type analysis
- Test error message quality and debugging information
- Test integration with ConditionParser and collection patterns

#### Task 9.4: Performance and edge case validation

- Test type detection performance (10,000 values in <1 second)
- Test pattern conflict edge cases and resolution
- Test error propagation and context preservation
- Test memory usage and handler instance management

### Phase 10: Documentation and Validation

**Objective**: Complete documentation and validate with integration tests

#### Task 10.1: Update design documentation

- Update comparison handler design documentation
- Document new handler architecture
- Add usage examples and patterns
- Document extension points

#### Task 10.2: Integration validation

- Test with real HA entities
- Validate collection pattern improvements
- Test performance impact
- Validate backward compatibility

#### Task 10.3: Code quality validation

- Run full test suite and ensure passes
- Validate type checking with mypy
- Run linting and formatting
- Ensure complexity standards compliance

## Architecture Alignment

This implementation follows the established compiler-like phased approach from the state and entity design guide:

### Layered Architecture Integration

- **Phase Integration**: Comparison handling becomes a dedicated phase within `evaluator_phases`
- **Single Responsibility**: Each handler has a specific comparison type responsibility
- **Extensibility**: Handler registration system allows for future extensions
- **Type Safety**: Strict type checking and validation throughout

### Compiler-Like Evaluation Flow

- **Variable Resolution Phase**: Handlers work with resolved values from Phase 1
- **Condition Parser**: Seamless integration with existing condition parsing logic
- **Collection Resolver**: Enhanced comparison capabilities for collection patterns
- **Error Handling**: Consistent with existing exception handling patterns

### Integration Points

1. **Variable Resolution Phase**: Handlers work with resolved values
2. **Pre-Evaluation Phase**: Type validation and early error detection
3. **Context Building**: Handler capability detection and selection
4. **Result Validation**: Type checking and error propagation

## Example Usage After Implementation

```yaml
sensors:
  # String comparisons
  device_states:
    formula: count("state:>='active'") # Lexicographic string comparison

  # Boolean comparisons
  enabled_devices:
    formula: count("attribute:enabled>=True") # Boolean logical comparison

  # DateTime comparisons
  recent_devices:
    formula: count("attribute:last_seen>='2024-01-01T00:00:00Z'") # Temporal comparison

  # Version comparisons
  compatible_firmware:
    formula: count("attribute:firmware_version>='2.1.0'") # Semantic version comparison
```

## Modularity and Extensibility

### Adding New Type Categories

The system is designed for easy extension with new type categories:

1. **Add new type category** to the type enumeration
2. **Extend type analyzer** with detection logic for the new type
3. **Update compatibility matrix** with conversion rules
4. **Add operator support** for the new type
5. **Implement handler** for the new type
6. **Register handler** with the system

### Modifying Type Precedence

Type detection precedence can be adjusted by reordering the detection logic in the type analyzer.

### Handler Composition

Handlers can delegate to other handlers for complex scenarios, enabling sophisticated comparison logic.

## Deterministic Failure Strategy

The comparison handler system implements a **fail-fast, fail-explicit** approach to ensure actionable sensor evaluations are
deterministic and reliable:

### Core Principles

1. **No Fallback Logic**: When a comparison cannot be performed, the system raises an explicit exception rather than
   returning a default value
2. **Type Validation**: All type combinations must be explicitly supported by handlers - no implicit conversions
3. **Operator Validation**: Each handler explicitly declares which operators it supports for which types
4. **Error Propagation**: Comparison failures propagate up the evaluation chain to enable proper error handling

### Exception Hierarchy

The system defines a clear exception hierarchy:

- **ComparisonHandlerError**: Base exception for comparison handler failures
- **UnsupportedComparisonError**: Raised when no handler supports the requested comparison
- **AmbiguousComparisonError**: Raised when multiple handlers could handle the comparison but with different semantics
- **InvalidOperatorError**: Raised when an operator is not valid for the given types

### Error Scenarios

- **Unsupported Type Combinations**: `5 > "apple"` → `UnsupportedComparisonError`
- **Invalid Operators**: `"text" * "other"` → `InvalidOperatorError`
- **Ambiguous Semantics**: Multiple handlers claim capability but would produce different results
- **Malformed Values**: Invalid datetime strings, malformed version numbers

### Benefits of Deterministic Failure

- **Reliability**: Sensor evaluations either succeed with correct results or fail explicitly
- **Debugging**: Clear error messages indicate exactly what comparison failed and why
- **Actionability**: Downstream systems can trust that sensor values are accurate or know definitively that they failed
- **Configuration Validation**: Invalid configurations are detected early rather than producing misleading results

## Benefits

- **Maintainability**: Clear separation of concerns with dedicated handler phases
- **Performance**: Efficient handler selection with priority-based routing
- **Future-Proof**: Architecture supports complex comparison logic extensions
- **Type Safety**: Comprehensive type validation and error handling
- **Deterministic**: No fallback logic ensures reliable, actionable results
- **Integration**: Seamless integration with existing evaluator architecture

## Scope Clarification: Comparison vs Formula Operations

### Current Design Scope

This comparison handler design is specifically focused on **comparison operations** used in collection patterns and
conditional expressions:

```yaml
# Comparison operations (this design)
sensors:
  filtered_devices:
    formula: count("state:>='active'")              # String comparison in collection
    formula: count("attribute:battery_level>=80")   # Numeric comparison in collection
    formula: count("state:=='on'")                  # Boolean comparison in collection
```

### Outside Current Scope: Formula Operations

**String concatenation** and **arithmetic operations** in main formulas are **outside the scope** of this comparison handler
design:

```yaml
# Formula operations (different system needed)
sensors:
  device_label:
    formula: device_name + " - " + location         # String concatenation

  formatted_status:
    formula: "Device: " + state + " (" + zone + ")" # Mixed string operations

  power_calculation:
    formula: voltage * current * efficiency          # Arithmetic operations
```

### Recommended Architecture: Coordinated Systems

For a complete solution, implement **two coordinated systems**:

#### 1. Comparison Handler System (This Design)

- **Purpose**: Type-aware comparisons for collection patterns
- **Operators**: `==`, `!=`, `<`, `<=`, `>`, `>=`
- **Usage**: Collection filtering, conditional expressions
- **Location**: `ConditionParser`, collection resolver

#### 2. Formula Operation System (Separate Design)

- **Purpose**: Arithmetic and string operations in main formulas
- **Operators**: `+`, `-`, `*`, `/`, `%`, string concatenation
- **Usage**: Main sensor formulas, attribute calculations
- **Location**: Main formula evaluator, expression handler

#### 3. Shared Components

Both systems should share common infrastructure:

- **Shared type analysis**: Consistent type detection across systems
- **Shared base classes**: Common operation selection patterns
- **Shared error handling**: Consistent exception hierarchy

### String Concatenation Design Considerations

If implementing string operations, consider these design patterns:

- **String operation handlers**: Specialized handlers for string operations
- **Mixed-type concatenation rules**: Explicit rules for type conversion
- **Operator disambiguation**: Clear distinction between concatenation and addition

### Benefits of Separation

1. **Clear Responsibilities**: Comparison vs operations have different semantics
2. **Operator Disambiguation**: `+` means concatenation for strings, addition for numbers
3. **Error Handling**: Different error types for comparison vs operation failures
4. **Testing**: Separate test suites for different operation categories
5. **Extensibility**: Can extend comparison and operations independently

### Integration in Task List

The **adjusted task list** now includes future-proofing for formula operations:

**Current Implementation (Comparison System)**

- All current phases remain valid with renamed components
- Shared infrastructure prepared for reuse
- Clear separation between comparison and formula operation contexts

**Future Phase: Formula Operation System**

- Extend base operation selector to create formula operation selector
- Reuse type analyzer for consistent type detection
- Implement arithmetic and string operation handlers
- Create operation-specific compatibility matrices
- Integrate with main formula evaluator through shared interfaces

## Plugin Architecture and Extensibility

### Overview

The comparison handler system supports multiple levels of extensibility through a plugin architecture that leverages Python's
protocol-based typing and duck typing. This allows users to:

1. **Register custom handlers** for new types or specialized comparison logic
2. **Inject comparison packages** through properly defined interfaces
3. **Leverage Python's built-in comparisons** as fallback for compatible types
4. **Extend operand types** through metadata-driven type identification

### Plugin Interface Protocols

The system defines several protocols for extensibility:

- **ComparisonHandlerProtocol**: Base protocol for comparison handlers
- **ExtendedTypeHandlerProtocol**: Protocol for metadata-aware handlers
- **ComparisonPackageProtocol**: Protocol for complete comparison packages

### Plugin Registry System

The registry system provides:

- **Handler registration**: Register handlers with priority levels
- **Package registration**: Register complete comparison packages
- **Handler discovery**: Find appropriate handlers using priority order
- **Fallback logic**: Graceful degradation to Python's native comparisons

### Python Fallback Handler

A fallback handler that uses Python's built-in comparison operators when:

- Types are compatible for Python comparison
- No specialized handler is available
- Safe fallback is enabled

### Metadata-Driven Type Extension

The system supports metadata-driven type identification through:

- **Type metadata providers**: Objects that provide comparison metadata
- **Metadata-aware handlers**: Handlers that work with metadata context
- **Preprocessing capabilities**: Value transformation before comparison

### Plugin Loading and Configuration

The system supports dynamic plugin loading through:

- **Module-based plugins**: Load handlers from Python modules
- **Package-based plugins**: Load complete comparison packages
- **Class-based plugins**: Load specific handler classes
- **Configuration-driven loading**: Load plugins from YAML configuration

### Configuration Examples

The system supports various configuration approaches:

- **YAML plugin configuration**: Declarative plugin specification
- **Programmatic registration**: Direct handler registration
- **Priority control**: Handler prioritization for optimal selection
- **Error isolation**: Plugin failures don't break the core system

### Benefits of Plugin Architecture

1. **Extensibility**: Users can add custom comparison logic without modifying core code
2. **Type Safety**: Protocol-based interfaces ensure proper implementation
3. **Python Integration**: Leverages Python's built-in capabilities where appropriate
4. **Metadata Support**: Enables sophisticated type identification and processing
5. **Fallback Strategy**: Graceful degradation to Python's native comparisons
6. **Package Support**: Complete comparison packages can be loaded as units
7. **Priority Control**: Handlers can be prioritized for optimal selection
8. **Error Isolation**: Plugin failures don't break the core system

## Formula-Based Type Reduction Architecture

### Core Principle: Numeric-First Evaluation Strategy

**This is not "backward compatibility" - this is the CORRECT design for formula evaluation systems.**

Formula evaluation systems must prioritize numeric conversion to enable mathematical operations. The type reduction hierarchy
ensures that:

- `"5" + 3` becomes `5.0 + 3.0 = 8.0` (not string concatenation)
- `True > 0` becomes `1.0 > 0.0 = True` (logical-mathematical operation)
- `"85" >= 80` becomes `85.0 >= 80.0 = True` (threshold comparison)

### Enhanced Type Reduction Hierarchy with Metadata

The TypeReducer operates in two phases: **Metadata-Driven Type Identification** followed by **Built-in Type Reduction**.

**Key Principle: User type reducers always return built-in type reductions.**

#### Reduction Flow Strategy

The reduction process follows this flow:

1. **Check for metadata**: Look for type metadata on operands
2. **Identify type from metadata**: Use metadata to determine user-defined types
3. **Call user type reducer**: If user type identified, call appropriate reducer
4. **Return built-in types**: User reducers always return built-in type reductions
5. **Continue with built-in logic**: Use standard comparison logic for reduced types

### Phase 1: Metadata-Driven Type Identification

Before applying built-in type detection, the system checks for metadata that defines custom user types.

#### Why This Design Works

1. **Transparent Integration**: Existing comparison handlers work without modification
2. **Formula Compatibility**: Formula evaluators receive standard numeric/string/datetime values
3. **Performance**: No special handling needed in downstream logic
4. **Extensibility**: New user types integrate automatically
5. **Caching**: Reduced values can be cached using standard types

#### Example Flow: Energy Value Comparison

Consider comparing two energy values with different units:

1. **Metadata detection** identifies both as 'energy' type
2. **User type reducer** converts both values to a common unit (e.g., kWh)
3. **Returns numeric values** that existing comparison logic can handle
4. **Standard comparison** proceeds with numeric comparison
5. **Result**: No changes needed to existing comparison or formula handlers

## Conclusion

The comparison handler design provides a robust, extensible foundation for type-aware comparisons in the synthetic sensors
integration. By following the phased implementation approach and leveraging Python's built-in capabilities where appropriate,
the system delivers essential functionality while maintaining clear extension paths for future enhancements.

The design emphasizes:

- **Type Safety**: Comprehensive validation and explicit error handling
- **Performance**: Efficient handler selection and minimal overhead
- **Extensibility**: Plugin architecture for custom comparison logic
- **Integration**: Seamless integration with existing evaluator architecture
- **Deterministic Behavior**: Reliable, actionable results with clear failure modes

This architecture ensures that the synthetic sensors integration can handle complex comparison scenarios while maintaining
the reliability and performance characteristics required for production use in Home Assistant environments.
