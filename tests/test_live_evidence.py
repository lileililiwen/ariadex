"""Tests for the opt-in live evidence harness.

All live-tmux paths are skipped-or-blocked when tmux is absent; the
install fixture is fully mocked so no host package manager ever runs.
"""

import io
import os
import stat
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ariadex import cli, live_evidence
from ariadex.live_evidence import (
    BLOCKED,
    PASSED,
    SKIPPED,
    format_report,
    gate_exit_code,
    isolated_tmux_session,
    run_all,
    scenario_install_fixture,
    scenario_provider_smoke,
    scenario_tmux_lifecycle,
    temp_project,
    unique_session_name,
    write_fake_provider,
)


class FixtureTest(unittest.TestCase):
    def test_session_names_unique(self):
        self.assertNotEqual(unique_session_name(), unique_session_name())

    def test_temp_project_cleanup_on_failure(self):
        captured = []
        try:
            with temp_project() as root:
                captured.append(str(root))
                self.assertTrue((root / ".ariadex").is_dir())
                raise RuntimeError("probe failure")
        except RuntimeError:
            pass
        self.assertFalse(Path(captured[0]).exists())

    def test_fake_provider_executable_and_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = write_fake_provider(tmp)
            self.assertTrue(os.access(fake, os.X_OK))
            text = fake.read_text(encoding="utf-8")
            self.assertIn("fake-echo", text)
            self.assertNotIn("http", text.lower())

    def test_isolated_session_always_terminates(self):
        from ariadex.terminal import FakeTerminalDriver

        driver = FakeTerminalDriver()
        name = unique_session_name("cleanup")
        with self.assertRaises(RuntimeError):
            with isolated_tmux_session(driver, name, "/tmp", ["fake"]):
                self.assertTrue(driver.session_alive(name))
                raise RuntimeError("boom")
        self.assertFalse(driver.session_alive(name))


class ClassificationTest(unittest.TestCase):
    def test_tmux_missing_is_skipped_with_prerequisite(self):
        with mock.patch("shutil.which", return_value=None):
            result = scenario_tmux_lifecycle(timeout_s=1)
        self.assertEqual(result.status, SKIPPED)
        self.assertIn("tmux", result.reason)
        self.assertIn("PATH", result.reason + result.diagnostics)

    def test_gate_requires_all_passed(self):
        ok = [live_evidence.EvidenceResult("a", PASSED, "fine")]
        mixed = ok + [live_evidence.EvidenceResult("b", SKIPPED, "no tmux")]
        self.assertEqual(gate_exit_code(ok), 0)
        self.assertNotEqual(gate_exit_code(mixed), 0)

    def test_report_never_calls_skipped_passing(self):
        results = [
            live_evidence.EvidenceResult("a", PASSED, "fine"),
            live_evidence.EvidenceResult("b", SKIPPED, "no tmux"),
        ]
        report = format_report(results)
        self.assertIn("1 passed, 1 skipped, 0 blocked", report)
        self.assertIn("not passing evidence", report)

    def test_run_all_classifies_harness_errors(self):
        with mock.patch.object(
            live_evidence, "SCENARIOS",
            [("boom", lambda **_: (_ for _ in ()).throw(RuntimeError("x")))],
        ):
            results = run_all()
        self.assertEqual(results[0].status, BLOCKED)

    def test_provider_smoke_skips_without_binaries(self):
        with mock.patch("shutil.which", return_value=None):
            result = scenario_provider_smoke(timeout_s=1)
        self.assertEqual(result.status, SKIPPED)


class ScenarioTest(unittest.TestCase):
    def test_provider_startup_passes_on_fake_driver(self):
        result = live_evidence.scenario_provider_startup()
        self.assertEqual(result.status, PASSED)

    def test_continuity_restart_passes(self):
        result = live_evidence.scenario_continuity_restart()
        self.assertEqual(result.status, PASSED)

    def test_verification_gating_passes(self):
        result = live_evidence.scenario_verification_gating()
        self.assertEqual(result.status, PASSED)

    def test_takeover_resync_passes(self):
        result = live_evidence.scenario_takeover_resync()
        self.assertEqual(result.status, PASSED)

    def test_install_fixture_never_touches_host(self):
        with mock.patch("subprocess.run") as run:
            result = scenario_install_fixture()
            run.assert_not_called()  # module patches its own subprocess ref
        self.assertEqual(result.status, PASSED)


def run_cli(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with chdir(root), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


class EvidenceCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        run_cli(self.root, "init")

    def test_evidence_reports_without_scheduling(self):
        code, out, _ = run_cli(self.root, "evidence", "--only",
                               "provider-startup,takeover-resync")
        self.assertEqual(code, 0)
        self.assertIn("provider-startup: passed", out)
        self.assertIn("takeover-resync: passed", out)
        self.assertIn("summary:", out)

    def test_evidence_gate_fails_on_skipped_tmux(self):
        with mock.patch("shutil.which", return_value=None):
            code, out, _ = run_cli(self.root, "evidence", "--gate", "--only",
                                   "tmux-lifecycle")
        self.assertNotEqual(code, 0)
        self.assertIn("skipped", out)

    def test_other_commands_still_work(self):
        code, _, _ = run_cli(self.root, "status")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
