## 1. Toolchain

- [ ] 1.1 Define a reproducible development environment for build, coverage, and pip-audit.
- [ ] 1.2 Add a documented preflight that reports Python, package, pip-audit, build, provider, and tmux locations/versions.
- [ ] 1.3 Add an offline or cached-build verification path and record its limitations.

## 2. tmux evidence

- [ ] 2.1 Verify `--tmux-bin PATH` against a user-supplied local binary with no install/removal.
- [ ] 2.2 Verify `--local-tmux` fetch/extract/cleanup and report the resolved absolute binary.
- [ ] 2.3 Verify the full no-skip evidence gate on a host or supplied binary where tmux is available.

## 3. Security evidence

- [ ] 3.1 Run the pinned pip-audit command in a network-enabled environment.
- [ ] 3.2 Record vulnerabilities, exemptions, or a clean result in release evidence.

