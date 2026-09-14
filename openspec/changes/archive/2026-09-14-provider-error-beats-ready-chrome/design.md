# Design: Provider error lines beat ready chrome

## Change 1: strong error markers in `classify_capture`

In `src/ariadex/robot.py`, split the generic error check. A new
`HARD_ERROR_MARKERS = ("traceback", "exception", "error:")` tuple is checked
unconditionally (after approval/quota/auth/max-steps/recoverable-terminal
handling, which keep their existing precedence) and returns `CLASS_ERROR`.
The remaining `ERROR_MARKERS = ("failed",)` keeps the OpenCode
`input_ready is True` exemption.

Rationale, pinned by existing tests on both sides:

- `Ask anything\nerror: provider exploded\n` carries a provider-emitted
  `error:` line in the same tail as the legacy ready chrome: it describes
  the live surface and must block (`test_error_blocks`,
  `test_generic_error_stays_blocked`, `test_error_is_blocked_without_input`).
- `failed earlier tool; error was recovered` plus the modern composer/footer
  surface is bare prose (`failed`, no colon form): the explicit ready surface
  still wins (`test_ready_opencode_state_overrides_generic_scrollback_words`).
- Recoverable terminal markers, quota, auth, approval, and max-steps keep
  their earlier positions, so `TERMINAL_*`, quota, and max-step fixtures
  route unchanged.

## Change 2: launch-command expectation

`OpenCodeAdapter.launch_command_for_provider` returns
`["opencode", "--port", <project-scoped port>]` by design (API session
state). `test_start_creates_session_with_launch_command` asserts the full
form instead of the bare `["opencode"]`.

## Tests

- Existing failing tests above go green without modification (except the
  adapter expectation).
- New `ClassifyTest` case: opencode modern ready surface plus a strong
  `error:` line classifies as error, proving ready chrome never vetoes a
  provider-emitted error.
