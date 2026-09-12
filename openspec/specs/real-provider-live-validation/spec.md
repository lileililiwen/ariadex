# real-provider-live-validation Specification

## Purpose
Defines provider-backed evidence for the MVP adapters: the evidence suite separately validates real OpenCode and Codex startup, safe-probe delivery, output capture, interruption, soft or documented hard-reset paths, termination, and restart in isolated tmux sessions, classifying unavailable prerequisites as skipped or blocked so the release gate never claims unproven validation.
## Requirements
### Requirement: Real adapters receive lifecycle evidence

The evidence suite MUST separately validate OpenCode and Codex startup, input delivery, output capture, interruption, reset behavior, and termination when those CLIs are available.

#### Scenario: OpenCode lifecycle
- **WHEN** OpenCode and tmux are available in an isolated evidence project
- **THEN** Ariadex records a real startup, prompt/capture, reset or documented hard-reset path, and clean termination

### Requirement: Provider evidence is honest

The suite MUST distinguish passed, skipped, and blocked prerequisites and MUST fail its gate unless every selected real-provider scenario passes.

#### Scenario: Codex is unavailable
- **WHEN** the Codex binary or required credentials are unavailable
- **THEN** the evidence identifies the exact prerequisite and the gate does not claim full provider validation

