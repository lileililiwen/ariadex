## Approach

Create a reproducible CI pipeline with separate fast unit, live tmux, static-quality, security, and artifact jobs. Required checks must fail closed; environment-dependent live checks must be explicitly labeled and cannot silently become green when skipped.

## Quality policy

Pin or constrain tools in development metadata, define a minimum coverage threshold after measuring the baseline, and scan dependencies and built artifacts. Keep the standard-library test framework unless a migration is justified.

## Dependencies

Consumes packaging metadata and live evidence commands. It is the release gate for subsequent changes.

