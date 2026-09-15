"""Bounded fresh-ready retry for new conversations.

After `adapter.new_conversation()`, the watcher must tolerate a transient
post-reset settle gap (composer render plus session-status transition) by
retrying the fresh input-ready surface within a bound, instead of blocking
on the first rapid check. The fail-closed rule stays: no prompt without a
verified ready surface, and the wait aborts on quit/shutdown/PAUSE.
"""

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from ariadex import handoff as handoff_mod
from ariadex import providers as providers_mod
from ariadex import robot as robot_mod
from ariadex import terminal as terminal_mod

try:
    import evidence_fakes
except ModuleNotFoundError:
    from tests import evidence_fakes  # type: ignore[no-redef]

READY = "Welcome back\nAsk anything · tab agents\n> "
BLANK = "blank screen, session resetting\n"


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


def make_change(root: Path, name: str) -> None:
    change = root / "openspec" / "changes" / name
    change.mkdir(parents=True, exist_ok=True)
    (change / "tasks.md").write_text("# Tasks\n\n- [ ] Open\n", encoding="utf-8")
    handoff = handoff_mod.read_handoff(root / "HANDOFF.md")
    handoff.current_spec = name
    handoff_mod.write_handoff(root / "HANDOFF.md", handoff)


def make_watcher(project: Path, driver: FakeDriver, **overrides):
    adapter = providers_mod.get_adapter("opencode", driver, "agent", project)
    params = {
        "session": "agent",
        "provider": "opencode",
        "initial_prompt": "please start",
        "continuation_prompt": "please continue",
        "confirmation_prompt": "please finish the rest",
        "debounce_polls": 1,
        "poll_interval_s": 0.01,
        "fresh_ready_attempts": 5,
        "fresh_ready_interval_s": 0,
    }
    params.update(overrides)
    shutdown_requested = params.pop("shutdown_requested", None)
    mode_requested = params.pop("mode_requested", None)
    return robot_mod.RobotWatcher(
        project,
        robot_mod.RobotConfig(**params),
        driver,
        adapter,
        shutdown_requested=shutdown_requested,
        mode_requested=mode_requested,
        evidence_runner=evidence_fakes.make_runner(project),
    )


def clean_git():
    return unittest.mock.patch.object(
        robot_mod, "_git_tree_clean", return_value=(True, "")
    )


class FreshReadyRetryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def test_delayed_ready_sends_confirmation_once(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo")
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        # Fresh-wait mechanics under test, not the readiness ask:
        # pre-arm its once-per-boundary guard.
        watcher._readiness_asked = ("demo", 1)
        with (
            clean_git(),
            unittest.mock.patch.object(
                watcher, "_capture", side_effect=[READY, BLANK, BLANK, READY]
            ),
            unittest.mock.patch.object(watcher.adapter, "new_conversation"),
        ):
            self.assertEqual(watcher.poll(), "continuing")
        self.assertEqual(driver.sent_inputs("agent"), ["please finish the rest"])
        self.assertEqual(watcher.confirmations_sent, 1)
        # One capture serves the draft/pause guard; the wait needs two more.
        self.assertEqual(watcher.last_fresh_ready_attempts, 2)
        messages = [event["message"] for event in watcher.activity_events]
        self.assertTrue(
            any("observed after 2 attempt(s)" in message for message in messages),
            messages,
        )

    def test_exhausted_bound_refires_without_prompt(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo")
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver, fresh_ready_attempts=3)
        watcher.initial_sent = True
        # Fresh-wait mechanics under test, not the readiness ask:
        # pre-arm its once-per-boundary guard.
        watcher._readiness_asked = ("demo", 1)
        with (
            clean_git(),
            unittest.mock.patch.object(
                watcher,
                "_capture",
                side_effect=[READY, BLANK, BLANK, BLANK, BLANK],
            ),
            unittest.mock.patch.object(watcher.adapter, "new_conversation"),
        ):
            self.assertEqual(watcher.poll(), "working")
        self.assertEqual(watcher.block_reason, "")
        self.assertEqual(watcher.confirmations_sent, 0)
        self.assertNotIn("please finish the rest", driver.sent_inputs("agent"))
        self.assertEqual(watcher.last_fresh_ready_attempts, 3)
        messages = [event["message"] for event in watcher.activity_events]
        self.assertTrue(
            any("re-observing the open boundary" in message for message in messages),
            messages,
        )

    def test_repeated_exhaustion_parks_visibly(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo")
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver, fresh_ready_attempts=2)
        watcher.initial_sent = True
        # Fresh-wait mechanics under test, not the readiness ask:
        # pre-arm its once-per-boundary guard.
        watcher._readiness_asked = ("demo", 1)
        # Three boundary cycles: READY reaches the boundary, BLANKs exhaust
        # the short wait. The third exhaustion parks instead of refiring.
        # Each cycle consumes poll + guard + two attempts.
        script = [READY, READY, BLANK, BLANK] * 3
        with (
            clean_git(),
            unittest.mock.patch.object(watcher, "_capture", side_effect=script),
            unittest.mock.patch.object(watcher.adapter, "new_conversation"),
        ):
            self.assertEqual(watcher.poll(), "working")
            driver.sessions["agent"]["output"] = READY
            self.assertEqual(watcher.poll(), "working")
            driver.sessions["agent"]["output"] = READY
            self.assertEqual(watcher.poll(), "waiting")
        self.assertIn("input-ready surface", watcher.block_reason)
        self.assertEqual(watcher.confirmations_sent, 0)
        self.assertNotIn("please finish the rest", driver.sent_inputs("agent"))

    def test_debounce_requires_consecutive_ready_across_retries(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo")
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver, debounce_polls=2)
        watcher.initial_sent = True
        # Fresh-wait mechanics under test, not the readiness ask:
        # pre-arm its once-per-boundary guard.
        watcher._readiness_asked = ("demo", 1)
        with (
            clean_git(),
            unittest.mock.patch.object(
                watcher,
                "_capture",
                side_effect=[READY, READY, BLANK, READY, READY],
            ),
            unittest.mock.patch.object(watcher.adapter, "new_conversation"),
        ):
            self.assertEqual(watcher.poll(), "finished-candidate")
            self.assertEqual(watcher.poll(), "continuing")
        self.assertEqual(watcher.confirmations_sent, 1)
        # Guard capture plus two debounced ready reads.
        self.assertEqual(watcher.last_fresh_ready_attempts, 2)

    def test_pause_parks_fresh_wait_for_resume(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo")
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        modes = iter(["AUTO", "AUTO", "PAUSE"])
        watcher = make_watcher(project, driver, mode_requested=lambda: next(modes))
        watcher.initial_sent = True
        # Fresh-wait mechanics under test, not the readiness ask:
        # pre-arm its once-per-boundary guard.
        watcher._readiness_asked = ("demo", 1)
        with (
            clean_git(),
            unittest.mock.patch.object(
                watcher, "_capture", side_effect=[READY, BLANK, READY]
            ),
            unittest.mock.patch.object(watcher.adapter, "new_conversation"),
        ):
            self.assertEqual(watcher.poll(), "paused")
        self.assertEqual(watcher.confirmations_sent, 0)
        self.assertNotIn("please finish the rest", driver.sent_inputs("agent"))

    def test_shutdown_aborts_fresh_wait_before_any_capture(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo")
        driver = FakeDriver()
        watcher = make_watcher(project, driver, shutdown_requested=lambda: True)
        with unittest.mock.patch.object(
            watcher, "_capture", side_effect=AssertionError("must not capture")
        ):
            self.assertIsNone(watcher._await_ready(sleep=lambda _: None))
        self.assertEqual(watcher.last_fresh_ready_attempts, 0)

    def test_sleep_runs_between_attempts(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo")
        driver = FakeDriver()
        watcher = make_watcher(
            project,
            driver,
            fresh_ready_attempts=3,
            fresh_ready_interval_s=7,
        )
        sleeps: list = []
        with unittest.mock.patch.object(watcher, "_capture", return_value=BLANK):
            self.assertFalse(watcher._await_ready(sleep=sleeps.append))
        self.assertEqual(sleeps, [7, 7])
        self.assertEqual(watcher.last_fresh_ready_attempts, 3)

    def test_invalid_fresh_config_rejected(self) -> None:
        with self.assertRaises(robot_mod.RobotError):
            robot_mod.validate_config(
                robot_mod.RobotConfig(session="s", fresh_ready_attempts=0)
            )
        with self.assertRaises(robot_mod.RobotError):
            robot_mod.validate_config(
                robot_mod.RobotConfig(session="s", fresh_ready_interval_s=-1)
            )

    def test_fresh_defaults_are_bounded_and_positive(self) -> None:
        config = robot_mod.RobotConfig(session="s")
        self.assertGreaterEqual(config.fresh_ready_attempts, 1)
        self.assertGreater(config.fresh_ready_interval_s, 0)


if __name__ == "__main__":
    unittest.main()
