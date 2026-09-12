# Robot controls specification

## Purpose

Provide graceful process interruption and global pause/resume control for the
floating robot watcher.

## ADDED Requirements

### Requirement: Graceful interrupt

The watch command MUST catch `Ctrl+C`, request watcher shutdown, close its
widget when present, and return success without a Python traceback.

#### Scenario: Terminal interrupt

- **WHEN** the foreground watch process receives `Ctrl+C`
- **THEN** it reports a clean stopped result and leaves the provider session
  alive

#### Scenario: Widget interrupt

- **WHEN** widget watch receives `Ctrl+C`
- **THEN** it closes the widget and stops watching without a traceback or
  provider-session termination

### Requirement: Global pause toggle

The robot widget MUST register the default `Ctrl+Esc` global hotkey and toggle
watcher pause/resume on each activation.

#### Scenario: Pause

- **WHEN** the watcher is active and `Ctrl+Esc` is pressed
- **THEN** the watcher pauses without sending provider input

#### Scenario: Resume

- **WHEN** the watcher is paused and `Ctrl+Esc` is pressed
- **THEN** the watcher resumes observation without sending provider input
