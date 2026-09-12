"""State-driven orchestration: inspect, determine, execute, persist.

Data flow per cycle: read handoff -> inspect repository -> determine next
action -> run adapter -> collect outcome -> persist handoff -> reset or stop.

The runner never selects work by enumerating spec files alone, never marks
work complete from agent prose, and persists before ending so a restart
resumes from durable state. Verification is a boundary here
(`UnavailableVerifier` until verification-logging-and-observability ships):
without a passed verification nothing advances and the runner stops after
persisting the outcome.
"""

from __future__ import annotations

import abc
import dataclasses
from pathlib import Path

from . import handoff as handoff_mod
from .adapters import AdapterError, AgentAdapter, StartupError, select_reset
from .config import Config

CONTEXT_STRATEGIES = ("per-spec", "per-task", "token-threshold", "manual", "never")

ACTION_RESOLVE_ISSUE = "resolve-issue"
ACTION_ADVANCE_SPEC = "advance-spec"
ACTION_START_SPEC = "start-spec"
ACTION_STOP = "stop"
ACTION_IDLE = "idle"


@dataclasses.dataclass
class VerificationResult:
    passed: bool
    detail: str


class Verifier(abc.ABC):
    """Verification boundary consumed by the runner."""

    @abc.abstractmethod
    def verify(self, action: str, output: str) -> VerificationResult:
        """Judge an adapter outcome. Never called with trusted completion."""


class UnavailableVerifier(Verifier):
    """Placeholder until shell verification is implemented."""

    def verify(self, action: str, output: str) -> VerificationResult:
        return VerificationResult(
            passed=False,
            detail=(
                "verification unavailable: shell verification arrives with "
                "`verification-logging-and-observability`; "
                "no work is marked complete"
            ),
        )


@dataclasses.dataclass
class CycleResult:
    kind: str
    action: str
    outcome: str
    detail: str
    stopped: bool
    stop_reason: str | None = None


@dataclasses.dataclass
class RepositoryView:
    spec_dir: str
    specs: list
    missing_spec_dir: bool = False


def inspect_repository(project_dir: Path, spec_dir: str) -> RepositoryView:
    """Inspect durable repository state: which spec changes exist."""
    path = project_dir / spec_dir
    if not path.is_dir():
        return RepositoryView(spec_dir=spec_dir, specs=[], missing_spec_dir=True)
    specs = sorted(entry.name for entry in path.iterdir() if entry.is_dir())
    return RepositoryView(spec_dir=spec_dir, specs=specs)


def select_next_action(
    handoff: handoff_mod.Handoff, repo: RepositoryView
) -> tuple[str, str]:
    """Determine the next action. OPEN issues precede spec advancement."""
    opens = handoff_mod.open_items(handoff)
    if opens:
        top = opens[0]
        return ACTION_RESOLVE_ISSUE, f"{top.id}: {top.description}"
    if handoff.current_spec is not None:
        if handoff.current_spec not in repo.specs:
            return (
                ACTION_STOP,
                f"current spec `{handoff.current_spec}` missing from {repo.spec_dir}",
            )
        return ACTION_ADVANCE_SPEC, handoff.current_spec
    if handoff.next_spec is not None:
        return ACTION_START_SPEC, handoff.next_spec
    return ACTION_IDLE, "no unresolved issues and no current or next spec"


def select_context_strategy(config: Config) -> str:
    if config.context_strategy not in CONTEXT_STRATEGIES:
        raise AdapterError(
            f"invalid context_strategy `{config.context_strategy}`: "
            f"expected one of {', '.join(CONTEXT_STRATEGIES)}"
        )
    return config.context_strategy


def apply_reset(
    adapter: AgentAdapter, reset_mode: str, boundary_reached: bool
) -> str | None:
    """Apply soft/hard/auto reset once a spec or task boundary completes."""
    if not boundary_reached:
        return None
    selection = select_reset(reset_mode, adapter.capabilities)
    if selection == "soft":
        adapter.new_session()
    else:
        adapter.terminate()
        adapter.start()
    return selection


class Runner:
    """One orchestration session over durable handoff state."""

    def __init__(
        self,
        project_dir: Path,
        config: Config,
        adapter: AgentAdapter,
        verifier: Verifier | None = None,
    ) -> None:
        self.project_dir = project_dir
        self.config = config
        self.adapter = adapter
        self.verifier = verifier or UnavailableVerifier()
        self.handoff_path = project_dir / config.handoff_file
        self.cycles: list[CycleResult] = []

    def _load(self) -> handoff_mod.Handoff:
        handoff = handoff_mod.read_handoff(self.handoff_path)
        if not handoff.session_id:
            from . import state as state_mod

            try:
                handoff.session_id = state_mod.read(self.project_dir).session_id
            except state_mod.StateError:
                handoff.session_id = ""
        return handoff

    def _save(self, handoff: handoff_mod.Handoff) -> None:
        handoff_mod.write_handoff(self.handoff_path, handoff)
        from . import state as state_mod

        try:
            stored = state_mod.read(self.project_dir)
        except state_mod.StateError:
            return
        stored.current_spec = handoff.current_spec
        stored.unresolved_count = handoff_mod.count_unresolved(handoff)
        state_mod.write(self.project_dir, stored)

    def _stop_for_blocker(
        self, handoff: handoff_mod.Handoff, reason: str
    ) -> CycleResult:
        handoff.status = "blocked"
        handoff.next_action = "none — blocked"
        self._save(handoff)
        if self.config.blocker_policy == "stop-on-blocker":
            return CycleResult(
                kind=ACTION_STOP,
                action="none — blocked",
                outcome="blocked",
                detail=reason,
                stopped=True,
                stop_reason="blocked",
            )
        return CycleResult(
            kind=ACTION_STOP,
            action="none — blocked",
            outcome="blocked",
            detail=f"{reason} (recorded; continuing per blocker policy)",
            stopped=False,
            stop_reason=None,
        )

    def run_once(self) -> CycleResult:
        try:
            handoff = self._load()
        except handoff_mod.HandoffError as exc:
            return CycleResult(
                kind=ACTION_STOP,
                action="none — unreadable handoff",
                outcome="failed",
                detail=str(exc),
                stopped=True,
                stop_reason="handoff-error",
            )
        repo = inspect_repository(self.project_dir, self.config.spec_dir)
        if repo.missing_spec_dir:
            handoff_mod.add_item(
                handoff,
                type="blocker",
                description=f"spec directory `{self.config.spec_dir}` is missing",
                priority="high",
            )
            return self._stop_for_blocker(handoff, "spec directory missing")

        blockers = [
            item for item in handoff.unresolved if item.status == "BLOCKED"
        ]
        if blockers and self.config.blocker_policy == "stop-on-blocker":
            return self._stop_for_blocker(
                handoff, f"{len(blockers)} BLOCKED item(s) present"
            )

        kind, target = select_next_action(handoff, repo)
        if kind == ACTION_IDLE:
            handoff.status = (
                "complete"
                if handoff.current_spec is None
                and handoff.next_spec is None
                and not handoff_mod.open_items(handoff)
                else "idle"
            )
            handoff.next_action = "none — idle"
            self._save(handoff)
            result = CycleResult(
                kind=kind, action="none — idle", outcome="idle",
                detail=target, stopped=True, stop_reason="idle",
            )
            self.cycles.append(result)
            return result
        if kind == ACTION_STOP:
            handoff_mod.add_item(
                handoff, type="blocker",
                description=target, priority="high",
            )
            result = self._stop_for_blocker(handoff, target)
            self.cycles.append(result)
            return result
        return self._execute(handoff, kind, target)

    def _execute(
        self, handoff: handoff_mod.Handoff, kind: str, target: str
    ) -> CycleResult:
        action = f"{kind} {target}"
        try:
            self.adapter.start()
        except StartupError as exc:
            handoff_mod.add_item(
                handoff, type="blocker",
                description=f"provider failed to start for `{action}`: {exc}",
                priority="high",
            )
            result = self._stop_for_blocker(handoff, "provider startup failed")
            self.cycles.append(result)
            return result
        prompt = (
            f"Ariadex next action [{kind}]: {target}\n"
            f"Spec directory: {self.config.spec_dir}\n"
            "Complete only work verifiable by the configured verification "
            "commands; report blockers instead of claiming progress."
        )
        try:
            self.adapter.send(prompt)
            output = self.adapter.capture_output()
        except AdapterError as exc:
            handoff_mod.add_item(
                handoff, type="blocker",
                description=f"adapter failed during `{action}`: {exc}",
                priority="high",
            )
            result = self._stop_for_blocker(handoff, "adapter failure")
            self.cycles.append(result)
            return result

        verdict = self.verifier.verify(action, output)
        if not verdict.passed:
            if kind == ACTION_RESOLVE_ISSUE:
                item_id = target.split(":", 1)[0]
                try:
                    item = handoff_mod.get_item(handoff, item_id)
                    item.history.append(
                        {"from": "OPEN", "to": "OPEN",
                         "at": handoff_mod.now_iso(),
                         "note": f"attempted; {verdict.detail}"}
                    )
                except handoff_mod.HandoffError:
                    pass
            handoff.status = "in-progress"
            handoff.next_action = action
            self._save(handoff)
            result = CycleResult(
                kind=kind, action=action, outcome="unverified",
                detail=verdict.detail, stopped=True,
                stop_reason="verification-unavailable",
            )
            self.cycles.append(result)
            return result

        boundary = self._apply_completion(handoff, kind, target)
        strategy = select_context_strategy(self.config)
        reset = None
        if strategy in ("per-spec", "per-task"):
            try:
                reset = apply_reset(self.adapter, self.config.reset_mode, boundary)
            except AdapterError as exc:
                handoff_mod.add_item(
                    handoff, type="blocker",
                    description=f"reset failed after `{action}`: {exc}",
                    priority="high",
                )
                result = self._stop_for_blocker(handoff, "reset failed")
                self.cycles.append(result)
                return result
        next_kind, next_target = select_next_action(
            handoff, inspect_repository(self.project_dir, self.config.spec_dir)
        )
        handoff.next_action = (
            "none — idle" if next_kind in (ACTION_IDLE, ACTION_STOP)
            else f"{next_kind} {next_target}"
        )
        self._save(handoff)
        result = CycleResult(
            kind=kind, action=action, outcome="completed",
            detail=f"verified; reset={reset}; next: {handoff.next_action}",
            stopped=False, stop_reason=None,
        )
        self.cycles.append(result)
        return result

    def _apply_completion(
        self, handoff: handoff_mod.Handoff, kind: str, target: str
    ) -> bool:
        """Record a verified completion. Returns whether a boundary closed."""
        if kind == ACTION_RESOLVE_ISSUE:
            item_id = target.split(":", 1)[0]
            handoff_mod.set_item_status(
                handoff, item_id, "RESOLVED", note="verified completion"
            )
            return True
        if kind == ACTION_ADVANCE_SPEC:
            handoff.completed.append(
                handoff_mod.CompletedItem(
                    id=f"c-{len(handoff.completed) + 1}",
                    summary=f"completed spec `{handoff.current_spec}`",
                )
            )
            handoff.current_spec = handoff.next_spec
            handoff.current_spec_file = (
                f"{self.config.spec_dir}/{handoff.next_spec}"
                if handoff.next_spec else None
            )
            handoff.next_spec = None
            handoff.status = (
                "complete" if handoff.current_spec is None else "in-progress"
            )
            return True
        if kind == ACTION_START_SPEC:
            handoff.current_spec = handoff.next_spec
            handoff.current_spec_file = (
                f"{self.config.spec_dir}/{handoff.next_spec}"
            )
            handoff.next_spec = None
            handoff.status = "in-progress"
            return True
        return False

    def run(self, max_cycles: int = 10) -> list[CycleResult]:
        """Loop cycles until stop. Bounded so an unverified loop cannot spin."""
        while len(self.cycles) < max_cycles:
            result = self.run_once()
            if result.stopped:
                break
        return self.cycles
