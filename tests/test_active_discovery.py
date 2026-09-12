"""Regression: archived changes are never active work."""

import io
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path

from ariadex import config, handoff, operator, spec_graph, state
from ariadex.runner import inspect_repository, select_next_action


def make_cfg(**overrides) -> config.Config:
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


def run_cli(root: Path, *argv: str) -> tuple[int, str, str]:
    from ariadex import cli

    out, err = io.StringIO(), io.StringIO()
    with chdir(root), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


class ActiveDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def make_fixture(self, active=("demo",)):
        base = self.root / "openspec" / "changes"
        for name in active:
            (base / name).mkdir(parents=True, exist_ok=True)
            (base / name / "proposal.md").write_text("# demo\n", encoding="utf-8")
        archive = base / "archive" / "2026-09-12-demo"
        archive.mkdir(parents=True, exist_ok=True)
        (archive / "proposal.md").write_text("# old\n", encoding="utf-8")
        (base / ".hidden").mkdir(parents=True, exist_ok=True)
        (base / "notes.txt").write_text("not a change\n", encoding="utf-8")
        return base

    def test_archive_hidden_and_files_never_active(self):
        base = self.make_fixture()
        names, ignored = spec_graph.discover_active_changes(base)
        self.assertEqual(names, ["demo"])
        self.assertIn("archive", ignored)
        self.assertIn(".hidden", ignored)
        self.assertIn("notes.txt", ignored)
        self.assertFalse(spec_graph.is_active_change_name("archive"))
        self.assertFalse(spec_graph.is_active_change_name(".hidden"))
        self.assertTrue(spec_graph.is_active_change_name("demo"))

    def test_load_graph_excludes_archive(self):
        self.make_fixture()
        graph, _ = spec_graph.load_graph(self.root, "openspec/changes")
        self.assertEqual(sorted(graph), ["demo"])
        self.assertNotIn("archive", graph)

    def test_inspect_repository_never_lists_archive(self):
        self.make_fixture()
        repo = inspect_repository(self.root, "openspec/changes")
        self.assertEqual(repo.specs, ["demo"])
        self.assertIn("archive", repo.ignored_specs)

    def test_all_archived_is_idle_never_start_spec_archive(self):
        base = self.root / "openspec" / "changes"
        (base / "archive" / "2026-09-12-old").mkdir(parents=True, exist_ok=True)
        cfg = make_cfg()
        repo = inspect_repository(self.root, cfg.spec_dir)
        self.assertEqual(repo.specs, [])
        kind, target = select_next_action(handoff.empty_handoff(), repo)
        self.assertEqual(kind, "idle")
        self.assertNotIn("archive", target)

    def test_doctor_reports_no_active_changes_after_archival(self):
        base = self.root / "openspec" / "changes"
        (base / "archive" / "2026-09-12-old").mkdir(parents=True, exist_ok=True)
        cfg = make_cfg()
        ok, detail = operator._spec_dir_ok(self.root, cfg)
        self.assertTrue(ok)
        self.assertIn("no active changes", detail)
        self.assertIn("archive", detail.lower() + "ignored")

    def test_preview_idle_when_only_archive(self):
        run_cli(self.root, "init")
        base = self.root / "openspec" / "changes"
        (base / "archive" / "2026-09-12-old").mkdir(parents=True, exist_ok=True)
        preview = operator.build_preview(self.root)
        self.assertEqual(preview["next_action"], "none — idle")
        self.assertNotIn("archive", preview["next_action"])

    def test_resync_never_selects_archive(self):
        from ariadex import resync as resync_mod

        run_cli(self.root, "init")
        base = self.root / "openspec" / "changes"
        (base / "archive" / "2026-09-12-old").mkdir(parents=True, exist_ok=True)
        _, report = resync_mod.resync(self.root, config.load(self.root))
        self.assertEqual(report.next_action, "none — idle")
        self.assertNotIn("archive", report.next_action)

    def test_empty_after_archive_cli_smoke(self):
        run_cli(self.root, "init")
        base = self.root / "openspec" / "changes"
        demo = base / "demo"
        demo.mkdir(parents=True, exist_ok=True)
        (demo / "proposal.md").write_text("# demo\n", encoding="utf-8")
        (base / "archive").mkdir(parents=True, exist_ok=True)
        _, out, _ = run_cli(self.root, "doctor")
        self.assertIn("active change", out)
        # Archive the only active change: doctor + preview go idle.
        target = base / "archive" / "2026-09-12-demo"
        demo.rename(target)
        _, out, _ = run_cli(self.root, "doctor")
        self.assertIn("no active changes", out)
        _, out, _ = run_cli(self.root, "preview")
        self.assertIn("none — idle", out)
        self.assertNotIn("start-spec archive", out)
        st = state.read(self.root)
        _ = st


if __name__ == "__main__":
    unittest.main()
