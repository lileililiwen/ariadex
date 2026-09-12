# Proposal: Tagged version and PyPI release alignment

## Why

Maintainers need a predictable release flow: pushing a version tag should
produce the same version on PyPI, without accidental mismatches or publishing
from an untagged commit.

## What changes

- Define the canonical tag format `ariadex-v<version>`.
- Validate that the tag, package metadata, built artifacts, and PyPI-installed
  package all use the same version.
- Make the GitHub release workflow build and publish only the tagged commit,
  then verify the exact version from PyPI.
- Document the maintainer command sequence and failure/rollback behavior.

## Non-goals

No automatic version guessing, mutable-release overwrites, or publishing from
ordinary branch pushes is included.
