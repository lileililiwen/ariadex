## ADDED Requirements

### Requirement: Unanswered approvals re-ask boundedly, then park visibly

An agent NOT DONE (or WORKING) reply to the unconfirmed-approval
question MUST re-arm the episode ask once after a bounded quiet
interval with no further input meanwhile. A repeated NOT DONE, or
a surface that outlasts the re-ask with no reply, MUST park the
watcher in a visible waiting state whose block reason names the
redacted request shape and the exact manual recovery step, and
send no further asks for the episode. DONE, timeout, and garbage
behave exactly as today. A reply MUST never approve anything; only
the permission policy on a parsed request may send approval
input.

#### Scenario: Agent reports it did not clear the prompt

- **WHEN** the agent replies NOT DONE to the approval question
- **THEN** Ariadex waits quietly, asks once more, and on a
  repeated NOT DONE parks with a visible reason instead of going
  quiet

#### Scenario: Cleared approval resumes

- **WHEN** the agent replies DONE and the surface clears
- **THEN** Ariadex resumes watching as today
