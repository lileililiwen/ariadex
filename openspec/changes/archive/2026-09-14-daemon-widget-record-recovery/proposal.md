## Why

The daemon can exit before readiness when an old widget record points to a
PID that has already disappeared. Widget health checking lets
`psutil.NoSuchProcess` escape instead of treating the record as unhealthy.

## What Changes

- Treat psutil lookup failures as an unhealthy widget record.
- Allow normal widget repair and daemon readiness to continue.

## Non-goals

- Do not reuse an unverified widget process.
- Do not change provider lifecycle behavior.
