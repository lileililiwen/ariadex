"""Focused failure-path tests for safety-critical modules.

Covers terminal transport errors, tmux-setup failure/timeout/permission
paths, concurrency lease contention and corruption, operator preflight
failures, and live-evidence fault injection. Everything is hermetic: no
tmux binary, network, or provider CLI is touched.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ariadex import cli as cli_mod
from ariadex import concurrency as concurrency_mod
from ariadex import operator as operator_mod
from ariadex import terminal as terminal_mod
from ariadex import tmux_setup as setup_mod
from ariadex.live_evidence import (
    BLOCKED,
    isolated_tmux_session,
    run_all,
    scenario_opencode_lifecycle,
)
from ariadex.terminal import (
    DeliveryFailed,
    FakeTerminalDriver,
    SessionMissing,
    TerminalError,
    TmuxNotAvailable,
    session_name_for,
)


def completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=["tmux"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TerminalFailureTest(unittest.TestCase):
    def test_run_wraps_missing_binary(self):
        driver = terminal_mod.TmuxDriver(executable="/no/such/tmux")
        with (
            mock.patch.object(
                terminal_mod.subprocess,
                "run",
                side_effect=FileNotFoundError("gone"),
            ),
            self.assertRaises(TmuxNotAvailable),
        ):
            driver._run(["has-session"], "ctx")

    def test_run_wraps_os_error(self):
        driver = terminal_mod.TmuxDriver()
        with (
            mock.patch.object(
                terminal_mod.subprocess, "run", side_effect=OSError("denied")
            ),
            self.assertRaises(TmuxNotAvailable),
        ):
            driver._run(["has-session"], "ctx")

    def test_run_reports_stderr_detail(self):
        driver = terminal_mod.TmuxDriver()
        with (
            mock.patch.object(
                terminal_mod.subprocess,
                "run",
                return_value=completed(1, stdout="", stderr="bad pane"),
            ),
            self.assertRaises(TerminalError) as ctx,
        ):
            driver._run(["capture-pane"], "ctx")
        self.assertIn("bad pane", str(ctx.exception))

    def test_run_timeout_surfaces(self):
        driver = terminal_mod.TmuxDriver()
        with (
            mock.patch.object(
                terminal_mod.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("tmux", 30),
            ),
            self.assertRaises(subprocess.TimeoutExpired),
        ):
            driver._run(["has-session"], "ctx")

    def test_session_alive_false_and_unavailable(self):
        driver = terminal_mod.TmuxDriver()
        with mock.patch.object(
            terminal_mod.subprocess, "run", return_value=completed(1)
        ):
            self.assertFalse(driver.session_alive("gone"))
        with (
            mock.patch.object(
                terminal_mod.subprocess, "run", side_effect=OSError("denied")
            ),
            self.assertRaises(TmuxNotAvailable),
        ):
            driver.session_alive("gone")

    def test_create_or_connect_branches(self):
        driver = terminal_mod.TmuxDriver()
        with mock.patch.object(driver, "session_alive", return_value=True):
            self.assertEqual(driver.create_or_connect("s", "/tmp", ["x"]), "connected")
        with (
            mock.patch.object(driver, "session_alive", return_value=False),
            mock.patch.object(terminal_mod.shutil, "which", return_value=None),
            self.assertRaises(TmuxNotAvailable),
        ):
            driver.create_or_connect("s", "/tmp", ["x"])
        with (
            mock.patch.object(driver, "session_alive", return_value=False),
            mock.patch.object(terminal_mod.shutil, "which", return_value="/bin/tmux"),
            self.assertRaises(TerminalError),
        ):
            driver.create_or_connect("s", "/tmp", [])

    def test_send_interrupt_capture_missing_session(self):
        driver = terminal_mod.TmuxDriver()
        with mock.patch.object(driver, "session_alive", return_value=False):
            with self.assertRaises(SessionMissing):
                driver.send_input("gone", "hi")
            with self.assertRaises(SessionMissing):
                driver.interrupt("gone")
            with self.assertRaises(SessionMissing):
                driver.capture("gone")

    def test_send_failure_becomes_delivery_failed(self):
        driver = terminal_mod.TmuxDriver()
        with (
            mock.patch.object(driver, "session_alive", return_value=True),
            mock.patch.object(
                driver, "_run", side_effect=TerminalError("tmux exploded")
            ),
        ):
            with self.assertRaises(DeliveryFailed):
                driver.send_input("s", "hi")
            with self.assertRaises(DeliveryFailed):
                driver.interrupt("s")

    def test_capture_returns_stdout_and_terminate_idempotent(self):
        driver = terminal_mod.TmuxDriver()
        with (
            mock.patch.object(driver, "session_alive", return_value=True),
            mock.patch.object(
                driver, "_run", return_value=completed(0, stdout="pane-text")
            ),
        ):
            self.assertEqual(driver.capture("s"), "pane-text")
        with mock.patch.object(driver, "session_alive", return_value=False):
            self.assertIsNone(driver.terminate("gone"))

    def test_session_name_mapping(self):
        self.assertEqual(session_name_for("abc"), "ariadex-abc")


class TmuxSetupFailureTest(unittest.TestCase):
    def test_needs_sudo_branches(self):
        with mock.patch.object(setup_mod.os, "geteuid", return_value=0):
            self.assertFalse(setup_mod.needs_sudo())
        with mock.patch.object(setup_mod.os, "geteuid", return_value=1000):
            self.assertTrue(setup_mod.needs_sudo())
        with mock.patch.object(
            setup_mod.os, "geteuid", side_effect=AttributeError("no geteuid")
        ):
            self.assertFalse(setup_mod.needs_sudo())

    def test_install_command_variants(self):
        with self.assertRaises(setup_mod.TmuxSetupError):
            setup_mod.install_command("no-such-manager")
        with (
            mock.patch.object(setup_mod, "needs_sudo", return_value=False),
            mock.patch.object(setup_mod.shutil, "which", return_value=None),
        ):
            self.assertEqual(
                setup_mod.install_command("apt-get"),
                ["apt-get", "install", "-y", "tmux"],
            )
        with (
            mock.patch.object(setup_mod, "needs_sudo", return_value=True),
            mock.patch.object(setup_mod.shutil, "which", return_value="/usr/bin/sudo"),
        ):
            cmd = setup_mod.install_command("apk")
            self.assertEqual(cmd[:2], ["sudo", "-n"])

    def test_remove_and_hint(self):
        with self.assertRaises(setup_mod.TmuxSetupError):
            setup_mod.remove_command("no-such-manager")
        self.assertIn("apt-get install", setup_mod.manual_hint("apt-get"))
        self.assertIn("package manager", setup_mod.manual_hint(None))

    def test_require_tmux(self):
        with mock.patch.object(setup_mod, "find_tmux", return_value="/usr/bin/tmux"):
            self.assertEqual(setup_mod.require_tmux(), "/usr/bin/tmux")
        with (
            mock.patch.object(setup_mod, "find_tmux", return_value=None),
            self.assertRaises(setup_mod.TmuxSetupError) as ctx,
        ):
            setup_mod.require_tmux()
        self.assertIn("auto-install disabled", str(ctx.exception))

    def test_ensure_tmux_branches(self):
        with mock.patch.object(setup_mod, "find_tmux", return_value="/usr/bin/tmux"):
            self.assertEqual(setup_mod.ensure_tmux(), "/usr/bin/tmux")
        with (
            mock.patch.object(setup_mod, "find_tmux", return_value=None),
            mock.patch.object(setup_mod, "detect_manager", return_value=None),
            self.assertRaises(setup_mod.TmuxSetupError),
        ):
            setup_mod.ensure_tmux()
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:2] == ["apt-get", "update"]:
                return completed(0)
            return completed(1, stderr="install denied")

        with (
            mock.patch.object(setup_mod, "find_tmux", return_value=None),
            mock.patch.object(setup_mod, "detect_manager", return_value="apt-get"),
            mock.patch.object(setup_mod, "needs_sudo", return_value=False),
            mock.patch.object(setup_mod.subprocess, "run", side_effect=fake_run),
            self.assertRaises(setup_mod.TmuxSetupError) as ctx,
        ):
            setup_mod.ensure_tmux()
        self.assertIn("install manually", str(ctx.exception))
        self.assertTrue(any(c[:2] == ["apt-get", "update"] for c in calls))

    def test_ensure_tmux_success_but_missing(self):
        with (
            mock.patch.object(
                setup_mod,
                "find_tmux",
                side_effect=[None, None],
            ),
            mock.patch.object(setup_mod, "detect_manager", return_value="brew"),
            mock.patch.object(setup_mod, "needs_sudo", return_value=False),
            mock.patch.object(setup_mod.subprocess, "run", return_value=completed(0)),
            self.assertRaises(setup_mod.TmuxSetupError) as ctx,
        ):
            setup_mod.ensure_tmux()
        self.assertIn("still not on PATH", str(ctx.exception))

    def test_uninstall_branches(self):
        with (
            mock.patch.object(setup_mod, "detect_manager", return_value=None),
            self.assertRaises(setup_mod.TmuxSetupError),
        ):
            setup_mod.uninstall_tmux()
        with (
            mock.patch.object(setup_mod, "detect_manager", return_value="dnf"),
            mock.patch.object(setup_mod, "needs_sudo", return_value=False),
            mock.patch.object(
                setup_mod.subprocess,
                "run",
                return_value=completed(1, stderr="locked"),
            ),
            self.assertRaises(setup_mod.TmuxSetupError),
        ):
            setup_mod.uninstall_tmux()
        with (
            mock.patch.object(setup_mod, "detect_manager", return_value="dnf"),
            mock.patch.object(setup_mod, "needs_sudo", return_value=False),
            mock.patch.object(setup_mod.subprocess, "run", return_value=completed(0)),
        ):
            self.assertEqual(setup_mod.uninstall_tmux(), "dnf")

    def test_read_depends_branches(self):
        with (
            mock.patch.object(setup_mod.shutil, "which", return_value=None),
            self.assertRaises(setup_mod.TmuxSetupError),
        ):
            setup_mod.read_depends()
        with (
            mock.patch.object(
                setup_mod.shutil, "which", return_value="/usr/bin/apt-cache"
            ),
            mock.patch.object(
                setup_mod.subprocess,
                "run",
                return_value=completed(1, stderr="nope"),
            ),
            self.assertRaises(setup_mod.TmuxSetupError),
        ):
            setup_mod.read_depends()
        out = "tmux\n  Depends: libtinfo6\n  Depends: libc6\n  Depends: libtinfo6\n"
        with (
            mock.patch.object(
                setup_mod.shutil, "which", return_value="/usr/bin/apt-cache"
            ),
            mock.patch.object(
                setup_mod.subprocess, "run", return_value=completed(0, stdout=out)
            ),
        ):
            self.assertEqual(setup_mod.read_depends(), ["libtinfo6", "libc6"])

    def test_missing_shared_libs_branches(self):
        with mock.patch.object(
            setup_mod.subprocess, "run", return_value=completed(1, stderr="bad elf")
        ):
            missing = setup_mod.missing_shared_libs("/bin/false")
        self.assertTrue(any("ldd failed" in m for m in missing))
        out = "\tlibfoo.so => not found\n\tlibc.so.6 => /lib/libc.so.6\n"
        seen_env = {}

        def fake_run(cmd, **kwargs):
            seen_env.update(kwargs.get("env", {}))
            return completed(0, stdout=out)

        with mock.patch.object(setup_mod.subprocess, "run", side_effect=fake_run):
            missing = setup_mod.missing_shared_libs("/bin/x", lib_dirs=["/opt/lib"])
        self.assertEqual(missing, ["libfoo.so"])
        self.assertIn("/opt/lib", seen_env.get("LD_LIBRARY_PATH", ""))

    def test_fetch_local_toolchain_and_download_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.object(setup_mod.shutil, "which", return_value=None),
                self.assertRaises(setup_mod.TmuxSetupError),
            ):
                setup_mod.fetch_local_tmux(tmp)
            with (
                mock.patch.object(
                    setup_mod.shutil, "which", return_value="/usr/bin/apt-get"
                ),
                mock.patch.object(
                    setup_mod, "read_depends", return_value=["libtinfo6"]
                ),
                mock.patch.object(
                    setup_mod.subprocess,
                    "run",
                    return_value=completed(1, stderr="offline"),
                ),
                self.assertRaises(setup_mod.TmuxSetupError) as ctx,
            ):
                setup_mod.fetch_local_tmux(tmp)
            self.assertIn("download", str(ctx.exception))

    def test_fetch_local_extract_and_verify_failures(self):
        def run_ok_empty(cmd, **kwargs):
            return completed(0, stdout="")

        with tempfile.TemporaryDirectory() as tmp:
            dl_dir = Path(tmp) / "debs"
            dl_dir.mkdir(parents=True)
            (dl_dir / "other_1.0_amd64.deb").write_text("x")
            with (
                mock.patch.object(
                    setup_mod.shutil, "which", return_value="/usr/bin/apt-get"
                ),
                mock.patch.object(setup_mod, "read_depends", return_value=[]),
                mock.patch.object(
                    setup_mod.subprocess, "run", side_effect=run_ok_empty
                ),
                self.assertRaises(setup_mod.TmuxSetupError) as ctx,
            ):
                setup_mod.fetch_local_tmux(tmp)
            self.assertIn("no tmux .deb", str(ctx.exception))

    def test_fetch_local_os_error_wrapped(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(
                setup_mod.shutil, "which", return_value="/usr/bin/apt-get"
            ),
            mock.patch.object(
                setup_mod, "read_depends", side_effect=OSError("disk gone")
            ),
            self.assertRaises(setup_mod.TmuxSetupError),
        ):
            setup_mod.fetch_local_tmux(tmp)

    def test_write_tmux_wrapper_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            wrapper = Path(tmp) / "bin" / "tmux"
            out = setup_mod.write_tmux_wrapper(
                wrapper, Path("/opt/root/usr/bin/tmux"), [Path("/opt/root/lib")]
            )
            self.assertEqual(out, wrapper)
            self.assertTrue(os.access(wrapper, os.X_OK))
            self.assertIn("LD_LIBRARY_PATH", wrapper.read_text(encoding="utf-8"))


class ConcurrencyFailureTest(unittest.TestCase):
    def _project(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def _write_lock(self, root: Path, payload: dict) -> Path:
        path = concurrency_mod.lock_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_acquire_corrupt_lock_refuses_without_deletion(self):
        root = self._project()
        path = self._write_lock(root, {"not": "a lock"})
        with self.assertRaises(concurrency_mod.LockError) as ctx:
            concurrency_mod.acquire(root, "s")
        self.assertIn("refusing to delete", str(ctx.exception))
        self.assertTrue(path.is_file())

    def test_acquire_live_and_stale(self):
        root = self._project()
        live = concurrency_mod.acquire(root, "owner-session")
        self.assertEqual(live.session_id, "owner-session")
        with self.assertRaises(concurrency_mod.ActiveLockError) as ctx:
            concurrency_mod.acquire(root, "second-session")
        self.assertIsNotNone(ctx.exception.owner)
        concurrency_mod.release(root)
        stale_payload = {
            "version": 1,
            "pid": 999999999,
            "hostname": "dead-host",
            "session_id": "stale",
            "started_at": "2000-01-01T00:00:00+00:00",
            "heartbeat_at": "2000-01-01T00:00:00+00:00",
        }
        self._write_lock(root, stale_payload)
        with self.assertRaises(concurrency_mod.StaleLockError):
            concurrency_mod.acquire(root, "fresh")

    def test_diagnose_corrupt_free_and_stale(self):
        root = self._project()
        self.assertEqual(concurrency_mod.diagnose(root)["state"], "free")
        self._write_lock(root, {"not": "a lock"})
        self.assertEqual(concurrency_mod.diagnose(root)["state"], "corrupt")

    def test_pid_alive_branches(self):
        self.assertTrue(concurrency_mod.pid_alive(os.getpid()))
        self.assertFalse(concurrency_mod.pid_alive(999999999))
        with mock.patch.object(
            concurrency_mod.os, "kill", side_effect=PermissionError("denied")
        ):
            self.assertTrue(concurrency_mod.pid_alive(1234))

    def test_heartbeat_and_release_ownership(self):
        root = self._project()
        self.assertFalse(concurrency_mod.heartbeat(root))
        self.assertFalse(concurrency_mod.release(root))
        concurrency_mod.acquire(root, "mine")
        self.assertTrue(concurrency_mod.heartbeat(root))
        self.assertTrue(concurrency_mod.release(root))
        self.assertFalse(concurrency_mod.release(root))

    def test_lock_from_dict_rejects_invalid(self):
        self.assertIsNone(concurrency_mod.lock_from_dict({}))
        self.assertIsNone(concurrency_mod.lock_from_dict({"pid": -3}))
        self.assertIsNone(concurrency_mod.lock_from_dict({"pid": "nan"}))

    def test_cancellation_signal_branches(self):
        root = self._project()
        self.assertIsNone(concurrency_mod.cancellation_requested(root))
        cancel = concurrency_mod.cancel_path(root)
        cancel.parent.mkdir(parents=True, exist_ok=True)
        cancel.write_text("not json", encoding="utf-8")
        unknown = concurrency_mod.cancellation_requested(root)
        assert unknown is not None
        self.assertEqual(unknown["requested_by"], "unknown")
        cancel.write_text(
            json.dumps({"requested_by": "op", "reason": "stop", "at": "now"}),
            encoding="utf-8",
        )
        known = concurrency_mod.cancellation_requested(root)
        assert known is not None
        self.assertEqual(known["requested_by"], "op")

    def test_tmux_session_status_reports_without_starting(self):
        root = self._project()
        with mock.patch(
            "ariadex.terminal.TmuxDriver.session_alive",
            side_effect=TmuxNotAvailable("no tmux"),
        ):
            name, alive = concurrency_mod.tmux_session_status(root, "sess-1")
        self.assertEqual(name, "ariadex-sess-1")
        self.assertIsNone(alive)

    def test_is_live_fresh_heartbeat_with_dead_pid(self):
        owner = concurrency_mod.LockInfo(
            pid=999999999, heartbeat_at=concurrency_mod.now_iso()
        )
        self.assertTrue(concurrency_mod.is_live(owner))

    def test_heartbeat_age_unparsable(self):
        owner = concurrency_mod.LockInfo(pid=1, heartbeat_at="not-a-time")
        self.assertIsNone(concurrency_mod.heartbeat_age_s(owner))


class OperatorFailureTest(unittest.TestCase):
    def _project(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / ".ariadex").mkdir(parents=True, exist_ok=True)
        (root / ".ariadex" / "config.yaml").write_text(
            "agent_provider: opencode\n"
            "terminal_driver: tmux\n"
            "context_strategy: per-spec\n"
            "reset_mode: auto\n"
            "spec_dir: openspec/changes\n"
            "handoff_file: .ariadex/handoff.md\n"
            "verification_commands: []\n"
            "retry_limit: 2\n"
            "blocker_policy: stop-on-blocker\n",
            encoding="utf-8",
        )
        (root / ".ariadex" / "handoff.md").write_text(
            "# Ariadex handoff\n", encoding="utf-8"
        )
        (root / ".ariadex" / "state.json").write_text(
            '{"mode": "AUTO", "session_id": "op", '
            '"current_spec": null, "unresolved_count": 0}',
            encoding="utf-8",
        )
        (root / "openspec" / "changes").mkdir(parents=True, exist_ok=True)
        return root

    def _failed(self, root: Path) -> dict[str, operator_mod.DoctorCheck]:
        checks, _ = operator_mod.run_doctor(root)
        return {c.name: c for c in checks if not c.ok}

    def test_doctor_invalid_config(self):
        root = self._project()
        (root / ".ariadex" / "config.yaml").write_text("{{{bad", encoding="utf-8")
        failed = self._failed(root)
        self.assertIn("config", failed)

    def test_doctor_unsupported_provider_and_terminal(self):
        root = self._project()
        text = (root / ".ariadex" / "config.yaml").read_text(encoding="utf-8")
        text = text.replace("agent_provider: opencode", "agent_provider: nope")
        text = text.replace("terminal_driver: tmux", "terminal_driver: nope")
        (root / ".ariadex" / "config.yaml").write_text(text, encoding="utf-8")
        failed = self._failed(root)
        self.assertIn("provider", failed)
        self.assertIn("terminal", failed)

    def test_doctor_missing_tmux_and_specs(self):
        root = self._project()
        real_which = operator_mod.shutil.which
        with mock.patch.object(
            operator_mod.shutil,
            "which",
            side_effect=lambda name: None if name == "tmux" else real_which(name),
        ):
            failed = self._failed(root)
        self.assertIn("tmux", failed)
        import shutil as shutil_mod

        shutil_mod.rmtree(root / "openspec")
        failed = self._failed(root)
        self.assertIn("specs", failed)

    def test_doctor_lock_states(self):
        root = self._project()
        concurrency_mod.acquire(root, "live-owner")
        try:
            failed = self._failed(root)
            self.assertIn("lock", failed)
            self.assertIn("no input sent", failed["lock"].detail)
        finally:
            concurrency_mod.release(root)
        stale = {
            "version": 1,
            "pid": 999999999,
            "hostname": "dead",
            "session_id": "stale",
            "started_at": "2000-01-01T00:00:00+00:00",
            "heartbeat_at": "2000-01-01T00:00:00+00:00",
        }
        path = concurrency_mod.lock_path(root)
        path.write_text(json.dumps(stale), encoding="utf-8")
        failed = self._failed(root)
        self.assertIn("recover", failed["lock"].detail)
        path.write_text(json.dumps({"not": "a lock"}), encoding="utf-8")
        failed = self._failed(root)
        self.assertIn("unreadable", failed["lock"].detail)
        path.unlink()

    def test_doctor_uncertain_cycle(self):
        root = self._project()
        concurrency_mod.write_cycle(root, "sent", action="probe")
        try:
            failed = self._failed(root)
            self.assertIn("interruption", failed)
        finally:
            concurrency_mod.clear_cycle(root)

    def test_cmd_doctor_fails_closed_without_verification(self):
        root = self._project()
        self.assertEqual(cli_mod.cmd_doctor(root), cli_mod.EXIT_ERROR)
        self.assertEqual(cli_mod.cmd_doctor(root, as_json=True), cli_mod.EXIT_ERROR)

    def test_acquire_schedule_lease_refuses_live_owner(self):
        root = self._project()
        self.assertTrue(cli_mod._acquire_schedule_lease(root, "first"))
        try:
            self.assertFalse(cli_mod._acquire_schedule_lease(root, "second"))
        finally:
            concurrency_mod.release(root)

    def test_prune_and_export_noninteractive_contract(self):
        root = self._project()
        # Non-interactive callers (tests, CI, pipes) proceed without a prompt.
        self.assertEqual(cli_mod.cmd_prune_logs(root), cli_mod.EXIT_OK)
        self.assertEqual(
            cli_mod.cmd_export_logs(root, out=str(root / "out")), cli_mod.EXIT_OK
        )
        self.assertEqual(
            cli_mod.cmd_export_logs(root, out=str(root / "out"), max_bytes=-1),
            cli_mod.EXIT_ERROR,
        )


class LiveEvidenceFaultTest(unittest.TestCase):
    def test_terminating_driver_still_classifies(self):
        class ExplodingDriver(FakeTerminalDriver):
            def terminate(self, name: str) -> None:
                raise TerminalError("cannot die")

        driver = ExplodingDriver()
        name = "fault-session"
        with isolated_tmux_session(driver, name, "/tmp", ["fake"]):
            self.assertTrue(driver.session_alive(name))

    def test_capture_failure_after_start_blocks(self):
        class FlakyDriver(FakeTerminalDriver):
            def capture(self, name: str) -> str:
                raise TerminalError("pane unreadable")

        with mock.patch("shutil.which", return_value="/bin/fake"):
            result = scenario_opencode_lifecycle(
                timeout_s=1, driver_factory=FlakyDriver
            )
        self.assertEqual(result.status, BLOCKED)

    def test_provision_failure_blocks_named_scenario(self):
        from ariadex import tmux_setup
        from ariadex.tmux_setup import TmuxSetupError

        with (
            mock.patch.object(tmux_setup, "find_tmux", return_value=None),
            mock.patch.object(
                tmux_setup, "ensure_tmux", side_effect=TmuxSetupError("no sudo")
            ),
        ):
            results = run_all(only=["tmux-lifecycle"], provision=True, timeout_s=1)
        by_name = {r.name: r for r in results}
        self.assertEqual(by_name["tmux-lifecycle"].status, BLOCKED)

    def test_unprovision_warnings(self):
        from ariadex import live_evidence, tmux_setup

        self.assertEqual(live_evidence.unprovision_tmux(False), "")
        with mock.patch.object(
            tmux_setup, "uninstall_tmux", side_effect=RuntimeError("boom")
        ):
            note = live_evidence.unprovision_tmux(True)
        self.assertIn("could not be removed", note)
        with (
            mock.patch.object(tmux_setup, "uninstall_tmux", return_value="apt-get"),
            mock.patch.object(tmux_setup, "find_tmux", return_value="/usr/bin/tmux"),
        ):
            note = live_evidence.unprovision_tmux(True)
        self.assertIn("still on PATH", note)


class TerminalSuccessTest(unittest.TestCase):
    def test_create_send_terminate_round_trip(self):
        from ariadex.terminal import TmuxDriver

        driver = TmuxDriver(executable="/bin/tmux")
        with (
            mock.patch.object(driver, "session_alive", side_effect=[False, True, True]),
            mock.patch.object(terminal_mod.shutil, "which", return_value="/bin/tmux"),
            mock.patch.object(
                driver, "_run", return_value=completed(0, stdout="pane")
            ) as run_mock,
        ):
            self.assertEqual(driver.create_or_connect("s", "/tmp", ["x"]), "created")
            driver.send_input("s", "hi")
            self.assertEqual(driver.capture("s"), "pane")
        kinds = [call.args[0][0] for call in run_mock.call_args_list]
        self.assertIn("new-session", kinds)
        self.assertIn("capture-pane", kinds)

    def test_send_second_key_failure(self):
        from ariadex.terminal import TmuxDriver

        driver = TmuxDriver()
        with (
            mock.patch.object(driver, "session_alive", return_value=True),
            mock.patch.object(
                driver,
                "_run",
                side_effect=[completed(0), TerminalError("enter lost")],
            ),
            self.assertRaises(DeliveryFailed),
        ):
            driver.send_input("s", "hi")

    def test_run_success_returns_proc(self):
        from ariadex.terminal import TmuxDriver

        driver = TmuxDriver()
        proc = completed(0, stdout="ok")
        with mock.patch.object(terminal_mod.subprocess, "run", return_value=proc):
            self.assertIs(driver._run(["has-session"], "ctx"), proc)

    def test_fake_empty_command_rejected(self):
        with self.assertRaises(TerminalError):
            FakeTerminalDriver().create_or_connect("s", "/tmp", [])

    def test_terminate_kills_live_session(self):
        from ariadex.terminal import TmuxDriver

        driver = TmuxDriver()
        with (
            mock.patch.object(driver, "session_alive", return_value=True),
            mock.patch.object(driver, "_run", return_value=completed(0)) as run_mock,
        ):
            self.assertIsNone(driver.terminate("s"))
        self.assertEqual(run_mock.call_args.args[0][0], "kill-session")


class TmuxSetupAptSuccessTest(unittest.TestCase):
    def test_ensure_tmux_apt_success(self):
        with (
            mock.patch.object(
                setup_mod, "find_tmux", side_effect=[None, "/usr/bin/tmux"]
            ),
            mock.patch.object(setup_mod, "detect_manager", return_value="apt-get"),
            mock.patch.object(setup_mod, "needs_sudo", return_value=False),
            mock.patch.object(setup_mod.subprocess, "run", return_value=completed(0)),
        ):
            self.assertEqual(setup_mod.ensure_tmux(), "/usr/bin/tmux")

    def test_ensure_tmux_apt_update_sudo_variant(self):
        seen = []

        def fake_run(cmd, **kwargs):
            seen.append(list(cmd))
            return completed(0)

        with (
            mock.patch.object(
                setup_mod, "find_tmux", side_effect=[None, "/usr/bin/tmux"]
            ),
            mock.patch.object(setup_mod, "detect_manager", return_value="apt-get"),
            mock.patch.object(setup_mod, "needs_sudo", return_value=True),
            mock.patch.object(setup_mod.shutil, "which", return_value="/usr/bin/sudo"),
            mock.patch.object(setup_mod.subprocess, "run", side_effect=fake_run),
        ):
            self.assertEqual(setup_mod.ensure_tmux(), "/usr/bin/tmux")
        self.assertTrue(any(c[:3] == ["sudo", "-n", "apt-get"] for c in seen))

    def test_remove_command_sudo_variant(self):
        with (
            mock.patch.object(setup_mod, "needs_sudo", return_value=True),
            mock.patch.object(setup_mod.shutil, "which", return_value="/usr/bin/sudo"),
        ):
            cmd = setup_mod.remove_command("apt-get")
        self.assertEqual(cmd[:2], ["sudo", "-n"])
        self.assertIn("tmux", cmd)

    def test_fetch_local_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl_dir = Path(tmp) / "debs"
            root = Path(tmp) / "root"

            def fake_run(cmd, **kwargs):
                if len(cmd) > 1 and cmd[1] == "download":
                    (dl_dir / "tmux_3.4-1_amd64.deb").write_text("fake-deb")
                if cmd[0] == "dpkg-deb":
                    target = root / "usr" / "bin"
                    target.mkdir(parents=True, exist_ok=True)
                    (target / "tmux").write_text("fake-tmux")
                return completed(0, stdout="")

            with (
                mock.patch.object(
                    setup_mod.shutil, "which", return_value="/usr/bin/apt-get"
                ),
                mock.patch.object(setup_mod, "read_depends", return_value=[]),
                mock.patch.object(setup_mod.subprocess, "run", side_effect=fake_run),
                mock.patch.object(setup_mod, "missing_shared_libs", return_value=[]),
            ):
                wrapper = setup_mod.fetch_local_tmux(tmp)
            self.assertTrue(wrapper.is_file())
            self.assertTrue(os.access(wrapper, os.X_OK))


class RunnerSelectTest(unittest.TestCase):
    def test_eligible_specs_fallback_branches(self):
        from ariadex import runner as runner_mod

        graph = {"b": ["a"], "a": []}
        self.assertEqual(
            runner_mod.eligible_specs_fallback(graph, {"a", "b"}, set()), "a"
        )
        self.assertEqual(runner_mod.eligible_specs_fallback(graph, {"x"}, set()), "x")
        cyclic = {"a": ["b"], "b": ["a"]}
        self.assertEqual(
            runner_mod.eligible_specs_fallback(cyclic, {"a", "b"}, set()), "a"
        )

    def test_select_context_strategy(self):
        from types import SimpleNamespace

        from ariadex import runner as runner_mod
        from ariadex.adapters import AdapterError

        cfg = SimpleNamespace(context_strategy="per-spec")
        self.assertEqual(runner_mod.select_context_strategy(cfg), "per-spec")
        bad = SimpleNamespace(context_strategy="bogus")
        with self.assertRaises(AdapterError):
            runner_mod.select_context_strategy(bad)


class EvidenceMainTest(unittest.TestCase):
    def _run_main(self, argv, results):
        import io
        from contextlib import redirect_stdout

        from ariadex import live_evidence as evidence_mod

        with (
            mock.patch.object(
                evidence_mod, "run_all", return_value=results
            ) as run_mock,
            redirect_stdout(io.StringIO()) as out,
        ):
            code = evidence_mod.main(argv)
        return code, run_mock, out.getvalue()

    def test_main_gate_and_report(self):
        from ariadex.live_evidence import EvidenceResult

        ok = [EvidenceResult("a", "passed", "fine")]
        code, _, report = self._run_main([], ok)
        self.assertEqual(code, 0)
        self.assertIn("1 passed", report)
        code, _, _ = self._run_main(["--gate"], ok)
        self.assertEqual(code, 0)
        mixed = [*ok, EvidenceResult("b", "skipped", "no tmux")]
        code, _, _ = self._run_main(["--gate"], mixed)
        self.assertEqual(code, 1)

    def test_main_parses_only_and_flags(self):
        from ariadex.live_evidence import EvidenceResult

        ok = [EvidenceResult("a", "passed", "fine")]
        code, run_mock, _ = self._run_main(
            [
                "--only",
                "a,b",
                "--timeout",
                "5",
                "--provision",
                "--tmux-bin",
                "/x/tmux",
                "--local-tmux",
            ],
            ok,
        )
        self.assertEqual(code, 0)
        _, kwargs = run_mock.call_args
        self.assertEqual(kwargs["only"], ["a", "b"])
        self.assertEqual(kwargs["timeout_s"], 5)
        self.assertTrue(kwargs["provision"])
        self.assertEqual(kwargs["tmux_bin"], "/x/tmux")
        self.assertTrue(kwargs["local_tmux"])

    def test_provision_tmux_found_and_report_blocked(self):
        from ariadex import live_evidence as evidence_mod
        from ariadex import tmux_setup

        with mock.patch.object(tmux_setup, "find_tmux", return_value="/usr/bin/tmux"):
            self.assertEqual(evidence_mod.provision_tmux(), ("/usr/bin/tmux", ""))
        from ariadex.live_evidence import EvidenceResult, format_report

        blocked = EvidenceResult("x", "blocked", "why", diagnostics="traceback!")
        report = format_report([blocked])
        self.assertIn("diagnostics:", report)
        self.assertIn("0 passed, 0 skipped, 1 blocked", report)


if __name__ == "__main__":
    unittest.main()
