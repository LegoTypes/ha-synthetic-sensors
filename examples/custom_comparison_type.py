"""Example: Creating Custom Comparison Types

This example demonstrates how to extend the comparison system with your own
custom comparison types using the extensible protocol-based architecture.
"""

from ha_synthetic_sensors.comparison_handlers import ComparisonTypeInfo, compare_values, register_user_comparison_handler
from ha_synthetic_sensors.exceptions import UnsupportedComparisonError
from ha_synthetic_sensors.type_analyzer import OperandType


class IPAddressComparisonType:
    """Example user-defined comparison type for IP addresses.

    This handler can:
    - Compare IP addresses for equality
    - Check if an IP is in a subnet (simplified implementation)
    - Handle IP address strings like "192.168.1.1"
    """

    def get_type_info(self) -> ComparisonTypeInfo:
        """Get type information for IP address comparisons."""
        return ComparisonTypeInfo(
            type_name="ip_address",
            priority=5,  # Higher priority than built-in handlers
            supported_operators={"==", "!=", "in", "not in"},
            can_handle_user_types=True,
        )

    def can_handle_user_type(self, value: OperandType, metadata: dict[str, any]) -> bool:
        """Check if this handler can process a user-defined type with metadata."""
        return metadata.get("type") == "ip_address"

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Check if this handler can compare these raw values."""
        if op not in self.get_type_info()["supported_operators"]:
            return False

        # Handle if either value looks like an IP address
        return self._is_ip_address(left_raw) or self._is_ip_address(right_raw)

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Compare raw IP address values."""
        if not self.can_handle_raw(left_raw, right_raw, op):
            raise UnsupportedComparisonError(
                f"IPAddressComparisonType cannot handle comparison between "
                f"{type(left_raw).__name__} and {type(right_raw).__name__} with operator '{op}'"
            )

        # Convert to comparable format
        left_parsed = self._parse_ip(left_raw)
        right_parsed = self._parse_ip(right_raw)

        if op == "==":
            return left_parsed == right_parsed
        elif op == "!=":
            return left_parsed != right_parsed
        elif op == "in":
            # Check if left IP is in right subnet/range
            return self._ip_in_subnet(left_parsed, right_parsed)
        elif op == "not in":
            return not self._ip_in_subnet(left_parsed, right_parsed)
        else:
            raise UnsupportedComparisonError(f"Unsupported operator for IP address: {op}")

    def _is_ip_address(self, value: OperandType) -> bool:
        """Check if value looks like an IP address."""
        if not isinstance(value, str):
            return False

        try:
            parts = value.split(".")
            if len(parts) != 4:
                return False

            for part in parts:
                num = int(part)
                if not 0 <= num <= 255:
                    return False
            return True
        except (ValueError, AttributeError):
            return False

    def _parse_ip(self, value: OperandType) -> tuple[int, int, int, int]:
        """Parse IP address string to tuple of integers."""
        if isinstance(value, str) and self._is_ip_address(value):
            return tuple(int(part) for part in value.split("."))
        raise ValueError(f"Invalid IP address: {value}")

    def _ip_in_subnet(self, ip: tuple[int, int, int, int], subnet: tuple[int, int, int, int]) -> bool:
        """Simplified subnet check (checks if first 3 octets match)."""
        return ip[:3] == subnet[:3]


class ColorComparisonType:
    """Example comparison type for color values.

    Supports hex colors like "#FF0000" and named colors like "red".
    """

    COLOR_NAMES = {
        "red": "#FF0000",
        "green": "#00FF00",
        "blue": "#0000FF",
        "white": "#FFFFFF",
        "black": "#000000",
        "yellow": "#FFFF00",
        "cyan": "#00FFFF",
        "magenta": "#FF00FF",
    }

    def get_type_info(self) -> ComparisonTypeInfo:
        """Get type information for color comparisons."""
        return ComparisonTypeInfo(
            type_name="color",
            priority=8,  # Higher priority than built-ins
            supported_operators={"==", "!="},
            can_handle_user_types=True,
        )

    def can_handle_user_type(self, value: OperandType, metadata: dict[str, any]) -> bool:
        """Check if this handler can process a user-defined type with metadata."""
        return metadata.get("type") == "color"

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Check if this handler can compare these raw values."""
        if op not in self.get_type_info()["supported_operators"]:
            return False

        return self._is_color(left_raw) and self._is_color(right_raw)

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Compare color values."""
        if not self.can_handle_raw(left_raw, right_raw, op):
            raise UnsupportedComparisonError(
                f"ColorComparisonType cannot handle comparison between "
                f"{type(left_raw).__name__} and {type(right_raw).__name__} with operator '{op}'"
            )

        # Normalize both colors to hex format
        left_hex = self._normalize_color(left_raw)
        right_hex = self._normalize_color(right_raw)

        if op == "==":
            return left_hex == right_hex
        elif op == "!=":
            return left_hex != right_hex
        else:
            raise UnsupportedComparisonError(f"Unsupported operator for color: {op}")

    def _is_color(self, value: OperandType) -> bool:
        """Check if value is a color (hex or named)."""
        if not isinstance(value, str):
            return False

        value = value.lower().strip()

        # Check named colors
        if value in self.COLOR_NAMES:
            return True

        # Check hex colors
        if value.startswith("#") and len(value) == 7:
            try:
                int(value[1:], 16)
                return True
            except ValueError:
                pass

        return False

    def _normalize_color(self, value: OperandType) -> str:
        """Convert color to normalized hex format."""
        if not isinstance(value, str):
            raise ValueError(f"Color must be string, got {type(value)}")

        value = value.lower().strip()

        # Named color
        if value in self.COLOR_NAMES:
            return self.COLOR_NAMES[value].upper()

        # Hex color
        if value.startswith("#") and len(value) == 7:
            try:
                int(value[1:], 16)  # Validate hex
                return value.upper()
            except ValueError:
                pass

        raise ValueError(f"Invalid color: {value}")


def demo_custom_comparison_types():
    """Demonstrate the custom comparison types."""

    # Register our custom comparison types
    ip_handler = IPAddressComparisonType()
    color_handler = ColorComparisonType()

    register_user_comparison_handler(ip_handler)
    register_user_comparison_handler(color_handler)

    print("=== IP Address Comparisons ===")

    # Basic IP equality
    print(f"'192.168.1.1' == '192.168.1.1': {compare_values('192.168.1.1', '192.168.1.1', '==')}")
    print(f"'192.168.1.1' != '192.168.1.2': {compare_values('192.168.1.1', '192.168.1.2', '!=')}")

    # Subnet membership (simplified - checks first 3 octets)
    print(f"'192.168.1.5' in '192.168.1.0': {compare_values('192.168.1.5', '192.168.1.0', 'in')}")
    print(f"'192.168.2.5' not in '192.168.1.0': {compare_values('192.168.2.5', '192.168.1.0', 'not in')}")

    print("\n=== Color Comparisons ===")

    # Color equality (hex vs named)
    print(f"'red' == '#FF0000': {compare_values('red', '#FF0000', '==')}")
    print(f"'blue' != 'red': {compare_values('blue', 'red', '!=')}")
    print(f"'#00FF00' == 'green': {compare_values('#00FF00', 'green', '==')}")

    print("\n=== Built-in Types Still Work ===")

    # Non-custom values fall back to built-in handlers
    print(f"'hello' == 'hello': {compare_values('hello', 'hello', '==')}")
    print(f"5 > 3: {compare_values(5, 3, '>')}")
    print(f"'2.1.0' > '1.0.0': {compare_values('2.1.0', '1.0.0', '>')}")  # Version comparison

    print("\n=== Handler Priority Order ===")

    # Show all registered handlers by priority
    from ha_synthetic_sensors.comparison_handlers import get_extensible_registry

    registry = get_extensible_registry()

    for handler in registry.get_ordered_handlers():
        info = handler.get_type_info()
        print(f"  {info['type_name']} (priority {info['priority']}): {list(info['supported_operators'])}")


if __name__ == "__main__":
    demo_custom_comparison_types()
