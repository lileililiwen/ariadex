Variable parts are adapter-owned: provider markers, composer parsing, API
status interpretation, and reset input such as OpenCode `/new`. Stable parts
are watcher policy, `InputSurface` values, pause checks, durable recording, and
the rule that only `EMPTY` permits automatic input. Codex and CodeBuddy use the
same interface and may conservatively return `UNKNOWN` until their surfaces
are verified.
