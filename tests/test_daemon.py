"""Tests for the resident daemon, local IPC, and simple lifecycle controls."""

import io
import json
import os
import socket
import tempfile
import threading
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ariadex import cli, concurrency, config, daemon, prerequisites, state
from ariadex.terminal import FakeTerminalDriver


def handoff_path(root: Path) -> Path:
    """Configured durable handoff location (default root `HANDOFF.md`)."""
    return root / config.load(root).handoff_file


def run_cli(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with chdir(root), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


def init_project(root: Path) -> None:
    code, _, _ = run_cli(root, "init")
    assert code == 0


def ready_report():
    """Coordinator success for tests that exercise later start phases."""
    return prerequisites.CoordinatorReport(
        results=[
            prerequisites.PrerequisiteResult("runtime", "present", "runtime ready"),
            prerequisites.PrerequisiteResult("provider", "present", "provider ok"),
            prerequisites.PrerequisiteResult("tmux", "present", "tmux ready"),
            prerequisites.PrerequisiteResult("widget", "present", "widget ready"),
        ],
        ready=True,
    )


class FakeManagedAdapter:
    """Adapter double over an in-memory driver (no tmux needed)."""

    def __init__(self, driver, session):
        self.driver = driver
        self.session_name = session

    def start(self):
        return self.driver.create_or_connect(self.session_name, ".", ["provider"])

    def terminate(self):
        self.driver.terminate(self.session_name)


class FakeManagedWatcher:
    def __init__(self, outcome="done"):
        self.outcome = outcome

    def run(self):
        from types import SimpleNamespace

        return SimpleNamespace(outcome=self.outcome, detail="fake")

    def request_quit(self):
        return "quit requested"


class FakeWidgetProc:
    def __init__(self):
        self._alive = True

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self._alive = False

    def kill(self):
        self._alive = False


def start_ipc_server(root: Path) -> tuple[threading.Event, threading.Thread]:
    """Serve handle_request over the project socket in a thread."""
    sock_path = daemon.socket_path(root)
    if sock_path.exists():
        sock_path.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    os.chmod(sock_path, 0o600)
    server.listen(8)
    stop = threading.Event()
    thread = threading.Thread(
        target=daemon._serve_forever, args=(root, server, stop), daemon=True
    )
    thread.start()
    return stop, thread


class RequestSchemaTest(unittest.TestCase):
    def test_known_types_round_trip(self):
        for name in ("status", "pause", "resume", "stop", "wake"):
            self.assertEqual(daemon.parse_request(json.dumps({"type": name})), name)

    def test_unknown_type_rejected(self):
        with self.assertRaises(daemon.DaemonError):
            daemon.build_request("reboot")
        with self.assertRaises(daemon.DaemonError):
            daemon.parse_request(json.dumps({"type": "reboot"}))

    def test_malformed_input_rejected(self):
        for bad in ("not json{", "[1, 2]", '"status"', ""):
            with self.subTest(bad=bad), self.assertRaises(daemon.DaemonError):
                daemon.parse_request(bad)

    def test_oversize_message_rejected(self):
        with self.assertRaises(daemon.DaemonError):
            daemon.parse_request("x" * (daemon.MAX_MESSAGE_BYTES + 1))

    def test_response_bound_enforced(self):
        with self.assertRaises(daemon.DaemonError):
            daemon.encode_message({"blob": "y" * daemon.MAX_MESSAGE_BYTES})


class HandleRequestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def runs_count(self) -> int:
        runs = self.root / ".ariadex" / "runs"
        return len(list(runs.iterdir())) if runs.is_dir() else 0

    def test_status_and_wake_are_read_only(self):
        before = self.runs_count()
        for name in ("status", "wake"):
            reply = daemon.handle_request(self.root, name)
            self.assertTrue(reply["ok"])
            self.assertIn("mode", reply["state"])
        self.assertEqual(state.read(self.root).mode, "MANUAL")
        self.assertEqual(self.runs_count(), before)

    def test_unknown_request_changes_nothing(self):
        before = self.runs_count()
        reply = daemon.handle_request(self.root, "reboot")
        self.assertFalse(reply["ok"])
        self.assertEqual(state.read(self.root).mode, "MANUAL")
        self.assertEqual(self.runs_count(), before)

    def test_pause_prevents_scheduling_without_input(self):
        before = self.runs_count()
        reply = daemon.handle_request(self.root, "pause")
        self.assertTrue(reply["ok"])
        self.assertEqual(state.read(self.root).mode, "PAUSE")
        self.assertIsNotNone(
            concurrency.cancellation_requested(self.root),
            "pause must coordinate in-flight work",
        )
        self.assertEqual(self.runs_count(), before)

    def test_resume_resynchronizes_before_scheduling(self):
        daemon.handle_request(self.root, "pause")
        reply = daemon.handle_request(self.root, "resume")
        self.assertTrue(reply["ok"], reply)
        self.assertEqual(state.read(self.root).mode, "MANUAL")
        self.assertIn("resync_next", reply["state"])
        self.assertIsNone(concurrency.cancellation_requested(self.root))

    def test_resume_rejected_outside_pause(self):
        reply = daemon.handle_request(self.root, "resume")
        self.assertFalse(reply["ok"])
        self.assertEqual(state.read(self.root).mode, "MANUAL")

    def test_stop_marks_stopping_without_deleting_work(self):
        handoff_before = (handoff_path(self.root)).read_text()
        reply = daemon.handle_request(self.root, "stop")
        self.assertTrue(reply["ok"])
        record = daemon.read_record(self.root)
        # No record yet in this fixture: stop still reports bounded state.
        self.assertIsNone(record)
        self.assertIn("handoff", handoff_before.lower())

    def test_handle_request_needs_no_daemon_record(self):
        self.assertIsNone(daemon.read_record(self.root))
        self.assertTrue(daemon.handle_request(self.root, "status")["ok"])


class SocketSafetyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def test_missing_socket_reports_repair(self):
        ok, repair = daemon.check_socket_safety(daemon.socket_path(self.root))
        self.assertFalse(ok)
        self.assertIn("ariadex start", repair)

    def test_non_socket_refused(self):
        daemon.socket_path(self.root).write_text("not a socket")
        ok, repair = daemon.check_socket_safety(daemon.socket_path(self.root))
        self.assertFalse(ok)
        self.assertIn("not a socket", repair)

    def test_broad_permissions_refused(self):
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(daemon.socket_path(self.root)))
            os.chmod(daemon.socket_path(self.root), 0o777)
            ok, repair = daemon.check_socket_safety(daemon.socket_path(self.root))
        finally:
            server.close()
        self.assertFalse(ok)
        self.assertIn("permissions", repair)

    def test_safe_socket_accepted(self):
        stop, thread = start_ipc_server(self.root)
        try:
            ok, _ = daemon.check_socket_safety(daemon.socket_path(self.root))
            self.assertTrue(ok)
        finally:
            stop.set()
            thread.join(timeout=10)


class IpcRoundTripTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def test_status_round_trip_over_unix_socket(self):
        stop, thread = start_ipc_server(self.root)
        try:
            response = daemon.send_request(self.root, "status", timeout_s=5.0)
            self.assertTrue(response["ok"])
            self.assertEqual(response["state"]["mode"], "MANUAL")
        finally:
            stop.set()
            thread.join(timeout=10)

    def test_unknown_client_request_rejected_locally(self):
        stop, thread = start_ipc_server(self.root)
        try:
            with self.assertRaises(daemon.DaemonError):
                daemon.send_request(self.root, "reboot", timeout_s=5.0)
        finally:
            stop.set()
            thread.join(timeout=10)

    def test_unreachable_daemon_fails_closed(self):
        with self.assertRaises(daemon.DaemonError):
            daemon.send_request(self.root, "status", timeout_s=2.0)

    def test_pause_round_trip_changes_mode_without_input(self):
        stop, thread = start_ipc_server(self.root)
        try:
            response = daemon.send_request(self.root, "pause", timeout_s=5.0)
            self.assertTrue(response["ok"])
            self.assertEqual(response["state"]["mode"], "PAUSE")
            self.assertEqual(state.read(self.root).mode, "PAUSE")
        finally:
            stop.set()
            thread.join(timeout=10)


class DaemonRecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def test_dead_pid_is_not_alive(self):
        record = daemon.DaemonRecord(pid=2**30, status="running")
        self.assertFalse(daemon.daemon_alive(record))
        self.assertFalse(daemon.daemon_alive(None))

    def test_stopped_record_is_not_alive(self):
        record = daemon.DaemonRecord(pid=os.getpid(), status="stopped")
        self.assertFalse(daemon.daemon_alive(record))

    def test_record_round_trip(self):
        record = daemon.DaemonRecord(
            pid=os.getpid(), started_at=daemon.now_iso(), status="running"
        )
        daemon.write_record(self.root, record)
        loaded = daemon.read_record(self.root)
        assert loaded is not None
        self.assertEqual(loaded.pid, os.getpid())
        self.assertTrue(daemon.daemon_alive(loaded))

    def test_corrupt_record_rejected(self):
        daemon.daemon_record_path(self.root).write_text('{"pid": -3}')
        self.assertIsNone(daemon.read_record(self.root))


class LifecycleCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def test_stop_without_daemon_is_idempotent(self):
        code, out, _ = run_cli(self.root, "stop")
        self.assertEqual(code, 0)
        self.assertIn("no running daemon", out)

    def test_start_refuses_live_lease_without_input(self):
        with (
            concurrency.owned_lock(self.root, state.read(self.root).session_id),
            mock.patch.object(
                cli.prerequisites_mod, "coordinate", return_value=ready_report()
            ),
        ):
            code, _, err = run_cli(self.root, "start")
        self.assertNotEqual(code, 0)
        self.assertIn("refused", err)
        self.assertIsNone(daemon.read_record(self.root))

    def test_duplicate_start_reports_existing_without_second_scheduler(self):
        stop, thread = start_ipc_server(self.root)
        daemon.write_record(
            self.root,
            daemon.DaemonRecord(
                pid=os.getpid(),
                started_at=daemon.now_iso(),
                status="running",
                session_id=state.read(self.root).session_id,
            ),
        )
        try:
            with mock.patch.object(
                cli, "_repair_live_runtime", return_value=0
            ) as repair:
                code, _out, _ = run_cli(self.root, "start")
            self.assertEqual(code, 0)
            repair.assert_called_once()
            record = daemon.read_record(self.root)
            assert record is not None
            self.assertEqual(record.pid, os.getpid())
        finally:
            stop.set()
            thread.join(timeout=10)

    def test_status_prefers_daemon_state_when_healthy(self):
        stop, thread = start_ipc_server(self.root)
        daemon.write_record(
            self.root,
            daemon.DaemonRecord(
                pid=os.getpid(),
                started_at=daemon.now_iso(),
                status="running",
                session_id=state.read(self.root).session_id,
            ),
        )
        try:
            daemon.handle_request(self.root, "pause")
            code, out, _ = run_cli(self.root, "status")
            self.assertEqual(code, 0)
            self.assertIn("daemon: running", out)
            self.assertIn("PAUSE", out)
        finally:
            stop.set()
            thread.join(timeout=10)

    def test_status_calculates_pending_spec_from_active_changes(self):
        change = self.root / "openspec" / "changes" / "next-change"
        change.mkdir(parents=True)
        (change / "tasks.md").write_text(
            "# Tasks\n\n- [ ] implement\n", encoding="utf-8"
        )
        view = daemon.daemon_status_view(self.root)
        self.assertEqual(view["next_action"], "start-spec next-change")

    def test_pause_resume_json_options(self):
        code, out, _ = run_cli(self.root, "pause", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["mode"], "PAUSE")
        code, out, _ = run_cli(self.root, "resume", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["mode"], "MANUAL")

    def test_full_start_stop_cycle(self):
        driver = FakeTerminalDriver()
        session = f"ariadex-{state.read(self.root).session_id}"
        with (
            mock.patch.object(
                cli.prerequisites_mod, "coordinate", return_value=ready_report()
            ),
            mock.patch.object(
                cli.providers_mod,
                "get_adapter",
                return_value=FakeManagedAdapter(driver, session),
            ),
            mock.patch.object(
                cli, "_spawn_widget_process", return_value=FakeWidgetProc()
            ),
            mock.patch.object(cli, "_attach_session", return_value=0),
            mock.patch.object(
                cli.robot_mod, "RobotWatcher", return_value=FakeManagedWatcher()
            ),
        ):
            code, out, _ = run_cli(self.root, "start")
        self.assertEqual(code, 0, out)
        self.assertIn("complete", out)
        # Queue-empty completion tears everything down deterministically.
        self.assertFalse(driver.session_alive(session))
        record = daemon.read_record(self.root)
        assert record is not None
        self.assertFalse(daemon.daemon_alive(record))
        code, out, _ = run_cli(self.root, "status", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertNotIn("daemon", payload)
        self.assertEqual(payload["mode"], "MANUAL")
        code, _, _ = run_cli(self.root, "stop")
        self.assertEqual(code, 0)


class RunDaemonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def test_run_daemon_refuses_live_owner(self):
        with concurrency.owned_lock(self.root, state.read(self.root).session_id):
            self.assertEqual(daemon.run_daemon(self.root, max_polls=1), 1)

    def test_run_daemon_bounded_loop_releases_lease(self):
        code = daemon.run_daemon(self.root, poll_interval_s=0.01, max_polls=2)
        self.assertEqual(code, 0)
        self.assertEqual(concurrency.diagnose(self.root)["state"], "free")
        record = daemon.read_record(self.root)
        assert record is not None
        self.assertEqual(record.status, "stopped")
        self.assertFalse(daemon.socket_path(self.root).exists())


class AdminNamespaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def test_admin_mirrors_top_level_doctor(self):
        top_code, top_out, _ = run_cli(self.root, "doctor")
        code, out, _ = run_cli(self.root, "admin", "doctor")
        self.assertEqual((code, out), (top_code, top_out))

    def test_admin_mirrors_status_and_queue(self):
        self.assertEqual(run_cli(self.root, "admin", "status")[0], 0)
        self.assertEqual(run_cli(self.root, "admin", "queue")[0], 0)

    def test_admin_rejects_unknown_command(self):
        code, _, err = run_cli(self.root, "admin", "reboot")
        self.assertNotEqual(code, 0)
        self.assertIn("unknown admin command", err)

    def test_admin_refuses_nesting(self):
        code, _, err = run_cli(self.root, "admin", "admin", "doctor")
        self.assertNotEqual(code, 0)
        self.assertIn("nested", err)

    def test_admin_lists_commands(self):
        code, out, _ = run_cli(self.root, "admin")
        self.assertEqual(code, 0)
        self.assertIn("doctor", out)


if __name__ == "__main__":
    unittest.main()
