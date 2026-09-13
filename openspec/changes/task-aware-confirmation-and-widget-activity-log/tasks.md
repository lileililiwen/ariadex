# Tasks

- [ ] Add and validate `confirmation_prompt` in configuration defaults,
      loading, migration, initialization prompts, and managed-start prompt
      resolution; preserve existing values and test blank/default behavior.
- [ ] Restore task completion as a boundary check and add a boundary decision
      result that distinguishes complete, unfinished, empty queue, and invalid
      metadata without silently discarding open tasks.
- [ ] Extend `RobotConfig` and `RobotWatcher` to select
      `confirmation_prompt` for valid unfinished tasks, open a fresh provider
      conversation only after the provider is ready, and repeat bounded
      confirmation attempts until tasks complete or a real blocker occurs.
- [ ] Add watcher activity-event recording with bounded retention and safe
      redaction; record prompt selection, provider readiness, boundary checks,
      unfinished task details, new-conversation failures, waiting states,
      pause/resume, and shutdown without recording raw captures or secrets.
- [ ] Extend the widget status model and text formatter with the latest event
      and bounded activity entries while preserving daemon truth for Pause,
      Play, Stop, and Quit controls.
- [ ] Add a collapsed/expanded robot-widget log panel with read-only scrolling,
      stable middle-right placement, no provider focus capture, and graceful
      rendering of empty, long, unreachable, and blocked logs.
- [ ] Add regression tests for configuration/init migration, task-aware prompt
      selection, repeated confirmation, completion/empty-queue behavior,
      provider readiness/quota/error safety, event bounds/redaction, pure view
      models, formatter output, and Tk expand/collapse wiring.
- [ ] Update README, PROJECT-GUIDE, and HANDOFF with the fourth prompt,
      unfinished-task recovery semantics, widget log behavior, and verification
      evidence; run the full test suite, Ruff, and strict OpenSpec validation.
