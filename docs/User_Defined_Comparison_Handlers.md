# User-Defined Comparison Handlers

The synthetic sensors library includes an **extensible comparison handler architecture** that allows users to define custom
comparison logic for specialized data types. This enables advanced pattern matching in collection functions and condition
evaluation.

## Overview

The comparison system supports both built-in types (numeric, string, boolean, datetime, version) and **user-defined types**
through a plugin architecture. User handlers can:

- **Define custom data types** with specialized comparison logic
- **Handle unit conversions** (e.g., energy values with different units)
- **Implement domain-specific comparisons** (e.g., IP addresses, version strings)
- **Override built-in behavior** for specific use cases
- **Integrate with collection patterns** for advanced entity filtering

## Architecture Components

**Base Handler**: `BaseComparisonHandler` provides the foundation for custom handlers **Extensible Registry**: Global registry
manages handler registration and priority **Factory Pattern**: `ComparisonFactory` selects appropriate handlers for each
comparison **Metadata-Driven**: Handlers provide type information for automatic discovery

## Creating a Custom Comparison Handler

### 1. Define Your Handler Class

```python
from ha_synthetic_sensors.comparison_handlers import BaseComparisonHandler
from ha_synthetic_sensors.comparison_handlers.comparison_protocol import ComparisonTypeInfo
from ha_synthetic_sensors.constants_types import TypeCategory
from ha_synthetic_sensors.type_analyzer import OperandType

class EnergyComparisonHandler(BaseComparisonHandler):
    """Custom handler for energy value comparisons with unit conversion."""

    def get_supported_types(self) -> set[TypeCategory]:
        """Get supported type categories."""
        return {TypeCategory.STRING}  # Handle energy strings

    def get_supported_operators(self) -> set[str]:
        """Get supported operators."""
        return {"==", "!=", "<", "<=", ">", ">="}

    def get_type_info(self) -> ComparisonTypeInfo:
        """Get type information for this comparison handler."""
        return ComparisonTypeInfo(
            type_name="energy",
            priority=5,  # Higher priority than built-in handlers
            supported_operators=self.get_supported_operators(),
            can_handle_user_types=True,
        )

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Check if this handler can process the given raw operands.

        This is the CRITICAL method that determines handler selection.
        The first handler that returns True for this method wins the comparison.
        """
        if op not in self.get_supported_operators():
            return False

        # Handle energy strings (e.g., "50W", "2kW")
        if isinstance(left_raw, str) and isinstance(right_raw, str):
            try:
                self._parse_energy_string(left_raw)  # Try to parse as energy
                self._parse_energy_string(right_raw)
                return True  # "Yes, I can handle this comparison!"
            except ValueError:
                return False  # "No, this isn't valid energy data"

        return False

    def _parse_energy_string(self, energy_str: str) -> float:
        """Parse energy string like '50W' or '2kW' into watts."""
        energy_str = energy_str.strip()
        if energy_str.endswith("kW"):
            return float(energy_str[:-2]) * 1000
        if energy_str.endswith("mW"):
            return float(energy_str[:-2]) / 1000
        if energy_str.endswith("W"):
            return float(energy_str[:-1])
        raise ValueError(f"Invalid energy string: {energy_str}")

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Compare raw energy values directly."""
        if not self.can_handle_raw(left_raw, right_raw, op):
            return False

        try:
            # Convert both to watts for comparison
            left_watts = self._parse_energy_string(left_raw)
            right_watts = self._parse_energy_string(right_raw)

            return self._apply_operator(left_watts, right_watts, op)

        except (ValueError, TypeError):
            return False

    def _compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform the actual comparison after type validation."""
        return self.compare_raw(actual_val, expected_val, op)
```

### 2. Register Your Handler

```python
from ha_synthetic_sensors.comparison_handlers import register_user_comparison_handler

# Register your custom handler
energy_handler = EnergyComparisonHandler()
register_user_comparison_handler(energy_handler)
```

### 3. Use in Collection Patterns

Once registered, your handler automatically integrates with collection patterns:

```yaml
sensors:
  high_power_devices:
    name: "High Power Devices"
    formula: count("attribute:power_consumption>=1kW")
    metadata:
      unit_of_measurement: "count"
      device_class: "energy"

  efficient_devices:
    name: "Efficient Devices"
    formula: count("state:<500W")
    metadata:
      unit_of_measurement: "count"
      device_class: "energy"
```

**Key Features:**

- **Unit-Aware Comparisons**: `"2kW" >= "1500W"` correctly evaluates to `True` (2000W >= 1500W)
- **Cross-Unit Support**: Handles mixed units like `"1.5kW" < "2000W"`
- **Error Handling**: Gracefully handles invalid energy strings
- **Priority System**: User handlers take precedence over built-in handlers

## Handler Selection and Priority System

The package uses a sophisticated **handler selection mechanism** to determine which handler processes each comparison.
Understanding this system is crucial for designing effective custom handlers.

### Priority-Based Selection Process

**Handler Selection Algorithm:**

1. **Priority Ordering**: Handlers are stored in a global registry sorted by priority (lower numbers = higher priority)
2. **Sequential Check**: For each comparison, handlers are checked in priority order
3. **First-Match-Wins**: The first handler that says "I can handle this" processes the comparison
4. **Fallback Behavior**: If no user handler can handle the comparison, built-in handlers take over

**Selection Flow:**

```python
def find_handler(left_raw, right_raw, op):
    """Simplified handler selection algorithm."""
    for handler in self._handlers:  # Iterate in priority order
        if handler.can_handle_raw(left_raw, right_raw, op):
            return handler  # First handler that can handle it wins
    return None  # Fall back to built-in handlers
```

### Priority Ranges and Guidelines

**Recommended Priority Ranges:**

| Priority Range | Handler Type                 | Example Use Cases                            | Built-in Priority |
| -------------- | ---------------------------- | -------------------------------------------- | ----------------- |
| **1-10**       | **Critical Domain Handlers** | Energy, temperature, currency, time zones    | N/A               |
| **11-25**      | **Specialized Data Types**   | IP addresses, version strings, file paths    | N/A               |
| **26-49**      | **Custom Business Logic**    | Device-specific formats, proprietary data    | N/A               |
| **50+**        | **Built-in Handlers**        | String, numeric, boolean (default fallbacks) | 50+               |

**Quick Reference:**

- **Priority 1-5**: Most critical handlers (energy, temperature)
- **Priority 6-10**: Important domain handlers (currency, time zones)
- **Priority 11-25**: Specialized data types (IP, versions, paths)
- **Priority 26-49**: Custom business logic (device-specific)
- **Priority 50+**: Built-in fallbacks (string=50, numeric=50, boolean=50)

**Priority Guidelines:**

- **Lower numbers = Higher precedence** (1 is highest priority)
- **User handlers typically use 1-49** to override built-in behavior
- **Built-in handlers use 50+** to provide fallback behavior
- **Conflicting handlers**: Lower priority number wins

### Handler Selection Examples

**Example 1: Energy vs String Handler**

```python
# Registered handlers (in priority order):
# 1. EnergyComparisonHandler(priority=5)
# 2. StringComparisonHandler(priority=50)

# Input: compare("2kW", "1500W", ">=")
#
# EnergyComparisonHandler.can_handle_raw("2kW", "1500W", ">=")
# → Tries to parse as energy → Success → Returns True
#
# Result: Energy handler processes with unit conversion
# 2000W >= 1500W = True (not lexicographic string comparison)
```

**Example 2: Fallback to Built-in Handler**

```python
# Input: compare("hello", "world", "==")
#
# EnergyComparisonHandler.can_handle_raw("hello", "world", "==")
# → Tries to parse as energy → Fails → Returns False
#
# StringComparisonHandler.can_handle_raw("hello", "world", "==")
# → Checks if both are strings → Success → Returns True
#
# Result: Built-in string handler processes
# "hello" == "world" = False
```

**Example 3: Multiple User Handlers**

```python
# Registered handlers:
# 1. EnergyComparisonHandler(priority=5)
# 2. IPAddressComparisonHandler(priority=10)
# 3. StringComparisonHandler(priority=50)

# Input: compare("192.168.1.1", "192.168.1.0/24", "in")
#
# EnergyComparisonHandler.can_handle_raw(...)
# → Tries to parse as energy → Fails → Returns False
#
# IPAddressComparisonHandler.can_handle_raw(...)
# → Checks if valid IP addresses → Success → Returns True
#
# Result: IP address handler processes network-aware comparison
# 192.168.1.1 in 192.168.1.0/24 = True
```

### Handler Registration Process

**Step-by-Step Registration:**

1. **Create Handler**: Define your handler class with appropriate priority
2. **User Registration**: Call `register_user_comparison_handler(handler)`
3. **Global Registry**: Handler is added to the extensible comparison registry
4. **Priority Sorting**: Registry automatically sorts handlers by priority
5. **Automatic Integration**: Collection patterns and condition evaluation use registered handlers

**Registration Example:**

```python
# Create handler with appropriate priority
energy_handler = EnergyComparisonHandler()  # priority=5
ip_handler = IPAddressComparisonHandler()   # priority=10

# Register handlers (order doesn't matter - priority determines order)
register_user_comparison_handler(energy_handler)
register_user_comparison_handler(ip_handler)

# Handlers are now available for all comparisons
```

### Discovery and Inspection

**Check Registered Handlers:**

```python
from ha_synthetic_sensors.comparison_handlers import get_comparison_factory

factory = get_comparison_factory()
handler_info = factory.get_handler_info()

# Inspect all registered handlers
for handler in handler_info:
    print(f"Handler: {handler['type_name']}, Priority: {handler['priority']}")

# Example output:
# Handler: energy, Priority: 5
# Handler: ip_address, Priority: 10
# Handler: string, Priority: 50
# Handler: numeric, Priority: 50
```

**Test Handler Selection:**

```python
from ha_synthetic_sensors.comparison_handlers import compare_values

# Test which handler is selected
result = compare_values("2kW", "1500W", ">=")
# Energy handler processes this (priority=5)

result = compare_values("192.168.1.1", "192.168.1.0/24", "in")
# IP handler processes this (priority=10)

result = compare_values("hello", "world", "==")
# String handler processes this (priority=50)
```

## Integration with Collection Resolver

The collection resolver automatically leverages user-defined comparison handlers for:

**Attribute Conditions:**

```yaml
formula: count("attribute:power_consumption>=1kW")
# Uses energy handler for unit-aware comparison
```

**State Conditions:**

```yaml
formula: count("state:<2kW")
# Uses energy handler for state value comparison
```

**Complex Patterns:**

```yaml
formula: count("attribute:power_consumption>=1kW and state:<3kW")
# Both conditions use energy handler
```

## Advanced Handler Examples

### IP Address Handler

```python
class IPAddressComparisonHandler(BaseComparisonHandler):
    """Handler for IP address comparisons with network awareness."""

    def get_supported_types(self) -> set[TypeCategory]:
        return {TypeCategory.STRING}

    def get_supported_operators(self) -> set[str]:
        return {"==", "!=", "in", "not in"}

    def get_type_info(self) -> ComparisonTypeInfo:
        return ComparisonTypeInfo(
            type_name="ip_address",
            priority=10,
            supported_operators=self.get_supported_operators(),
            can_handle_user_types=True,
        )

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        if op not in self.get_supported_operators():
            return False

        # Check if both are valid IP addresses
        return (self._is_valid_ip(left_raw) and
                (isinstance(right_raw, str) and self._is_valid_ip(right_raw)))

    def _is_valid_ip(self, ip_str: str) -> bool:
        """Validate IP address format."""
        import ipaddress
        try:
            ipaddress.ip_address(ip_str)
            return True
        except ValueError:
            return False

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        if not self.can_handle_raw(left_raw, right_raw, op):
            return False

        import ipaddress
        left_ip = ipaddress.ip_address(left_raw)
        right_ip = ipaddress.ip_address(right_raw)

        if op == "==":
            return left_ip == right_ip
        elif op == "!=":
            return left_ip != right_ip
        elif op == "in":
            # Check if left_ip is in right_ip network
            right_network = ipaddress.ip_network(right_raw, strict=False)
            return left_ip in right_network
        elif op == "not in":
            right_network = ipaddress.ip_network(right_raw, strict=False)
            return left_ip not in right_network

        return False

    def _compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        return self.compare_raw(actual_val, expected_val, op)
```

### Version String Handler

```python
class VersionComparisonHandler(BaseComparisonHandler):
    """Handler for semantic version comparisons."""

    def get_supported_types(self) -> set[TypeCategory]:
        return {TypeCategory.STRING}

    def get_supported_operators(self) -> set[str]:
        return {"==", "!=", "<", "<=", ">", ">="}

    def get_type_info(self) -> ComparisonTypeInfo:
        return ComparisonTypeInfo(
            type_name="version",
            priority=15,
            supported_operators=self.get_supported_operators(),
            can_handle_user_types=True,
        )

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        if op not in self.get_supported_operators():
            return False

        return (self._is_valid_version(left_raw) and
                self._is_valid_version(right_raw))

    def _is_valid_version(self, version_str: str) -> bool:
        """Validate semantic version format."""
        import re
        pattern = r'^\d+\.\d+\.\d+(\-[a-zA-Z0-9]+)?(\+[a-zA-Z0-9]+)?$'
        return bool(re.match(pattern, version_str))

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        if not self.can_handle_raw(left_raw, right_raw, op):
            return False

        from packaging import version
        left_ver = version.parse(left_raw)
        right_ver = version.parse(right_raw)

        return self._apply_operator(left_ver, right_ver, op)

    def _compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        return self.compare_raw(actual_val, expected_val, op)
```

## Best Practices

**Handler Design:**

- **Single Responsibility**: Each handler should focus on one data type or domain
- **Error Handling**: Gracefully handle invalid inputs and return `False` for unparseable values
- **Performance**: Keep parsing and comparison logic efficient
- **Documentation**: Provide clear type information and supported operators

**Registration Strategy:**

- **Early Registration**: Register handlers before setting up synthetic sensors
- **Priority Management**: Use appropriate priority levels to avoid conflicts
- **Testing**: Test handlers thoroughly with various input combinations

**Integration Patterns:**

- **Collection Patterns**: Use in `count()`, `sum()`, `average()` functions
- **Condition Evaluation**: Works with attribute and state conditions
- **Formula Variables**: Can be used in sensor formulas and attributes

## Testing User-Defined Handlers

```python
import pytest
from ha_synthetic_sensors.comparison_handlers import compare_values

def test_energy_handler_integration():
    """Test that energy handler works in collection patterns."""

    # Register handler
    energy_handler = EnergyComparisonHandler()
    register_user_comparison_handler(energy_handler)

    # Test direct comparisons
    assert compare_values("2kW", "1500W", ">=") == True
    assert compare_values("1kW", "2000W", "<") == True
    assert compare_values("1kW", "1000W", "==") == True

    # Test error handling
    assert compare_values("invalid", "1000W", ">=") == False
```

## Collection Functions with User-Defined Handlers

Collection functions (`sum()`, `count()`, `avg()`, etc.) automatically leverage user-defined comparison handlers when available.
This enables advanced filtering with domain-specific logic:

```yaml
sensors:
  # Energy-aware filtering with custom energy handler
  high_power_devices:
    name: "High Power Devices"
    formula: count("attribute:power_consumption>=1kW") # Uses energy handler
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:flash"

  # Version-aware filtering with custom version handler
  updated_firmware:
    name: "Updated Firmware Devices"
    formula: count("attribute:firmware_version>='v2.1.0'") # Uses version handler
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:update"

  # IP address filtering with custom IP handler
  local_network_devices:
    name: "Local Network Devices"
    formula: count("attribute:ip_address in '192.168.1.0/24'") # Uses IP handler
    metadata:
      unit_of_measurement: "devices"
      icon: "mdi:network"

  # Complex energy calculations with unit conversion
  total_energy_consumption:
    name: "Total Energy Consumption"
    formula: sum("attribute:energy_consumption>=1kWh") # Uses energy handler
    metadata:
      unit_of_measurement: "kWh"
      device_class: "energy"
```

**Automatic Handler Integration:**

When you register custom comparison handlers, collection patterns automatically use them for:

- **Attribute conditions**: `attribute:power_consumption>=1kW` uses energy handler for unit-aware comparison
- **State conditions**: `state:<2kW` uses energy handler for state value comparison
- **Complex patterns**: `attribute:power_consumption>=1kW and state:<3kW` uses handlers for both conditions
- **Mixed units**: `attribute:power_consumption>=1.5kW` correctly compares with `"1500W"` values

**Available Collection Functions:**

- `count()` - Count entities matching patterns
- `sum()` - Sum numeric values from matching entities
- `avg()` / `mean()` - Average numeric values from matching entities
- `min()` / `max()` - Find minimum/maximum values from matching entities
- `std()` / `var()` - Calculate standard deviation/variance from matching entities

**Pattern Types with Handler Support:**

- `"device_class:power"` - Device class filtering
- `"regex:pattern_variable"` - Regex pattern matching
- `"area:kitchen"` - Area-based filtering
- `"attribute:name>=value"` - **Uses user handlers for comparison**
- `"state:value"` - **Uses user handlers for comparison**
- `"label:security"` - Label-based filtering

This integration enables powerful, domain-specific entity filtering without requiring changes to your YAML configuration when
handlers are registered.

## Handler Selection Design Principles

The handler selection system follows these key principles to ensure predictable and reliable behavior:

### 1. **First-Come-First-Served (Priority-Based)**

- Handlers are checked in strict priority order
- First handler that returns `True` from `can_handle_raw()` wins
- No backtracking or complex conflict resolution
- Lower priority numbers always win over higher priority numbers

### 2. **Explicit Capability Declaration**

- Each handler must explicitly declare what it can handle via `can_handle_raw()`
- No automatic type inference or guessing
- Clear separation of concerns - handlers only handle their domain
- Predictable behavior based on explicit capability checks

### 3. **Graceful Degradation**

- If no user handler can handle the comparison, built-in handlers take over
- System never fails due to missing handlers
- Predictable fallback behavior for all comparison types
- Robust error handling for edge cases

### 4. **Priority-Based Control**

- Users have complete control over handler precedence
- Lower priority numbers = higher precedence (1 is highest)
- Built-in handlers have lower priority (50+) by default
- Easy to override built-in behavior with user handlers

### 5. **Deterministic Selection**

- Same inputs always select the same handler
- No race conditions or non-deterministic behavior
- Predictable selection based on priority and capability
- Easy to debug and reason about handler selection

**Example: Predictable Selection**

```python
# Registered handlers (in priority order):
# 1. EnergyComparisonHandler(priority=5)
# 2. IPAddressComparisonHandler(priority=10)
# 3. StringComparisonHandler(priority=50)

# These comparisons will ALWAYS select the same handlers:
compare("2kW", "1500W", ">=")      # → Energy handler (priority=5)
compare("192.168.1.1", "192.168.1.0/24", "in")  # → IP handler (priority=10)
compare("hello", "world", "==")    # → String handler (priority=50)
```

The user-defined comparison handler system provides powerful extensibility for domain-specific data types while maintaining
clean integration with the existing synthetic sensors architecture.
