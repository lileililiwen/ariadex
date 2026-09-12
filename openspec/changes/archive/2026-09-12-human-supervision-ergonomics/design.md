## Approach

Keep the CLI as the primary interface. Add read-only `doctor`, queue/status views, JSON output, and explicit confirmation for operations that will send provider input. Mutations must use the existing handoff lifecycle and retain history.

## Safety

Preview must show mode, provider, target action, unresolved items, verification commands, and prerequisite results. Confirmation must be required unless an explicit non-interactive flag is provided and the caller accepts the risk.

## Dependencies

Depends on the existing control, handoff, and verification modules. It should precede remote monitoring.

