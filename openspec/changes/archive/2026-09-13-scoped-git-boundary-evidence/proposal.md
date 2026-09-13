# Proposal: Scope Git Evidence at the Conversation Boundary

## Why

The watcher currently treats every `git status --porcelain` entry as user
work. Ariadex-owned `.ariadex/` runtime records can therefore block a proven
OpenSpec boundary, so the next provider conversation is never opened.

## What Changes

- Keep Git status as the source of repository-work evidence.
- Exclude Ariadex-owned `.ariadex/` runtime state from that evidence.
- Continue combining the filtered Git result with `openspec list --json`,
  `openspec status --change <recorded-spec> --json`, canonical-spec listing,
  strict validation, and archive proof before opening the next conversation.
- Add a regression test proving an archived recorded spec advances to the
  active next spec while runtime state is dirty.

## Non-goals

- Do not ignore user source, `HANDOFF.md`, or OpenSpec changes.
- Do not weaken contradictory or unavailable OpenSpec evidence.
- Do not change provider reset commands or readiness detection.
