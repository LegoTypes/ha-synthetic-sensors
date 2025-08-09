---
description: `Unify type conversion through a priority analyzer and generalize alternate state handlers to accept literals or formula objects; scope missing-state guard to referenced variables.`
globs:
alwaysApply: false
---

# Priority Type Analyzer adoption and generalized alternate state handlers

## Title

Priority Type Analyzer adoption and generalized alternate state handlers

### Rationale

- Stringly-typed inputs (e.g., globals like '15', alternates like 'false') currently rely on ad-hoc numeric-only coercions
  during Phase 3 substitution. Boolean-like strings are not uniformly coerced. This leads to type errors in comparisons and
  inconsistent behavior.
- Alternate state handlers (`UNAVAILABLE`/`UNKNOWN`) are treated as raw expression strings, forcing users to quote boolean
  values and preventing simple literal usage.
- A global missing-state guard in the evaluator short-circuits when any context entry is unknown/unavailable, even if
  unrelated to the current formula (affecting metadata-only computed variables like within_grace).

### Proposal

1. Use a single, priority type analyzer everywhere conversion is desired
   - Analyzer behavior: boolean-first (HA boolean strings and canonical true/false), then numeric; preserve HA state tokens
     (unknown/unavailable).
   - Apply analyzer at:
     - Core variable and dotted-entity substitution
     - Core Phase 3 context extraction (ReferenceValue.value)
     - Computed-variable alternate evaluation context
     - Evaluator result processing for string results

2. Generalize alternate state handlers
   - Accept either:
     - A literal (boolean/number/string) that is returned directly after analyzer typing; or
     - An object with `formula:` and optional `variables:` evaluated via the standard pipeline.
   - Maintain compatibility for existing string expressions (no breaking schema changes in 1.0; we extend with oneOf).

3. Scope the missing-state guard
   - Limit the Phase 3 missing-state short-circuit to variables actually referenced by the post-metadata resolved formula. Do
     not short-circuit based on unrelated context entries. If `state` appears only within `metadata(state, ...)`, it should
     not trigger the guard.

### Task List

- Priority analyzer adoption
  - Replace numeric-only coercions with the analyzer in:
    - `CoreFormulaEvaluator._substitute_values_in_formula`
    - `CoreFormulaEvaluator._extract_values_for_enhanced_evaluation`
    - `utils_config._extract_values_for_simpleeval`
    - `EvaluatorHelpers.process_evaluation_result` (string branch)

- Alternate handler generalization
  - Schema: allow `UNAVAILABLE`/`UNKNOWN` to be oneOf [string, number, boolean, object{formula, variables}]. Update at
    sensor, variable, and attribute levels as applicable.
  - Parsing: allow literal or object; keep string expressions unchanged. Store on `AlternateStateHandler` without forcing
    string type.
  - Evaluation: if literal → return analyzer(value); if object → evaluate via pipeline using its variables; if string →
    existing evaluation path.

- Missing-state guard scoping
  - In `CoreFormulaEvaluator.evaluate_formula`, compute referenced identifiers from post-metadata `resolved_formula` and pass
    to extraction; only guard for those.

- Tests/fixtures
  - Add unit tests for analyzer conversions (globals, variables, alternates) and for object-form alternates.
  - Add tests for metadata-only computed variable unaffected by unrelated unknowns.
  - Keep existing fixtures using string alternates unchanged; add new cases using booleans/literals.

- Documentation
  - Cookbook: document the two alternate handler forms and analyzer behavior.
  - within_grace guard doc: reference scoped guard and analyzer usage.

### Acceptance Criteria

- All existing tests remain green after updates; additional tests pass.
- Numeric and boolean-like strings are typed correctly in evaluation contexts.
- Alternate handlers accept literals or `{ formula, variables }` and work via pipeline.
- Missing-state guard only affects referenced variables.
