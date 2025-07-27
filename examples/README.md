# Examples

This directory contains examples demonstrating how to extend and use the HA Synthetic Sensors comparison system.

## Custom Comparison Types

### `custom_comparison_type.py`

This example shows how to create your own custom comparison types using the extensible protocol-based architecture:

1. **IPAddressComparisonType** - A handler for IP address comparisons that supports:
   - Basic equality (`==`, `!=`)
   - Subnet membership checks (`in`, `not in`)
   - IP address validation and parsing

2. **ColorComparisonType** - A handler for color value comparisons that supports:
   - Named colors (`"red"`, `"blue"`, etc.)
   - Hex colors (`"#FF0000"`, `"#00FF00"`, etc.)
   - Color normalization and equality checking

### How to Create Custom Comparison Types

To create your own comparison type, implement these methods:

```python
class MyCustomType:
    def get_type_info(self) -> ComparisonTypeInfo:
        """Return type information including priority and supported operators."""

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Check if this handler can compare these raw values."""

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Perform the actual comparison."""

    def can_handle_user_type(self, value: OperandType, metadata: dict[str, any]) -> bool:
        """Optional: Handle user-defined types with metadata."""
```

### Key Concepts

- **Priority**: Lower numbers = higher priority. Your custom types can override built-in behavior by using priorities < 10.
- **TypedDict**: The `ComparisonTypeInfo` uses TypedDict to ensure type safety and extensibility.
- **Protocol-based**: Uses Python protocols for clean, extensible interfaces.
- **User Types**: Can handle both raw values and user-defined types with metadata.

### Running the Example

```bash
# From the project root
poetry run python examples/custom_comparison_type.py
```

This will demonstrate all the custom comparison types in action and show the handler priority order.

### `using_typed_conditions.py`

This example demonstrates the TypedDict-based condition parsing system. It shows how:

- **ParsedCondition** and **ParsedAttributeCondition** provide structured, type-safe condition representations
- **Any comparison type** (built-in or user-defined) can be represented with the same structure
- **JSON serialization** works seamlessly with TypedDict structures
- **Manual condition creation** is possible using the TypedDict interface

```bash
# From the project root
poetry run python examples/using_typed_conditions.py
```

## Architecture Benefits

The new extensible system provides:

1. **Type Safety**: Uses TypedDict and protocols for compile-time type checking
2. **Priority System**: Automatic handler ordering based on priority values
3. **User Extensions**: Easy registration of custom comparison logic
4. **Clean Interface**: Protocol-based design for consistent behavior
5. **Backward Compatibility**: All existing comparisons continue to work

## Integration with Home Assistant

Custom comparison types can be particularly useful for:

- Device-specific value formats (IP addresses, MAC addresses, etc.)
- Custom sensor data types (colors, coordinates, etc.)
- Domain-specific comparisons (chemical formulas, units, etc.)
- Complex state matching for automations
