"""Tests for real-provider lifecycle evidence.

Scripted drivers stand in for tmux plus the real CLI so classification,
gate handling, redaction bounds, and cleanup are deterministic. No LLM
API, network, or provider binary is touched here; live runs happen only
through `ariadex evidence --only opencode-lifecycle,codex-lifecycle`.
"""

import unittest
from unittest import mock

from ariadex.live_evidence import (
    BLOCKED,
    PASSED,
    SKIPPED,
    gate_exit_code,
    scenario_codex_lifecycle,
    scenario_opencode_lifecycle,
)
from ariadex.terminal import FakeTerminalDriver, SessionMissing

OPENCODE_READY = "opencode banner\nAsk anything...  tab agents ctrl+p commands"
CODEX_READY = "OpenAI Codex (v0.153.4)\nmodel: test\nAsk Codex to do anything"


class ScriptedDriver(FakeTerminalDriver):
    """Fake driver replaying queued captures, repeating the last one."""

    def __init__(self, captures: list[str]):
        super().__init__()
        self._queue = list(captures)
        self._last = captures[-1] if captures else ""

    def capture(self, name: str) -> str:
        self._check_binary()
        if name not in self.sessions:
            raise SessionMissing(f"tmux session `{name}` does not exist (fake)")
        self.calls.append(("capture", name))
        if self._queue:
            self._last = self._queue.pop(0)
        return self._last


def run_opencode(captures: list[str], **mocks):
    factory = lambda: ScriptedDriver(captures)  # noqa: E731
    with mock.patch("shutil.which", return_value="/bin/fake"):
        return scenario_opencode_lifecycle(timeout_s=2, driver_factory=factory, **mocks)


def run_codex(captures: list[str], **mocks):
    factory = lambda: ScriptedDriver(captures)  # noqa: E731
    with mock.patch("shutil.which", return_value="/bin/fake"):
        return scenario_codex_lifecycle(timeout_s=2, driver_factory=factory, **mocks)


class PrerequisiteTest(unittest.TestCase):
    def test_missing_tmux_skips(self):
        with mock.patch("shutil.which", return_value=None):
            result = scenario_opencode_lifecycle(timeout_s=1)
        self.assertEqual(result.status, SKIPPED)
        self.assertIn("tmux", result.reason)

    def test_missing_provider_binary_skips(self):
        def which(name):
            return "/usr/bin/tmux" if name == "tmux" else None

        with mock.patch("shutil.which", side_effect=which):
            result = scenario_codex_lifecycle(timeout_s=1)
        self.assertEqual(result.status, SKIPPED)
        self.assertIn("codex", result.reason)
        self.assertIn("PATH", result.reason + result.diagnostics)

    def test_explicit_bad_tmux_blocks(self):
        result = scenario_opencode_lifecycle(timeout_s=1, executable="/no/tmux")
        self.assertEqual(result.status, BLOCKED)


class OpenCodeLifecycleTest(unittest.TestCase):
    def test_full_lifecycle_passes(self):
        captures = [
            OPENCODE_READY,
            OPENCODE_READY + "\n/help",
            OPENCODE_READY,
            OPENCODE_READY,
        ]
        result = run_opencode(captures)
        self.assertEqual(result.status, PASSED)
        self.assertIn("soft reset", result.reason)

    def test_help_overlay_counts_as_probe_response(self):
        overlay = (
            "Help   esc/enter\nPress ctrl+p to see all available actions\n"
            "Ask  ok  Build"
        )
        result = run_opencode([OPENCODE_READY, overlay, OPENCODE_READY, OPENCODE_READY])
        self.assertEqual(result.status, PASSED)

    def test_startup_failure_blocks(self):
        driver = ScriptedDriver([OPENCODE_READY])
        driver.missing_binary = True
        with mock.patch("shutil.which", return_value="/bin/fake"):
            result = scenario_opencode_lifecycle(
                timeout_s=1, driver_factory=lambda: driver
            )
        self.assertEqual(result.status, BLOCKED)

    def test_missing_ready_prompt_blocks_with_rerun(self):
        result = run_opencode(["blank pane"] * 20)
        self.assertEqual(result.status, BLOCKED)
        self.assertIn("--only opencode-lifecycle", result.reason)

    def test_auth_refusal_skips(self):
        result = run_opencode(["please log in to continue"])
        self.assertEqual(result.status, SKIPPED)
        self.assertIn("--only opencode-lifecycle", result.reason)

    def test_gate_never_passes_on_skip(self):
        result = run_opencode(["please log in to continue"])
        self.assertNotEqual(gate_exit_code([result]), 0)


class CodexLifecycleTest(unittest.TestCase):
    def test_gates_answered_then_passes(self):
        captures = [
            "Update available! 0.153.4 -> 0.154.0\n1. Update now\n2. Skip",
            "Do you trust the contents of this directory?\n1. Yes, continue",
            CODEX_READY,
            CODEX_READY + "\n/help",
            CODEX_READY,
            CODEX_READY,
        ]
        seen: dict[str, ScriptedDriver] = {}

        def factory():
            driver = ScriptedDriver(captures)
            seen["driver"] = driver
            return driver

        with mock.patch("shutil.which", return_value="/bin/fake"):
            result = scenario_codex_lifecycle(timeout_s=2, driver_factory=factory)
        self.assertEqual(result.status, PASSED)
        self.assertIn("hard reset", result.reason)
        sent = seen["driver"].sent_inputs(seen["driver"].calls[0][1])
        self.assertIn("2", sent)
        self.assertIn("1", sent)

    def test_missing_ready_prompt_blocks(self):
        result = run_codex(["blank pane"] * 20)
        self.assertEqual(result.status, BLOCKED)


class RedactionTest(unittest.TestCase):
    def test_secret_redacted_and_bounded(self):
        secret = "ghp_" + "s3cr3t" * 10
        pane = "pane output " + secret + " " + ("x" * 5000)
        result = run_opencode([pane] * 20)
        self.assertEqual(result.status, BLOCKED)
        self.assertNotIn(secret, result.diagnostics)
        self.assertLessEqual(len(result.diagnostics), 2200)
        self.assertIn("redactions:", result.diagnostics)


class ProvisionSelectionTest(unittest.TestCase):
    def test_local_tmux_failure_blocks_selected_backed_scenario(self):
        from ariadex import tmux_setup
        from ariadex.live_evidence import run_all

        with mock.patch.object(
            tmux_setup,
            "fetch_local_tmux",
            side_effect=tmux_setup.TmuxSetupError("no network"),
        ):
            results = run_all(only=["opencode-lifecycle"], local_tmux=True, timeout_s=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "opencode-lifecycle")
        self.assertEqual(results[0].status, BLOCKED)

    def test_local_tmux_not_fetched_without_backed_selection(self):
        from ariadex import tmux_setup
        from ariadex.live_evidence import run_all

        with mock.patch.object(
            tmux_setup,
            "fetch_local_tmux",
            side_effect=AssertionError("must not fetch"),
        ):
            results = run_all(only=["provider-smoke"], timeout_s=1)
        self.assertTrue(all(r.name == "provider-smoke" for r in results))


class CleanupTest(unittest.TestCase):
    def test_failed_startup_leaves_no_session(self):
        drivers: list[ScriptedDriver] = []

        def factory():
            driver = ScriptedDriver([])
            driver.missing_binary = True
            drivers.append(driver)
            return driver

        with mock.patch("shutil.which", return_value="/bin/fake"):
            result = scenario_opencode_lifecycle(timeout_s=1, driver_factory=factory)
        self.assertEqual(result.status, BLOCKED)
        self.assertEqual(drivers[0].sessions, {})


if __name__ == "__main__":
    unittest.main()
