"""Boundary diagnostic evidence: every no-advance decision is diagnosable.

Covers structured no-advance fields (classification, recorded current
spec, authoritative queue, task counts, decision, blocker, operation,
next action) at provider stops, boundary evaluations, failed
new-conversation operations, blocked transitions, and shutdown; widget
retention/rendering of the bounded chronological evidence with the exact
blocker and next action; and Copy log/Context carrying the same redacted
evidence without secrets or raw transcripts.
"""

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from ariadex import companion as companion_mod
from ariadex import daemon as daemon_mod
from ariadex import diagnostics as diagnostics_mod
from ariadex import handoff as handoff_mod
from ariadex import providers as providers_mod
from ariadex import robot as robot_mod
from ariadex import terminal as terminal_mod

try:
    import evidence_fakes
except ModuleNotFoundError:
    from tests import evidence_fakes  # type: ignore[no-redef]

READY = "Welcome back\nAsk anything · tab agents\n> "
APPROVAL = "Ask anything\nApproval required: allow `rm`? [y/n]\n"
QUOTA = "Ask anything · tab agents\nModel quota expired. Switch model.\n> "
ERROR = "Ask anything\nerror: provider exploded\n"


class FakeDriver(terminal_mod.FakeTerminalDriver):
    def __init__(self) -> None:
        super().__init__()
        self.executable = "tmux"


def make_project(state: list) -> Path:
    tmp = tempfile.TemporaryDirectory()
    state.append(tmp)
    root = Path(tmp.name)
    (root / ".ariadex").mkdir(parents=True)
    handoff_mod.write_handoff(root / "HANDOFF.md", handoff_mod.empty_handoff("s"))
    (root / "openspec" / "changes").mkdir(parents=True)
    return root


def make_change(root: Path, name: str, tasks: str) -> None:
    change = root / "openspec" / "changes" / name
    change.mkdir(parents=True, exist_ok=True)
    (change / "tasks.md").write_text(tasks, encoding="utf-8")
    handoff = handoff_mod.read_handoff(root / "HANDOFF.md")
    handoff.current_spec = name
    handoff_mod.write_handoff(root / "HANDOFF.md", handoff)


def make_watcher(
    project: Path, driver: FakeDriver, output: str = READY, **overrides
) -> robot_mod.RobotWatcher:
    adapter = providers_mod.get_adapter("opencode", driver, "agent", project)
    params = {
        "session": "agent",
        "provider": "opencode",
        "initial_prompt": "please start",
        "debounce_polls": 1,
        "poll_interval_s": 0.01,
    }
    params.update(overrides)
    config = robot_mod.RobotConfig(**params)
    driver.sessions["agent"] = {"command": [], "output": output, "workdir": "/t"}
    return robot_mod.RobotWatcher(
        project,
        config,
        driver,
        adapter,
        evidence_runner=evidence_fakes.make_runner(project),
    )


def clean_git() -> unittest.mock._patch:
    """Compatibility context; robot scheduling no longer queries Git."""
    return unittest.mock.patch.object(
        robot_mod, "_git_tree_clean", return_value=(True, "")
    )


def last_record(project: Path) -> dict:
    records, _ = diagnostics_mod.read_diagnostics(project, limit=1)
    assert records, "expected at least one diagnostic record"
    return records[-1]


class NoAdvanceEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def test_approval_wait_carries_decision_and_next_action(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        watcher = make_watcher(project, driver, output=APPROVAL)
        self.assertEqual(watcher.poll(), "waiting")
        record = last_record(project)
        self.assertEqual(record["classification"], "approval")
        self.assertEqual(record["decision"], "waiting")
        self.assertIn("approval", record["blocker"])
        self.assertEqual(record["operation"], "")
        self.assertEqual(record["policy"], "prompt")
        self.assertIn("approval", record["next_action"])

    def test_quota_wait_names_operator_recovery(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        watcher = make_watcher(project, driver, output=QUOTA)
        self.assertEqual(watcher.poll(), "waiting")
        record = last_record(project)
        self.assertEqual(record["classification"], "waiting")
        self.assertEqual(record["decision"], "waiting")
        self.assertIn("quota", record["blocker"])
        self.assertIn("credentials", record["next_action"])

    def test_provider_error_blocked_with_recovery(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        watcher = make_watcher(project, driver, output=ERROR)
        self.assertEqual(watcher.poll(), "blocked")
        record = last_record(project)
        self.assertEqual(record["classification"], "error")
        self.assertEqual(record["decision"], "blocked")
        self.assertIn("error", record["blocker"])
        self.assertIn("resume watching", record["next_action"])

    def test_boundary_blocked_carries_queue_evidence_and_spec(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Open\n")
        driver = FakeDriver()
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        real_check = robot_mod.check_boundary

        def blocked(*args, **kwargs):
            return robot_mod.BoundaryCheck(
                ok=False,
                reason="git status refused: boom",
                active=["demo"],
                decision="blocked",
                current_spec="demo",
                task_detail="git status refused: boom",
                evidence_source="internal",
            )

        with (
            clean_git(),
            unittest.mock.patch.object(robot_mod, "check_boundary", blocked),
        ):
            try:
                self.assertEqual(watcher.poll(), "blocked")
            finally:
                robot_mod.check_boundary = real_check  # type: ignore[assignment]
        record = last_record(project)
        self.assertEqual(record["decision"], "blocked")
        self.assertIn("boom", record["blocker"])
        self.assertEqual(record["current_spec"], "demo")
        self.assertEqual(record["active_queue"], ["demo"])
        self.assertEqual(record["evidence_source"], "internal")
        self.assertIn("resume watching", record["next_action"])

    def test_done_stop_names_empty_decision(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        real_check = robot_mod.check_boundary

        def empty(*args, **kwargs):
            return robot_mod.BoundaryCheck(
                ok=True,
                reason="",
                active=[],
                decision="empty",
                evidence_source="internal",
            )

        with (
            clean_git(),
            unittest.mock.patch.object(robot_mod, "check_boundary", empty),
        ):
            try:
                self.assertEqual(watcher.poll(), "done")
            finally:
                robot_mod.check_boundary = real_check  # type: ignore[assignment]
        record = last_record(project)
        self.assertEqual(record["decision"], "empty")
        self.assertIn("stop", record["next_action"])

    def test_failed_new_conversation_names_operation_and_blocker(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [x] Done\n")
        driver = FakeDriver()
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        real_check = robot_mod.check_boundary

        def complete(*args, **kwargs):
            return robot_mod.BoundaryCheck(
                ok=True,
                reason="",
                active=["demo", "next"],
                decision="complete",
                current_spec="next",
                evidence_source="internal",
            )

        def failing() -> None:
            raise RuntimeError("restart refused")

        with (
            clean_git(),
            unittest.mock.patch.object(robot_mod, "check_boundary", complete),
            unittest.mock.patch.object(watcher, "_capture", side_effect=[READY, READY]),
            unittest.mock.patch.object(watcher.adapter, "new_conversation", failing),
        ):
            try:
                self.assertEqual(watcher.poll(), "blocked")
            finally:
                robot_mod.check_boundary = real_check  # type: ignore[assignment]
        record = last_record(project)
        self.assertEqual(record["decision"], "blocked")
        self.assertEqual(record["operation"], "new-conversation")
        self.assertIn("restart refused", record["blocker"])
        self.assertEqual(record["current_spec"], "next")
        self.assertEqual(record["active_queue"], ["demo", "next"])

    def test_fresh_ready_never_observed_blocks_with_next_action(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Open\n")
        driver = FakeDriver()
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        with (
            clean_git(),
            unittest.mock.patch.object(
                watcher, "_capture", side_effect=[READY, "blank screen"]
            ),
            unittest.mock.patch.object(watcher.adapter, "new_conversation"),
        ):
            self.assertEqual(watcher.poll(), "blocked")
        record = last_record(project)
        self.assertEqual(record["decision"], "blocked")
        self.assertEqual(record["operation"], "new-conversation")
        self.assertIn("input-ready", record["blocker"])
        self.assertIn("input-ready", record["next_action"])

    def test_max_polls_shutdown_is_diagnosable(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        watcher = make_watcher(project, driver, output="blank", max_polls=1)
        report = watcher.run(sleep=lambda _: None)
        self.assertEqual(report.outcome, "max-polls")
        record = last_record(project)
        self.assertEqual(record["decision"], "max-polls")
        self.assertIn("poll budget", record["blocker"])
        self.assertIn("--max-polls", record["next_action"])

    def test_evidence_gap_never_fabricates_values(self) -> None:
        record = diagnostics_mod.build_diagnostic(
            "boundary", "boundary evaluation blocked"
        )
        self.assertEqual(record["classification"], "")
        self.assertEqual(record["active_queue"], [])
        self.assertEqual(record["decision"], "")
        self.assertEqual(record["blocker"], "")
        self.assertEqual(record["next_action"], "")


class WidgetRetentionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def _seed_events(self, project: Path, count: int) -> None:
        for index in range(count):
            diagnostics_mod.try_record(
                project,
                diagnostics_mod.build_diagnostic(
                    "boundary",
                    f"event {index}",
                    result="blocked",
                    message=f"blocked reason {index}",
                    current_spec="demo",
                    decision="blocked",
                    blocker=f"exact blocker {index}",
                    operation="evaluate-boundary",
                    next_action=f"operator step {index}",
                    active_queue=("demo", "next"),
                ),
            )

    def test_widget_retains_bounded_chronological_evidence(self) -> None:
        project = make_project(self._tmp)
        self._seed_events(project, 25)
        state = {
            "diagnostic_context": daemon_mod.managed_diagnostic_context(project),
            "next_action": "none — blocked",
        }
        projection = companion_mod.build_managed_context(state)
        self.assertEqual(
            len(projection["events"]), companion_mod.MANAGED_LOG_VIEW_LINES
        )
        first = projection["events"][0]
        self.assertIn("event 5", first["action"])
        self.assertEqual(first["decision"], "blocked")
        self.assertIn("exact blocker 5", first["blocker"])
        self.assertIn("operator step 5", first["next_action"])
        self.assertEqual(first["active_queue"], ["demo", "next"])
        last = projection["events"][-1]
        self.assertIn("event 24", last["action"])
        self.assertIn("blocked", projection["latest_text"])
        self.assertIn("exact blocker 24", projection["latest_text"])
        self.assertIn("operator step 24", projection["latest_text"])

    def test_log_text_renders_blocker_and_next_action(self) -> None:
        project = make_project(self._tmp)
        self._seed_events(project, 2)
        state = {
            "diagnostic_context": daemon_mod.managed_diagnostic_context(project),
            "next_action": "none — blocked",
        }
        projection = companion_mod.build_managed_context(state)
        text = companion_mod.format_managed_log_text(projection)
        self.assertIn("decision=blocked", text)
        self.assertIn("blocker: exact blocker 0", text)
        self.assertIn("next: operator step 1", text)
        self.assertIn("queue=[demo, next]", text)

    def test_copy_snapshot_carries_decision_blocker_next(self) -> None:
        project = make_project(self._tmp)
        self._seed_events(project, 1)
        state = {
            "diagnostic_context": daemon_mod.managed_diagnostic_context(project),
            "next_action": "none — blocked",
            "provider": "opencode",
            "session": "agent",
            "mode": "AUTO",
            "open_count": 1,
            "blocked_count": 0,
        }
        projection = companion_mod.build_managed_context(state)
        snapshot = companion_mod.format_context_snapshot(projection, state)
        self.assertIn("decision: blocked", snapshot)
        self.assertIn("blocker: exact blocker 0", snapshot)
        self.assertIn("next: operator step 0", snapshot)
        self.assertIn("latest blocker: exact blocker 0", snapshot)

    def test_copy_evidence_is_redacted_and_bounded(self) -> None:
        project = make_project(self._tmp)
        diagnostics_mod.try_record(
            project,
            diagnostics_mod.build_diagnostic(
                "provider",
                "provider reports an error",
                result="blocked",
                message="token=supersecretvalue",
                decision="blocked",
                blocker="token=supersecretvalue needs rotation",
                next_action="fix it in the session, then resume watching",
            ),
        )
        state = {
            "diagnostic_context": daemon_mod.managed_diagnostic_context(project),
            "next_action": "none — blocked",
        }
        projection = companion_mod.build_managed_context(state)
        log_text = companion_mod.format_managed_log_text(projection)
        snapshot = companion_mod.format_context_snapshot(projection, state)
        for text in (log_text, snapshot):
            self.assertNotIn("supersecretvalue", text)
            self.assertIn("<redacted>", text)
            self.assertIn("blocked", text)


if __name__ == "__main__":
    unittest.main()
