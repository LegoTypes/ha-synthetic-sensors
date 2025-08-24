"""Example: Using ConditionParser for Condition Evaluation

This example demonstrates how to use the ConditionParser for parsing and evaluating
conditions without the removed comparison handler system.
"""

from ha_synthetic_sensors.condition_parser import ConditionParser, ParsedAttributeCondition, ParsedCondition


def demo_condition_parsing():
    """Demonstrate condition parsing and evaluation using ConditionParser."""

    print("=== Built-in Type Conditions ===")

    # Parse various condition types - all return TypedDict structures
    numeric_condition = ConditionParser.parse_state_condition(">= 50")
    print(f"Numeric condition: {numeric_condition}")
    print(f"Type: {type(numeric_condition)}")

    boolean_condition = ConditionParser.parse_state_condition("!off")
    print(f"Boolean condition: {boolean_condition}")

    string_condition = ConditionParser.parse_state_condition("== hello")
    print(f"String condition: {string_condition}")

    print("\n=== Attribute Conditions ===")

    # Parse attribute conditions
    temp_attr = ConditionParser.parse_attribute_condition("temperature > 20")
    print(f"Temperature attribute: {temp_attr}")
    print(f"Type: {type(temp_attr)}")

    battery_attr = ConditionParser.parse_attribute_condition("battery_level <= 50")
    print(f"Battery attribute: {battery_attr}")

    print("\n=== Evaluating Conditions ===")

    # Test evaluations with actual values
    print(f"75 >= 50: {ConditionParser.evaluate_condition(75, numeric_condition)}")
    print(f"'on' != 'off': {ConditionParser.evaluate_condition('on', boolean_condition)}")
    print(f"'hello' == 'hello': {ConditionParser.evaluate_condition('hello', string_condition)}")

    # Test attribute evaluations
    print(f"Temperature 25 > 20: {ConditionParser.evaluate_condition(25, temp_attr)}")
    print(f"Battery 30 <= 50: {ConditionParser.evaluate_condition(30, battery_attr)}")

    print("\n=== Working with Raw TypedDict ===")

    # You can also create conditions manually
    manual_condition: ParsedCondition = {
        "operator": ">",
        "value": "100",
    }

    result = ConditionParser.evaluate_condition(150, manual_condition)
    print(f"Manual condition: {manual_condition}")
    print(f"150 > 100: {result}")

    # Attribute condition creation
    manual_attr: ParsedAttributeCondition = {"attribute": "friendly_name", "operator": "==", "value": "Living Room"}
    print(f"Manual attribute condition: {manual_attr}")

    print("\n=== Type Conversion Examples ===")

    # ConditionParser handles type conversion automatically
    string_number_condition = ConditionParser.parse_state_condition("== 42")
    print(f"'42' == 42: {ConditionParser.evaluate_condition('42', string_number_condition)}")
    print(f"42 == '42': {ConditionParser.evaluate_condition(42, string_number_condition)}")

    boolean_string_condition = ConditionParser.parse_state_condition("== true")
    print(f"True == 'true': {ConditionParser.evaluate_condition(True, boolean_string_condition)}")
    print(f"'true' == True: {ConditionParser.evaluate_condition('true', boolean_string_condition)}")

    print("\n=== Error Handling ===")

    # Invalid operators return False
    invalid_condition = {"operator": "invalid", "value": "test"}
    print(f"Invalid operator: {ConditionParser.evaluate_condition('test', invalid_condition)}")

    # Type errors return False
    numeric_condition = ConditionParser.parse_state_condition("> 10")
    print(f"String > number: {ConditionParser.evaluate_condition('hello', numeric_condition)}")

    print("\n=== Extensibility Benefits ===")

    # The ConditionParser approach means:
    # 1. Type safety at compile time
    # 2. Easy serialization/deserialization (JSON, YAML, etc.)
    # 3. Works with any comparison type
    # 4. Clean, structured interface

    import json

    serialized = json.dumps(numeric_condition)
    print(f"JSON serializable: {serialized}")

    # You can extend the evaluation logic for custom types
    def custom_evaluate_with_logging(actual_value, condition):
        """Custom evaluation with logging."""
        print(f"Evaluating: {actual_value} {condition['operator']} {condition['value']}")
        result = ConditionParser.evaluate_condition(actual_value, condition)
        print(f"Result: {result}")
        return result

    print("\n=== Custom Evaluation with Logging ===")
    custom_evaluate_with_logging(75, numeric_condition)


if __name__ == "__main__":
    demo_condition_parsing()
