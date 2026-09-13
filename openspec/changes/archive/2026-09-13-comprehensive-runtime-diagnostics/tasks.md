# Tasks

- [x] Define the versioned diagnostic event schema and safe field/redaction
      policy for every managed lifecycle boundary.
- [x] Add secure bounded JSONL storage with atomic writes, retention, rotation,
      malformed-record handling, and concurrent-writer protection.
- [x] Instrument startup, OpenSpec selection, conversation identity, prompt
      delivery, provider readiness/wait/quota/error, boundary evaluation,
      verification, widget lifecycle, pause/resume, and shutdown.
- [x] Add an admin diagnostic read command with chronological text and JSON
      output, filters, bounded limits, and honest unavailable-state handling.
- [x] Add a local diagnostic bundle/export containing manifest, state, OpenSpec
      evidence, diagnostics, and selected telemetry with redaction and size
      limits.
- [x] Add focused and integration tests proving event completeness, ordering,
      redaction, bounds, failure isolation, and zero provider-input side effect.
- [x] Update README, PROJECT-GUIDE, admin help, security/logging docs, and
      HANDOFF with the full-log research workflow and verification evidence.
