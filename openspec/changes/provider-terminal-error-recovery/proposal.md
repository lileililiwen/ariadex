## Why

A provider can stop a response with a recoverable terminal error while its
input surface remains usable. Ariadex currently classifies that surface as a
generic error and blocks before it evaluates the current OpenSpec change, so
the configured confirmation or continuation prompt is never sent.

## What Changes

Recognize provider-specific terminal-error surfaces as recoverable boundaries
when the provider is ready for input. Route them through the existing
task-aware OpenSpec decision and fresh-conversation adapter operation.

## Non-goals

Quota, authentication, approval, malformed evidence, and unavailable provider
surfaces remain waiting or blocked. Ariadex does not claim completion from an
error and does not call a provider API.
