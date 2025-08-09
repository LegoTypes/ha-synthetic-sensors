# Computed Variable Validation Fix

## Overview

This document describes a critical bug fix for computed variable validation during YAML parsing that was causing synthetic
sensor configuration generation to fail on fresh installations.

## Problem Description

### Symptoms

- Runtime error during synthetic sensor setup: `Computed variable validation failed`
- Nearly empty YAML export files on fresh installations
- Error message:
  `Computed variable 'within_grace' references undefined variables: ['minutes', 'energy_grace_period_minutes']`

### Root Cause

The issue occurred in the validation phase during YAML parsing in `ConfigManager.load_from_yaml()`. Two separate problems
were causing validation failures:

1. **Missing Global Variables**: The `validate_computed_variable_references()` function was not receiving global variables
   during validation
2. **Missing Built-in Functions**: Duration and datetime functions (like `minutes()`, `hours()`) were not recognized as valid
   during validation

### Impact

This bug prevented the SPAN panel integration from successfully generating synthetic sensor configurations on fresh
installations, resulting in empty or incomplete YAML exports.

## Technical Details

### Validation Flow

```text
ConfigManager.load_from_yaml()
├── _parse_yaml_config()
│   ├── _parse_sensor_config()
│   │   └── _parse_single_formula()
│   │       └── validate_computed_variable_references() ❌ Missing global vars
│   └── _parse_attribute_formula()
│       └── validate_computed_variable_references() ❌ Missing global vars
```

### Example Failing Configuration

```yaml
global_settings:
  device_identifier: span_span-sim-001
  variables:
    energy_grace_period_minutes: "30"

sensors:
  span_span-sim-001_main_meter_produced_energy:
    formula: "state + 0"
    variables:
      within_grace:
        formula: "((now() - metadata(state, 'last_changed')) / minutes(1)) < energy_grace_period_minutes"
        UNAVAILABLE: "false"
```

The validation would fail because:

- `energy_grace_period_minutes` wasn't recognized (missing global variables)
- `minutes` wasn't recognized (missing duration functions)

## Solution

### Fix 1: Global Variables Passing

**Modified Files**: `src/ha_synthetic_sensors/config_manager.py`

#### Changes to `_parse_single_formula()`

**Before**:

```python
def _parse_single_formula(self, sensor_key: str, sensor_data: SensorConfigDict) -> FormulaConfig:
    # ...
    validation_errors = validate_computed_variable_references(variables, sensor_key)
```

**After**:

```python
def _parse_single_formula(self, sensor_key: str,
                          sensor_data: SensorConfigDict,
                          global_settings: GlobalSettingsDict | None = None) -> FormulaConfig:
    # ...
    global_variables = (global_settings or {}).get("variables", {})
    validation_errors = validate_computed_variable_references(variables, sensor_key, global_variables)
```

#### Changes to `_parse_attribute_formula()`

**Before**:

```python
global_variables = self._config.global_settings.get("variables", {}) if self._config else {}
```

**After**:

```python
global_variables = (global_settings or {}).get("variables", {})
```

#### Updated Call Site

**Before**:

```python
formula = self._parse_single_formula(sensor_key, sensor_data)
```

**After**:

```python
formula = self._parse_single_formula(sensor_key, sensor_data, global_settings)
```

### Fix 2: Built-in Functions Recognition

**Modified Files**: `src/ha_synthetic_sensors/utils_config.py`

#### Added Missing Imports

**Before**:

```python
from .shared_constants import METADATA_FUNCTIONS
```

**After**:

```python
from .shared_constants import METADATA_FUNCTIONS, DURATION_FUNCTIONS, DATETIME_FUNCTIONS
```

#### Updated Always Available Variables

**Before**:

```python
always_available = {"state", "now", "today", "yesterday"}
always_available.update(METADATA_FUNCTIONS)
available_vars.update(always_available)
```

**After**:

```python
always_available = {"state", "now", "today", "yesterday"}
always_available.update(METADATA_FUNCTIONS)   # Add metadata functions
always_available.update(DURATION_FUNCTIONS)   # Add duration functions
always_available.update(DATETIME_FUNCTIONS)   # Add datetime functions
available_vars.update(always_available)
```

This ensures functions like `minutes()`, `hours()`, `days()`, `now()`, etc. are recognized during validation.

## Verification

### Test Coverage

The fix was verified through:

1. **Existing Tests**: All computed variable validation tests continue to pass
2. **Integration Tests**: SPAN panel grace period integration tests pass
3. **Manual Testing**: YAML parsing now works with complex synthetic sensor configurations

### Test Example

```python
# This now works without validation errors
test_yaml = """
version: '1.0'
global_settings:
  device_identifier: span_span-sim-001
  variables:
    energy_grace_period_minutes: "30"

sensors:
  test_sensor:
    formula: "state + 0"
    variables:
      within_grace:
        formula: "((now() - metadata(state, 'last_changed')) / minutes(1)) < energy_grace_period_minutes"
"""

config = ConfigManager(hass).load_from_yaml(test_yaml)  # ✅ Success
```

## Prevention

### Code Review Checklist

When modifying validation logic:

- [ ] Ensure global variables are passed to validation functions
- [ ] Verify all built-in function types are included in always-available variables
- [ ] Test with realistic YAML configurations that use global variables
- [ ] Run integration tests that exercise the full YAML generation pipeline

### Future Considerations

- Consider adding automated tests that verify validation works with all supported built-in functions
- Monitor for similar issues when adding new function types or variable scoping features

## Related Files

- `src/ha_synthetic_sensors/config_manager.py` - Main configuration parsing logic
- `src/ha_synthetic_sensors/utils_config.py` - Validation utilities
- `src/ha_synthetic_sensors/shared_constants.py` - Built-in function definitions
- `tests/date_time/test_computed_variables_validation.py` - Validation test coverage

## Git Commits

The fix was implemented across two main changes:

1. Updated global variable passing in config manager
2. Added duration and datetime functions to validation scope

Both changes maintain backward compatibility and don't affect existing functionality.
