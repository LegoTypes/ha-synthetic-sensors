"""Boolean state mappings for SimpleEval integration.

This module provides centralized boolean state mappings that can be used
as names in SimpleEval to enable proper comparison between entity references
and string literals in formulas.
"""

from .constants_boolean_states import get_core_false_states, get_core_true_states


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

        # Add core true states only (avoid domain-specific states that should remain as strings)
        for state in get_core_true_states():
            if state is not None:
                boolean_names[str(state)] = True

        # Add core false states only (avoid domain-specific states that should remain as strings)
        for state in get_core_false_states():
            if state is not None:
                boolean_names[str(state)] = False

        return boolean_names
