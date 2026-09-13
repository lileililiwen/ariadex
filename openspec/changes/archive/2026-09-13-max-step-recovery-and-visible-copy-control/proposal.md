# Proposal: Max-step recovery and visible copy control

## Why

The managed workflow must recover from provider-imposed step limits without
silently stopping, and operators must be able to export diagnostics from the
normal collapsed widget when a run stalls.

## What Changes

Add recoverable max-step boundary handling and expose the bounded log-copy
control in the collapsed widget.

## Problem

OpenCode can stop a response after its maximum step limit and leave a usable
input surface. Ariadex currently classifies that text as a generic provider
error, enters `BLOCKED`, and never sends the configured task-recovery prompt.
The managed widget also places `Copy log` only in its expanded details, making
the control effectively invisible in the normal collapsed start view.

## Outcome

Classify known max-step-limit messages as recoverable conversation boundaries so
the existing task-aware confirmation/continuation decision can send the next
prompt after a fresh ready surface. Put `Copy log` in the always-visible
collapsed widget controls while retaining the expanded diagnostic context.

## Non-goals

Do not treat arbitrary provider errors as completion, bypass task or OpenSpec
verification, expose raw provider captures, or add external clipboard
prerequisites.
