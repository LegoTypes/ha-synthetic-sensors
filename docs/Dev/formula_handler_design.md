# Formula Handler Design

## Overview

The formula handler system provides a safe, cached, and extensible formula evaluation framework for synthetic sensors.
Building on SimpleEval's proven AST caching architecture, this design creates an umbrella formula evaluator that delegates
operations to specialized handlers while maintaining performance through caching strategies.

The system integrates with the comparison handler design, enabling complex formulas that combine mathematical operations,
string operations, and type-aware comparisons within a deterministic evaluation framework.

## Architecture Principles

### 1. **AST-Based Caching Strategy**

Following SimpleEval's approach, formulas are parsed once into Abstract Syntax Trees (ASTs) and cached for repeated
evaluation. The core caching strategy involves:

- **Formula Cache**: Stores compiled formula representations to avoid repeated parsing
- **AST Cache**: Caches parsed syntax trees for reuse across multiple evaluations
- **Compiled Cache**: Stores optimized execution plans for each formula

The caching system uses a layered approach where formulas are first parsed into ASTs, then compiled into optimized execution
plans, and finally cached for repeated evaluation with different variable sets.

### 2. **Umbrella Delegation Architecture**

The formula evaluator acts as an umbrella coordinator that delegates operations to specialized subsystems:

- **Comparison Handler**: Handles all comparison operations using the existing comparison system
- **Arithmetic Handler**: Manages mathematical operations with type awareness
- **String Handler**: Processes string operations including concatenation
- **Function Handler**: Executes function calls including collection functions
- **Numeric Evaluator**: Integrates SimpleEval for safe numeric operations

The umbrella architecture ensures that each operation type is handled by the most appropriate specialized system while
maintaining a unified interface for formula evaluation.

### 3. **Layered Compilation Strategy**

Formulas are compiled in layers, with each layer handling specific operation types:

- **AST Analysis**: Parse the formula and identify all operation types
- **Operation Planning**: Create optimized execution plans for different operation categories
- **Handler Assignment**: Assign appropriate handlers to each operation type
- **Optimization**: Optimize the execution order for performance

This layered approach allows for sophisticated optimization while maintaining clear separation of concerns.

## Integration with Comparison Handler System

### Shared Type Analysis Infrastructure

Both formula and comparison systems share the same type analysis infrastructure. The formula system leverages the existing
TypeAnalyzer from the comparison handler design, ensuring consistent type handling across both comparison and formula
operations.

The shared infrastructure includes:

- Type categorization and analysis using `TypeAnalyzer`
- Value extraction using `ValueExtractor.extract_comparable_value`
- Built-in type constants from `BUILTIN_VALUE_TYPES`
- User-defined type handling through `UserType` protocol

### Simplified Metadata Approach

The formula system follows the same simplified approach as the comparison system:

- **No Complex Metadata**: Metadata extraction only occurs when extension registration system exists
- **Extension-First**: Check for user extensions first, then proceed with built-in operations
- **Direct Operation**: Built-in formula operations work directly on operands without requiring metadata

### Operation Context Integration

The formula system uses a simplified operation routing approach aligned with the comparison system:

- **Comparison Operations**: Delegates to the comparison handler system (which checks for extensions first)
- **Arithmetic Operations**: Built-in mathematical operations work directly on operands
- **String Operations**: Built-in string operations (concatenation) work directly on operands
- **Function Operations**: Collection and mathematical functions work directly on operands

**Future Extension Points**: When the YAML extension registration system is implemented, each operation type will check for
registered user extensions before proceeding with built-in logic.

This integration ensures operations are handled consistently while avoiding unnecessary metadata processing until the
extension system exists.

## Multi-Layer Caching Strategy

### Layer 1: AST Parsing Cache

The AST cache stores parsed Abstract Syntax Trees using an LRU (Least Recently Used) eviction strategy. This layer:

- Validates formula syntax before caching
- Implements safety checks to prevent malicious expressions
- Uses efficient storage with automatic cleanup of old entries
- Provides fast lookup for repeated formula parsing

### Layer 2: Operation Plan Cache

The operation plan cache stores compiled execution plans that optimize formula evaluation:

- Analyzes operation dependencies and execution order
- Creates optimized execution plans for different operation types
- Caches plans to avoid repeated compilation
- Supports plan optimization for performance

### Layer 3: Sub-Expression Cache

The sub-expression cache optimizes evaluation within a single formula execution:

- Caches intermediate results during formula evaluation
- Tracks variable dependencies for cache invalidation
- Provides fast access to repeated sub-expressions
- Clears automatically between different evaluation contexts

## Formula Operation Handlers

### Arithmetic Operation Handler

The arithmetic operation handler manages mathematical operations with sophisticated type awareness:

- **Type Analysis**: Analyzes operand types before performing operations
- **Type-Specific Logic**: Routes operations to appropriate type handlers
- **Safety Features**: Implements safe arithmetic with overflow protection
- **Error Handling**: Provides clear error messages for unsupported operations

The handler supports numeric arithmetic, datetime arithmetic, and user-defined type arithmetic with automatic type conversion
and unit handling.

### String Operation Handler

The string operation handler processes string operations including concatenation:

- **Type Conversion**: Automatically converts values to strings with appropriate formatting
- **Length Limits**: Enforces maximum string length to prevent memory exhaustion
- **HA Conventions**: Follows Home Assistant conventions for boolean and null values
- **Safety Checks**: Validates operations before execution

### Function Call Handler

The function call handler executes function calls including collection functions:

- **Built-in Functions**: Supports standard mathematical and collection functions
- **Custom Functions**: Allows registration of user-defined functions
- **Collection Support**: Integrates with the collection pattern system
- **Context Awareness**: Provides evaluation context to functions

## Plugin Architecture and Extensibility

### Overview

The formula handler system extends the comparison plugin architecture to support pluggable formula operations, custom
evaluators, and specialized processing handlers. This creates a unified plugin ecosystem where both comparison and formula
operations can be extended through the same infrastructure.

### Plugin Interface Protocols

The plugin system defines several protocols for different types of extensions:

- **FormulaOperationProtocol**: For operation handlers supporting duck-style typing
- **FormulaFunctionProtocol**: For custom formula functions
- **FormulaEvaluatorProtocol**: For complete formula evaluators
- **FormulaPackageProtocol**: For complete formula packages combining multiple handlers

Each protocol defines the interface that plugins must implement, ensuring consistency and interoperability across the plugin
ecosystem.

### Plugin Registry System

The plugin registry manages formula plugins with hierarchical fallback:

- **Operation Handlers**: Registers handlers by operation context (arithmetic, string, logical, custom)
- **Function Handlers**: Manages function handlers with special support for collection functions
- **Evaluators**: Supports complete formula evaluators as fallback options
- **Package Support**: Allows registration of complete formula packages

The registry implements sophisticated fallback logic, trying specialized handlers first before falling back to more general
solutions.

### Python and SimpleEval Integration

#### Fallback Handler System

The Python fallback handler provides safe access to Python's built-in capabilities:

- **Safety Validation**: Checks if operations are safe for Python execution
- **Type Compatibility**: Ensures operands are compatible for the requested operation
- **Error Handling**: Provides clear error messages for failed operations
- **Operator Support**: Supports arithmetic, comparison, logical, and containment operations

#### SimpleEval Integration Handler

The SimpleEval integration handler leverages SimpleEval for safe numeric expressions:

- **Safety Configuration**: Applies appropriate safety limits and restrictions
- **Function Support**: Adds safe mathematical functions
- **Syntax Validation**: Checks for supported syntax before evaluation
- **Error Handling**: Provides clear error messages for evaluation failures

### Metadata-Driven Formula Extensions

#### Formula Metadata Protocol

The metadata protocol allows objects to provide formula evaluation metadata:

- **Formula Metadata**: Provides context for formula evaluation
- **Processing Hints**: Offers hints for specialized processing
- **Custom Evaluation**: Indicates when custom evaluation logic is required

#### Metadata-Aware Operation Handler

The metadata-aware handler uses metadata for sophisticated operation handling:

- **Metadata Analysis**: Analyzes operand metadata to determine operation strategy
- **Component-wise Operations**: Supports operations on composite values
- **Normalized Operations**: Handles operations with automatic normalization
- **Custom Processors**: Invokes custom processors based on metadata

### Plugin Configuration and Loading

#### Advanced Plugin Configuration

The plugin system supports sophisticated configuration through YAML files:

```yaml
# formula_plugins.yaml
formula_plugins:
  - type: package
    package: "advanced_math_operations"
    class: "AdvancedMathPackage"
    config:
      precision: "high"
      enable_complex_numbers: true
      custom_functions:
        - "integrate"
        - "differentiate"
        - "solve_equation"

  - type: operation_handler
    module: "custom_energy_operations"
    class: "EnergyArithmeticHandler"
    context: "arithmetic"
    priority: "high"
    config:
      energy_units: "kwh"
      conversion_factors:
        joules: 3600000
        btus: 3412.14

  - type: function_handler
    module: "statistical_functions"
    handlers:
      - class: "StatisticalFunctionHandler"
        functions: ["median", "mode", "std_dev", "variance"]
      - class: "CollectionStatHandler"
        functions: ["percentile", "quartile", "outliers"]

  - type: evaluator
    module: "symbolic_evaluator"
    class: "SymbolicMathEvaluator"
    priority: "high"
    config:
      enable_symbolic_math: true
      simplify_expressions: true

evaluation_settings:
  enable_python_fallback: true
  enable_simpleeval_fallback: true
  strict_type_checking: false
  enable_metadata_processing: true
  cache_compiled_expressions: true
```

#### Dynamic Plugin Loader

The dynamic plugin loader loads formula plugins from configuration:

- **Configuration Parsing**: Reads plugin configurations from YAML files
- **Dynamic Loading**: Loads plugins at runtime based on configuration
- **Error Handling**: Provides clear error messages for loading failures
- **Initialization**: Initializes plugins with appropriate context

### Integration Example

#### Complete Usage Example

The plugin system enables sophisticated formula evaluation with custom handlers:

- **Plugin Registration**: Register custom operation and function handlers
- **Enhanced Evaluation**: Use custom handlers for specialized operations
- **Collection Functions**: Leverage collection functions with metadata support
- **Complex Formulas**: Evaluate complex formulas with plugin support

The system supports energy calculations with automatic unit conversion, statistical analysis with custom functions, and
sophisticated mathematical operations through the plugin architecture.

### Benefits of Formula Plugin Architecture

1. **Unified Extensibility**: Same plugin system for both comparisons and formulas
2. **Metadata-Driven Processing**: Sophisticated handling based on value metadata
3. **Python Integration**: Seamless fallback to Python's built-in capabilities
4. **SimpleEval Compatibility**: Leverages existing safe evaluation infrastructure
5. **Hierarchical Fallback**: Multiple layers of handler selection and fallback
6. **Package Support**: Complete formula packages can provide integrated functionality
7. **Type Safety**: Protocol-based interfaces ensure correct implementation
8. **Performance**: Plugin caching and optimized handler selection

## SimpleEval Integration

### Safe Numeric Operations

The system integrates SimpleEval for safe numeric operations:

- **Safety Limits**: Applies appropriate limits for power operations and string length
- **Custom Functions**: Adds safe mathematical functions
- **Error Handling**: Provides clear error messages for evaluation failures
- **Type Safety**: Ensures numeric results are properly typed

### Custom AST Node Handling

The system extends SimpleEval's AST handling for custom operations:

- **Comparison Integration**: Routes comparison nodes to the comparison handler system
- **Binary Operations**: Handles binary operations with type awareness
- **Function Calls**: Processes function calls including collection functions
- **Custom Routing**: Routes operations to appropriate specialized handlers

## Performance Optimization Strategies

### 1. **Layered Compilation**

The system uses layered compilation for optimal performance:

- **AST Parsing**: Parse formulas once and cache the results
- **Static Analysis**: Identify static subexpressions that can be pre-computed
- **Execution Planning**: Create optimized execution plans
- **Pre-computation**: Pre-compute static parts of formulas

### 2. **Variable Dependency Analysis**

The system analyzes variable dependencies for caching optimization:

- **Dependency Tracking**: Track which variables each subexpression depends on
- **Cache Validation**: Determine if cached results are still valid
- **Optimization**: Optimize evaluation based on dependency patterns
- **Invalidation**: Invalidate cache when dependencies change

## Error Handling and Safety

### Exception Hierarchy

The system implements a comprehensive exception hierarchy:

- **FormulaError**: Base exception for all formula-related errors
- **FormulaSyntaxError**: Invalid formula syntax
- **FormulaEvaluationError**: Errors during formula evaluation
- **UnsupportedOperationError**: Operations not supported for given types
- **NumericEvaluationError**: Errors in numeric evaluation
- **StringTooLongError**: String results exceeding maximum length
- **FunctionArgumentError**: Invalid function arguments

### Safety Validation

The system includes comprehensive safety validation:

- **AST Safety**: Validates AST for safety concerns
- **Import Prevention**: Prevents import statements
- **Lambda Prevention**: Prevents lambda expressions
- **Comprehension Limits**: Limits comprehension size to prevent memory exhaustion
- **Function Call Validation**: Validates function calls for safety

## Usage Examples

### Basic Formula Evaluation

The system supports various types of formula evaluation:

- **Mathematical Expressions**: Basic arithmetic with automatic operator precedence
- **Variable Evaluation**: Formulas with variables and dynamic values
- **String Operations**: String concatenation with automatic type conversion
- **Comparison Operations**: Boolean expressions with type-aware comparisons

### Collection Function Integration

The system integrates collection functions with comparison handlers:

- **Pattern Matching**: Use collection patterns for entity filtering
- **Aggregation**: Apply aggregation functions to filtered collections
- **Complex Formulas**: Combine multiple operations in single formulas
- **Percentage Calculations**: Calculate percentages and ratios

### Cached Evaluation

The system provides efficient cached evaluation:

- **Parse Once**: Parse formulas once and cache the results
- **Multiple Evaluations**: Evaluate the same formula with different variables
- **Performance**: Achieve high performance through caching
- **Memory Efficiency**: Use LRU caching to manage memory usage

## Implementation Phases

### Phase 1: Core Infrastructure

- [ ] Basic formula evaluator with AST caching
- [ ] Integration with existing comparison handler system
- [ ] SimpleEval wrapper for safe numeric operations
- [ ] Basic error handling and safety validation

### Phase 2: Operation Handlers

- [ ] Arithmetic operation handler with type awareness
- [ ] String operation handler for concatenation
- [ ] Function call handler for collection functions
- [ ] Operation context routing system

### Phase 3: Advanced Caching

- [ ] Multi-layer caching system (AST, plans, subexpressions)
- [ ] Variable dependency analysis
- [ ] Cache invalidation strategies
- [ ] Performance optimization

### Phase 4: Integration and Testing

- [ ] Full integration with evaluator phases architecture
- [ ] Comprehensive test suite
- [ ] Performance benchmarking
- [ ] Documentation and examples

## Benefits

- **Performance**: Multi-layer caching eliminates repeated parsing and compilation
- **Safety**: Built on SimpleEval's proven safety model with additional protections
- **Extensibility**: Modular handler system allows easy addition of new operations
- **Integration**: Seamless integration with existing comparison handler system
- **Type Safety**: Type-aware operations prevent runtime errors
- **Deterministic**: No fallback logic ensures predictable behavior

## Conclusion

This formula handler design provides a robust, performant, and safe foundation for formula evaluation in synthetic sensors.
By building on SimpleEval's proven AST caching approach while integrating with our type-aware comparison system, we achieve
both safety and performance while maintaining the deterministic behavior required for actionable sensor evaluations.

## Integration with Type System

### Shared Type Infrastructure

The formula handler system leverages the same simplified type infrastructure as the comparison handler system, ensuring
consistent type handling across both comparison and formula operations. The shared infrastructure includes:

- **Value Extraction**: Uses `ValueExtractor.extract_comparable_value` for consistent value extraction
- **Built-in Type Constants**: Shares `BUILTIN_VALUE_TYPES` for consistent type checking
- **User Type Protocol**: Supports `UserType` objects that implement the required protocol
- **Type Categorization**: Uses shared type analysis patterns for operation dispatch

### User Type Formula Operations

User-defined types work seamlessly in formula operations through the same simplified approach:

- **Protocol-Based**: `UserType` objects implement required methods for value extraction and metadata
- **Extension Registration**: Future YAML-based extension system will register handlers for user types
- **Built-in Integration**: User types integrate through the same value extraction mechanisms
- **Future Enhancement**: Custom arithmetic operations will be supported when extension system exists

### Enhanced Formula Examples with User Types

The system supports sophisticated formulas with user-defined types:

- **Energy Management**: Automatic unit conversion for energy calculations
- **Temperature Operations**: Celsius/Fahrenheit conversion in formulas
- **Pressure and Flow**: Hydraulic calculations with unit handling
- **Collection Functions**: Collection functions that work with user types

### User Type Function Extensions

User types can provide custom functions that integrate with the formula system:

- **Energy Functions**: Unit conversion, power duration, and cost calculations
- **Statistical Functions**: Median, mode, standard deviation for user types
- **Physical Functions**: Velocity, pressure drop, and efficiency calculations
- **Financial Functions**: Cost analysis and economic calculations

### Extension-Based Operation Routing (Future)

When the YAML extension registration system is implemented, the formula system will determine operation handlers through:

- **Extension Configuration**: YAML-defined extensions for specific operation types
- **Handler Registration**: Registered handlers for physical units, financial calculations, etc.
- **Declarative Setup**: Extensions configured through YAML rather than metadata analysis
- **Simple Pipeline**: Check for registered extensions first, then proceed with built-in operations

### Performance Optimizations

The simplified system includes several performance optimizations:

- **Value Extraction Caching**: Cache results from `extract_comparable_value` for repeated operations
- **Type Analysis Caching**: Cache type categorization results for performance
- **Extension Lookup Caching**: Cache extension registration lookups (when system exists)
- **LRU Eviction**: Use LRU caching to manage memory usage efficiently

This design demonstrates how the simplified type system provides an efficient foundation for both comparison and formula
operations, avoiding unnecessary metadata processing while supporting future extensibility through the YAML-based extension
registration system.
