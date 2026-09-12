"""Robot agent supervisor: watch an existing provider session.

The robot supervises a user-selected existing tmux session running an
already-open coding-agent conversation (OpenCode, Codex, or CodeBuddy).
It never interprets a single word such as ``done`` as completion: a
finished candidate must show the provider-specific input-ready signal,
stay stable for the configured debounce interval, and show no running
tool, approval request, confirmation prompt, provider error, or fresh
output. Only then is the durable completion boundary evaluated
(``HANDOFF.md``, task markers, git state, active OpenSpec list) before
a new provider conversation is opened and the continuation prompt sent.

The robot never calls a provider LLM API, never injects input while the
agent is working, and never creates or terminates a tmux session unless
the operator explicitly requests the ``--create`` fallback. Pause stops
new input and leaves the user-owned session running; quit stops the
watcher and leaves the session attachable.
"""

from __future__ import annotations

import dataclasses
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from . import handoff as handoff_mod
from . import spec_graph as spec_graph_mod
from .adapters import AgentAdapter, UnsupportedOperation
from .terminal import TerminalDriver

DEFAULT_CONTINUATION_PROMPT = "Please read the HANDOFF.md, and implement the next spec."

SUPPORTED_ROBOT_PROVIDERS = ("opencode", "codex", "codebuddy")

# Input-ready signals. OpenCode/Codex markers are the live-verified ready
# prompts from `ariadex evidence --only opencode-lifecycle,codex-lifecycle`.
# CodeBuddy markers are declared (not live-verified) and stay conservative:
# an unknown surface classifies as unknown, never as finished.
READY_MARKERS: dict[str, tuple[str, ...]] = {
    "opencode": ("Ask anything", "tab agents"),
    "codex": ("OpenAI Codex", "Ask Codex to do anything"),
    "codebuddy": ("CodeBuddy", "codebuddy"),
}

# An approval/confirmation request always blocks continuation: the human
# must answer inside the user-owned session, never the robot.
APPROVAL_MARKERS = (
    "approve",
    "approval",
    "permission",
    "confirm",
    "allow?",
    "[y/n]",
    "(y/n)",
    "would you like",
    "press y",
)

# Provider failures block continuation with the exact reason reported.
ERROR_MARKERS = (
    "traceback",
    "exception",
    "error:",
    "failed",
    "not logged in",
    "please log in",
    "please login",
    "authentication required",
    "invalid api key",
    "missing api key",
    "no api key",
)

# Fresh activity proves the agent is still working, even beside a stale
# ready prompt further up the scrollback.
BUSY_MARKERS = (
    "running",
    "executing",
    "thinking",
    "working...",
    "esc to interrupt",
)

# Phases of the bounded polling state machine (see design.md).
ATTACHED = "attached"
WORKING = "working"
FINISHED_CANDIDATE = "finished-candidate"
VERIFIED_BOUNDARY = "verified-boundary"
NEW_CONVERSATION = "new-conversation"
CONTINUING = "continuing"
WAITING = "waiting"
BLOCKED = "blocked"
PAUSED = "paused"
DONE = "done"
STOPPED = "stopped"

# Raw capture classifications. Only "finished" advances the debounce
# counter; "unknown" is treated as working (send nothing).
CLASS_WORKING = "working"
CLASS_FINISHED = "finished"
CLASS_APPROVAL = "approval"
CLASS_ERROR = "error"
CLASS_UNKNOWN = "unknown"
CLASSIFICATION_TAIL_LINES = 16


class RobotError(Exception):
    """Typed robot failure: configuration, session, or boundary refusal."""


def classify_capture(provider: str, text: str) -> str:
    """Classify one pane capture without sending input.

    Conservative order: approval and error states win over a ready
    marker, and busy markers win over a stale ready prompt. Unknown
    surfaces (including unknown providers) never classify as finished.
    """
    # Pane capture includes scrollback. Only the current tail can describe
    # the provider's present surface; old approvals/errors must not block a
    # later ready prompt forever.
    lowered = "\n".join((text or "").splitlines()[-CLASSIFICATION_TAIL_LINES:]).lower()
    if any(marker in lowered for marker in APPROVAL_MARKERS):
        return CLASS_APPROVAL
    if any(marker in lowered for marker in ERROR_MARKERS):
        return CLASS_ERROR
    if any(marker in lowered for marker in BUSY_MARKERS):
        return CLASS_WORKING
    markers = READY_MARKERS.get(provider)
    if markers and any(marker.lower() in lowered for marker in markers):
        return CLASS_FINISHED
    if markers:
        return CLASS_UNKNOWN
    return CLASS_UNKNOWN


@dataclasses.dataclass
class RobotConfig:
    """Validated watcher configuration with durable prompt storage."""

    session: str = ""
    provider: str = "opencode"
    initial_prompt: str = ""
    continuation_prompt: str = DEFAULT_CONTINUATION_PROMPT
    debounce_polls: int = 3
    poll_interval_s: float = 5.0
    max_polls: int = 0  # 0 means unbounded; widgets quit explicitly
    spec_dir: str = "openspec/changes"
    handoff_file: str = ".ariadex/handoff.md"
    finished_change: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def validate_config(config: RobotConfig) -> RobotConfig:
    """Fail closed on unusable watcher configuration."""
    if not config.session.strip():
        raise RobotError(
            "no tmux session selected; pass `--session NAME` "
            "(see `ariadex watch --list-sessions`)"
        )
    if config.provider not in SUPPORTED_ROBOT_PROVIDERS:
        raise RobotError(
            f"unsupported robot provider `{config.provider}`; "
            f"robot supports: {', '.join(SUPPORTED_ROBOT_PROVIDERS)}"
        )
    # An empty initial prompt is attach mode: the existing conversation is
    # already in progress and must be observed without injecting input.
    if not config.continuation_prompt.strip():
        raise RobotError("continuation prompt must not be empty")
    if config.debounce_polls < 1:
        raise RobotError("debounce must be at least 1 poll")
    if config.poll_interval_s <= 0:
        raise RobotError("poll interval must be positive")
    if config.max_polls < 0:
        raise RobotError("max polls must not be negative")
    return config


def list_sessions(driver: TerminalDriver) -> list[str]:
    """Existing tmux sessions for explicit user selection (read-only)."""
    try:
        names = driver.list_sessions()
    except AttributeError as exc:
        raise RobotError("terminal driver does not support session discovery") from exc
    except Exception as exc:
        raise RobotError(f"session discovery failed: {exc}") from exc
    return sorted(names)


def _git_tree_clean(project_dir: Path) -> tuple[bool, str]:
    """Check `git status --porcelain`; failures block, never pass."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        return False, f"git is not installed ({exc}); commit state unverifiable"
    except OSError as exc:
        return False, f"git status failed ({exc}); commit state unverifiable"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown git error").strip()
        return False, f"git status refused: {detail}; commit state unverifiable"
    if proc.stdout.strip():
        return False, "uncommitted changes present; commit before continuing"
    return True, ""


def _tasks_complete(project_dir: Path, spec_dir: str, change: str) -> tuple[bool, str]:
    """All `- [ ]` markers checked in the finished change's tasks.md."""
    tasks_path = project_dir / spec_dir / change / "tasks.md"
    if not tasks_path.is_file():
        if not (project_dir / spec_dir / change).is_dir():
            # Archived (or otherwise recorded) changes carry no open tasks.
            return True, ""
        return (
            False,
            f"`{change}` has no tasks.md; task completion unverifiable",
        )
    try:
        text = tasks_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"tasks.md for `{change}` unreadable: {exc}"
    open_tasks = sum(
        1 for line in text.splitlines() if line.strip().startswith("- [ ]")
    )
    if open_tasks:
        return (
            False,
            f"`{change}` has {open_tasks} open task(s); "
            "finish the work before continuing",
        )
    return True, ""


@dataclasses.dataclass
class BoundaryCheck:
    """Durable completion boundary outcome (fail-closed)."""

    ok: bool = False
    reason: str = ""
    active: list[str] = dataclasses.field(default_factory=list)


def check_boundary(
    project_dir: Path,
    config: RobotConfig,
) -> BoundaryCheck:
    """Inspect HANDOFF.md, tasks, git, and the active OpenSpec list.

    Returns ok only when the previous conversation's work is represented
    durably. An empty active list is ok with no remaining work: the
    caller stops instead of sending a continuation prompt.
    """
    handoff_path = project_dir / config.handoff_file
    if not handoff_path.is_file():
        return BoundaryCheck(
            ok=False,
            reason=(
                f"no handoff file at `{config.handoff_file}`; "
                "record the work before continuing"
            ),
            active=[],
        )
    try:
        handoff_mod.read_handoff(handoff_path)
    except (handoff_mod.HandoffError, OSError) as exc:
        return BoundaryCheck(ok=False, reason=f"handoff unreadable: {exc}", active=[])
    graph, errors = spec_graph_mod.load_graph(project_dir, config.spec_dir)
    if errors:
        first = sorted(errors)[0]
        return BoundaryCheck(
            ok=False,
            reason=f"spec metadata blocked: {errors[first]}",
            active=sorted(graph),
        )
    if config.finished_change:
        done, reason = _tasks_complete(
            project_dir, config.spec_dir, config.finished_change
        )
        if not done:
            return BoundaryCheck(ok=False, reason=reason, active=sorted(graph))
    clean, reason = _git_tree_clean(project_dir)
    if not clean:
        return BoundaryCheck(ok=False, reason=reason, active=sorted(graph))
    active, _ = spec_graph_mod.discover_active_changes(project_dir / config.spec_dir)
    return BoundaryCheck(ok=True, reason="", active=sorted(active))


@dataclasses.dataclass
class RobotReport:
    """One bounded watch run outcome for the operator."""

    outcome: str = STOPPED  # done | blocked | stopped | max-polls
    detail: str = ""
    prompts_sent: int = 0

    def format(self) -> str:
        return (
            f"robot {self.outcome}: {self.detail} (prompts sent: {self.prompts_sent})"
        )


class RobotWatcher:
    """Bounded polling supervisor over one user-owned session.

    Collaborators (driver, adapter) are injected so every state is
    unit-testable without tmux. The watcher sends input only in two
    places: the one-time initial prompt and the post-boundary
    continuation prompt, both after a stable input-ready signal.
    """

    def __init__(
        self,
        project_dir: Path,
        config: RobotConfig,
        driver: TerminalDriver,
        adapter: AgentAdapter,
    ) -> None:
        self.project_dir = project_dir
        self.config = validate_config(config)
        self.driver = driver
        self.adapter = adapter
        self.phase = ATTACHED
        self.stable_polls = 0
        # Empty initial prompt means attach to the current conversation and
        # never inject a synthetic first request.
        self.initial_sent = not self.config.initial_prompt.strip()
        self.prompts_sent = 0
        self.last_classification = CLASS_UNKNOWN
        self.block_reason = ""
        self._paused = False
        self._quit = False

    def request_pause(self) -> str:
        """Stop new input; the user-owned session keeps running."""
        self._paused = True
        self.phase = PAUSED
        return "paused: no new input; the provider session keeps running"

    def request_quit(self) -> str:
        """Stop watching; the user-owned session is left attachable."""
        self._quit = True
        self.phase = STOPPED
        return "stopped: watcher exited; the provider session is untouched"

    @property
    def paused(self) -> bool:
        return self._paused

    def status_view(self) -> dict:
        """Widget-visible robot state (pure data, no I/O)."""
        return {
            "provider": self.adapter.provider_name,
            "session": self.config.session,
            "phase": self.phase,
            "paused": self._paused,
            "initial_sent": self.initial_sent,
            "stable_polls": self.stable_polls,
            "block_reason": self.block_reason,
        }

    def _capture(self) -> str:
        try:
            return self.driver.capture(self.config.session)
        except Exception as exc:
            raise RobotError(f"capture failed: {exc}") from exc

    def _send(self, text: str) -> None:
        try:
            self.adapter.send(text)
        except Exception as exc:
            raise RobotError(f"prompt delivery failed: {exc}") from exc

    def poll(self) -> str:
        """Advance one bounded step; returns the current phase."""
        if self._quit:
            self.phase = STOPPED
            return self.phase
        if self._paused:
            self.phase = PAUSED
            return self.phase
        capture = self._capture()
        observed = classify_capture(self.adapter.provider_name, capture)
        self.last_classification = observed
        if observed == CLASS_APPROVAL:
            # Approval/confirmation belongs to the provider conversation. The
            # user may answer it later; it must not terminate the watcher or
            # cause the initial prompt to be resent.
            self.phase = WAITING
            self.stable_polls = 0
            self.block_reason = (
                "provider waits for approval; watcher continues observing"
            )
            return self.phase
        if observed == CLASS_ERROR:
            self.phase = BLOCKED
            self.stable_polls = 0
            self.block_reason = (
                "provider reports an error; fix it in the session, then resume watching"
            )
            return self.phase
        if observed != CLASS_FINISHED:
            self.phase = WORKING if self.initial_sent else ATTACHED
            self.stable_polls = 0
            return self.phase
        self.stable_polls += 1
        if self.stable_polls < self.config.debounce_polls:
            self.phase = FINISHED_CANDIDATE
            return self.phase
        return self._on_stable_finished()

    def _on_stable_finished(self) -> str:
        if not self.initial_sent:
            self._send(self.config.initial_prompt)
            self.initial_sent = True
            self.prompts_sent += 1
            self.stable_polls = 0
            self.phase = CONTINUING
            return self.phase
        self.phase = VERIFIED_BOUNDARY
        check = check_boundary(self.project_dir, self.config)
        if not check.ok:
            self.phase = BLOCKED
            self.block_reason = check.reason
            return self.phase
        if not check.active:
            self.phase = DONE
            return self.phase
        return self._open_continuation()

    def _open_continuation(self) -> str:
        """Open the next conversation via the adapter contract only.

        Provider commands, restart details, and input-delivery rules stay
        inside the adapter (`new_conversation`); this method never branches
        on provider identity or command strings. Any failure enters
        `BLOCKED` with the provider, operation, and recovery reason, and no
        continuation prompt is sent until the fresh input surface is
        observed.
        """
        self.phase = NEW_CONVERSATION
        try:
            self.adapter.new_conversation()
        except UnsupportedOperation as exc:
            self.phase = BLOCKED
            self.block_reason = (
                f"`{self.adapter.provider_name}` automatic continuation "
                f"unavailable: {exc}"
            )
            return self.phase
        except Exception as exc:
            self.phase = BLOCKED
            self.block_reason = (
                f"new conversation failed for "
                f"`{self.adapter.provider_name}` via automatic "
                f"new-conversation operation: {exc}; no prompt was sent"
            )
            return self.phase
        ready = self._await_ready()
        if not ready:
            self.phase = BLOCKED
            self.block_reason = (
                "new conversation never reported an input-ready surface; "
                "no prompt was sent"
            )
            return self.phase
        self._send(self.config.continuation_prompt)
        self.prompts_sent += 1
        self.stable_polls = 0
        self.phase = CONTINUING
        return self.phase

    def _await_ready(self) -> bool:
        """Bounded wait for the new input surface (no prompt until ready)."""
        bound = max(self.config.debounce_polls, 1)
        stable = 0
        for _ in range(bound):
            capture = self._capture()
            if classify_capture(self.adapter.provider_name, capture) == CLASS_FINISHED:
                stable += 1
                if stable >= self.config.debounce_polls:
                    return True
            else:
                stable = 0
        return False

    def run(
        self,
        sleep: Callable[[float], None] | None = None,
    ) -> RobotReport:
        """Poll until done, blocked, quit, or the poll budget is spent."""
        do_sleep = sleep if sleep is not None else time.sleep
        polls = 0
        while True:
            if self._quit:
                return RobotReport(
                    outcome=STOPPED,
                    detail=(
                        self.block_reason
                        or "quit requested; the provider session is untouched"
                    ),
                    prompts_sent=self.prompts_sent,
                )
            if self.phase in (DONE, BLOCKED):
                outcome = "done" if self.phase == DONE else BLOCKED
                detail = self.block_reason or self._done_detail()
                return RobotReport(
                    outcome=outcome,
                    detail=detail,
                    prompts_sent=self.prompts_sent,
                )
            if self.config.max_polls and polls >= self.config.max_polls:
                return RobotReport(
                    outcome="max-polls",
                    detail=(
                        f"poll budget of {self.config.max_polls} spent "
                        f"in phase `{self.phase}`; no completion claimed"
                    ),
                    prompts_sent=self.prompts_sent,
                )
            self.poll()
            polls += 1
            if self.phase in (DONE, BLOCKED) or self._quit:
                continue
            do_sleep(self.config.poll_interval_s)

    def _done_detail(self) -> str:
        return "no active OpenSpec work remains; no further prompt sent"
