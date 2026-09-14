# managed-start (delta)

## ADDED Requirements

### Requirement: Normal supervision completion does not tear down the runtime

Managed start MUST keep the provider session, widget, and daemon alive after
queue-empty completion. Provider termination MUST occur only after explicit
operator quit/Ctrl+C shutdown or startup/setup failure cleanup.

#### Scenario: Queue becomes empty

- **WHEN** the watcher reaches verified queue-empty completion
- **THEN** Ariadex stops supervision without terminating the provider session
- **AND** the widget and daemon remain alive
- **AND** the user can explicitly quit or send Ctrl+C to exit

#### Scenario: Provider exits independently

- **WHEN** the attached provider exits without an Ariadex quit request
- **THEN** Ariadex reports the provider exit
- **AND** leaves the widget and daemon alive for inspection and recovery
- **AND** does not claim completion from the exit
