"""Portable terminal transport: pty relay daemon and PtyDriver.

Covers the full session lifecycle without tmux, cross-process reconnect,
stale-registry refusal, backend selection, and protocol bounds. Unix-only:
the pty backend requires the stdlib `pty` module.
"""

import hashlib
import json
import socket
import tempfile
import time
import unittest
from contextlib import suppress
from pathlib import Path
from unittest import mock

from ariadex import terminal as terminal_mod

try:
    import pty as _pty_check  # noqa: F401

    HAVE_PTY = True
except ImportError:
    HAVE_PTY = False


def make_project(state: list) -> Path:
    tmp = tempfile.TemporaryDirectory()
    state.append(tmp)
    return Path(tmp.name)


@unittest.skipUnless(HAVE_PTY, "pty backend requires Unix")
class PtyLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])
        self.project = make_project(self._tmp)
        self.driver = terminal_mod.PtyDriver(self.project)

    def tearDown(self) -> None:
        for name in ("s1", "s2"):
            with suppress(Exception):
                self.driver.terminate(name)

    def test_create_send_capture_terminate_without_tmux(self) -> None:
        with mock.patch.object(terminal_mod.shutil, "which", return_value=None):
            self.assertEqual(
                self.driver.create_or_connect("s1", self.project, ["cat"]),
                "created",
            )
        self.assertTrue(self.driver.session_alive("s1"))
        self.assertEqual(
            self.driver.create_or_connect("s1", self.project, ["cat"]),
            "connected",
        )
        self.driver.send_input("s1", "hello-pty")
        deadline = time.monotonic() + 10.0
        captured = ""
        while time.monotonic() < deadline:
            captured = self.driver.capture("s1")
            if "hello-pty" in captured:
                break
            time.sleep(0.2)
        self.assertIn("hello-pty", captured)
        pid = self.driver.session_pid("s1")
        self.assertIsInstance(pid, int)
        self.assertEqual(self.driver.list_sessions(), ["s1"])
        self.driver.interrupt("s1")
        self.driver.terminate("s1")
        self.assertFalse(self.driver.session_alive("s1"))
        self.assertEqual(self.driver.list_sessions(), [])
        self.driver.terminate("s1")  # idempotent

    def test_cross_process_reconnect(self) -> None:
        self.driver.create_or_connect("s1", self.project, ["cat"])
        other = terminal_mod.PtyDriver(self.project)
        try:
            self.assertEqual(
                other.create_or_connect("s1", self.project, ["cat"]),
                "connected",
            )
            other.send_input("s1", "second-writer")
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                if "second-writer" in self.driver.capture("s1"):
                    break
                time.sleep(0.2)
            self.assertIn("second-writer", self.driver.capture("s1"))
        finally:
            other.terminate("s1")

    def test_dead_child_reports_not_alive(self) -> None:
        self.driver.create_or_connect("s1", self.project, ["true"])
        time.sleep(0.5)
        self.assertFalse(self.driver.session_alive("s1"))
        self.driver.terminate("s1")

    def test_stale_registry_is_replaced(self) -> None:
        base = self.project / ".ariadex" / "pty"
        base.mkdir(parents=True, exist_ok=True)
        record = {
            "name": "s1",
            "socket": str(base / "dead.sock"),
            "log": str(base / "dead.log"),
            "relay_pid": 999999999,
            "relay_start": 1.0,
            "command": ["cat"],
        }
        digest = hashlib.sha256(b"s1").hexdigest()[:16]
        (base / f"relay-{digest}.json").write_text(json.dumps(record), encoding="utf-8")
        self.assertFalse(self.driver.session_alive("s1"))
        self.assertEqual(
            self.driver.create_or_connect("s1", self.project, ["cat"]),
            "created",
        )
        self.assertTrue(self.driver.session_alive("s1"))

    def test_invalid_name_refused(self) -> None:
        with self.assertRaises(terminal_mod.TerminalError):
            self.driver.create_or_connect("../evil", self.project, ["cat"])
        self.assertFalse(self.driver.session_alive("../evil"))

    def test_unknown_session_reports_missing(self) -> None:
        with self.assertRaises(terminal_mod.SessionMissing):
            self.driver.send_input("nope", "hi")
        with self.assertRaises(terminal_mod.SessionMissing):
            self.driver.capture("nope")
        with self.assertRaises(terminal_mod.SessionMissing):
            self.driver.attach_command("nope")

    def test_attach_observes_session_log(self) -> None:
        self.driver.create_or_connect("s1", self.project, ["cat"])
        argv = self.driver.attach_command("s1")
        self.assertEqual(argv[0], "tail")
        self.assertIn(".log", argv[-1])

    def test_malformed_request_keeps_relay_serving(self) -> None:
        self.driver.create_or_connect("s1", self.project, ["cat"])
        paths = self.driver._paths("s1")
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.settimeout(5.0)
            client.connect(str(paths["socket"]))
            client.sendall(b"not json\n")
            data = b""
            while b"\n" not in data:
                data += client.recv(4096)
            reply = json.loads(data.decode("utf-8"))
            self.assertFalse(reply["ok"])
        finally:
            client.close()
        self.assertTrue(self.driver.session_alive("s1"))


class DriverSelectionTest(unittest.TestCase):
    def test_make_driver_selects_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsInstance(
                terminal_mod.make_driver("pty", tmp), terminal_mod.PtyDriver
            )
            self.assertIsInstance(
                terminal_mod.make_driver("tmux", tmp), terminal_mod.TmuxDriver
            )
            with self.assertRaises(terminal_mod.TerminalError):
                terminal_mod.make_driver("wat", tmp)

    def test_pty_accepted_in_supported_drivers(self) -> None:
        from ariadex import config as config_mod

        self.assertIn("pty", config_mod.SUPPORTED_TERMINAL_DRIVERS)


@unittest.skipUnless(HAVE_PTY, "pty backend requires Unix")
class ProvisioningTest(unittest.TestCase):
    def test_pty_skips_tmux_provisioning(self) -> None:
        from ariadex import cli as cli_mod

        with tempfile.TemporaryDirectory() as tmp:
            cfg = mock.Mock()
            cfg.terminal_driver = "pty"
            with mock.patch.object(
                cli_mod.tmux_setup_mod,
                "ensure_tmux",
                side_effect=AssertionError("tmux must not be provisioned"),
            ):
                driver = cli_mod._provisioned_driver(Path(tmp), cfg)
            self.assertIsInstance(driver, terminal_mod.PtyDriver)


class PtyPrerequisiteTest(unittest.TestCase):
    def test_check_pty_reports_presence(self) -> None:
        from ariadex import prerequisites as prerequisites_mod

        result = prerequisites_mod.check_pty()
        if HAVE_PTY:
            self.assertTrue(result.ready)
            self.assertEqual(result.name, "pty")
        else:
            self.assertFalse(result.ready)


if __name__ == "__main__":
    unittest.main()
