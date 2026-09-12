## Why

Ariadex is currently runnable only from a source checkout. It has no package metadata, version, dependency declaration, wheel, or supported installation path.

## What Changes

- Package `src/ariadex` with a console entry point.
- Declare Python and PyYAML requirements and a project version.
- Build and validate sdist/wheel artifacts.
- Add license, changelog, security contact, and installation documentation.

## Non-goals

- No bundled Coding CLI, tmux binary, provider API, or daemon.

