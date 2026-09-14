# Tasks

- [x] Add the durable managed-generation record and typed lifecycle states for
      daemon, provider, widget, shutdown reason, and cleanup outcome.
- [x] Move managed adapter/provider/widget/watcher startup into the daemon and
      make the daemon the only provider-input writer.
- [x] Reduce `ariadex start` and attach/Ctrl+C handling to daemon ensure and
      typed control requests; remove foreground watcher ownership.
- [x] Implement ordered, bounded daemon cleanup for stop, widget Quit, and
      Ctrl+C, including ownership clearing and explicit-generation reset.
- [x] Make startup reuse require a live responsive daemon generation and make
      operator-stopped generations start a fresh provider backend.
- [x] Add regression tests for first-prompt delivery, one watcher, process
      topology, shutdown ordering, widget/provider termination, and no reuse.
- [x] Update README, PROJECT-GUIDE, and HANDOFF; run focused/full verification,
      strict OpenSpec validation, archive this change with canonical spec
      updates, and commit implementation plus documentation according to
      AGENTS.md.
