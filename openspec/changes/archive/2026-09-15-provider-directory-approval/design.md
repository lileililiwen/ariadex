# Design: Generic provider directory approval

Directory-access prompts are a distinct provider surface from
file-operation prompts: they name a directory (not a file action) and
often list match patterns. The design treats them as first-class parsed
requests with the same fail-closed gates as file requests, and routes
them through the existing policy engine plus a selector-aware approval
contract. No concrete directory path appears in product code; containment
is always computed from operator configuration at runtime.

- **Classification:** `classify_capture` checks approval markers before
  consulting provider process state, so a tail containing an approval
  surface classifies as approval even when `provider_state()` reports
  active/busy. `_poll_observed` routes that to `_handle_approval` as
  today. Pure busy output with no approval markers is unaffected.
- **Parsing:** `parse_permission_request` additionally recognizes
  directory-access wording (generic directory/folder/external-access
  synonyms) with exactly one unambiguous directory on the access line
  itself; surrounding pattern and history lines are context only and
  never widen the grant (the tail includes scrollback, so only the
  access line may contribute the path). A globbed or multi-directory
  access line stays unparsed. Privileged-marker, shell-character, and
  ambiguity refusals are unchanged. The directory operation is recorded
  as `read` of the directory itself and gated by `permission_actions`
  like any file request.
- **Evaluation:** parsed directory requests flow through `evaluate()`
  unchanged: `project-temp-auto`/`allowlist` require containment in the
  temp root/allowlist entries, `auto` approves any parsed request with
  an enabled operation, traversal/symlink-escape/privileged outcomes are
  preserved. The normalized directory path lands in the existing
  diagnostic fields.
- **Approval delivery:** the adapter contract gains an optional
  selector-aware approval sequence (ordered terminal keys, e.g. navigate
  to the Allow choice and confirm); the terminal driver gains a
  key-sequence send operation implemented with `tmux send-keys` named
  keys. Text surfaces keep using `permission_approve_input`. Dedup (once
  per provider+operation+normalized-path) covers both delivery modes.

## Testing

Unit matrices for classification (busy+approval vs busy alone),
directory parsing (wording variants, pattern lists, ambiguous and
privileged cases), and policy evaluation per directory request; adapter
and driver fakes for the key-sequence path; existing permission suites
must pass unchanged. Live verification is manual: attach to a provider
session showing a directory prompt under `auto` and confirm one approval
plus a recorded diagnostic.
