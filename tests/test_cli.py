"""Tests for CLI lifecycle semantics and exit behavior."""

import io
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path

from ariadex import cli, config, state


def run_cli(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with chdir(root), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


def write_raw_config(root: Path, text: str) -> None:
    path = root / config.CONFIG_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class InitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_init_creates_defaults(self):
        code, out, _ = run_cli(self.root, "init")
        self.assertEqual(code, 0)
        self.assertIn("created", out)
        self.assertTrue((self.root / ".ariadex" / "config.yaml").is_file())
        self.assertTrue((self.root / ".ariadex" / "handoff.md").is_file())
        self.assertTrue((self.root / ".ariadex" / "state.json").is_file())

    def test_init_preserves_existing_files(self):
        write_raw_config(self.root, "agent_provider: codex\n")
        handoff = self.root / ".ariadex" / "handoff.md"
        handoff.parent.mkdir(parents=True, exist_ok=True)
        handoff.write_text("human content\n", encoding="utf-8")
        code, out, _ = run_cli(self.root, "init")
        self.assertEqual(code, 0)
        self.assertIn("preserved", out)
        self.assertIn("agent_provider: codex", (self.root / config.CONFIG_REL_PATH).read_text())
        self.assertEqual(handoff.read_text(encoding="utf-8"), "human content\n")

    def test_init_preserves_existing_state_session(self):
        run_cli(self.root, "init")
        before = state.read(self.root).session_id
        run_cli(self.root, "init")
        self.assertEqual(state.read(self.root).session_id, before)


class StatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        run_cli(self.root, "init")

    def test_status_reports_persisted_state(self):
        code, out, _ = run_cli(self.root, "status")
        self.assertEqual(code, 0)
        st = state.read(self.root)
        self.assertIn(st.mode, out)
        self.assertIn(st.session_id, out)
        self.assertIn("unresolved", out)

    def test_status_fails_without_state(self):
        (self.root / state.STATE_REL_PATH).unlink()
        code, _, err = run_cli(self.root, "status")
        self.assertNotEqual(code, 0)
        self.assertIn("state", err)

    def test_status_rejects_invalid_configuration(self):
        write_raw_config(self.root, "reset_mode: turbo\n")
        code, _, err = run_cli(self.root, "status")
        self.assertNotEqual(code, 0)
        self.assertIn("reset_mode", err)


class TransitionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        run_cli(self.root, "init")

    def mode(self) -> str:
        return state.read(self.root).mode

    def test_pause_is_idempotent_and_keeps_session(self):
        session = state.read(self.root).session_id
        self.assertEqual(run_cli(self.root, "pause")[0], 0)
        code, out, _ = run_cli(self.root, "pause")
        self.assertEqual(code, 0)
        self.assertIn("already PAUSE", out)
        self.assertEqual(self.mode(), "PAUSE")
        self.assertEqual(state.read(self.root).session_id, session)

    def test_resume_leaves_pause(self):
        run_cli(self.root, "pause")
        self.assertEqual(run_cli(self.root, "resume")[0], 0)
        self.assertEqual(self.mode(), "MANUAL")

    def test_takeover_enters_manual(self):
        run_cli(self.root, "auto")
        self.assertEqual(run_cli(self.root, "takeover")[0], 0)
        self.assertEqual(self.mode(), "MANUAL")

    def test_auto_enters_auto(self):
        self.assertEqual(run_cli(self.root, "auto")[0], 0)
        self.assertEqual(self.mode(), "AUTO")


class RunAttachTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        run_cli(self.root, "init")

    def test_run_without_supported_provider_fails(self):
        write_raw_config(self.root, "agent_provider: wat\n")
        code, _, err = run_cli(self.root, "run")
        self.assertNotEqual(code, 0)
        self.assertIn("wat", err)

    def test_run_does_not_claim_progress(self):
        code, out, err = run_cli(self.root, "run")
        self.assertNotEqual(code, 0)
        combined = out + err
        self.assertNotIn("complete", combined.lower().replace("not implemented", ""))
        self.assertIn("no work was started", combined)

    def test_run_refuses_paused_project(self):
        run_cli(self.root, "pause")
        code, _, err = run_cli(self.root, "run")
        self.assertNotEqual(code, 0)
        self.assertIn("PAUSED", err)

    def test_attach_reports_missing_driver(self):
        code, _, err = run_cli(self.root, "attach")
        self.assertNotEqual(code, 0)
        self.assertIn("tmux driver", err)


if __name__ == "__main__":
    unittest.main()
