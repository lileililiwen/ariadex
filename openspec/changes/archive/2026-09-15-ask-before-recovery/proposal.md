# Proposal: Ask-before-recovery (readiness check)

## Why

Screen-quiet plus incomplete task files is ambiguous: the agent may be
pausing mid-work or truly stuck. Jumping straight to confirmation
recovery (`/new` + prompt) on a pausing agent destroys its context;
waiting forever on a stuck one strands the queue. One bounded question
in the current conversation resolves it before anything is reset.

## What Changes

- When the boundary would fire confirmation recovery (screen finished,
  evidence incomplete), the watcher first sends a readiness ask in the
  current conversation: "Spec X still shows N open tasks. Reply with
  exactly one line: DONE or WORKING."
- Strict token parse on the reply's first non-empty line:
  DONE → confirmation recovery exactly as today;
  WORKING → stay in working state and restart the debounce count;
  timeout or anything unparseable → today's behavior unchanged.
- Loop guard: never ask twice in a row for the same undecided
  boundary; the second evaluation proceeds without asking.
- Quiescence stays the primary finish gate; the ask is backup only and
  never fires while the screen is ambiguous or the agent looks busy.
- Canonical `robot-agent-supervisor` gains the readiness-ask step.

## BFS Impact Map

- Capabilities: delta to `robot-agent-supervisor`.
- Callers: `robot.py` confirmation-recovery decision point; reuses the
  existing send-and-wait prompt machinery and bounded waits.
- Contracts: adapter untouched; no config keys; token protocol is
  prompt text plus strict parser.
- Failure behavior: every ask outcome (DONE/WORKING/timeout/garbage)
  maps to an existing behavior; no new stuck states.
- Tests: token parser matrix, one-ask guard, timeout fallback,
  WORKING reset, DONE passthrough.
- Compatibility: boundaries that never hit this ambiguity behave
  byte-identically to today.

## Capabilities

- robot-agent-supervisor (delta)

## Non-goals

- Replacing quiescence or file evidence (they stay primary).
- Free-text interpretation of the reply (exact token or nothing).
- Asking on the archive path (evidence complete needs no question).
- Multiple languages or synonyms for the tokens.
