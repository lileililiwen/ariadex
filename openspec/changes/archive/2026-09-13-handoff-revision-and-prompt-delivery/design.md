# Design: Hidden Ariadex Handoff State

## Storage boundary

The configured handoff filename remains a public human-document name. The
handoff module maps all public handoff paths to the fixed Ariadex-owned
`.ariadex/handoff.md` state path. Direct paths already inside `.ariadex/` are
left unchanged for internal callers and compatibility tests.

Initialization continues creating a plain public `HANDOFF.md`; it does not
write machine front matter there. Structured state is created only in the
hidden directory when Ariadex first persists it.

## Scheduling boundary

The robot reads hidden Ariadex state for its recorded conversation context,
but it does not require the public document to exist or be parseable. Inside
an OpenSpec repository, `openspec list --json`, status, archive proof, and
strict validation remain the scheduling evidence. Git is not queried by the
robot and cannot block a prompt or conversation transition.

## Failure behavior

Malformed hidden Ariadex state remains a real runtime-state error. Malformed,
missing, or arbitrary public HANDOFF text is ignored by scheduling. Provider
approval behavior remains unchanged: `prompt` waits for the operator and does
not resend the initial prompt.

## Verification

Tests prove that public HANDOFF text is preserved, structured state is hidden,
OpenSpec boundaries work without a public HANDOFF, and completed tasks do not
require Git state.
