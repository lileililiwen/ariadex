# Proposal: Generic provider directory approval

## Why

A provider directory-access prompt (for example OpenCode's `Access
external directory` selector with a pattern list) stalls an unattended
run and stays silent: the provider process still reports busy, so the
watcher keeps classifying the surface as working and never reaches the
permission branch — no diagnostic, no widget reason. When the branch is
reached, the file-request parser does not understand directory-access
wording or multi-pattern lists, so even the explicit `auto` policy waits.
Operators who opted into hands-off supervision get a silent stall for a
routine directory grant.

## What Changes

- Approval classification wins over a busy provider process state: a
  capture tail carrying approval markers routes to the permission branch
  even while the provider reports active/busy. Safety is unchanged: the
  branch still only auto-approves per policy and otherwise waits with a
  recorded reason.
- The permission parser generically recognizes provider directory-access
  requests (directory/folder wording with one unambiguous primary
  directory plus an optional pattern list), with no path literal for any
  concrete directory. Ambiguous surfaces stay unparsed and wait.
- Parsed directory requests evaluate against the existing policies
  (`project-temp-auto`, `allowlist`, `auto`) and `permission_actions`
  exactly like file requests, including containment, traversal/symlink
  refusal, and privileged-marker refusal.
- The approval keystroke contract becomes selector-aware through the
  adapter: providers whose permission surface is a choice selector get an
  adapter-owned key sequence (navigate to Allow, confirm) sent through
  the terminal driver instead of the single `y` text. Every approval is
  still sent at most once per distinct request with the same dedup key.

## BFS Impact Map

- Capabilities: delta to `robot-agent-supervisor` (approval
  classification + directory permission evaluation).
- Callers: `robot.py` (`classify_capture`, `_poll_observed`,
  `_handle_approval`), `permissions.py` (parse + evaluate),
  `adapters.py`/`providers.py` (approval input contract),
  `terminal.py` (key-sequence delivery).
- Contracts: diagnostic schema unchanged (same fields, directory path in
  `requested_path`/`normalized_path`); dedup semantics unchanged;
  `permission_approve_input` stays for text surfaces.
- Failure behavior: unparsed/ambiguous, traversal, symlink escape,
  privileged markers, disabled operations, and unknown policies keep
  current wait/deny outcomes with reasons.
- Tests: classification matrix (busy+approval), parser matrix (generic
  directory surfaces, no concrete-path fixtures outside tmp), policy
  matrix per directory operation, selector key-sequence delivery, dedup.
- Compatibility: default `prompt` behavior byte-identical; text-surface
  approvals unchanged.
- Privacy/security: directory grants stay policy-gated; shared,
  world-writable, or other-user locations are never allowlisted by
  default and require an explicit operator entry.

## Capabilities

- robot-agent-supervisor (delta)

## Non-goals

- Hardcoding any concrete directory path in product code or tests
  (fixtures use the platform temporary directory only).
- Changing the default policy (stays `prompt`).
- Approving unparsed surfaces under any policy.
- Provider-side auto flags or widget click controls (the widget keeps
  showing status; approvals travel as keystrokes).
