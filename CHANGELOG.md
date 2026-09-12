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

## [Unreleased audit remediation]

- `active-spec-discovery-and-archive-isolation`: archived changes are
  never scheduled as active work.
- `bounded-run-completion-and-cycle-limit`: cycle-limit exhaustion is an
  explicit incomplete outcome, never success.
- `takeover-cancellation-and-scheduler-coordination`: takeover and pause
  cancel in-flight scheduling without new provider input.
- `canonical-spec-and-doc-governance`: complete canonical purposes,
  reconciled current/historical docs, and a consistency test.
- `real-provider-live-validation`: isolated real OpenCode/Codex lifecycle
  evidence (startup, probe, interrupt, reset, termination, restart).
- `repository-identity-security-and-release-readiness`: canonical
  repository `https://github.com/lileililiwen/ariadex`, issues-based
  security contact, and a fail-closed release dry run
  (`python -m ariadex.release --tag ...`).

## [Unreleased managed start]

- `2026-09-13-init-prompt-config`: `ariadex init` asks for the provider and
  first/continuation prompts (blank answers keep the built-in defaults);
  plain `init` refuses on initialized projects and `init --force` confirms,
  then removes only `.ariadex/` before reinitializing.
- `2026-09-13-prerequisite-coordinator`: one readiness path (runtime,
  provider CLI, tmux with automatic preparation, desktop/Tkinter widget)
  with typed `present`/`installed`/`unsupported`/`declined`/`blocked`
  results; providers are never installed and `uv` stays development-only.
- `2026-09-13-managed-start-facade`: `ariadex start` composes guard,
  config plus `--agent`/`--first-prompt`/`--continuation-prompt` overrides,
  prerequisites, one daemon, one adapter-owned tmux session, the detached
  widget, terminal attach, supervised first/continuation prompts, and
  reconciled shutdown (queue-empty completion, provider exit, detach,
  Ctrl+C). Duplicate starts report the live owner and create nothing.

## Release guidance

Version invariants (tag, package, artifacts, and PyPI must all agree):

- Single source of truth: `__version__` in `src/ariadex/__init__.py` only.
- A release tag MUST be exactly `ariadex-v<version>`.
- Built artifacts MUST carry the same version in their file names and in
  their embedded metadata (wheel `METADATA`, sdist `PKG-INFO`).
- The PyPI index MUST serve exactly the tagged version after publication.
- Versions are immutable: an already-published version MUST NOT be
  overwritten or republished. If publication succeeds but index
  verification fails, the release is incomplete — record the exact tag,
  package version, and remediation in `HANDOFF.md`; yank the broken
  release on PyPI if needed, then bump and tag a new version.

Maintainer sequence:

1. Bump `__version__` in `src/ariadex/__init__.py` only.
2. Add a `CHANGELOG.md` entry under a new version heading.
3. Build: `python3 -m build` (produces `dist/ariadex-<version>.tar.gz`
   and `dist/ariadex-<version>-py3-none-any.whl`).
4. Verify in a clean virtual environment:
   `pip install dist/ariadex-<version>-py3-none-any.whl`,
   then `ariadex --help` and `ariadex init` in a scratch directory.
5. Tag the release commit (`git tag ariadex-v<version>`).
6. Dry run (publishes nothing, must pass):
   `python -m ariadex.release --tag ariadex-v<version>` checks the
   canonical `origin` remote, package identity URLs, tag/version
   alignment, artifact presence and embedded metadata versions, and the
   security-reporting route. Add `--check-pypi` (as the release workflow
   does) to also reject an already-published version. Pushing the
   tag runs the release workflow, which re-verifies every gate and then
   publishes to PyPI via scoped trusted publishing, verifies the exact
   version from a clean-index install (`--version` compared against the
   tag, plus `init`/`status`), and records tag, package version,
   artifact hashes, and the verified PyPI version in the run summary.

Rollback: yank the release on PyPI and delete the tag and GitHub
release; never force-push `main`, never republish under the same
version.
