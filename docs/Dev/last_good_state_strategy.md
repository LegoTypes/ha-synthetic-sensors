<!--
Proposal: how to preserve "last-good" energy readings for synthetic sensors during panel outages.
This document describes two viable options, trade-offs, and a recommended implementation.
-->

# Last-good state strategy for synthetic energy sensors

Problem

- Home Assistant energy sensors with `state_class=total_increasing` must not produce large spurious deltas when the panel
  becomes unavailable. When backing entity `state` becomes `None` (or `unavailable`) the synthetic sensor needs a safe way to
  present the previous valid reading while the integration's configured grace period is active.

Constraints

- Avoid circular template attributes (attributes computed from `state` will not reliably retain previous values).
- Minimize changes to user-visible YAML templates.
- Prefer solutions that are easy to test and log.

Options

Recommendation (user-facing UX)

- The synthetic package should expose coordinator-managed values as real, read-only attributes on the entity state so templates
  can reference them directly. Specifically:
  - Provide a reserved attribute named `__last_valid_state` and a timestamp attribute `__last_valid_changed` (double-underscore
    prefix to reduce collision risk).
  - Allow template authors to use either attribute access or metadata helper forms:
    - `state.__last_valid_state` and `state.__last_valid_changed`
    - or `metadata(state, 'last_valid_state')` and `metadata(state, 'last_valid_changed')`
  - Example template fallback that users should be able to write in YAML:
    - `formula: "state if within_grace else state.__last_valid_state"`
    - (or) `formula: "state if within_grace else metadata(state, 'last_valid_state')"`

Why this UX

- Templates become simple and expressive: they continue to use `state` as the primary backing value and can fall back to
  coordinator-provided stable attributes when `state` is missing.
- No circular attribute computation: the `__last_valid_*` attributes are supplied by the synthetic package
  (coordinator/data-provider) and are not calculated by the synthetic sensor itself.

Implementation sketch (how the synthetic package provides these attributes)

- The `__last_valid_state` and `__last_valid_changed` values MUST be derived from the synthetic sensor's _calculated_ state (the
  value the synthetic engine writes to Home Assistant), not from raw backing-entity payloads. In other words, the last-good
  value is the post-evaluation state the engine publishes for the synthetic sensor.
- No coordinator-level write by integrations is required. The synthetic engine should compute the final sensor state through the
  normal evaluation pipeline (Phases 0–4) and then set the reserved attributes on the HA entity when writing that final state
  (see engine-managed implementation below).
- Fallback semantics: templates should use `state.__last_valid_state` only when `state` is missing and the template's grace
  logic requires it (e.g., `within_grace`). The engine is responsible for preserving `__last_valid_state` across alternate state
  writes so templates reliably read the last calculated good value.

Examples (user YAML)

Simple energy fallback:

```yaml
formula: "state if within_grace else state.__last_valid_state"
```

Attribute-based fallback:

```yaml
formula: "state if within_grace else metadata(state, 'last_valid_state')"
```

When to update the attributes

- The coordinator will update `__last_valid_state` only while is not an alternative state
- The coordinator will update `__last_valid_changed` only while is not an alternative state

Testing and observability

- Add debug logs when the coordinator updates `__last_valid_state` and when it is used to satisfy a template fallback.
- Integration test: simulate panel offline; assert templates return `__last_valid_state` during grace and `STATE_NONE` (or
  expected) after timeout.

Notes and cautions

- Do not overwrite HA-managed `last_changed`. Instead, expose `__last_valid_changed` as a separate timestamp attribute.

Engine-managed implementation (Option A, no integration changes)

Summary of change

- The synthetic engine (the package that creates and updates the Home Assistant entities) will own and maintain the
  `__last_valid_state` and `__last_valid_changed` attributes on each synthetic HA entity it manages. Integrations that register
  backing entities do not need to write or manage any coordinator-level caches to support this feature.

Behavioral rules

- When the synthetic engine writes a new non-alternate state to the HA entity (i.e., the computed or backing state is a normal
  value, not `STATE_NONE`/`STATE_UNAVAILABLE`/`STATE_UNKNOWN`), it MUST set or update the two reserved attributes on the entity:
  - `__last_valid_state`: the state value that was written (use the same normalized type the engine exposes via HA)
  - `__last_valid_changed`: an ISO-8601 timestamp (string) or epoch float representing when that last-good state was recorded
- When the engine writes an alternate state (None/`unknown`/`unavailable` or any alternate-state result produced by the
  alternate state handler system), it MUST NOT change either `__last_valid_state` or `__last_valid_changed` (they remain as the
  last recorded good values).
- On initial entity creation the engine SHOULD initialize the attributes only if the initial state is a non-alternate valid
  value; otherwise leave them absent until a valid state is observed.

Where to implement

- Implement this logic in the final entity update path — the component that performs the atomic HA state+attribute write after
  Phase 4 consolidation (the same place that currently commits evaluated results to Home Assistant, e.g., the `SensorManager` or
  entity update helper).
- Ensure the update is atomic: compute the final state and attribute map, then perform a single HA set_state/update call with
  the combined payload so observers never see an inconsistent intermediate state.

Implementation sketch (high-level pseudocode)

```python
# After full evaluation, alternate-state processing, and result consolidation
new_state = evaluation_result.state
is_alternate = evaluation_result.is_alternate_state

# copy existing attributes to avoid overwriting unrelated keys
attrs = dict(entity.attributes or {})

if not is_alternate:
    # normalize new_state as the engine does for HA exposure
    attrs['__last_valid_state'] = normalize_for_ha(new_state)
    attrs['__last_valid_changed'] = now_iso()
# else: leave attrs['__last_valid_*'] unchanged

# perform the atomic write of state + attributes
async_set_state(entity_id, new_state, attributes=attrs)
```

Implementation notes

- Use the consolidated alternate-state decision from Phase 4 (post-evaluation processing) as the authoritative `is_alternate`
  signal. Do not rely on only early-phase detection for the final update because handlers or exceptions may change the final
  state decision.
- `normalize_for_ha()` should match the engine's existing normalization rules (numeric strings → numbers, booleans, etc.) so
  `__last_valid_state` matches the `state` type visible in Home Assistant.
- Keep attribute keys double-underscored to minimize collision risk with user-provided attributes.

Observability and logging

- Log at DEBUG when the engine records a `__last_valid_state` and when it intentionally skips updating due to an alternate-state
  write. Example messages:
- Emit a single INFO when a sensor records its first-ever valid state (helpful for diagnosing initialization issues).

Testing plan

- Unit tests (entity update path):
  - Normal value write updates `__last_valid_state` and `__last_valid_changed`.
  - Alternate-state write preserves existing `__last_valid_*` attributes.
  - Initial entity create with valid state initializes the attributes.
  - Initial entity create with alternate state leaves attributes absent until first valid state.
- Integration tests:
  - Simulate backing entity transitions valid→unavailable→valid and assert `__last_valid_state` remains last valid value across
    the unavailable period and updates only when a new valid value arrives.
  - Assert templates using `state.__last_valid_state` return expected values during grace-period fallback scenarios.

Edge cases and cautions

- Do not overwrite HA-managed `last_changed` or `last_updated` — `__last_valid_changed` is additive and separate.
- Avoid storing large or sensitive data in `__last_valid_state`; restrict to the same types the sensor exposes as `state`.

Migration and compatibility

- No integration code changes required — this is a pure engine-side behavior change. Existing templates that use
  `state.__last_valid_state` will begin to function once the engine has recorded the first valid state.
- Document guarantee: `__last_valid_state` will be available only after the synthetic engine has observed a non-alternate state
  at least once for that entity.

Impact summary

- Integrations: no changes required
- Synthetic engine: small responsibility added in the entity update path (write attributes when writing valid states)
- Tests: add unit and integration tests covering update semantics and grace-period fallback
