# Security policy

## Supported versions

Only the latest tagged release (currently `0.1.0`) receives security fixes.
Pre-release `0.x` versions are supported on a best-effort basis.

## Scope notes

- Ariadex orchestrates Coding CLIs you already run; it never calls a
  provider LLM API itself and stores no API keys.
- tmux and provider CLIs (`opencode`/`codex`) are external host
  prerequisites, never bundled artifacts.
- `.ariadex/runs/` logs and `metrics.jsonl` may contain shell output from
  your own commands. Review them before sharing.

## Sensitive data handling

- Run logs and metrics are redacted before persistence: OpenAI-style
  keys, AWS access keys, PEM private-key blocks, `password=`/`token=`
  assignments, `Bearer` tokens, GitHub (`ghp_`/`gho_`/`github_pat_`) and
  GitLab (`glpat-`) tokens, Slack tokens, JWTs, and AWS secret fields are
  replaced with `<redacted>`. Only the redaction count is recorded
  (`redactions:` in logs, `redactions` in metrics); matched values are
  never stored.
- Redaction is heuristic, not a guarantee. Treat logs as sensitive,
  review `export-logs` output before sharing, and rotate any credential
  that touched a prompt or shell output.
- Telemetry files use restrictive permissions where supported (directories
  `0700`, files `0600`). On Windows, POSIX modes do not apply and `doctor`
  reports the platform fallback; Windows ACLs govern access instead.

## Retention, backup, and recovery

- Retention is explicit and bounded via `log_retention_days` (default 30,
  `0` keeps everything), `log_max_bytes` (default 10485760), and
  `metrics_max_bytes` (default 5242880, `0` disables that cap). Bounds are
  enforced after every cycle and on demand via `ariadex prune-logs`
  (confirmation required for interactive use; `--yes` skips the prompt).
- `prune-logs` and size rotation remove only telemetry under
  `.ariadex/runs/` and `metrics.jsonl`, oldest first, and report what was
  removed or retained. Handoff history (`.ariadex/handoff.md`), state,
  config, and lock files are never touched; deletion never claims work
  was undone.
- `ariadex export-logs --out DIR` copies telemetry only into `DIR`,
  refusing when the payload exceeds `--max-bytes` (default 52428800) so an
  unbounded export cannot fill the disk. Back up `DIR` with your usual
  tools; to recover, copy the files back and run `ariadex doctor` and
  `ariadex recover` to reconcile state before resuming.

## Reporting a vulnerability

Open a GitHub issue at <https://github.com/lileililiwen/ariadex/issues>
with the `security` label, or contact the maintainers through the same
tracker. Include:

- affected version (`ariadex --version`)
- steps to reproduce
- impact assessment, if known

Do not include secrets, API keys, or private log contents in the report.
Maintainers will acknowledge receipt, assess, and publish a fix with a
`CHANGELOG.md` entry.
