# Type Handling Proposal

## Overall Design and Code Guidance

It's essential that we main modularity and code hygiene so we adhere to the
[![design guide](docs/Dev/state_and_entity_design_guide)] in terms of compiler like phasing and the pluggable nature of
comparisons [![comparison handlers](/Users/bflood/projects/HA/ha-synthetic-sensors/docs/User_Defined_Comparison_Handlers.md)]

In crafting code we use strict typing, keep our methods short and our modules within the pylint guidance, avoid mypy errors,
create unit tests that avoid anti-test patterns while developing integration tests that adhere to the
[![integration test guidance](tests/docs/integration_test_guide.md)]. Where YAML is used in tests we use external YAML
fixtures, never embedding YAML directly in tests.

## Overview

The HA Synthetic Sensors package currently supports basic string comparisons (`==`, `!=`, `in`, `not in`) but lacks
comprehensive string manipulation capabilities. This proposal outlines an enhanced string handling system that provides
robust string operations while maintaining compatibility with the existing formula evaluation architecture.

## Current Limitations

### Existing String Support

The package currently supports:

- Basic string equality: `"state == 'on'"`
- String containment: `"attribute:name in 'Living'"`
- Simple pattern matching: `"device_class:power"`

### Missing Capabilities

The current system lacks:

- **String concatenation and assignment** for dynamic attribute construction
- Case-insensitive comparisons
- String normalization (trimming, whitespace handling)
- Substring operations
- String transformation functions
- Pattern-based string manipulation
- Multi-string operations

## Proposed String Handling Architecture

### Core Design Principles

1. **Pre-Evaluation Processing**: String operations occur before formula evaluation
2. **Boolean Result**: All string operations must produce boolean results for comparison contexts
3. **Formula Compatibility**: String operations work within the existing comparison framework
4. **Type Safety**: Explicit type validation and error handling
5. **Performance**: Efficient string processing with caching where appropriate

### Arithmetic Handler Architecture (Basis for `+` Formula Evaluation)

The arithmetic operations will use a **simplified routing system with explicit user functions** that eliminates complex type
conversion logic while giving users complete control over evaluation behavior. This approach integrates seamlessly with the
existing formula evaluation pipeline.

#### Three-Category Formula Routing

```python
# Enhanced pipeline integration:
VariableResolutionPhase → FormulaPreprocessor → FormulaRouter → [Evaluator Selection]
                                                     ↓
                      ┌─ StringEvaluator (no cache) ←── User functions & string literals
                      ├─ DateEvaluator (no cache) ←──── User date functions
                      ├─ NumericEvaluator (cache) ←──── User numeric functions & default
                      └─ BooleanEvaluator (no cache) ←── User boolean functions (future)
```

#### Category 1: Explicit User Functions (Highest Priority)

Users explicitly control evaluation behavior with wrapper functions:

```yaml
# Explicit type control - no ambiguity:
attributes:
  numeric_result:
    formula: "numeric(state) + numeric(other_sensor)" # Force numeric conversion

  string_result:
    formula: "str(state) + str(other_sensor)" # Force string concatenation

  date_arithmetic:
    formula: "date(start_date) + numeric(days_offset)" # Date + number arithmetic

  mixed_operations:
    formula: "str(numeric(state) * 1.1)" # Numeric calc → string result
```

#### Category 2: String Literals (Automatic String Routing)

Formulas containing string literals are automatically routed to string evaluation:

```yaml
# Automatic string detection:
attributes:
  status_message:
    formula: "'Device: ' + state + ' status'" # Contains string literals

  combined_info:
    formula: "state + ' - Power: ' + power + 'W'" # Mixed string + variables
```

#### Category 3: Default Numeric (Existing Behavior)

All other formulas use existing numeric evaluation with AST caching:

```yaml
# Default numeric evaluation (unchanged):
sensors:
  power_calculation:
    formula: "state * efficiency_factor" # Numeric operations

  device_count:
    formula: "count('device_class:power')" # Collection functions
```

#### Iterative Arithmetic Processing

Within each evaluator, arithmetic operations are processed iteratively, left-to-right:

```python
# Example in StringEvaluator: "'Result: ' + state + ' - ' + power + 'W'"
# Iteration 1: "'Result: ' + state" → "Result: on"
# Iteration 2: "Result: on" + " - " → "Result: on - "
# Iteration 3: "Result: on - " + power → "Result: on - 1000"
# Iteration 4: "Result: on - 1000" + "W" → "Result: on - 1000W"
```

#### Defensive Configuration

```python
@dataclass
class ArithmeticTokenizerConfig:
    """Configuration for arithmetic tokenization processing."""
    max_iterations: int = 100  # Defensive limit against edge cases
    enable_iteration_logging: bool = False  # For debugging
```

#### Key Benefits

1. **User Control**: Explicit functions eliminate ambiguity about evaluation behavior
2. **Simple Implementation**: No complex type conversion priority or runtime re-routing
3. **Predictable Caching**: Clear caching decisions based on evaluator type
4. **Backward Compatible**: All existing formulas continue to work unchanged
5. **Extensible**: Easy to add new user functions (bool(), version(), etc.)
6. **Error Prevention**: Clear error messages for invalid type conversions

### String Operation Categories

#### 1. Case Manipulation Operations

**Case-Insensitive Comparisons**

```yaml
sensors:
  case_insensitive_devices:
    formula: count("lower(state)=='on'") # Matches 'on', 'ON', 'On', etc.
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:devices"

  normalized_states:
    formula: count("lower(attribute:status)=='active'") # Matches 'Active', 'ACTIVE', etc.
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:check-circle"
```

**Case-Insensitive Comparisons**

```yaml
sensors:
  living_room_devices:
    formula: count("lower(attribute:name)=='living room'") # Matches 'Living Room', 'LIVING ROOM', 'living room'
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:home"

  active_state_devices:
    formula: count("lower(state)=='on'") # Matches 'on', 'ON', 'On'
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:lightbulb"
```

**Case Transformation Functions**

```yaml
sensors:
  title_case_devices:
    formula: count("title(attribute:name)=='Living Room'") # Matches 'living room', 'LIVING ROOM'
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:home"

  capitalized_states:
    formula: count("capitalize(state)=='On'") # Matches 'on', 'ON', 'On'
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:lightbulb"
```

#### 2. String Normalization Operations

**Whitespace Handling**

```yaml
sensors:
  trimmed_devices:
    formula: count("trim(attribute:description)=='active device'") # Matches ' active device ', 'active device  '
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:devices"

  normalized_names:
    formula: count("normalize(attribute:name)=='test device'") # Handles multiple spaces, tabs, newlines
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:tag"
```

**String Cleaning Operations**

```yaml
sensors:
  clean_states:
    formula: count("clean(state)=='on'") # Removes special characters, normalizes
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:check"

  sanitized_names:
    formula: count("sanitize(attribute:name)=='device_name'") # Converts to safe identifier format
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:identifier"
```

#### 3. Substring and Pattern Operations

**Substring Matching**

```yaml
sensors:
  contains_pattern:
    formula: count("contains(attribute:name, 'sensor')") # Matches any name containing 'sensor'
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:magnify"

  starts_with_pattern:
    formula: count("startswith(attribute:name, 'living')") # Matches names starting with 'living'
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:home"

  ends_with_pattern:
    formula: count("endswith(attribute:name, 'sensor')") # Matches names ending with 'sensor'
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:devices"
```

**Pattern Extraction**

```yaml
sensors:
  extracted_values:
    formula: count("extract(attribute:serial, 'SN-\\d{6}')") # Matches serial numbers with pattern
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:identifier"

  pattern_matches:
    formula: count("matches(attribute:version, 'v\\d+\\.\\d+\\.\\d+')") # Matches version strings
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:tag"
```

#### 4. Multi-String Operations

**String Combination**

```yaml
sensors:
  combined_names:
    formula: count("attribute:name + ' ' + 'device_type'") # Combines multiple attributes with spaces
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:devices"

  formatted_states:
    formula: count("format(state, attribute:device_name + ' is ' + attribute:status)") # String formatting with variables
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:format-text"

  complex_concatenation:
    formula: count("attribute:name + ' - ' + attribute:status + ' (' + attribute:room + ')'") # Multiple concatenation
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:devices"
```

**String Splitting and Joining**

```yaml
sensors:
  split_values:
    formula: count("split(attribute:tags, ',')") # Splits comma-separated tags
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:tag-multiple"

  joined_attributes:
    formula: count("join(attribute:components, ',')") # Joins array values
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:connection"
```

#### 5. String Concatenation and Assignment

**Dynamic Attribute Construction**

```yaml
sensors:
  device_status:
    name: "Device Status"
    formula: "current_power"
    variables:
      current_power: "sensor.power_meter"
    attributes:
      status_message:
        formula: "'Device is ' + state + ' - ' + current_power + 'W'"
        metadata:
          icon: "mdi:message-text"

      temperature_display:
        formula: "'Temperature: ' + temperature + '°C'"
        variables:
          temperature: "sensor.temperature"
        metadata:
          icon: "mdi:thermometer"

      combined_info:
        formula: "'Device: ' + device_name + ' | Status: ' + status + ' | Power: ' + power + 'W'"
        variables:
          device_name: "sensor.device_name"
          status: "sensor.device_status"
          power: "sensor.power_reading"
        metadata:
          icon: "mdi:information"
```

**Literal and Variable Concatenation**

```yaml
sensors:
  smart_device:
    name: "Smart Device"
    formula: "device_power"
    variables:
      device_power: "sensor.power_meter"
    attributes:
      custom_label:
        formula: "'MyToasterIsThisHot - ' + state + ' degrees'"
        metadata:
          icon: "mdi:label"

      formatted_power:
        formula: "'Power Level: ' + power_level + ' (' + status + ')'"
        variables:
          power_level: "sensor.power_level"
          status: "sensor.device_status"
        metadata:
          icon: "mdi:flash"

      device_summary:
        formula: "'Device ' + device_id + ' is ' + state + ' at ' + power + 'W'"
        variables:
          device_id: "sensor.device_id"
          power: "sensor.power_reading"
        metadata:
          icon: "mdi:devices"
```

**Advanced String Function Integration**

```yaml
sensors:
  advanced_device:
    name: "Advanced Device"
    formula: "device_power"
    variables:
      device_power: "sensor.power_meter"
    attributes:
      processed_description:
        formula: "str(trim(attribute:description == 'active device'))"
        metadata:
          icon: "mdi:format-text"

      normalized_status:
        formula: "'Status: ' + str(lower(attribute:status))"
        metadata:
          icon: "mdi:check-circle"

      formatted_info:
        formula: "str(trim(attribute:name)) + ' - ' + str(upper(attribute:status))"
        metadata:
          icon: "mdi:information"

      complex_display:
        formula: "'Device: ' + str(title(trim(attribute:name))) + ' | ' + str(capitalize(attribute:status))"
        metadata:
          icon: "mdi:devices"
```

#### 6. Advanced String Operations

**String Length Operations**

```yaml
sensors:
  long_names:
    formula: count("length(attribute:name)>=10") # Names with 10+ characters
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:format-size"

  short_states:
    formula: count("length(state)<=3") # States with 3 or fewer characters
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:format-size"
```

**String Replacement Operations**

```yaml
sensors:
  replaced_names:
    formula: count("replace(attribute:name, 'old', 'new')=='new_device'") # String replacement
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:rename-box"

  cleaned_states:
    formula: count("replace_all(state, '_', ' ')=='on line'") # Replace all underscores
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:format-clear"
```

## String Operation Syntax

### Operation Chaining

String operations can be chained for complex transformations:

```yaml
sensors:
  complex_filter:
    formula: count("attribute:name:lower:trim:replace=='old','new'=='new device'")
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:filter"
```

### String Function Integration

String functions can be integrated with concatenation for advanced processing:

```yaml
sensors:
  advanced_processing:
    attributes:
      processed_result:
        formula: "str(trim(attribute:description == 'active device'))"
        metadata:
          icon: "mdi:format-text"

      formatted_display:
        formula: "'Device: ' + str(title(trim(attribute:name))) + ' | ' + str(upper(attribute:status))"
        metadata:
          icon: "mdi:devices"

      simple_concatenation:
        formula: "attribute:name + ' - ' + attribute:status"
        metadata:
          icon: "mdi:devices"

      multiple_concatenation:
        formula: "'Device: ' + attribute:name + ' is ' + attribute:status + ' in ' + attribute:room"
        metadata:
          icon: "mdi:devices"

      complex_processing:
        formula:
          "'Device: ' + str(title(trim(attribute:name))) + ' is ' + str(lower(attribute:status)) + ' in ' +
          str(capitalize(attribute:room))"
        metadata:
          icon: "mdi:devices"
```

### Operation Parameters

Operations can accept parameters for flexible behavior:

```yaml
sensors:
  parameterized_operations:
    formula: count("attribute:name:replace:'old':'new'=='new_device'")
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:devices"
```

### Boolean Result Conversion

All string operations produce boolean results for comparison contexts:

```yaml
sensors:
  boolean_results:
    formula: count("attribute:name:contains=='sensor'") # Returns true/false for each device
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:check-circle"
```

### String Function Result Conversion

String functions can produce string results for concatenation contexts:

```yaml
sensors:
  string_results:
    attributes:
      processed_text:
        formula: "str(trim(attribute:description == 'active device'))" # Returns processed string
        metadata:
          icon: "mdi:format-text"
```

### Type Conversion Priority and Error Handling

**Numeric Priority**: When the `+` operator is encountered, the system first attempts numeric conversion:

```yaml
# Numeric conversion (preferred)
formula: "5 + 3"           # Result: 8 (numeric)
formula: "5 + '3'"         # Result: 8 (numeric conversion)
formula: "'5' + 3"         # Result: 8 (numeric conversion)

# String conversion (fallback)
formula: "'hello' + 'world'"  # Result: "helloworld" (string)
formula: "'hello' + 5"        # Result: "hello5" (string conversion)
formula: "5 + 'hello'"        # Result: "5hello" (string conversion)
```

**Note**: This enhanced type conversion capability is **not currently supported** by simpleeval. The current system treats
string + number as an error. This proposal includes extending the formula evaluator to support automatic type conversion.

**Collection Pattern Requirements**: String results in collection patterns cause errors:

```yaml
# ❌ ERROR: count() expects a collection pattern, not a string result
formula: count("'hello' + 'world'")  # Error: "helloworld" is not a collection pattern

# ✅ CORRECT: count() with proper collection pattern
formula: count("attribute:name + ' device'")  # Works: filters entities by concatenated name

# ✅ CORRECT: String result in attribute assignment
attributes:
  display_name:
    formula: "'Device: ' + attribute:name + ' is ' + attribute:status"  # Works: creates string attribute
```

## Integration with Existing Systems

### Pipeline Integration

The arithmetic tokenization system integrates seamlessly with the existing evaluation pipeline:

```python
# Current Pipeline:
VariableResolutionPhase → FormulaPreprocessor → simpleeval → HandlerFactory

# Enhanced Pipeline:
VariableResolutionPhase → FormulaPreprocessor → ArithmeticTokenizer → simpleeval → HandlerFactory
```

**Key Integration Points:**

1. **Variable Resolution First**: All variables (state, attributes, computed variables) are resolved to concrete values
   before arithmetic tokenization
2. **Pre-simpleeval Processing**: Arithmetic operations are resolved before formula reaches simpleeval
3. **Selective Caching**: Only numeric results are cached in `FormulaCompilationCache` - string operations bypass caching
4. **Error Flow**: Tokenization errors flow through existing `EvaluatorErrorHandler` and circuit breaker systems

### Type Conversion Strategy

The system leverages existing type conversion infrastructure:

1. **Existing Type Analyzer**: Uses `TypeAnalyzer.try_reduce_to_numeric()` for numeric conversion attempts
2. **Priority-Based Fallback**: Follows same priority pattern as comparison handlers (numeric → string → boolean)
3. **Dependency Validation**: Existing `DependencyParser` handles circular dependencies, eliminating need for complex
   iteration limits
4. **Context-Aware Results**: String results route to `StringHandler`, numeric results route to `NumericHandler`

### Comparison Handler Integration

String operations integrate with the existing comparison handler system:

1. **Pre-processing Phase**: String operations execute before comparison evaluation
2. **Type Preservation**: Operations maintain string type for comparison contexts
3. **Boolean Conversion**: Results convert to boolean for final evaluation
4. **Error Handling**: Invalid operations raise explicit exceptions through existing error infrastructure

### Formula Evaluation Compatibility

String operations work within the existing formula evaluation constraints:

1. **Dual Result Types**: Formulas can produce either numeric or string results
2. **Context Validation**: Collection patterns require boolean/numeric results, attributes allow string results
3. **Type Conversion Priority**: Numeric conversion preferred, string conversion as fallback
4. **Collection Pattern Validation**: String results in collection patterns cause errors with clear messaging
5. **Type Safety**: Operations validate input types and handle errors gracefully
6. **Performance**: Efficient processing with minimal overhead, leveraging existing caching for numeric operations

## Error Handling and Validation

### Input Validation

- **Type Checking**: Validate input types before processing
- **Parameter Validation**: Ensure operation parameters are valid
- **Pattern Validation**: Validate regex patterns and format strings
- **Length Limits**: Prevent excessive string processing

### Error Scenarios

- **Invalid Operations**: Unsupported string operations
- **Malformed Patterns**: Invalid regex or format patterns
- **Type Mismatches**: Non-string inputs to string operations
- **Parameter Errors**: Invalid operation parameters
- **Collection Pattern Errors**: String results used in collection patterns (e.g., `count("'hello' + 'world'")`)
- **Type Conversion Failures**: Failed numeric conversions that fall back to string operations

### Error Recovery

- **Graceful Degradation**: Fall back to simple string comparison
- **Error Propagation**: Clear error messages for debugging
- **Default Values**: Sensible defaults for failed operations
- **Logging**: Comprehensive logging for troubleshooting

## Performance Considerations

### Caching Strategy

- **Operation Caching**: Cache frequently used string operations
- **Result Caching**: Cache operation results for repeated evaluations
- **Pattern Compilation**: Pre-compile regex patterns for efficiency
- **Memory Management**: Efficient memory usage for large string sets

### Optimization Techniques

- **Lazy Evaluation**: Evaluate operations only when needed
- **Early Termination**: Stop processing when result is determined
- **Batch Processing**: Process multiple operations efficiently
- **Type Optimization**: Optimize for common string types

## Implementation Roadmap

### Phase 1: Core Formula Routing and Basic String Operations

#### **Milestone 1.1: Formula Router Implementation** ⭐ _Critical Foundation_

**Objective**: Implement three-category formula routing system

**Tasks**:

1. Create `FormulaRouter` class with category detection logic
2. Implement user function detection (`str()`, `numeric()`, `date()`)
3. Implement string literal detection (non-collection patterns)
4. Integrate router between `FormulaPreprocessor` and existing handlers
5. Add routing unit tests and integration tests

**Deliverables**:

- `src/ha_synthetic_sensors/formula_router.py`
- Updated `src/ha_synthetic_sensors/evaluator.py` pipeline
- Comprehensive test suite: `tests/unit/test_formula_router.py`

**Success Criteria**:

- All existing formulas continue to work unchanged
- User functions route to correct evaluators
- String literals automatically route to string evaluation
- Performance overhead < 5ms per formula

#### **Milestone 1.2: Enhanced String Evaluator** ✅ _COMPLETED - Core String Functionality_

**Objective**: Extend existing `StringHandler` with arithmetic operations

**Tasks**: ✅ **ALL COMPLETED**

1. ✅ Extend `StringHandler` to support arithmetic operations (`+` concatenation)
2. ✅ Implement iterative left-to-right string processing
3. ✅ Add support for `str()` function with nested evaluation
4. ✅ Add basic string functions: `trim()`, `lower()`, `upper()`, `title()`
5. ✅ Implement defensive iteration limits with configuration

**Deliverables**: ✅ **ALL DELIVERED**

- ✅ Enhanced `src/ha_synthetic_sensors/evaluator_handlers/string_handler.py`
- ✅ Comprehensive unit tests: `tests/unit/test_string_functions.py`
- ✅ Integration tests: `tests/integration/test_string_operations.py`

**Success Criteria**: ✅ **ALL MET**

- ✅ String concatenation works: `"'Device: ' + state + ' status'"`
- ✅ Nested functions work: `"str(numeric(state) * 1.1)"`, `"trim(lower('  HELLO  '))"`
- ✅ String functions work: `"trim(state)"`, `"lower(attribute:name)"`, `"upper(status)"`, `"title('hello world')"`
- ✅ No performance regression for existing string operations

#### **Milestone 1.3: Syntax Validation** ✅ _COMPLETED - Error Handling Foundation_

**Objective**: Create robust formula syntax validation with proper error handling

**Tasks**: ✅ **ALL COMPLETED**

1. ✅ Implement `FormulaSyntaxError` for specific syntax errors
2. ✅ Add comprehensive syntax validation to `FormulaRouter`
3. ✅ Validate malformed function calls, unclosed quotes, mismatched parentheses
4. ✅ Provide helpful error messages with position indicators
5. ✅ Integrate syntax validation with existing error handling pipeline

**Deliverables**: ✅ **ALL DELIVERED**

- ✅ Enhanced `src/ha_synthetic_sensors/formula_router.py` with syntax validation
- ✅ `FormulaSyntaxError` exception with position tracking
- ✅ Comprehensive unit tests: `tests/unit/test_formula_syntax_validation.py`
- ✅ Integration with existing error handling

**Success Criteria**: ✅ **ALL MET**

- ✅ Malformed function calls raise `FormulaSyntaxError` instead of silent failures
- ✅ Error messages include formula and position information
- ✅ Visual position indicators (`^`) point to error locations
- ✅ All existing error handling continues to work unchanged

#### **Milestone 1.4: Basic String Functions** ✅ _COMPLETED - Function Implementation_

**Objective**: Implement core string manipulation functions with full integration

**Tasks**: ✅ **ALL COMPLETED**

1. ✅ Implement `trim()`, `lower()`, `upper()`, `title()` functions
2. ✅ Update `FormulaRouter` to recognize new string functions
3. ✅ Add function evaluation logic to `StringHandler`
4. ✅ Support nested function calls and concatenation integration
5. ✅ Create comprehensive test coverage

**Deliverables**: ✅ **ALL DELIVERED**

- ✅ String function implementations in `StringHandler`
- ✅ Updated `FormulaRouter` with new function detection
- ✅ Comprehensive unit tests: `tests/unit/test_string_functions.py`
- ✅ Integration tests validating end-to-end functionality

**Success Criteria**: ✅ **ALL MET**

- ✅ Individual functions work: `trim('  hello  ')` → `"hello"`
- ✅ Nested functions work: `trim(lower('  HELLO  '))` → `"hello"`
- ✅ Concatenation integration: `'Device: ' + trim(device_name)`
- ✅ Context variable support: `upper(status)` with variable resolution
- ✅ Error handling for malformed syntax

---

## 🎉 **Phase 1 Complete - Core Formula Routing and Basic String Operations**

**Phase 1 Status**: ✅ **FULLY COMPLETED**

All foundational components for the type handling system have been successfully implemented:

- **✅ Formula Router**: Three-category routing system with user function detection
- **✅ String Concatenation**: Left-to-right iterative processing with `+` operator
- **✅ Basic String Functions**: `trim()`, `lower()`, `upper()`, `title()` with full nesting support
- **✅ Advanced String Functions**: `contains()`, `startswith()`, `endswith()`, `length()`, `replace()`
- **✅ Syntax Validation**: Robust error handling with `FormulaSyntaxError` and position indicators
- **✅ Integration**: Seamless integration with existing evaluation pipeline
- **✅ Testing**: Comprehensive unit and integration test coverage
- **✅ Code Quality**: All constants consolidated into shared locations following established patterns

## ✅ **String Main Values Successfully Enabled**

**Problem Resolved**: Modified the evaluator to allow string main formula results since the formula router now provides
proper type handling and routing.

**Solution Implemented**:

- Updated `evaluator.py` line 637: `if is_main_formula and not isinstance(result, int | float | str | bool)`
- This enables powerful string sensors where the main state is a string value
- Attribute formulas can now operate on string states using the `state` token

**Integration Test Results**: ✅ **ALL PASSING**

- `normalize('  hello   world  ')` → `"hello world"`
- `clean('device@name#123!')` → `"devicename123"`
- `sanitize('hello world')` → `"hello_world"`
- Complex nested: `sanitize(normalize(clean('  Smart@Device#1!!  ')))` → `"SmartDevice1"`
- String concatenation: `'Cleaned: ' + normalize(...)` → `"Cleaned: hello world"`

**Benefits Unlocked**:

1. **String sensors with string main values** - Full integration into HA ecosystem
2. **Attribute formulas on string state** - Can reference string sensor state in calculations
3. **Cross-sensor string references** - Other sensors can use string sensor states
4. **Mixed-type operations** - String and numeric operations work seamlessly

---

**Next Phase**: Ready to proceed to **Phase 3 - Optimization and Production Readiness**

---

### Phase 2: Advanced String Operations and Integration

#### **Milestone 2.1: Advanced String Function Library** ✅ COMPLETED

**Objective**: Comprehensive string manipulation functions

**Tasks**:

1. ✅ Implement substring operations: `contains()`, `startswith()`, `endswith()`
2. ✅ Add string replacement: `replace()` (basic implementation)
3. ⭐ Implement string normalization: `normalize()`, `clean()`, `sanitize()` - _NEXT PHASE_
4. ✅ Add string length and validation functions: `length()`
5. ⭐ Create function chaining support - _NEXT PHASE_

**Deliverables**:

- ✅ Complete basic string function library (`contains`, `startswith`, `endswith`, `length`, `replace`)
- ✅ Multi-parameter function support with proper parsing
- ✅ Integration with existing evaluation pipeline
- ✅ Comprehensive test coverage

#### **Milestone 2.2: Extended String Functions** ✅ _COMPLETED - Advanced String Operations_

**Objective**: Additional string manipulation and normalization functions

**Tasks**: ✅ **ALL COMPLETED**

1. ✅ Implement string normalization: `normalize()`, `clean()`, `sanitize()`
2. ✅ Add advanced replacement: `replace_all()` for multiple replacements
3. ✅ Implement string validation: `isalpha()`, `isdigit()`, `isnumeric()`, `isalnum()`
4. ✅ Add string splitting and joining: `split()`, `join()`
5. ✅ Implement string padding: `pad_left()`, `pad_right()`, `center()`

**Deliverables**: ✅ **ALL DELIVERED**

- ✅ Extended string function library (15 additional functions)
- ✅ Advanced text processing capabilities with parameter validation
- ✅ Integration test suite validating all 20 extended functions
- ✅ Proper error handling and syntax validation

#### **Milestone 2.2: Date Arithmetic System**

**Objective**: Date manipulation and arithmetic operations

**Tasks**:

1. Implement `DateEvaluator` with date parsing
2. Add date arithmetic: date + number, date - date
3. Implement date formatting and conversion functions
4. Create date validation and error handling
5. Add timezone support considerations

**Deliverables**:

- `src/ha_synthetic_sensors/evaluator_handlers/date_handler.py`
- Date function library
- Date arithmetic operations
- Integration tests with time-based scenarios

#### **Milestone 2.3: Collection Pattern Integration**

**Objective**: Ensure string operations work correctly with collection patterns

**Tasks**:

1. Validate collection vs. attribute context enforcement
2. Implement clear error messages for invalid usage
3. Test string operations within collection functions
4. Ensure boolean result conversion for comparisons
5. Validate performance with large entity collections

**Deliverables**:

- Context validation system
- Enhanced error messaging
- Collection pattern test suite
- Performance validation

### Phase 3: Optimization and Production Readiness

#### **Milestone 3.1: Performance Optimization**

**Objective**: Ensure production-ready performance

**Tasks**:

1. Implement selective caching strategy (numeric cache, string no-cache)
2. Add formula complexity analysis and warnings
3. Optimize string function implementations
4. Add performance monitoring and metrics
5. Create benchmarking and load testing

**Deliverables**:

- Performance monitoring integration
- Caching optimization
- Benchmarking test suite
- Performance documentation

#### **Milestone 3.2: Error Handling and Validation**

**Objective**: Production-ready error handling

**Tasks**:

1. Integrate with existing `EvaluatorErrorHandler` system
2. Add specific error types for string operations
3. Implement circuit breaker integration
4. Create comprehensive error documentation
5. Add error recovery and fallback mechanisms

**Deliverables**:

- Enhanced error handling integration
- String operation error types
- Error recovery mechanisms
- Troubleshooting documentation

#### **Milestone 3.3: Documentation and Testing**

**Objective**: Complete documentation and test coverage

**Tasks**:

1. Create user guide for string operations
2. Add migration guide for new features
3. Ensure 100% test coverage for new components
4. Create performance tuning guide
5. Add troubleshooting and FAQ section

**Deliverables**:

- Complete user documentation
- Migration and upgrade guides
- Test coverage reports
- Performance and troubleshooting guides

## Priority and Dependencies

### **Critical Path** (Must complete in order)

1. **Phase 1.1** → **Phase 1.2** → **Phase 1.3** (Foundation)
2. **Phase 2.1** (Core string functionality)
3. **Phase 3.1** → **Phase 3.2** → **Phase 3.3** (Production readiness)

### **Parallel Development** (Can develop simultaneously)

- **Phase 2.2** (Date system) - Independent of string operations
- **Phase 2.3** (Collection integration) - Can develop after Phase 1.2

### **Release Strategy**

- **v1.0**: Phase 1 complete (Core functionality)
- **v1.1**: Phase 2.1 complete (Full string operations)
- **v1.2**: Phase 2.2-2.3 complete (Date arithmetic and validation)
- **v2.0**: Phase 3 complete (Production optimization)

## Success Metrics

### **Functional Metrics**

- ✅ All existing formulas continue to work unchanged
- ✅ String concatenation operations work reliably
- ✅ User functions provide predictable type control
- ✅ Error messages are clear and actionable

### **Performance Metrics**

- ✅ Formula routing overhead < 5ms
- ✅ String operations performance comparable to numeric operations
- ✅ AST caching effectiveness maintained for numeric formulas
- ✅ Memory usage impact < 10% increase

### **Quality Metrics**

- ✅ Test coverage > 95% for all new components
- ✅ Integration tests cover real-world usage scenarios
- ✅ Error handling covers all failure modes
- ✅ Documentation covers all user-facing features

## Compatibility and Migration

### Backward Compatibility

- **Existing Patterns**: All current string comparisons continue to work
- **Gradual Migration**: New operations can be adopted incrementally
- **Fallback Behavior**: Graceful degradation for unsupported operations
- **Documentation**: Clear migration guides and examples

### Version Management

- **Feature Flags**: Enable/disable new string operations
- **Deprecation Strategy**: Clear timeline for deprecated features
- **Testing**: Comprehensive testing for all operation combinations
- **Validation**: Automated validation of operation correctness

## Testing Strategy

### Unit Testing

- **Operation Testing**: Test each string operation individually
- **Parameter Testing**: Test operation parameters and edge cases
- **Error Testing**: Test error conditions and exception handling
- **Performance Testing**: Test operation performance and memory usage

### Integration Testing

- **Comparison Integration**: Test integration with comparison handlers
- **Formula Integration**: Test integration with formula evaluation
- **Collection Integration**: Test integration with collection patterns
- **Real-World Testing**: Test with actual Home Assistant entities

### Validation Testing

- **Syntax Validation**: Test operation syntax and parsing
- **Type Validation**: Test type checking and conversion
- **Result Validation**: Test operation result correctness
- **Performance Validation**: Test performance under load

## Documentation and Examples

### User Documentation

- **Operation Reference**: Complete reference for all string operations
- **Usage Examples**: Practical examples for common use cases
- **Best Practices**: Guidelines for effective string operation usage
- **Troubleshooting**: Common issues and solutions

### Developer Documentation

- **Architecture Guide**: Detailed architecture and design decisions
- **Extension Guide**: Guide for adding custom string operations
- **Testing Guide**: Comprehensive testing strategies and examples
- **Performance Guide**: Performance optimization techniques

## Conclusion

This string handling proposal provides a comprehensive framework for enhanced string manipulation capabilities in the HA
Synthetic Sensors package. The design maintains compatibility with existing systems while adding powerful new capabilities
for string processing, comparison, and **dynamic attribute construction**.

The phased implementation approach ensures that core functionality can be delivered quickly while providing a clear path for
advanced features. The focus on type safety, performance, and error handling ensures that the system will be reliable and
maintainable in production environments.

The proposed string operations will significantly enhance the package's capabilities for device filtering, state analysis,
complex sensor calculations, and **dynamic attribute generation**, making it an even more powerful tool for Home Assistant
integrations.
