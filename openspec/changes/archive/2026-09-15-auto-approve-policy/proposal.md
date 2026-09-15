# Proposal: Hands-off auto-approve policy

## Why

The existing policies (`prompt`, `project-temp-auto`, `allowlist`,
`deny`) all interrupt an absent operator for something: unlisted paths,
unparsed-but-benign surfaces, or routine work outside the temp root.
For an operator whose safety net is version control and who optimizes
for zero interruptions, there must be one explicit policy that approves
every parsed request and only stops for what cannot be understood.

## What Changes

- Add an explicit opt-in `auto` permission policy: any parsed request
  whose operation is in `permission_actions` is approved with the
  adapter-owned keystroke, regardless of path. Default stays `prompt`.
- Unparsed surfaces still wait under `auto`: approval without a parsed
  operation and path is never sent.
- `permission_actions` remains the operation gate (default
  read/write/create/delete; adding execution-class operations is the
  operator's explicit choice and is labeled dangerous in config docs).
- Canonical `robot-agent-supervisor` permission requirements gain the
  opt-in and its boundary.

## BFS Impact Map

- Capabilities: delta to `robot-agent-supervisor` (permission policy).
- Callers: `permissions.py` (`evaluate` + policy list), `config.py`
  docs/defaults, `cli.py` init prompts listing policies.
- Contracts: adapter `permission_approve_input` reused; diagnostic
  schema unchanged; dedup (once per distinct request) unchanged.
- Failure behavior: unknown policy names, unparsed surfaces, and
  disabled operations keep current wait/deny outcomes with reasons.
- Tests: policy matrix (allow/wait/deny), config acceptance, init
  prompts, diagnostic recording.
- Compatibility: default config unchanged; existing policies byte-
  identical behavior.

## Capabilities

- robot-agent-supervisor (delta)

## Non-goals

- Changing the default policy (stays `prompt`).
- Approving unparsed surfaces (never approved under any policy).
- Provider-side auto flags (orthogonal; untouched).
- Widget, transport, or watcher-policy changes.
