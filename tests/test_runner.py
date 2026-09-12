"""Tests for next-action selection, execution boundaries, and restarts."""

import tempfile
import unittest
from pathlib import Path

from ariadex import config, handoff, providers, runner, state
from ariadex.handoff import add_item, read_handoff, set_item_status, write_handoff
from ariadex.runner import (
    Runner,
    UnavailableVerifier,
    VerificationResult,
    Verifier,
    apply_reset,
    inspect_repository,
    select_context_strategy,
    select_next_action,
)
from ariadex.terminal import FakeTerminalDriver


class PassVerifier(Verifier):
    def verify(self, action, output):
        return VerificationResult(passed=True, detail="stub pass")


class FailVerifier(Verifier):
    def verify(self, action, output):
        return VerificationResult(passed=False, detail="stub failure")


def make_project(root: Path, specs=("demo",), **overrides) -> config.Config:
    spec_dir = Path(root) / "openspec" / "changes"
    for name in specs:
        (spec_dir / name).mkdir(parents=True, exist_ok=True)
    values = dict(spec_dir="openspec/changes", handoff_file=".ariadex/handoff.md")
    values.update(overrides)
    raw = {
        "agent_provider": "opencode",
        "terminal_driver": "tmux",
        "context_strategy": "per-spec",
        "reset_mode": "auto",
        "retry_limit": 0,
        "blocker_policy": "stop-on-blocker",
        **values,
    }
    return config.validate(raw)


def make_runner(root: Path, cfg=None, verifier=None, provider="opencode"):
    cfg = cfg or make_project(root)
    (root / ".ariadex").mkdir(parents=True, exist_ok=True)
    state.write(root, state.initial_state())
    driver = FakeTerminalDriver()
    adapter = providers.get_adapter(
        provider, driver, "test-session", root
    )
    return Runner(root, cfg, adapter, verifier), driver


class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_open_high_priority_issue_precedes_next_spec(self):
        cfg = make_project(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        add_item(doc, "issue", "broken", priority="high", item_id="u-1")
        kind, target = select_next_action(
            doc, inspect_repository(self.root, cfg.spec_dir)
        )
        self.assertEqual(kind, "resolve-issue")
        self.assertTrue(target.startswith("u-1"))

    def test_no_issues_advances_current_spec(self):
        cfg = make_project(self.root)
        doc = handoff.empty_handoff()
        doc.current_spec = "demo"
        kind, target = select_next_action(
            doc, inspect_repository(self.root, cfg.spec_dir)
        )
        self.assertEqual(kind, "advance-spec")
        self.assertEqual(target, "demo")

    def test_missing_current_spec_stops(self):
        cfg = make_project(self.root)
        doc = handoff.empty_handoff()
        doc.current_spec = "ghost"
        kind, _ = select_next_action(
            doc, inspect_repository(self.root, cfg.spec_dir)
        )
        self.assertEqual(kind, "stop")

    def test_nothing_to_do_is_idle(self):
        cfg = make_project(self.root)
        kind, _ = select_next_action(
            handoff.empty_handoff(), inspect_repository(self.root, cfg.spec_dir)
        )
        self.assertEqual(kind, "idle")


class ExecutionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write_doc(self, doc):
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)

    def test_restart_resumes_open_issue_before_next_spec(self):
        run, _ = make_runner(self.root, verifier=PassVerifier())
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        add_item(doc, "issue", "broken", priority="high", item_id="u-1")
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.kind, "resolve-issue")
        self.assertEqual(result.outcome, "completed")
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        item = handoff.get_item(reloaded, "u-1")
        self.assertEqual(item.status, "RESOLVED")
        self.assertTrue(item.history)

    def test_unverified_outcome_persists_without_advancing(self):
        run, _ = make_runner(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        add_item(doc, "issue", "broken", priority="high", item_id="u-1")
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.outcome, "unverified")
        self.assertTrue(result.stopped)
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertEqual(handoff.get_item(reloaded, "u-1").status, "OPEN")
        self.assertIsNone(reloaded.current_spec)

    def test_provider_startup_failure_records_blocker(self):
        run, driver = make_runner(self.root, verifier=PassVerifier())
        driver.missing_binary = True
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.outcome, "blocked")
        self.assertTrue(result.stopped)
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertEqual(reloaded.status, "blocked")
        self.assertIsNone(reloaded.current_spec)

    def test_existing_blocker_stops_scheduling(self):
        run, _ = make_runner(self.root, verifier=PassVerifier())
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        add_item(doc, "blocker", "provider gone", priority="high", item_id="u-b")
        set_item_status(doc, "u-b", "BLOCKED", note="crashed")
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.outcome, "blocked")
        self.assertTrue(result.stopped)
        # Spec did not advance.
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertIsNone(reloaded.current_spec)

    def test_verified_start_sets_current_spec(self):
        run, _ = make_runner(self.root, verifier=PassVerifier())
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.kind, "start-spec")
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertEqual(reloaded.current_spec, "demo")

    def test_state_syncs_current_spec_and_unresolved_count(self):
        run, _ = make_runner(self.root, verifier=PassVerifier())
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        add_item(doc, "issue", "broken", priority="low", item_id="u-1")
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.outcome, "completed")
        stored = state.read(self.root)
        self.assertEqual(stored.unresolved_count, 0)
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertEqual(reloaded.next_action, "start-spec demo")

    def test_run_loops_until_idle(self):
        run, _ = make_runner(self.root, verifier=PassVerifier())
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        self.write_doc(doc)
        cycles = run.run(max_cycles=5)
        # start-spec, advance-spec (demo -> None), idle.
        self.assertEqual([c.kind for c in cycles], ["start-spec", "advance-spec", "idle"])
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertEqual(reloaded.status, "complete")

    def test_malformed_handoff_stops_with_error(self):
        run, _ = make_runner(self.root)
        path = self.root / ".ariadex" / "handoff.md"
        path.write_text("---\nversion: 1\nstatus: BOGUS\n---\n", encoding="utf-8")
        result = run.run_once()
        self.assertEqual(result.outcome, "failed")
        self.assertTrue(result.stopped)


class ResetTest(unittest.TestCase):
    def test_auto_selects_soft_for_opencode(self):
        driver = FakeTerminalDriver()
        adapter = providers.OpenCodeAdapter(driver, "s", "/tmp")
        adapter.start()
        self.assertEqual(apply_reset(adapter, "auto", True), "soft")
        self.assertIn(("send_input", "s", "/new"), driver.calls)

    def test_auto_selects_hard_for_codex(self):
        driver = FakeTerminalDriver()
        adapter = providers.CodexAdapter(driver, "s", "/tmp")
        adapter.start()
        self.assertEqual(apply_reset(adapter, "auto", True), "hard")
        ops = [op for op, *_ in driver.calls]
        # Hard reset terminates and restarts: session exists again.
        self.assertIn("terminate", ops)
        self.assertEqual(ops.count("create_or_connect"), 2)
        self.assertIn("s", driver.sessions)

    def test_no_boundary_no_reset(self):
        driver = FakeTerminalDriver()
        adapter = providers.OpenCodeAdapter(driver, "s", "/tmp")
        adapter.start()
        calls = len(driver.calls)
        self.assertIsNone(apply_reset(adapter, "auto", False))
        self.assertEqual(len(driver.calls), calls)

    def test_manual_strategy_skips_reset(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        cfg = make_project(root, context_strategy="manual")
        self.assertEqual(select_context_strategy(cfg), "manual")


if __name__ == "__main__":
    unittest.main()
