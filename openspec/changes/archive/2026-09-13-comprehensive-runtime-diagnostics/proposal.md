# Proposal: Comprehensive runtime diagnostics

## Problem

The current widget message is too small to explain lifecycle decisions. It
cannot show why a prompt was selected, why a boundary failed, which OpenSpec
evidence was observed, or whether the provider was waiting, ready, or blocked.
Existing run logs, metrics, and events are separate and difficult to collect
as one debugging record.

## Outcome

Create a structured, bounded diagnostic stream with events at every important
runtime boundary and a user-facing full-log retrieval/export command. The
live widget consumes a safe recent projection; later research can use a full
diagnostic bundle without relying on terminal scrollback.

## Scope and non-goals

- Record lifecycle, provider, OpenSpec, prompt, boundary, process, widget,
  prerequisite, pause, quota, error, and shutdown events.
- Keep raw provider captures out of normal diagnostics; retain only bounded,
  redacted evidence references and classifications.
- Add a machine-readable full export with stable schema and bounded size.
- Do not add remote telemetry, provider API calls, or automatic log upload.
