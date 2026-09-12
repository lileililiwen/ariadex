## Approach

Use standard PEP 517/518 packaging with `pyproject.toml`, a console script named `ariadex`, and a single source of version truth. Runtime dependencies remain minimal; tmux and Coding CLIs remain host prerequisites.

## Release contract

Build artifacts must install into a clean virtual environment, expose `ariadex`, import successfully, and preserve the documented source/runtime boundary. Release metadata must include supported Python versions and license information.

## Dependencies

Independent of runtime feature work. CI quality gates should consume the artifact build defined here.

