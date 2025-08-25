"""Unit tests for type_safe_context module."""

import pytest
from unittest.mock import MagicMock, patch

from ha_synthetic_sensors.type_safe_context import TypeSafeEvaluationContext
from ha_synthetic_sensors.type_definitions import ReferenceValue


class TestTypeSafeEvaluationContext:
    """Test cases for TypeSafeEvaluationContext class."""

    def test_init(self) -> None:
        """Test TypeSafeEvaluationContext initialization."""
        context = TypeSafeEvaluationContext()
        assert isinstance(context, dict)
        assert len(context) == 0

    def test_setitem_with_reference_value(self) -> None:
        """Test setting item with ReferenceValue object."""
        context = TypeSafeEvaluationContext()
        ref_value = ReferenceValue("test_var", "test_value")

        context["test_key"] = ref_value

        assert context["test_key"] == ref_value

    def test_setitem_with_special_key(self) -> None:
        """Test setting item with special key starting with underscore."""
        context = TypeSafeEvaluationContext()

        context["_special_key"] = "raw_value"

        assert context["_special_key"] == "raw_value"

    def test_setitem_with_callable(self) -> None:
        """Test setting item with callable value."""
        context = TypeSafeEvaluationContext()

        def test_func():
            return "test"

        context["test_func"] = test_func

        assert context["test_func"] == test_func

    def test_setitem_with_none(self) -> None:
        """Test setting item with None value."""
        context = TypeSafeEvaluationContext()

        context["test_key"] = None

        assert context["test_key"] is None

    def test_setitem_with_raw_string_raises_error(self) -> None:
        """Test that setting raw string value raises TypeError."""
        context = TypeSafeEvaluationContext()

        with pytest.raises(TypeError, match="Raw value assignment blocked for variable 'test_key'"):
            context["test_key"] = "raw_string"

    def test_setitem_with_raw_int_raises_error(self) -> None:
        """Test that setting raw int value raises TypeError."""
        context = TypeSafeEvaluationContext()

        with pytest.raises(TypeError, match="Raw value assignment blocked for variable 'test_key'"):
            context["test_key"] = 42

    def test_setitem_with_raw_float_raises_error(self) -> None:
        """Test that setting raw float value raises TypeError."""
        context = TypeSafeEvaluationContext()

        with pytest.raises(TypeError, match="Raw value assignment blocked for variable 'test_key'"):
            context["test_key"] = 3.14

    def test_setitem_with_raw_bool_raises_error(self) -> None:
        """Test that setting raw bool value raises TypeError."""
        context = TypeSafeEvaluationContext()

        with pytest.raises(TypeError, match="Raw value assignment blocked for variable 'test_key'"):
            context["test_key"] = True

    def test_set_variable_with_reference(self) -> None:
        """Test set_variable_with_reference method."""
        context = TypeSafeEvaluationContext()

        with patch(
            "ha_synthetic_sensors.type_safe_context.ReferenceValueManager.set_variable_with_reference_value"
        ) as mock_set:
            context.set_variable_with_reference("test_var", "test_value", "resolved_value")

            mock_set.assert_called_once_with(context, "test_var", "test_value", "resolved_value")

    def test_to_evaluation_context(self) -> None:
        """Test to_evaluation_context method."""
        context = TypeSafeEvaluationContext()
        mock_context = MagicMock()

        with patch(
            "ha_synthetic_sensors.type_safe_context.ReferenceValueManager.convert_to_evaluation_context"
        ) as mock_convert:
            mock_convert.return_value = mock_context

            result = context.to_evaluation_context()

            assert result == mock_context
            mock_convert.assert_called_once_with(context)
