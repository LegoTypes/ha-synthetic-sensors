"""Boolean state mappings for SimpleEval integration.

This module provides centralized boolean state mappings that can be used
as names in SimpleEval to enable proper comparison between entity references
and string literals in formulas.
"""

import re

from .constants_boolean_states import get_current_false_states, get_current_true_states


class BooleanStates:
    """Collection of boolean state mappings for formula evaluation."""

    @staticmethod
    def get_all_boolean_names() -> dict[str, bool]:
        """Get all boolean state name mappings for SimpleEval.

        This enables formulas like 'binary_sensor.door == on' to work correctly
        by mapping string literals like 'on', 'off', 'locked', etc. to their
        boolean equivalents.

        Returns:
            Dictionary mapping state strings to boolean values
        """
        boolean_names: dict[str, bool] = {}

        # Add all true states
        for state in get_current_true_states():
            if state is not None:
                boolean_names[str(state)] = True

        # Add all false states
        for state in get_current_false_states():
            if state is not None:
                boolean_names[str(state)] = False

        return boolean_names

    @staticmethod
    def preprocess_formula_for_boolean_literals(formula: str) -> str:
        """Preprocess formula to convert quoted boolean literals to unquoted names.

        This converts formulas like "binary_sensor.door == 'on'" to
        "binary_sensor.door == on" so that SimpleEval can use the names mapping.

        Args:
            formula: The original formula string

        Returns:
            Formula with quoted boolean literals converted to unquoted names
        """
        # Get all boolean state strings
        boolean_states = set()
        for state in get_current_true_states():
            if state is not None:
                boolean_states.add(str(state))
        for state in get_current_false_states():
            if state is not None:
                boolean_states.add(str(state))

        # Convert quoted boolean literals to unquoted names
        processed_formula = formula
        for state in boolean_states:
            # Replace single-quoted literals: 'on' -> on
            processed_formula = re.sub(rf"'{re.escape(state)}'", state, processed_formula)
            # Replace double-quoted literals: "on" -> on
            processed_formula = re.sub(rf'"{re.escape(state)}"', state, processed_formula)

        return processed_formula
