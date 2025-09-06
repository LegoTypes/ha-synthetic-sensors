# Formula Parsing Optimization: Parse-Once Architecture with Clean Modular Design

## Executive Summary

The current synthetic sensors system performs redundant formula parsing across multiple evaluation phases, leading to
significant performance overhead and architectural complexity. This document proposes a **Parse-Once Architecture** that
leverages existing AST caching infrastructure to eliminate redundant parsing and improve system performance by 70-80% **while
maintaining clean architectural boundaries and phase modularity**.

## Architectural Lessons Learned

Previous attempts at parse-once optimization violated clean architecture principles by:

- Bypassing the evaluation pipeline entirely
- Creating tight coupling between phases
- Breaking phase independence and testability
- Disrupting the main-formula-first execution order

This enhanced proposal addresses these issues by **enhancing phases with AST capabilities rather than bypassing them**.

## Current Problem Analysis

### Redundant Parsing Identified

The system currently parses the same formulas multiple times across different phases:

```python
# CURRENT INEFFICIENT FLOW
# Phase 1: Variable Resolution
variables = extract_variables("state + computed_var")  # ❌ AST Parse #1

# Phase 1: Computed Variable Discovery
computed_vars = extract_variables("metadata(state, 'last_changed')")  # ❌ AST Parse #2

# Phase 2: Dependency Management
dependencies = extract_dependencies("state + computed_var")  # ❌ AST Parse #3
dependencies = extract_dependencies("metadata(state, 'last_changed')")  # ❌ AST Parse #4

# Phase 3: Formula Execution
compiled = cache.get_compiled_formula("state + computed_var")  # ✅ AST Parse #5 (cached)
compiled = cache.get_compiled_formula("metadata(state, 'last_changed')")  # ✅ AST Parse #6 (cached)
```

**Result**: For a sensor with 1 main formula + 3 computed variables + 5 attributes, the system performs **54 parsing
operations** instead of **9**.

### Performance Impact

- **CPU Overhead**: 70-80% redundant parsing operations
- **Startup Time**: Significant delay during sensor initialization
- **Memory Usage**: Multiple AST representations of identical formulas
- **Debugging Complexity**: Parsing errors can occur in multiple phases
- **Testing Overhead**: Each parsing path requires separate test coverage

### Root Cause

Each evaluation phase implements its own parsing logic instead of leveraging the existing `FormulaCompilationCache`:

1. **Variable Resolution Phase**: Uses `formula_parsing/variable_extractor.py`
2. **Dependency Management Phase**: Uses `DependencyParser`
3. **Formula Execution Phase**: Uses `FormulaCompilationCache` ✅ (only this one is efficient)

## Core Architectural Principles to Maintain

1. **Phase Independence**: Each phase remains self-contained and testable
2. **Pipeline Flow**: Maintain the Pre-Evaluation → Variable Resolution → Main Evaluation → Post-Evaluation flow
3. **Execution Order**: Main formula first, then attributes (as shown in evaluation pipeline)
4. **Clean Interfaces**: Phases communicate only through well-defined interfaces
5. **Testability**: Each component can be tested in isolation

## Enhanced Solution: AST Analysis Service Architecture

### Core Principle

**Enhance each evaluation phase with AST-based analysis while preserving pipeline modularity and phase independence.**

### Architecture Overview

```text
graph TD
    A[YAML Import] --> B[Parse Formulas Once]
    B --> C[Store in FormulaCompilationCache]

    D[AST Analysis Service] --> C
    D --> E[Cached Formula Analysis]

    F[Pre-Evaluation Phase] --> D
    G[Variable Resolution Phase] --> D
    H[Dependency Management Phase] --> D
    I[Main Evaluation Phase] --> C
    J[Post-Evaluation Phase] --> K[Results]

    F --> G
    G --> H
    H --> I
    I --> J

    style D fill:#ffeb3b
    style C fill:#4caf50
    style E fill:#4caf50
```

### AST Analysis Service Design

Instead of bypassing phases, we introduce an **AST Analysis Service** that provides parsed data to phases without changing their
interfaces:

```python
class FormulaASTAnalysisService:
    """Service that provides AST-based analysis to evaluation phases.

    This service maintains the parse-once philosophy while preserving
    phase independence and clean architecture.
    """

    def __init__(self, compilation_cache: FormulaCompilationCache):
        self._compilation_cache = compilation_cache
        self._analysis_cache: dict[str, FormulaAnalysis] = {}

    def get_formula_analysis(self, formula: str) -> FormulaAnalysis:
        """Get comprehensive analysis for a formula (cached)."""
        if formula not in self._analysis_cache:
            # Parse once, analyze once, cache forever
            compiled = self._compilation_cache.get_compiled_formula(formula)
            self._analysis_cache[formula] = self._analyze_ast(compiled.parsed_ast)
        return self._analysis_cache[formula]

    def _analyze_ast(self, ast_node: ast.AST) -> FormulaAnalysis:
        """Extract all information from AST in one pass."""
        visitor = ComprehensiveASTVisitor()
        visitor.visit(ast_node)

        return FormulaAnalysis(
            variables=visitor.variables,
            entity_references=visitor.entity_references,
            dependencies=visitor.dependencies,
            metadata_calls=visitor.metadata_calls,
            collection_functions=visitor.collection_functions,
            cross_sensor_refs=visitor.cross_sensor_refs
        )

@dataclass
class FormulaAnalysis:
    """Complete analysis of a formula's AST."""
    variables: set[str]
    entity_references: set[str]
    dependencies: set[str]
    metadata_calls: list[tuple[str, str]]
    collection_functions: list[str]
    cross_sensor_refs: set[str]
```

## Incremental Migration Plan

### Phase 1: Infrastructure Without Disruption (Week 1-2)

**Goal**: Add AST analysis capability without changing existing code

```python
# 1. Create the AST Analysis Service
class FormulaASTAnalysisService:
    # Implementation above
    pass

# 2. Enhance existing phases with OPTIONAL AST analysis
class VariableResolutionPhase:
    def __init__(self, ast_analysis_service: FormulaASTAnalysisService | None = None):
        self._ast_service = ast_analysis_service
        # Keep existing extractor for backward compatibility
        self._legacy_extractor = FormulaVariableExtractor()

    def extract_variables(self, formula: str) -> set[str]:
        """Extract variables using AST service if available, fallback to legacy."""
        if self._ast_service:
            analysis = self._ast_service.get_formula_analysis(formula)
            return analysis.variables
        else:
            # Existing logic unchanged
            return self._legacy_extractor.extract_variables(formula)

# 3. Same pattern for other phases
class DependencyManagementPhase:
    def __init__(self, ast_analysis_service: FormulaASTAnalysisService | None = None):
        self._ast_service = ast_analysis_service
        self._legacy_parser = DependencyParser()

    def extract_dependencies(self, formula: str) -> set[str]:
        if self._ast_service:
            analysis = self._ast_service.get_formula_analysis(formula)
            return analysis.dependencies
        else:
            return self._legacy_parser.extract_dependencies(formula)
```

**Benefits**:

- Zero risk - existing code unchanged
- New service can be thoroughly tested in isolation
- Phases maintain their interfaces and responsibilities

### Phase 2: Gradual Phase Enhancement (Week 3-4)

**Goal**: Enable AST analysis in phases while maintaining pipeline flow

```python
# Enhanced evaluator that provides AST service to phases
class Evaluator:
    def __init__(self):
        # Create AST service
        self._ast_service = FormulaASTAnalysisService(self._compilation_cache)

        # Inject into phases (but keep them independent)
        self._pre_eval_phase = PreEvaluationPhase(ast_service=self._ast_service)
        self._var_resolution_phase = VariableResolutionPhase(ast_service=self._ast_service)
        self._dependency_phase = DependencyManagementPhase(ast_service=self._ast_service)
        self._main_eval_phase = MainEvaluationPhase()
        self._post_eval_phase = PostEvaluationPhase()

    async def evaluate_sensor(self, sensor_config: SensorConfig, context: EvaluationContext) -> EvaluationResult:
        """Maintain exact same pipeline flow with enhanced phases."""

        # SAME PIPELINE - just enhanced phases
        context = await self._pre_eval_phase.execute(sensor_config, context)
        context = await self._var_resolution_phase.execute(sensor_config, context)
        context = await self._dependency_phase.execute(sensor_config, context)

        # Main formula first (as per architecture)
        main_result = await self._main_eval_phase.evaluate_main_formula(sensor_config, context)
        context.set_main_result(main_result)

        # Then attributes (as per architecture)
        attribute_results = await self._main_eval_phase.evaluate_attributes(sensor_config, context)
        context.update_attributes(attribute_results)

        return await self._post_eval_phase.execute(sensor_config, context)
```

**Benefits**:

- Pipeline flow unchanged
- Execution order preserved (main first, then attributes)
- Each phase still testable independently
- Performance improvement without architectural disruption

### Phase 3: Cross-Sensor Dependency Enhancement (Week 5-6)

**Goal**: Fix the cross-sensor dependency issue using AST analysis

```python
class CrossSensorDependencyManager:
    def __init__(self, ast_analysis_service: FormulaASTAnalysisService):
        self._ast_service = ast_analysis_service

    def _is_valid_cross_sensor_reference(self, formula: str, sensor_name: str) -> bool:
        """Use AST analysis to properly detect cross-sensor references.

        This replaces the simplified regex-based implementation with proper
        AST parsing to distinguish between:
        - Variable names that happen to contain sensor names
        - Actual cross-sensor references
        - String literals containing sensor names
        """

        # Get comprehensive AST analysis
        analysis = self._ast_service.get_formula_analysis(formula)

        # Check if sensor_name appears as a variable reference (not in strings)
        return sensor_name in analysis.variables

    def extract_cross_sensor_dependencies(self, formula: str, available_sensors: set[str]) -> set[str]:
        """Extract cross-sensor dependencies using AST analysis."""

        analysis = self._ast_service.get_formula_analysis(formula)

        # Only variables that match available sensor names are cross-sensor deps
        return analysis.variables & available_sensors
```

**Benefits**:

- Solves the original problem (distinguishing variables from string literals)
- Uses proper AST parsing instead of fragile regex
- Maintains the existing interface

### Phase 4: Testing Strategy for Each Phase

```python
# Test AST service in isolation
def test_ast_analysis_service():
    """Test that AST service correctly analyzes formulas."""
    service = FormulaASTAnalysisService(compilation_cache)

    analysis = service.get_formula_analysis("state + computed_var")
    assert "state" in analysis.variables
    assert "computed_var" in analysis.variables

    # Test caching
    analysis2 = service.get_formula_analysis("state + computed_var")
    assert analysis is analysis2  # Same object (cached)

# Test phases with AST service
def test_variable_resolution_with_ast():
    """Test that variable resolution works with AST service."""
    ast_service = FormulaASTAnalysisService(compilation_cache)
    phase = VariableResolutionPhase(ast_service=ast_service)

    variables = phase.extract_variables("state + computed_var")
    assert variables == {"state", "computed_var"}

# Test phases without AST service (backward compatibility)
def test_variable_resolution_legacy():
    """Test that variable resolution still works without AST service."""
    phase = VariableResolutionPhase()  # No AST service

    variables = phase.extract_variables("state + computed_var")
    assert variables == {"state", "computed_var"}

# Test full pipeline integration
def test_pipeline_with_ast_enhancement():
    """Test that enhanced pipeline maintains same behavior."""
    evaluator = Evaluator()  # Uses AST service internally

    result = await evaluator.evaluate_sensor(sensor_config, context)

    # Same results as before, but faster
    assert result.main_value == expected_value
    assert result.attributes == expected_attributes
```

### Phase 5: Performance Validation (Week 7)

```python
def test_performance_improvement():
    """Validate that AST enhancement improves performance."""

    # Measure baseline (legacy)
    legacy_evaluator = Evaluator()  # Without AST service
    start_time = time.time()
    for _ in range(100):
        await legacy_evaluator.evaluate_sensor(sensor_config, context)
    legacy_time = time.time() - start_time

    # Measure enhanced
    enhanced_evaluator = Evaluator()  # With AST service
    start_time = time.time()
    for _ in range(100):
        await enhanced_evaluator.evaluate_sensor(sensor_config, context)
    enhanced_time = time.time() - start_time

    # Verify improvement
    improvement = (legacy_time - enhanced_time) / legacy_time
    assert improvement > 0.5  # At least 50% improvement
```

## Key Architectural Safeguards

### 1. Dependency Injection Pattern

```python
# Phases receive AST service via constructor, not global access
class VariableResolutionPhase:
    def __init__(self, ast_service: FormulaASTAnalysisService | None = None):
        self._ast_service = ast_service
```

### 2. Interface Preservation

```python
# Phase interfaces remain unchanged
class VariableResolutionPhase:
    def extract_variables(self, formula: str) -> set[str]:
        # Implementation enhanced, interface unchanged
        pass
```

### 3. Fallback Compatibility

```python
# Always maintain backward compatibility
def extract_variables(self, formula: str) -> set[str]:
    if self._ast_service:
        return self._ast_service.get_formula_analysis(formula).variables
    else:
        return self._legacy_extractor.extract_variables(formula)
```

### 4. Single Responsibility Maintenance

- **AST Service**: Only responsible for parsing and analysis
- **Variable Resolution Phase**: Only responsible for variable resolution
- **Dependency Phase**: Only responsible for dependency management
- **Evaluator**: Only responsible for orchestrating the pipeline

## Migration Validation Checklist

- [ ] Pipeline flow unchanged (Pre → Variable → Dependency → Main → Post)
- [ ] Execution order preserved (Main formula first, then attributes)
- [ ] Each phase testable in isolation
- [ ] Backward compatibility maintained
- [ ] Performance improvement measurable
- [ ] No tight coupling introduced
- [ ] Clean interfaces preserved
- [ ] Single responsibility principle maintained

## Legacy Implementation Strategy (Replaced by Enhanced Approach Above)

The sections below represent the original approach that violated clean architecture principles. They are preserved for reference
but should NOT be implemented.

### Original Phase 2: Runtime Evaluation Optimization (DEPRECATED)

**Location**: `Evaluator` and evaluation phases

```python
class OptimizedEvaluator:
    """Evaluator that uses pre-parsed formula analysis."""

    def __init__(self):
        self._sensor_analyses: dict[str, SensorAnalysisResult] = {}

    async def load_sensor_analysis(self, sensor_set_id: str) -> None:
        """Load pre-computed sensor analyses from storage."""
        self._sensor_analyses = await self._storage.load_sensor_analyses(sensor_set_id)

    async def evaluate_sensor(self, sensor_id: str, context: EvaluationContext) -> EvaluationResult:
        """Evaluate sensor using pre-parsed analysis."""

        analysis = self._sensor_analyses[sensor_id]

        # Use pre-computed evaluation order (no runtime dependency calculation)
        for formula_id in analysis.evaluation_order:

            if formula_id == "main":
                formula_analysis = analysis.main_formula
            elif formula_id in analysis.computed_variables:
                formula_analysis = analysis.computed_variables[formula_id]
            elif formula_id in analysis.attributes:
                formula_analysis = analysis.attributes[formula_id]

            # Variables already extracted during import
            variables_needed = formula_analysis.variables

            # Dependencies already extracted during import
            dependencies_needed = formula_analysis.dependencies

            # AST already compiled and cached
            compiled_formula = formula_analysis.compiled_ast

            # Only do resolution and execution (no parsing!)
            resolved_context = await self._resolve_variables(variables_needed, context)
            result = compiled_formula.evaluate(resolved_context)

            # Update context for next formula
            context[formula_id] = result

# Phase Integration
class VariableResolutionPhase:
    """Optimized variable resolution using pre-parsed analysis."""

    def resolve_variables(self, formula_analysis: FormulaAnalysisResult, context: EvaluationContext) -> EvaluationContext:
        """Resolve variables using pre-extracted variable list."""

        # No parsing needed - use pre-extracted variables
        variables_to_resolve = formula_analysis.variables

        for var_name in variables_to_resolve:
            # Resolve each variable (existing logic)
            resolved_value = self._resolve_single_variable(var_name, context)
            context[var_name] = resolved_value

        return context

class DependencyManagementPhase:
    """Optimized dependency management using pre-parsed analysis."""

    def extract_dependencies(self, formula_analysis: FormulaAnalysisResult) -> set[str]:
        """Get dependencies from pre-parsed analysis."""

        # No parsing needed - return pre-extracted dependencies
        return formula_analysis.dependencies
```

#### Phase 3: AST-Based Extraction Methods

**Location**: New `formula_parsing/ast_extractor.py`

```python
import ast
from typing import set

class FormulaASTExtractor(ast.NodeVisitor):
    """Extract information from parsed AST without re-parsing."""

    def __init__(self):
        self.variables: set[str] = set()
        self.entity_references: set[str] = set()
        self.function_calls: list[tuple[str, list[str]]] = []
        self.metadata_calls: list[tuple[str, str]] = []

    def visit_Name(self, node: ast.Name) -> None:
        """Extract variable names."""
        if isinstance(node.ctx, ast.Load):
            self.variables.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Extract entity.attribute patterns."""
        if isinstance(node.value, ast.Name):
            entity_ref = f"{node.value.id}.{node.attr}"
            if self._is_entity_id_pattern(entity_ref):
                self.entity_references.add(entity_ref)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Extract function calls including metadata()."""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id

            if func_name == "metadata" and len(node.args) >= 2:
                # Extract metadata(entity, 'attribute') calls
                entity_arg = self._extract_string_or_name(node.args[0])
                attr_arg = self._extract_string_literal(node.args[1])
                if entity_arg and attr_arg:
                    self.metadata_calls.append((entity_arg, attr_arg))

            # Extract all function calls
            args = [self._extract_string_or_name(arg) for arg in node.args]
            self.function_calls.append((func_name, args))

        self.generic_visit(node)

    def _is_entity_id_pattern(self, text: str) -> bool:
        """Check if text matches entity_id pattern."""
        return "." in text and not text.startswith("_")

    def _extract_string_or_name(self, node: ast.AST) -> str | None:
        """Extract string literal or variable name from AST node."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        elif isinstance(node, ast.Name):
            return node.id
        return None

    def _extract_string_literal(self, node: ast.AST) -> str | None:
        """Extract string literal from AST node."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

def extract_from_compiled_formula(compiled_formula: CompiledFormula) -> FormulaAnalysisData:
    """Extract all information from a compiled formula's AST."""

    extractor = FormulaASTExtractor()
    extractor.visit(compiled_formula.parsed_ast)

    return FormulaAnalysisData(
        variables=extractor.variables,
        entity_references=extractor.entity_references,
        function_calls=extractor.function_calls,
        metadata_calls=extractor.metadata_calls
    )
```

### Benefits of Parse-Once Architecture

#### Performance Improvements

- **70-80% Reduction** in parsing operations
- **Faster Startup**: All parsing done once during import
- **Lower CPU Usage**: Eliminate redundant AST generation
- **Better Memory Efficiency**: Single AST per unique formula

#### Development Benefits

- **Fail Fast**: Formula errors caught during YAML import, not runtime
- **Better Testing**: Single parsing path to test thoroughly
- **Easier Debugging**: Clear separation between parsing and evaluation
- **Simplified Architecture**: Eliminate redundant parsing logic across phases

#### Operational Benefits

- **Predictable Performance**: No runtime parsing overhead
- **Better Error Messages**: Formula errors reported with full context during import
- **Validation at Import**: Catch circular dependencies and syntax errors upfront
- **Atomic Operations**: Either all formulas parse successfully or import fails

### Migration Strategy

#### Phase 1: Infrastructure (Week 1-2)

1. **Create AST Extractor**: Implement `formula_parsing/ast_extractor.py`
2. **Extend FormulaAnalysisResult**: Add comprehensive formula analysis
3. **Update StorageManager**: Add formula analysis during import
4. **Create Storage Schema**: Store pre-computed analysis results

#### Phase 2: Evaluation Optimization (Week 3-4)

1. **Update VariableResolutionPhase**: Use pre-extracted variables
2. **Update DependencyManagementPhase**: Use pre-extracted dependencies
3. **Update Evaluator**: Load and use sensor analyses
4. **Maintain Backward Compatibility**: Fallback to current method if analysis missing

#### Phase 3: Cleanup (Week 5-6)

1. **Remove Redundant Parsing**: Clean up old parsing logic
2. **Update Tests**: Migrate tests to new architecture
3. **Performance Validation**: Measure and document improvements
4. **Documentation**: Update architecture docs

### Testing Strategy

#### Import-Time Testing

```python
def test_formula_analysis_during_import():
    """Test that all formulas are analyzed correctly during YAML import."""

    yaml_content = """
    sensors:
      test_sensor:
        formula: "state + computed_var"
        variables:
          computed_var:
            formula: "metadata(state, 'last_changed')"
        attributes:
          is_high:
            formula: "main_result > 100"
    """

    # Import should parse all formulas once
    result = await storage_manager.async_from_yaml(yaml_content, "test_set")

    # Verify analysis was created
    analysis = await storage_manager.load_sensor_analysis("test_sensor")

    assert "state" in analysis.main_formula.variables
    assert "computed_var" in analysis.main_formula.variables
    assert "state" in analysis.computed_variables["computed_var"].variables
    assert ("state", "last_changed") in analysis.computed_variables["computed_var"].metadata_calls

    # Verify dependency graph
    assert analysis.evaluation_order == ["computed_var", "main", "is_high"]

def test_formula_parsing_error_during_import():
    """Test that formula errors are caught during import, not runtime."""

    yaml_content = """
    sensors:
      bad_sensor:
        formula: "invalid syntax +"  # Syntax error
    """

    # Should fail during import
    with pytest.raises(ConfigurationError, match="Formula parsing failed"):
        await storage_manager.async_from_yaml(yaml_content, "test_set")

def test_circular_dependency_detection_during_import():
    """Test that circular dependencies are caught during import."""

    yaml_content = """
    sensors:
      circular_sensor:
        formula: "var_a + var_b"
        variables:
          var_a:
            formula: "var_b * 2"  # var_a depends on var_b
          var_b:
            formula: "var_a / 2"  # var_b depends on var_a (circular!)
    """

    # Should fail during import
    with pytest.raises(ConfigurationError, match="Circular dependency"):
        await storage_manager.async_from_yaml(yaml_content, "test_set")
```

#### Runtime Testing

```python
def test_runtime_uses_cached_ast():
    """Test that runtime evaluation uses cached AST without re-parsing."""

    # Mock the FormulaCompilationCache to track parse calls
    with patch('ha_synthetic_sensors.formula_compilation_cache.FormulaCompilationCache') as mock_cache:
        mock_compiled = Mock()
        mock_cache.get_compiled_formula.return_value = mock_compiled

        # Import sensor (should parse once)
        await storage_manager.async_from_yaml(yaml_content, "test_set")

        # Evaluate sensor multiple times
        for _ in range(5):
            await evaluator.evaluate_sensor("test_sensor", context)

        # Verify: Parse called only during import, not during evaluation
        assert mock_cache.get_compiled_formula.call_count == 3  # main + computed_var + attribute

        # Verify: No additional parsing during evaluation
        mock_cache.reset_mock()
        await evaluator.evaluate_sensor("test_sensor", context)
        assert mock_cache.get_compiled_formula.call_count == 0  # Uses cached analysis
```

### Performance Benchmarks

#### Before Optimization

```python
# Sensor with 1 main + 3 computed vars + 5 attributes = 9 formulas
# Current system: 9 formulas × 6 parsing operations each = 54 parse operations
# Parsing time: ~0.5ms per operation = 27ms total parsing time per evaluation
```

#### After Optimization

```python
# Same sensor configuration
# Parse-once system: 9 formulas × 1 parsing operation each = 9 parse operations (during import only)
# Runtime parsing time: 0ms (uses cached AST)
# Performance improvement: 100% elimination of runtime parsing overhead
```

### Risk Mitigation

#### Backward Compatibility

- **Gradual Migration**: New architecture runs alongside existing system
- **Fallback Logic**: If pre-computed analysis missing, fall back to current method
- **Feature Flags**: Enable/disable optimization per sensor set

#### Error Handling

- **Import Validation**: Comprehensive validation during YAML import
- **Graceful Degradation**: System continues working if analysis cache corrupted
- **Clear Error Messages**: Better error reporting with full context

#### Storage Considerations

- **Analysis Persistence**: Store pre-computed analysis in sensor set storage
- **Cache Invalidation**: Clear analysis when formulas change
- **Memory Management**: Limit analysis cache size to prevent memory bloat

## Conclusion

The Enhanced Parse-Once Architecture with Clean Modular Design represents a fundamental improvement to the synthetic sensors
system that:

1. **Eliminates 70-80% of redundant parsing operations**
2. **Improves startup performance significantly**
3. **Maintains clean architectural boundaries**
4. **Preserves phase independence and testability**
5. **Enables comprehensive testing of each component**
6. **Provides better error handling through proper AST analysis**

### Key Advantages Over Previous Attempts

- **Preserves Pipeline Flow**: Maintains the established Pre → Variable → Dependency → Main → Post evaluation flow
- **Maintains Execution Order**: Main formula evaluated first, then attributes (as per architectural requirements)
- **Zero Breaking Changes**: Existing interfaces preserved, backward compatibility maintained
- **Incremental Migration**: Each phase can be enhanced independently with full fallback support
- **Clean Separation**: AST service provides analysis without creating tight coupling between phases

### Success Criteria

This implementation will be considered successful when:

1. **Performance**: 50%+ reduction in parsing operations during evaluation
2. **Architecture**: All phases remain independently testable
3. **Compatibility**: Existing tests pass without modification
4. **Modularity**: Each component maintains single responsibility
5. **Cross-Sensor Dependencies**: Proper AST-based detection replaces fragile regex patterns

By enhancing phases with AST capabilities rather than bypassing them, we achieve substantial performance improvements while
maintaining the clean, modular architecture that makes the system maintainable and extensible.

The migration can be implemented incrementally with zero risk, allowing for thorough testing and validation at each step before
proceeding to the next phase.
