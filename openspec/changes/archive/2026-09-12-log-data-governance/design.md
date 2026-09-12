## Approach

Keep local logs as the default, but make retention explicit and bounded. Apply redaction before persistence, use restrictive permissions where supported, and provide operator-controlled export and deletion with clear scope and confirmation.

## Data contract

Metrics and logs receive schema versions, session/spec identity, timestamps, and redaction status. Deletion must not alter handoff history or claim work was undone.

## Dependencies

Depends on existing logging and human-supervision ergonomics. Remote export remains a separate concern.

