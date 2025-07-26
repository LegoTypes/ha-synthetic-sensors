# Comparison Handler Design

## Overview

The condition parser in the synthetic sensors integration uses a handler-based architecture for performing type-specific
comparisons in collection patterns. This design provides extensibility while maintaining type safety and clear error
handling.

## Current Architecture

### Handler-Based Comparison System

The `ConditionParser` class delegates comparison operations to specialized handlers rather than using hardcoded type
checking. This approach provides:

- **Extensibility**: New comparison types can be added without modifying core logic
- **Type Safety**: Each handler validates its own input types
- **Clear Error Messages**: Specific warnings when no handler can process a comparison
- **Graceful Degradation**: System continues operating when comparisons can't be performed

### Current Implementation

```python
@staticmethod
def _dispatch_comparison(actual_val: Any, expected_val: Any, op: str) -> bool:
    """Dispatch comparison to appropriate handler based on types and operator."""

    # Handle equality operators (work with any type)
    if op in ("==", "!="):
        return bool(actual_val == expected_val) if op == "==" else bool(actual_val != expected_val)

    # Try to find a comparison handler
    handler = ConditionParser._get_comparison_handler(actual_val, expected_val, op)
    if handler:
        return handler.compare(actual_val, expected_val, op)

    # No handler found - log warning and return False
    _LOGGER.warning("No comparison handler found for types %s and %s with operator %s: %s %s %s",
                   type(actual_val).__name__, type(expected_val).__name__, op, actual_val, op, expected_val)
    return False
```

### Handler Interface

Each comparison handler implements two methods:

```python
class ComparisonHandler:
    def can_handle(self, actual_val: Any, expected_val: Any, op: str) -> bool:
        """Check if this handler can process the given types and operator."""

    def compare(self, actual_val: Any, expected_val: Any, op: str) -> bool:
        """Perform the comparison and return result."""
```

## Current Handlers

### NumericComparisonHandler

Handles numeric comparisons with operators: `<`, `>`, `<=`, `>=`

```python
class _NumericComparisonHandler:
    def can_handle(self, actual_val: Any, expected_val: Any, op: str) -> bool:
        return (isinstance(actual_val, (int, float)) and
               isinstance(expected_val, (int, float)) and
               op in ("<=", ">=", "<", ">"))

    def compare(self, actual_val: float, expected_val: float, op: str) -> bool:
        comparison_ops = {
            "<=": lambda a, e: a <= e,
            ">=": lambda a, e: a >= e,
            "<": lambda a, e: a < e,
            ">": lambda a, e: a > e,
        }
        return bool(comparison_ops[op](actual_val, expected_val))
```

## Recommendations for Extension

### 1. String Comparison Handler

Add support for string comparisons with lexicographic ordering:

```python
class _StringComparisonHandler:
    """Handler for string comparisons using lexicographic ordering."""

    def can_handle(self, actual_val: Any, expected_val: Any, op: str) -> bool:
        return (isinstance(actual_val, str) and
               isinstance(expected_val, str) and
               op in ("<=", ">=", "<", ">"))

    def compare(self, actual_val: str, expected_val: str, op: str) -> bool:
        comparison_ops = {
            "<=": lambda a, e: a <= e,
            ">=": lambda a, e: a >= e,
            "<": lambda a, e: a < e,
            ">": lambda a, e: a > e,
        }
        return bool(comparison_ops[op](actual_val, expected_val))
```

**Use Cases:**

Add support for boolean comparisons with logical ordering:

```python
class _BooleanComparisonHandler:
    """Handler for boolean comparisons where False < True."""

    def can_handle(self, actual_val: Any, expected_val: Any, op: str) -> bool:
        return (isinstance(actual_val, bool) and
               isinstance(expected_val, bool) and
               op in ("<=", ">=", "<", ">"))

    def compare(self, actual_val: bool, expected_val: bool, op: str) -> bool:
        # Convert to int for comparison (False=0, True=1)
        a_val = int(actual_val)
        e_val = int(expected_val)

        comparison_ops = {
            "<=": lambda a, e: a <= e,
            ">=": lambda a, e: a >= e,
            "<": lambda a, e: a < e,
            ">": lambda a, e: a > e,
        }
        return bool(comparison_ops[op](a_val, e_val))
```

**Use Cases:**

### 3. DateTime Comparison Handler

```python

    def can_handle(self, actual_val: Any, expected_val: Any, op: str) -> bool:
        from datetime import datetime
        return (self._is_datetime_like(actual_val) and
               self._is_datetime_like(expected_val) and
               op in ("<=", ">=", "<", ">"))

    def _is_datetime_like(self, value: Any) -> bool:
        """Check if value can be converted to datetime."""
        from datetime import datetime
        if isinstance(value, datetime):
            return True
        if isinstance(value, str):
            try:
                datetime.fromisoformat(value.replace('Z', '+00:00'))
                return True
            except ValueError:
                return False
        return False

    def compare(self, actual_val: Any, expected_val: Any, op: str) -> bool:
        from datetime import datetime

        # Convert to datetime objects
        actual_dt = self._to_datetime(actual_val)
        expected_dt = self._to_datetime(expected_val)

        comparison_ops = {
            "<=": lambda a, e: a <= e,
            ">=": lambda a, e: a >= e,
            "<": lambda a, e: a < e,
            ">": lambda a, e: a > e,
        }
        return bool(comparison_ops[op](actual_dt, expected_dt))

    def _to_datetime(self, value: Any) -> datetime:
        """Convert value to datetime object."""
        from datetime import datetime
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace('Z', '+00:00'))

        raise ValueError(f"Cannot convert {value} to datetime")
```

**Use Cases:**

- Time-based filtering: `"attribute:last_seen>='2024-01-01T00:00:00Z'"`
- Age-based filtering: `"state:updated_at>=yesterday"`

### 4. Version Comparison Handler

Add support for semantic version comparisons:

```python
class \_VersionComparisonHandler: """Handler for semantic version comparisons."""

    def can_handle(self, actual_val: Any, expected_val: Any, op: str) -> bool:
               self._is_version_like(expected_val) and
               op in ("<=", ">=", "<", ">"))

    def _is_version_like(self, value: Any) -> bool:
        """Check if value looks like a version string."""
        if not isinstance(value, str):
            return False
        import re
        # Match semantic version pattern (x.y.z)
        return bool(re.match(r'^\d+\.\d+\.\d+', value))

    def compare(self, actual_val: str, expected_val: str, op: str) -> bool:
        """Compare semantic versions."""
        actual_parts = self._parse_version(actual_val)
        expected_parts = self._parse_version(expected_val)

        comparison_ops = {
            "<=": lambda a, e: a <= e,
            ">=": lambda a, e: a >= e,
            "<": lambda a, e: a < e,
            ">": lambda a, e: a > e,
        }
        return bool(comparison_ops[op](actual_parts, expected_parts))

    def _parse_version(self, version: str) -> tuple[int, ...]:
        """Parse version string into comparable tuple."""
        import re

        # Extract numeric parts
        parts = re.findall(r'\d+', version)
        return tuple(int(part) for part in parts)

```

**Use Cases:**

- Firmware filtering: `"attribute:firmware_version>='2.1.0'"`
- Software compatibility: `"attribute:app_version<'3.0.0'"`

## Handler Registration System

### Recommended Enhancement

Implement a registration system to allow dynamic handler addition:

```python
class ConditionParser:
    _comparison_handlers: list[ComparisonHandler] = []

    @classmethod
    def register_comparison_handler(cls, handler: ComparisonHandler) -> None:
        """Register a new comparison handler."""
        cls._comparison_handlers.append(handler)
        # Sort by priority if handlers have priority attribute
        if hasattr(handler, 'priority'):
            cls._comparison_handlers.sort(key=lambda h: getattr(h, 'priority', 0), reverse=True)

    @classmethod
    def _get_comparison_handlers(cls) -> list[ComparisonHandler]:
        """Get all registered comparison handlers."""
        if not cls._comparison_handlers:
            # Register default handlers
            cls.register_comparison_handler(cls._NumericComparisonHandler())
            cls.register_comparison_handler(cls._StringComparisonHandler())
            cls.register_comparison_handler(cls._BooleanComparisonHandler())
            # Add more as needed

        return cls._comparison_handlers
```

### Handler Priority

Implement priority-based handler selection:

```python
class _NumericComparisonHandler:
    priority = 100  # High priority for exact type matches

class _StringComparisonHandler:
    priority = 90   # Lower priority for string comparisons

class _FallbackComparisonHandler:
    priority = 1    # Lowest priority - converts everything to strings
```

## Testing Strategy

### Unit Tests for Each Handler

```python
def test_numeric_comparison_handler():
    handler = ConditionParser._NumericComparisonHandler()

    # Test can_handle
    assert handler.can_handle(5, 10, ">")
    assert not handler.can_handle("5", "10", ">")  # Should reject strings
    assert not handler.can_handle(5, 10, "==")     # Should reject equality

    # Test compare
    assert handler.compare(10, 5, ">") == True
    assert handler.compare(5, 10, ">") == False
    assert handler.compare(5, 5, ">=") == True

def test_string_comparison_handler():
    handler = ConditionParser._StringComparisonHandler()

    # Test can_handle
    assert handler.can_handle("apple", "banana", ">")
    assert not handler.can_handle(5, 10, ">")  # Should reject numbers

    # Test compare - lexicographic ordering
    assert handler.compare("banana", "apple", ">") == True
    assert handler.compare("apple", "banana", ">") == False
```

### Integration Tests

```python
def test_collection_with_string_comparisons():
    """Test collection patterns with string state comparisons."""
    # Test: count("state:>='active'")
    # Should include states: "active", "on", "running"
    # Should exclude states: "inactive", "off", "idle"
    pass

def test_mixed_type_comparisons():
    """Test that mixed types gracefully fall back."""

    # Test: comparing number to string should log warning and return False
    result = ConditionParser.compare_values(5, ">", "apple")
    assert result == False  # No handler can process this
```

## Migration Strategy

### Phase 1: Add Handler Infrastructure ✅

- [x] Implement handler-based dispatch system

### Phase 2: Add Basic Handlers

- [ ] Implement string comparison handler

- [ ] Implement datetime comparison handler
- [ ] Add handler registration system

- [ ] Performance optimization

```text
sensors: high_power_devices:

sensors:

    formula: count("attribute:last_seen>='2024-01-01T00:00:00Z'")  # DateTime

compatible_firmware: formula: count("attribute:firmware_version>='2.1.0'") # Version comparison formula:
count("attribute:enabled>=True") # Boolean comparison
```

## Benefits

**Maintainability**: Clear separation of concerns **Performance**: Handler selection is efficient **Future-Proof**:
Architecture supports complex comparison logic

## Conclusion
