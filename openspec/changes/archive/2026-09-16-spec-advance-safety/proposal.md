# Proposal: Safe spec advance

## Why

A finished spec advances into the next spec while its work may still
be uncommitted, mingling two specs on one tree — and nobody ever asks
the agent "finished and committed?" first. Separately, the advance
itself freezes two ways: scrollback commands (for example `cat`) push
directory prompts down the file path where they die as ambiguous, and
the bare word "confirm" in ordinary agent prose ("commit only when
you confirm") classifies as a live approval, so the watcher waits
forever instead of verifying completion. And when the watcher is
unsure — an unparsable approval, an undecided surface — it either
waits silently or resets into a new conversation instead of simply
asking the agent. Operators get a stuck run, a silent wait, or a
mingled tree.

## What Changes

- Before advancing on a complete boundary, the watcher asks the
  agent in the current conversation a natural confirm question:
  finished and committed? If the reply gives a clear answer, the
  watcher routes on it; if the reply is unclear, a strict backup
  follows — reply with exactly one line, DONE or NOT DONE. A clear
  yes (or DONE) advances as today; a clear no (or NOT DONE) waits
  again with no reset. Timeout or garbage keeps today's advance —
  the ask is a veto, never a new requirement. No git is consulted
  anywhere: with many uncommitted files in a tree (caches,
  artifacts, drafts), only the agent can judge what "committed"
  means.
- Anything the watcher is unsure about gets the same two-step
  treatment instead of silence or a blind new conversation. First
  case: an unparsable or ambiguous approval first asks the natural
  confirmation (what is showing, please answer the prompt in the
  session), then the strict DONE-or-NOT-DONE backup only if the
  reply is unclear — and keeps waiting on every outcome. Approvals
  never reset, and the ask fires once per approval episode, not
  every poll.
- A failed file parse falls through to the directory-access attempt
  instead of stopping, so scrollback commands no longer hide a
  directory prompt.
- Approval markers become UI phrases: bare `confirm` is replaced by
  `enter confirm`, `enter to confirm`, `confirm?`, `confirm:`, so
  agent prose no longer freezes the run as a false approval.

## BFS Impact Map

- Capabilities: delta to `robot-agent-supervisor` (commit ask before
  advance, unconfirmed approval ask, directory parse, markers).
- Callers: `robot.py` (continuation advance, approval branch, parse
  fallback); `permissions.py` (parse fallback); diagnostics carry new
  asks and replies opaquely, no schema change.
- Contracts: confirm-then-backup replaces single-shot asks for the
  new flows; the strict reply set is DONE / NOT DONE (WORKING still
  accepted as "not done" for older agents); all existing decisions,
  asks, and prompts unchanged.
- Failure behavior: WORKING vetoes the advance and waits; unparsed
  approvals wait with one ask per episode and never reset; ambiguous
  surfaces still wait; clean advances flow as today.
- Tests: commit-ask matrix (DONE advances, WORKING waits, garbage
  advances as today, one ask per advance), unconfirmed-ask matrix
  (single ask per episode, never resets, all outcomes wait), parse
  matrix with file-word scrollback, marker matrix with agent prose —
  every new test proven to fail on the old code.
- Compatibility: default prompts unchanged; two new fixed protocol
  questions only.
- Privacy/security: asks travel the existing prompt channel;
  approvals stay policy-gated with dedup unchanged.

## Capabilities

- robot-agent-supervisor (delta)

## Non-goals

- Judging commit state from git (uncommitted files are normal; only
  the agent judges).
- Auto-committing, branch, message, stash, push, or history policies.
- Approving unparsed surfaces under any policy.
- Resetting the conversation on approvals, ever.
