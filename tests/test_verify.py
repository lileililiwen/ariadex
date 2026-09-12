"""Tests for shell verification gates."""

import tempfile
import unittest
from pathlib import Path

from ariadex.verify import (
    ShellVerifier,
    UnavailableVerifier,
    run_command,
    run_commands,
)


class RunCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_passing_command_captures_exit_and_output(self):
        result = run_command("echo hello", self.root)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("hello", result.output)
        self.assertFalse(result.timed_out)
        self.assertGreaterEqual(result.duration_s, 0)

    def test_failing_command_reports_exit_code(self):
        result = run_command("exit 3", self.root)
        self.assertEqual(result.exit_code, 3)
        self.assertFalse(result.timed_out)

    def test_timeout_is_a_failure(self):
        result = run_command("sleep 30", self.root, timeout_s=1)
        self.assertTrue(result.timed_out)
        self.assertIsNone(result.exit_code)
        self.assertIn("timed out", result.output)

    def test_output_is_bounded(self):
        result = run_command("seq 1 100000", self.root)
        self.assertLessEqual(len(result.output), 20000 + 200)
        self.assertIn("truncated", result.output)


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_all_pass_opens_the_gate(self):
        outcome = run_commands(["true", "echo ok"], self.root)
        self.assertTrue(outcome.passed)
        self.assertEqual(outcome.exit_code, 0)
        self.assertEqual(len(outcome.results), 2)

    def test_one_failure_closes_the_gate(self):
        outcome = run_commands(["true", "exit 2"], self.root)
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.exit_code, 2)
        self.assertIn("exit 2", outcome.detail)

    def test_empty_command_list_passes_vacuously(self):
        outcome = run_commands([], self.root)
        self.assertTrue(outcome.passed)

    def test_shell_verifier_reports_through(self):
        verifier = ShellVerifier(["exit 1"], self.root)
        verdict = verifier.verify("do work", "agent output")
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.exit_code, 1)

    def test_shell_verifier_without_commands_is_unavailable(self):
        verdict = ShellVerifier([], self.root).verify("do work", "out")
        self.assertFalse(verdict.passed)
        self.assertIsNone(verdict.exit_code)

    def test_unavailable_verifier_never_passes(self):
        verdict = UnavailableVerifier().verify("do work", "out")
        self.assertFalse(verdict.passed)


if __name__ == "__main__":
    unittest.main()
