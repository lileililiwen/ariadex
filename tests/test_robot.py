"""Robot agent supervisor: watcher states, prompts, adapters, controls."""

import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

from ariadex import handoff as handoff_mod
from ariadex import providers as providers_mod
from ariadex import robot as robot_mod
from ariadex import terminal as terminal_mod
from ariadex.adapters import UnsupportedOperation

READY_OPENCODE = "Welcome back\nAsk anything · tab agents\n> "
READY_CODEX = "OpenAI Codex\nAsk Codex to do anything\n> "
READY_CODEBUDDY = "CodeBuddy ready\ncodebuddy listening\n> "
BUSY = "running tool `pytest` …\nesc to interrupt\n"
APPROVAL = "Ask anything\nApproval required: allow `rm`? [y/n]\n"
ERROR = "Ask anything\nerror: provider exploded\n"


class FakeDriver(terminal_mod.FakeTerminalDriver):
    """In-memory driver with tmux-style construction."""

    def __init__(self, executable: str = "tmux") -> None:
        super().__init__()
        self.executable = executable

    def terminated(self) -> list[str]:
        return [args[1] for op, *args in self.calls if op == "terminate"]


def make_project(monkey_state=None) -> Path:
    tmp = tempfile.TemporaryDirectory()
    monkey_state.append(tmp)
    root = Path(tmp.name)
    (root / ".ariadex").mkdir(parents=True)
    handoff_mod.write_handoff(
        root / ".ariadex" / "handoff.md", handoff_mod.empty_handoff("s")
    )
    (root / "openspec" / "changes").mkdir(parents=True)
    return root


def make_watcher(
    project: Path,
    driver: FakeDriver,
    provider: str = "opencode",
    **overrides,
) -> robot_mod.RobotWatcher:
    adapter = providers_mod.get_adapter(provider, driver, "agent", project)
    params = {
        "session": "agent",
        "provider": provider,
        "initial_prompt": "please start",
        "debounce_polls": 2,
        "poll_interval_s": 0.01,
    }
    params.update(overrides)
    config = robot_mod.RobotConfig(**params)
    return robot_mod.RobotWatcher(project, config, driver, adapter)


class ClassifyTest(unittest.TestCase):
    def test_opencode_ready_is_finished(self) -> None:
        self.assertEqual(
            robot_mod.classify_capture("opencode", READY_OPENCODE), "finished"
        )

    def test_codex_ready_is_finished(self) -> None:
        self.assertEqual(robot_mod.classify_capture("codex", READY_CODEX), "finished")

    def test_codebuddy_ready_is_finished(self) -> None:
        self.assertEqual(
            robot_mod.classify_capture("codebuddy", READY_CODEBUDDY), "finished"
        )

    def test_busy_markers_win_over_stale_ready_prompt(self) -> None:
        self.assertEqual(
            robot_mod.classify_capture("opencode", READY_OPENCODE + BUSY),
            "working",
        )

    def test_stale_approval_in_scrollback_does_not_block_current_ready(self) -> None:
        old = "Approval required: allow command? [y/n]"
        current = "Welcome back\nAsk anything · tab agents\n> "
        self.assertEqual(
            robot_mod.classify_capture("opencode", old + "\n" * 30 + current),
            "finished",
        )

    def test_single_done_word_is_never_finished(self) -> None:
        self.assertEqual(
            robot_mod.classify_capture("opencode", "all done, bye"), "unknown"
        )

    def test_approval_blocks(self) -> None:
        self.assertEqual(robot_mod.classify_capture("opencode", APPROVAL), "approval")

    def test_error_blocks(self) -> None:
        self.assertEqual(
            robot_mod.classify_capture("codex", READY_CODEX + ERROR), "error"
        )

    def test_auth_failure_blocks(self) -> None:
        self.assertEqual(robot_mod.classify_capture("codex", "please log in"), "error")

    def test_unknown_provider_never_finishes(self) -> None:
        self.assertEqual(robot_mod.classify_capture("wat", READY_OPENCODE), "unknown")

    def test_empty_capture_is_unknown(self) -> None:
        self.assertEqual(robot_mod.classify_capture("opencode", ""), "unknown")


class ConfigTest(unittest.TestCase):
    def test_defaults_carry_handoff_prompt(self) -> None:
        config = robot_mod.RobotConfig(session="s", initial_prompt="go")
        self.assertEqual(
            config.continuation_prompt, robot_mod.DEFAULT_CONTINUATION_PROMPT
        )
        self.assertIn("HANDOFF.md", config.continuation_prompt)

    def test_missing_session_refused(self) -> None:
        with self.assertRaises(robot_mod.RobotError):
            robot_mod.validate_config(
                robot_mod.RobotConfig(session=" ", initial_prompt="go")
            )

    def test_unknown_provider_refused(self) -> None:
        with self.assertRaises(robot_mod.RobotError):
            robot_mod.validate_config(
                robot_mod.RobotConfig(session="s", provider="wat", initial_prompt="go")
            )

    def test_empty_initial_prompt_is_attach_mode(self) -> None:
        config = robot_mod.validate_config(
            robot_mod.RobotConfig(session="s", initial_prompt="  ")
        )
        self.assertEqual(config.initial_prompt, "  ")

    def test_empty_continuation_refused(self) -> None:
        with self.assertRaises(robot_mod.RobotError):
            robot_mod.validate_config(
                robot_mod.RobotConfig(
                    session="s", initial_prompt="go", continuation_prompt=" "
                )
            )

    def test_bad_bounds_refused(self) -> None:
        base = {"session": "s", "initial_prompt": "go"}
        with self.assertRaises(robot_mod.RobotError):
            robot_mod.validate_config(robot_mod.RobotConfig(debounce_polls=0, **base))
        with self.assertRaises(robot_mod.RobotError):
            robot_mod.validate_config(
                robot_mod.RobotConfig(poll_interval_s=0.0, **base)
            )
        with self.assertRaises(robot_mod.RobotError):
            robot_mod.validate_config(robot_mod.RobotConfig(max_polls=-1, **base))


class SessionDiscoveryTest(unittest.TestCase):
    def test_lists_existing_sessions_sorted(self) -> None:
        driver = FakeDriver()
        driver.sessions["zeta"] = {"command": [], "output": "", "workdir": "/tmp"}
        driver.sessions["alpha"] = {"command": [], "output": "", "workdir": "/tmp"}
        self.assertEqual(robot_mod.list_sessions(driver), ["alpha", "zeta"])

    def test_unsupported_driver_reports(self) -> None:
        class NoList(terminal_mod.TerminalDriver):
            def create_or_connect(self, name, workdir, command):
                raise AssertionError("unused")

            def session_alive(self, name):
                raise AssertionError("unused")

            def send_input(self, name, text):
                raise AssertionError("unused")

            def interrupt(self, name):
                raise AssertionError("unused")

            def capture(self, name):
                raise AssertionError("unused")

            def attach_command(self, name):
                raise AssertionError("unused")

            def terminate(self, name):
                raise AssertionError("unused")

            def list_sessions(self):  # type: ignore[override]
                raise terminal_mod.TerminalError("cannot list")

        with self.assertRaises(robot_mod.RobotError):
            robot_mod.list_sessions(NoList())


class TerminalListTest(unittest.TestCase):
    def test_base_driver_reports_unsupported_listing(self) -> None:
        class Bare(terminal_mod.TerminalDriver):
            def create_or_connect(self, name, workdir, command):
                raise AssertionError("unused")

            def session_alive(self, name):
                raise AssertionError("unused")

            def send_input(self, name, text):
                raise AssertionError("unused")

            def interrupt(self, name):
                raise AssertionError("unused")

            def capture(self, name):
                raise AssertionError("unused")

            def attach_command(self, name):
                raise AssertionError("unused")

            def terminate(self, name):
                raise AssertionError("unused")

        with self.assertRaises(terminal_mod.TerminalError):
            Bare().list_sessions()
        with self.assertRaises(robot_mod.RobotError):
            robot_mod.list_sessions(Bare())

    def _tmux(self):
        return terminal_mod.TmuxDriver(executable="tmux")

    def test_tmux_lists_and_sorts_sessions(self) -> None:
        proc = unittest.mock.Mock()
        proc.returncode = 0
        proc.stdout = "zeta\nalpha\n"
        proc.stderr = ""
        with unittest.mock.patch("ariadex.terminal.subprocess.run", return_value=proc):
            self.assertEqual(self._tmux().list_sessions(), ["alpha", "zeta"])

    def test_tmux_without_server_lists_empty(self) -> None:
        proc = unittest.mock.Mock()
        proc.returncode = 1
        proc.stdout = ""
        proc.stderr = "no server running on /tmp/tmux-1000/default"
        with unittest.mock.patch("ariadex.terminal.subprocess.run", return_value=proc):
            self.assertEqual(self._tmux().list_sessions(), [])

    def test_tmux_error_refuses(self) -> None:
        proc = unittest.mock.Mock()
        proc.returncode = 1
        proc.stdout = ""
        proc.stderr = "weird failure"
        with (
            unittest.mock.patch("ariadex.terminal.subprocess.run", return_value=proc),
            self.assertRaises(terminal_mod.TerminalError),
        ):
            self._tmux().list_sessions()

    def test_tmux_missing_binary_reports(self) -> None:
        with (
            unittest.mock.patch(
                "ariadex.terminal.subprocess.run",
                side_effect=FileNotFoundError("tmux"),
            ),
            self.assertRaises(terminal_mod.TmuxNotAvailable),
        ):
            self._tmux().list_sessions()


class WatcherStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(self._close_tmp)

    def _close_tmp(self) -> None:
        for tmp in self._tmp:
            tmp.cleanup()

    def _ready(self, provider: str = "opencode") -> str:
        return {
            "opencode": READY_OPENCODE,
            "codex": READY_CODEX,
            "codebuddy": READY_CODEBUDDY,
        }[provider]

    def test_working_agent_is_left_alone(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": BUSY, "workdir": "/t"}
        watcher = make_watcher(project, driver, max_polls=3)
        report = watcher.run(sleep=lambda _: None)
        self.assertEqual(report.outcome, "max-polls")
        self.assertEqual(driver.sent_inputs("agent"), [])
        self.assertEqual(report.prompts_sent, 0)

    def test_debounce_requires_stable_polls(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": self._ready(),
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, debounce_polls=3)
        self.assertEqual(watcher.poll(), "finished-candidate")
        self.assertEqual(driver.sent_inputs("agent"), [])
        self.assertEqual(watcher.poll(), "finished-candidate")
        self.assertEqual(driver.sent_inputs("agent"), [])

    def test_unstable_signal_resets_debounce(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": self._ready(),
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, debounce_polls=2)
        self.assertEqual(watcher.poll(), "finished-candidate")
        driver.sessions["agent"]["output"] = BUSY
        self.assertEqual(watcher.poll(), "attached")
        self.assertEqual(driver.sent_inputs("agent"), [])

    def test_initial_prompt_sent_once_when_ready(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": self._ready(),
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, debounce_polls=1, max_polls=6)
        watcher.poll()
        self.assertEqual(driver.sent_inputs("agent"), ["please start"])
        self.assertTrue(watcher.initial_sent)
        # The echoed prompt keeps the surface ready; the boundary check
        # runs (git fails in the fixture) instead of resending.
        watcher.poll()
        self.assertEqual(driver.sent_inputs("agent"), ["please start"])

    def test_approval_waits_without_input(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": APPROVAL,
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, debounce_polls=1)
        self.assertEqual(watcher.poll(), robot_mod.WAITING)
        self.assertIn("approval", watcher.block_reason)
        self.assertEqual(driver.sent_inputs("agent"), [])

        driver.sessions["agent"]["output"] = BUSY
        self.assertEqual(watcher.poll(), "attached")
        self.assertEqual(driver.sent_inputs("agent"), [])

    def test_error_is_blocked_without_input(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": ERROR,
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, debounce_polls=1)
        self.assertEqual(watcher.poll(), "blocked")
        self.assertIn("error", watcher.block_reason)
        self.assertEqual(driver.sent_inputs("agent"), [])

    def test_pause_stops_input_and_keeps_session(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": self._ready(),
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, debounce_polls=1)
        watcher.request_pause()
        self.assertTrue(watcher.paused)
        self.assertEqual(watcher.poll(), "paused")
        self.assertEqual(driver.sent_inputs("agent"), [])
        self.assertIn("agent", driver.sessions)

    def test_quit_leaves_session_untouched(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": self._ready(),
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, debounce_polls=1)
        watcher.request_quit()
        report = watcher.run(sleep=lambda _: None)
        self.assertEqual(report.outcome, "stopped")
        self.assertEqual(driver.terminated(), [])
        self.assertIn("agent", driver.sessions)

    def test_status_view_reports_robot_state(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": "", "workdir": "/t"}
        watcher = make_watcher(project, driver)
        view = watcher.status_view()
        self.assertEqual(view["provider"], "opencode")
        self.assertEqual(view["session"], "agent")
        self.assertEqual(view["phase"], "attached")
        self.assertFalse(view["initial_sent"])

    def test_report_format_names_outcome(self) -> None:
        report = robot_mod.RobotReport(outcome="done", detail="all finished")
        self.assertIn("done", report.format())
        self.assertIn("prompts sent: 0", report.format())


class ContinuationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(self._close_tmp)

    def _close_tmp(self) -> None:
        for tmp in self._tmp:
            tmp.cleanup()

    def _ok_boundary(self, active: list[str]):
        def check(project_dir, config):
            return robot_mod.BoundaryCheck(ok=True, reason="", active=list(active))

        return check

    def test_verified_boundary_continues_opencode(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": READY_OPENCODE,
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, debounce_polls=1)
        real_check = robot_mod.check_boundary
        robot_mod.check_boundary = self._ok_boundary(["next-change"])  # type: ignore[assignment]
        try:
            watcher.poll()  # initial prompt
            self.assertEqual(watcher.poll(), "continuing")
        finally:
            robot_mod.check_boundary = real_check  # type: ignore[assignment]
        sent = driver.sent_inputs("agent")
        self.assertEqual(len(sent), 3)
        self.assertEqual(sent[0], "please start")
        self.assertEqual(sent[1], "/new")
        self.assertEqual(sent[2], robot_mod.DEFAULT_CONTINUATION_PROMPT)
        self.assertEqual(watcher.prompts_sent, 2)

    def test_custom_continuation_prompt_used(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": READY_OPENCODE,
            "workdir": "/t",
        }
        watcher = make_watcher(
            project, driver, debounce_polls=1, continuation_prompt="custom next"
        )
        real_check = robot_mod.check_boundary
        robot_mod.check_boundary = self._ok_boundary(["next-change"])  # type: ignore[assignment]
        try:
            watcher.poll()
            self.assertEqual(watcher.poll(), "continuing")
        finally:
            robot_mod.check_boundary = real_check  # type: ignore[assignment]
        self.assertEqual(driver.sent_inputs("agent")[-1], "custom next")

    def test_no_active_work_stops_without_prompt(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": READY_OPENCODE,
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, debounce_polls=1)
        real_check = robot_mod.check_boundary
        robot_mod.check_boundary = self._ok_boundary([])  # type: ignore[assignment]
        try:
            watcher.poll()  # initial prompt
            self.assertEqual(watcher.poll(), "done")
            report = watcher.run(sleep=lambda _: None)
        finally:
            robot_mod.check_boundary = real_check  # type: ignore[assignment]
        self.assertEqual(report.outcome, "done")
        self.assertEqual(driver.sent_inputs("agent"), ["please start"])

    def test_unfinished_work_blocks_with_reason(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": READY_OPENCODE,
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, debounce_polls=1)

        def blocked(project_dir, config):
            return robot_mod.BoundaryCheck(
                ok=False, reason="uncommitted changes present", active=["x"]
            )

        real_check = robot_mod.check_boundary
        robot_mod.check_boundary = blocked  # type: ignore[assignment]
        try:
            watcher.poll()
            self.assertEqual(watcher.poll(), "blocked")
            report = watcher.run(sleep=lambda _: None)
        finally:
            robot_mod.check_boundary = real_check  # type: ignore[assignment]
        self.assertEqual(report.outcome, "blocked")
        self.assertIn("uncommitted", report.detail)
        self.assertEqual(driver.sent_inputs("agent"), ["please start"])

    def test_codex_continues_via_automatic_restart(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": READY_CODEX,
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, provider="codex", debounce_polls=1)
        real_new = watcher.adapter.new_conversation

        def restarting() -> None:
            real_new()
            driver.sessions["agent"]["output"] = READY_CODEX

        watcher.adapter.new_conversation = restarting  # type: ignore[method-assign]
        real_check = robot_mod.check_boundary
        robot_mod.check_boundary = self._ok_boundary(["next-change"])  # type: ignore[assignment]
        try:
            watcher.poll()  # initial prompt
            self.assertEqual(watcher.poll(), "continuing")
        finally:
            robot_mod.check_boundary = real_check  # type: ignore[assignment]
        sent = driver.sent_inputs("agent")
        self.assertEqual(sent, ["please start", robot_mod.DEFAULT_CONTINUATION_PROMPT])
        ops = [op for op, *_ in driver.calls]
        self.assertIn("terminate", ops)
        self.assertIn("create_or_connect", ops)
        self.assertEqual(watcher.prompts_sent, 2)

    def test_codebuddy_continues_via_automatic_restart(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": READY_CODEBUDDY,
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, provider="codebuddy", debounce_polls=1)
        real_new = watcher.adapter.new_conversation

        def restarting() -> None:
            real_new()
            driver.sessions["agent"]["output"] = READY_CODEBUDDY

        watcher.adapter.new_conversation = restarting  # type: ignore[method-assign]
        real_check = robot_mod.check_boundary
        robot_mod.check_boundary = self._ok_boundary(["next-change"])  # type: ignore[assignment]
        try:
            self.assertEqual(watcher.poll(), "continuing")  # initial prompt
            self.assertEqual(watcher.poll(), "continuing")
        finally:
            robot_mod.check_boundary = real_check  # type: ignore[assignment]
        sent = driver.sent_inputs("agent")
        self.assertEqual(sent, ["please start", robot_mod.DEFAULT_CONTINUATION_PROMPT])
        ops = [op for op, *_ in driver.calls]
        self.assertIn("terminate", ops)
        self.assertIn("create_or_connect", ops)

    def test_unavailable_operation_blocks_as_capability(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": READY_OPENCODE,
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, debounce_polls=1)

        def unavailable() -> None:
            raise UnsupportedOperation("no automatic operation here")

        watcher.adapter.new_conversation = unavailable  # type: ignore[method-assign]
        real_check = robot_mod.check_boundary
        robot_mod.check_boundary = self._ok_boundary(["next-change"])  # type: ignore[assignment]
        try:
            watcher.poll()  # initial prompt
            self.assertEqual(watcher.poll(), "blocked")
        finally:
            robot_mod.check_boundary = real_check  # type: ignore[assignment]
        self.assertIn("opencode", watcher.block_reason)
        self.assertIn("unavailable", watcher.block_reason)
        self.assertNotIn("successful", watcher.block_reason)
        # Only the initial prompt was ever sent; the session is untouched.
        self.assertEqual(driver.sent_inputs("agent"), ["please start"])
        self.assertEqual(watcher.prompts_sent, 1)

    def test_failed_restart_blocks_with_provider_and_operation(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": READY_CODEX,
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, provider="codex", debounce_polls=1)

        def failing() -> None:
            raise RuntimeError("restart refused")

        watcher.adapter.new_conversation = failing  # type: ignore[method-assign]
        real_check = robot_mod.check_boundary
        robot_mod.check_boundary = self._ok_boundary(["next-change"])  # type: ignore[assignment]
        try:
            watcher.poll()  # initial prompt
            self.assertEqual(watcher.poll(), "blocked")
        finally:
            robot_mod.check_boundary = real_check  # type: ignore[assignment]
        self.assertIn("codex", watcher.block_reason)
        self.assertIn("new-conversation", watcher.block_reason)
        self.assertIn("no prompt was sent", watcher.block_reason)
        self.assertEqual(driver.sent_inputs("agent"), ["please start"])

    def test_watcher_stays_provider_neutral(self) -> None:
        import inspect

        source = inspect.getsource(robot_mod.RobotWatcher._open_continuation)
        for banned in ("/new", "new_session", "soft_reset", "terminate"):
            self.assertNotIn(banned, source)
        for provider_literal in ("'opencode'", "'codex'", "'codebuddy'"):
            self.assertNotIn(provider_literal, source)
        self.assertIn("new_conversation", source)

    def test_failed_new_session_blocks_without_prompt(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": READY_OPENCODE,
            "workdir": "/t",
        }
        driver.fail_delivery = True
        watcher = make_watcher(project, driver, debounce_polls=1)
        real_check = robot_mod.check_boundary
        robot_mod.check_boundary = self._ok_boundary(["next-change"])  # type: ignore[assignment]
        try:
            # Initial send fails delivery -> RobotError surfaces, no claim.
            with self.assertRaises(robot_mod.RobotError):
                watcher.poll()
        finally:
            robot_mod.check_boundary = real_check  # type: ignore[assignment]

    def test_new_surface_never_ready_blocks(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {
            "command": [],
            "output": READY_OPENCODE,
            "workdir": "/t",
        }
        watcher = make_watcher(project, driver, debounce_polls=1)
        real_check = robot_mod.check_boundary
        robot_mod.check_boundary = self._ok_boundary(["next-change"])  # type: ignore[assignment]
        captures = [READY_OPENCODE, READY_OPENCODE, "blank screen"]
        with unittest.mock.patch.object(watcher, "_capture", side_effect=captures):
            try:
                watcher.poll()  # initial prompt sent
                self.assertEqual(watcher.poll(), "blocked")
            finally:
                robot_mod.check_boundary = real_check  # type: ignore[assignment]
        self.assertIn("never reported an input-ready surface", watcher.block_reason)


class BoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(self._close_tmp)

    def _close_tmp(self) -> None:
        for tmp in self._tmp:
            tmp.cleanup()

    def _config(self, **overrides) -> robot_mod.RobotConfig:
        params = {
            "session": "agent",
            "provider": "opencode",
            "initial_prompt": "go",
        }
        params.update(overrides)
        return robot_mod.RobotConfig(**params)

    def test_missing_handoff_blocks(self) -> None:
        project = make_project(self._tmp)
        (project / ".ariadex" / "handoff.md").unlink()
        check = robot_mod.check_boundary(project, self._config())
        self.assertFalse(check.ok)
        self.assertIn("handoff", check.reason)

    def test_malformed_spec_metadata_blocks(self) -> None:
        project = make_project(self._tmp)
        change = project / "openspec" / "changes" / "broken"
        change.mkdir(parents=True)
        (change / ".openspec.yaml").write_text(
            "depends_on: not-a-list\n", encoding="utf-8"
        )
        check = robot_mod.check_boundary(project, self._config())
        self.assertFalse(check.ok)
        self.assertIn("broken", check.reason)

    def test_open_tasks_block(self) -> None:
        project = make_project(self._tmp)
        change = project / "openspec" / "changes" / "demo"
        change.mkdir(parents=True)
        (change / "tasks.md").write_text(
            "# Tasks\n\n- [x] Done\n- [ ] Open\n", encoding="utf-8"
        )
        check = robot_mod.check_boundary(project, self._config(finished_change="demo"))
        self.assertFalse(check.ok)
        self.assertIn("open task", check.reason)

    def test_missing_tasks_file_blocks(self) -> None:
        project = make_project(self._tmp)
        (project / "openspec" / "changes" / "demo").mkdir(parents=True)
        check = robot_mod.check_boundary(project, self._config(finished_change="demo"))
        self.assertFalse(check.ok)
        self.assertIn("tasks.md", check.reason)

    def test_archived_change_has_no_open_tasks(self) -> None:
        project = make_project(self._tmp)
        done, reason = robot_mod._tasks_complete(project, "openspec/changes", "gone")
        self.assertTrue(done)
        self.assertEqual(reason, "")

    def test_completed_tasks_pass_to_git_gate(self) -> None:
        project = make_project(self._tmp)
        change = project / "openspec" / "changes" / "demo"
        change.mkdir(parents=True)
        (change / "tasks.md").write_text("# Tasks\n\n- [x] Done\n", encoding="utf-8")
        # The fixture is not a git checkout, so the git gate blocks next.
        check = robot_mod.check_boundary(project, self._config(finished_change="demo"))
        self.assertFalse(check.ok)
        self.assertTrue(
            "git" in check.reason or "uncommitted" in check.reason,
            check.reason,
        )

    def test_handoff_current_spec_is_checked_without_override(self) -> None:
        project = make_project(self._tmp)
        change = project / "openspec" / "changes" / "demo"
        change.mkdir(parents=True)
        (change / "tasks.md").write_text(
            "# Tasks\n\n- [x] Implemented\n", encoding="utf-8"
        )
        handoff = handoff_mod.read_handoff(project / ".ariadex" / "handoff.md")
        handoff.current_spec = "demo"
        handoff_mod.write_handoff(project / ".ariadex" / "handoff.md", handoff)

        with unittest.mock.patch.object(
            robot_mod, "_git_tree_clean", return_value=(True, "")
        ):
            check = robot_mod.check_boundary(project, self._config())

        self.assertTrue(check.ok, check.reason)
        self.assertEqual(check.active, ["demo"])

    def test_handoff_current_spec_open_tasks_block_without_override(self) -> None:
        project = make_project(self._tmp)
        change = project / "openspec" / "changes" / "demo"
        change.mkdir(parents=True)
        (change / "tasks.md").write_text(
            "# Tasks\n\n- [x] Implemented\n- [ ] Still running\n",
            encoding="utf-8",
        )
        handoff = handoff_mod.read_handoff(project / ".ariadex" / "handoff.md")
        handoff.current_spec = "demo"
        handoff_mod.write_handoff(project / ".ariadex" / "handoff.md", handoff)

        check = robot_mod.check_boundary(project, self._config())

        self.assertFalse(check.ok)
        self.assertIn("1 open task", check.reason)

    def test_git_gate_refuses_outside_a_repo(self) -> None:
        project = make_project(self._tmp)
        clean, reason = robot_mod._git_tree_clean(project)
        self.assertFalse(clean)
        self.assertTrue(reason)


class ProviderBoundaryTest(unittest.TestCase):
    def test_codebuddy_adapter_contract(self) -> None:
        driver = terminal_mod.FakeTerminalDriver()
        adapter = providers_mod.get_adapter("codebuddy", driver, "s", "/tmp")
        self.assertEqual(adapter.provider_name, "codebuddy")
        self.assertFalse(adapter.capabilities.soft_reset)
        with self.assertRaises(UnsupportedOperation):
            adapter.new_session()

    def test_robot_providers_are_registered(self) -> None:
        for provider in robot_mod.SUPPORTED_ROBOT_PROVIDERS:
            with self.subTest(provider=provider):
                adapter = providers_mod.get_adapter(
                    provider, terminal_mod.FakeTerminalDriver(), "s", "/tmp"
                )
                self.assertEqual(adapter.provider_name, provider)


class FakeTkWidget:
    def __init__(self, master=None, **options):
        self.options = dict(options)
        self.packed = False
        self.command = options.get("command")

    def pack(self, **kwargs):
        self.packed = True

    def configure(self, **options):
        self.options.update(options)

    config = configure

    def invoke(self):
        if self.command is not None:
            self.command()


class FakeTkRoot(FakeTkWidget):
    def __init__(self):
        super().__init__(None)
        self.after_calls: list = []
        self.destroyed = False
        self._seq = 0

    def title(self, text):
        self.options["title"] = text

    def overrideredirect(self, flag):
        pass

    def attributes(self, *args):
        pass

    def geometry(self, spec):
        self.options["geometry"] = spec

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    def after(self, ms, func=None):
        self._seq += 1
        token = f"after{self._seq}"
        if func is not None:
            self.after_calls.append((ms, func))
        return token

    def after_cancel(self, token):
        pass

    def destroy(self):
        self.destroyed = True


def install_fake_tk(test: unittest.TestCase):
    tk_mod = types.ModuleType("tkinter")
    tk_mod.Tk = FakeTkRoot  # type: ignore[attr-defined]
    tk_mod.Frame = FakeTkWidget  # type: ignore[attr-defined]
    tk_mod.Label = FakeTkWidget  # type: ignore[attr-defined]
    tk_mod.Button = FakeTkWidget  # type: ignore[attr-defined]
    saved = sys.modules.get("tkinter")
    sys.modules["tkinter"] = tk_mod

    def restore():
        if saved is None:
            sys.modules.pop("tkinter", None)
        else:
            sys.modules["tkinter"] = saved

    test.addCleanup(restore)


class RobotWidgetTest(unittest.TestCase):
    def setUp(self) -> None:
        install_fake_tk(self)

    def test_view_model_matrix(self) -> None:
        from ariadex import companion as companion_mod

        cases = {
            "attached": "watching",
            "working": "working",
            "continuing": "working",
            "new-conversation": "working",
            "finished-candidate": "working",
            "verified-boundary": "working",
            "paused": "paused",
            "blocked": "blocked",
            "done": "completed",
            "stopped": "stopped",
        }
        for phase, indicator in cases.items():
            with self.subTest(phase=phase):
                model = companion_mod.build_robot_view_model(
                    {"phase": phase, "provider": "opencode", "session": "agent"}
                )
                self.assertEqual(model["indicator"], indicator)
                self.assertIn("opencode @ agent", model["work_label"])

    def test_pause_gated_by_phase(self) -> None:
        from ariadex import companion as companion_mod

        watching = companion_mod.build_robot_view_model({"phase": "attached"})
        self.assertTrue(watching["actions"]["pause"])
        self.assertTrue(watching["actions"]["quit"])
        stopped = companion_mod.build_robot_view_model({"phase": "stopped"})
        self.assertFalse(stopped["actions"]["pause"])
        self.assertFalse(stopped["actions"]["quit"])

    def test_blocked_reason_is_visible(self) -> None:
        from ariadex import companion as companion_mod

        model = companion_mod.build_robot_view_model(
            {"phase": "blocked", "block_reason": "answer approval"}
        )
        self.assertIn("answer approval", model["work_label"])
        text = companion_mod.format_robot_text(model)
        self.assertIn("BLOCKED", text)
        self.assertIn("answer approval", text)

    def test_robot_window_stays_middle_right_with_pause_quit(self) -> None:
        from ariadex import companion as companion_mod

        calls: list[str] = []
        status = {"phase": "working", "provider": "codex", "session": "agent"}

        def status_fn():
            return dict(status)

        window = companion_mod.RobotWindow(
            FakeTkRoot(),
            status_fn,
            on_pause=lambda: calls.append("pause") or "paused",
            on_quit=lambda: calls.append("quit") or "stopped",
        )
        self.assertEqual(window.state_label.options["text"], "WORKING")
        self.assertIn("+", window.root.options["geometry"])
        window.pause_button.invoke()
        self.assertEqual(calls, ["pause"])
        window.quit_button.invoke()
        self.assertEqual(calls, ["pause", "quit"])
        self.assertTrue(window.root.destroyed)

    def test_robot_window_reports_poll_failure(self) -> None:
        from ariadex import companion as companion_mod

        def failing():
            raise RuntimeError("no watcher")

        window = companion_mod.RobotWindow(
            FakeTkRoot(),
            failing,
            on_pause=lambda: "paused",
            on_quit=lambda: "stopped",
        )
        self.assertEqual(window.state_label.options["text"], "UNREACHABLE")


class WatchCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(self._close_tmp)
        from ariadex import cli as cli_mod

        self.cli = cli_mod
        self.driver = FakeDriver()
        patcher = unittest.mock.patch.object(
            cli_mod.terminal_mod, "TmuxDriver", lambda executable="tmux": self.driver
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        setup_patcher = unittest.mock.patch.object(
            cli_mod.tmux_setup_mod, "ensure_tmux", return_value="tmux"
        )
        setup_patcher.start()
        self.addCleanup(setup_patcher.stop)

    def _close_tmp(self) -> None:
        for tmp in self._tmp:
            tmp.cleanup()

    def _project(self) -> Path:
        return make_project(self._tmp)

    def test_list_sessions_reports_without_watching(self) -> None:
        import io
        from contextlib import redirect_stdout

        self.driver.sessions["one"] = {"command": [], "output": "", "workdir": "/t"}
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = self.cli.cmd_watch(self._project(), list_sessions=True)
        self.assertEqual(code, 0)
        self.assertIn("session: one", buf.getvalue())

    def test_missing_session_selection_refused(self) -> None:
        code = self.cli.cmd_watch(
            self._project(), session=None, initial_prompt="go", provider="opencode"
        )
        self.assertEqual(code, 1)

    def test_missing_session_never_created_implicitly(self) -> None:
        code = self.cli.cmd_watch(
            self._project(),
            session="ghost",
            initial_prompt="go",
            provider="opencode",
        )
        self.assertEqual(code, 1)
        self.assertNotIn("ghost", self.driver.sessions)

    def test_explicit_create_fallback_starts_session(self) -> None:
        code = self.cli.cmd_watch(
            self._project(),
            session="fresh",
            initial_prompt="go",
            provider="opencode",
            create=True,
            max_polls=2,
            poll_interval=0.01,
        )
        self.assertEqual(code, 1)  # budget spent, nothing claimed
        self.assertIn("fresh", self.driver.sessions)

    def test_unsupported_provider_refused(self) -> None:
        code = self.cli.cmd_watch(
            self._project(),
            session="agent",
            initial_prompt="go",
            provider="wat",
        )
        self.assertEqual(code, 1)

    def test_missing_initial_prompt_refused(self) -> None:
        code = self.cli.cmd_watch(self._project(), session="agent", provider="opencode")
        self.assertEqual(code, 1)

    def test_done_run_exits_zero_with_one_prompt(self) -> None:
        import io
        from contextlib import redirect_stdout

        self.driver.sessions["agent"] = {
            "command": [],
            "output": READY_OPENCODE,
            "workdir": "/t",
        }
        real_check = robot_mod.check_boundary
        robot_mod.check_boundary = (  # type: ignore[assignment]
            lambda project_dir, config: robot_mod.BoundaryCheck(
                ok=True, reason="", active=[]
            )
        )
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = self.cli.cmd_watch(
                    self._project(),
                    session="agent",
                    initial_prompt="go",
                    provider="opencode",
                    debounce=1,
                    poll_interval=0.01,
                    max_polls=10,
                )
        finally:
            robot_mod.check_boundary = real_check  # type: ignore[assignment]
        self.assertEqual(code, 0)
        self.assertIn("robot done", buf.getvalue())
        self.assertEqual(self.driver.sent_inputs("agent"), ["go"])

    def test_blocked_run_reports_and_exits_nonzero(self) -> None:
        import io
        from contextlib import redirect_stdout

        self.driver.sessions["agent"] = {
            "command": [],
            "output": READY_OPENCODE,
            "workdir": "/t",
        }
        real_check = robot_mod.check_boundary
        robot_mod.check_boundary = (  # type: ignore[assignment]
            lambda project_dir, config: robot_mod.BoundaryCheck(
                ok=False, reason="uncommitted changes present", active=["x"]
            )
        )
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = self.cli.cmd_watch(
                    self._project(),
                    session="agent",
                    initial_prompt="go",
                    provider="opencode",
                    debounce=1,
                    poll_interval=0.01,
                )
        finally:
            robot_mod.check_boundary = real_check  # type: ignore[assignment]
        self.assertEqual(code, 1)
        self.assertIn("robot blocked", buf.getvalue())
        self.assertIn("uncommitted", buf.getvalue())

    def test_tmux_setup_failure_refused(self) -> None:
        from ariadex import tmux_setup as tmux_setup_mod

        with unittest.mock.patch.object(
            self.cli.tmux_setup_mod,
            "ensure_tmux",
            side_effect=tmux_setup_mod.TmuxSetupError("no tmux"),
        ):
            code = self.cli.cmd_watch(
                self._project(),
                session="agent",
                initial_prompt="go",
                provider="opencode",
            )
        self.assertEqual(code, 1)

    def test_session_probe_failure_refused(self) -> None:
        self.driver.missing_binary = True
        code = self.cli.cmd_watch(
            self._project(),
            session="agent",
            initial_prompt="go",
            provider="opencode",
        )
        self.assertEqual(code, 1)

    def test_adapter_build_failure_refused(self) -> None:
        from ariadex.adapters import AdapterError

        with unittest.mock.patch.object(
            self.cli.providers_mod,
            "get_adapter",
            side_effect=AdapterError("nope"),
        ):
            code = self.cli.cmd_watch(
                self._project(),
                session="agent",
                initial_prompt="go",
                provider="opencode",
            )
        self.assertEqual(code, 1)

    def test_explicit_create_failure_refused(self) -> None:
        self.driver.missing_binary = True
        code = self.cli.cmd_watch(
            self._project(),
            session="ghost",
            initial_prompt="go",
            provider="opencode",
            create=True,
        )
        self.assertEqual(code, 1)
        self.assertNotIn("ghost", self.driver.sessions)

    def test_invalid_debounce_refused(self) -> None:
        self.driver.sessions["agent"] = {
            "command": [],
            "output": "",
            "workdir": "/t",
        }
        code = self.cli.cmd_watch(
            self._project(),
            session="agent",
            initial_prompt="go",
            provider="opencode",
            debounce=0,
        )
        self.assertEqual(code, 1)

    def test_no_provider_without_config_refused(self) -> None:
        self.driver.sessions["agent"] = {
            "command": [],
            "output": "",
            "workdir": "/t",
        }
        code = self.cli.cmd_watch(self._project(), session="agent", initial_prompt="go")
        self.assertEqual(code, 1)

    def test_keyboard_interrupt_quits_cleanly(self) -> None:
        import io
        from contextlib import redirect_stdout

        self.driver.sessions["agent"] = {
            "command": [],
            "output": "",
            "workdir": "/t",
        }

        class Interrupted:
            def __init__(self, *args, **kwargs):
                pass

            def run(self):
                raise KeyboardInterrupt

            def request_quit(self):
                return "stopped: watcher exited"

        with unittest.mock.patch.object(robot_mod, "RobotWatcher", Interrupted):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = self.cli.cmd_watch(
                    self._project(),
                    session="agent",
                    initial_prompt="go",
                    provider="opencode",
                )
        self.assertEqual(code, 0)
        self.assertIn("stopped", buf.getvalue())

    def test_watch_dispatch_via_main(self) -> None:
        import io
        from contextlib import redirect_stdout

        project = self._project()
        self.driver.sessions["one"] = {"command": [], "output": "", "workdir": "/t"}
        with unittest.mock.patch.object(self.cli, "_project_dir", return_value=project):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = self.cli.main(["watch", "--list-sessions"])
        self.assertEqual(code, 0)
        self.assertIn("session: one", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
