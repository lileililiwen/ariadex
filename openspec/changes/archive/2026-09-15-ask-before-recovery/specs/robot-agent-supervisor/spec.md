## ADDED Requirements

### Requirement: Readiness ask before confirmation recovery

When the boundary would fire confirmation recovery for unfinished
tasks, the supervisor MUST first send one readiness ask in the current
conversation and route on its strict token reply before resetting
anything. DONE runs confirmation recovery as today; WORKING returns to
working state with the debounce count restarted; a timeout or any
unparseable reply proceeds exactly as today without asking again for
the same undecided boundary.

#### Scenario: Agent reports still working

- **WHEN** the readiness ask replies WORKING
- **THEN** the supervisor sends no `/new`, restarts the debounce
  count, and keeps watching the current conversation

#### Scenario: Agent reports done with tasks open

- **WHEN** the readiness ask replies DONE while tasks remain open
- **THEN** the supervisor runs confirmation recovery exactly as
  without the ask

#### Scenario: Ask happens at most once per boundary

- **WHEN** the same undecided boundary evaluates again after an ask
- **THEN** the supervisor skips the ask and proceeds as today
