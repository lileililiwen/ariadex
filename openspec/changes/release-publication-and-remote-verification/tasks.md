## 1. Repository verification

- [x] 1.1 Add and verify the canonical `origin` remote.
- [x] 1.2 Verify default branch, required status checks, pull-request protection, and release-environment reviewers.
- [x] 1.3 Run CI on the remote and record the workflow URLs and outcomes.

## 2. Release verification

- [ ] 2.1 Configure PyPI trusted publishing scoped to the canonical workflow.
- [ ] 2.2 Run a maintainer-reviewed tag release with no skipped live evidence.
- [ ] 2.3 Verify PyPI metadata, hashes, install, `ariadex --version`, `init`, and `status` from the published artifact.

## 3. Handoff

- [ ] 3.1 Record exact release version, workflow runs, artifact hashes, and external permissions.
- [ ] 3.2 Preserve a manual rollback/yank procedure and next release action.

