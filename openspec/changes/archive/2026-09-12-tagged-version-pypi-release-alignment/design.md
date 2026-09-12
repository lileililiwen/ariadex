# Design: Tagged version and PyPI release alignment

## Canonical version

The package’s single source of truth remains `ariadex.__version__`. A release
tag MUST be exactly `ariadex-v<that version>`. The workflow must check the tag
before building and again inspect the wheel and sdist metadata after building.

## GitHub workflow

Only pushes of `ariadex-v*` trigger publication. The workflow checks out the
tag commit, runs all tests and quality gates, builds the artifacts, and uses
trusted PyPI publishing. It must reject an existing or mismatched version
before publication. Ordinary branch pushes may run CI but never publish.

## Post-publish proof

After publication, the workflow must install the exact version from the PyPI
index in a fresh environment, verify `ariadex --version`, and run a clean
directory smoke test. A successful workflow must identify the tag, package
version, artifact filenames, and verified PyPI version in its summary.

## Failure and rollback

Any mismatch or failed gate stops before publishing. If publication succeeds
but index verification fails, the release is incomplete and the handoff must
record the exact version, tag, and remediation; it must not silently publish a
replacement under the same version.
