from ha_synthetic_sensors.evaluator_handlers.numeric_handler import NumericHandler
from ha_synthetic_sensors.type_definitions import ReferenceValue


def test_numeric_handler_extracts_reference_values_and_evaluates() -> None:
    handler = NumericHandler(use_enhanced_evaluation=False)
    ctx = {"x": ReferenceValue(reference="x", value="30")}
    result = handler.evaluate("x + 2", ctx)
    assert result == 32.0


def test_numeric_handler_enhanced_mode_handles_duration_division() -> None:
    handler = NumericHandler(use_enhanced_evaluation=True)
    # minutes(5)/minutes(1) should produce 5.0 via enhanced evaluation
    result = handler.evaluate("minutes(5) / minutes(1)")
    assert result == 5.0


def test_numeric_handler_routing_error_for_non_numeric_result() -> None:
    handler = NumericHandler()
    try:
        handler.evaluate('"hello"')
        assert False, "Expected numeric-only ValueError"
    except Exception as e:  # ValueError from numeric-only enforcement
        assert "Expected numeric result" in str(e)


def test_numeric_handler_cache_stats_and_clear() -> None:
    handler = NumericHandler()
    _ = handler.evaluate("1+2")
    stats = handler.get_compilation_cache_stats()
    assert isinstance(stats, dict)
    handler.clear_compiled_formulas()
    stats_after = handler.get_compilation_cache_stats()
    assert isinstance(stats_after, dict)
