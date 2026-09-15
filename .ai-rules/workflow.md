# Change workflow

Use this sequence for each non-trivial change. OpenSpec defines the intended
behavior; implementation evidence determines whether it is complete.

## 1. Breadth analysis

- Read `README.md`, `ROADMAP.md`, `HANDOFF.md`, the active proposal/design/
  tasks/spec delta, and the relevant canonical specs.
- Map affected concepts, modules, contracts, callers, persistent data, CLI
  surfaces, tests, compatibility, and provider/host boundaries before editing.
- Select exactly one active change with `openspec list`. If none exists, make
  no product implementation and report the planning gap.
- Identify relevant architecture and concern rules before deep work.

## 2. Structural pass

Establish the coherent shape of the change: domain types, contracts, function
signatures, DTOs/events, dependency wiring, callers, and test skeletons. Keep
the project compiling when practical, but label this state `SKELETON_READY`;
compilation does not prove behavior. Do not broaden scope beyond the selected
change.

## 3. Depth implementation

Implement one requirement/scenario at a time through the affected layers:
domain logic, application flow, infrastructure, and external integration.
For each scenario, cover success, failure, and relevant boundary behavior.
Preserve Ariadex's durable state, human-control, adapter, and ownership
invariants. Update the active `tasks.md` as verified work completes.

## 4. Breadth verification

Revisit the full impact map: requirements and scenarios, callers, persistence,
CLI/API compatibility, permissions, validation, logging/redaction, events,
concurrency, recovery, and current-change placeholders. Run relevant tests,
project checks, and strict OpenSpec validation before archive. Resolve or
explicitly record any gaps; do not defer first verification to CI.

## Archive and delivery

Archive only after local verification and promotion of the change into
canonical specs. Never use `--skip-specs`. Commit only implementation, tests,
archive, and related canonical spec updates. Then update `HANDOFF.md` with
evidence and the next change, commit only that update, and stop. Do not push.

For a fresh development checkout, run `ariadex dev setup` first. The normal
verification commands are documented in `README.md`; strict change validation
is `openspec validate --changes --strict --no-interactive`.
