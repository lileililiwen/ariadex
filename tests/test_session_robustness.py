"""Session-loss survival and single live-owner guard.

Transport loss (dead tmux session, failed capture/send) parks the
watcher in WAITING with an `unexpected-provider-exit` diagnostic and
sends no input — it never escapes as an exception and never kills the
watcher thread. Managed `start` refuses a second live owner for the
same project directory; stale records keep today's recovery path.
"""

import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

from ariadex import cli as cli_mod
from ariadex import daemon as daemon_mod
from ariadex import diagnostics as diagnostics_mod
from ariadex import handoff as handoff_mod
from ariadex import managed_runtime as managed_runtime_mod
from ariadex import providers as providers_mod
from ariadex import robot as robot_mod
from ariadex import terminal as terminal_mod
from ariadex.adapters import TransportError

try:
    import evidence_fakes
except ModuleNotFoundError:
    from tests import evidence_fakes  # type: ignore[no-redef]

READY = "Welcome back\nAsk anything \u00b7 tab agents\n> "


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
        "fresh_ready_attempts": 3,
        "fresh_ready_interval_s": 0,
    }
    params.update(overrides)
    return robot_mod.RobotWatcher(
        project,
        robot_mod.RobotConfig(**params),
        driver,
        adapter,
        evidence_runner=evidence_fakes.make_runner(project),
    )


class SessionLossPollTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def test_session_vanishes_mid_poll_waits_without_input(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        with unittest.mock.patch.object(
            watcher.driver,
            "capture",
            side_effect=terminal_mod.SessionMissing("gone"),
        ):
            phase = watcher.poll()
        self.assertEqual(phase, "waiting")
        self.assertEqual(watcher.phase, "waiting")
        self.assertIn("waiting", watcher.block_reason)
        self.assertIn("no input sent", watcher.block_reason)
        self.assertEqual(driver.sent_inputs("agent"), [])

    def test_capture_failure_records_unexpected_exit_diagnostic(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        with unittest.mock.patch.object(
            watcher.driver,
            "capture",
            side_effect=terminal_mod.TerminalError("pane unreadable"),
        ):
            watcher.poll()
        records, _ = diagnostics_mod.read_diagnostics(project)
        exits = [r for r in records if r["action"] == "unexpected-provider-exit"]
        self.assertTrue(exits, "expected an unexpected-provider-exit diagnostic")
        self.assertEqual(exits[-1]["result"], "waiting")

    def test_send_transport_failure_maps_to_transport_loss(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        with (
            unittest.mock.patch.object(
                watcher.adapter, "send", side_effect=TransportError("lost")
            ),
            self.assertRaises(robot_mod.TransportLoss),
        ):
            watcher._send("hello")
        # TransportLoss stays a RobotError so approval paths keep waiting.
        self.assertTrue(issubclass(robot_mod.TransportLoss, robot_mod.RobotError))

    def test_await_ready_propagates_transport_loss(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        with (
            unittest.mock.patch.object(
                watcher, "_capture", side_effect=robot_mod.TransportLoss("gone")
            ),
            self.assertRaises(robot_mod.TransportLoss),
        ):
            watcher._await_ready()

    def test_run_survives_transport_loss_within_budget(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver, max_polls=1)
        with unittest.mock.patch.object(
            watcher.driver,
            "capture",
            side_effect=terminal_mod.SessionMissing("gone"),
        ):
            report = watcher.run(sleep=lambda _: None)
        self.assertEqual(watcher.phase, "waiting")
        self.assertEqual(driver.sent_inputs("agent"), [])
        self.assertIsNotNone(report)


class RunWatcherCatchAllTest(unittest.TestCase):
    def test_run_exception_records_diagnostic_and_preserves_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            boom = RuntimeError("watcher blew up")

            class ExplodingWatcher:
                prompts_sent = 0

                def run(self):
                    raise boom

            runtime = managed_runtime_mod.ManagedRuntime(root)
            runtime.watcher = ExplodingWatcher()
            runtime._run_watcher()
            self.assertIsNotNone(runtime.outcome)
            self.assertEqual(getattr(runtime.outcome, "outcome", ""), "crashed")
            records, _ = diagnostics_mod.read_diagnostics(root)
            exits = [r for r in records if r["action"] == "unexpected-provider-exit"]
            self.assertEqual(len(exits), 1)
            self.assertIn("watcher blew up", str(exits[0]["details"]))

    def test_run_success_without_provider_loss_records_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            class CalmWatcher:
                def run(self):
                    return SimpleNamespace(outcome="stopped")

            class LiveDriver:
                def session_alive(self, _name):
                    return True

            runtime = managed_runtime_mod.ManagedRuntime(root)
            runtime.watcher = CalmWatcher()
            runtime.adapter = SimpleNamespace(
                provider_name="opencode",
                session_name="s",
                driver=LiveDriver(),
            )
            runtime._run_watcher()
            self.assertEqual(runtime.outcome.outcome, "stopped")
            records, _ = diagnostics_mod.read_diagnostics(root)
            exits = [r for r in records if r["action"] == "unexpected-provider-exit"]
            self.assertEqual(exits, [])


def write_daemon_record(project: Path, pid: int, status: str = "running") -> None:
    record = daemon_mod.DaemonRecord(
        version=daemon_mod.DAEMON_VERSION,
        pid=pid,
        started_at="2026-09-15T00:00:00+00:00",
        endpoint=str(daemon_mod.SOCKET_REL_PATH),
        status=status,
        session_id="s",
    )
    daemon_mod.write_record(project, record)


class SingleOwnerGuardTest(unittest.TestCase):
    def test_live_owner_refuses_with_attach_and_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_daemon_record(root, os.getpid())
            with unittest.mock.patch.object(
                cli_mod, "_daemon_ipc_or_none", return_value=None
            ):
                self.assertTrue(cli_mod._live_owner(root, False))
            with (
                unittest.mock.patch.object(
                    cli_mod, "_daemon_ipc_or_none", return_value=None
                ),
                unittest.mock.patch("builtins.print") as printed,
            ):
                cli_mod._report_live_owner(root, daemon_mod.read_record(root), False)
            text = " ".join(str(call.args[0]) for call in printed.call_args_list)
            self.assertIn("attach", text)
            self.assertIn("--project", text)

    def test_start_daemon_only_refuses_live_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_daemon_record(root, os.getpid())
            with unittest.mock.patch("builtins.print"):
                rc = cli_mod._start_daemon_only(root)
            self.assertEqual(rc, cli_mod.EXIT_ERROR)

    def test_stale_record_keeps_recovery_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_daemon_record(root, 999999999)
            record = daemon_mod.read_record(root)
            self.assertIsNotNone(record)
            self.assertFalse(daemon_mod.daemon_alive(record))
            with unittest.mock.patch.object(
                cli_mod, "_daemon_ipc_or_none", return_value=None
            ):
                self.assertFalse(cli_mod._live_owner(root, False))


if __name__ == "__main__":
    unittest.main()
