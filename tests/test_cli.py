"""Tests for CLI lifecycle semantics and exit behavior."""

import io
import re
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

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
        self.assertTrue((self.root / "HANDOFF.md").is_file())
        self.assertTrue((self.root / ".ariadex" / "state.json").is_file())

    def test_init_creates_custom_handoff_path(self):
        write_raw_config(self.root, "handoff_file: docs/NEXT.md\n")
        code, out, _ = run_cli(self.root, "init")
        self.assertEqual(code, 0)
        self.assertIn("docs/NEXT.md", out)
        self.assertTrue((self.root / "docs" / "NEXT.md").is_file())

    def test_init_preserves_existing_files(self):
        write_raw_config(self.root, "agent_provider: codex\n")
        handoff = self.root / "HANDOFF.md"
        handoff.write_text("human content\n", encoding="utf-8")
        code, out, _ = run_cli(self.root, "init")
        self.assertEqual(code, 0)
        self.assertIn("preserved", out)
        text = (self.root / config.CONFIG_REL_PATH).read_text()
        self.assertIn("agent_provider: codex", text)
        self.assertEqual(handoff.read_text(encoding="utf-8"), "human content\n")

    def test_init_preserves_existing_state_session(self):
        run_cli(self.root, "init")
        before = state.read(self.root).session_id
        code, _, err = run_cli(self.root, "init")
        self.assertNotEqual(code, 0)
        self.assertIn("init --force", err)
        self.assertEqual(state.read(self.root).session_id, before)


class WidgetCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tkinter = mock.patch(
            "ariadex.cli.companion_mod.tkinter_available", return_value=True
        )
        self.tkinter.start()
        self.addCleanup(self.tkinter.stop)

    def test_widget_is_hidden_from_top_level_help(self):
        code, out, _ = run_cli(self.root, "--help")
        self.assertEqual(code, 0)
        self.assertIsNone(re.search(r"^\s+widget(\s|$)", out, re.MULTILINE))

    def test_widget_is_internal_to_managed_start(self):
        code, out, _ = run_cli(self.root, "admin")
        self.assertEqual(code, 0)
        self.assertNotIn("widget", out)
        self.assertIn("doctor", out)

    def test_widget_defaults_to_current_directory(self):
        with (
            mock.patch("ariadex.cli.cmd_init", return_value=0) as init,
            mock.patch("ariadex.cli._start_daemon_only", return_value=0) as start,
            mock.patch("ariadex.cli.cmd_companion", return_value=0) as companion,
        ):
            code, _, _ = run_cli(self.root, "admin", "widget")
        self.assertEqual(code, 0)
        init.assert_called_once_with(self.root)
        start.assert_called_once_with(self.root)
        companion.assert_called_once_with(self.root, hotkey=None, editor=None)

    def test_widget_accepts_optional_project_path(self):
        project = self.root / "project"
        with (
            mock.patch("ariadex.cli.cmd_init", return_value=0) as init,
            mock.patch("ariadex.cli._start_daemon_only", return_value=0) as start,
            mock.patch("ariadex.cli.cmd_companion", return_value=0) as companion,
        ):
            code, _, _ = run_cli(
                self.root, "admin", "widget", "--project", str(project)
            )
        self.assertEqual(code, 0)
        init.assert_called_once_with(project)
        start.assert_called_once_with(project)
        companion.assert_called_once_with(project, hotkey=None, editor=None)

    def test_widget_stops_when_daemon_start_fails(self):
        with (
            mock.patch("ariadex.cli.cmd_init", return_value=0) as init,
            mock.patch("ariadex.cli._start_daemon_only", return_value=1) as start,
            mock.patch("ariadex.cli.cmd_companion", return_value=0) as companion,
        ):
            code, _, _ = run_cli(self.root, "admin", "widget")
        self.assertEqual(code, 1)
        init.assert_called_once_with(self.root)
        start.assert_called_once_with(self.root)
        companion.assert_not_called()

    def test_widget_reuses_existing_daemon(self):
        with (
            mock.patch("ariadex.cli.cmd_init", return_value=0),
            mock.patch("ariadex.cli._daemon_ipc_or_none", return_value={"ok": True}),
            mock.patch("ariadex.cli._start_daemon_only", return_value=0) as start,
            mock.patch("ariadex.cli.cmd_companion", return_value=0) as companion,
        ):
            code, _, _ = run_cli(self.root, "admin", "widget")
        self.assertEqual(code, 0)
        start.assert_not_called()
        companion.assert_called_once_with(self.root, hotkey=None, editor=None)

    def test_widget_does_not_start_daemon_when_tkinter_is_missing(self):
        with (
            mock.patch("ariadex.cli.cmd_init", return_value=0) as init,
            mock.patch(
                "ariadex.cli.companion_mod.tkinter_available", return_value=False
            ),
            mock.patch("ariadex.cli.tmux_setup_mod.detect_manager", return_value=None),
            mock.patch("ariadex.cli._start_daemon_only", return_value=0) as start,
        ):
            code, _, err = run_cli(self.root, "admin", "widget")
        self.assertEqual(code, 1)
        init.assert_called_once_with(self.root)
        start.assert_not_called()
        self.assertIn("Tkinter is not installed", err)


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
        self.assertEqual(self.mode(), "AUTO")

    def test_takeover_enters_manual(self):
        run_cli(self.root, "--no-auto-install", "auto")
        self.assertEqual(run_cli(self.root, "takeover")[0], 0)
        self.assertEqual(self.mode(), "MANUAL")

    def test_auto_enters_auto(self):
        run_cli(self.root, "--no-auto-install", "auto")
        self.assertEqual(self.mode(), "AUTO")


class RunAttachTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        run_cli(self.root, "init")

    def test_run_without_supported_provider_fails(self):
        write_raw_config(self.root, "agent_provider: wat\n")
        st = state.read(self.root)
        st.mode = "AUTO"
        state.write(self.root, st)
        code, _, err = run_cli(self.root, "--no-auto-install", "run")
        self.assertNotEqual(code, 0)
        self.assertIn("wat", err)

    def test_run_does_not_claim_progress(self):
        st = state.read(self.root)
        st.mode = "AUTO"
        state.write(self.root, st)
        code, out, err = run_cli(self.root, "--no-auto-install", "run")
        self.assertNotEqual(code, 0)
        combined = out + err
        self.assertNotIn("complete", combined.lower())
        # Either the tmux prerequisite stops the run, or the runner stops
        # safely (blocker/idle/unverified) without advancing work.
        self.assertTrue(
            "tmux" in combined
            or "blocked" in combined
            or "idle" in combined
            or "verification" in combined,
            combined,
        )

    def test_run_refuses_paused_project(self):
        run_cli(self.root, "pause")
        code, _, err = run_cli(self.root, "--no-auto-install", "run")
        self.assertNotEqual(code, 0)
        self.assertIn("PAUSED", err)

    def test_attach_reports_missing_driver(self):
        code, _, err = run_cli(self.root, "--no-auto-install", "attach")
        self.assertNotEqual(code, 0)
        self.assertIn("attach is unavailable", err)


if __name__ == "__main__":
    unittest.main()
