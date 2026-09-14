## ADDED Requirements

### Requirement: Durable host memory setup

The project MUST provide one idempotent operator script that adds an explicit
8 GiB swap file without disabling existing swap, persists it in `/etc/fstab`,
and enables earlyoom at boot.

#### Scenario: First setup

- **WHEN** an operator runs the setup script on a host without
  `/swapfile-ariadex`
- **THEN** the script creates and activates the file, persists exactly one
  matching fstab entry, and enables earlyoom

#### Scenario: Repeated setup

- **WHEN** an operator runs the script after a successful setup
- **THEN** it does not recreate, reformat, or duplicate the swap file or fstab
  entry

### Requirement: Conservative earlyoom policy

The setup MUST configure earlyoom to prefer browser processes and MUST NOT
silently exempt OpenCode from emergency memory protection.

#### Scenario: Policy verification

- **WHEN** setup completes
- **THEN** `/etc/default/earlyoom` contains the browser preference and the
  earlyoom service is enabled and active

### Requirement: Fail-closed privileged operations

The script MUST stop on command failure and MUST NOT run `swapoff -a`.

#### Scenario: Privileged failure

- **WHEN** swap or service configuration fails
- **THEN** the script exits non-zero and does not print a successful completion
  result
