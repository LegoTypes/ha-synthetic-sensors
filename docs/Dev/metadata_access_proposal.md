# Entity Metadata Access Proposal

## Overview

This proposal introduces bracket notation syntax for accessing Home Assistant entity metadata in synthetic sensor formulas.
This extends the current dot notation system to provide collision-free access to built-in HA entity properties.

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

## Proposed Solution: Bracket Notation

Introduce **bracket notation** `entity["metadata_key"]` to access HA built-in entity metadata, complementing the existing dot
notation for custom attributes.

### Syntax Examples

```yaml
# Entity metadata access
formula: "state['last_changed']"                    # When entity state last changed
formula: "sensor.temp['last_updated']"              # When entity was last updated
formula: "state['entity_id']"                       # Full entity ID
formula: "sensor.power['domain']"                   # Entity domain (sensor)
formula: "state['object_id']"                       # Entity object ID

# Combined with existing patterns
formula: "state.voltage * sensor.current['last_changed']"  # Mix attributes and metadata
```

### Grace Period Use Case

```yaml
within_grace:
  formula: "((now() - state['last_changed']) / 60) < grace_period_minutes"
  variables:
    grace_period_minutes: 15
```

## Design Rationale

### 1. Collision Avoidance

**Problem**: Custom attributes could conflict with metadata names

```yaml
# Potential collision with dot notation
state.last_changed # HA metadata or custom attribute?
```

**Solution**: Bracket notation provides separate namespace

```yaml
state.last_changed     # Custom attribute (if exists)
state['last_changed']  # HA metadata (guaranteed)
```

### 2. Future Extensibility

HA metadata will grow over time. Bracket notation accommodates expansion:

**Current Metadata**:

- `last_changed` - When state value changed
- `last_updated` - When entity was updated
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

| Syntax           | Purpose           | Example                 | Collision Risk |
| ---------------- | ----------------- | ----------------------- | -------------- |
| `entity`         | State value       | `sensor.temp`           | None           |
| `entity.attr`    | Custom attributes | `state.voltage`         | Low            |
| `entity['meta']` | HA metadata       | `state['last_changed']` | **None**       |

## Implementation Considerations

### 1. Variable Resolution Extensions

Extend the existing variable resolver to handle bracket notation:

```python
# Current: state.voltage -> resolve attribute "voltage"
# New: state['last_changed'] -> resolve metadata "last_changed"

def resolve_metadata_reference(self, entity_ref: str, metadata_key: str):
    """Resolve entity metadata using HA state object."""
    # Access entity.last_changed, entity.last_updated, etc.
```

### 2. Validation Updates

Update formula validation to recognize bracket notation as valid references:

```python
# Pattern matching for metadata access
METADATA_PATTERN = re.compile(r"(\w+(?:\.\w+)*)\['([^']+)'\]")

def validate_metadata_reference(self, entity_ref: str, metadata_key: str):
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
formula: "state['invalid_key']"
# Error: "Unknown metadata key 'invalid_key'. Available: last_changed, last_updated, entity_id, domain, object_id, friendly_name"

# Entity doesn't exist
formula: "sensor.nonexistent['last_changed']"
# Error: "Entity 'sensor.nonexistent' not found"
```

## Examples by Use Case

### 1. Grace Period Logic

```yaml
energy_sensor:
  formula: "entity_id"
  UNAVAILABLE: "if(within_grace, state, UNAVAILABLE)"
  variables:
    within_grace:
      formula: "((now() - state['last_changed']) / 60) < grace_period_minutes"
      UNAVAILABLE: "false"
    grace_period_minutes: 15
```

### 2. Entity Introspection

```yaml
dynamic_sensor:
  formula: "if(state['domain'] == 'sensor', state * 2, state)"
  attributes:
    source_entity:
      formula: "state['entity_id']"
    last_seen:
      formula: "state['last_updated']"
```

### 3. Freshness Validation

```yaml
validated_sensor:
  formula: "if(data_is_fresh, state, 'stale')"
  variables:
    data_is_fresh:
      formula: "((now() - state['last_updated']) / 60) < max_age_minutes"
    max_age_minutes: 30
```

### 4. Multi-Entity Metadata

```yaml
comparison_sensor:
  formula: "if(temp_newer, sensor.temp1, sensor.temp2)"
  variables:
    temp_newer:
      formula: "sensor.temp1['last_changed'] > sensor.temp2['last_changed']"
```

## Backward Compatibility

This proposal is **fully backward compatible**:

- Existing dot notation continues to work unchanged
- Bracket notation is additive functionality
- No breaking changes to current formulas
- Gradual adoption possible

## Alternative Syntaxes Considered

### 1. Extended Dot Notation

```yaml
# Pros: Familiar syntax
# Cons: Collision risk with custom attributes
formula: "state.last_changed"
```

### 2. Function-Style Access

```yaml
# Pros: Clear function call semantics
# Cons: More verbose, inconsistent with attribute access
formula: "metadata(state, 'last_changed')"
```

### 3. Special Prefix

```yaml
# Pros: Clear metadata indication
# Cons: Less intuitive, adds complexity
formula: "state.__last_changed"
```

**Verdict**: Bracket notation provides the best balance of clarity, collision avoidance, and extensibility.

## Implementation Priority

**Phase 1**: Core metadata access

- `last_changed`, `last_updated`, `entity_id`
- Basic bracket notation parsing
- Validation and error handling

**Phase 2**: Extended metadata

- `domain`, `object_id`, `friendly_name`
- Complex metadata operations
- Performance optimizations

**Phase 3**: Future metadata

- `previous_state`, `state_duration` (when available in HA)
- Advanced introspection capabilities

## Conclusion

Bracket notation for metadata access provides:

✅ **Collision-free** access to HA entity metadata ✅ **Future-proof** extensible syntax ✅ **Clear semantics**
distinguishing metadata from attributes ✅ **Backward compatibility** with existing formulas ✅ **Intuitive syntax** familiar
from other languages

This enhancement enables powerful new use cases like grace period logic while maintaining the simplicity and clarity of the
current synthetic sensor system.
