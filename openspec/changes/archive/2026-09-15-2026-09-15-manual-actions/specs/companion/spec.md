## ADDED Requirements

### Requirement: Manual actions panel

The expanded widget MUST show a labeled Manual group with Retry,
Model (selectbox + Apply), and Message (textarea + Send) rows —
organized as labeled rows, never as tabs. Retry MUST resend the most
recent prompt verbatim or stay disabled; model apply MUST use only
the configured `models` list; message send MUST refuse empty text, a
present human draft, and PAUSE mode, recording the reason each time.

#### Scenario: Operator retries the due prompt

- **WHEN** the last prompt went unanswered and the operator presses
  Retry
- **THEN** the exact prompt text is sent once into the current
  conversation and the fresh status returns

#### Scenario: Operator corrects a diverging agent

- **WHEN** the operator writes a correction and presses Send with an
  empty composer
- **THEN** the text is sent into the current conversation once

#### Scenario: Send refused over a human draft

- **WHEN** the operator presses Send while the composer holds a draft
- **THEN** nothing is sent and the reason names the draft guard
