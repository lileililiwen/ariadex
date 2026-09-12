# bounded-run-completion Specification

## Purpose
Defines honest run termination: cycle-limit exhaustion and zero-budget runs are explicit incomplete outcomes that preserve the next action, send no further input, and exit non-zero instead of reporting success.
## Requirements
### Requirement: Cycle-limit exhaustion is not success

When the runner reaches its cycle limit while work remains, it MUST return an explicit stopped `cycle-limit` outcome and the CLI MUST return non-zero.

#### Scenario: Work remains at the bound
- **WHEN** ten cycles complete without idle, blocker, or another terminal outcome
- **THEN** Ariadex preserves the next action, reports cycle-limit exhaustion, and does not claim the run completed

### Requirement: Zero-cycle runs are honest

A run with a zero cycle budget MUST return an explicit incomplete outcome and MUST NOT return success.

#### Scenario: Zero budget
- **WHEN** `run(max_cycles=0)` is requested
- **THEN** no provider input is sent and the result identifies that no execution budget was available

