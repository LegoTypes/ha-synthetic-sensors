# HA Synthetic Sensors Architecture Overview

## Introduction

The HA Synthetic Sensors system implements a layered architecture for creating and managing synthetic sensors in Home Assistant.
This architecture follows compiler-like design principles with clear separation of concerns, enabling extensible formula
evaluation, robust dependency management, and type-safe entity reference handling.

## Architectural Design

### Layered Design

The system is organized into distinct layers, each with specific responsibilities:

- **Configuration Layer**: Handles YAML parsing, validation, and sensor definition management
- **Evaluation Layer**: Multi-phase formula evaluation with variable resolution and handler routing
- **Storage Layer**: Manages persistence, CRUD operations, and YAML export/import
- **Integration Layer**: Provides Home Assistant integration and entity management

### Evaluator Architecture

The evaluation system implements a **layered evaluator architecture** with clear separation of concerns:

#### Evaluator (`evaluator.py`)

**High-level orchestrator** that manages the entire evaluation pipeline:

- **Multi-Phase Coordination**: Orchestrates 5 distinct evaluation phases in strict order
- **Dependency Management**: Handles cross-sensor references and attribute dependencies
- **Circuit Breaker Pattern**: Implements two-tier error handling (fatal vs transient errors)
- **Caching & Performance**: Manages evaluation caching and compilation optimizations
- **Configuration Integration**: Handles sensor configurations and entity mappings
- **Cross-Sensor References**: Manages sensor registry for cross-sensor value sharing

#### CoreFormulaEvaluator (`core_formula_evaluator.py`)

**Focused evaluation service** implementing the CLEAN SLATE routing architecture:

- **CLEAN SLATE Routing**: Two-path routing system for formula evaluation
  - Path 1: Metadata functions → MetadataHandler
  - Path 2: Everything else → Enhanced SimpleEval (99% of cases)
- **Value Resolution**: Substitutes ReferenceValue objects with their actual values
- **Missing State Detection**: Identifies when sensors should be unavailable
- **Result Normalization**: Converts various result types to consistent return types
- **Reusable Service**: Designed for use across different contexts (main formulas, computed variables, attributes)
- **Deterministic Behavior**: Single responsibility with no fallback code

#### Hierarchical Relationship

```text
Evaluator (High-level orchestrator)
    ↓ uses
FormulaExecutionEngine (Execution coordination)
    ↓ uses
CoreFormulaEvaluator (Core evaluation logic)
    ↓ uses
EnhancedSimpleEvalHelper (Math operations)
```

#### FormulaEvaluatorService

**Shared service layer** that provides unified access to CoreFormulaEvaluator:

- **Unified Interface**: Single entry point for all formula types
- **Shared Core**: All formulas use the same CoreFormulaEvaluator instance
- **Pipeline Support**: Enables full pipeline evaluation for computed variables and attributes

### ReferenceValue Architecture

At the heart of the system is the ReferenceValue architecture that ensures type safety and provides handlers with access to both
entity references and their resolved values. This enables features like the `metadata()` function that require knowledge of the
reference from which the value was derived at any point in the resolution and evaluation pipeline.

#### Lazy Value Resolution

The ReferenceValue system implements lazy value resolution to preserve original entity references throughout the evaluation
pipeline:

- **Reference Preservation**: ReferenceValue objects maintain the original entity reference (e.g., `sensor.power_meter`)
  alongside the resolved value (e.g., `1000.0`)
- **Computed Variable Handling**: Computed variables containing metadata functions use lazy ReferenceValue resolution to prevent
  premature value extraction
- **Evaluation Order Control**: The 4-phase pipeline ensures metadata processing occurs before value resolution, preserving
  references for metadata handlers

### Evaluation Pipeline

Formula evaluation follows a multi-phase approach with distinct responsibilities:

- **Phase 0**: Pre-evaluation validation and preparation
- **Phase 1**: Entity ID resolution and ReferenceValue creation with early result detection
- **Phase 2**: Metadata function processing and context building
- **Phase 2**: Dependency management and evaluation routing
- **Phase 3**: Value resolution and formula execution
- **Phase 4**: Consolidated result processing, alternate state handling, and caching

This phased approach ensures proper evaluation order, particularly for evaluation handlers that require access to original
entity references rather than resolved values. All formula artifacts (main sensor formulas, computed variables, and attributes)
share the same pipeline via a core evaluation service. Phase 4 serves as the single consolidation point for all alternate state
processing, eliminating duplicate logic across phases.

## Formula Evaluation Order by Artifact Type

The system evaluates different formula artifacts in a specific order to handle dependencies correctly:

### 1. Configuration Variables

- Evaluated first during variable resolution phase (Phase 1)
- Global settings variables are inherited by all sensors in a sensor set
- Local variable definitions override global ones within their scope
- Creates ReferenceValue objects for use in subsequent evaluations

### 2. Main Sensor Formulas

- Evaluated after variables are resolved
- Can reference configuration variables and backing entities
- Result becomes the primary state value for the synthetic sensor
- Dependency management ensures required entities are available

### 3. Sensor Attributes

- Evaluated after main sensor formula if dependencies exist
- Can reference the main sensor value, other attributes, and configuration variables
- Dependency graph resolution ensures attributes are evaluated in correct order
- Circular attribute references are detected and rejected during pre-evaluation

### 4. Cross-Sensor References

- Handled through SensorRegistryPhase which maintains sensor value registry
- Sensors can reference other synthetic sensors by their key name
- Registry is updated after each successful sensor evaluation
- Enables complex sensor dependency networks

## Evaluation Pipeline Architecture

Each phase has specific responsibilities and cannot proceed until the previous phase completes successfully. All formula keys
whether in the main sensor, attributes, or variables use a single formula evaluation entry point.

### Core Formula Evaluation Service

- **Shared Service Pattern**: `FormulaEvaluatorService` provides a unified interface for all formula types using the same
  CoreFormulaEvaluator
- Entry points:
  - `FormulaEvaluatorService.evaluate_formula(resolved_formula, original_formula, context)` for main formulas (Phase 3
    execution).
  - `FormulaEvaluatorService.evaluate_formula_via_pipeline(formula, context, *, variables=None, bypass_dependency_management=False)`
    for computed variables and attributes to run the full pipeline (Phases 1–3) with dependency management.
- **Layered Architecture**:
  - Evaluator (high-level orchestrator) → FormulaExecutionEngine (execution coordination) → CoreFormulaEvaluator (core
    evaluation logic)
- Computed variables are evaluated by creating a temporary `FormulaConfig` (id `temp_cv_<hash>`) and invoking the same evaluator
  used for main/attribute formulas. A variables view can be supplied to expose global/sensor-level simple variables to the
  computed variable (excluding nested `ComputedVariable` instances to avoid recursion).
- All formula artifacts therefore share identical ordering: variable resolution → pre-eval handlers like metadata → reduction
  from ReferenceValue or numeric from string → evaluation.
- simpleeval evaluation is enhanced with additional functions for datetime, duration, and other capabilities beyond its native
  features

### Variable Scoping and Inheritance

- Scopes:
  - Global variables: available across the sensor set; inherited by all sensors unless locally overridden.
  - Sensor-level variables: available to the main sensor and its attributes.
  - Attribute-level variables: visible only within the attribute formula.
- Inheritance and precedence are handled by `VariableInheritanceHandler`:
  - Precedence: attribute-level > sensor-level > global.
  - Inherited variables are merged into the evaluation context prior to resolution.
- When evaluating computed variables via the unified service, a variables view is constructed from the parent
  `FormulaConfig.variables` (simple values only) to ensure correct scope visibility without forcing premature evaluation of
  nested computed variables.

### Dependency Extraction Coverage

- Dependencies are extracted from:
  - Main formula strings.
  - Sensor-level `variables` including recursive extraction from `ComputedVariable.formula` values.
  - Attribute `formulas` and attribute `variables` (including recursive extraction from `ComputedVariable.formula`).
- This ensures entity references inside computed variables and attributes are tracked, so missing entities trigger re-evaluation
  when they become available (fixes "Undefined variable: 'sensor'" caused by untracked dependencies).

### Lazy ReferenceValue Lifecycle and Substitution

- Phase 1 places `ReferenceValue` objects in the context for entity references and `state`, preserving original references and
  deferring value extraction.
- Phase 2 processes `metadata()` with access to preserved references.
- Phase 3 performs value substitution and evaluation:
  - Variable names in the formula are substituted with values from the handler context, converting numeric strings to numbers.
  - Secondary safeguard: any remaining dotted entity_id tokens (e.g., `sensor.x`) are substituted by looking up both an alias
    form (`sensor_x`) and the raw entity_id in the handler context. This covers cases where earlier phases deliberately
    preserved dotted tokens for metadata.
  - Unknown/unavailable states propagate as transient (non-fatal) and will make the synthetic sensor unavailable/unknown rather
    than raising configuration errors.

### Startup and Transient States

- During startup, entities may report `unknown` or `unavailable`. These are treated as transient conditions and do not generate
  errors:
  - Dependency checks classify these states separately from fatal missing entities.
  - Evaluation substitutes values accordingly and propagates transient state to synthetic sensors.
- Logging related to early context building and unresolved tokens is at DEBUG level to keep startup logs clean.

### Logging Guidance

- Context tracing (e.g., `ENTITY_REFERENCE_CONTEXT_DEBUG`) logs at DEBUG.
- Hints about non-substitution in early phases log at DEBUG.
- Core evaluation only logs errors for genuine evaluation failures; dotted token presence is traced at DEBUG before/after Phase
  3 substitution.

### Phase Coordination and Data Flow

The Evaluator orchestrates phase execution through the `_evaluate_formula_core` method (invoked by `FormulaEvaluatorService`),
which:

1. **Guards Against Premature Execution**: Pre-evaluation checks prevent processing of invalid or cached formulas
2. **Ensures Type Safety**: Variable resolution creates ReferenceValue objects before any handler execution
3. **Manages Dependencies**: Dependency analysis occurs after variable resolution but before execution
4. **Handles Errors Gracefully**: Each phase can return early with appropriate error states
5. **Optimizes Performance**: Caching and circuit breaker patterns prevent unnecessary computation

### Inter-Phase Communication

- **Phase 0 → Phase 1**: Passes validated FormulaConfig and initial context
- **Phase 1 → Phase 2**: Provides resolved formula with ReferenceValue objects
- **Phase 2 → Phase 3**: Delivers complete evaluation context with validated dependencies, preserving entity references in
  `ReferenceValue` objects for value substitution
- **Phase 3 → Phase 4**: Returns raw computation results for standardization
- **Phase 4 → Caller**: Provides standardized EvaluationResult with state information

### Error Propagation Strategy

The system implements a two-tier error handling approach:

- **Fatal Errors**: Configuration issues, circular dependencies, missing entity mappings trigger immediate failure
- **Transient Errors**: Temporary entity unavailability propagates as "unknown" or "unavailable" state, allowing recovery.
  Startup conditions where entities are not yet available are treated as transient, not fatal.
- **Circuit Breaker**: Repeated failures activate skip logic to prevent resource waste
- **State Propagation**: Error states flow through phases to provide meaningful sensor states

### Performance Optimizations

- **Early Exit**: Cache hits and circuit breaker activation prevent unnecessary phase execution
- **Compilation Caching**: Resolved formulas and compiled expressions are cached across evaluations
- **Reference Sharing**: ReferenceValueManager prevents duplicate entity lookups
- **Batch Processing**: Collection patterns are resolved efficiently in single operations

## Evaluation Pipeline Diagram

The following diagrams illustrate the complete evaluation pipeline with all phases, components, and data flow.

- **Method-level diagram**: `evaluation_pipeline_flow_with_methods.jpeg` — maps pipeline nodes to implementing modules.
  - **Examples**: `Evaluator._evaluate_formula_core`, `CoreFormulaEvaluator.evaluate_formula`, `MetadataHandler.evaluate`,
    `VariableResolutionPhase`.
  - **Purpose**: Helps trace runtime behavior back to source implementation for easier navigation and debugging.

![Evaluation Pipeline (method-level)](evaluation_pipeline_flow_with_methods.jpeg)

- **Overview diagram**: a high-level conceptual flow retained for orientation and design discussion.

![Evaluator Flow Diagram](evaluator_flow_diagram.jpeg)

_Figure: Multi-phase evaluation pipeline showing the flow from formula input through entity ID resolution, metadata processing,
value resolution, formula execution, and result processing. The 4-phase approach with lazy ReferenceValue resolution ensures
metadata functions receive original entity references rather than prematurely resolved values. The method-level diagram above
provides direct mapping between pipeline steps and their implementing functions/modules for easier navigation of the codebase._

## Major Components

### 1. Configuration Management

#### ConfigManager

Central configuration management component responsible for:

- Loading and validating YAML configurations
- Managing sensor sets and global settings
- Coordinating configuration updates and persistence
- Providing configuration validation and error reporting

#### SchemaValidator

Handles comprehensive schema validation for YAML configurations:

- Validates sensor definitions against schema rules
- Ensures type safety and structural integrity
- Provides detailed error messages for configuration issues
- Supports both individual sensor and batch validation

#### ConfigModels

Defines the data models for configuration structures:

- SensorConfig: Represents individual sensor definitions
- AttributeConfig: Handles sensor attribute configurations
- GlobalSettings: Manages global configuration settings
- VariableConfig: Represents variable definitions and references

### 2. Sensor Management

#### SensorManager

Core sensor lifecycle management component:

- Creates and manages DynamicSensor entities
- Handles sensor registration with Home Assistant
- Coordinates sensor updates and state changes
- Manages sensor metadata and device associations

#### SensorSet

Container for managing groups of related sensors:

- Maintains sensor collections with shared configuration
- Handles cross-sensor references and dependencies
- Provides bulk operations for sensor management
- Manages entity indexing and tracking

#### SensorSetGlobalSettings

Manages global settings that apply to all sensors in a set:

- Handles variable inheritance and scoping
- Manages device identifier associations
- Provides default metadata and configuration
- Coordinates global settings updates

### 3. Evaluation System

#### Evaluator

Main evaluation orchestrator that coordinates the multi-phase evaluation process:

- **Phase Coordination**: Manages five distinct evaluation phases in strict order with lazy ReferenceValue resolution
- **Circuit Breaker Pattern**: Implements two-tier error handling (fatal vs transient errors)
- **Dependency Management**: Handles cross-sensor references and attribute dependencies
- **Error Resilience**: Distinguishes between configuration errors and runtime failures
- **Performance Optimization**: Integrates caching and compilation optimizations
- **Metadata Function Support**: Ensures metadata functions receive original entity references, not prematurely resolved values
- **High-Level Orchestration**: Coordinates the entire evaluation pipeline including dependency management, caching, and error
  handling
- **Cross-Sensor References**: Manages sensor registry for cross-sensor value sharing
- **Configuration Integration**: Handles sensor configurations and entity mappings

#### VariableResolutionPhase

Phase 1 of the evaluation pipeline responsible for reference resolution:

- **Reference Resolution**: Converts entity references, variables, and cross-sensor references to ReferenceValue objects
- **Entity Detection**: Identifies Home Assistant state patterns and handles direct state access
- **Collection Expansion**: Resolves collection patterns (device_class, area, label) to actual entity lists
- **Variable Inheritance**: Applies global settings and handles variable scoping rules
- **Type Safety**: Ensures all resolved values are wrapped in ReferenceValue objects
- **Lazy Value Resolution**: Preserves original entity references in ReferenceValue objects for metadata function processing

#### ReferenceValueManager

Central component for managing ReferenceValue objects:

- Maintains entity reference registry for consistency
- Prevents double wrapping of ReferenceValue objects
- Provides type-safe context conversion
- Ensures memory efficiency through shared instances
- **Lazy Resolution Support**: Enables delayed value extraction to preserve original references for metadata functions
- **Computed Variable Handling**: Special handling for computed variables containing metadata functions to prevent premature
  value resolution

#### PreEvaluationPhase

Phase 0 component that validates formulas before any processing:

- **Circular Reference Detection**: Uses CircularReferenceValidator to detect dependency loops
- **Circuit Breaker Management**: Checks ErrorHandler to skip repeatedly failing formulas
- **Cache Validation**: Leverages EvaluatorCache to return cached results when available
- **State Token Validation**: Validates proper use of 'state' token in formulas

#### DependencyManagementPhase

Phase 2 component that handles dependency analysis and context preparation:

- **Dependency Extraction**: Uses DependencyParser to identify all entity dependencies
- **Collection Processing**: Expands collection patterns into concrete entity lists
- **Availability Checking**: Validates that all required entities are accessible
- **Context Merging**: Combines resolved variables with dependency data

#### ContextBuildingPhase

Phase 2 component that builds the final evaluation context:

- **Variable Integration**: Merges configuration variables with runtime context
- **Reference Validation**: Ensures all references are properly resolved
- **Context Normalization**: Standardizes context format for handler consumption
- **Priority Resolution**: Handles variable precedence (runtime > config > global)

#### FormulaExecutionEngine

Phase 3 component that coordinates formula execution and delegates to CoreFormulaEvaluator:

- **Execution Coordination**: Manages the execution flow and delegates to CoreFormulaEvaluator
- **Handler Integration**: Provides access to HandlerFactory and EnhancedSimpleEvalHelper
- **Error Handling**: Provides structured error reporting and state propagation
- **Result Processing**: Converts handler results to standardized EvaluationResult objects
- **Core Evaluator Access**: Exposes CoreFormulaEvaluator for shared service usage

### 4. Core Formula Evaluation and Handler Architecture

#### CoreFormulaEvaluator

Core formula evaluation service implementing the CLEAN SLATE routing architecture:

- **CLEAN SLATE Routing**: Implements two-path routing system for formula evaluation
  - Path 1: Metadata functions → MetadataHandler
  - Path 2: Everything else → Enhanced SimpleEval (99% of cases)
- **Value Resolution**: Substitutes ReferenceValue objects with their actual values in formulas
- **Missing State Detection**: Identifies when sensors should be unavailable due to missing state values
- **Result Normalization**: Converts various result types to consistent return types
- **Reusable Service**: Designed to be used across different contexts (main formulas, computed variables, attributes)
- **Deterministic Behavior**: Implements single responsibility with no fallback code

#### Handler Architecture (Phase 3 Components)

The handler system executes resolved formulas based on their content type. All handlers operate on ReferenceValue objects
created during Phase 1.

**AST Caching Integration**: Handlers that perform formula transformations for AST caching compatibility implement a specific
protocol:

- **Transformation Protocol**: Handlers return `tuple[str, dict[str, str]]` from `evaluate()` method
  - First element: Transformed formula string suitable for AST caching
  - Second element: Dictionary of pre-computed values for context injection
- **Cache Consistency**: Transformed formulas maintain consistent structure for cache key generation
- **Value Preservation**: Pre-computed values are injected into evaluation context for SimpleEval access
- **Optional Protocol**: This is an optional protocol - handlers that don't need AST caching transformations can return single
  values
- **Future Handler Support**: This pattern enables other handlers to implement similar AST caching transformations
- **Base Class Compatibility**: The base `FormulaHandler` class maintains `evaluate() -> Any` signature for backward
  compatibility

#### HandlerFactory

Selects and instantiates appropriate handlers based on formula analysis:

- **Content Analysis**: Examines formula to determine required handler type
- **Handler Selection**: Routes to NumericHandler or MetadataHandler based on formula content
- **Fallback Logic**: NumericHandler serves as the default handler for most expressions
- **Extension Support**: Enables registration of custom handler types

#### NumericHandler

Processes mathematical expressions and calculations:

- **SimpleEval Integration**: Uses enhanced SimpleEval for safe expression evaluation
- **ReferenceValue Extraction**: Converts ReferenceValue objects to numeric values
- **Collection Functions**: Implements sum(), avg(), min(), max() for entity collections
- **Mathematical Operations**: Supports standard arithmetic and advanced functions
- **Default Handler**: Serves as the fallback handler for most formula types

#### MetadataHandler

Provides access to Home Assistant entity metadata:

- **metadata() Function**: Implements the metadata(entity_id, attribute) function
- **Entity Registry Access**: Retrieves entity information from Home Assistant registry
- **Dynamic Lookups**: Enables runtime metadata queries within formulas
- **Reference Validation**: Ensures entity exists before metadata access
- **ReferenceValue Support**: Processes ReferenceValue objects containing original entity references
- **Lazy Resolution Integration**: Works with the 4-phase pipeline to receive original references, not prematurely resolved
  values
- **AST Caching Transformation**: Transforms metadata function calls for AST caching compatibility
  - Replaces `metadata(entity, 'key')` with `metadata_result(_metadata_N)` in formula strings
  - Returns tuple of `(transformed_formula, metadata_results_dict)` for cache consistency
  - Enables AST caching while preserving metadata lookup functionality

### 5. Variable Resolution System

#### VariableResolverFactory

Factory for creating and managing specialized variable resolvers:

- Coordinates different resolver types
- Provides unified resolution interface
- Handles resolver selection and routing
- Manages resolver lifecycle and state

#### Specialized Resolvers

Domain-specific resolvers for different reference types:

- **StateAttributeResolver**: Handles state.attribute patterns
- **EntityReferenceResolver**: Manages direct entity references
- **CrossSensorReferenceResolver**: Processes cross-sensor dependencies
- **SelfReferenceResolver**: Handles sensor self-references
- **ConfigVariableResolver**: Manages configuration variables
- **EntityAttributeResolver**: Processes entity attribute access

### 6. Storage and Persistence

#### StorageManager

Central storage management component:

- Handles YAML configuration persistence
- Manages sensor set storage operations
- Provides import/export functionality
- Coordinates storage updates and validation

#### StorageSensorOps

Handles sensor-specific storage operations:

- Manages sensor CRUD operations
- Handles sensor configuration updates
- Provides sensor migration capabilities
- Coordinates sensor storage validation

#### StorageYamlHandler

Specialized YAML processing component:

- Handles YAML serialization and deserialization
- Manages YAML formatting and structure
- Provides YAML validation and error reporting
- Supports YAML versioning and migration

### 7. Entity Management

#### EntityRegistryListener

Monitors and responds to Home Assistant entity registry changes:

- Detects entity ID renames and updates
- Coordinates system-wide entity reference updates
- Handles entity registry event processing
- Provides entity change resilience

#### EntityChangeHandler

Coordinates system-wide responses to entity changes:

- Manages cache invalidation across components
- Coordinates configuration updates
- Handles integration callbacks
- Ensures system consistency after entity changes

#### EntityIndex

Maintains comprehensive entity reference tracking:

- Indexes all entity references in sensor configurations
- Supports efficient entity lookup and dependency analysis
- Provides entity relationship mapping
- Handles entity collision detection and resolution

### 8. Cross-Sensor Reference Management

#### CrossSensorReferenceManager

Manages cross-sensor dependencies and references:

- Detects and analyzes cross-sensor dependencies
- Maintains sensor registry for value sharing
- Handles circular reference detection
- Coordinates evaluation order based on dependencies

#### CrossSensorReferenceDetector

Identifies cross-sensor references in configurations:

- Analyzes formulas for sensor key references
- Builds dependency graphs between sensors
- Provides reference resolution strategies
- Handles collision detection and resolution

#### CrossSensorReferenceReassignment

Manages entity ID reassignment for cross-sensor references:

- Updates references when entity IDs change
- Handles collision resolution with suffix generation
- Maintains reference integrity across updates
- Provides reference validation and error handling

### 9. Formula Processing

#### FormulaPreprocessor

Prepares formulas for evaluation:

- Handles formula normalization and formatting
- Manages formula validation and syntax checking
- Provides formula optimization opportunities
- Supports formula transformation and enhancement

#### FormulaCompilationCache

Caches compiled formulas for performance:

- Stores compiled AST formula representations
- Provides cache invalidation and updates
- Handles cache key generation and management
- Supports cache statistics and monitoring

#### FormulaUtils

Utility functions for formula processing:

- Provides formula analysis and inspection
- Handles formula transformation and manipulation
- Supports formula validation and error detection
- Manages formula optimization opportunities

### 10. Collection Processing

#### CollectionResolver

Handles collection-based operations and aggregations:

- Processes collection patterns (device_class, area, label)
- Manages collection functions (sum, avg, count, min, max)
- Supports collection filtering and exclusion
- Provides collection validation and error handling

### 11. Device Management

#### DeviceAssociation

Manages device associations for sensors:

- Handles device creation and registration
- Manages device metadata and properties
- Coordinates device-sensor relationships
- Provides device-based entity organization

#### EntityFactory

Creates and manages Home Assistant entities:

- Handles entity creation and configuration
- Manages entity metadata and properties
- Supports entity registration and updates
- Provides entity lifecycle management

### 12. Integration Layer

#### Integration

Main Home Assistant integration component:

- Handles Home Assistant setup and configuration
- Manages integration lifecycle and state
- Provides service interfaces and APIs
- Coordinates integration updates and maintenance

#### ServiceLayer

Provides service interfaces for external interactions:

- Handles service calls and requests
- Manages service validation and error handling
- Provides service documentation and discovery
- Supports service extensibility and customization

## Component Interactions

### Configuration Flow

1. **ConfigManager** loads YAML configurations
2. **SchemaValidator** validates configuration structure
3. **ConfigModels** create typed configuration objects
4. **SensorManager** creates sensor entities based on configuration
5. **SensorSet** organizes sensors into manageable groups

### Evaluation Flow

The evaluation pipeline processes formulas through distinct phases, each with specific responsibilities:

#### Phase 0: Pre-Evaluation (PreEvaluationPhase)

1. **CircularReferenceValidator** detects circular dependencies before any resolution
2. **ErrorHandler** checks circuit breaker status to skip repeatedly failing formulas
3. **EvaluatorCache** checks for cached results to avoid re-computation
4. **StateTokenValidator** validates state token resolution for formulas using 'state'

#### Phase 1: Entity ID Resolution (VariableResolutionPhase)

1. **VariableResolverFactory** creates specialized resolvers for different reference types
2. **EntityReferenceResolver** resolves entity references to ReferenceValue objects (preserving original references)
3. **CrossSensorReferenceResolver** resolves references to other synthetic sensors
4. **StateAttributeResolver** processes entity.attribute patterns
5. **ConfigVariableResolver** resolves configuration variables
6. **VariableInheritanceHandler** applies global settings and variable inheritance
7. **ReferenceValueManager** creates type-safe ReferenceValue objects with lazy value resolution

**Key Feature**: All entity references are converted to ReferenceValue objects that preserve the original reference while
allowing lazy value extraction during later phases.

#### Phase 2: Entity Reference-Reliant Handler Processing (VariableResolutionPhase)

Certain handlers are reliant on entity references to carry out work before evaluation. The metadata handler is one such entity
that needs an entity_id or 'state' token as its first parameter (by convention) to perform work just before evaluation. The
metadata handler needs an entity_id to query HA about metadata like 'last_changed' state. Normally entity references would be
resolve to values but we avoid this step to allow these handlers to use that entity reference first.

1. **Metadata Function Detection**: Identifies `metadata()` function calls in formulas
2. **MetadataHandler Processing**: Processes metadata functions with access to ReferenceValue objects containing original
   references
3. **Function Replacement**: Replaces metadata function calls with their resolved results
4. **Context Preservation**: Maintains ReferenceValue objects in context for subsequent processing

Entity Reference Handlers, e.g., Metadata functions receive ReferenceValue objects with original entity references (e.g.,
`sensor.power_meter`), not prematurely resolved values (e.g., `1000.0`), enabling proper metadata lookup.

#### Evaluation of entity reference reliant handlers (e.g., metadata) containing computed variables

- Computed variables whose formulas contain `metadata(...)` are discovered during variable resolution.
- To preserve the single-entry evaluation model and avoid spreading handler awareness, they are evaluated (when possible) in the
  same resolver pass that already processes metadata for the current formula.
- Gate conditions:
  - `_hass` and `current_sensor_entity_id` exist in context, and
  - `hass.states.get(current_sensor_entity_id)` returns a state object.
- When the gate passes, the computed variable is evaluated via the evaluation pipeline and its `ReferenceValue` is updated to
  hold the concrete boolean/numeric result. When the gate fails (e.g., during startup), a lazy `ReferenceValue` with
  `value=None` is kept for that cycle. On later polls, once the entity is present, the resolver evaluates and updates the
  computed variable, so attribute formulas that reference it (e.g., `grace_period_active: within_grace`) substitute a real
  boolean instead of `None`.

#### Phase 3: Value Resolution and Formula Execution (CoreFormulaEvaluator)

1. **Pipeline Routing**: Processes formula elements through pipeline in order using the handlers first
   - Metadata functions → MetadataHandler
   - Everything else → Enhanced SimpleEval
2. **Handler Transformation**: Handlers perform formula transformations for AST caching compatibility
   - MetadataHandler transforms `metadata(entity, 'key')` → `metadata_result(_metadata_N)`
   - Returns `(transformed_formula, metadata_results_dict)` for cache consistency
   - Pre-computed values are injected into evaluation context
3. **ReferenceValue Extraction**: Extracts actual values from ReferenceValue objects for final formula evaluation
4. **Formula Substitution**: Replaces variable references with resolved values in the formula string
5. **Missing State Detection**: Identifies missing states that should trigger unavailable sensor behavior
6. **Enhanced SimpleEval Execution**: Performs final mathematical evaluation using enhanced SimpleEval
7. **Result Processing**: Converts evaluation results to standardized format

Value extraction occurs only at the final evaluation stage, ensuring metadata functions have access to original references
throughout the pipeline.

**AST Caching Integration**: The transformation pattern ensures cache consistency by:

- Using transformed formulas (e.g., `metadata_result(_metadata_0)`) as cache keys
- Maintaining consistent formula structure across evaluations
- Enabling cache hits for formulas with dynamic metadata values

**AST Cache Setup Call Chain for Metadata Functions**:

1. **CoreFormulaEvaluator.evaluate_formula()** (Phase 3)
   - Receives original formula: `"metadata(sensor_1, 'last_changed')"`
   - Calls: `handler.evaluate(original_formula, handler_context)`

2. **MetadataHandler.evaluate()**
   - Transforms formula: `"metadata(sensor_1, 'last_changed')"` → `"metadata_result(_metadata_0)"`
   - Returns: `("metadata_result(_metadata_0)", {"_metadata_0": "2025-01-01T12:00:00+00:00"})`

3. **CoreFormulaEvaluator.evaluate_formula()** (continued)
   - Sets: `resolved_formula = "metadata_result(_metadata_0)"`
   - Calls: `self._enhanced_helper.try_enhanced_eval(resolved_formula, enhanced_context)`

4. **EnhancedSimpleEvalHelper.try_enhanced_eval()**
   - Calls: `self._compilation_cache.get_compiled_formula(formula)` ← **AST CACHE SETUP HAPPENS HERE**
   - Formula parameter: `"metadata_result(_metadata_0)"` (transformed formula)

5. **FormulaCompilationCache.get_compiled_formula()**
   - Generates cache key from: `"metadata_result(_metadata_0)"`
   - Creates: `CompiledFormula("metadata_result(_metadata_0)", math_functions)`
   - Parses AST: `self.evaluator.parse("metadata_result(_metadata_0)")` ← **AST PARSING HAPPENS HERE**
   - Stores in cache: `self._cache[cache_key] = compiled`

For metadata functions we resolve its two parameters before simpleeval evaluation. We then need the AST cache to reflect a
single parameter call because we already have resolved the metadata value and we are only doing single parameter substitution.
The metadata function simpleeval knows about simply returns the parameter it was given. The AST cache is set up using the
**transformed function** (`"metadata_result(_metadata_0)"`), not the original formula (`"metadata(sensor_1, 'last_changed')"`).
This ensures cache consistency because subsequent evaluations will use the same transformed formula structure.

**Subsequent Evaluations (Cache Hit)**:

1. **CoreFormulaEvaluator.evaluate_formula()** (Phase 3)
   - Receives same original formula: `"metadata(sensor_1, 'last_changed')"`
   - Calls: `handler.evaluate(original_formula, handler_context)`

2. **MetadataHandler.evaluate()**
   - Transforms to same structure: `"metadata_result(_metadata_0)"` (different metadata value)
   - Returns: `("metadata_result(_metadata_0)", {"_metadata_0": "2025-01-01T12:30:00+00:00"})` (updated value)

3. **CoreFormulaEvaluator.evaluate_formula()** (continued)
   - Sets: `resolved_formula = "metadata_result(_metadata_0)"` (same structure)
   - Calls: `self._enhanced_helper.try_enhanced_eval(resolved_formula, enhanced_context)`

4. **EnhancedSimpleEvalHelper.try_enhanced_eval()**
   - Calls: `self._compilation_cache.get_compiled_formula(formula)`
   - Formula parameter: `"metadata_result(_metadata_0)"` (same transformed formula)

5. **FormulaCompilationCache.get_compiled_formula()**
   - Generates same cache key from: `"metadata_result(_metadata_0)"`
   - **CACHE HIT**: Returns existing `CompiledFormula` with pre-parsed AST
   - **No AST parsing needed**: Uses cached AST for evaluation

**Result**: The same formula structure enables cache hits, while different metadata values are handled through context injection
rather than formula changes.

#### Phase 4: Consolidated Result Processing and Alternate State Handling

1. **Early Result Processing**: Handles early results from Phase 1 (HA state detection)
2. **Evaluation Result Processing**: Processes results from Phase 3 evaluation
3. **Exception Processing**: Handles exceptions from Phase 3 evaluation
4. **Consolidated Alternate State Handling**: Single point for all alternate state handler processing
5. **Result Finalization**: Final result processing and caching

**Key Feature**: Phase 4 serves as the single consolidation point for all alternate state processing. 2. **Handler
Integration**: Provides access to HandlerFactory and EnhancedSimpleEvalHelper 3. **Error Propagation**: Handles and propagates
evaluation errors appropriately 4. **Result Standardization**: Converts CoreFormulaEvaluator results to standardized format

### Single Value Detection and Alternate State Processing

The system implements early detection of single value cases and consolidates all alternate state processing in Phase 4:

#### Phase 1: Formula-Level Single Value Detection

- **Location**: End of Variable Resolution Phase
- **Purpose**: Detects when entire formula resolves to single HA state value
- **Examples**: `"unknown"`, `"unavailable"`, `"none"`
- **Flow**: Returns early result → Phase 4 processing

#### Phase 4: Consolidated Alternate State Processing

- **Location**: Post-Evaluation Processing
- **Purpose**: Single point for all alternate state handler processing
- **Inputs**: Early results from Phase 1, evaluation results from Phase 3, exceptions from Phase 3
- **Handler**: `process_evaluation_result()` (unified logic)

### Result Processing

1. **EvaluatorResults** creates standardized result objects
2. **EvaluatorCache** caches successful results for performance
3. **ErrorHandler** tracks evaluation success/failure for circuit breaker logic

### Storage Flow

1. **StorageManager** coordinates persistence operations
2. **StorageYamlHandler** handles YAML serialization
3. **StorageSensorOps** manages sensor-specific storage
4. **EntityIndex** updates entity reference tracking

### Entity Change Flow

1. **EntityRegistryListener** detects entity changes
2. **EntityChangeHandler** coordinates system updates
3. **StorageManager** updates persisted configurations
4. **CrossSensorReferenceManager** updates references
5. **FormulaCompilationCache** invalidates affected formulas

## Architectural Considerations

### Extensibility

The handler architecture, pluggable comparison, and modular design enable extension of functionality through new handlers,
resolvers, and evaluation phases.

**AST Caching Transformation Protocol**: The system supports handlers that need to transform formulas for AST caching
compatibility:

- **Optional Protocol**: Handlers can implement the transformation protocol by returning `tuple[str, dict[str, str]]` from
  `evaluate()`
- **Cache Consistency**: Transformed formulas maintain consistent structure for cache key generation
- **Value Preservation**: Pre-computed values are injected into evaluation context for SimpleEval access
- **Backward Compatibility**: Existing handlers continue to work without modification
- **Future Handler Support**: New handlers can implement similar transformations for AST caching benefits

### Performance

Multi-layered caching, compiled formulas, and efficient reference resolution provide high performance for complex sensor
configurations.

### Resilience

The system gracefully handles entity changes, configuration updates, and error conditions without requiring manual intervention.

### Maintainability

Clear separation of concerns, well-defined interfaces, and extensive testing.
