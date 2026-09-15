# widget-control-room Specification

## Purpose
Defines a truthful widget control surface: non-modal Stop confirmation,
visible busy feedback, a live per-spec job pile, combined scheduling and
provider Pause, and plain-word waiting states.
## Requirements
### Requirement: Non-blocking Stop confirmation

The widget MUST confirm Stop without opening a modal dialog. The Tk event
loop MUST stay responsive while a stop is armed, and expiry MUST return to
the safe default of not stopping.

#### Scenario: Stop needs two presses

- **WHEN** the operator presses Stop once
- **THEN** the widget shows an armed confirm state and keeps responding
  to all other controls

#### Scenario: Armed confirm expires

- **WHEN** the armed confirm is not pressed again within its timeout
- **THEN** it disarms and no stop is sent

### Requirement: Honest busy controls

Every widget control MUST show a working state while its request is in
flight, and extra clicks MUST receive visible acknowledgment instead of
being silently dropped.

#### Scenario: Click during in-flight request

- **WHEN** the operator clicks a control while its IPC is in flight
- **THEN** the control shows it is working and the click is acknowledged
  without sending a duplicate request

### Requirement: Visible job pile

The widget MUST render the local OpenSpec queue with per-spec progress,
refreshed on every poll, without provider I/O.

#### Scenario: Pile visible during absence

- **WHEN** the provider is busy, blocked, or idle
- **THEN** the widget still shows every queued spec with completed/total
  and the current target highlighted

### Requirement: Combined Pause

Pause MUST stop scheduling and request a provider interrupt through the
adapter contract. Denial or delivery failure MUST keep the pause and
record the exact reason.

#### Scenario: Pause a running provider

- **WHEN** the operator pauses while the provider is working
- **THEN** scheduling stops and an interrupt is requested; the outcome
  is recorded either way

### Requirement: Plain-word waiting states

Waiting, refire, and model-switch activity MUST render as plain words in
the widget log from the existing diagnostic stream.

#### Scenario: Refire visible

- **WHEN** the watcher refires an open boundary after an exhausted wait
- **THEN** the widget log shows waiting in plain words with no codes

