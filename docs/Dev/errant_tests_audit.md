# Errant Tests Audit

This document tracks tests that require attention because they:

- Use conditional assertions (e.g., `if ...: assert ...`) — assertions must be unconditional.
- Use weak checks like `is not None` without validating the actual value or behavior.
- Assert alternate-state string literals (e.g., `"unknown"` or `"unavailable"`) in places where the test likely intends to
  assert a numeric/None/boolean result.

All implementation code is frozen. Only tests will be modified to correctly express intent.

## Findings (initial scan)

- `tests/evaluator/test_non_numeric_states.py`
  - Multiple `assert result.get("state") == "unknown"` lines. Verify intent: if the test is checking that the engine returns an
    explicit HA-style string state, keep; otherwise update to assert on `result["value"]` or `result["success"]` and the
    semantic value.

- `tests/evaluator/test_formula_evaluation.py`
  - `assert result["state"] == "unknown"` — verify intent and replace with explicit checks of `value` where appropriate.

- `tests/evaluator/test_fatal_error_handling.py`
  - `assert result["value"] == "unknown"` — confirm that `"unknown"` is the intended API, otherwise change to semantically
    meaningful asserts.

- `tests/storage/test_data_validation.py`
  - `assert result == "unknown"` — data validation tests asserting string conversions that may be masking issues. Confirm
    intent.

- `tests/evaluator/test_alternate_handlers_comprehensive.py`
  - Previously had an integration-only skipped test; converted to a unit assertion that verifies `AlternateStateHandler` accepts
    `None`.

- **Conditional asserts** found across integration tests (examples):
  - `tests/docs/integration_test_guide.md` — multiple `if ...: assert ...` occurrences.
  - `tests/integration/test_string_operations.py` — `if ...: assert ...` patterns.

## Proposed remediation plan

1. For each test asserting `"unknown"` or `"unavailable`:
   - Read the test to confirm intended behavior (is it testing alternate-state handling intentionally?).
   - If intent is to test alternate-state handling, update assertions to use the public constants or structured `result` keys
     (`result["value"] is None` or `result["success"] is True`), and add clarifying comments.
   - If intent is to test numeric/string/boolean results, change assertions to compare the concrete expected value.

2. Replace `assert x is not None` with stronger assertions:
   - `assert x == expected_value` or
   - `assert isinstance(x, ExpectedType)` and `assert x == expected_value` where type matters.

3. Remove conditional assertions:
   - Convert `if cond: assert ...` into either unconditional `assert cond and ...` never skip tests

4. Apply changes in small batches (5–10 files), run pre-commit and pytest, fix lints/format issues.

## Next batch candidate files (priority)

1. `tests/evaluator/test_non_numeric_states.py`
2. `tests/evaluator/test_formula_evaluation.py`
3. `tests/evaluator/test_fatal_error_handling.py`
4. `tests/evaluator/test_numeric_literals.py`
5. `tests/storage/test_data_validation.py`

## Notes

- Preserve test intent. If a test intentionally asserts alternate-state strings as part of the public behavior, do not change
  semantics; instead make assertions clearer (use constants or structured results).
- For integration tests that rely on runtime environment and contain conditional assertions, prefer to use `pytest.skip()` with
  a clear reason if the environment isn't present.

---

I'll begin applying fixes to the first priority batch after you confirm. Each change will be test-only and staged; I'll run
pre-commit and tests after each batch.
