# Design: first-run agent and prompt configuration

## Configuration contract

Add durable project configuration values for:

- `agent_provider`: one of the registered provider names; default `opencode`.
- `first_prompt`: the prompt sent when the first provider conversation becomes
  ready.
- `continuation_prompt`: the prompt sent after a verified conversation boundary;
  default `Please read the HANDOFF.md, and implement the next spec.`.

Use the existing configuration loader, validation, atomic persistence, and
provider registry. Do not persist executable paths, shell fragments, tmux
commands, session names, or implementation-only polling values as part of this
user-facing setup.

## First initialization

`ariadex init` detects the absence of the project initialization/configuration
state. It asks one question for each configurable value. An empty answer, an
explicit skip, or an omitted optional answer selects the built-in default.
The wizard validates the provider before writing configuration. Invalid input
must be rejected and re-prompted without creating partial initialization.

The initialization operation must be atomic from the user’s perspective:
create the directory and files only after all answers validate. Existing
non-Ariadex project files are never touched.

## Existing initialization

When initialization already exists, plain `ariadex init` must fail with a
short message directing the user to `ariadex init --force`. It must not prompt,
overwrite config, reset state, or alter logs.

`ariadex start` must not invoke this wizard implicitly. An uninitialized
project fails with an instruction to run `ariadex init`.

## Destructive reset

`ariadex init --force` must:

1. Verify the target is the current project’s `.ariadex` directory.
2. Explain that all Ariadex runtime state will be removed.
3. Require interactive confirmation unless an explicit internal/non-interactive
   confirmation is supplied by the existing CLI convention.
4. Remove the complete `.ariadex` directory, including config, state, daemon
   records, locks, cancellation signals, logs, events, and runtime metadata.
5. Recreate a clean initialization through the same wizard.

It must preserve `HANDOFF.md`, `openspec/`, source files, untracked project
files outside `.ariadex`, and git history. If deletion or recreation fails,
report the exact phase and do not claim a successful initialization.

## Compatibility

Existing configuration files without the new prompt keys receive defaults on
load or migration according to the current config conventions. Existing
advanced commands continue using their current handlers; this change only adds
the values needed by managed startup.

## Tests

Cover first-run defaults, custom answers, invalid provider retry, blank answers,
already-initialized refusal, `start` refusal without initialization, force
confirmation/decline, complete `.ariadex` reset, preservation of project
artifacts, failed reset reporting, and config round trips.
