"""Robot agent supervisor: watch an existing provider session.

The robot supervises a user-selected existing tmux session running an
already-open coding-agent conversation (OpenCode, Codex, or CodeBuddy).
It never interprets a single word such as ``done`` as completion: a
finished candidate must show the provider-specific input-ready signal,
stay stable for the configured debounce interval, and show no running
tool, approval request, confirmation prompt, provider error, or fresh
output. Only then is the durable completion boundary evaluated
(``openspec`` evidence and task markers) before
a new provider conversation is opened and the continuation prompt sent.

The robot never calls a provider LLM API, never injects input while the
agent is working, and never creates or terminates a tmux session unless
the operator explicitly requests the ``--create`` fallback. Pause stops
new input and leaves the user-owned session running; quit stops the
watcher and leaves the session attachable.
"""

from __future__ import annotations

import contextlib
import dataclasses
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import diagnostics as diagnostics_mod
from . import handoff as handoff_mod
from . import openspec_evidence as evidence_mod
from . import permissions as permissions_mod
from . import spec_graph as spec_graph_mod
from .adapters import AgentAdapter, UnsupportedOperation
from .config import DEFAULT_CONFIRMATION_PROMPT
from .logging import redact
from .terminal import TerminalDriver

DEFAULT_CONTINUATION_PROMPT = "Please read the HANDOFF.md, and implement the next spec."

# Re-exported so watcher defaults stay identical to managed configuration.
DEFAULT_ROBOT_CONFIRMATION_PROMPT = DEFAULT_CONFIRMATION_PROMPT

#: Maximum stored activity events per watcher (in-memory, informational only).
MAX_ACTIVITY_EVENTS = 50

#: Maximum activity events exposed through `status_view()` to the widget.
MAX_ACTIVITY_VIEW = 20

#: Maximum characters per activity message shown in the widget.
MAX_ACTIVITY_MESSAGE = 280

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
# Authentication markers stay blocked (operator recovery) and take
# precedence over any recoverable terminal-error marker.
AUTH_MARKERS = (
    "not logged in",
    "please log in",
    "please login",
    "authentication required",
    "invalid api key",
    "missing api key",
    "no api key",
)

ERROR_MARKERS = ("failed",)

# Provider-emitted error lines describe the live surface, not scrollback
# prose: they block even when the same tail carries a ready marker (the
# legacy `Ask anything` chrome shares the tail with the error line).
HARD_ERROR_MARKERS = (
    "traceback",
    "exception",
    "error:",
)

# Recoverable provider terminal errors: the provider stops the current
# response but leaves its input surface usable. Declared per provider on
# the adapters (see `providers.RECOVERABLE_TERMINAL_ERROR_MARKERS`); the
# watcher mirrors them here so classification stays provider-neutral and
# testable without importing provider modules. A marker is eligible for a
# boundary only when the same current capture also contains a verified
# input-ready marker; otherwise the surface stays a generic error.
RECOVERABLE_TERMINAL_ERROR_MARKERS: dict[str, tuple[str, ...]] = {
    "opencode": (
        "stream interrupted",
        "response interrupted",
        "connection reset",
        "connection error",
        "network error",
        "request timeout",
        "request timed out",
        "timed out",
        "deadline exceeded",
        "internal server error",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "server overloaded",
        "overloaded",
        "try again",
    ),
    "codex": (
        "stream interrupted",
        "response interrupted",
        "connection reset",
        "connection error",
        "network error",
        "request timeout",
        "request timed out",
        "timed out",
        "deadline exceeded",
        "internal server error",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "server overloaded",
        "overloaded",
        "try again",
    ),
    "codebuddy": (
        "stream interrupted",
        "response interrupted",
        "connection reset",
        "connection error",
        "network error",
        "request timeout",
        "request timed out",
        "timed out",
        "deadline exceeded",
        "internal server error",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "server overloaded",
        "overloaded",
        "try again",
    ),
}

# OpenCode stops the current answer at this boundary but leaves the editor
# usable. Treat it as a recoverable conversation boundary so task-aware
# continuation/confirmation logic can send the next prompt.
MAX_STEP_MARKERS = (
    "maximum step limit",
    "maximum number of steps",
    "max step limit",
    "max steps",
    "step limit reached",
    "maximum steps",
)

# Recoverable provider limits require operator action (switch model, account,
# or credentials), but should not end supervision. The watcher waits on the
# same conversation and resumes once the provider presents a usable surface.
QUOTA_MARKERS = (
    "quota",
    "rate limit",
    "rate-limit",
    "usage limit",
    "exceeded your limit",
    "you've hit your limit",
    "out of credits",
    "credits exhausted",
    "insufficient credits",
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
CLASS_MAX_STEPS = "max-steps"
CLASS_TERMINAL_ERROR = "terminal-error"
CLASS_QUOTA = "waiting"
CLASS_UNKNOWN = "unknown"
CLASSIFICATION_TAIL_LINES = 16


class RobotError(Exception):
    """Typed robot failure: configuration, session, or boundary refusal."""


def classify_capture(provider: str, text: str, input_ready: bool | None = None) -> str:
    """Classify one pane capture without sending input.

    Conservative order: approval, quota/authentication, and known
    recoverable terminal errors win over a generic error; a recoverable
    terminal error is eligible only when the same current capture also
    contains a verified input-ready marker. Busy markers win over a stale
    ready prompt. Unknown surfaces (including unknown providers) never
    classify as finished.
    """
    # Pane capture includes scrollback. Only the current tail can describe
    # the provider's present surface; old approvals/errors must not block a
    # later ready prompt forever.
    lowered = "\n".join((text or "").splitlines()[-CLASSIFICATION_TAIL_LINES:]).lower()
    if any(marker in lowered for marker in APPROVAL_MARKERS):
        return CLASS_APPROVAL
    if any(marker in lowered for marker in QUOTA_MARKERS):
        return CLASS_QUOTA
    if any(marker in lowered for marker in AUTH_MARKERS):
        return CLASS_ERROR
    if any(marker in lowered for marker in MAX_STEP_MARKERS):
        return CLASS_MAX_STEPS
    recoverable = RECOVERABLE_TERMINAL_ERROR_MARKERS.get(provider, ())
    markers = READY_MARKERS.get(provider)
    ready_present = (
        input_ready
        if input_ready is not None
        else bool(markers and any(marker.lower() in lowered for marker in markers))
    )
    if recoverable and any(marker in lowered for marker in recoverable):
        if ready_present:
            return CLASS_TERMINAL_ERROR
        return CLASS_ERROR
    # Generic words belong to captured scrollback, not provider state. Once
    # the OpenCode adapter has explicitly reported its live ready surface,
    # they must not override that state or prevent the OpenSpec boundary.
    # Provider-emitted error lines (colon form, tracebacks, exceptions) are
    # exempt from that rule: they describe the live surface itself.
    if any(marker in lowered for marker in HARD_ERROR_MARKERS):
        return CLASS_ERROR
    if any(marker in lowered for marker in ERROR_MARKERS) and not (
        provider == "opencode" and input_ready is True
    ):
        return CLASS_ERROR
    if any(marker in lowered for marker in BUSY_MARKERS):
        return CLASS_WORKING
    if ready_present:
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
    confirmation_prompt: str = DEFAULT_ROBOT_CONFIRMATION_PROMPT
    debounce_polls: int = 3
    poll_interval_s: float = 5.0
    max_polls: int = 0  # 0 means unbounded; widgets quit explicitly
    fresh_ready_attempts: int = 12
    fresh_ready_interval_s: float = 2.0
    spec_dir: str = "openspec/changes"
    handoff_file: str = "HANDOFF.md"
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
    if not config.confirmation_prompt.strip():
        raise RobotError("confirmation prompt must not be empty")
    if config.debounce_polls < 1:
        raise RobotError("debounce must be at least 1 poll")
    if config.poll_interval_s <= 0:
        raise RobotError("poll interval must be positive")
    if config.max_polls < 0:
        raise RobotError("max polls must not be negative")
    if config.fresh_ready_attempts < 1:
        raise RobotError("fresh-ready attempts must be at least 1")
    if config.fresh_ready_interval_s < 0:
        raise RobotError("fresh-ready interval must not be negative")
    return config


def queue_summary(
    project_dir: Path,
    *,
    spec_dir: str = "openspec/changes",
    handoff_file: str = "HANDOFF.md",
    finished_change: str = "",
) -> dict:
    """Per-project queue evidence as a plain dict (never raises).

    Keys: `active_count`, `current_spec`, `open_tasks`, `total_tasks`,
    `unavailable` ("" when readable). A missing spec directory means the
    project carries no OpenSpec queue rather than an empty one. Explicit
    paths (instead of `RobotConfig`) so hub tabs can report queue evidence
    without owning a watcher.
    """
    summary: dict = {
        "active_count": 0,
        "current_spec": "",
        "open_tasks": 0,
        "total_tasks": 0,
        "unavailable": "",
    }
    if not (project_dir / spec_dir).is_dir():
        summary["unavailable"] = "not an OpenSpec project"
        return summary
    try:
        active, _ignored = spec_graph_mod.discover_active_changes(
            project_dir / spec_dir
        )
    except Exception as exc:
        summary["unavailable"] = f"spec queue unreadable: {exc}"
        return summary
    summary["active_count"] = len(active)
    try:
        handoff = handoff_mod.read_handoff(project_dir / handoff_file)
    except Exception as exc:
        summary["unavailable"] = f"handoff unreadable: {exc}"
        return summary
    try:
        target = _recorded_target_for(project_dir, finished_change, handoff)
    except Exception as exc:
        summary["unavailable"] = str(exc)
        return summary
    if not target:
        return summary
    summary["current_spec"] = target
    try:
        text = (project_dir / spec_dir / target / "tasks.md").read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        summary["unavailable"] = f"tasks.md unreadable: {exc}"
        return summary
    lines = [line.strip() for line in text.splitlines()]
    open_tasks = sum(1 for line in lines if line.startswith("- [ ]"))
    closed_tasks = sum(1 for line in lines if line[:4] in ("- [x", "- [X"))
    summary["open_tasks"] = open_tasks
    summary["total_tasks"] = open_tasks + closed_tasks
    return summary


def list_sessions(driver: TerminalDriver) -> list[str]:
    """Existing tmux sessions for explicit user selection (read-only)."""
    try:
        names = driver.list_sessions()
    except AttributeError as exc:
        raise RobotError("terminal driver does not support session discovery") from exc
    except Exception as exc:
        raise RobotError(f"session discovery failed: {exc}") from exc
    return sorted(names)


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
    """Durable completion boundary outcome (fail-closed).

    `decision` distinguishes the task-aware result without changing the
    historical `ok` contract: `complete` (tasks done, work remains),
    `unfinished` (valid open tasks, recoverable via confirmation),
    `ready-to-archive` (all tasks complete but the recorded change is
    still active: archive and validate instead of advancing),
    `empty` (no active specs remain), and `blocked` (hard failure, no
    prompt). `current_spec` names the task target; `open_tasks` counts
    its unchecked markers; `task_detail` carries the operator-readable
    unfinished/invalid task description. `evidence_source` names the
    queue authority (`openspec` for OpenSpec JSON, `internal` for the
    legacy discovery fallback outside an OpenSpec repository).
    """

    ok: bool = False
    reason: str = ""
    active: list[str] = dataclasses.field(default_factory=list)
    decision: str = "blocked"
    current_spec: str = ""
    open_tasks: int = 0
    task_detail: str = ""
    evidence_source: str = "internal"


def _git_tree_clean(project_dir: Path) -> tuple[bool, str]:
    """Deprecated compatibility seam; Git is not part of robot decisions."""
    return True, ""


def _boundary_target(
    project_dir: Path, config: RobotConfig, handoff: handoff_mod.Handoff
) -> str:
    """Resolve which change's tasks.md gates the boundary decision."""
    override = (config.finished_change or "").strip()
    if override:
        return override
    return (handoff.current_spec or "").strip()


def _task_decision(
    project_dir: Path, config: RobotConfig, target: str
) -> tuple[str, int, str]:
    """Inspect one change's task markers without touching provider state.

    Returns `(decision, open_count, detail)` where decision is `complete`,
    `unfinished`, or `blocked`. A missing change directory means the work
    was archived or recorded elsewhere: no open tasks. A present directory
    without a readable/valid tasks.md is a hard metadata failure, never a
    silent recovery.
    """
    if not target:
        return "complete", 0, ""
    tasks_path = project_dir / config.spec_dir / target / "tasks.md"
    if not (project_dir / config.spec_dir / target).is_dir():
        return "complete", 0, ""
    if not tasks_path.is_file():
        return (
            "blocked",
            0,
            f"`{target}` has no tasks.md; task completion unverifiable",
        )
    try:
        text = tasks_path.read_text(encoding="utf-8")
    except OSError as exc:
        return "blocked", 0, f"tasks.md for `{target}` unreadable: {exc}"
    open_names = [
        line.strip()[len("- [ ]") :].strip() or "(unnamed task)"
        for line in text.splitlines()
        if line.strip().startswith("- [ ]")
    ]
    if not open_names:
        return "complete", 0, ""
    shown = ", ".join(open_names[:3])
    if len(open_names) > 3:
        shown += f", +{len(open_names) - 3} more"
    return (
        "unfinished",
        len(open_names),
        f"`{target}` has {len(open_names)} open task(s): {shown}",
    )


def _read_recorded_conversation(
    project_dir: Path,
) -> evidence_mod.ConversationRecord | None:
    """Crash-recovery read of the conversation record.

    Raises ``EvidenceBlocked`` when the record exists but is malformed;
    the boundary then stays blocked instead of silently falling back to
    a stale handoff field.
    """
    try:
        return evidence_mod.read_conversation(project_dir)
    except evidence_mod.ConversationError as exc:
        raise evidence_mod.EvidenceBlocked(
            f"conversation record unreadable: {exc}; "
            "verify `.ariadex/conversation.json` before continuing"
        ) from exc


def _recorded_target(
    project_dir: Path, config: RobotConfig, handoff: handoff_mod.Handoff
) -> str:
    """Resolve the recorded change without inferring from `next_action`.

    Preference is the explicit `--finished-change` override, then the
    durable conversation record, then hidden Ariadex state. A stale
    `next_action` is never a target: it describes intent, not evidence.
    """
    return _recorded_target_for(project_dir, config.finished_change, handoff)


def _recorded_target_for(
    project_dir: Path, finished_change: str, handoff: handoff_mod.Handoff
) -> str:
    """`_recorded_target` over explicit fields (no `RobotConfig` needed)."""
    override = (finished_change or "").strip()
    if override:
        return override
    record = _read_recorded_conversation(project_dir)
    if record is not None and record.current_spec.strip():
        return record.current_spec.strip()
    return (handoff.current_spec or "").strip()


def _preferred_target(candidates: list[str], handoff_target: str) -> str:
    """First prompt target: keep the durable target when still eligible."""
    if handoff_target and handoff_target in candidates:
        return handoff_target
    return candidates[0]


def select_first_target(
    project_dir: Path,
    config: RobotConfig,
    handoff: handoff_mod.Handoff,
    runner: Callable[..., object] | None = None,
) -> tuple[str, list[str]]:
    """Select the first-conversation target from authoritative evidence.

    Returns `(target, queue)`. An empty queue returns `("", [])` so the
    caller stops without a prompt. Raises ``EvidenceBlocked`` when
    OpenSpec evidence is unavailable or contradictory and
    ``NotOpenSpecRoot`` outside an OpenSpec repository (caller falls
    back to internal discovery).
    """
    override = (config.finished_change or "").strip()
    changes = evidence_mod.query_changes(project_dir, runner=runner)
    if not changes.order:
        return "", []
    if override:
        if override not in changes.entries:
            raise evidence_mod.EvidenceBlocked(
                f"requested change `{override}` is not in the active "
                "OpenSpec queue; verify the change name before continuing"
            )
        return override, changes.order
    handoff_target = (handoff.current_spec or "").strip()
    record = _read_recorded_conversation(project_dir)
    recorded = record.current_spec.strip() if record is not None else ""
    preferred = recorded or handoff_target
    if preferred and preferred in changes.entries:
        return preferred, changes.order
    return changes.order[0], changes.order


def _openspec_boundary(
    project_dir: Path,
    config: RobotConfig,
    handoff: handoff_mod.Handoff,
    runner: Callable[..., object] | None = None,
) -> BoundaryCheck:
    """Evaluate the recorded change against OpenSpec JSON evidence.

    Raises ``NotOpenSpecRoot`` outside an OpenSpec repository so the
    caller keeps the legacy internal discovery. Every other evidence
    failure raises ``EvidenceBlocked`` with the exact reason.
    """
    changes = evidence_mod.query_changes(project_dir, runner=runner)
    ordered = changes.order
    target = _recorded_target(project_dir, config, handoff)
    if not ordered:
        if not target:
            return BoundaryCheck(
                ok=True,
                reason="",
                active=[],
                decision="empty",
                evidence_source="openspec",
            )
        spec_ids = evidence_mod.query_spec_ids(project_dir, runner=runner)
        evidence_mod.check_specs_valid(project_dir, runner=runner)
        detail = evidence_mod.check_archive_proof(
            project_dir, config.spec_dir, target, spec_ids
        )
        return BoundaryCheck(
            ok=True,
            reason="",
            active=[],
            decision="empty",
            current_spec=target,
            task_detail=detail,
            evidence_source="openspec",
        )
    if not target:
        return BoundaryCheck(
            ok=True,
            reason="",
            active=ordered,
            decision="complete",
            current_spec="",
            evidence_source="openspec",
        )
    progress = changes.entries.get(target)
    if progress is None:
        status = evidence_mod.query_change_status(project_dir, target, runner=runner)
        if status.found:
            raise evidence_mod.EvidenceBlocked(
                f"recorded change `{target}` is reported present but is "
                "absent from the active OpenSpec queue; evidence is "
                "contradictory — no completion claimed"
            )
        spec_ids = evidence_mod.query_spec_ids(project_dir, runner=runner)
        evidence_mod.check_specs_valid(project_dir, runner=runner)
        detail = evidence_mod.check_archive_proof(
            project_dir, config.spec_dir, target, spec_ids
        )
        return BoundaryCheck(
            ok=True,
            reason="",
            active=ordered,
            decision="complete",
            current_spec="",
            task_detail=detail,
            evidence_source="openspec",
        )
    task_decision, open_count, task_detail = _task_decision(project_dir, config, target)
    if progress.open_tasks:
        if task_decision == "complete":
            raise evidence_mod.EvidenceBlocked(
                f"recorded change `{target}` reports "
                f"{progress.open_tasks} open task(s) in OpenSpec JSON but "
                "its tasks.md shows none; evidence is contradictory — "
                "no completion claimed"
            )
        if task_decision == "blocked":
            return BoundaryCheck(
                ok=False,
                reason=task_detail,
                active=ordered,
                decision="blocked",
                current_spec=target,
                open_tasks=progress.open_tasks,
                task_detail=task_detail,
                evidence_source="openspec",
            )
        return BoundaryCheck(
            ok=True,
            reason="",
            active=ordered,
            decision="unfinished",
            current_spec=target,
            open_tasks=open_count,
            task_detail=task_detail,
            evidence_source="openspec",
        )
    if task_decision != "complete":
        detail = task_detail or (
            f"`{target}` reports complete tasks in OpenSpec JSON but "
            "its tasks.md disagrees; evidence is contradictory"
        )
        return BoundaryCheck(
            ok=False,
            reason=detail,
            active=ordered,
            decision="blocked",
            current_spec=target,
            open_tasks=0,
            task_detail=detail,
            evidence_source="openspec",
        )
    return BoundaryCheck(
        ok=True,
        reason="",
        active=ordered,
        decision="ready-to-archive",
        current_spec=target,
        task_detail=(
            f"`{target}` has all {progress.total} task(s) complete but is "
            "still active; archive the change and run strict validation "
            "before advancing"
        ),
        evidence_source="openspec",
    )


def check_boundary(
    project_dir: Path,
    config: RobotConfig,
    runner: Callable[..., object] | None = None,
) -> BoundaryCheck:
    """Inspect Ariadex state, tasks, and the active OpenSpec list.

    OpenSpec JSON evidence controls the decision inside an OpenSpec
    repository; outside one the legacy internal discovery applies. The
    public HANDOFF document and Git state are never scheduling inputs.
    Returns ok only when the previous conversation's work is represented
    durably. An empty active list is ok with no remaining work: the
    caller stops instead of sending a continuation prompt. Valid open
    tasks stay ok but carry the `unfinished` decision so the caller sends
    the confirmation prompt instead of claiming completion. A recorded
    change with complete tasks that is still active carries the
    `ready-to-archive` decision so the caller requests archival work
    instead of advancing.
    """
    handoff = handoff_mod.read_handoff(project_dir / config.handoff_file)
    graph, errors = spec_graph_mod.load_graph(project_dir, config.spec_dir)
    if errors:
        first = sorted(errors)[0]
        return BoundaryCheck(
            ok=False,
            reason=f"spec metadata blocked: {errors[first]}",
            active=sorted(graph),
            decision="blocked",
        )
    try:
        return _openspec_boundary(project_dir, config, handoff, runner)
    except evidence_mod.NotOpenSpecRoot:
        pass
    except evidence_mod.EvidenceBlocked as exc:
        try:
            blocked_target = _recorded_target(project_dir, config, handoff)
        except evidence_mod.EvidenceBlocked:
            blocked_target = ""
        return BoundaryCheck(
            ok=False,
            reason=str(exc),
            active=sorted(graph),
            decision="blocked",
            current_spec=blocked_target,
            task_detail=str(exc),
            evidence_source="openspec",
        )
    active, _ = spec_graph_mod.discover_active_changes(project_dir / config.spec_dir)
    ordered = sorted(active)
    if not ordered:
        check = BoundaryCheck(ok=True, reason="", active=[], decision="empty")
        return check
    target = _boundary_target(project_dir, config, handoff)
    task_decision, open_count, task_detail = _task_decision(project_dir, config, target)
    if task_decision == "blocked":
        return BoundaryCheck(
            ok=False,
            reason=task_detail,
            active=ordered,
            decision="blocked",
            current_spec=target,
            open_tasks=0,
            task_detail=task_detail,
        )
    if task_decision == "unfinished":
        return BoundaryCheck(
            ok=True,
            reason="",
            active=ordered,
            decision="unfinished",
            current_spec=target,
            open_tasks=open_count,
            task_detail=task_detail,
        )
    check = BoundaryCheck(
        ok=True,
        reason="",
        active=ordered,
        decision="complete",
        current_spec=target,
    )
    return check


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
        shutdown_requested: Callable[[], bool] | None = None,
        mode_requested: Callable[[], str] | None = None,
        evidence_runner: Callable[..., Any] | None = None,
    ) -> None:
        self.project_dir = project_dir
        self.config = validate_config(config)
        self.driver = driver
        self.adapter = adapter
        self.shutdown_requested = shutdown_requested
        self.mode_requested = mode_requested
        self.evidence_runner = evidence_runner
        self.phase = ATTACHED
        self.stable_polls = 0
        # Empty initial prompt means attach to the current conversation and
        # never inject a synthetic first request.
        self.initial_sent = not self.config.initial_prompt.strip()
        self.prompts_sent = 0
        self.confirmations_sent = 0
        self.last_classification = CLASS_UNKNOWN
        #: Approved permission requests sent to the provider session.
        self.permissions_granted = 0
        #: Deduplication key of the last approved permission request
        #: (provider/operation/normalized path). A repeated surface for the
        #: same key waits instead of resending approval input.
        self._last_permission_key = ""
        #: Recoverable boundary category driving the current debounce
        #: ("" for a clean finish, "max-steps"/"terminal-error" otherwise).
        #: Recorded in boundary diagnostics without raw provider captures.
        self.boundary_error_category = ""
        self.block_reason = ""
        self._paused = False
        self._quit = False
        #: Attempts used by the latest `_await_ready` fresh-surface wait.
        self.last_fresh_ready_attempts = 0
        #: Abort reason of the latest `_await_ready` wait (`""`, `"paused"`,
        #: or `"stopped"`); empty unless the wait was operator-aborted.
        self._fresh_ready_aborted = ""
        self._events: list[dict] = []
        self._event_seq = 0
        self._recovery_logged = False

    def _record(self, category: str, message: str) -> dict:
        """Append one bounded, redacted activity event (informational only)."""
        self._event_seq += 1
        safe = redact(str(message or ""))[:MAX_ACTIVITY_MESSAGE]
        event = {
            "seq": self._event_seq,
            "category": str(category),
            "message": safe,
        }
        self._events.append(event)
        if len(self._events) > MAX_ACTIVITY_EVENTS:
            self._events = self._events[-MAX_ACTIVITY_EVENTS:]
        return event

    @property
    def activity_events(self) -> list[dict]:
        """Bounded copy of recorded activity events (oldest first)."""
        return [dict(event) for event in self._events]

    def _diag(
        self,
        category: str,
        action: str,
        *,
        result: str = "",
        message: str = "",
        current_spec: str | None = None,
        open_tasks: int = 0,
        closed_tasks: int = 0,
        command_role: str = "",
        recovery: str = "",
        classification: str = "",
        active_queue: tuple[str, ...] | list[str] = (),
        evidence_source: str = "",
        decision: str = "",
        blocker: str = "",
        operation: str = "",
        next_action: str = "",
        requested_path: str = "",
        normalized_path: str = "",
        policy: str = "",
    ) -> None:
        """Persist one durable diagnostic (best-effort, never raises).

        Diagnostic failure never changes scheduling: the in-memory
        activity event is already recorded and the lifecycle decision
        stands. Raw provider captures are never included; only bounded,
        redacted classifications and evidence references. Every
        no-advance path carries the provider classification, recorded
        spec, authoritative queue, task counts, decision, blocker,
        operation, and next action so the widget can explain the stop.
        """
        try:
            conversation_id = ""
            with contextlib.suppress(Exception):
                record = evidence_mod.read_conversation(self.project_dir)
                if record is not None:
                    conversation_id = record.conversation_id
                    if current_spec is None:
                        current_spec = record.current_spec or None
        except Exception:
            conversation_id = ""
        with contextlib.suppress(Exception):
            diagnostics_mod.try_record(
                self.project_dir,
                diagnostics_mod.build_diagnostic(
                    category,
                    action,
                    result=result,
                    message=message,
                    provider=self.adapter.provider_name,
                    session=self.config.session,
                    phase=self.phase,
                    conversation_id=conversation_id,
                    current_spec=current_spec,
                    open_tasks=open_tasks,
                    closed_tasks=closed_tasks,
                    command_role=command_role,
                    recovery=recovery,
                    classification=classification or self.last_classification,
                    active_queue=tuple(active_queue),
                    evidence_source=evidence_source,
                    decision=decision,
                    blocker=blocker,
                    operation=operation,
                    next_action=next_action,
                    requested_path=requested_path,
                    normalized_path=normalized_path,
                    policy=policy,
                ),
            )

    def request_pause(self) -> str:
        """Stop new input; the user-owned session keeps running."""
        self._paused = True
        self.phase = PAUSED
        self._record("pause", "paused: no new input will be sent")
        self._diag(
            "pause",
            "watcher paused",
            result="paused",
            message="no new input will be sent",
        )
        return "paused: no new input; the provider session keeps running"

    def request_resume(self) -> str:
        """Resume observation; do not inject input just because of resume."""
        self._paused = False
        self.block_reason = ""
        self.stable_polls = 0
        self.phase = WORKING if self.initial_sent else ATTACHED
        self._record("resume", "resumed: watcher is observing the provider session")
        self._diag(
            "pause",
            "watcher resumed",
            result="resumed",
            message="watcher is observing the provider session",
        )
        return "resumed: watcher is observing the provider session"

    def request_quit(self) -> str:
        """Stop watching; the user-owned session is left attachable."""
        self._quit = True
        self.phase = STOPPED
        self._record("shutdown", "stopped: watcher exited; session untouched")
        self._diag(
            "shutdown",
            "watcher stopped",
            result="stopped",
            message="watcher exited; session untouched",
            decision="stopped",
            operation="shutdown",
            next_action="re-run the watcher to resume supervision",
        )
        return "stopped: watcher exited; the provider session is untouched"

    @property
    def paused(self) -> bool:
        return self._paused

    def _permission_settings(self) -> tuple[str, str, list[str], list[str]]:
        """Configured (policy, temp root, actions, allowlist), fail-closed.

        Missing or invalid project configuration falls back to the safe
        `prompt` default: no automatic approval is ever sent.
        """
        from . import config as config_mod

        try:
            cfg = config_mod.load(self.project_dir)
        except Exception:
            return (
                "prompt",
                config_mod.DEFAULT_PERMISSION_TEMP_ROOT,
                ["read", "write", "create", "delete"],
                [],
            )
        if cfg.permission_policy not in permissions_mod.PERMISSION_POLICIES:
            return (
                "prompt",
                cfg.permission_temp_root,
                list(cfg.permission_actions),
                list(cfg.permission_allowlist),
            )
        return (
            cfg.permission_policy,
            cfg.permission_temp_root,
            list(cfg.permission_actions),
            list(cfg.permission_allowlist),
        )

    def _handle_approval(self, capture: str) -> str:
        """Evaluate one provider approval surface against the policy.

        Returns the watcher phase (always WAITING for approvals). Sends
        the adapter-owned keystroke only for a verified, contained request
        under an auto policy, at most once per distinct request. Every
        other surface waits for explicit human action with the exact
        reason recorded; nothing is ever denied blindly or approved
        without a parsed operation and contained path.
        """
        policy, temp_root_cfg, actions, allowlist_cfg = self._permission_settings()
        parsed = self.adapter.recognize_permission(capture)
        temp_root: Path | None = None
        allow_roots: list[Path] = []
        prep_error = ""
        if policy in ("project-temp-auto", "allowlist"):
            try:
                allow_roots = permissions_mod.allowlist_roots(
                    self.project_dir, allowlist_cfg
                )
            except Exception as exc:
                prep_error = f"allowlist unreadable: {exc}"
            if policy == "project-temp-auto":
                try:
                    temp_root = permissions_mod.ensure_temp_root(
                        self.project_dir, temp_root_cfg
                    )
                except (ValueError, OSError) as exc:
                    prep_error = f"temp root unavailable: {exc}"
        if prep_error:
            decision = permissions_mod.PermissionDecision(
                self.adapter.provider_name,
                "",
                "",
                "",
                policy,
                "waiting",
                f"{prep_error}; answer the approval in the provider session",
            )
        else:
            decision = permissions_mod.evaluate(
                provider=self.adapter.provider_name,
                parsed=parsed,
                raw_tail=capture,
                policy=policy,
                temp_root=temp_root,
                allowlist=allow_roots,
                allowed_actions=actions,
                approve_input=self.adapter.permission_approve_input or "",
                project_dir=self.project_dir,
            )
        summary = permissions_mod.decision_summary(decision)
        if decision.result == "allow" and decision.approve_input:
            key = "|".join(
                (decision.provider, decision.operation, decision.normalized_path)
            )
            if key and key == self._last_permission_key:
                decision = permissions_mod.PermissionDecision(
                    decision.provider,
                    decision.operation,
                    decision.requested_path,
                    decision.normalized_path,
                    decision.policy,
                    "waiting",
                    "already approved once; waiting for the provider to "
                    "proceed instead of resending approval input",
                )
                summary = permissions_mod.decision_summary(decision)
            else:
                try:
                    self._send(decision.approve_input)
                except RobotError as exc:
                    decision = permissions_mod.PermissionDecision(
                        decision.provider,
                        decision.operation,
                        decision.requested_path,
                        decision.normalized_path,
                        decision.policy,
                        "waiting",
                        f"approval delivery failed ({exc}); answer the "
                        "approval in the provider session",
                    )
                    summary = permissions_mod.decision_summary(decision)
                else:
                    self.permissions_granted += 1
                    self._last_permission_key = key
        elif decision.result == "allow":
            decision = permissions_mod.PermissionDecision(
                decision.provider,
                decision.operation,
                decision.requested_path,
                decision.normalized_path,
                decision.policy,
                "waiting",
                "provider surface is not understood (no safe response "
                "declared); answer the approval in the provider session",
            )
            summary = permissions_mod.decision_summary(decision)
        self.phase = WAITING
        self.stable_polls = 0
        self.block_reason = summary
        self._record("waiting", summary)
        recovery = (
            "approved with the provider-owned keystroke; watching resumes"
            if decision.result == "allow"
            else "answer the approval in the provider session; "
            "watching resumes afterwards"
        )
        self._diag(
            "provider",
            f"permission decision ({decision.result})",
            result=decision.result,
            message=summary,
            classification=CLASS_APPROVAL,
            decision=decision.result,
            blocker="" if decision.result == "allow" else decision.reason,
            operation=decision.operation,
            next_action=recovery,
            requested_path=decision.requested_path,
            normalized_path=decision.normalized_path,
            policy=decision.policy,
        )
        return self.phase

    def status_view(self) -> dict:
        """Widget-visible robot state (pure data, no I/O)."""
        visible = self._events[-MAX_ACTIVITY_VIEW:]
        latest = dict(visible[-1]) if visible else None
        return {
            "provider": self.adapter.provider_name,
            "session": self.config.session,
            "phase": self.phase,
            "paused": self._paused,
            "initial_sent": self.initial_sent,
            "stable_polls": self.stable_polls,
            "block_reason": self.block_reason,
            "latest_event": latest,
            "activity": [dict(event) for event in visible],
            "prompts_sent": self.prompts_sent,
            "confirmations_sent": self.confirmations_sent,
            "permissions_granted": self.permissions_granted,
        }

    def queue_summary(self) -> dict:
        """Per-project queue evidence for supervision surfaces (never raises).

        File reads only: active-change discovery, the recorded
        conversation, the handoff, and the current spec's tasks.md. No
        subprocess and no provider I/O, so the hub poll loop can call this
        every refresh. Unreadable pieces yield `unavailable` with the exact
        reason instead of raising.
        """
        return queue_summary(
            self.project_dir,
            spec_dir=self.config.spec_dir,
            handoff_file=self.config.handoff_file,
            finished_change=self.config.finished_change,
        )

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
        if self.mode_requested is not None:
            mode = self.mode_requested()
            if mode == "PAUSE":
                self._paused = True
                self.phase = PAUSED
                self.stable_polls = 0
                self._record("pause", "daemon mode PAUSE: no new input will be sent")
                self._diag(
                    "pause",
                    "daemon mode PAUSE observed",
                    result="paused",
                    message="no new input will be sent",
                )
                return self.phase
            if self._paused and mode == "AUTO":
                self.request_resume()
        if self._paused:
            self.phase = PAUSED
            return self.phase
        capture = self._capture()
        provider_state = self.adapter.provider_state()
        if self.adapter.provider_state_required and provider_state is None:
            observed = CLASS_UNKNOWN
        else:
            observed = classify_capture(
                self.adapter.provider_name,
                capture,
                input_ready=(
                    provider_state == "idle"
                    if provider_state is not None
                    else self.adapter.is_input_ready(capture)
                ),
            )
            if provider_state == "active":
                observed = CLASS_WORKING
            elif provider_state == "retry":
                observed = CLASS_QUOTA
            elif provider_state == "error":
                observed = CLASS_ERROR
        self.last_classification = observed
        if observed == CLASS_APPROVAL:
            # Approval/confirmation belongs to the provider conversation.
            # The permission policy decides: contained temp-root or
            # allowlist requests under an auto policy are approved with the
            # adapter-owned keystroke; every other surface waits for the
            # human to answer inside the user-owned session. Waiting never
            # terminates the watcher and never resends the initial prompt.
            return self._handle_approval(capture)
        if observed == CLASS_QUOTA:
            self.phase = WAITING
            self.stable_polls = 0
            self.block_reason = (
                "provider quota or rate limit reached; switch the model or "
                "credentials, then watcher will resume"
            )
            self._record("waiting", self.block_reason)
            self._diag(
                "quota",
                "provider quota or rate limit reached",
                result="waiting",
                message=self.block_reason,
                recovery="switch model or credentials, then watching resumes",
                classification=observed,
                decision="waiting",
                blocker=self.block_reason,
                operation="observe",
                next_action="switch the model or credentials, then watching resumes",
            )
            return self.phase
        if observed == CLASS_ERROR:
            self.phase = BLOCKED
            self.stable_polls = 0
            self.boundary_error_category = ""
            self.block_reason = (
                "provider reports an error; fix it in the session, then resume watching"
            )
            self._record("error", self.block_reason)
            self._diag(
                "provider",
                "provider reports an error",
                result="blocked",
                message=self.block_reason,
                recovery="fix it in the session, then resume watching",
                classification=observed,
                decision="blocked",
                blocker=self.block_reason,
                operation="observe",
                next_action="fix the provider error in the session, "
                "then resume watching",
            )
            return self.phase
        if observed == CLASS_MAX_STEPS:
            self.phase = FINISHED_CANDIDATE
            self.boundary_error_category = "max-steps"
            self.stable_polls += 1
            self._record(
                "boundary",
                "provider reached max-step limit; evaluating task boundary",
            )
            if self.stable_polls < self.config.debounce_polls:
                return self.phase
            return self._on_stable_finished()
        if observed == CLASS_TERMINAL_ERROR:
            self.phase = FINISHED_CANDIDATE
            self.boundary_error_category = "terminal-error"
            self.stable_polls += 1
            self._record(
                "boundary",
                "provider reported a recoverable terminal error; "
                "evaluating task boundary",
            )
            self._diag(
                "provider",
                "provider reported a recoverable terminal error",
                result="recoverable",
                message="evaluating the OpenSpec task boundary; "
                "no raw provider capture stored",
                recovery="fresh conversation with the task-selected prompt",
                classification=observed,
                decision="recoverable",
                operation="evaluate-boundary",
                next_action="run the OpenSpec task boundary, then open a "
                "fresh conversation with the selected prompt",
            )
            if self.stable_polls < self.config.debounce_polls:
                return self.phase
            return self._on_stable_finished()
        if observed != CLASS_FINISHED:
            self.phase = WORKING if self.initial_sent else ATTACHED
            self.stable_polls = 0
            return self.phase
        self.boundary_error_category = ""
        self.stable_polls += 1
        if self.stable_polls < self.config.debounce_polls:
            self.phase = FINISHED_CANDIDATE
            return self.phase
        return self._on_stable_finished()

    def _log_recovery_once(self) -> str:
        """Surface interrupted-conversation recovery evidence once.

        A surviving conversation record names the change that gates the
        next boundary instead of inferring it from a stale `next_action`.
        Returns "" when recovery state is usable, else the blocking
        reason. Never raises: an unreadable record blocks the boundary
        and a missing record simply means nothing to recover.
        """
        if self._recovery_logged:
            return ""
        self._recovery_logged = True
        try:
            record = evidence_mod.read_conversation(self.project_dir)
        except evidence_mod.ConversationError as exc:
            return (
                f"conversation record unreadable: {exc}; verify "
                "`.ariadex/conversation.json` before continuing"
            )
        if record is None:
            return ""
        self._record(
            "recovery",
            f"recovered conversation {record.conversation_id} for "
            f"`{record.current_spec}` (role {record.role}); "
            "the recorded change gates the boundary",
        )
        return ""

    def _record_before_prompt(self, role: str, target: str, queue: list[str]) -> bool:
        """Persist the conversation target before any provider input.

        Returns True when recorded (the caller may send the prompt).
        On any failure the watcher enters BLOCKED and sends nothing, so
        an unverified prompt is never delivered and the evidence gap is
        preserved for the operator.
        """
        try:
            record = evidence_mod.record_conversation(
                self.project_dir,
                role,
                target,
                self.config.spec_dir,
                queue,
                self.config.handoff_file,
            )
        except (
            evidence_mod.ConversationError,
            handoff_mod.HandoffError,
            OSError,
        ) as exc:
            self.phase = BLOCKED
            self.block_reason = (
                f"conversation target `{target}` could not be recorded: "
                f"{exc}; no prompt was sent"
            )
            self._record("error", self.block_reason)
            self._diag(
                "openspec",
                f"conversation target `{target}` not recorded",
                result="blocked",
                message=self.block_reason,
                current_spec=target,
                active_queue=tuple(queue),
                decision="blocked",
                blocker=self.block_reason,
                operation="record-conversation",
                next_action="verify `.ariadex/conversation.json` before continuing",
                recovery="verify `.ariadex/conversation.json` before continuing",
            )
            return False
        self._record(
            "prompt",
            f"recorded conversation {record.conversation_id} for "
            f"`{target}` (role {role})",
        )
        self._diag(
            "openspec",
            f"conversation recorded for `{target}`",
            result="recorded",
            message=f"role {role}; the recorded change gates the boundary",
            current_spec=target,
            active_queue=tuple(queue),
            decision="recorded",
            operation="record-conversation",
            next_action="open a fresh conversation, then send the "
            f"{role} prompt after the input-ready surface",
        )
        return True

    def _legacy_first_target(
        self, handoff: handoff_mod.Handoff
    ) -> tuple[str, list[str]]:
        """First-conversation target from internal discovery (fallback).

        Used only outside an OpenSpec repository. Returns `("", [])`
        when no active specs remain so the caller stops without a
        prompt; raises ``EvidenceBlocked`` for an unusable override.
        """
        active, _ = spec_graph_mod.discover_active_changes(
            self.project_dir / self.config.spec_dir
        )
        ordered = sorted(active)
        if not ordered:
            return "", []
        override = (self.config.finished_change or "").strip()
        if override:
            if override not in ordered:
                raise evidence_mod.EvidenceBlocked(
                    f"requested change `{override}` is not in the active "
                    "spec list; verify the change name before continuing"
                )
            return override, ordered
        handoff_target = (handoff.current_spec or "").strip()
        return _preferred_target(ordered, handoff_target), ordered

    def _send_initial(self) -> str:
        """Record the first-conversation target, then send the prompt once."""
        try:
            handoff = handoff_mod.read_handoff(
                self.project_dir / self.config.handoff_file
            )
        except (handoff_mod.HandoffError, OSError) as exc:
            self.phase = BLOCKED
            self.block_reason = f"handoff unreadable: {exc}"
            self._record("boundary", f"blocked: {self.block_reason}")
            self._diag(
                "boundary",
                "first-conversation selection blocked",
                result="blocked",
                message=self.block_reason,
                command_role="handoff-read",
                decision="blocked",
                blocker=self.block_reason,
                operation="selection",
                next_action="verify Ariadex runtime state before continuing",
                recovery="verify Ariadex runtime state before continuing",
            )
            return self.phase
        try:
            target, queue = select_first_target(
                self.project_dir, self.config, handoff, self.evidence_runner
            )
        except evidence_mod.NotOpenSpecRoot:
            try:
                target, queue = self._legacy_first_target(handoff)
            except evidence_mod.EvidenceBlocked as exc:
                self.phase = BLOCKED
                self.block_reason = str(exc)
                self._record("boundary", f"blocked: {self.block_reason}")
                self._diag(
                    "selection",
                    "first-conversation selection blocked",
                    result="blocked",
                    message=self.block_reason,
                    command_role="spec-discovery",
                    decision="blocked",
                    blocker=self.block_reason,
                    operation="selection",
                    next_action="verify the change name before continuing",
                )
                return self.phase
        except evidence_mod.EvidenceBlocked as exc:
            self.phase = BLOCKED
            self.block_reason = str(exc)
            self._record("boundary", f"blocked: {self.block_reason}")
            self._diag(
                "selection",
                "first-conversation selection blocked",
                result="blocked",
                message=self.block_reason,
                command_role="openspec-list",
                decision="blocked",
                blocker=self.block_reason,
                operation="selection",
                next_action="verify the OpenSpec queue before continuing",
            )
            return self.phase
        if not target:
            self.phase = DONE
            self._record("boundary", "no active OpenSpec work remains; stopping")
            self._diag(
                "boundary",
                "no active OpenSpec work remains",
                result="done",
                message="stopping without a prompt",
                active_queue=tuple(queue),
                decision="empty",
                operation="selection",
                next_action="stop the managed workflow",
            )
            return self.phase
        if not self._record_before_prompt("first", target, queue):
            return self.phase
        self._send(self.config.initial_prompt)
        self.initial_sent = True
        self.prompts_sent += 1
        self.stable_polls = 0
        self.phase = CONTINUING
        self._record("prompt", "sent initial prompt to the ready conversation")
        self._diag(
            "prompt",
            "sent initial prompt",
            result="sent",
            message="sent initial prompt to the ready conversation",
            current_spec=target,
            active_queue=tuple(queue),
            decision="first-prompt",
            operation="send-initial-prompt",
            next_action="supervise the provider conversation until the "
            "next stable input-ready surface",
        )
        return self.phase

    def _on_stable_finished(self) -> str:
        recovery = self._log_recovery_once()
        if recovery:
            self.phase = BLOCKED
            self.block_reason = recovery
            self._record("boundary", f"blocked: {recovery}")
            self._diag(
                "boundary",
                "conversation recovery blocked",
                result="blocked",
                message=recovery,
                decision="blocked",
                blocker=recovery,
                operation="recover-conversation",
                next_action="verify `.ariadex/conversation.json` before continuing",
            )
            return self.phase
        if not self.initial_sent:
            return self._send_initial()
        self.phase = VERIFIED_BOUNDARY
        check = check_boundary(self.project_dir, self.config, self.evidence_runner)
        error_category = self.boundary_error_category or "clean-finish"
        evidence_detail = (
            f"decision={check.decision}; current_spec="
            f"{check.current_spec or '(none)'}; active="
            f"{','.join(check.active) or '(none)'}; open_tasks={check.open_tasks}; "
            f"evidence={check.evidence_source}; error_category={error_category}"
        )
        if not check.ok:
            self.phase = BLOCKED
            self.block_reason = check.reason
            self._record(
                "boundary",
                f"blocked: {check.reason}; {evidence_detail}; next=operator recovery",
            )
            self._diag(
                "boundary",
                "boundary evaluation blocked",
                result="blocked",
                message=f"{check.reason}; {evidence_detail}",
                current_spec=check.current_spec or None,
                open_tasks=check.open_tasks,
                command_role=check.evidence_source,
                active_queue=tuple(check.active),
                evidence_source=check.evidence_source,
                decision="blocked",
                blocker=check.reason,
                operation="evaluate-boundary",
                next_action="resolve the blocker, then resume watching",
            )
            self.boundary_error_category = ""
            return self.phase
        if not check.active:
            self.phase = DONE
            self._record(
                "boundary",
                f"{evidence_detail}; next=stop managed workflow",
            )
            self._diag(
                "boundary",
                "no active OpenSpec work remains",
                result="done",
                message="stopping without a prompt",
                current_spec=check.current_spec or None,
                active_queue=tuple(check.active),
                evidence_source=check.evidence_source,
                decision="empty",
                operation="evaluate-boundary",
                next_action="stop the managed workflow",
            )
            self.boundary_error_category = ""
            return self.phase
        if check.decision == "unfinished":
            self._record(
                "boundary",
                f"{check.task_detail or 'unfinished tasks remain'}; "
                f"{evidence_detail}; next=confirmation conversation",
            )
            self._diag(
                "boundary",
                "unfinished tasks remain; confirmation recovery",
                result="unfinished",
                message=check.task_detail or "unfinished tasks remain",
                current_spec=check.current_spec or None,
                open_tasks=check.open_tasks,
                command_role=check.evidence_source,
                active_queue=tuple(check.active),
                evidence_source=check.evidence_source,
                decision="unfinished",
                operation="evaluate-boundary",
                next_action="open a fresh conversation and send the "
                "confirmation prompt",
            )
            return self._open_confirmation(check)
        if check.decision == "ready-to-archive":
            self._record(
                "boundary",
                f"{check.task_detail or 'tasks complete; archival needed'}; "
                f"{evidence_detail}; next=archival confirmation",
            )
            self._diag(
                "boundary",
                "tasks complete; archival needed",
                result="ready-to-archive",
                message=check.task_detail or "tasks complete; archival needed",
                current_spec=check.current_spec or None,
                open_tasks=check.open_tasks,
                command_role=check.evidence_source,
                active_queue=tuple(check.active),
                evidence_source=check.evidence_source,
                decision="ready-to-archive",
                operation="evaluate-boundary",
                next_action="open a fresh conversation and send the "
                "confirmation prompt with the archival instruction",
            )
            return self._open_confirmation(check, check.task_detail)
        self._record(
            "boundary",
            f"verified boundary for `{check.current_spec or check.active[0]}`; "
            f"{evidence_detail}; next=continuation conversation",
        )
        self._diag(
            "boundary",
            f"verified boundary for `{check.current_spec or check.active[0]}`",
            result="complete",
            message="opening a new conversation",
            current_spec=check.current_spec or check.active[0],
            open_tasks=check.open_tasks,
            command_role=check.evidence_source,
            active_queue=tuple(check.active),
            evidence_source=check.evidence_source,
            decision="complete",
            operation="evaluate-boundary",
            next_action="open a fresh conversation and send the continuation prompt",
        )
        return self._open_continuation(check)

    def _open_continuation(self, check: BoundaryCheck) -> str:
        """Open the next conversation via the adapter contract only.

        The next target is recorded before any provider input so the
        boundary never advances on a stale assumption. Provider
        commands, restart details, and input-delivery rules stay inside
        the adapter (`new_conversation`); this method never branches on
        provider identity or command strings. Any failure enters
        `BLOCKED` with the provider, operation, and recovery reason, and
        no continuation prompt is sent until the fresh input surface is
        observed.
        """
        next_target = check.current_spec.strip() or (
            check.active[0] if check.active else ""
        )
        if not next_target:
            self.phase = DONE
            self._record("boundary", "no active OpenSpec work remains; stopping")
            self._diag(
                "boundary",
                "no active OpenSpec work remains",
                result="done",
                message="stopping without a prompt",
                active_queue=tuple(check.active),
                evidence_source=check.evidence_source,
                decision="empty",
                operation="new-conversation",
                next_action="stop the managed workflow",
            )
            return self.phase
        if not self._record_before_prompt(
            "continuation", next_target, list(check.active)
        ):
            return self.phase
        self.phase = NEW_CONVERSATION
        try:
            self.adapter.new_conversation()
        except UnsupportedOperation as exc:
            self.phase = BLOCKED
            self.block_reason = (
                f"`{self.adapter.provider_name}` automatic continuation "
                f"unavailable: {exc}"
            )
            self._record("error", self.block_reason)
            self._diag(
                "error",
                "automatic continuation unavailable",
                result="blocked",
                message=self.block_reason,
                current_spec=next_target,
                active_queue=tuple(check.active),
                evidence_source=check.evidence_source,
                decision="blocked",
                blocker=self.block_reason,
                operation="new-conversation",
                next_action="open a new provider conversation manually, "
                "then resume watching",
            )
            return self.phase
        except Exception as exc:
            self.phase = BLOCKED
            self.block_reason = (
                f"new conversation failed for "
                f"`{self.adapter.provider_name}` via automatic "
                f"new-conversation operation: {exc}; no prompt was sent"
            )
            self._record("error", self.block_reason)
            self._diag(
                "error",
                "new conversation failed",
                result="blocked",
                message=self.block_reason,
                current_spec=next_target,
                active_queue=tuple(check.active),
                evidence_source=check.evidence_source,
                decision="blocked",
                blocker=self.block_reason,
                operation="new-conversation",
                next_action="verify the provider session before continuing",
                recovery="verify the provider session before continuing",
            )
            return self.phase
        ready = self._await_ready()
        if ready is None:
            return self._abort_fresh_wait(next_target, list(check.active))
        if not ready:
            self.phase = BLOCKED
            self.block_reason = (
                "new conversation never reported an input-ready surface; "
                "no prompt was sent"
            )
            self._record(
                "readiness",
                "fresh input-ready surface not observed after "
                f"{self.last_fresh_ready_attempts} attempt(s); no prompt sent",
            )
            self._record("error", self.block_reason)
            self._diag(
                "provider",
                "fresh input-ready surface never observed",
                result="blocked",
                message=self.block_reason,
                current_spec=next_target,
                active_queue=tuple(check.active),
                evidence_source=check.evidence_source,
                decision="blocked",
                blocker=self.block_reason,
                operation="new-conversation",
                next_action="verify the provider session shows an "
                "input-ready surface, then resume watching",
            )
            return self.phase
        self._record(
            "readiness",
            "fresh input-ready surface observed after "
            f"{self.last_fresh_ready_attempts} attempt(s)",
        )
        self._send(self.config.continuation_prompt)
        self.prompts_sent += 1
        self.stable_polls = 0
        self.phase = CONTINUING
        error_category = self.boundary_error_category or "clean-finish"
        self._record(
            "prompt",
            f"sent continuation prompt in a fresh conversation "
            f"(error_category={error_category})",
        )
        self._diag(
            "prompt",
            "sent continuation prompt",
            result="sent",
            message="sent continuation prompt in a fresh conversation; "
            f"error_category={error_category}; no raw provider capture stored",
            current_spec=next_target,
            active_queue=tuple(check.active),
            evidence_source=check.evidence_source,
            decision="continuation",
            operation="new-conversation",
            next_action="supervise the fresh conversation until the next "
            "stable input-ready surface",
        )
        self.boundary_error_category = ""
        return self.phase

    def _open_confirmation(self, check: BoundaryCheck, instruction: str = "") -> str:
        """Recover unfinished tasks via the adapter contract only.

        The confirmation target is recorded before any provider input.
        A `ready-to-archive` boundary carries the archival instruction so
        the recovery conversation archives and validates instead of
        advancing. Provider commands, restart details, and
        input-delivery rules stay inside the adapter
        (`new_conversation`); this method never branches on provider
        identity or command strings. The confirmation prompt is sent only
        after the fresh input-ready surface is observed, so a repeated
        unfinished boundary simply opens another bounded attempt.
        """
        target = check.current_spec.strip()
        if not target:
            self.phase = BLOCKED
            self.block_reason = (
                "confirmation has no recorded change to recover; "
                "verify the conversation record before continuing"
            )
            self._record("error", self.block_reason)
            self._diag(
                "error",
                "confirmation has no recorded change",
                result="blocked",
                message=self.block_reason,
                active_queue=tuple(check.active),
                evidence_source=check.evidence_source,
                decision="blocked",
                blocker=self.block_reason,
                operation="new-conversation",
                next_action="verify the conversation record before continuing",
            )
            return self.phase
        if not self._record_before_prompt("confirmation", target, list(check.active)):
            return self.phase
        self.phase = NEW_CONVERSATION
        detail = check.task_detail or (
            f"`{check.current_spec}` has {check.open_tasks} open task(s)"
        )
        if instruction and instruction != detail:
            detail = f"{detail}; recovery instruction: {instruction}"
        error_category = self.boundary_error_category or "clean-finish"
        self._record(
            "prompt",
            f"confirmation recovery selected: {detail} "
            f"(error_category={error_category})",
        )
        self._diag(
            "prompt",
            "confirmation recovery selected",
            result="selected",
            message=f"{detail}; error_category={error_category}",
            current_spec=target,
            open_tasks=check.open_tasks,
            active_queue=tuple(check.active),
            evidence_source=check.evidence_source,
            decision=check.decision,
            operation="new-conversation",
            next_action="open a fresh conversation and send the "
            "confirmation prompt after the input-ready surface",
        )
        try:
            self.adapter.new_conversation()
        except UnsupportedOperation as exc:
            self.phase = BLOCKED
            self.block_reason = (
                f"`{self.adapter.provider_name}` automatic confirmation "
                f"unavailable: {exc}"
            )
            self._record("error", self.block_reason)
            self._diag(
                "error",
                "automatic confirmation unavailable",
                result="blocked",
                message=self.block_reason,
                current_spec=target,
                open_tasks=check.open_tasks,
                active_queue=tuple(check.active),
                evidence_source=check.evidence_source,
                decision="blocked",
                blocker=self.block_reason,
                operation="new-conversation",
                next_action="open a new provider conversation manually, "
                "then resume watching",
            )
            return self.phase
        except Exception as exc:
            self.phase = BLOCKED
            self.block_reason = (
                "new conversation failed for "
                f"`{self.adapter.provider_name}` via automatic "
                f"new-conversation operation: {exc}; no prompt was sent"
            )
            self._record("error", self.block_reason)
            self._diag(
                "error",
                "new conversation failed",
                result="blocked",
                message=self.block_reason,
                current_spec=target,
                open_tasks=check.open_tasks,
                active_queue=tuple(check.active),
                evidence_source=check.evidence_source,
                decision="blocked",
                blocker=self.block_reason,
                operation="new-conversation",
                next_action="verify the provider session before continuing",
                recovery="verify the provider session before continuing",
            )
            return self.phase
        self._record("readiness", "waiting for the fresh input-ready surface")
        ready = self._await_ready()
        if ready is None:
            return self._abort_fresh_wait(target, list(check.active))
        if not ready:
            self.phase = BLOCKED
            self.block_reason = (
                "new conversation never reported an input-ready surface; "
                "no prompt was sent"
            )
            self._record(
                "readiness",
                "fresh input-ready surface not observed after "
                f"{self.last_fresh_ready_attempts} attempt(s); no prompt sent",
            )
            self._record("error", self.block_reason)
            self._diag(
                "provider",
                "fresh input-ready surface never observed",
                result="blocked",
                message=self.block_reason,
                current_spec=target,
                open_tasks=check.open_tasks,
                active_queue=tuple(check.active),
                evidence_source=check.evidence_source,
                decision="blocked",
                blocker=self.block_reason,
                operation="new-conversation",
                next_action="verify the provider session shows an "
                "input-ready surface, then resume watching",
            )
            return self.phase
        self._record(
            "readiness",
            "fresh input-ready surface observed after "
            f"{self.last_fresh_ready_attempts} attempt(s)",
        )
        self._send(self.config.confirmation_prompt)
        self.prompts_sent += 1
        self.confirmations_sent += 1
        self.stable_polls = 0
        self.phase = CONTINUING
        error_category = self.boundary_error_category or "clean-finish"
        self._record(
            "prompt",
            f"sent confirmation prompt in a fresh conversation "
            f"(error_category={error_category})",
        )
        self._diag(
            "prompt",
            "sent confirmation prompt",
            result="sent",
            message="sent confirmation prompt in a fresh conversation; "
            f"error_category={error_category}; no raw provider capture stored",
            current_spec=target,
            open_tasks=check.open_tasks,
            active_queue=tuple(check.active),
            evidence_source=check.evidence_source,
            decision="confirmation",
            operation="new-conversation",
            next_action="supervise the fresh conversation until the next "
            "stable input-ready surface",
        )
        self.boundary_error_category = ""
        return self.phase

    def _abort_fresh_wait(self, target: str, active: list[str]) -> str:
        """Handle an operator-aborted fresh-ready wait without prompting.

        A `PAUSE` abort parks the watcher in PAUSED so Play resumes it and
        the still-open boundary refires on the next stable surface;
        quit/shutdown parks it BLOCKED with the exact reason so the run
        loop can stop. Never sends provider input.
        """
        if self._fresh_ready_aborted == "paused":
            self.phase = PAUSED
            self.stable_polls = 0
            self._record(
                "pause",
                "daemon mode PAUSE observed during fresh-ready wait; "
                "no prompt was sent",
            )
            self._diag(
                "pause",
                "fresh-ready wait paused",
                result="paused",
                message="daemon mode PAUSE observed during fresh-ready wait; "
                "no prompt was sent",
                current_spec=target,
                active_queue=tuple(active),
                decision="paused",
                operation="new-conversation",
                next_action="resume watching to retry the fresh conversation",
            )
            return self.phase
        self.phase = BLOCKED
        self.block_reason = (
            "fresh-ready wait interrupted by shutdown; no prompt was sent"
        )
        self._record("error", self.block_reason)
        self._diag(
            "shutdown",
            "fresh-ready wait interrupted",
            result="blocked",
            message=self.block_reason,
            current_spec=target,
            active_queue=tuple(active),
            decision="blocked",
            blocker=self.block_reason,
            operation="new-conversation",
            next_action="resolve the shutdown, then resume watching",
        )
        return self.phase

    def _await_ready(self, sleep: Callable[[float], None] | None = None) -> bool | None:
        """Bounded wait for the new input surface (no prompt until ready).

        Polls up to `fresh_ready_attempts` times with
        `fresh_ready_interval_s` between attempts so a transient
        post-`new_conversation` settle gap does not block the recovery.
        Still requires `debounce_polls` consecutive ready observations
        before reporting ready. Returns True when ready, False when the
        bound is exhausted, and None when quit, managed shutdown, or
        observed `PAUSE` aborts the wait (`_fresh_ready_aborted` names
        the abort as `"paused"` or `"stopped"`). The attempt count of
        the latest wait is kept on `last_fresh_ready_attempts` for
        activity records.
        """
        do_sleep = sleep if sleep is not None else time.sleep
        bound = max(self.config.fresh_ready_attempts, 1)
        needed = max(self.config.debounce_polls, 1)
        stable = 0
        self.last_fresh_ready_attempts = 0
        self._fresh_ready_aborted = ""
        for attempt in range(1, bound + 1):
            if self._quit or (
                self.shutdown_requested is not None and self.shutdown_requested()
            ):
                self._fresh_ready_aborted = "stopped"
                return None
            if self.mode_requested is not None and self.mode_requested() == "PAUSE":
                self._fresh_ready_aborted = "paused"
                return None
            self.last_fresh_ready_attempts = attempt
            capture = self._capture()
            provider_state = self.adapter.provider_state()
            if self.adapter.provider_state_required:
                ready = provider_state == "idle"
            else:
                ready = (
                    classify_capture(
                        self.adapter.provider_name,
                        capture,
                        input_ready=self.adapter.is_input_ready(capture),
                    )
                    == CLASS_FINISHED
                )
            if ready:
                stable += 1
                if stable >= needed:
                    return True
            else:
                stable = 0
            if attempt < bound:
                do_sleep(self.config.fresh_ready_interval_s)
        return False

    def run(
        self,
        sleep: Callable[[float], None] | None = None,
    ) -> RobotReport:
        """Poll until done, blocked, quit, or the poll budget is spent."""
        do_sleep = sleep if sleep is not None else time.sleep
        polls = 0
        self._diag(
            "startup",
            "watcher started",
            result="started",
            message=f"watching session `{self.config.session}`",
            decision="started",
            operation="watch",
            next_action="observe the provider session until a stable "
            "input-ready surface",
        )
        while True:
            if self._quit:
                self._diag(
                    "shutdown",
                    "watcher quit requested",
                    result="stopped",
                    message=self.block_reason or "provider session untouched",
                    decision="stopped",
                    blocker=self.block_reason,
                    operation="shutdown",
                    next_action="re-run the watcher to resume supervision",
                )
                return RobotReport(
                    outcome=STOPPED,
                    detail=(
                        self.block_reason
                        or "quit requested; the provider session is untouched"
                    ),
                    prompts_sent=self.prompts_sent,
                )
            if self.shutdown_requested is not None and self.shutdown_requested():
                self.request_quit()
                self.block_reason = "managed shutdown requested"
                self._record("shutdown", "managed shutdown requested")
                self._diag(
                    "shutdown",
                    "managed shutdown requested",
                    result="stopped",
                    message="managed shutdown requested",
                    decision="stopped",
                    operation="shutdown",
                    next_action="stopped; re-run the watcher to resume",
                )
                continue
            if self.phase in (DONE, BLOCKED):
                outcome = "done" if self.phase == DONE else BLOCKED
                detail = self.block_reason or self._done_detail()
                self._diag(
                    "shutdown" if outcome == "done" else "boundary",
                    f"watcher {outcome}",
                    result=outcome,
                    message=detail,
                    decision=outcome,
                    blocker="" if outcome == "done" else detail,
                    operation="shutdown",
                    next_action="stop the managed workflow"
                    if outcome == "done"
                    else "resolve the blocker, then resume watching",
                )
                return RobotReport(
                    outcome=outcome,
                    detail=detail,
                    prompts_sent=self.prompts_sent,
                )
            if self.config.max_polls and polls >= self.config.max_polls:
                self._diag(
                    "shutdown",
                    "poll budget spent",
                    result="max-polls",
                    message=f"poll budget of {self.config.max_polls} spent "
                    f"in phase `{self.phase}`; no completion claimed",
                    decision="max-polls",
                    blocker=f"poll budget of {self.config.max_polls} spent "
                    f"in phase `{self.phase}`",
                    operation="watch",
                    next_action="raise `--max-polls` and re-run to continue",
                )
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
