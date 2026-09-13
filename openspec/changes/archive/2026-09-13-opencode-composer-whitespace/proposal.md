# Proposal: Match OpenCode composer formatting safely

## Why

OpenCode's provider-owned footer spacing varies (`▣ Build` versus `▣  Build`),
causing Ariadex to miss an otherwise visible input-ready composer.

## What Changes

- Normalize only provider UI whitespace for the OpenCode composer/footer
  signal.
- Keep readiness independent of assistant message content.

## Non-goals

- Do not add completion keywords or prose parsing.
- Do not change OpenSpec boundary decisions.
