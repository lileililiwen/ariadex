# Design: hands-off auto-approve policy

`auto` is a deliberate relaxation for operators who accept it: version
control is their safety net, and interruptions cost more than contained
mistakes. It stays strictly opt-in (explicit config value), never the
default, and the one hard boundary — no parsed operation and path, no
approval — holds under every policy including `auto`.

- `PERMISSION_POLICIES` gains `auto`; `evaluate()` handles it after the
  `prompt`/`deny`/unknown branches: parsed requests with an allowed
  operation approve regardless of containment; unparsed, privileged-
  marker, traversal, and disabled-operation outcomes are unchanged.
- Config docs label `auto` hands-off with the version-control safety-net
  expectation; `permission_actions` docs label execution-class additions
  dangerous.
- `cli init` policy prompt lists `auto` alongside the others.
- Diagnostics record policy `auto` like any other; widget text unchanged.
