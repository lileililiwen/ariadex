# Design: Scoped Git Boundary Evidence

`robot._git_tree_clean` remains the Git evidence boundary. It invokes Git
with an explicit pathspec that includes the project and excludes
`:(exclude).ariadex/**`, while requesting all untracked files. A non-zero Git
result still blocks fail-closed; any remaining source, handoff, or OpenSpec
change still blocks completion/advancement.

The OpenSpec path remains authoritative for spec lifecycle decisions:
`openspec list --json` identifies the active queue, the recorded current spec
is checked with `openspec status --change --json`, and an absent active entry
must pass canonical-spec listing, strict validation, and archive-directory
proof. Only after these checks and the filtered Git evidence succeed does the
watcher call the provider adapter's `new_conversation` operation.

Tests use a real temporary Git repository with an untracked `.ariadex/` file
and the existing hermetic OpenSpec runner. This proves the actual pathspec
behavior rather than mocking the Git result.
