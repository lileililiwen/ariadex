# Changelog

All notable changes to this project are documented here. Versioning is
informative while the project is pre-release (`0.x`); the packaged version
lives in exactly one place: `src/ariadex/__init__.py` (`__version__`), and
`pyproject.toml` reads it dynamically.

## [0.1.0] - 2026-09-12

### Added

- PEP 517/518 packaging (`pyproject.toml`, setuptools src-layout) with
  `ariadex` console entry point (`ariadex.cli:main`).
- Declared runtime: Python `>=3.11`, `PyYAML>=6`. No other runtime
  dependencies.
- `ariadex --version` reporting the single-source package version.
- `LICENSE` (MIT), `SECURITY.md`, and pip/pipx/source installation docs.
- sdist/wheel build validated by installing the wheel into a clean
  environment and running `ariadex --help` and `ariadex init`.

### Scope reaffirmed

- tmux and Coding CLIs (`opencode`/`codex`) remain external host
  prerequisites. Ariadex never bundles them and never calls a provider LLM
  API itself.

## [Unreleased MVP history]

- `project-foundation-and-cli`, `agent-adapters-and-tmux-driver`,
  `state-driven-runner-and-handoff`,
  `verification-logging-and-observability`, `human-control-and-resync`,
  `tmux-auto-install`, `live-runtime-evidence` (see `HANDOFF.md` and
  `openspec/specs/`).

## [Unreleased post-MVP foundations]

- `packaging-and-distribution`, `ci-quality-security-gates`,
  `human-supervision-ergonomics`, `single-runner-concurrency-and-recovery`,
  `log-data-governance`, `spec-dependency-and-execution-governance`,
  `metrics-export-and-notifications` (see `HANDOFF.md` and
  `openspec/specs/`). Notable surface: `doctor`, `preview`, `queue`,
  `history`, `resolve`/`defer`/`reopen`/`reprioritize`, `recover`,
  `prune-logs`, `export-logs`, `events`, `export-events`, per-change
  `depends_on` ordering, single-scheduler lease with crash recovery,
  telemetry retention/redaction, and opt-in redacted notifications.

## Release guidance

1. Bump `__version__` in `src/ariadex/__init__.py` only.
2. Add a `CHANGELOG.md` entry under a new version heading.
3. Build: `python3 -m build` (produces `dist/ariadex-<version>.tar.gz`
   and `dist/ariadex-<version>-py3-none-any.whl`).
4. Verify in a clean virtual environment:
   `pip install dist/ariadex-<version>-py3-none-any.whl`,
   then `ariadex --help` and `ariadex init` in a scratch directory.
5. Tag the release commit (`git tag ariadex-v<version>`).
