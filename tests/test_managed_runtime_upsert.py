"""Regression tests for idempotent managed runtime reconciliation."""

import io
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ariadex import cli, config, state, widget_runtime

TOKEN = "widget-" + "token"


class WidgetRuntimeRecordTests(unittest.TestCase):
    def test_widget_record_round_trip_and_health(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = widget_runtime.WidgetRecord(
                project=str(root.resolve()),
                pid=123,
                process_start_ticks=456,
                token=TOKEN,
                daemon_pid=77,
                ready=True,
            )
            widget_runtime.write_record(root, record)
            self.assertEqual(widget_runtime.read_record(root), record)
            with mock.patch.object(
                widget_runtime,
                "process_identity",
                return_value=(123, 456, TOKEN),
            ):
                self.assertTrue(widget_runtime.is_healthy(root, record))

    def test_widget_record_rejects_process_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = widget_runtime.WidgetRecord(
                project=str(root.resolve()),
                pid=123,
                process_start_ticks=456,
                token=TOKEN,
                daemon_pid=77,
                ready=True,
            )
            with mock.patch.object(
                widget_runtime,
                "process_identity",
                return_value=(123, 999, "other-" + "token"),
            ):
                self.assertFalse(widget_runtime.is_healthy(root, record))


class ManagedStartRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        with (
            chdir(self.root),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(cli.main(["init"]), 0)

    def test_live_daemon_rerun_repairs_crashed_widget_without_new_session(self):
        cfg = config.load(self.root)
        st = state.read(self.root)
        replacement = object()
        with (
            mock.patch.object(
                cli.daemon_mod,
                "read_record",
                return_value=SimpleNamespace(pid=10, endpoint="sock", status="running"),
            ),
            mock.patch.object(cli.daemon_mod, "daemon_alive", return_value=True),
            mock.patch.object(cli, "_daemon_ipc_or_none", return_value={"ok": True}),
            mock.patch.object(
                cli.widget_runtime_mod,
                "ensure_widget",
                return_value=(replacement, True),
            ) as ensure,
            mock.patch.object(cli.terminal_mod, "TmuxDriver") as driver_type,
            mock.patch.object(cli, "_has_terminal", return_value=True),
            mock.patch.object(cli, "_attach_session", return_value=0) as attach,
        ):
            driver_type.return_value.session_alive.return_value = True
            driver_type.return_value.attach_command.return_value = ["tmux", "attach"]
            code = cli.cmd_start(self.root)
        self.assertEqual(code, cli.EXIT_OK)
        ensure.assert_called_once_with(self.root, cfg, st)
        attach.assert_called_once()

    def test_start_help_hides_internal_lifecycle_commands(self):
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            cli.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        text = output.getvalue()
        for command in (
            "run",
            "attach",
            "status",
            "pause",
            "resume",
            "stop",
            "companion",
            "watch",
        ):
            self.assertNotIn(f"  {command}", text)
        self.assertIn("  init", text)
        self.assertIn("  start", text)
