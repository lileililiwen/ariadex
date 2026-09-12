## 1. Verification

- [ ] 1.1 Implement configured command execution with exit code and timeout capture.
- [ ] 1.2 Implement pass/fail gate and bounded retries.
- [ ] 1.3 Persist failed verification as unresolved work or blocker.

## 2. Logs and metrics

- [ ] 2.1 Implement session log writer under `.ariadex/runs/`.
- [ ] 2.2 Implement metrics JSONL writer with explicit unavailable usage.
- [ ] 2.3 Add redaction and append/recovery tests.

## 3. Status

- [ ] 3.1 Implement operator status projection.
- [ ] 3.2 Add status tests for fresh context, unresolved counts, failures, and elapsed time.

## 4. Verification

- [ ] 4.1 Run tests and strict OpenSpec validation; record results in `HANDOFF.md`.
