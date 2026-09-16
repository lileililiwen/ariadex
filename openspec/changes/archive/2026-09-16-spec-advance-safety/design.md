# Design: Safe spec advance

Three small mechanisms, each reusing an existing seam: the advance
asks one veto question; the approval branch asks one confirmation
question per episode; the parser falls through; one marker becomes
four phrases. Nothing else moves, and git is not consulted anywhere.

- **Commit ask before advance:** `_open_continuation`, before any
  reset, runs a two-step confirm in the current conversation through
  the existing bounded ask machinery under a `commit` kind (so it
  never shares the task ask's once-guard). Step one sends the
  natural confirm question ("finished and committed for this
  spec?"); step two, only when the reply carries no clear answer,
  sends the strict backup ("reply with exactly one line: DONE or
  NOT DONE"). Clear means a strict token on its own line (DONE, NOT
  DONE, or legacy WORKING) — everything else is unclear, judged
  mechanically, never guessed. A clear yes (or DONE) proceeds with
  the continuation exactly as today; a clear no (or NOT DONE)
  parks to watching with no reset and the debounce restarted, so
  the next finished screen asks again; timeout or garbage proceeds
  as today. The ask is a veto, not a requirement: it can only stop
  an advance, never demand one, and the agent's DONE is trusted for
  the advance because only the agent can judge its own commit state.
- **Unconfirmed approval ask:** `_handle_approval`, on an unparsable
  or ambiguous surface, runs the same two-step in the current
  conversation: the natural confirmation names what is showing and
  asks the agent to answer the prompt in the session; the strict
  backup follows only on an unclear reply. Every outcome then keeps
  waiting — DONE, NOT DONE, WORKING, timeout, garbage — and never
  resets. A consecutive-approval counter fires the ask once per
  episode (first repeat poll) and clears on any non-approval
  surface, so a stuck dialog gets exactly one poke no matter how
  the tail churns.
- **Parse fallback:** `parse_permission_request` tries the file parse
  first (behavior identical on success); any file failure (ambiguous,
  shell characters, blank) falls through to `_parse_directory_access`
  instead of returning None. Single-path file surfaces never reach
  the directory attempt, so existing outcomes are preserved.
- **Markers:** `APPROVAL_MARKERS` drops bare `confirm` for `enter
  confirm`, `enter to confirm`, `confirm?`, `confirm:`. Live
  selector hints (`select enter confirm`) and `[y/n]` surfaces still
  classify; agent prose no longer does.

## Testing

Commit-ask matrix (DONE advances, WORKING waits without reset,
garbage/timeout advance as today, fresh ask per advance); approval
matrix (single ask per episode across churning tails, never resets,
all outcomes wait; parsed approvals untouched); parse matrix
(file-word scrollback still finds the directory; ambiguous files
still None); marker matrix (prose not approval, selector hints
approval). Full focused suites must pass unchanged.
