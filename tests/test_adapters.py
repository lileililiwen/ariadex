"""Tests for the AgentAdapter lifecycle contract and reset selection."""

import unittest

from ariadex import providers
from ariadex.adapters import (
    AdapterError,
    Capabilities,
    CaptureError,
    StartupError,
    TerminationError,
    TransportError,
    UnsupportedOperation,
    select_reset,
)
from ariadex.terminal import FakeTerminalDriver, SessionMissing, TmuxNotAvailable


def make_open_code(driver=None):
    driver = driver or FakeTerminalDriver()
    return providers.OpenCodeAdapter(driver, "test-session", "/tmp"), driver


class LifecycleTest(unittest.TestCase):
    def test_start_creates_session_with_launch_command(self):
        adapter, driver = make_open_code()
        self.assertEqual(adapter.start(), "created")
        self.assertEqual(driver.sessions["test-session"]["command"], ["opencode"])

    def test_start_connects_when_session_alive(self):
        adapter, _driver = make_open_code()
        adapter.start()
        self.assertEqual(adapter.start(), "connected")

    def test_send_delivers_text(self):
        adapter, driver = make_open_code()
        adapter.start()
        adapter.send("hello agent")
        self.assertIn(("send_input", "test-session", "hello agent"), driver.calls)

    def test_interrupt_supported(self):
        adapter, driver = make_open_code()
        adapter.start()
        adapter.interrupt()
        self.assertIn(("interrupt", "test-session"), driver.calls)

    def test_new_session_uses_provider_input(self):
        adapter, driver = make_open_code()
        adapter.start()
        adapter.new_session()
        self.assertIn(("send_input", "test-session", "/new"), driver.calls)

    def test_capture_preserves_raw_output(self):
        adapter, driver = make_open_code()
        adapter.start()
        driver.append_output("test-session", "\x1b[32mok\x1b[0m  done\n")
        self.assertEqual(adapter.capture_output(), "\x1b[32mok\x1b[0m  done\n")

    def test_is_idle_is_conservative(self):
        adapter, _ = make_open_code()
        self.assertFalse(adapter.is_idle())

    def test_terminate_removes_session(self):
        adapter, driver = make_open_code()
        adapter.start()
        adapter.terminate()
        self.assertNotIn("test-session", driver.sessions)


class FailureMappingTest(unittest.TestCase):
    def test_missing_tmux_maps_to_startup_error(self):
        driver = FakeTerminalDriver()
        driver.missing_binary = True
        adapter, _ = make_open_code(driver)
        with self.assertRaises(StartupError):
            adapter.start()

    def test_dead_session_maps_to_transport_error(self):
        adapter, driver = make_open_code()
        adapter.start()
        driver.kill_session("test-session")
        with self.assertRaises(TransportError):
            adapter.send("lost")

    def test_dead_session_maps_to_capture_error(self):
        adapter, driver = make_open_code()
        adapter.start()
        driver.kill_session("test-session")
        with self.assertRaises(CaptureError):
            adapter.capture_output()

    def test_failed_delivery_maps_to_transport_error(self):
        adapter, driver = make_open_code()
        adapter.start()
        driver.fail_delivery = True
        with self.assertRaises(TransportError):
            adapter.send("lost")

    def test_terminate_failure_maps_to_termination_error(self):
        class BrokenDriver(FakeTerminalDriver):
            def terminate(self, name):
                raise SessionMissing("boom")

        adapter = providers.OpenCodeAdapter(BrokenDriver(), "s", "/tmp")
        with self.assertRaises(TerminationError):
            adapter.terminate()

    def test_missing_tmux_is_typed(self):
        driver = FakeTerminalDriver()
        driver.missing_binary = True
        adapter, _ = make_open_code(driver)
        with self.assertRaises(AdapterError):
            adapter.start()
        try:
            adapter.start()
        except AdapterError as exc:
            self.assertIsInstance(exc.__cause__, TmuxNotAvailable)


class UnsupportedCapabilityTest(unittest.TestCase):
    def test_codex_cannot_soft_reset(self):
        driver = FakeTerminalDriver()
        adapter = providers.CodexAdapter(driver, "codex-session", "/tmp")
        adapter.start()
        with self.assertRaises(UnsupportedOperation) as ctx:
            adapter.new_session()
        self.assertIn("soft_reset", str(ctx.exception))

    def test_codex_hard_reset_path_works(self):
        driver = FakeTerminalDriver()
        adapter = providers.CodexAdapter(driver, "codex-session", "/tmp")
        adapter.start()
        adapter.terminate()
        self.assertEqual(adapter.start(), "created")

    def test_interrupt_without_capability_reports(self):
        class NoInterrupt(providers.OpenCodeAdapter):
            @property
            def capabilities(self):
                return Capabilities(interrupt=False)

        adapter = NoInterrupt(FakeTerminalDriver(), "s", "/tmp")
        with self.assertRaises(UnsupportedOperation):
            adapter.interrupt()

    def test_unknown_provider_reports_supported(self):
        with self.assertRaises(UnsupportedOperation) as ctx:
            providers.get_adapter("wat", FakeTerminalDriver(), "s", "/tmp")
        self.assertIn("wat", str(ctx.exception))
        self.assertIn("opencode", str(ctx.exception))

    def test_registry_matches_config_contract(self):
        from ariadex import config

        self.assertEqual(
            tuple(sorted(providers.supported_providers())),
            tuple(sorted(config.SUPPORTED_PROVIDERS)),
        )


class SelectResetTest(unittest.TestCase):
    def test_auto_prefers_soft_when_available(self):
        self.assertEqual(
            select_reset("auto", Capabilities(soft_reset=True, hard_reset=True)),
            "soft",
        )

    def test_auto_falls_back_to_hard_reset(self):
        # Proposal scenario: auto + soft_reset:false + hard_reset:true
        # -> the runner terminates and restarts the adapter session.
        self.assertEqual(
            select_reset("auto", Capabilities(soft_reset=False, hard_reset=True)),
            "hard",
        )

    def test_auto_with_no_reset_capability_fails(self):
        with self.assertRaises(UnsupportedOperation):
            select_reset("auto", Capabilities(soft_reset=False, hard_reset=False))

    def test_explicit_soft_without_capability_fails(self):
        with self.assertRaises(UnsupportedOperation):
            select_reset("soft", Capabilities(soft_reset=False, hard_reset=True))

    def test_opencode_selects_soft_codex_selects_hard(self):
        self.assertEqual(
            select_reset(
                "auto",
                providers.OpenCodeAdapter(
                    FakeTerminalDriver(), "s", "/tmp"
                ).capabilities,
            ),
            "soft",
        )
        self.assertEqual(
            select_reset(
                "auto",
                providers.CodexAdapter(FakeTerminalDriver(), "s", "/tmp").capabilities,
            ),
            "hard",
        )

    def test_usage_unavailable_by_default(self):
        for cls in (providers.OpenCodeAdapter, providers.CodexAdapter):
            caps = cls(FakeTerminalDriver(), "s", "/tmp").capabilities
            self.assertFalse(caps.token_usage)


if __name__ == "__main__":
    unittest.main()
