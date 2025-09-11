# HA Entity Reference Attribute Update Bug

## Problem Summary

**Issue**: Synthetic sensor attributes that reference Home Assistant entities (via entity ID) do not update when the referenced
HA entity's state changes. The attributes remain stuck at their initial values even when the underlying HA entity changes state.

**Impact**: This affects any synthetic sensor that uses HA entity references in attributes or variables, causing stale attribute
values that don't reflect current system state.

## Bug Description

### Expected Behavior

When a synthetic sensor has attributes that reference HA entities (e.g., `binary_sensor.panel_status`), those attributes should
automatically update when the referenced HA entity's state changes.

### Actual Behavior

Attributes that reference HA entities get evaluated once during initial setup but do not update when the referenced HA entity's
state changes. The attributes remain frozen at their initial values.

### Root Cause Analysis

The synthetic sensor system appears to only track changes to:

1. **Backing entities** (via data provider callbacks)
2. **Direct formula dependencies** in the main sensor state

However, it does **not** track changes to:

- HA entities referenced in **attributes**
- HA entities referenced in **variables** used by attributes

## Reproduction Test

### Test Case: `test_direct_entity_reference_in_attributes`

**Location**: `/tests/test_boolean_variable_debug.py`

**YAML Configuration**:

```yaml
sensors:
  panel_status_fallback_test:
    name: "Panel Status Fallback Test"
    entity_id: sensor.test_synthetic_sensor
    formula: state
    alternate_states:
      FALLBACK:
        formula: "42.0"
    variables:
      panel_status:
        formula: binary_sensor.virtual_panel_status_test
    attributes:
      debug_panel_status_is:
        formula: panel_status
      debug_panel_status_direct:
        formula: binary_sensor.virtual_panel_status_test
```

### Test Scenario

1. **Setup**: Create synthetic sensor with attributes referencing `binary_sensor.virtual_panel_status_test`
2. **Initial State**: Panel status = "on" → Attributes show `1.0` ✅
3. **State Change**: Panel status = "off" → Attributes should show `0.0` ❌
4. **Actual Result**: Attributes remain `1.0` (stale)

### Test Output Evidence

```
CRITICAL PANEL STATUS UPDATE TEST:
  Panel online (normal): 1.0     ✅ Correct
  Panel online (fallback): 1.0   ✅ Correct
  Panel offline (fallback): 1.0  ❌ Should be 0.0
  Panel back online (fallback): 1.0  ❌ Should reflect current state
```

**Key Evidence**: The panel status attribute stays at `1.0` even when the referenced `binary_sensor.virtual_panel_status_test`
changes from "on" → "off" → "on".

## Technical Details

### Data Provider Callback Behavior

- ✅ **Working**: Backing entity changes are detected via data provider callbacks
- ✅ **Working**: Main sensor state updates when backing entity changes
- ❌ **Broken**: Attribute formulas don't re-evaluate when HA entities change

### Change Detection Gap

The synthetic sensor system successfully detects:

- Changes to virtual backing entities (via `data_provider_callback`)
- Changes that affect the main sensor formula

But fails to detect:

- Changes to HA entities referenced in attribute formulas
- Changes to HA entities referenced in variable formulas used by attributes

## Impact Assessment

### Affected Use Cases

1. **Panel Status Monitoring**: Attributes showing panel connectivity status
2. **Device State Tracking**: Attributes referencing other integration sensors
3. **Cross-Integration Dependencies**: Attributes combining data from multiple integrations
4. **Conditional Logic**: Variables that depend on external HA entity states

### Real-World Example

In the SPAN Panel integration, synthetic sensors have attributes like:

```yaml
attributes:
  panel_status:
    formula: binary_sensor.span_panel_status
```

When the panel goes offline, `binary_sensor.span_panel_status` changes to "off", but the synthetic sensor's `panel_status`
attribute remains "on", providing incorrect status information to users.

## Proposed Solution Areas

### 1. HA Entity Change Tracking

The synthetic sensor system needs to:

- Identify all HA entity references in attribute formulas
- Subscribe to state changes for those entities
- Trigger attribute re-evaluation when referenced entities change

### 2. Variable Dependency Tracking

For variables used in attributes:

- Track HA entity dependencies in variable formulas
- Re-evaluate variables when their HA entity dependencies change
- Propagate variable updates to dependent attributes

### 3. Selective Update Optimization

Rather than re-evaluating all attributes:

- Track which attributes depend on which HA entities
- Only re-evaluate affected attributes when specific entities change
- Maintain performance while ensuring correctness

## Test Verification

The test `test_direct_entity_reference_in_attributes` provides a reliable reproduction case that:

1. ✅ Confirms the bug exists
2. ✅ Shows exactly which attributes are affected
3. ✅ Demonstrates the state change sequence
4. ✅ Provides clear pass/fail criteria for fixes

### Running the Test

```bash
python -m pytest tests/test_boolean_variable_debug.py::TestDirectEntityReferenceDebug::test_direct_entity_reference_in_attributes -v -s
```

### Expected Fix Validation

When fixed, the test should show:

```
CRITICAL PANEL STATUS UPDATE TEST:
  Panel online (normal): 1.0     ✅
  Panel online (fallback): 1.0   ✅
  Panel offline (fallback): 0.0  ✅ Fixed!
  Panel back online (fallback): 1.0  ✅ Fixed!
```

## Priority

**High Priority** - This bug affects core functionality of synthetic sensors that reference HA entities in attributes, leading
to incorrect and stale attribute values that can mislead users and break automations that depend on accurate sensor attributes.
