# Entity Metadata Access Proposal

## Overview

This proposal introduces function-style syntax for accessing Home Assistant entity metadata in synthetic sensor formulas.
This extends the current dot notation system to provide collision-free access to built-in HA entity properties.

Use strict type checking. run linters/mypy after making code changes, tests should follow patterns in the datetime
integration tests

## Implementation Decision

**APPROVED: Function-Style Implementation**

After technical analysis, we will implement the `metadata()` function approach rather than bracket notation for the following
reasons:

- Leverages existing function infrastructure (similar to `now()`, `date()`)
- Faster and lower-risk implementation
- Clear semantic intent and validation
- Consistent with established patterns in the codebase

## Problem Statement

Home Assistant entities have built-in metadata (e.g., `last_changed`, `last_updated`, `entity_id`) that is fundamental to
entity state management. Currently, synthetic sensors can only access:

1. **Entity State Values**: Direct entity references (`sensor.temperature`)
2. **Custom Attributes**: Dot notation (`state.voltage`, `sensor.temp.humidity`)

However, there's no way to access HA's built-in entity metadata, which is needed for advanced use cases like:

- **Grace Period Logic**: `last_changed` for time-based availability decisions
- **Entity Introspection**: `entity_id`, `domain`, `object_id` for dynamic formulas
- **Update Tracking**: `last_updated` for freshness validation
- **State History**: Future metadata like `previous_state`, `state_duration`

## Current Limitation

```yaml
# ✅ Works - Entity state value
formula: "sensor.temperature"

# ✅ Works - Custom attributes
formula: "state.voltage"

# ❌ Doesn't work - HA metadata
formula: "state.last_changed"  # Validation error: undefined variable
```

## Approved Solution: Function-Style Access

Introduce **`metadata()` function** to access HA built-in entity metadata, complementing the existing dot notation for custom
attributes.

### Syntax Examples

```yaml
# Entity metadata access
formula: "metadata(state, 'last_changed')"          # When entity state last changed
formula: "metadata(sensor.temp, 'last_updated')"    # When entity was last updated
formula: "metadata(state, 'entity_id')"             # Full entity ID
formula: "metadata(sensor.power, 'domain')"         # Entity domain (sensor)
formula: "metadata(state, 'object_id')"             # Entity object ID

# Combined with existing patterns
formula: "state.voltage * metadata(sensor.current, 'last_changed')"  # Mix attributes and metadata
```

### Grace Period Use Case

```yaml
within_grace:
  formula: "time_diff_minutes < grace_period_minutes"
  variables:
    time_diff_minutes:
      formula: "minutes_between(metadata(state, 'last_changed'), now())"
    grace_period_minutes: 15
```

## Design Rationale

### 1. Collision Avoidance

**Problem**: Custom attributes could conflict with metadata names

```yaml
# Potential collision with dot notation
state.last_changed # HA metadata or custom attribute?
```

**Solution**: Function syntax provides separate namespace

```yaml
state.last_changed                  # Custom attribute (if exists)
metadata(state, 'last_changed')     # HA metadata (guaranteed)
```

### 2. Future Extensibility

HA metadata will grow over time. Bracket notation accommodates expansion:

**Current Metadata**:

- `last_changed` - When state value changed (datetime object for use with datetime functions)
- `last_updated` - When entity was updated (datetime object for use with datetime functions)
- `entity_id` - Full entity identifier
- `domain` - Entity domain (sensor, switch, etc.)
- `object_id` - Entity name part
- `friendly_name` - Display name

**Future Metadata**:

- `last_restored` - When entity was restored from state
- `reliability_score` - Entity reliability metric
- `update_frequency` - How often entity updates
- `previous_state` - Previous state value
- `state_duration` - How long in current state

### 3. Clear Semantic Distinction

| Syntax                    | Purpose           | Example                           | Collision Risk |
| ------------------------- | ----------------- | --------------------------------- | -------------- |
| `entity`                  | State value       | `sensor.temp`                     | None           |
| `entity.attr`             | Custom attributes | `state.voltage`                   | Low            |
| `metadata(entity, 'key')` | HA metadata       | `metadata(state, 'last_changed')` | **None**       |

## Implementation Considerations

### 1. Function Implementation

Implement `metadata()` function as a specialized handler that returns datetime objects for use with enhanced SimpleEval datetime functions:

```python
class MetadataHandler:
    """Specialized handler for entity metadata access."""
    
    def evaluate(self, formula: str, context: dict[str, ReferenceValue]) -> Any:
        """Handle metadata function calls with entity state resolution."""
        entity_ref, metadata_key = self._parse_metadata_call(formula)
        entity_value = self._resolve_entity_reference(entity_ref, context)
        
        if entity_value and hasattr(entity_value, 'hass_state'):
            hass_state = entity_value.hass_state
            
            # Return raw datetime objects for use with enhanced SimpleEval datetime functions
            # Enhanced SimpleEval has minutes_between(), hours_between(), etc.
            if metadata_key in ('last_changed', 'last_updated'):
                return getattr(hass_state, metadata_key, None)
                
            # Handle direct attribute access for other metadata
            return getattr(hass_state, metadata_key, None)
        return None
        
    def can_handle(self, formula: str) -> bool:
        """Check if formula contains metadata function calls."""
        return 'metadata(' in formula
```

### 2. Enhanced SimpleEval Integration

Metadata functions integrate with the enhanced SimpleEval routing system:

```python
class EnhancedFormulaRouter:
    """Router with fast-path detection for metadata calls."""
    
    def route_formula(self, formula: str) -> EvaluatorType:
        """Ultra-fast routing: metadata detection + enhanced SimpleEval."""
        
        # Step 1: Ultra-fast metadata scan (1% of cases)
        if 'metadata(' in formula:
            return EvaluatorType.METADATA
            
        # Step 2: Enhanced SimpleEval handles 99% of everything else
        return EvaluatorType.ENHANCED_SIMPLEEVAL

def validate_metadata_function(self, entity_ref: str, metadata_key: str):
    """Validate that metadata key exists in HA entity model."""
    valid_metadata = {
        'last_changed', 'last_updated', 'entity_id',
        'domain', 'object_id', 'friendly_name'
    }
    return metadata_key in valid_metadata
```

### 3. Error Handling

Provide clear error messages for invalid metadata access:

```yaml
# Invalid metadata key
formula: "metadata(state, 'invalid_key')"
# Error: "Unknown metadata key 'invalid_key'. Available: last_changed, last_updated, entity_id, domain, object_id, friendly_name"

# Entity doesn't exist
formula: "metadata(sensor.nonexistent, 'last_changed')"
# Error: "Entity 'sensor.nonexistent' not found"
```

### 4. Sensor Key Handling

**Critical Implementation Notes:**

#### State Resolution

When users reference raw sensor keys in YAML, ensure they are properly converted to `state` in metadata functions:

```yaml
# User writes sensor key in formula
my_sensor:
  formula: "metadata(my_sensor, 'last_changed')"  # Uses sensor key

# System converts to:
  formula: "metadata(state, 'last_changed')"      # Uses state token
```

#### Cross-Sensor Entity ID Updates

During HA registration phase, when entity_ids are finalized, ensure metadata function entity references are updated:

```yaml
# Initial configuration
other_sensor:
  formula: "metadata(temp_sensor, 'entity_id')"   # Uses sensor key reference

# After HA registration (entity_id becomes sensor.temp_12345)
other_sensor:
  formula: "metadata(sensor.temp_12345, 'entity_id')"  # Uses actual entity_id
```

**Implementation Requirements:**

- **Phase 1 (Pre-evaluation)**: Convert sensor key self-references to `state` token
- **Phase 2 (Post-registration)**: Update cross-sensor references with actual entity_ids from HA
- **Validation**: Ensure metadata functions work with both `state` token and explicit entity_ids

## Examples by Use Case

### 1. Grace Period Logic

```yaml
energy_sensor:
  formula: "state if within_grace else 'unavailable'"
  variables:
    within_grace:
      formula: "time_diff_minutes < grace_period_minutes"
    time_diff_minutes:
      formula: "minutes_between(metadata(state, 'last_changed'), now())"
    grace_period_minutes: 15
```

### 2. Entity Introspection

```yaml
dynamic_sensor:
  formula: "state * 2 if metadata(state, 'domain') == 'sensor' else state"
  attributes:
    source_entity:
      formula: "metadata(state, 'entity_id')"
    last_seen:
      formula: "metadata(state, 'last_updated')"
```

### 3. Freshness Validation

```yaml
validated_sensor:
  formula: "state if data_is_fresh else 'stale'"
  variables:
    data_is_fresh:
      formula: "age_minutes < max_age_minutes"
    age_minutes:
      formula: "minutes_between(metadata(state, 'last_updated'), now())"
    max_age_minutes: 30
```

### 4. Multi-Entity Metadata

```yaml
comparison_sensor:
  formula: "sensor.temp1 if temp_newer else sensor.temp2"
  variables:
    temp_newer:
      formula: "metadata(sensor.temp1, 'last_changed') > metadata(sensor.temp2, 'last_changed')"
```

### 5. Complete Grace Period Example

```yaml
sensors:
  power_with_grace:
    entity_id: sensor.span_panel_instantaneous_power
    formula: "state if is_fresh else 'stale'"
    variables:
      is_fresh:
        formula: "minutes_since_update < grace_period"
      minutes_since_update:
        formula: "minutes_between(metadata(state, 'last_updated'), now())"
      grace_period: 15
    attributes:
      last_update_time:
        formula: "format_friendly(metadata(state, 'last_updated'))"
      minutes_ago:
        formula: "minutes_since_update"
      status:
        formula: "'fresh' if is_fresh else 'stale'"
```

### 6. Business Day Calculations

```yaml
sensors:
  next_business_update:
    formula: "days_between(today(), next_update)"
    variables:
      next_update:
        formula: "add_business_days(metadata(state, 'last_changed'), 5)"
      is_business_day_now:
        formula: "is_business_day(today())"
    attributes:
      update_date:
        formula: "format_date(next_update)"
      business_day_check:
        formula: "is_business_day_now"
```

## Backward Compatibility

This proposal is **fully backward compatible**:

- Existing dot notation continues to work unchanged
- Function syntax is additive functionality
- No breaking changes to current formulas
- Gradual adoption possible

## Alternative Syntaxes Considered

### 1. Extended Dot Notation

```yaml
# Pros: Familiar syntax
# Cons: Collision risk with custom attributes
formula: "state.last_changed"
```

### 2. Bracket Notation (Original Proposal)

```yaml
# Pros: Clear distinction, familiar from other languages
# Cons: Complex parsing, ambiguous with array access
formula: "state['last_changed']"
```

### 3. Special Prefix

```yaml
# Pros: Clear metadata indication
# Cons: Less intuitive, adds complexity
formula: "state.__last_changed"
```

**Verdict**: Function-style provides the best balance of clarity, implementation simplicity, and consistency with existing
patterns.

## Implementation Priority

**Phase 1**: Core metadata access

- `last_changed`, `last_updated`, `entity_id`
- `metadata()` function implementation
- Sensor key to `state` token conversion
- Validation and error handling

**Phase 2**: Extended metadata and resolution

- `domain`, `object_id`, `friendly_name`
- Cross-sensor entity_id update after HA registration
- Complex metadata operations
- Performance optimizations

**Phase 3**: Future metadata

- `previous_state`, `state_duration` (when available in HA)
- Advanced introspection capabilities

## Conclusion

Function-style metadata access provides:

✅ **Collision-free** access to HA entity metadata
✅ **Future-proof** extensible syntax  
✅ **Clear semantics** distinguishing metadata from attributes
✅ **Backward compatibility** with existing formulas
✅ **Enhanced SimpleEval integration** with ultra-fast routing
✅ **Consistent patterns** with the enhanced handler architecture

This enhancement enables powerful new use cases like grace period logic while maintaining the simplicity and performance
of the enhanced synthetic sensor system. The metadata function integrates seamlessly with enhanced SimpleEval's native
conditional syntax (`x if condition else y`) and datetime operations.

**Key Implementation Notes:**

- Sensor key self-references must be converted to `state` token
- Cross-sensor entity_id references must be updated after HA registration  
- Metadata handler integrates with enhanced SimpleEval routing for optimal performance
- Function approach allows faster delivery with lower implementation risk
