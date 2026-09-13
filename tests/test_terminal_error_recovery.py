"""Recoverable provider terminal errors reach the task boundary.

Covers provider fixtures with a usable input-ready surface, quota/auth/
approval negative cases, provider-neutral classification with adapter
capability agreement, task-aware confirmation/continuation routing with
fresh-ready checks, and error-category recording without raw captures.
"""

import inspect
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from ariadex import handoff as handoff_mod
from ariadex import providers as providers_mod
from ariadex import robot as robot_mod
from ariadex import terminal as terminal_mod
from ariadex.adapters import AgentAdapter

try:
    import evidence_fakes
except ModuleNotFoundError:
    from tests import evidence_fakes  # type: ignore[no-redef]

READY_OPENCODE = "Welcome back\nAsk anything · tab agents\n> "
READY_CODEX = "OpenAI Codex\nAsk Codex to do anything\n> "
READY_CODEBUDDY = "CodeBuddy ready\ncodebuddy listening\n> "

TERMINAL_OPENCODE = (
    "Welcome back\nAsk anything · tab agents\n"
    "stream interrupted: connection reset by peer\n> "
)
TERMINAL_CODEX = (
    "OpenAI Codex\nAsk Codex to do anything\nrequest timed out; try again\n> "
)
TERMINAL_CODEBUDDY = (
    "CodeBuddy ready\ncodebuddy listening\nservice unavailable; try again later\n> "
)


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
    project: Path, driver: FakeDriver, provider: str = "opencode", **overrides
) -> robot_mod.RobotWatcher:
    adapter = providers_mod.get_adapter(provider, driver, "agent", project)
    params = {
        "session": "agent",
        "provider": provider,
        "initial_prompt": "please start",
        "debounce_polls": 1,
        "poll_interval_s": 0.01,
    }
    params.update(overrides)
    config = robot_mod.RobotConfig(**params)
    evidence_runner = overrides.get("evidence_runner")
    if evidence_runner is None:
        evidence_runner = evidence_fakes.make_runner(project)
    return robot_mod.RobotWatcher(
        project, config, driver, adapter, evidence_runner=evidence_runner
    )


class ClassifyTerminalErrorTest(unittest.TestCase):
    def test_opencode_terminal_error_with_ready_is_recoverable(self) -> None:
        self.assertEqual(
            robot_mod.classify_capture("opencode", TERMINAL_OPENCODE),
            robot_mod.CLASS_TERMINAL_ERROR,
        )

    def test_codex_terminal_error_with_ready_is_recoverable(self) -> None:
        self.assertEqual(
            robot_mod.classify_capture("codex", TERMINAL_CODEX),
            robot_mod.CLASS_TERMINAL_ERROR,
        )

    def test_codebuddy_terminal_error_with_ready_is_recoverable(self) -> None:
        self.assertEqual(
            robot_mod.classify_capture("codebuddy", TERMINAL_CODEBUDDY),
            robot_mod.CLASS_TERMINAL_ERROR,
        )

    def test_terminal_error_without_ready_stays_blocked(self) -> None:
        self.assertEqual(
            robot_mod.classify_capture("opencode", "stream interrupted\nworking…"),
            robot_mod.CLASS_ERROR,
        )

    def test_quota_wins_over_terminal_error(self) -> None:
        capture = (
            "Ask anything · tab agents\n"
            "stream interrupted\nrate limit reached; switch model\n> "
        )
        self.assertEqual(robot_mod.classify_capture("opencode", capture), "waiting")

    def test_auth_wins_over_terminal_error(self) -> None:
        capture = "Ask anything\nstream interrupted\nplease log in\n> "
        self.assertEqual(
            robot_mod.classify_capture("opencode", capture), robot_mod.CLASS_ERROR
        )
        # Auth without a terminal marker is also a plain error, never recoverable.
        self.assertEqual(
            robot_mod.classify_capture("codex", "please log in"),
            robot_mod.CLASS_ERROR,
        )

    def test_approval_wins_over_terminal_error(self) -> None:
        capture = "Ask anything\nstream interrupted\nApproval required: allow? [y/n]\n"
        self.assertEqual(
            robot_mod.classify_capture("opencode", capture), robot_mod.CLASS_APPROVAL
        )

    def test_generic_error_stays_blocked(self) -> None:
        capture = "Ask anything\nerror: provider exploded\n"
        self.assertEqual(
            robot_mod.classify_capture("opencode", capture), robot_mod.CLASS_ERROR
        )


class AdapterCapabilityTest(unittest.TestCase):
    def test_every_provider_declares_recoverable_markers(self) -> None:
        for provider in ("opencode", "codex", "codebuddy"):
            adapter_cls = providers_mod.ADAPTERS[provider]
            markers = adapter_cls.recoverable_error_markers
            self.assertTrue(markers, f"{provider} declares no markers")
            self.assertEqual(
                tuple(markers),
                robot_mod.RECOVERABLE_TERMINAL_ERROR_MARKERS[provider],
                f"{provider} adapter markers disagree with classification",
            )

    def test_base_adapter_declares_none(self) -> None:
        self.assertEqual(AgentAdapter.recoverable_error_markers, ())

    def test_recovery_paths_stay_provider_neutral(self) -> None:
        for name in ("_open_continuation", "_open_confirmation"):
            source = inspect.getsource(getattr(robot_mod.RobotWatcher, name))
            for banned in ("/new", "new_session", "soft_reset", "terminate"):
                self.assertNotIn(banned, source)
            for literal in ("'opencode'", "'codex'", "'codebuddy'"):
                self.assertNotIn(literal, source)
            self.assertIn("new_conversation", source)


class RoutingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def _clean_git(self) -> unittest.mock._patch:
        import subprocess

        real_run = subprocess.run

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["git", "status"]:
                return unittest.mock.Mock(returncode=0, stdout="", stderr="")
            return real_run(cmd, **kwargs)

        return unittest.mock.patch("ariadex.robot.subprocess.run", fake_run)

    def test_terminal_error_with_unfinished_tasks_sends_confirmation(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Open\n")
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": READY_OPENCODE,
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        with (
            self._clean_git(),
            unittest.mock.patch.object(
                watcher, "_capture", side_effect=[TERMINAL_OPENCODE, READY_OPENCODE]
            ),
            unittest.mock.patch.object(watcher.adapter, "new_conversation"),
        ):
            self.assertEqual(watcher.poll(), "continuing")
        # Confirmation prompt configured on the watcher is delivered.
        self.assertEqual(
            driver.sent_inputs("agent"), [watcher.config.confirmation_prompt]
        )
        self.assertEqual(watcher.confirmations_sent, 1)
        self.assertEqual(watcher.boundary_error_category, "")

    def test_terminal_error_after_completed_work_sends_continuation(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [x] Done\n")
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": READY_OPENCODE,
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        real_check = robot_mod.check_boundary

        def ok_complete(*args, **kwargs):
            return robot_mod.BoundaryCheck(
                ok=True,
                reason="",
                active=["demo", "next"],
                decision="complete",
                current_spec="next",
                evidence_source="internal",
            )

        with (
            self._clean_git(),
            unittest.mock.patch.object(
                watcher, "_capture", side_effect=[TERMINAL_OPENCODE, READY_OPENCODE]
            ),
            unittest.mock.patch.object(watcher.adapter, "new_conversation"),
            unittest.mock.patch.object(robot_mod, "check_boundary", ok_complete),
        ):
            try:
                self.assertEqual(watcher.poll(), "continuing")
            finally:
                robot_mod.check_boundary = real_check  # type: ignore[assignment]
        sent = driver.sent_inputs("agent")
        self.assertIn(robot_mod.DEFAULT_CONTINUATION_PROMPT, sent)

    def test_terminal_error_waits_for_fresh_ready_surface(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Open\n")
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": READY_OPENCODE,
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        with (
            self._clean_git(),
            unittest.mock.patch.object(
                watcher, "_capture", side_effect=[TERMINAL_OPENCODE, "blank screen"]
            ),
            unittest.mock.patch.object(watcher.adapter, "new_conversation"),
        ):
            self.assertEqual(watcher.poll(), "blocked")
        self.assertIn("never reported an input-ready surface", watcher.block_reason)
        self.assertEqual(watcher.confirmations_sent, 0)


class RecordingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def test_error_category_recorded_without_raw_capture(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Open\n")
        driver = FakeDriver()
        secret_capture = TERMINAL_OPENCODE + "token=supersecretvalue\n"
        driver.sessions["agent"] = {
            "command": [],
            "output": READY_OPENCODE,
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        import subprocess

        real_run = subprocess.run

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["git", "status"]:
                return unittest.mock.Mock(returncode=0, stdout="", stderr="")
            return real_run(cmd, **kwargs)

        with (
            unittest.mock.patch("ariadex.robot.subprocess.run", fake_run),
            unittest.mock.patch.object(
                watcher, "_capture", side_effect=[secret_capture, READY_OPENCODE]
            ),
            unittest.mock.patch.object(watcher.adapter, "new_conversation"),
        ):
            self.assertEqual(watcher.poll(), "continuing")
        messages = [event["message"] for event in watcher.activity_events]
        self.assertTrue(
            any("error_category=terminal-error" in message for message in messages),
            messages,
        )
        for message in messages:
            self.assertNotIn("supersecretvalue", message)


if __name__ == "__main__":
    unittest.main()
