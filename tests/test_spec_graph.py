"""Tests for spec dependency graph and execution governance."""

import tempfile
import unittest
from pathlib import Path

import yaml

from ariadex import config, handoff, providers, spec_graph, state
from ariadex.handoff import add_item, set_item_status, write_handoff
from ariadex.runner import (
    Runner,
    inspect_repository,
    select_next_action,
)
from ariadex.terminal import FakeTerminalDriver
from ariadex.verify import VerificationResult, Verifier


class PassVerifier(Verifier):
    def verify(self, action, output):
        return VerificationResult(passed=True, detail="stub pass", exit_code=0)


def make_cfg(root: Path, **overrides) -> config.Config:
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


def make_specs(root: Path, specs: dict[str, list[str] | None]) -> None:
    base = root / "openspec" / "changes"
    for name, deps in specs.items():
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        if deps is not None:
            (d / ".openspec.yaml").write_text(
                yaml.safe_dump({"depends_on": deps}), encoding="utf-8"
            )


def make_runner(root: Path, cfg=None, verifier=None):
    cfg = cfg or make_cfg(root)
    (root / ".ariadex").mkdir(parents=True, exist_ok=True)
    stored = state.initial_state()
    stored.mode = "AUTO"
    state.write(root, stored)
    driver = FakeTerminalDriver()
    adapter = providers.get_adapter("opencode", driver, "test-session", root)
    return Runner(root, cfg, adapter, verifier or PassVerifier()), driver


def completed_handoff(*names: str) -> handoff.Handoff:
    doc = handoff.empty_handoff()
    for i, name in enumerate(names):
        doc.completed.append(
            handoff.CompletedItem(id=f"c-{i + 1}", summary=f"completed spec `{name}`")
        )
    return doc


class MetadataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_absent_metadata_means_no_predecessors(self):
        make_specs(self.root, {"a": None})
        self.assertEqual(
            spec_graph.read_spec_dependencies(self.root / "openspec" / "changes", "a"),
            [],
        )

    def test_dependencies_alias_accepted(self):
        base = self.root / "openspec" / "changes" / "b"
        base.mkdir(parents=True, exist_ok=True)
        (base / ".openspec.yaml").write_text(
            yaml.safe_dump({"dependencies": ["a"]}), encoding="utf-8"
        )
        self.assertEqual(
            spec_graph.read_spec_dependencies(self.root / "openspec" / "changes", "b"),
            ["a"],
        )

    def test_malformed_metadata_raises(self):
        base = self.root / "openspec" / "changes" / "bad"
        base.mkdir(parents=True, exist_ok=True)
        (base / ".openspec.yaml").write_text(
            yaml.safe_dump({"depends_on": "not-a-list"}), encoding="utf-8"
        )
        with self.assertRaises(spec_graph.SpecGraphError):
            spec_graph.read_spec_dependencies(self.root / "openspec" / "changes", "bad")

    def test_self_dependency_raises(self):
        make_specs(self.root, {"a": ["a"]})
        with self.assertRaises(spec_graph.SpecGraphError):
            spec_graph.read_spec_dependencies(self.root / "openspec" / "changes", "a")

    def test_load_graph_reports_errors_without_raising(self):
        make_specs(self.root, {"good": ["base"], "bad": ["x"]})
        base = self.root / "openspec" / "changes" / "bad"
        (base / ".openspec.yaml").write_text("depends_on: [unclosed", encoding="utf-8")
        graph, errors = spec_graph.load_graph(self.root, "openspec/changes")
        self.assertIn("bad", errors)
        self.assertIn("good", graph)


class GraphTest(unittest.TestCase):
    def test_linear_chain_topological_order(self):
        graph = {"a": [], "b": ["a"], "c": ["b"]}
        # Only changes with all predecessors verified complete are ready.
        self.assertEqual(spec_graph.eligible_specs(graph, set()), ["a"])
        self.assertEqual(spec_graph.eligible_specs(graph, {"a"}), ["b"])
        self.assertEqual(spec_graph.eligible_specs(graph, {"a", "b"}), ["c"])

    def test_branching_diamond_deterministic(self):
        graph = {"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]}
        self.assertEqual(spec_graph.eligible_specs(graph, set()), ["a"])
        self.assertEqual(spec_graph.eligible_specs(graph, {"a"}), ["b", "c"])
        # d waits until both branches complete.
        self.assertEqual(
            spec_graph.incomplete_predecessors("d", graph, {"a", "b"}), ["c"]
        )

    def test_missing_dependency_detected(self):
        graph = {"a": ["ghost"]}
        missing = spec_graph.find_missing(graph, {"a"}, set())
        self.assertEqual(missing, {"a": ["ghost"]})
        ok, reason = spec_graph.validate_target("a", graph, {"a"}, set())
        self.assertFalse(ok)
        self.assertIn("ghost", reason)

    def test_cycle_detected_deterministically(self):
        graph = {"a": ["b"], "b": ["a"], "c": []}
        cycles = spec_graph.find_cycles(graph)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(set(cycles[0]), {"a", "b"})
        # Unaffected spec remains eligible.
        self.assertEqual(spec_graph.eligible_specs(graph, set()), ["c"])
        ok, reason = spec_graph.validate_target("a", graph, set(graph), set())
        self.assertFalse(ok)
        self.assertIn("cycle", reason)

    def test_self_cycle(self):
        graph = {"a": ["a"]}
        self.assertEqual(spec_graph.find_cycles(graph), [["a"]])

    def test_completed_predecessor_satisfies(self):
        graph = {"b": ["a"]}
        ok, _ = spec_graph.validate_target("b", graph, {"a", "b"}, {"a"})
        self.assertTrue(ok)

    def test_completed_specs_excluded_from_eligible(self):
        graph = {"a": [], "b": []}
        self.assertEqual(spec_graph.eligible_specs(graph, {"a"}), ["b"])
        self.assertEqual(spec_graph.eligible_specs(graph, {"a", "b"}), [])


class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_explicit_target_with_unfinished_prerequisite_stops(self):
        make_specs(self.root, {"base": None, "top": ["base"]})
        cfg = make_cfg(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "top"
        kind, target = select_next_action(
            doc, inspect_repository(self.root, cfg.spec_dir)
        )
        self.assertEqual(kind, "stop")
        self.assertIn("base", target)

    def test_explicit_target_with_completed_prerequisite_starts(self):
        make_specs(self.root, {"base": None, "top": ["base"]})
        cfg = make_cfg(self.root)
        doc = completed_handoff("base")
        doc.next_spec = "top"
        kind, target = select_next_action(
            doc, inspect_repository(self.root, cfg.spec_dir)
        )
        self.assertEqual(kind, "start-spec")
        self.assertEqual(target, "top")

    def test_missing_dependency_stops(self):
        make_specs(self.root, {"top": ["ghost"]})
        cfg = make_cfg(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "top"
        kind, target = select_next_action(
            doc, inspect_repository(self.root, cfg.spec_dir)
        )
        self.assertEqual(kind, "stop")
        self.assertIn("ghost", target)

    def test_cycle_stops_and_names_cycle(self):
        make_specs(self.root, {"a": ["b"], "b": ["a"]})
        cfg = make_cfg(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "a"
        kind, target = select_next_action(
            doc, inspect_repository(self.root, cfg.spec_dir)
        )
        self.assertEqual(kind, "stop")
        self.assertIn("cycle", target)
        self.assertIn("a", target)

    def test_no_explicit_target_picks_eligible_not_directory_order(self):
        # zzz sorts last alphabetically but has no deps; aaa waits on base.
        make_specs(self.root, {"zzz": None, "aaa": ["base"], "base": None})
        cfg = make_cfg(self.root)
        kind, target = select_next_action(
            handoff.empty_handoff(), inspect_repository(self.root, cfg.spec_dir)
        )
        # Deterministic topological order: base and zzz ready, base first.
        self.assertEqual(kind, "start-spec")
        self.assertEqual(target, "base")

    def test_all_complete_is_idle(self):
        make_specs(self.root, {"a": None})
        cfg = make_cfg(self.root)
        doc = completed_handoff("a")
        kind, _ = select_next_action(doc, inspect_repository(self.root, cfg.spec_dir))
        self.assertEqual(kind, "idle")

    def test_malformed_metadata_stops(self):
        make_specs(self.root, {"bad": ["x"]})
        base = self.root / "openspec" / "changes" / "bad"
        (base / ".openspec.yaml").write_text("depends_on: [unclosed", encoding="utf-8")
        cfg = make_cfg(self.root)
        kind, target = select_next_action(
            handoff.empty_handoff(), inspect_repository(self.root, cfg.spec_dir)
        )
        self.assertEqual(kind, "stop")
        self.assertIn("bad", target)


class RunnerIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write_doc(self, doc):
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)

    def test_blocked_explicit_target_sends_no_input_and_persists_blocker(self):
        make_specs(self.root, {"base": None, "top": ["base"]})
        run, driver = make_runner(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "top"
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.outcome, "blocked")
        self.assertTrue(result.stopped)
        self.assertEqual(driver.calls, [])
        reloaded = handoff.read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertTrue(
            any(
                item.type == "blocker" and "base" in item.description
                for item in reloaded.unresolved
            )
        )
        self.assertIsNone(reloaded.current_spec)

    def test_dependency_blocker_does_not_duplicate_across_cycles(self):
        make_specs(self.root, {"top": ["ghost"]})
        run, _ = make_runner(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "top"
        self.write_doc(doc)
        run.run_once()
        first = handoff.read_handoff(self.root / ".ariadex" / "handoff.md")
        count_first = len(first.unresolved)
        # Second cycle runs with a fresh runner over the same files; the
        # BLOCKED stop policy would normally stop first, so use
        # record-and-continue to reach selection again... instead simulate
        # two selections persisting the same reason: reload and rerun the
        # STOP persistence path directly.
        run2, _ = make_runner(self.root, cfg=run.config)
        # Clear BLOCKED stoppers to reach dependency selection again.
        doc2 = handoff.read_handoff(self.root / ".ariadex" / "handoff.md")
        for item in doc2.unresolved:
            if item.status == "BLOCKED":
                item.status = "RESOLVED"
                item.history.append({"from": "BLOCKED", "to": "RESOLVED"})
        doc2.status = "idle"
        self.write_doc(doc2)
        run2.run_once()
        second = handoff.read_handoff(self.root / ".ariadex" / "handoff.md")
        descriptions = [item.description for item in second.unresolved]
        self.assertEqual(len(descriptions), len(set(descriptions)))
        self.assertLessEqual(len(second.unresolved), count_first + 1)

    def test_cycle_records_durable_blocker_naming_cycle(self):
        make_specs(self.root, {"a": ["b"], "b": ["a"]})
        run, driver = make_runner(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "a"
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.outcome, "blocked")
        self.assertEqual(driver.calls, [])
        reloaded = handoff.read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertTrue(
            any("cycle" in item.description for item in reloaded.unresolved)
        )

    def test_unaffected_spec_schedules_despite_cycle_elsewhere(self):
        make_specs(self.root, {"a": ["b"], "b": ["a"], "c": None})
        run, _ = make_runner(self.root)
        doc = handoff.empty_handoff()
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.kind, "start-spec")
        self.assertIn("c", result.action)

    def test_completed_chain_advances_in_order(self):
        make_specs(self.root, {"base": None, "top": ["base"]})
        run, _ = make_runner(self.root)
        doc = handoff.empty_handoff()
        self.write_doc(doc)
        first = run.run_once()
        self.assertEqual(first.kind, "start-spec")
        self.assertIn("base", first.action)
        reloaded = handoff.read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertEqual(reloaded.current_spec, "base")
        # Complete base, then top becomes eligible automatically.
        second = run.run_once()
        self.assertEqual(second.kind, "advance-spec")
        third = run.run_once()
        self.assertEqual(third.kind, "start-spec")
        self.assertIn("top", third.action)

    def test_deferred_predecessor_still_blocks(self):
        make_specs(self.root, {"base": None, "top": ["base"]})
        run, _ = make_runner(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "top"
        item = add_item(doc, "issue", "deferred work", item_id="u-1")
        set_item_status(doc, "u-1", "DEFERRED", target_spec="base", reason="later")
        self.assertEqual(item.status, "DEFERRED")
        self.write_doc(doc)
        result = run.run_once()
        # base never verified complete, so top stays blocked.
        self.assertEqual(result.outcome, "blocked")
        self.assertIn("base", result.detail)

    def test_blocked_predecessor_still_blocks(self):
        make_specs(self.root, {"base": None, "top": ["base"]})
        doc = handoff.empty_handoff()
        doc.next_spec = "top"
        add_item(doc, "blocker", "base broken", item_id="u-9")
        set_item_status(doc, "u-9", "BLOCKED", note="crash")
        # record-and-continue so the runner reaches dependency selection.
        cfg = make_cfg(self.root, blocker_policy="record-and-continue")
        run2, _ = make_runner(self.root, cfg=cfg)
        self.write_doc(doc)
        result = run2.run_once()
        self.assertEqual(result.outcome, "blocked")
        self.assertIn("base", result.detail)

    def test_verification_gate_still_required_for_eligible_spec(self):
        from ariadex.verify import ShellVerifier

        make_specs(self.root, {"base": None})
        cfg = make_cfg(self.root, retry_limit=2)
        run, _ = make_runner(
            self.root, cfg=cfg, verifier=ShellVerifier(["exit 1"], self.root)
        )
        doc = handoff.empty_handoff()
        doc.next_spec = "base"
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.outcome, "verification-failed")
        reloaded = handoff.read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertEqual(reloaded.current_spec, None)
        self.assertEqual(reloaded.completed, [])


if __name__ == "__main__":
    unittest.main()
