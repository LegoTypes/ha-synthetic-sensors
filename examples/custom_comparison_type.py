"""Example: Using ConditionParser for Custom Comparisons

This example demonstrates how to use the ConditionParser for custom comparison logic
without the need for the removed comparison handler system.
"""

from ha_synthetic_sensors.condition_parser import ConditionParser, ParsedCondition
from ha_synthetic_sensors.type_analyzer import OperandType


class IPAddressComparisonHelper:
    """Example helper class for IP address comparisons.

    This demonstrates how to implement custom comparison logic
    using the ConditionParser's evaluate_condition method.
    """

    @staticmethod
    def is_ip_address(value: OperandType) -> bool:
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

    @staticmethod
    def parse_ip(value: OperandType) -> tuple[int, int, int, int]:
        """Parse IP address string to tuple of integers."""
        if isinstance(value, str) and IPAddressComparisonHelper.is_ip_address(value):
            return tuple(int(part) for part in value.split("."))
        raise ValueError(f"Invalid IP address: {value}")

    @staticmethod
    def ip_in_subnet(ip: tuple[int, int, int, int], subnet: tuple[int, int, int, int]) -> bool:
        """Simplified subnet check (checks if first 3 octets match)."""
        return ip[:3] == subnet[:3]

    @staticmethod
    def compare_ip_addresses(left: OperandType, right: OperandType, operator: str) -> bool:
        """Compare IP addresses using the specified operator."""
        if not IPAddressComparisonHelper.is_ip_address(left) or not IPAddressComparisonHelper.is_ip_address(right):
            return False

        left_parsed = IPAddressComparisonHelper.parse_ip(left)
        right_parsed = IPAddressComparisonHelper.parse_ip(right)

        if operator == "==":
            return left_parsed == right_parsed
        elif operator == "!=":
            return left_parsed != right_parsed
        elif operator == "in":
            return IPAddressComparisonHelper.ip_in_subnet(left_parsed, right_parsed)
        elif operator == "not in":
            return not IPAddressComparisonHelper.ip_in_subnet(left_parsed, right_parsed)
        else:
            return False


class ColorComparisonHelper:
    """Example helper class for color comparisons.

    Supports hex colors like "#FF0000" and named colors like "red".
    """

    # Simple color mapping for demonstration
    NAMED_COLORS = {
        "red": "#FF0000",
        "green": "#00FF00",
        "blue": "#0000FF",
        "yellow": "#FFFF00",
        "cyan": "#00FFFF",
        "magenta": "#FF00FF",
        "white": "#FFFFFF",
        "black": "#000000",
    }

    @staticmethod
    def is_hex_color(value: OperandType) -> bool:
        """Check if value is a hex color."""
        if not isinstance(value, str):
            return False
        return value.startswith("#") and len(value) == 7 and all(c in "0123456789ABCDEFabcdef" for c in value[1:])

    @staticmethod
    def normalize_color(value: OperandType) -> str:
        """Normalize color to hex format."""
        if isinstance(value, str):
            # If it's already hex, return as is
            if ColorComparisonHelper.is_hex_color(value):
                return value.upper()

            # If it's a named color, convert to hex
            if value.lower() in ColorComparisonHelper.NAMED_COLORS:
                return ColorComparisonHelper.NAMED_COLORS[value.lower()]

        return str(value)

    @staticmethod
    def compare_colors(left: OperandType, right: OperandType, operator: str) -> bool:
        """Compare colors using the specified operator."""
        left_normalized = ColorComparisonHelper.normalize_color(left)
        right_normalized = ColorComparisonHelper.normalize_color(right)

        if operator == "==":
            return left_normalized == right_normalized
        elif operator == "!=":
            return left_normalized != right_normalized
        else:
            return False


def demo_custom_comparisons():
    """Demonstrate custom comparison logic using ConditionParser."""

    print("=== IP Address Comparisons ===")

    # Create conditions using ConditionParser
    ip_condition = ConditionParser.parse_state_condition("== 192.168.1.1")
    subnet_condition = ConditionParser.parse_state_condition("in 192.168.1.0")

    # Test IP comparisons
    test_ip = "192.168.1.1"
    test_ip2 = "192.168.1.5"

    # Use custom helper for IP-specific logic
    print(f"IP equality: {IPAddressComparisonHelper.compare_ip_addresses(test_ip, '192.168.1.1', '==')}")
    print(f"IP in subnet: {IPAddressComparisonHelper.compare_ip_addresses(test_ip2, '192.168.1.0', 'in')}")

    # Use ConditionParser for standard comparisons
    print(f"Standard equality: {ConditionParser.evaluate_condition(test_ip, ip_condition)}")

    print("\n=== Color Comparisons ===")

    # Create color conditions
    color_condition = ConditionParser.parse_state_condition("!= red")

    # Test color comparisons
    test_color = "blue"
    test_hex = "#FF0000"

    print(f"Color inequality: {ColorComparisonHelper.compare_colors(test_color, 'red', '!=')}")
    print(f"Hex to named: {ColorComparisonHelper.compare_colors(test_hex, 'red', '==')}")
    print(f"Standard color comparison: {ConditionParser.evaluate_condition(test_color, color_condition)}")

    print("\n=== Integration with ConditionParser ===")

    # You can extend ConditionParser.evaluate_condition for custom types
    def custom_evaluate_condition(actual_value: OperandType, condition: ParsedCondition) -> bool:
        """Custom evaluation that handles IP addresses and colors."""
        operator = condition["operator"]
        expected_value = condition["value"]

        # Try custom handlers first
        if IPAddressComparisonHelper.is_ip_address(actual_value) or IPAddressComparisonHelper.is_ip_address(expected_value):
            return IPAddressComparisonHelper.compare_ip_addresses(actual_value, expected_value, operator)

        if ColorComparisonHelper.is_hex_color(actual_value) or ColorComparisonHelper.is_hex_color(expected_value):
            return ColorComparisonHelper.compare_colors(actual_value, expected_value, operator)

        # Fall back to standard ConditionParser
        return ConditionParser.evaluate_condition(actual_value, condition)

    # Test custom evaluation
    custom_ip_condition = {"operator": "in", "value": "192.168.1.0"}
    print(f"Custom IP evaluation: {custom_evaluate_condition('192.168.1.5', custom_ip_condition)}")

    custom_color_condition = {"operator": "==", "value": "red"}
    print(f"Custom color evaluation: {custom_evaluate_condition('#FF0000', custom_color_condition)}")


if __name__ == "__main__":
    demo_custom_comparisons()
