## 1. Coverage and failure paths

- [x] 1.1 Add focused tests for terminal/tmux setup failure, timeout, permissions, and cleanup paths.
- [x] 1.2 Add focused tests for concurrency/recovery and operator command failure paths.
- [x] 1.3 Add live-evidence harness fault-injection tests and raise or add per-module safety thresholds.

## 2. Static and documentation gates

- [x] 2.1 Add security lint rules for subprocess, shell commands, and secret handling with justified suppressions.
- [x] 2.2 Replace the no-active-change documentation skip with fixture-based active-change consistency tests.
- [x] 2.3 Add workflow syntax/structure checks and verify immutable action references.

## 3. Verification

- [ ] 3.1 Run the complete local quality suite and compare coverage to the current 83% baseline.
- [ ] 3.2 Run CI on the canonical remote and record required-check behavior.

