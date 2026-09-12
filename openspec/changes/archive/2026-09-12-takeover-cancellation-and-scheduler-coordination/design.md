## Design

Use a project-scoped cancellation signal observed before provider send, after send/capture, before verification, and before reset/next-cycle scheduling. A takeover or pause request must prevent any new provider input and mark an in-flight operation as cancelled or uncertain according to its persisted phase.

Coordinate mode changes with the scheduler lease. If a cycle cannot be interrupted safely, the command reports that cancellation is pending and the runner stops at the next safe boundary. Existing recovery semantics remain authoritative for uncertain delivery.

## Verification

Exercise takeover and pause during each phase with a controllable fake adapter/verifier. Assert no post-request provider input, preserved tmux identity, correct phase/recovery record, and no race-induced state loss. Test active-owner coordination and restart recovery.
