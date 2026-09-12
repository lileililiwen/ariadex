# Proposal: Development environment bootstrap

## Why

The project declares `pip-audit` and the quality tools in the `dev` extra,
but a fresh checkout still requires users to discover and install `uv`
manually. This makes the documented development and security workflow
incomplete and makes the local environment differ from CI.

## What changes

- Add an explicit `ariadex dev setup` command for preparing the development
  environment.
- Detect or install `uv` through supported user-scoped installation paths,
  with confirmation required unless `--yes` is supplied.
- Run the locked development sync and verify the required tools afterward.
- Commit `uv.lock` and make CI consume the same locked `dev` environment.
- Keep normal runtime installation separate from development-tool bootstrap.

## Non-goals

- Do not install development tools during ordinary `ariadex install`.
- Do not install system packages without explicit confirmation.
- Do not claim a clean security audit when the vulnerability service is
  unavailable.
