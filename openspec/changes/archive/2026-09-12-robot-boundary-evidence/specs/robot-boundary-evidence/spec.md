# Robot boundary evidence specification

## Purpose

Use HANDOFF, task markers, git state, and the active OpenSpec list as the
default evidence gate before robot continuation.

## ADDED Requirements

### Requirement: Infer the finished change

When no explicit finished-change override is supplied, the watcher MUST use the
current change named by `HANDOFF.md` to locate and inspect its `tasks.md`.

#### Scenario: Current tasks are complete

- **WHEN** the current provider conversation is ready and HANDOFF names a
  change whose tasks are all checked
- **THEN** the watcher continues evaluating git and active OpenSpec evidence

#### Scenario: Current tasks remain open

- **WHEN** HANDOFF names a change with unchecked task markers
- **THEN** the watcher does not open a new conversation and reports the exact
  open-task count

### Requirement: Durable evidence gates continuation

The watcher MUST require readable HANDOFF, completed current tasks, clean git
state, and valid active OpenSpec discovery before opening a new conversation.

#### Scenario: Evidence passes

- **WHEN** all durable evidence passes and an active change remains
- **THEN** the watcher opens a new provider conversation and sends the
  continuation prompt

#### Scenario: Evidence fails

- **WHEN** any evidence check fails
- **THEN** the watcher sends no new-conversation command and reports the exact
  blocking evidence
