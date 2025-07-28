"""Example: Using TypedDict for Condition Parsing

This example demonstrates how the ConditionParser now uses TypedDict structures
to represent parsed conditions, making them extensible for any type - built-in
or user-defined.
"""

import os

# Import from the same directory
import sys

from ha_synthetic_sensors.comparison_handlers import register_user_comparison_handler
from ha_synthetic_sensors.condition_parser import ConditionParser, ParsedAttributeCondition, ParsedCondition

sys.path.append(os.path.dirname(__file__))
from custom_comparison_type import ColorComparisonType, IPAddressComparisonType


def demo_typed_dict_conditions():
    """Demonstrate TypedDict-based condition parsing and evaluation."""

    # Register custom comparison types
    ip_handler = IPAddressComparisonType()
    color_handler = ColorComparisonType()
    register_user_comparison_handler(ip_handler)
    register_user_comparison_handler(color_handler)

    print("=== Built-in Type Conditions ===")

    # Parse various condition types - all return TypedDict structures
    numeric_condition = ConditionParser.parse_state_condition(">= 50")
    print(f"Numeric condition: {numeric_condition}")
    print(f"Type: {type(numeric_condition)}")

    boolean_condition = ConditionParser.parse_state_condition("!off")
    print(f"Boolean condition: {boolean_condition}")

    version_condition = ConditionParser.parse_state_condition("== 2.1.0")
    print(f"Version condition: {version_condition}")

    print("\n=== User-Defined Type Conditions ===")

    # IP address conditions
    ip_condition = ConditionParser.parse_state_condition("== 192.168.1.1")
    print(f"IP condition: {ip_condition}")

    # Color conditions
    color_condition = ConditionParser.parse_state_condition("!= red")
    print(f"Color condition: {color_condition}")

    print("\n=== Attribute Conditions ===")

    # Parse attribute conditions
    temp_attr = ConditionParser.parse_attribute_condition("temperature > 20")
    print(f"Temperature attribute: {temp_attr}")
    print(f"Type: {type(temp_attr)}")

    ip_attr = ConditionParser.parse_attribute_condition("device_ip == 192.168.1.100")
    print(f"IP attribute: {ip_attr}")

    print("\n=== Evaluating Conditions ===")

    # Test evaluations with actual values
    print(f"75 >= 50: {ConditionParser.evaluate_condition(75, numeric_condition)}")
    print(f"'on' != 'off': {ConditionParser.evaluate_condition('on', boolean_condition)}")
    print(f"'3.0.0' == '2.1.0': {ConditionParser.evaluate_condition('3.0.0', version_condition)}")

    # Custom type evaluations
    print(f"'192.168.1.1' == '192.168.1.1': {ConditionParser.evaluate_condition('192.168.1.1', ip_condition)}")
    print(f"'blue' != 'red': {ConditionParser.evaluate_condition('blue', color_condition)}")

    print("\n=== Working with Raw TypedDict ===")

    # You can also create conditions manually
    manual_condition: ParsedCondition = {
        "operator": "in",
        "value": "192.168.1.0",  # Subnet check
    }

    result = ConditionParser.evaluate_condition("192.168.1.5", manual_condition)
    print(f"Manual subnet condition: {manual_condition}")
    print(f"'192.168.1.5' in '192.168.1.0': {result}")

    # Attribute condition creation
    manual_attr: ParsedAttributeCondition = {"attribute": "friendly_name", "operator": "==", "value": "Living Room"}
    print(f"Manual attribute condition: {manual_attr}")

    print("\n=== Extensibility Benefits ===")

    # The TypedDict approach means:
    # 1. Type safety at compile time
    # 2. Easy serialization/deserialization (JSON, YAML, etc.)
    # 3. Works with any comparison type (built-in or user-defined)
    # 4. Clean, structured interface

    import json

    serialized = json.dumps(ip_condition)
    print(f"JSON serializable: {serialized}")

    deserialized = json.loads(serialized)
    print(f"Deserialized works: {ConditionParser.evaluate_condition('192.168.1.1', deserialized)}")


if __name__ == "__main__":
    demo_typed_dict_conditions()
