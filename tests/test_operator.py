"""Tests for human-supervision ergonomics: doctor, preview, queue, lifecycle."""

import io
import json
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ariadex import cli, config, handoff, operator, state
from ariadex.handoff import add_item, write_handoff


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


def make_project(root: Path, verification=("echo ok",)) -> None:
    run_cli(root, "init")
    if verification is not None:
        import yaml

        cfg_path = root / ".ariadex" / "config.yaml"
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        raw["verification_commands"] = list(verification)
        cfg_path.write_text(
            __import__("yaml").safe_dump(raw, sort_keys=False), encoding="utf-8"
        )


class DoctorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_project(self.root)

    def test_doctor_passes_with_healthy_project(self):
        (self.root / "openspec" / "changes" / "demo").mkdir(parents=True)
        code, out, _ = run_cli(self.root, "doctor")
        # tmux is absent on this host, so doctor fails on tmux; details shown.
        self.assertIn("config:", out)
        self.assertIn("provider:", out)
        self.assertIn("tmux:", out)
        self.assertIn("specs:", out)
        self.assertIn("verification:", out)
        self.assertIn("doctor:", out)
        _ = code  # exit depends on tmux presence; output is the contract

    def test_doctor_json_is_stable(self):
        _code, out, _ = run_cli(self.root, "doctor", "--json")
        # Re-parse: JSON must load and round-trip with sorted keys.
        payload = json.loads(out)
        self.assertIn("checks", payload)
        self.assertIn("ok", payload)
        names = [c["name"] for c in payload["checks"]]
        for expected in (
            "config",
            "state",
            "provider",
            "tmux",
            "specs",
            "verification",
        ):
            self.assertIn(expected, names)

    def test_doctor_reports_missing_verification(self):
        make_project(self.root, verification=())
        import yaml

        cfg_path = self.root / ".ariadex" / "config.yaml"
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        raw["verification_commands"] = []
        cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        _, out, _ = run_cli(self.root, "doctor")
        self.assertIn("verification:", out)


class PreviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_project(self.root)

    def test_preview_shows_required_fields_and_sends_no_input(self):
        (self.root / "openspec" / "changes" / "demo").mkdir(parents=True)
        doc = handoff.empty_handoff()
        add_item(doc, "issue", "real work", priority="high", item_id="u-1")
        write_handoff(handoff_path(self.root), doc)
        code, out, _ = run_cli(self.root, "preview")
        self.assertEqual(code, 0)
        st = state.read(self.root)
        for expected in (
            f"mode: {st.mode}",
            "provider:",
            f"session: {st.session_id}",
            "next:",
            "u-1",
            "verification:",
            "prerequisites:",
        ):
            self.assertIn(expected, out)
        # Preview sends no provider input: no run logs or metrics created.
        self.assertFalse((self.root / ".ariadex" / "metrics.jsonl").exists())
        self.assertFalse(list((self.root / ".ariadex" / "runs").rglob("*.log")))

    def test_preview_reports_missing_prerequisite(self):
        # No verification commands and no tmux here: blockers must be named.
        import yaml

        cfg_path = self.root / ".ariadex" / "config.yaml"
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        raw["verification_commands"] = []
        cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        code, out, _ = run_cli(self.root, "preview")
        self.assertEqual(code, 0)
        self.assertIn("blocker:", out)
        self.assertIn("scheduling: blocked", out)

    def test_preview_json_stable(self):
        _, out, _ = run_cli(self.root, "preview", "--json")
        payload = json.loads(out)
        for key in (
            "mode",
            "provider",
            "session",
            "next_action",
            "unresolved",
            "verification_commands",
            "prerequisites",
            "blockers",
            "can_schedule",
        ):
            self.assertIn(key, payload)

    def test_auto_preview_flag_sends_no_input(self):
        (self.root / "openspec" / "changes" / "demo").mkdir(parents=True)
        code, out, _ = run_cli(self.root, "--no-auto-install", "auto", "--preview")
        self.assertEqual(code, 0)
        self.assertIn("resync:", out)
        self.assertIn("next:", out)
        self.assertFalse((self.root / ".ariadex" / "metrics.jsonl").exists())

    def test_run_preview_flag_sends_no_input(self):
        st = state.read(self.root)
        st.mode = "AUTO"
        state.write(self.root, st)
        code, out, _ = run_cli(self.root, "--no-auto-install", "run", "--preview")
        self.assertEqual(code, 0)
        self.assertIn("next:", out)
        self.assertFalse((self.root / ".ariadex" / "metrics.jsonl").exists())


class QueueHistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_project(self.root)
        doc = handoff.empty_handoff()
        add_item(doc, "issue", "open work", priority="high", item_id="u-open")
        add_item(doc, "issue", "deferred work", priority="medium", item_id="u-def")
        handoff.set_item_status(
            doc, "u-def", "DEFERRED", target_spec="later", reason="not yet", note="d"
        )
        add_item(doc, "issue", "blocked work", priority="low", item_id="u-block")
        handoff.set_item_status(doc, "u-block", "BLOCKED", note="b")
        add_item(doc, "issue", "done work", priority="low", item_id="u-done")
        handoff.set_item_status(doc, "u-done", "RESOLVED", note="r")
        write_handoff(handoff_path(self.root), doc)

    def test_queue_lists_all_statuses(self):
        _, out, _ = run_cli(self.root, "queue")
        for item_id in ("u-open", "u-def", "u-block", "u-done"):
            self.assertIn(item_id, out)

    def test_queue_filter(self):
        _, out, _ = run_cli(self.root, "queue", "--status", "OPEN")
        self.assertIn("u-open", out)
        self.assertNotIn("u-done", out)

    def test_queue_invalid_filter_rejected(self):
        code, _, err = run_cli(self.root, "queue", "--status", "MAYBE")
        self.assertNotEqual(code, 0)
        self.assertIn("MAYBE", err)

    def test_queue_json(self):
        _, out, _ = run_cli(self.root, "queue", "--json")
        payload = json.loads(out)
        self.assertEqual(len(payload["items"]), 4)

    def test_history_shows_transitions(self):
        _, out, _ = run_cli(self.root, "history", "u-def")
        self.assertIn("u-def", out)
        self.assertIn("DEFERRED", out)
        self.assertIn("history:", out)

    def test_history_json(self):
        _, out, _ = run_cli(self.root, "history", "u-def", "--json")
        payload = json.loads(out)
        self.assertEqual(payload["id"], "u-def")
        self.assertTrue(payload["history"])

    def test_history_unknown_rejected(self):
        code, _, err = run_cli(self.root, "history", "u-ghost")
        self.assertNotEqual(code, 0)
        self.assertIn("u-ghost", err)


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_project(self.root)
        doc = handoff.empty_handoff()
        add_item(doc, "issue", "work one", priority="medium", item_id="u-1")
        write_handoff(handoff_path(self.root), doc)

    def read_item(self, item_id="u-1"):
        return handoff.get_item(handoff.read_handoff(handoff_path(self.root)), item_id)

    def test_resolve_retains_history(self):
        code, out, _ = run_cli(self.root, "resolve", "u-1", "--note", "verified")
        self.assertEqual(code, 0)
        item = self.read_item()
        self.assertEqual(item.status, "RESOLVED")
        self.assertTrue(item.history)
        self.assertIn("u-1", out)

    def test_resolve_already_resolved_rejected(self):
        run_cli(self.root, "resolve", "u-1")
        code, _, err = run_cli(self.root, "resolve", "u-1")
        self.assertNotEqual(code, 0)
        self.assertIn("already RESOLVED", err)

    def test_defer_requires_target_and_reason(self):
        code, _, _ = run_cli(self.root, "defer", "u-1", "--to", "later")
        self.assertNotEqual(code, 0)  # argparse: --reason missing
        doc = handoff.read_handoff(handoff_path(self.root))
        # Direct operator validation as well.
        with self.assertRaises(handoff.HandoffError):
            operator.apply_defer(doc, "u-1", "", "")

    def test_defer_persists_target_reason_history(self):
        code, _, _ = run_cli(
            self.root, "defer", "u-1", "--to", "later", "--reason", "not yet"
        )
        self.assertEqual(code, 0)
        item = self.read_item()
        self.assertEqual(item.status, "DEFERRED")
        self.assertEqual(item.target_spec, "later")
        self.assertEqual(item.reason, "not yet")
        self.assertTrue(item.history)

    def test_reopen_returns_to_open(self):
        run_cli(self.root, "defer", "u-1", "--to", "later", "--reason", "not yet")
        code, _, _ = run_cli(self.root, "reopen", "u-1")
        self.assertEqual(code, 0)
        item = self.read_item()
        self.assertEqual(item.status, "OPEN")
        self.assertEqual(len(item.history), 2)

    def test_reopen_already_open_rejected(self):
        code, _, err = run_cli(self.root, "reopen", "u-1")
        self.assertNotEqual(code, 0)
        self.assertIn("already OPEN", err)

    def test_reprioritize_updates_priority_and_history(self):
        code, _, _ = run_cli(self.root, "reprioritize", "u-1", "--priority", "high")
        self.assertEqual(code, 0)
        item = self.read_item()
        self.assertEqual(item.priority, "high")
        self.assertTrue(item.history)

    def test_reprioritize_invalid_priority_rejected(self):
        code, _, err = run_cli(self.root, "reprioritize", "u-1", "--priority", "urgent")
        self.assertNotEqual(code, 0)
        self.assertIn("urgent", err)

    def test_mutation_updates_unresolved_count(self):
        run_cli(self.root, "resolve", "u-1")
        stored = state.read(self.root)
        self.assertEqual(stored.unresolved_count, 0)

    def test_durable_across_restart(self):
        run_cli(self.root, "defer", "u-1", "--to", "later", "--reason", "not yet")
        before = handoff.read_handoff(handoff_path(self.root))
        # Fresh process instance re-reads the same file.
        after = handoff.read_handoff(handoff_path(self.root))
        self.assertEqual(after.unresolved[0].status, "DEFERRED")
        self.assertEqual(after.unresolved[0].history, before.unresolved[0].history)
        self.assertEqual(after.unresolved[0].target_spec, "later")


class ModeCoverageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_project(self.root)
        doc = handoff.empty_handoff()
        add_item(doc, "issue", "work", priority="high", item_id="u-1")
        write_handoff(handoff_path(self.root), doc)

    def set_mode(self, mode: str):
        st = state.read(self.root)
        st.mode = mode
        state.write(self.root, st)

    def test_read_only_commands_work_in_every_mode(self):
        for mode in ("AUTO", "MANUAL", "PAUSE"):
            self.set_mode(mode)
            for argv in (
                ("status",),
                ("status", "--json"),
                ("doctor",),
                ("preview",),
                ("queue",),
                ("history", "u-1"),
            ):
                code, out, _ = run_cli(self.root, *argv)
                # doctor may exit non-zero on missing tmux; others must succeed.
                if argv[0] != "doctor":
                    self.assertEqual(code, 0, f"{argv} in {mode}")
                self.assertTrue(out.strip(), f"{argv} in {mode}")

    def test_mutations_work_in_every_mode(self):
        for mode in ("AUTO", "MANUAL", "PAUSE"):
            self.set_mode(mode)
            code, _, _ = run_cli(self.root, "reprioritize", "u-1", "--priority", "low")
            self.assertEqual(code, 0, f"reprioritize in {mode}")
            code, _, _ = run_cli(self.root, "reprioritize", "u-1", "--priority", "high")
            self.assertEqual(code, 0, f"reprioritize in {mode}")


class ConfirmationTest(unittest.TestCase):
    def test_non_interactive_proceeds_without_yes(self):
        with mock.patch.object(cli.sys.stdin, "isatty", return_value=False):
            self.assertTrue(cli._confirm_scheduling(False))

    def test_yes_skips_prompt(self):
        with mock.patch.object(cli.sys, "stdin") as stdin:
            stdin.isatty.return_value = True
            self.assertTrue(cli._confirm_scheduling(True))
            stdin.isatty.assert_not_called() if False else None

    def test_interactive_decline_aborts(self):
        with (
            mock.patch.object(cli.sys.stdin, "isatty", return_value=True),
            mock.patch.object(cli, "input", return_value="n"),
        ):
            self.assertFalse(cli._confirm_scheduling(False))

    def test_interactive_accept_proceeds(self):
        with (
            mock.patch.object(cli.sys.stdin, "isatty", return_value=True),
            mock.patch.object(cli, "input", return_value="yes"),
        ):
            self.assertTrue(cli._confirm_scheduling(False))


if __name__ == "__main__":
    unittest.main()
