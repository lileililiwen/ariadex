"""Human control: durable mode transitions and input ownership.

AUTO owns scheduling and input. MANUAL disables automatic input but keeps
observation and logs. PAUSE disables new scheduling operations while the
CLI process may remain alive. Successful transitions are persisted before
the command reports success and are idempotent.
"""

from __future__ import annotations

MODES = ("AUTO", "MANUAL", "PAUSE")

VIA_TARGETS = {
    "pause": "PAUSE",
    "resume": "AUTO",
    "takeover": "MANUAL",
    "auto": "AUTO",
}


class TransitionError(Exception):
    """A mode transition was rejected."""


def owns_input(mode: str) -> bool:
    """Whether Ariadex may send input to the Coding CLI in `mode`."""
    return mode == "AUTO"


def allows_scheduling(mode: str) -> bool:
    """Whether new scheduling operations may start in `mode`."""
    return mode == "AUTO"


def transition(current: str, target: str, via: str) -> str:
    """Compute the next mode or raise TransitionError.

    `via` names the commanding operation (pause, resume, takeover, auto)
    and must agree with `target`. Repeating the current mode succeeds
    without change. `resume` is valid only from PAUSE.
    """
    if current not in MODES:
        raise TransitionError(
            f"invalid current mode `{current}`: expected one of {', '.join(MODES)}"
        )
    if target not in MODES:
        raise TransitionError(
            f"invalid target mode `{target}`: expected one of {', '.join(MODES)}"
        )
    expected = VIA_TARGETS.get(via)
    if expected is None:
        raise TransitionError(f"unknown transition `{via}`")
    if target != expected:
        raise TransitionError(f"`{via}` cannot enter {target}: it enters {expected}")
    if via == "resume" and current != "PAUSE":
        raise TransitionError(
            f"resume rejected from {current}: only a PAUSED project may resume "
            "(use `takeover` or `auto` from other modes)"
        )
    if current == target:
        return current
    return target
