## ADDED Requirements

### Requirement: Waiting reasons name the redacted request shape

Waiting and deny decisions for unparsable or ambiguous provider
requests MUST carry a short redacted shape tag derived from
already-computed signals (`privileged-markers`,
`no-operation-word`, or `ambiguous-paths(n)`) within the existing
reason bounds. Raw provider text MUST never be stored or shown.

#### Scenario: Execution prompt waits with its shape named

- **WHEN** the surface carries privileged markers and cannot parse
- **THEN** the reason names the privileged shape and the manual
  answer step

#### Scenario: Pathless file request waits with its shape named

- **WHEN** the surface names a file action but no single
  unambiguous path
- **THEN** the reason names the ambiguous-path shape so a parser
  gap is recognizable
