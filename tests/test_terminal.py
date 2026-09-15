"""Tests for the terminal driver contract and tmux implementation."""

import unittest
from unittest import mock

from ariadex.terminal import (
    DeliveryFailed,
    FakeTerminalDriver,
    SessionMissing,
    TerminalError,
    TmuxDriver,
    TmuxNotAvailable,
    session_name_for,
)


class FakeDriverTest(unittest.TestCase):
    def setUp(self):
        self.driver = FakeTerminalDriver()

    def test_create_then_connect(self):
        self.assertEqual(
            self.driver.create_or_connect("s", "/tmp", ["opencode"]), "created"
        )
        self.assertEqual(
            self.driver.create_or_connect("s", "/tmp", ["opencode"]), "connected"
        )

    def test_send_and_capture_round_trip(self):
        self.driver.create_or_connect("s", "/tmp", ["codex"])
        self.driver.send_input("s", "hello")
        self.assertEqual(self.driver.capture("s"), "hello\n")

    def test_send_keys_round_trip(self):
        self.driver.create_or_connect("s", "/tmp", ["codex"])
        self.driver.send_keys("s", ["Enter"])
        self.assertEqual(self.driver.sent_key_sequences("s"), [["Enter"]])
        self.assertEqual(self.driver.sent_inputs("s"), [])
        with self.assertRaises(SessionMissing):
            self.driver.send_keys("ghost", ["Enter"])

    def test_send_keys_delivery_failure_is_typed(self):
        self.driver.create_or_connect("s", "/tmp", ["opencode"])
        self.driver.fail_delivery = True
        with self.assertRaises(DeliveryFailed):
            self.driver.send_keys("s", ["Enter"])

    def test_operations_on_missing_session_fail_typed(self):
        with self.assertRaises(SessionMissing):
            self.driver.send_input("ghost", "hi")
        with self.assertRaises(SessionMissing):
            self.driver.capture("ghost")
        with self.assertRaises(SessionMissing):
            self.driver.interrupt("ghost")

    def test_terminate_is_idempotent(self):
        self.driver.terminate("ghost")
        self.driver.create_or_connect("s", "/tmp", ["opencode"])
        self.driver.terminate("s")
        self.driver.terminate("s")

    def test_delivery_failure_is_typed(self):
        self.driver.create_or_connect("s", "/tmp", ["opencode"])
        self.driver.fail_delivery = True
        with self.assertRaises(DeliveryFailed):
            self.driver.send_input("s", "hi")

    def test_missing_binary_is_typed(self):
        self.driver.missing_binary = True
        with self.assertRaises(TmuxNotAvailable):
            self.driver.session_alive("s")
        with self.assertRaises(TmuxNotAvailable):
            self.driver.create_or_connect("s", "/tmp", ["opencode"])

    def test_attach_command_shape(self):
        self.assertEqual(
            self.driver.attach_command("ariadex-abc"),
            ["tmux", "attach-session", "-t", "ariadex-abc"],
        )


class TmuxDriverUnitTest(unittest.TestCase):
    def test_missing_binary_reports_prerequisite(self):
        driver = TmuxDriver(executable="ariadex-missing-tmux-binary")
        with self.assertRaises(TmuxNotAvailable) as ctx:
            driver.session_alive("any")
        self.assertIn("ariadex-missing-tmux-binary", str(ctx.exception))

    def test_create_reports_missing_binary_before_sending_work(self):
        driver = TmuxDriver(executable="ariadex-missing-tmux-binary")
        with self.assertRaises(TmuxNotAvailable):
            driver.create_or_connect("any", "/tmp", ["opencode"])

    def test_attach_command_shape(self):
        self.assertEqual(
            TmuxDriver().attach_command("ariadex-abc"),
            ["tmux", "attach-session", "-t", "ariadex-abc"],
        )

    def test_session_name_mapping(self):
        self.assertEqual(session_name_for("abc123"), "ariadex-abc123")

    def test_send_keys_rejects_unknown_key_names(self):
        driver = TmuxDriver(executable="tmux")
        with mock.patch.object(driver, "_require_alive", return_value=None):
            with self.assertRaises(TerminalError):
                driver.send_keys("s", ["F13"])
            with self.assertRaises(TerminalError):
                driver.send_keys("s", [])

    def test_send_keys_uses_named_tmux_keys(self):
        driver = TmuxDriver(executable="tmux")
        seen: list[list[str]] = []
        with (
            mock.patch.object(driver, "_require_alive", return_value=None),
            mock.patch.object(
                driver, "_run", side_effect=lambda args, ctx: seen.append(args)
            ),
        ):
            driver.send_keys("s", ["Down", "Enter"])
        self.assertEqual(
            seen,
            [
                ["send-keys", "-t", "s", "Down"],
                ["send-keys", "-t", "s", "Enter"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
