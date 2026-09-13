# Design: Stale daemon owner recovery

On POSIX hosts, daemon liveness first checks `/proc/<pid>` and the recorded
process identity where available. A signal permission result alone is
insufficient because supervisors and sandboxes may return `PermissionError`
for nonexistent or uninspectable processes. The daemon socket must also be a
real endpoint for a live owner to be reusable.

If the record is stale or its socket is missing, `start` follows the existing
stale-owner reconciliation and creates one replacement daemon. It does not
create a second daemon when both process identity and socket are valid.
