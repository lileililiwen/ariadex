## 1. Foundation

- [x] 1.1 Create the application and test project layout.
- [x] 1.2 Define configuration, mode, session, and state types.
- [x] 1.3 Implement YAML configuration loading, defaults, and validation.
- [x] 1.4 Implement durable state read/write with atomic replacement.

## 2. CLI

- [x] 2.1 Implement `init` without overwriting user files.
- [x] 2.2 Implement `status`, `pause`, and `resume` state transitions.
- [x] 2.3 Implement `takeover` and `auto` command placeholders with explicit lifecycle semantics.
- [x] 2.4 Add command and serialization tests.

## 3. Verification

- [x] 3.1 Run relevant tests and record the exact command in `HANDOFF.md`.
- [x] 3.2 Run `openspec validate --changes --strict --no-interactive`.
