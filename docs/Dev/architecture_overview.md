# HA Synthetic Sensors Architecture Overview

## Introduction

The HA Synthetic Sensors system implements a sophisticated, layered architecture for creating and managing synthetic sensors
in Home Assistant. This architecture follows compiler-like design principles with clear separation of concerns, enabling
extensible formula evaluation, robust dependency management, and type-safe entity reference handling.

## Core Architectural Principles

### Layered Design

The system is organized into distinct layers, each with specific responsibilities:

- **Configuration Layer**: Handles YAML parsing, validation, and sensor definition management
- **Evaluation Layer**: Multi-phase formula evaluation with variable resolution and handler routing
- **Storage Layer**: Manages persistence, CRUD operations, and YAML export/import
- **Integration Layer**: Provides Home Assistant integration and entity management

### ReferenceValue Architecture

At the heart of the system is the ReferenceValue architecture that ensures type safety and provides handlers with access to
both entity references and resolved values. This enables features like the `metadata()` function that require knowledge of
actual Home Assistant entity IDs.

### Compiler-Like Evaluation

Formula evaluation follows a multi-phase approach similar to compiler design:

- **Phase 0**: Early circular reference detection
- **Phase 1**: Complete reference resolution
- **Phase 2**: Handler routing and evaluation
- **Phase 3**: Result validation and caching

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

- Manages evaluation phases and their execution order
- Routes formulas to appropriate handlers
- Handles evaluation results and error propagation
- Provides caching and performance optimization

#### VariableResolutionPhase

First critical phase in the evaluation pipeline:

- Resolves all variable references in formulas
- Creates ReferenceValue objects for type safety
- Handles entity ID collision resolution
- Provides enhanced dependency reporting

#### ReferenceValueManager

Central component for managing ReferenceValue objects:

- Maintains entity reference registry for consistency
- Prevents double wrapping of ReferenceValue objects
- Provides type-safe context conversion
- Ensures memory efficiency through shared instances

#### FormulaRouter

Intelligently routes formulas to appropriate handlers:

- Analyzes formula content to determine handler type
- Supports handler composition and chaining
- Provides extensible handler registration
- Handles fallback and error scenarios

### 4. Handler Architecture

#### BaseHandler

Abstract base class defining the handler interface:

- Provides common handler functionality
- Defines evaluation contract for implementations
- Supports handler composition and delegation
- Handles error reporting and validation

#### NumericHandler

Processes mathematical expressions and calculations:

- Uses SimpleEval for formula evaluation
- Handles mathematical functions and operations
- Supports collection functions (sum, avg, min, max)
- Extracts values from ReferenceValue objects

#### StringHandler

Manages string operations and text processing:

- Handles string literals and concatenation
- Provides text manipulation functions
- Supports pattern matching and validation
- Processes string-based formulas

#### BooleanHandler

Evaluates logical expressions and conditions:

- Handles comparison operations and logical operators
- Supports conditional expressions and ternary operations
- Manages boolean state conversions
- Provides truth value evaluation

#### MetadataHandler

Specialized handler for entity metadata operations:

- Implements the metadata() function for entity information access
- Handles Home Assistant entity metadata lookups
- Provides entity registry information
- Supports metadata-based calculations

#### DateHandler

Processes date and time operations:

- Handles datetime functions and calculations
- Supports date arithmetic and comparisons
- Provides timezone-aware operations
- Manages temporal expressions

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

- Stores compiled formula representations
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

1. **Evaluator** initiates evaluation process
2. **VariableResolutionPhase** resolves all references
3. **ReferenceValueManager** creates type-safe contexts
4. **FormulaRouter** selects appropriate handler
5. **Specialized Handler** processes formula and returns result

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

## Architectural Principles

### Type Safety

The ReferenceValue architecture ensures type safety throughout the system, preventing raw values from being passed to
handlers expecting entity references.

### Extensibility

The handler architecture and modular design enable easy extension of functionality through new handlers, resolvers, and
evaluation phases.

### Performance

Multi-layered caching, compiled formulas, and efficient reference resolution provide high performance for complex sensor
configurations.

### Resilience

The system gracefully handles entity changes, configuration updates, and error conditions without requiring manual
intervention.

### Maintainability

Clear separation of concerns, well-defined interfaces, and comprehensive testing make the system easy to maintain and extend.

This architecture provides a robust foundation for synthetic sensor management in Home Assistant, enabling complex
calculations, cross-sensor dependencies, and seamless integration with the Home Assistant ecosystem.
