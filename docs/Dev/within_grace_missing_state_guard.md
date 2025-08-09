---
description: `Document the cause of computed variables (like within_grace) evaluating to None due to a global missing-state short-circuit in the evaluator, and propose a targeted fix that only applies the guard to variables referenced by the current formula.`
globs:
alwaysApply: false
---

# Grace State Guard

## Title

Missing-state short-circuit causes computed variables like `within_grace` to evaluate to None

### Summary

- **Symptom**: Attribute formulas that reference a computed variable (e.g., `grace_period_active: formula: within_grace`)
  sometimes show `None`, even though `metadata(state, 'last_changed')` exists and `minutes_between(...) < N` should return a
  boolean.
- **Scope**: Any evaluation where the context contains entries whose raw value is `unknown` or `unavailable` while the
  current expression does not actually use those entries.
- **Impact**: Grace period attributes are intermittently `None` during startup/reload or transient unavailability of
  unrelated entities.

### Reproduction

1. Use YAML where a sensor defines:
   - `variables.within_grace.formula: minutes_between(metadata(state, 'last_changed'), now()) < energy_grace_period_minutes`
   - Attribute `grace_period_active: formula: within_grace`.
2. Observe after reload that `grace_period_active` may be `None` while the sensor’s `last_changed` clearly exists.

### Observations

- Developer Tools → Template confirms HA metadata is present:

  ```text
  {{ states(<entity_id>).last_changed }}
  {{ (now() - states(<entity_id>).last_changed).total_seconds() / 60 }}
  ```

  Both return valid values, so this is not a metadata failure.

### Root cause

- The evaluator applies a global guard that aborts evaluation if it finds any context entry with raw value equal to `unknown`
  or `unavailable` (case-insensitive), even if that entry is not referenced by the current formula.

Code reference:

ha-synthetic-sensors/src/ha_synthetic_sensors/core_formula_evaluator.py

```python
            # Check for missing state values that should trigger unavailable sensor
            missing_states = [STATE_UNKNOWN, STATE_UNAVAILABLE]

            for key, value in context.items():
                if isinstance(value, ReferenceValue):
                    raw_value = value.value
                    if isinstance(raw_value, str) and raw_value.lower() in missing_states:
                        _LOGGER.debug("Found missing state '%s' = '%s', sensor should become unavailable", key, raw_value)
                        return None
```

- During initialization, the current sensor’s own `state` or some unrelated dependency can briefly be `"unknown"`. That flag
  triggers the early return `None`, so the computed variable result becomes `None` before the expression is evaluated.
- The variable-level `UNAVAILABLE/UNKNOWN: 'false'` guards in YAML cannot help, because the evaluator exits before it
  evaluates the formula.

### Proposed solution

- Modify the missing-state guard to only consider variables actually referenced by the expression being evaluated. By
  convention, specialized handlers that consume entity references (e.g., `metadata(ref, ...)`) take the entity reference as
  their first parameter. Those reference parameters are not value-substituted and must not trigger the guard. This convention
  makes the guard future-proof for additional reference-consuming handlers.

Implementation outline:

- Extract the set of variable names referenced by the current `resolved_formula` (simple regex over identifiers, excluding
  function names), or reuse the dependency extractor for attribute/computed-variable contexts.
- In `_extract_values_for_enhanced_evaluation(...)`, check missing-state only for those referenced variables. Ignore
  unrelated context entries.
- Special-cases:
  - If the formula explicitly references `state`, then the guard remains in effect for `state`.
  - For the main sensor formula evaluation, keeping the current behavior is acceptable (if desired) because an unknown
    `state` should typically make the sensor unavailable.

Acceptance criteria:

- `within_grace` evaluates to a boolean immediately (no `None`) provided metadata and time functions are available,
  regardless of other context entries being `unknown`.
- The main sensor state still becomes `unavailable` when its own required inputs are missing.
- Unit tests cover cases where unrelated context entries are `unknown` while the formula does not reference them.

### Alternatives considered

- Keep current guard and document the startup `None`: rejected, produces confusing UI and breaks downstream logic.
- Add per-variable `UNAVAILABLE/UNKNOWN` overrides in YAML: ineffective when the evaluator aborts before evaluation.
- Switch to `metadata(state, 'last_updated')`: unrelated to the abort; metadata is already correct.

### Test plan (high level)

- Unit: Add tests that build a handler context with `state == "unknown"` but evaluate a formula that does not use `state`
  (e.g., `minutes_between(metadata(state, 'last_changed'), now()) < 30`). Expect a boolean result.
- Integration: Reload sensors and verify `grace_period_active` is boolean from the first evaluation cycle.

### Rollout notes

- Purely evaluator-internal change; no YAML changes required.
- No migration impact; metadata keys `last_changed`/`last_updated` remain supported.
