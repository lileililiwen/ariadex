"""Tests for the AgentAdapter lifecycle contract and reset selection."""

import unittest
from pathlib import Path
from unittest import mock

from ariadex import provider_runtime, providers
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
        self.assertEqual(
            driver.sessions["test-session"]["command"],
            ["opencode", "--port", str(adapter.api_port)],
        )

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

    def test_start_attaches_to_surviving_owned_backend_after_ui_exit(self):
        adapter, driver = make_open_code()
        record = provider_runtime.ProviderRuntimeRecord(
            provider="opencode",
            project=str(Path("/tmp").resolve()),
            session_id="test-session",
            tmux_session="test-session",
            endpoint=f"http://127.0.0.1:{adapter.api_port}/session/status",
            port=adapter.api_port,
            pid=1234,
            process_start_ticks=5678,
            generation="generation-1",
        )
        with (
            mock.patch.object(provider_runtime, "read_record", return_value=record),
            mock.patch.object(provider_runtime, "is_reusable", return_value=True),
        ):
            self.assertEqual(adapter.start(), "created")
        self.assertEqual(
            driver.sessions["test-session"]["command"],
            ["opencode", "attach", f"http://127.0.0.1:{adapter.api_port}"],
        )

    def test_start_refuses_responsive_unknown_backend(self):
        adapter, driver = make_open_code()
        with (
            mock.patch.object(
                providers.provider_runtime, "read_record", return_value=None
            ),
            mock.patch.object(
                providers.provider_runtime, "find_process", return_value=None
            ),
            mock.patch.object(
                providers.provider_runtime,
                "endpoint_is_responsive",
                return_value=True,
            ),
            self.assertRaises(StartupError) as raised,
        ):
            adapter.start()
        self.assertIn("ownership conflict", str(raised.exception))
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


class NewConversationTest(unittest.TestCase):
    def test_opencode_uses_soft_path_without_terminate(self):
        adapter, driver = make_open_code()
        adapter.start()
        calls_before = len(driver.calls)
        adapter.new_conversation()
        self.assertIn(("send_input", "test-session", "/new"), driver.calls)
        ops = [op for op, *_ in driver.calls[calls_before:]]
        self.assertNotIn("terminate", ops)

    def test_codex_uses_hard_restart_in_same_session(self):
        driver = FakeTerminalDriver()
        adapter = providers.CodexAdapter(driver, "codex-session", "/tmp")
        adapter.start()
        driver.sessions["codex-session"]["output"] = "stale"
        adapter.new_conversation()
        ops = [op for op, *_ in driver.calls]
        self.assertIn("terminate", ops)
        self.assertIn("create_or_connect", ops)
        self.assertIn("codex-session", driver.sessions)
        self.assertEqual(driver.sessions["codex-session"]["command"], ["codex"])

    def test_codebuddy_uses_hard_restart_in_same_session(self):
        driver = FakeTerminalDriver()
        adapter = providers.CodeBuddyAdapter(driver, "buddy-session", "/tmp")
        adapter.start()
        adapter.new_conversation()
        self.assertIn("buddy-session", driver.sessions)
        self.assertEqual(driver.sessions["buddy-session"]["command"], ["codebuddy"])

    def test_every_supported_provider_declares_automatic_continuation(self):
        for provider in ("opencode", "codex", "codebuddy"):
            adapter = providers.get_adapter(provider, FakeTerminalDriver(), "s", "/tmp")
            self.assertTrue(
                adapter.auto_continuation_available,
                f"{provider} must declare automatic continuation",
            )

    def test_no_reset_capability_reports_unavailable(self):
        from ariadex.adapters import AgentAdapter, Capabilities

        class NoReset(AgentAdapter):
            provider_name = "noreset"
            launch_command = ("noreset",)

            @property
            def capabilities(self):
                return Capabilities(soft_reset=False, hard_reset=False, interrupt=False)

        adapter = NoReset(FakeTerminalDriver(), "s", "/tmp")
        self.assertFalse(adapter.auto_continuation_available)
        with self.assertRaises(UnsupportedOperation):
            adapter.new_conversation()

    def test_failed_restart_propagates_typed_error(self):
        class BrokenDriver(FakeTerminalDriver):
            def terminate(self, name):
                raise SessionMissing("boom")

        adapter = providers.CodexAdapter(BrokenDriver(), "s", "/tmp")
        from ariadex.adapters import AdapterError

        with self.assertRaises(AdapterError):
            adapter.new_conversation()

    def test_failed_start_propagates_typed_error(self):
        driver = FakeTerminalDriver()
        driver.missing_binary = True
        adapter = providers.CodexAdapter(driver, "s", "/tmp")
        from ariadex.adapters import AdapterError

        with self.assertRaises(AdapterError):
            adapter.new_conversation()


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
