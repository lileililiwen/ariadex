## ADDED Requirements

### Requirement: Commit question before advancing

Before advancing on a complete boundary, the watcher MUST ask the
agent a natural confirm question in the current conversation
(finished and committed?). If the reply gives no clear answer, a
strict backup MUST follow (reply with exactly one line, DONE or NOT
DONE). A clear yes (or DONE) advances as today; a clear no (or NOT
DONE) waits again with no reset and the question repeats on the next
advance. Timeout or garbage advances as today. Commit state is
judged only by the agent, never by inspecting the tree.

#### Scenario: Agent confirms finished and committed

- **WHEN** the agent clearly confirms, or the backup replies DONE
- **THEN** Ariadex advances with the continuation exactly as today

#### Scenario: Agent says still working

- **WHEN** the agent clearly declines, or the backup replies NOT
  DONE
- **THEN** Ariadex sends no `/new`, restarts the debounce count,
  keeps watching, and asks again on the next advance

### Requirement: Unconfirmed approval ask instead of silent waiting

On an unparsable or ambiguous approval surface, the watcher MUST
first ask a natural confirmation question in the current conversation
naming what is showing and asking the agent to answer the prompt in
the session, and only on an unclear reply follow with the strict
DONE-or-NOT-DONE backup. Every outcome MUST keep waiting without any
reset, and the ask MUST fire once per approval episode regardless of
tail churn.

#### Scenario: Unparsable approval pokes the agent once

- **WHEN** an approval surface cannot be parsed and the episode is
  new
- **THEN** Ariadex sends the confirmation question once and keeps
  waiting; later polls in the same episode send nothing more

#### Scenario: Approvals never reset the conversation

- **WHEN** any approval outcome resolves (DONE, WORKING, timeout,
  garbage)
- **THEN** Ariadex keeps waiting in the current conversation and
  never opens a new one

### Requirement: Directory parse survives file-word scrollback

A failed file parse (ambiguous paths, shell characters, blank) MUST
fall through to the directory-access attempt instead of returning
unknown. Successful single-path file parses MUST behave exactly as
today.

#### Scenario: Scrollback command hides a directory prompt

- **WHEN** the tail holds a directory prompt plus history lines that
  trigger the file path with extra paths
- **THEN** Ariadex still parses the single directory on the access
  line

### Requirement: Approval markers are UI phrases

Agent prose MUST NOT classify as a live approval. Bare `confirm`
MUST be replaced by UI phrases (`enter confirm`, `enter to
confirm`, `confirm?`, `confirm:`); live selector and `[y/n]`
surfaces MUST still classify as approval.

#### Scenario: Agent prose with confirm is not approval

- **WHEN** the tail holds prose such as "commit only when you
  confirm" with no approval UI
- **THEN** Ariadex does not classify approval

#### Scenario: Selector hints still classify

- **WHEN** the tail holds `select enter confirm` or equivalent UI
  hints
- **THEN** Ariadex classifies approval
