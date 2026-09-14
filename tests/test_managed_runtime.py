"""Tests for daemon-owned managed runtime lifecycle."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ariadex import cli, diagnostics, managed_runtime, prerequisites


class FakeAdapter:
    def __init__(self, events):
        self.events = events

    def start(self):
        self.events.append("provider-start")

    def terminate(self):
        self.events.append("provider-stop")


class DeadDriver:
    def session_alive(self, _name):
        return False


class DeadAdapter(FakeAdapter):
    provider_name = "opencode"
    session_name = "ariadex-test"
    driver = DeadDriver()

    def capture_output(self):
        return "final pane output"


class FakeWatcher:
    def __init__(self, events):
        self.events = events
        self.quit_requested = False

    def run(self):
        self.events.append("watcher-run")
        return SimpleNamespace(outcome="stopped")

    def request_quit(self):
        self.quit_requested = True
        self.events.append("watcher-stop")


class FakeWidget:
    pid = 123

    def stop(self):
        self.events.append("widget-stop")


class ManagedRuntimeTest(unittest.TestCase):
    def test_generation_record_preserves_operator_shutdown(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = managed_runtime.ManagedGeneration(
                generation="g1",
                project=str(root),
                daemon_pid=10,
                provider_pid=11,
                widget_pid=12,
                status="running",
            )
            managed_runtime.write_generation(root, record)
            managed_runtime.mark_generation_stopped(root, "operator")

            loaded = managed_runtime.read_generation(root)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.status, "stopped")
            self.assertEqual(loaded.shutdown_reason, "operator")

    def test_start_command_only_ensures_daemon(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(cli.cmd_init(root), cli.EXIT_OK)
            report = prerequisites.CoordinatorReport(results=[], ready=True)
            with (
                mock.patch.object(
                    cli.prerequisites_mod, "coordinate", return_value=report
                ),
                mock.patch.object(cli, "_start_daemon_only", return_value=cli.EXIT_OK),
                mock.patch.object(cli, "_has_terminal", return_value=False),
                mock.patch.object(cli.providers_mod, "get_adapter") as adapter,
                mock.patch.object(cli.robot_mod, "RobotWatcher") as watcher,
            ):
                self.assertEqual(cli.cmd_start(root), cli.EXIT_OK)
            adapter.assert_not_called()
            watcher.assert_not_called()

    def test_start_owns_provider_watcher_and_widget_once(self):
        events = []
        with tempfile.TemporaryDirectory() as temp:
            runtime = managed_runtime.ManagedRuntime(
                Path(temp),
                adapter_factory=lambda: FakeAdapter(events),
                widget_factory=lambda: events.append("widget-start") or None,
                watcher_factory=lambda: FakeWatcher(events),
            )

            runtime.start()

            self.assertEqual(
                events[:3], ["provider-start", "widget-start", "watcher-run"]
            )
            self.assertTrue(runtime.started)

    def test_stop_terminates_watcher_provider_and_widget_in_order(self):
        events = []
        with tempfile.TemporaryDirectory() as temp:
            widget = SimpleNamespace(stop=lambda: events.append("widget-stop"), pid=123)
            runtime = managed_runtime.ManagedRuntime(
                Path(temp),
                adapter_factory=lambda: FakeAdapter(events),
                widget_factory=lambda: widget,
                watcher_factory=lambda: FakeWatcher(events),
            )
            runtime.start()
            events.clear()

            runtime.stop("operator")

            self.assertEqual(events, ["watcher-stop", "provider-stop", "widget-stop"])
            self.assertFalse(runtime.started)

    def test_stop_is_idempotent_before_start(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = managed_runtime.ManagedRuntime(Path(temp))
            runtime.stop("operator")
            self.assertFalse(runtime.started)

    def test_stop_records_operator_reason_for_later_generation_boundary(self):
        events = []
        with tempfile.TemporaryDirectory() as temp:
            runtime = managed_runtime.ManagedRuntime(
                Path(temp),
                adapter_factory=lambda: FakeAdapter(events),
                watcher_factory=lambda: FakeWatcher(events),
            )
            runtime.start()
            runtime.stop("operator")
            self.assertEqual(runtime.last_stop_reason, "operator")

    def test_unexpected_provider_exit_records_final_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = managed_runtime.ManagedRuntime(
                Path(temp),
                adapter_factory=lambda: DeadAdapter([]),
                watcher_factory=lambda: FakeWatcher([]),
            )
            with mock.patch.object(managed_runtime, "write_generation"):
                runtime.start()
            runtime._watcher_thread.join(timeout=2)
            records, _ = diagnostics.read_diagnostics(Path(temp))
            exits = [r for r in records if r["action"] == "unexpected-provider-exit"]
            self.assertEqual(len(exits), 1)
            self.assertEqual(exits[0]["details"]["final_capture"], "final pane output")


if __name__ == "__main__":
    unittest.main()
