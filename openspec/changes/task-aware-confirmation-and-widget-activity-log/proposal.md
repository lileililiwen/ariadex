# Proposal: Task-aware confirmation and widget activity log

## Problem

The managed watcher currently has only a first prompt and a continuation
prompt. When the provider returns to an input-ready surface while the active
OpenSpec change still contains unchecked tasks, Ariadex must not claim that the
spec is complete or blindly advance. It needs a deliberate prompt that asks
the provider to finish the remaining work. The widget also does not explain
why a continuation was or was not sent, which makes boundary decisions look
like silent failures.

## Outcome

Add a configurable `confirmation_prompt`, collected by `ariadex init` and
stored in `.ariadex/config.yaml`. When a conversation ends with unfinished
tasks, the watcher opens a fresh provider conversation and sends this prompt
after readiness. When all tasks are complete, it retains the existing
continuation behavior.

Add a bounded Ariadex activity log to the robot widget. The collapsed widget
shows the latest event; the expanded view shows recent lifecycle, boundary,
prompt, waiting, pause, and error events. It must not display raw provider
transcripts or inject diagnostic text into the provider editor.

## Scope and non-goals

- Restore task completion as a real completion decision, while making
  unfinished-task completion recoverable through the confirmation prompt.
- Keep provider reset and `/new` behavior inside `AgentAdapter`.
- Keep the existing durable telemetry and redaction policy.
- Do not add LLM API calls, IDE features, or a new user-facing lifecycle
  command.
- Do not make malformed task metadata silently recoverable; report it in the
  widget and remain blocked.
