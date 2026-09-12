# takeover-cancellation Specification

## Purpose
Defines immediate human preemption of a running scheduler: takeover and pause requests cancel in-flight cycles at phase checkpoints without new provider input, send-phase uncertainty is preserved for recovery, and verified completions stand.
## Requirements
### Requirement: Manual control prevents new automatic input

After takeover or pause is accepted, the runner MUST send no new provider input, including when the request arrives between cycle phases.

#### Scenario: Takeover during verification
- **WHEN** verification is running and the operator enters MANUAL
- **THEN** the current operation is cancelled or allowed to finish without further provider input, and the next scheduling step is not started

### Requirement: Cancellation preserves uncertainty

If cancellation occurs after provider input may have been delivered, Ariadex MUST preserve the persisted phase and require recovery or verification rather than fabricating completion.

#### Scenario: Cancellation after send
- **WHEN** takeover is requested after the send phase
- **THEN** the handoff records an uncertain operation and no completion is claimed

