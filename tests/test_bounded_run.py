"""Tests for bounded run completion and cycle-limit exhaustion."""

import tempfile
import unittest
from pathlib import Path

from ariadex import cli, config, handoff, providers, state
from ariadex.handoff import add_item, read_handoff, write_handoff
from ariadex.runner import (
    ACTION_CYCLE_LIMIT,
    CycleResult,
    Runner,
    VerificationResult,
    Verifier,
)
from ariadex.terminal import FakeTerminalDriver


class PassVerifier(Verifier):
    def verify(self, action, output):
        return VerificationResult(passed=True, detail="stub pass", exit_code=0)


def make_project(root: Path, specs=("demo",), **overrides) -> config.Config:
    spec_dir = Path(root) / "openspec" / "changes"
    spec_dir.mkdir(parents=True, exist_ok=True)
    for name in specs:
        (spec_dir / name).mkdir(parents=True, exist_ok=True)
    values = {"spec_dir": "openspec/changes", "handoff_file": ".ariadex/handoff.md"}
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


def make_runner(root: Path, cfg=None, verifier=None):
    cfg = cfg or make_project(root)
    (root / ".ariadex").mkdir(parents=True, exist_ok=True)
    stored = state.initial_state()
    stored.mode = "AUTO"
    state.write(root, stored)
    driver = FakeTerminalDriver()
    adapter = providers.get_adapter("opencode", driver, "test-session", root)
    return Runner(root, cfg, adapter, verifier or PassVerifier()), driver


class ZeroBudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_zero_budget_sends_no_input_and_reports_incomplete(self):
        run, driver = make_runner(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        add_item(doc, "issue", "broken", priority="high", item_id="u-1")
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)
        cycles = run.run(max_cycles=0)
        self.assertEqual(len(cycles), 1)
        last = cycles[-1]
        self.assertEqual(last.kind, ACTION_CYCLE_LIMIT)
        self.assertEqual(last.outcome, "cycle-limit")
        self.assertTrue(last.stopped)
        self.assertEqual(last.stop_reason, "cycle-limit")
        self.assertIn("no execution budget", last.detail)
        self.assertEqual(driver.calls, [])
        self.assertEqual(cli.exit_for_cycles(cycles), cli.EXIT_ERROR)

    def test_negative_budget_is_incomplete(self):
        run, driver = make_runner(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)
        cycles = run.run(max_cycles=-2)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[-1].outcome, "cycle-limit")
        self.assertTrue(cycles[-1].stopped)
        self.assertEqual(driver.calls, [])
        self.assertEqual(cli.exit_for_cycles(cycles), cli.EXIT_ERROR)

    def test_zero_budget_preserves_handoff_state(self):
        run, _ = make_runner(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        add_item(doc, "issue", "broken", priority="high", item_id="u-1")
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)
        run.run(max_cycles=0)
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertIsNone(reloaded.current_spec)
        self.assertEqual(handoff.get_item(reloaded, "u-1").status, "OPEN")
        self.assertIn("no execution budget", reloaded.next_action)


class ExactBoundTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_terminal_at_bound_appends_no_cycle_limit(self):
        run, _ = make_runner(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)
        cycles = run.run(max_cycles=5)
        kinds = [c.kind for c in cycles]
        self.assertEqual(kinds, ["start-spec", "advance-spec", "idle"])
        self.assertFalse([c for c in cycles if c.outcome == "cycle-limit"])
        self.assertEqual(cli.exit_for_cycles(cycles), cli.EXIT_OK)


class ExhaustionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write_issues(self, count: int):
        doc = handoff.empty_handoff()
        for i in range(1, count + 1):
            add_item(doc, "issue", f"work {i}", priority="high", item_id=f"u-{i}")
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)

    def test_exhausted_budget_appends_stopped_cycle_limit(self):
        cfg = make_project(self.root, specs=())
        run, driver = make_runner(self.root, cfg=cfg)
        self.write_issues(12)
        cycles = run.run(max_cycles=10)
        # Ten verified completions, then the explicit exhaustion result.
        self.assertEqual(len(cycles), 11)
        for cycle in cycles[:10]:
            self.assertEqual(cycle.kind, "resolve-issue")
            self.assertEqual(cycle.outcome, "completed")
            self.assertFalse(cycle.stopped)
        last = cycles[-1]
        self.assertEqual(last.kind, ACTION_CYCLE_LIMIT)
        self.assertEqual(last.outcome, "cycle-limit")
        self.assertTrue(last.stopped)
        self.assertEqual(last.stop_reason, "cycle-limit")
        self.assertIn("resolve-issue", last.action)
        self.assertIn("resolve-issue", last.detail)
        self.assertNotIn("completed", last.action)
        # The appended result itself sends no provider input: replaying ten
        # single cycles on a twin project uses the identical call count.
        twin_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(twin_tmp.cleanup)
        twin_root = Path(twin_tmp.name)
        twin_cfg = make_project(twin_root, specs=())
        twin_run, twin_driver = make_runner(twin_root, cfg=twin_cfg)
        twin_doc = handoff.empty_handoff()
        for i in range(1, 13):
            add_item(twin_doc, "issue", f"work {i}", priority="high", item_id=f"u-{i}")
        write_handoff(twin_root / ".ariadex" / "handoff.md", twin_doc)
        for _ in range(10):
            twin_run.run_once()
        self.assertEqual(len(driver.calls), len(twin_driver.calls))
        sent = [c[2] for c in driver.calls if c[0] == "send_input"]
        self.assertFalse(any("cycle-limit" in text for text in sent))
        self.assertEqual(cli.exit_for_cycles(cycles), cli.EXIT_ERROR)

    def test_exhaustion_preserves_remaining_next_action(self):
        cfg = make_project(self.root, specs=())
        run, _ = make_runner(self.root, cfg=cfg)
        self.write_issues(12)
        run.run(max_cycles=10)
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertTrue(reloaded.next_action.startswith("resolve-issue u-11"))
        remaining = [i for i in reloaded.unresolved if i.status == "OPEN"]
        self.assertEqual(len(remaining), 2)
        resolved = [i for i in reloaded.unresolved if i.status == "RESOLVED"]
        self.assertEqual(len(resolved), 10)
        self.assertIsNone(reloaded.current_spec)

    def test_cycle_limit_recorded_in_metrics(self):
        from ariadex.logging import read_metrics
        from ariadex.observability import summarize_metrics

        cfg = make_project(self.root, specs=())
        run, _ = make_runner(self.root, cfg=cfg)
        self.write_issues(12)
        run.run(max_cycles=10)
        records = read_metrics(self.root / ".ariadex" / "metrics.jsonl")
        self.assertEqual(records[-1]["outcome"], "cycle-limit")
        summary = summarize_metrics(records)
        self.assertIn("cycle-limit", summary["outcomes"])
        self.assertEqual(summary["outcomes"]["cycle-limit"], 1)
        self.assertEqual(summary["outcomes"]["completed"], 10)


class ExitMappingTest(unittest.TestCase):
    def test_idle_tail_is_success(self):
        cycles = [
            CycleResult(
                kind="idle",
                action="none — idle",
                outcome="idle",
                detail="done",
                stopped=True,
                stop_reason="idle",
            )
        ]
        self.assertEqual(cli.exit_for_cycles(cycles), cli.EXIT_OK)

    def test_blocked_tail_is_error(self):
        cycles = [
            CycleResult(
                kind="stop",
                action="none — blocked",
                outcome="blocked",
                detail="x",
                stopped=True,
                stop_reason="blocked",
            )
        ]
        self.assertEqual(cli.exit_for_cycles(cycles), cli.EXIT_ERROR)

    def test_cycle_limit_tail_is_error(self):
        cycles = [
            CycleResult(
                kind="cycle-limit",
                action="resolve-issue u-11: work 11",
                outcome="cycle-limit",
                detail="budget exhausted",
                stopped=True,
                stop_reason="cycle-limit",
            )
        ]
        self.assertEqual(cli.exit_for_cycles(cycles), cli.EXIT_ERROR)

    def test_unstopped_tail_and_empty_never_read_as_success(self):
        unstopped = [
            CycleResult(
                kind="resolve-issue",
                action="resolve-issue u-1: work",
                outcome="completed",
                detail="verified",
                stopped=False,
                stop_reason=None,
            )
        ]
        self.assertEqual(cli.exit_for_cycles(unstopped), cli.EXIT_ERROR)
        self.assertEqual(cli.exit_for_cycles([]), cli.EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
