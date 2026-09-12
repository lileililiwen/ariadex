"""Tests for resynchronization after manual intervention."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from ariadex import config, handoff, resync
from ariadex.handoff import HandoffError, add_item, read_handoff, write_handoff


def make_config(root: Path, **overrides) -> config.Config:
    values = {
        "agent_provider": "opencode",
        "terminal_driver": "tmux",
        "context_strategy": "per-spec",
        "reset_mode": "auto",
        "spec_dir": "openspec/changes",
        "handoff_file": ".ariadex/handoff.md",
        "verification_commands": [],
        "retry_limit": 2,
        "blocker_policy": "stop-on-blocker",
    }
    values.update(overrides)
    return config.validate(values)


def init_git(root: Path) -> None:
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "t@t.t"], check=True
    )
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)


class ResyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "openspec" / "changes" / "demo").mkdir(parents=True)
        (self.root / ".ariadex").mkdir(parents=True, exist_ok=True)
        self.cfg = make_config(self.root)
        init_git(self.root)

    def write_doc(self, doc):
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)

    def test_stale_next_action_recomputed(self):
        doc = handoff.empty_handoff()
        doc.next_action = "resolve u-ghost: stale"
        add_item(doc, "issue", "real work", priority="high", item_id="u-1")
        self.write_doc(doc)
        _, report = resync.resync(self.root, self.cfg)
        self.assertTrue(report.next_action.startswith("resolve-issue u-1"))
        self.assertTrue(any("recomputed" in note for note in report.notes))
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertTrue(reloaded.next_action.startswith("resolve-issue u-1"))

    def test_manual_fix_is_evidence_not_completion(self):
        target = self.root / "app.py"
        target.write_text("print('manual fix')\n", encoding="utf-8")
        doc = handoff.empty_handoff()
        doc.current_spec = "demo"
        add_item(doc, "issue", "app broken", priority="high", item_id="u-1")
        self.write_doc(doc)
        _, report = resync.resync(self.root, self.cfg)
        self.assertIn("app.py", report.changed_files)
        self.assertTrue(any("evidence" in note for note in report.notes))
        reloaded = read_handoff(self.root / ".ariadex" / "handoff.md")
        # The issue stays OPEN; resync fabricates no completion.
        self.assertEqual(handoff.get_item(reloaded, "u-1").status, "OPEN")
        self.assertEqual(reloaded.current_spec, "demo")
        self.assertEqual(reloaded.completed, [])

    def test_clean_tree_keeps_issue_actionable(self):
        doc = handoff.empty_handoff()
        add_item(doc, "issue", "still open", priority="medium", item_id="u-1")
        self.write_doc(doc)
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-qm", "handoff"], check=True
        )
        _, report = resync.resync(self.root, self.cfg)
        self.assertEqual(report.changed_files, [])
        self.assertTrue(report.next_action.startswith("resolve-issue u-1"))
        self.assertTrue(any("clean tree" in note for note in report.notes))

    def test_non_git_project_still_resyncs(self):
        (self.root / ".git").rename(self.root / ".git-bak")
        try:
            doc = handoff.empty_handoff()
            doc.next_spec = "demo"
            self.write_doc(doc)
            _, report = resync.resync(self.root, self.cfg)
            self.assertFalse(report.git_available)
            self.assertEqual(report.next_action, "start-spec demo")
        finally:
            (self.root / ".git-bak").rename(self.root / ".git")

    def test_unreadable_handoff_refuses(self):
        path = self.root / ".ariadex" / "handoff.md"
        path.write_text("---\nversion: 1\nstatus: BOGUS\n---\n", encoding="utf-8")
        with self.assertRaises(HandoffError):
            resync.resync(self.root, self.cfg)


if __name__ == "__main__":
    unittest.main()
