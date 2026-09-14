## ADDED Requirements

### Requirement: Missing widget records do not crash startup

When a recorded widget PID cannot be found by the process SDK, Ariadex MUST
treat the widget as unhealthy and continue daemon startup through widget repair.

#### Scenario: Widget crashed before restart

- **WHEN** the widget record points to a missing PID
- **THEN** health checking returns false without an exception escaping, and the
  daemon can create a replacement widget
