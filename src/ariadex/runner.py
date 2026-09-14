"""State-driven orchestration: inspect, determine, execute, persist.

Data flow per cycle: read handoff -> inspect repository -> determine next
action -> run adapter -> collect outcome -> verify -> persist handoff ->
log and record metrics -> reset or stop.

The runner never selects work by enumerating spec files alone, never marks
work complete from agent prose, and persists before ending so a restart
resumes from durable state. Completion requires every configured shell
verification command to exit zero; failures schedule bounded retries and
then persist as unresolved or blocked.
"""

from __future__ import annotations

import contextlib
import dataclasses
from pathlib import Path

from . import handoff as handoff_mod
from . import logging as logging_mod
from . import spec_graph as spec_graph_mod
from .adapters import AdapterError, AgentAdapter, StartupError, select_reset
from .config import Config
from .verify import (
    ShellVerifier,
    UnavailableVerifier,
    Verifier,
)
from .verify import (
    VerificationResult as VerificationResult,
)

CONTEXT_STRATEGIES = ("per-spec", "per-task", "token-threshold", "manual", "never")

ACTION_RESOLVE_ISSUE = "resolve-issue"
ACTION_ADVANCE_SPEC = "advance-spec"
ACTION_START_SPEC = "start-spec"
ACTION_STOP = "stop"
ACTION_IDLE = "idle"
ACTION_CYCLE_LIMIT = "cycle-limit"


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
    dependencies: dict = dataclasses.field(default_factory=dict)
    graph_errors: dict = dataclasses.field(default_factory=dict)
    ignored_specs: dict = dataclasses.field(default_factory=dict)


def inspect_repository(project_dir: Path, spec_dir: str) -> RepositoryView:
    """Inspect durable repository state: which spec changes exist.

    Active discovery shares one boundary with graph loading, doctor,
    preview, and resync: the reserved `archive` directory, hidden
    entries, and non-directories are ignored with operator-visible
    reasons in `ignored_specs` and never scheduled. Also loads optional
    per-change dependency metadata (`depends_on` in `.openspec.yaml`).
    Malformed metadata is reported in `graph_errors` and never raises;
    scheduling treats it as a blocker.
    """
    path = project_dir / spec_dir
    if not path.is_dir():
        return RepositoryView(spec_dir=spec_dir, specs=[], missing_spec_dir=True)
    specs, ignored = spec_graph_mod.discover_active_changes(path)
    graph, errors = spec_graph_mod.load_graph(project_dir, spec_dir)
    return RepositoryView(
        spec_dir=spec_dir,
        specs=specs,
        dependencies=graph,
        graph_errors=errors,
        ignored_specs=ignored,
    )


def ensure_blocker_once(
    handoff: handoff_mod.Handoff, description: str, priority: str = "high"
) -> handoff_mod.UnresolvedItem:
    """Persist a blocker without duplicating identical open/blocked work.

    Dependency, cycle, and missing-spec reasons recur every cycle while the
    underlying state is unchanged. Reusing the existing item keeps the
    unresolved queue bounded while history retention still applies.
    """
    for item in handoff.unresolved:
        if (
            item.description == description
            and item.status in ("OPEN", "BLOCKED")
            and item.type == "blocker"
        ):
            return item
    return handoff_mod.add_item(
        handoff, type="blocker", description=description, priority=priority
    )


def select_next_action(
    handoff: handoff_mod.Handoff,
    repo: RepositoryView,
    retry_limit: int | None = None,
) -> tuple[str, str]:
    """Determine the next action. OPEN issues precede spec advancement.

    Issues whose attempts exceed `retry_limit` are skipped: no additional
    automatic attempt is scheduled for them.

    Explicit handoff targets (`current_spec`/`next_spec`) remain
    authoritative when valid; a missing or ineligible target returns STOP
    with a durable reason instead of silently selecting another spec. With
    no explicit target, the first eligible spec in deterministic
    topological order is selected; directory sort order alone never decides.
    """
    opens = handoff_mod.open_items(handoff)
    if retry_limit is not None:
        opens = [item for item in opens if item.attempts <= retry_limit]
    if opens:
        top = opens[0]
        return ACTION_RESOLVE_ISSUE, f"{top.id}: {top.description}"
    if repo.graph_errors:
        name = sorted(repo.graph_errors)[0]
        return (
            ACTION_STOP,
            f"spec `{name}` dependency metadata invalid: {repo.graph_errors[name]}",
        )
    if not repo.specs:
        # The queue is drained: a stale explicit target naming an archived
        # change must not hold the daemon status on blocked. Open issues
        # and graph errors above still precede.
        return ACTION_IDLE, "no active changes; queue drained"
    graph = (
        dict(repo.dependencies)
        if repo.dependencies
        else {name: [] for name in repo.specs}
    )
    for name in repo.specs:
        graph.setdefault(name, [])
    active = set(repo.specs)
    completed = spec_graph_mod.completed_spec_names(handoff)
    if handoff.current_spec is not None:
        target = handoff.current_spec
        if target not in active:
            return (
                ACTION_STOP,
                f"current spec `{target}` missing from {repo.spec_dir}",
            )
        ok, reason = spec_graph_mod.validate_target(target, graph, active, completed)
        if not ok:
            return ACTION_STOP, reason
        return ACTION_ADVANCE_SPEC, target
    if handoff.next_spec is not None:
        target = handoff.next_spec
        if target not in active:
            return (
                ACTION_STOP,
                f"next spec `{target}` missing from {repo.spec_dir}",
            )
        ok, reason = spec_graph_mod.validate_target(target, graph, active, completed)
        if not ok:
            return ACTION_STOP, reason
        return ACTION_START_SPEC, target
    eligible = spec_graph_mod.eligible_specs(graph, completed)
    if eligible:
        return ACTION_START_SPEC, eligible[0]
    if active:
        # Every active change already verified complete: the queue is
        # drained even though the directories still exist pre-archive.
        if active <= completed:
            return ACTION_IDLE, "all specs verified complete"
        # No eligible spec: name the underlying dependency reason so the
        # runner persists it instead of idling silently over blocked work.
        missing = spec_graph_mod.find_missing(graph, active, completed)
        if missing:
            name = sorted(missing)[0]
            deps = ", ".join(f"`{dep}`" for dep in missing[name])
            return (
                ACTION_STOP,
                f"spec `{name}` depends on missing {deps}; "
                "declare the predecessor or remove the dependency",
            )
        cycles = spec_graph_mod.find_cycles(graph)
        if cycles:
            cycle = cycles[0]
            chain = " -> ".join(f"`{part}`" for part in [*cycle, cycle[0]])
            return (
                ACTION_STOP,
                f"dependency cycle {chain}; break the cycle before scheduling",
            )
        # Every remaining spec waits on incomplete predecessors.
        name = eligible_specs_fallback(graph, active, completed)
        incomplete = spec_graph_mod.incomplete_predecessors(name, graph, completed)
        names = ", ".join(f"`{dep}`" for dep in incomplete) or "predecessors"
        return (
            ACTION_STOP,
            f"spec `{name}` waits on incomplete {names}; complete predecessors first",
        )
    return ACTION_IDLE, "no unresolved issues and no current or next spec"


def eligible_specs_fallback(
    graph: dict[str, list[str]], active: set[str], completed: set[str]
) -> str:
    """First alphabetically among active, incomplete, non-cyclic specs."""
    missing = spec_graph_mod.find_missing(graph, active, completed)
    blocked = spec_graph_mod.specs_in_cycles(spec_graph_mod.find_cycles(graph))
    candidates = sorted(
        name
        for name in active
        if name not in missing and name not in blocked and name not in completed
    )
    if candidates:
        return candidates[0]
    return sorted(active)[0]


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
        if verifier is not None:
            self.verifier = verifier
        elif config.verification_commands:
            self.verifier = ShellVerifier(config.verification_commands, project_dir)
        else:
            self.verifier = UnavailableVerifier()
        self.handoff_path = project_dir / config.handoff_file
        self.runs_dir = project_dir / ".ariadex" / logging_mod.RUNS_DIRNAME
        self.metrics_path = project_dir / ".ariadex" / logging_mod.METRICS_FILENAME
        self.cycles: list[CycleResult] = []
        self._ctx: dict = {}

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
        self._ctx["output"] = reason
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
        self._ctx = {
            "input": "",
            "output": "",
            "exit_code": None,
            "validation": "unavailable",
            "reset": None,
            "retries": 0,
        }
        started = logging_mod.now_iso()
        guard = self._mode_guard()
        result = guard if guard is not None else self._cycle()
        self._observe(result, started)
        self._announce(result)
        return result

    def _announce(self, result: CycleResult) -> None:
        """Record attention events and deliver opt-in notifications.

        Best-effort and isolated: observability never changes the cycle
        outcome, never sends provider input, and never fails the cycle.
        """
        from . import observability as observability_mod

        with contextlib.suppress(Exception):
            try:
                handoff = handoff_mod.read_handoff(self.handoff_path)
                session = handoff.session_id
                spec = handoff.current_spec
            except handoff_mod.HandoffError:
                session, spec = "", None
            try:
                usage = self.adapter.get_usage()
                usage_available = usage is not None
            except Exception:
                usage_available = False
            event = observability_mod.event_for_result(
                result,
                session=session,
                spec=spec,
                usage_available=usage_available,
            )
            if event is None:
                return
            with contextlib.suppress(TypeError, ValueError):
                event["retry_count"] = int(self._ctx.get("retries", 0))
            observability_mod.announce(self.project_dir, self.config, event)

    def _mode_guard(self) -> CycleResult | None:
        """Refuse automatic input unless the durable mode is AUTO.

        MANUAL keeps observation and logs but sends nothing; PAUSE allows
        no new scheduling operations. Neither path touches the adapter.
        """
        from . import control as control_mod
        from . import state as state_mod

        try:
            mode = state_mod.read(self.project_dir).mode
        except state_mod.StateError:
            return None
        if control_mod.allows_scheduling(mode):
            return None
        self._ctx["output"] = (
            f"mode is {mode}: no automatic input without `ariadex auto`"
        )
        return CycleResult(
            kind=ACTION_STOP,
            action=f"none — {mode} mode",
            outcome="mode-guard",
            detail=f"mode is {mode}: scheduling requires AUTO",
            stopped=True,
            stop_reason="not-auto",
        )

    def _observe(self, result: CycleResult, started: str) -> None:
        """Persist one run log and one metrics record per cycle."""
        try:
            handoff = handoff_mod.read_handoff(self.handoff_path)
        except handoff_mod.HandoffError:
            handoff = None
        ctx = self._ctx
        try:
            usage: object = logging_mod.usage_record(self.adapter.get_usage())
        except Exception:
            usage = "unavailable"
        ended = logging_mod.now_iso()
        record = logging_mod.RunLogRecord(
            session_id=handoff.session_id if handoff else "",
            spec=handoff.current_spec if handoff else None,
            action=result.action,
            input=ctx["input"],
            output=ctx["output"],
            exit_code=ctx["exit_code"],
            validation_result=ctx["validation"],
            reset_reason=ctx["reset"],
            retry_count=ctx["retries"],
            started_at=started,
            ended_at=ended,
        )
        logging_mod.write_run_log(self.runs_dir, record)
        logging_mod.append_metrics(
            self.metrics_path,
            {
                "schema_version": logging_mod.METRICS_SCHEMA_VERSION,
                "session": record.session_id,
                "spec": record.spec,
                "action": result.action,
                "outcome": result.outcome,
                "started_at": started,
                "ended_at": ended,
                "exit_code": ctx["exit_code"],
                "validation_result": ctx["validation"],
                "reset": ctx["reset"],
                "retry_count": ctx["retries"],
                "redactions": record.redaction_count,
                "usage": usage,
            },
        )
        # Enforce telemetry bounds after every cycle. Best-effort: a
        # pruning failure must never fail the cycle itself.
        with contextlib.suppress(Exception):
            logging_mod.apply_retention(
                self.runs_dir,
                self.metrics_path,
                retention_days=self.config.log_retention_days,
                log_max_bytes=self.config.log_max_bytes,
                metrics_max_bytes=self.config.metrics_max_bytes,
            )

    def _cycle(self) -> CycleResult:
        try:
            handoff = self._load()
        except handoff_mod.HandoffError as exc:
            self._ctx["output"] = str(exc)
            return CycleResult(
                kind=ACTION_STOP,
                action="none — unreadable handoff",
                outcome="failed",
                detail=str(exc),
                stopped=True,
                stop_reason="handoff-error",
            )
        unreconciled = self._unreconciled_interruption()
        if unreconciled is not None:
            return unreconciled
        repo = inspect_repository(self.project_dir, self.config.spec_dir)
        if repo.missing_spec_dir:
            handoff_mod.add_item(
                handoff,
                type="blocker",
                description=f"spec directory `{self.config.spec_dir}` is missing",
                priority="high",
            )
            return self._stop_for_blocker(handoff, "spec directory missing")

        blockers = [item for item in handoff.unresolved if item.status == "BLOCKED"]
        if blockers and self.config.blocker_policy == "stop-on-blocker":
            return self._stop_for_blocker(
                handoff, f"{len(blockers)} BLOCKED item(s) present"
            )

        kind, target = select_next_action(
            handoff, repo, retry_limit=self.config.retry_limit
        )
        if kind == ACTION_IDLE:
            handoff.status = (
                "complete"
                if handoff.current_spec is None
                and handoff.next_spec is None
                and not handoff_mod.open_items(handoff)
                else "idle"
            )
            handoff.next_action = "none — idle"
            self._ctx["output"] = target
            self._save(handoff)
            result = CycleResult(
                kind=kind,
                action="none — idle",
                outcome="idle",
                detail=target,
                stopped=True,
                stop_reason="idle",
            )
            self.cycles.append(result)
            return result
        if kind == ACTION_STOP:
            ensure_blocker_once(handoff, target)
            result = self._stop_for_blocker(handoff, target)
            self.cycles.append(result)
            return result
        return self._execute(handoff, kind, target)

    def _unreconciled_interruption(self) -> CycleResult | None:
        """Stop when a prior attempt died mid-delivery without recovery.

        A persisted uncertain phase means restart cannot prove whether
        provider input or verification completed. The runner sends nothing
        and requires explicit `ariadex recover` first; recovery records the
        blocker. Never guesses delivery complete.
        """
        from . import concurrency as concurrency_mod

        try:
            cycle = concurrency_mod.read_cycle(self.project_dir)
        except Exception:
            return None
        if cycle is None or cycle.phase not in concurrency_mod.UNCERTAIN_PHASES:
            return None
        self._ctx["output"] = (
            f"unreconciled interruption in phase `{cycle.phase}`"
            f"{f' for `{cycle.action}`' if cycle.action else ''}; "
            "run `ariadex recover` before retrying"
        )
        return CycleResult(
            kind=ACTION_STOP,
            action="none — unreconciled interruption",
            outcome="interrupted",
            detail=(
                f"interrupted in phase `{cycle.phase}`; "
                "explicit recovery required before retrying"
            ),
            stopped=True,
            stop_reason="interrupted",
        )

    def _cancel_requested(self) -> dict | None:
        """Return the pending takeover/pause cancellation signal, if any."""
        from . import concurrency as concurrency_mod

        try:
            return concurrency_mod.cancellation_requested(self.project_dir)
        except Exception:
            return None

    def _cancel_safe(
        self, handoff: handoff_mod.Handoff, action: str, cancel: dict
    ) -> CycleResult:
        """Stop before any provider input was sent: safe to retry later."""
        from . import concurrency as concurrency_mod

        handoff.next_action = action
        self._ctx["output"] = (
            f"cancelled before provider input for `{action}` "
            f"(requested by {cancel.get('requested_by', 'unknown')}); "
            "no input sent, safe to retry"
        )
        self._save(handoff)
        concurrency_mod.clear_cycle(self.project_dir)
        concurrency_mod.clear_cancellation(self.project_dir)
        return CycleResult(
            kind=ACTION_STOP,
            action="none — cancelled",
            outcome="cancelled",
            detail=self._ctx["output"],
            stopped=True,
            stop_reason="cancelled",
        )

    def _cancel_uncertain(
        self, handoff: handoff_mod.Handoff, action: str, cancel: dict, phase: str
    ) -> CycleResult:
        """Stop after provider input may have been delivered.

        Preserves the persisted phase for explicit `recover` handling and
        claims no completion: existing recovery semantics stay authoritative
        for uncertain delivery.
        """
        from . import concurrency as concurrency_mod

        handoff.status = "in-progress"
        handoff.next_action = action
        self._ctx["output"] = (
            f"cancelled in phase `{phase}` for `{action}` "
            f"(requested by {cancel.get('requested_by', 'unknown')}); "
            "provider input may have been delivered, no completion claimed; "
            "run `ariadex recover` before retrying"
        )
        self._save(handoff)
        concurrency_mod.clear_cancellation(self.project_dir)
        return CycleResult(
            kind=ACTION_STOP,
            action="none — cancelled",
            outcome="cancelled",
            detail=self._ctx["output"],
            stopped=True,
            stop_reason="cancelled",
        )

    def _execute(
        self, handoff: handoff_mod.Handoff, kind: str, target: str
    ) -> CycleResult:
        from . import concurrency as concurrency_mod

        action = f"{kind} {target}"
        concurrency_mod.write_cycle(
            self.project_dir, concurrency_mod.PHASE_BEFORE_SEND, action
        )
        cancel = self._cancel_requested()
        if cancel is not None:
            return self._cancel_safe(handoff, action, cancel)
        try:
            self.adapter.start()
        except StartupError as exc:
            handoff_mod.add_item(
                handoff,
                type="blocker",
                description=f"provider failed to start for `{action}`: {exc}",
                priority="high",
            )
            result = self._stop_for_blocker(handoff, "provider startup failed")
            self.cycles.append(result)
            concurrency_mod.clear_cycle(self.project_dir)
            return result
        prompt = (
            f"Ariadex next action [{kind}]: {target}\n"
            f"Spec directory: {self.config.spec_dir}\n"
            "Complete only work verifiable by the configured verification "
            "commands; report blockers instead of claiming progress."
        )
        try:
            self.adapter.send(prompt)
            concurrency_mod.write_cycle(
                self.project_dir, concurrency_mod.PHASE_SENT, action
            )
            output = self.adapter.capture_output()
            concurrency_mod.write_cycle(
                self.project_dir, concurrency_mod.PHASE_CAPTURED, action
            )
        except AdapterError as exc:
            handoff_mod.add_item(
                handoff,
                type="blocker",
                description=f"adapter failed during `{action}`: {exc}",
                priority="high",
            )
            result = self._stop_for_blocker(handoff, "adapter failure")
            self.cycles.append(result)
            concurrency_mod.clear_cycle(self.project_dir)
            return result

        cancel = self._cancel_requested()
        if cancel is not None:
            return self._cancel_uncertain(
                handoff, action, cancel, concurrency_mod.PHASE_CAPTURED
            )
        concurrency_mod.write_cycle(
            self.project_dir, concurrency_mod.PHASE_VERIFYING, action
        )
        verdict = self.verifier.verify(action, output)
        self._ctx["input"] = prompt
        self._ctx["output"] = output
        self._ctx["exit_code"] = verdict.exit_code
        if verdict.passed:
            self._ctx["validation"] = "passed"
        elif isinstance(self.verifier, UnavailableVerifier):
            self._ctx["validation"] = "unavailable"
        else:
            self._ctx["validation"] = "failed"
        if verdict.passed:
            concurrency_mod.write_cycle(
                self.project_dir, concurrency_mod.PHASE_COMPLETING, action
            )
            result = self._complete(handoff, kind, target, action)
            if result.stop_reason != "cancelled":
                concurrency_mod.clear_cycle(self.project_dir)
            return result
        if isinstance(self.verifier, UnavailableVerifier):
            handoff.status = "in-progress"
            handoff.next_action = action
            self._save(handoff)
            result = CycleResult(
                kind=kind,
                action=action,
                outcome="unverified",
                detail=verdict.detail,
                stopped=True,
                stop_reason="verification-unavailable",
            )
            self.cycles.append(result)
            concurrency_mod.clear_cycle(self.project_dir)
            return result
        result = self._retry_or_persist(handoff, kind, target, action, verdict.detail)
        concurrency_mod.clear_cycle(self.project_dir)
        return result

    def _failure_item(
        self,
        handoff: handoff_mod.Handoff,
        kind: str,
        target: str,
        action: str,
        detail: str,
    ) -> handoff_mod.UnresolvedItem:
        if kind == ACTION_RESOLVE_ISSUE:
            item_id = target.split(":", 1)[0]
            try:
                item = handoff_mod.get_item(handoff, item_id)
            except handoff_mod.HandoffError:
                item = handoff_mod.add_item(
                    handoff,
                    type="issue",
                    description=f"verification failed: {action}",
                    priority="high",
                )
        else:
            description = f"verification failed: {action}"
            matches = [
                item
                for item in handoff.unresolved
                if item.status == "OPEN" and item.description == description
            ]
            item = (
                matches[0]
                if matches
                else handoff_mod.add_item(
                    handoff, type="issue", description=description, priority="high"
                )
            )
        item.attempts += 1
        item.history.append(
            {
                "from": item.status,
                "to": item.status,
                "at": handoff_mod.now_iso(),
                "note": f"verification failed (attempt {item.attempts}): {detail}",
            }
        )
        return item

    def _retry_or_persist(
        self,
        handoff: handoff_mod.Handoff,
        kind: str,
        target: str,
        action: str,
        detail: str,
    ) -> CycleResult:
        item = self._failure_item(handoff, kind, target, action, detail)
        self._ctx["retries"] = item.attempts
        handoff.status = "in-progress"
        if item.attempts <= self.config.retry_limit:
            handoff.next_action = f"resolve-issue {item.id}: {item.description}"
            self._save(handoff)
            result = CycleResult(
                kind=kind,
                action=action,
                outcome="verification-failed",
                detail=f"{detail}; repair scheduled "
                f"(attempt {item.attempts}/{self.config.retry_limit})",
                stopped=False,
                stop_reason=None,
            )
            self.cycles.append(result)
            return result
        if self.config.blocker_policy == "stop-on-blocker":
            handoff_mod.set_item_status(
                handoff,
                item.id,
                "BLOCKED",
                note=f"retry limit reached: {detail}",
            )
            result = self._stop_for_blocker(handoff, "retry limit reached")
            self.cycles.append(result)
            return result
        handoff.next_action = self._plan_next(handoff)
        self._save(handoff)
        result = CycleResult(
            kind=kind,
            action=action,
            outcome="verification-failed",
            detail=f"{detail}; retry limit reached, recorded per policy",
            stopped=False,
            stop_reason=None,
        )
        self.cycles.append(result)
        return result

    def _plan_next(self, handoff: handoff_mod.Handoff) -> str:
        next_kind, next_target = select_next_action(
            handoff,
            inspect_repository(self.project_dir, self.config.spec_dir),
            retry_limit=self.config.retry_limit,
        )
        if next_kind in (ACTION_IDLE, ACTION_STOP):
            return "none — idle"
        return f"{next_kind} {next_target}"

    def _complete(
        self, handoff: handoff_mod.Handoff, kind: str, target: str, action: str
    ) -> CycleResult:
        from . import concurrency as concurrency_mod

        cancel = self._cancel_requested()
        if cancel is not None:
            return self._cancel_uncertain(
                handoff, action, cancel, concurrency_mod.PHASE_COMPLETING
            )
        boundary = self._apply_completion(handoff, kind, target)
        strategy = select_context_strategy(self.config)
        reset = None
        if strategy in ("per-spec", "per-task"):
            cancel = self._cancel_requested()
            if cancel is not None:
                # Verified completion stands, but reset would send provider
                # input: skip it and stop instead. The next loop iteration
                # mode-guards, so no new scheduling starts.
                self._ctx["reset"] = (
                    f"skipped (cancelled by {cancel.get('requested_by', 'unknown')})"
                )
                concurrency_mod.clear_cancellation(self.project_dir)
            else:
                try:
                    reset = apply_reset(self.adapter, self.config.reset_mode, boundary)
                except AdapterError as exc:
                    handoff_mod.add_item(
                        handoff,
                        type="blocker",
                        description=f"reset failed after `{action}`: {exc}",
                        priority="high",
                    )
                    result = self._stop_for_blocker(handoff, "reset failed")
                    self.cycles.append(result)
                    return result
        if self._ctx.get("reset") is None:
            self._ctx["reset"] = reset
        handoff.next_action = self._plan_next(handoff)
        self._save(handoff)
        result = CycleResult(
            kind=kind,
            action=action,
            outcome="completed",
            detail=f"verified; reset={self._ctx.get('reset')}; "
            f"next: {handoff.next_action}",
            stopped=False,
            stop_reason=None,
        )
        self.cycles.append(result)
        return result

    def _apply_completion(
        self, handoff: handoff_mod.Handoff, kind: str, target: str
    ) -> bool:
        """Record a verified completion. Returns whether a boundary closed."""
        if kind == ACTION_RESOLVE_ISSUE:
            item_id = target.split(":", 1)[0]
            self._ctx["retries"] = handoff_mod.get_item(handoff, item_id).attempts
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
                if handoff.next_spec
                else None
            )
            handoff.next_spec = None
            handoff.status = (
                "complete" if handoff.current_spec is None else "in-progress"
            )
            return True
        if kind == ACTION_START_SPEC:
            handoff.current_spec = target
            handoff.current_spec_file = f"{self.config.spec_dir}/{target}"
            handoff.next_spec = None
            handoff.status = "in-progress"
            return True
        return False

    def run(self, max_cycles: int = 10) -> list[CycleResult]:
        """Loop cycles until stop. Bounded so an unverified loop cannot spin.

        Exhausting the budget while work remains appends an explicit
        stopped `cycle-limit` result instead of returning an unstopped
        tail that reads as success. A zero (or negative) budget sends no
        provider input and returns the explicit incomplete result.
        """
        if max_cycles <= 0:
            return [self._cycle_limit_exhausted(budget=max_cycles, ran=0)]
        while len(self.cycles) < max_cycles:
            cancel = self._cancel_requested()
            if cancel is not None:
                # Takeover/pause arrived between cycles: honor it before any
                # new scheduling instead of starting another provider send.
                started = logging_mod.now_iso()
                self._ctx = {
                    "input": "",
                    "output": "",
                    "exit_code": None,
                    "validation": "unavailable",
                    "reset": None,
                    "retries": 0,
                }
                try:
                    pending = self._load()
                except handoff_mod.HandoffError as exc:
                    from . import concurrency as concurrency_mod

                    result = CycleResult(
                        kind=ACTION_STOP,
                        action="none — cancelled",
                        outcome="cancelled",
                        detail=f"cancelled between cycles; handoff unreadable: {exc}",
                        stopped=True,
                        stop_reason="cancelled",
                    )
                    self._ctx["output"] = str(exc)
                    self._observe(result, started)
                    self._announce(result)
                    concurrency_mod.clear_cancellation(self.project_dir)
                    self.cycles.append(result)
                    break
                result = self._cancel_safe(
                    pending, pending.next_action or "none — unknown", cancel
                )
                self._observe(result, started)
                self._announce(result)
                self.cycles.append(result)
                break
            result = self.run_once()
            if result.stopped:
                break
        if not self.cycles or not self.cycles[-1].stopped:
            self.cycles.append(
                self._cycle_limit_exhausted(budget=max_cycles, ran=len(self.cycles))
            )
        return self.cycles

    def _cycle_limit_exhausted(self, *, budget: int, ran: int) -> CycleResult:
        """Report an exhausted cycle budget without claiming completion.

        Recomputes and persists the remaining next action so a restart
        resumes from durable state. Sends no provider input, advances no
        spec, and resolves no issue: per-cycle verified completions stand,
        but the run itself is reported incomplete (`cycle-limit`).
        """
        started = logging_mod.now_iso()
        self._ctx = {
            "input": "",
            "output": "",
            "exit_code": None,
            "validation": "unavailable",
            "reset": None,
            "retries": 0,
        }
        try:
            handoff = self._load()
        except handoff_mod.HandoffError as exc:
            self._ctx["output"] = str(exc)
            result = CycleResult(
                kind=ACTION_CYCLE_LIMIT,
                action="none — cycle limit reached",
                outcome="cycle-limit",
                detail=f"cycle budget exhausted ({ran}/{budget}); {exc}",
                stopped=True,
                stop_reason="cycle-limit",
            )
            self._observe(result, started)
            self._announce(result)
            return result
        if budget <= 0:
            action = "none — no execution budget"
            detail = (
                f"no execution budget (max_cycles={budget}); no provider input sent"
            )
        else:
            action = self._plan_next(handoff)
            detail = (
                f"cycle budget exhausted ({ran}/{budget}); "
                f"remaining work preserved as `{action}`"
            )
        handoff.next_action = action
        self._ctx["output"] = detail
        self._save(handoff)
        result = CycleResult(
            kind=ACTION_CYCLE_LIMIT,
            action=action,
            outcome="cycle-limit",
            detail=detail,
            stopped=True,
            stop_reason="cycle-limit",
        )
        self._observe(result, started)
        self._announce(result)
        return result
