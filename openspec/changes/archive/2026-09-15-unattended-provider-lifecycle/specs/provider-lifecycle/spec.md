## ADDED Requirements

### Requirement: Adapter-owned model switch

Adapters MUST declare model-switch support and expose one switch command.
The watcher MUST route quota and model-error states to switch-and-continue
through the adapter contract, never through provider-specific watcher code.

#### Scenario: Model error recovery

- **WHEN** the provider reports a quota or model error and fallbacks remain
- **THEN** the watcher switches to the next configured model and continues
  the same spec without human input

#### Scenario: No fallback available

- **WHEN** fallbacks are empty or exhausted, or the adapter reports
  unsupported
- **THEN** the watcher keeps the current manual-recovery outcome with the
  exact reason recorded

### Requirement: No automatic input over drafts or pauses

The watcher MUST NOT reset or send any automatic input unless a fresh
capture reports `InputSurface.EMPTY` and no PAUSE is observed. This applies
to initial, continuation, confirmation, and retry inputs alike.

#### Scenario: Confirmation with human draft

- **WHEN** the confirmation path fires while the composer holds a draft
- **THEN** no `/new` or prompt is sent and the boundary refires later

### Requirement: Exhaustion refires instead of shutting down

Fresh-ready waits MUST stay bounded, and exhaustion MUST refire the
still-open boundary with a durable waiting state rather than shut the
watcher down.

#### Scenario: Busy provider outlasts the wait

- **WHEN** bounded fresh-ready attempts exhaust while the boundary is open
- **THEN** the watcher records waiting, sends nothing, and retries the
  boundary instead of stopping

#### Scenario: Repeated exhaustion parks visibly

- **WHEN** bounded waits exhaust repeatedly with the boundary still open
- **THEN** the watcher parks in a visible waiting state that resume clears,
  still sending nothing, instead of shutting down
