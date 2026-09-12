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

## Reporting a vulnerability

Open a GitHub issue at <https://github.com/anomalyco/opencode/issues>
with the `security` label, or contact the maintainers through the same
tracker. Include:

- affected version (`ariadex --version`)
- steps to reproduce
- impact assessment, if known

Do not include secrets, API keys, or private log contents in the report.
Maintainers will acknowledge receipt, assess, and publish a fix with a
`CHANGELOG.md` entry.
