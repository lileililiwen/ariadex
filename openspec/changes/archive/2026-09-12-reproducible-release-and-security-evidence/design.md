## Approach

Document and test two supported modes: an online clean build/security environment and an offline/reused-tool-cache diagnostic mode. Make `ariadex evidence --tmux-bin PATH` the deterministic path for a locally supplied tmux binary, and report the absolute binary path and version. Keep `--local-tmux` isolated and side-effect-free.

## Evidence

The release checklist must distinguish source-checkout commands from installed-package commands, and must record whether `pip-audit`, build, provider, and tmux checks were actually executed or only historically recorded.

## Dependencies

Depends on existing live evidence and packaging. Release publication consumes the resulting evidence report.

