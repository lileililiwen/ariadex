# Design: Development environment bootstrap

`ariadex dev setup` is an explicit, opt-in project command. It uses the
repository root as its target, checks for `uv`, and installs it user-scoped
only after confirmation (or with `--yes`). The installer must support the
official installer on supported platforms and clearly report unsupported
platforms or failed installation without modifying system Python.

Once `uv` is available, the command runs `uv sync --extra dev` and verifies
that the lockfile and declared tools, including `pip-audit`, are available
through `uv run`. A later invocation is idempotent. `--no-dependency-install`
reports the missing toolchain without mutation, matching the existing
prerequisite safety model.

CI and release workflows use the official `setup-uv` action, `uv sync
--frozen --extra dev`, and `uv run` for quality/security commands. The
committed lockfile is the shared resolution; CI must fail if it is stale.

The command does not alter Ariadex runtime configuration, install tmux, or
install the desktop companion. It records actionable failures and never
reports the environment ready unless all required setup and verification
steps pass. Tests cover detection, confirmation, successful and failed
installation, locked sync invocation, verification, idempotence, and the
workflow contract without network access.
