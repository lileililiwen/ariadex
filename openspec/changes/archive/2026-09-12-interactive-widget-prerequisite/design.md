# Design: Interactive widget prerequisite installation

The existing dependency installer gains an `interactive_sudo` option. The
widget command sets it only after its foreground confirmation prompt succeeds
without `--yes`; automated `--yes` calls preserve the existing `sudo -n`
behavior. The daemon starts only after dependency installation and interpreter
verification succeed.
