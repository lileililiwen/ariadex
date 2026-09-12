## Why

Run logs contain provider prompts and raw output. Current redaction is heuristic and there is no retention, rotation, permission, export, or deletion policy.

## What Changes

- Add configurable retention and size limits.
- Harden local file permissions and redact structured secrets.
- Add safe export/deletion and document sensitive-data handling.

## Non-goals

- No claim of perfect secret detection or default remote log storage.

