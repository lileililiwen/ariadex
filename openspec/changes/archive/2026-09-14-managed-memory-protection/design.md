# Design: Managed host memory protection

The repository ships `scripts/setup-memory-protection.sh` as the single
operator entry point. It uses explicit paths, preserves existing swap, adds
`/swapfile-ariadex` only when absent, adds one exact `/etc/fstab` entry, and
rewrites the earlyoom argument assignment to a known safe policy. Repeated
runs therefore converge instead of appending duplicate configuration.

The script uses `--prefer` for browsers rather than `--avoid '^opencode$'`.
OpenCode remains eligible as a last-resort victim so the machine does not
trade one managed-session failure for a frozen desktop or system services.
The script deliberately leaves project ignore behavior, Node limits, and
dotnet build parallelism to verified project/provider configuration.

## Failure behavior

`set -euo pipefail` stops before claiming success when a privileged operation
fails. No `swapoff -a` is used. The final output reports active swap, the
persisted fstab entry, and earlyoom service state.
