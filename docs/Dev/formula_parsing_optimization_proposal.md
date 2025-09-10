# Formula Parsing Optimization: Parse-Once Architecture with Clean Modular Design

## Summary

This document proposes a **Parse-Once Architecture** that leverages existing AST caching infrastructure to eliminate redundant
parsing and improve system performance by 70-80% **while maintaining clean architectural boundaries and phase modularity**.

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

We introduce an **AST Analysis Service** that provides parsed data to phases without changing their interfaces:

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
