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
from ariadex.verify import ShellVerifier


class PassVerifier(Verifier):
    def verify(self, action, output):
        return VerificationResult(passed=True, detail="stub pass", exit_code=0)


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
        "verification_commands": [],
        **values,
    }
    return config.validate(raw)


def make_runner(root: Path, cfg=None, verifier=None, provider="opencode"):
    cfg = cfg or make_project(root)
    (root / ".ariadex").mkdir(parents=True, exist_ok=True)
    stored = state.initial_state()
    stored.mode = "AUTO"
    state.write(root, stored)
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


class VerificationGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write_doc(self, doc):
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)

    def failing_run(self, **overrides):
        values = dict(retry_limit=2)
        values.update(overrides)
        cfg = make_project(self.root, **values)
        return make_runner(
            self.root, cfg=cfg, verifier=ShellVerifier(["exit 1"], self.root)
        )

    def test_failed_tests_schedule_bounded_repair_then_block(self):
        run, _ = self.failing_run()
        doc = handoff.empty_handoff()
        add_item(doc, "issue", "broken", priority="high", item_id="u-1")
        self.write_doc(doc)
        first = run.run_once()
        self.assertEqual(first.outcome, "verification-failed")
        self.assertFalse(first.stopped)
        second = run.run_once()
        self.assertFalse(second.stopped)
        third = run.run_once()
        self.assertTrue(third.stopped)
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        item = handoff.get_item(reloaded, "u-1")
        self.assertEqual(item.status, "BLOCKED")
        self.assertEqual(item.attempts, 3)
        # Three failure notes plus the BLOCKED transition: history retained.
        self.assertEqual(len(item.history), 4)
        self.assertEqual(item.history[-1]["to"], "BLOCKED")

    def test_retry_limit_reached_continues_per_policy(self):
        run, _ = self.failing_run(retry_limit=0, blocker_policy="record-and-continue")
        doc = handoff.empty_handoff()
        add_item(doc, "issue", "broken", priority="high", item_id="u-1")
        add_item(doc, "issue", "other", priority="low", item_id="u-2")
        self.write_doc(doc)
        result = run.run_once()
        self.assertFalse(result.stopped)
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        # u-1 stays OPEN but exhausted; the runner moves to u-2.
        self.assertEqual(handoff.get_item(reloaded, "u-1").status, "OPEN")
        self.assertTrue(reloaded.next_action.startswith("resolve-issue u-2"))

    def test_attempts_survive_restart(self):
        run, _ = self.failing_run()
        doc = handoff.empty_handoff()
        add_item(doc, "issue", "broken", priority="high", item_id="u-1")
        self.write_doc(doc)
        run.run_once()
        fresh, _ = make_runner(
            self.root, cfg=run.config,
            verifier=ShellVerifier(["exit 1"], self.root),
        )
        fresh.run_once()
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertEqual(handoff.get_item(reloaded, "u-1").attempts, 2)

    def test_failing_spec_verification_keeps_spec_incomplete(self):
        run, _ = self.failing_run()
        doc = handoff.empty_handoff()
        doc.current_spec = "demo"
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.kind, "advance-spec")
        self.assertEqual(result.outcome, "verification-failed")
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertEqual(reloaded.current_spec, "demo")
        self.assertEqual(reloaded.completed, [])

    def test_eventual_pass_completes_after_repair(self):
        marker = self.root / "pass-marker"
        cfg = make_project(self.root, retry_limit=2)
        verifier = ShellVerifier([f"test -f {marker}"], self.root)
        run, _ = make_runner(self.root, cfg=cfg, verifier=verifier)
        doc = handoff.empty_handoff()
        add_item(doc, "issue", "broken", priority="high", item_id="u-1")
        self.write_doc(doc)
        self.assertEqual(run.run_once().outcome, "verification-failed")
        marker.write_text("ok", encoding="utf-8")
        result = run.run_once()
        self.assertEqual(result.outcome, "completed")
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertEqual(handoff.get_item(reloaded, "u-1").status, "RESOLVED")


class ObservabilityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_cycle_writes_log_and_metrics(self):
        run, _ = make_runner(self.root, verifier=PassVerifier())
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)
        run.run_once()
        logs = list((self.root / ".ariadex" / "runs").rglob("*.log"))
        self.assertEqual(len(logs), 1)
        from ariadex.logging import read_metrics

        records = read_metrics(self.root / ".ariadex" / "metrics.jsonl")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["usage"], "unavailable")
        self.assertEqual(records[0]["validation_result"], "passed")
        self.assertEqual(records[0]["exit_code"], 0)

    def test_available_usage_persisted(self):
        class UsageAdapter(providers.OpenCodeAdapter):
            def get_usage(self):
                return {"input_tokens": 10, "output_tokens": 4, "cost": 0.02}

        cfg = make_project(self.root)
        (self.root / ".ariadex").mkdir(parents=True, exist_ok=True)
        stored = state.initial_state()
        stored.mode = "AUTO"
        state.write(self.root, stored)
        adapter = UsageAdapter(FakeTerminalDriver(), "s", self.root)
        run = Runner(self.root, cfg, adapter, PassVerifier())
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)
        run.run_once()
        from ariadex.logging import read_metrics

        records = read_metrics(self.root / ".ariadex" / "metrics.jsonl")
        self.assertEqual(records[0]["usage"]["input_tokens"], 10)


if __name__ == "__main__":
    unittest.main()
