# Evaluator Flow Diagram

The evaluation pipeline processes formulas through five distinct phases:

## Phase 0: Pre-Evaluation Validation

- **CircularReferenceValidator**: Detects circular dependencies before any resolution
- **Circuit Breaker Check**: Skips repeatedly failing formulas to prevent resource waste
- **Cache Check**: Returns cached results when available for performance
- **State Token Validation**: Validates proper use of 'state' token in formulas

## Phase 1: Variable Resolution

- **VariableResolverFactory**: Creates specialized resolvers for different reference types
- **Specialized Resolvers**: Handle attribute references, cross-sensor references, state patterns, and config variables
- **ReferenceValueManager**: Creates type-safe ReferenceValue objects for all resolved references

## Phase 2: Dependency Management

- **DependencyParser**: Extracts entity dependencies from formulas
- **CollectionResolver**: Expands collection patterns (device_class, area, label) to entity lists
- **EvaluatorDependency**: Validates entity availability and handles missing dependencies
- **ContextBuildingPhase**: Merges variables and dependencies into evaluation context

## Phase 3: Formula Execution

- **HandlerFactory**: Selects appropriate handler based on formula content analysis
- **Specialized Handlers**: Execute formulas using NumericHandler (default) or MetadataHandler
- **SimpleEval Integration**: Provides safe mathematical expression evaluation

## Phase 4: Result Processing

- **EvaluatorResults**: Creates standardized result objects with proper state information
- **EvaluatorCache**: Caches successful results for performance optimization
- **ErrorHandler**: Tracks evaluation success/failure for circuit breaker logic

## Error Handling Paths

- **Fatal Errors**: Circular references, configuration errors, missing mappings
- **Transient Errors**: Temporarily unavailable entities, network issues
- **Cache Hits**: Short-circuit evaluation for previously computed results
- **Circuit Breaker**: Skip evaluation for repeatedly failing formulas

The system ensures type safety through ReferenceValue objects, handles dependencies correctly through phase separation, and
provides resilient error handling for both permanent and temporary issues.
