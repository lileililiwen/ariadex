"""Tests for takeover, resume guards, auto resync, and mode-gated runs."""

import io
import tempfile
import unittest
import unittest.mock
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path

from ariadex import cli, config, handoff, providers, state
from ariadex.handoff import add_item, write_handoff
from ariadex.runner import Runner
from ariadex.terminal import FakeTerminalDriver
from ariadex.tmux_setup import TmuxSetupError


def handoff_path(root: Path) -> Path:
    """Configured durable handoff location (default root `HANDOFF.md`)."""
    return root / config.load(root).handoff_file


def run_cli(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with chdir(root), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


class TakeoverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        run_cli(self.root, "init")

    def test_takeover_enters_manual_and_preserves_session(self):
        before = state.read(self.root).session_id
        code, out, _ = run_cli(self.root, "takeover")
        self.assertEqual(code, 0)
        self.assertIn("MANUAL", out)
        stored = state.read(self.root)
        self.assertEqual(stored.mode, "MANUAL")
        # The tmux session identity is preserved, never terminated here.
        self.assertEqual(stored.session_id, before)

    def test_takeover_keeps_observation_log(self):
        st = state.read(self.root)
        st.mode = "AUTO"
        state.write(self.root, st)
        run_cli(self.root, "takeover")
        logs = list((self.root / ".ariadex" / "runs").rglob("*.log"))
        self.assertEqual(len(logs), 1)
        self.assertIn("takeover", logs[0].read_text(encoding="utf-8"))

    def test_manual_run_sends_no_input(self):
        run_cli(self.root, "takeover")
        code, _, err = run_cli(self.root, "--no-auto-install", "run")
        self.assertNotEqual(code, 0)
        self.assertIn("MANUAL", err)
        # Refused before scheduling: no cycles observed anything.
        self.assertFalse((self.root / ".ariadex" / "metrics.jsonl").exists())

    def test_manual_mode_survives_restart(self):
        run_cli(self.root, "takeover")
        doc = handoff.empty_handoff()
        add_item(doc, "issue", "work", priority="high", item_id="u-1")
        write_handoff(handoff_path(self.root), doc)
        # A fresh Runner process instance still sends nothing.
        from ariadex import config as config_mod

        cfg = config_mod.load(self.root)
        driver = FakeTerminalDriver()
        adapter = providers.get_adapter("opencode", driver, "s", self.root)
        fresh = Runner(self.root, cfg, adapter)
        result = fresh.run_once()
        self.assertTrue(result.stopped)
        self.assertEqual(result.outcome, "mode-guard")
        self.assertEqual(driver.calls, [])


class PauseResumeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        run_cli(self.root, "init")

    def test_pause_preserves_cli_session(self):
        before = state.read(self.root).session_id
        code, out, _ = run_cli(self.root, "pause")
        self.assertEqual(code, 0)
        self.assertIn("PAUSE", out)
        stored = state.read(self.root)
        self.assertEqual(stored.mode, "PAUSE")
        self.assertEqual(stored.session_id, before)

    def test_resume_idempotent_from_auto(self):
        code, out, _ = run_cli(self.root, "resume")  # AUTO after init
        self.assertEqual(code, 0)
        self.assertIn("AUTO", out)
        self.assertEqual(state.read(self.root).mode, "AUTO")

    def test_resume_still_rejected_from_manual(self):
        run_cli(self.root, "takeover")
        code, _, err = run_cli(self.root, "resume")
        self.assertNotEqual(code, 0)
        self.assertIn("resume rejected", err)

    def test_pause_then_resume_returns_to_auto(self):
        run_cli(self.root, "pause")
        code, _, _ = run_cli(self.root, "resume")
        self.assertEqual(code, 0)
        self.assertEqual(state.read(self.root).mode, "AUTO")


class AutoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        run_cli(self.root, "init")

    def test_auto_ignores_unreadable_public_handoff(self):
        run_cli(self.root, "takeover")
        path = self.root / "HANDOFF.md"
        path.write_text("---\nversion: 1\nstatus: BOGUS\n---\n", encoding="utf-8")
        _, _, err = run_cli(self.root, "--no-auto-install", "auto")
        self.assertNotIn("unreadable handoff", err)
        self.assertEqual(state.read(self.root).mode, "AUTO")

    def test_auto_resyncs_then_reports_missing_tmux(self):
        (self.root / "openspec" / "changes" / "demo").mkdir(parents=True)
        doc = handoff.empty_handoff()
        doc.next_action = "resolve u-ghost: stale"
        doc.next_spec = "demo"
        add_item(doc, "issue", "real work", priority="high", item_id="u-1")
        write_handoff(handoff_path(self.root), doc)
        run_cli(self.root, "takeover")
        # Deterministic missing-tmux simulation: the real `require_tmux`
        # raises on tmux-less hosts, but on tmux hosts `auto` would schedule
        # live provider input. Forcing the failure exercises the same
        # refusal path on every host with no live scheduling risk.
        with unittest.mock.patch.object(
            cli.tmux_setup_mod,
            "require_tmux",
            side_effect=TmuxSetupError("tmux executable `tmux` not found"),
        ):
            code, out, _ = run_cli(self.root, "--no-auto-install", "auto")
        self.assertNotEqual(code, 0)  # no tmux: loop cannot schedule
        self.assertEqual(state.read(self.root).mode, "AUTO")
        self.assertIn("resync", out)
        reloaded = handoff.read_handoff(handoff_path(self.root))
        self.assertTrue(reloaded.next_action.startswith("resolve-issue u-1"))


if __name__ == "__main__":
    unittest.main()
