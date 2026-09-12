## Why

Ariadex needs a stable executable boundary before adapters and orchestration can be implemented. The foundation must make configuration, state location, and the minimum CLI contract explicit without coupling the product to a Coding CLI or persistence technology.

## What Changes

- Establish the application layout and testable core contracts.
- Add `.ariadex/config.yaml` loading with safe defaults and validation.
- Define durable runtime state and the `init`, `status`, `pause`, `resume`, `takeover`, and `auto` command surface.

## Capabilities

### New Capabilities

- `project-foundation`: runnable project structure, configuration, and state primitives.
- `cli-lifecycle`: stable MVP command names and exit behavior.

## Impact

This is the first implementation change. Later changes depend on its configuration and state contracts. It must not start agents, invoke shells, or add provider-specific behavior.

## ADDED Requirements

### Requirement: Foundation exposes validated project configuration

The system MUST load agent, terminal, context, workflow, verification, and automation settings from a project configuration file and report invalid values before execution.

#### Scenario: Missing configuration is initialized
- **WHEN** a user runs `ariadex init` in a project without Ariadex configuration
- **THEN** the command creates a documented default configuration and durable state location without overwriting existing files
