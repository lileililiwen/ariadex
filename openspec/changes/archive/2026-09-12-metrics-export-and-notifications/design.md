## Approach

Introduce a small event model over existing local records. Keep stdout and local files authoritative, with opt-in webhook, email, or command sinks behind a provider-neutral notification interface. Redact before export and rate-limit repeated alerts.

## Dependencies

Depends on log governance, runner recovery, and human operator CLI. Remote monitoring remains optional and must not affect scheduling correctness.

## Safety

Notification failure MUST be observable but MUST NOT mark work complete, erase blockers, or cause unbounded retries.

