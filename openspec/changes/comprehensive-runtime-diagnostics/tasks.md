# Tasks

- [ ] Define the versioned diagnostic event schema and safe field/redaction
      policy for every managed lifecycle boundary.
- [ ] Add secure bounded JSONL storage with atomic writes, retention, rotation,
      malformed-record handling, and concurrent-writer protection.
- [ ] Instrument startup, OpenSpec selection, conversation identity, prompt
      delivery, provider readiness/wait/quota/error, boundary evaluation,
      verification, widget lifecycle, pause/resume, and shutdown.
- [ ] Add an admin diagnostic read command with chronological text and JSON
      output, filters, bounded limits, and honest unavailable-state handling.
- [ ] Add a local diagnostic bundle/export containing manifest, state, OpenSpec
      evidence, diagnostics, and selected telemetry with redaction and size
      limits.
- [ ] Add focused and integration tests proving event completeness, ordering,
      redaction, bounds, failure isolation, and zero provider-input side effect.
- [ ] Update README, PROJECT-GUIDE, admin help, security/logging docs, and
      HANDOFF with the full-log research workflow and verification evidence.
