# Boolean False Evaluation Issue

## Problem Statement

Computed variables that evaluate to boolean `False` are being converted to `None` during the evaluation pipeline, causing
attributes to display as "Unknown" in the Home Assistant UI instead of showing the correct `False` value.

## The Real Issue (Not a Red Herring)

**This is NOT about `metadata()` returning `None`**. The `metadata()` function correctly returns valid values (dates, states,
etc.). The issue occurs in the subsequent formula evaluation and attribute storage pipeline.

## Observed Behavior

### Test Case

```yaml
sensors:
  test_boolean_issue:
    name: "Test Boolean Issue"
    formulas:
      - id: "main"
        formula: "True"
    variables:
      is_within_grace_period:
        formula: "metadata('sensor.span_panel_instant_power', 'last_changed') is not None"
    attributes:
      is_within_grace_period_value:
        formula: "is_within_grace_period"
```

### Expected vs Actual

- **Expected**: `is_within_grace_period_value: False` (when the formula evaluates to `False`)
- **Actual**: `is_within_grace_period_value: None` (shows as "Unknown" in HA UI)

## Root Cause Analysis

The issue occurs somewhere in the evaluation pipeline where:

1. **Computed Variable Resolution**: `is_within_grace_period` correctly evaluates to `False`
2. **Context Storage**: The `False` value should be stored in a `ReferenceValue` object
3. **Attribute Evaluation**: When `is_within_grace_period_value` formula runs, it should retrieve the `False` value
4. **Result Storage**: The `False` should be stored in `_attr_extra_state_attributes`

**The failure point**: Somewhere between steps 1-4, the `False` value is being lost or converted to `None`.

## Architecture Context

### Hierarchical Context System

We've implemented a bulletproof hierarchical context system with:

- `EvaluationContext` for layered scoping (global → sensor → attribute)
- `HierarchicalContextDict` to prevent silent type conversions
- `ReferenceValue` objects to preserve both values and their references
- Context integrity tracking with UUIDs and checksums

### Type Safety Measures

- All context parameters are now `HierarchicalContextDict` (not `dict | None`)
- Direct context assignments throw exceptions
- Context copying is prevented to maintain reference chains
- "Start fresh" anti-patterns have been eliminated

## Current Status

The context architecture is **bulletproof and type-safe**. The issue is now isolated to the **evaluation logic itself**, not
context management.

## Investigation Focus

The remaining investigation should focus on:

1. **Formula Evaluation**: Why does the formula evaluation return `None` instead of `False`?
2. **ReferenceValue Handling**: Are `False` values being properly wrapped in `ReferenceValue` objects?
3. **Attribute Resolution**: Is the attribute formula correctly retrieving the computed variable value?
4. **Result Processing**: Is the final result being incorrectly filtered or converted?

## Key Insight

This is a **data flow issue** in the evaluation pipeline, not a context management issue. The `metadata()` function works
correctly - the problem is in how boolean `False` results are processed through the formula evaluation and attribute storage
system.

## Test Isolation

The issue has been isolated to a minimal test case (`test_minimal_boolean_issue.py`) that reproduces the problem without the
complexity of the full SPAN integration, making it easier to debug the specific evaluation logic failure.
