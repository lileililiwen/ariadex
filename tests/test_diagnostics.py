"""Comprehensive runtime diagnostics: schema, storage, CLI, instrumentation."""

import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from ariadex import diagnostics
from ariadex.diagnostics import DIAGNOSTIC_SCHEMA_VERSION

try:
    import evidence_fakes
except ModuleNotFoundError:
    from tests import evidence_fakes  # type: ignore[no-redef]


def make_record(category="boundary", action="test action", **overrides):
    params = {"category": category, "action": action}
    params.update(overrides)
    return diagnostics.build_diagnostic(**params)


class SchemaTest(unittest.TestCase):
    def test_record_has_versioned_stable_keys(self):
        record = make_record(
            "prompt",
            "sent initial prompt",
            result="sent",
            current_spec="demo",
        )
        self.assertEqual(record["schema_version"], DIAGNOSTIC_SCHEMA_VERSION)
        self.assertEqual(
            sorted(record),
            sorted(
                [
                    "schema_version",
                    "at",
                    "category",
                    "action",
                    "result",
                    "message",
                    "provider",
                    "session",
                    "phase",
                    "conversation_id",
                    "current_spec",
                    "open_tasks",
                    "closed_tasks",
                    "command_role",
                    "recovery",
                    "redactions",
                    "classification",
                    "active_queue",
                    "evidence_source",
                    "decision",
                    "blocker",
                    "operation",
                    "next_action",
                    "requested_path",
                    "normalized_path",
                    "policy",
                    "details",
                ]
            ),
        )

    def test_unknown_category_maps_to_error(self):
        record = make_record("nope", "x")
        self.assertEqual(record["category"], "error")

    def test_secret_redacted_with_count(self):
        record = make_record(
            "boundary",
            "blocked",
            message="token=supersecret-value-here",
        )
        self.assertNotIn("supersecret-value-here", record["message"])
        self.assertIn("<redacted>", record["message"])
        self.assertGreaterEqual(record["redactions"], 1)

    def test_long_fields_truncated(self):
        record = make_record("prompt", "a" * 5000)
        self.assertLessEqual(len(record["action"]), 2200)
        self.assertIn("truncated", record["action"])

    def test_details_are_bounded_and_redacted(self):
        record = make_record(
            "provider",
            "provider session ended",
            details={"pid": 42, "capture_tail": "token=secret " * 500},
        )
        self.assertEqual(record["details"]["pid"], 42)
        self.assertNotIn("secret", record["details"]["capture_tail"])
        self.assertLessEqual(len(record["details"]["capture_tail"]), 2200)


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_round_trip_oldest_first_with_limit(self):
        for index in range(5):
            diagnostics.record_diagnostic(
                self.root, make_record(action=f"step {index}")
            )
        records, info = diagnostics.read_diagnostics(self.root, limit=3)
        self.assertEqual([r["action"] for r in records], ["step 2", "step 3", "step 4"])
        self.assertEqual(info["malformed_skipped"], 0)

    def test_limit_zero_shows_none(self):
        diagnostics.record_diagnostic(self.root, make_record())
        records, _ = diagnostics.read_diagnostics(self.root, limit=0)
        self.assertEqual(records, [])

    def test_malformed_lines_skipped_and_counted(self):
        diagnostics.record_diagnostic(self.root, make_record(action="good"))
        stream = diagnostics.diagnostics_path(self.root)
        with open(stream, "a", encoding="utf-8") as handle:
            handle.write("not json at all\n")
            handle.write("[1, 2]\n")
        diagnostics.record_diagnostic(self.root, make_record(action="good2"))
        records, info = diagnostics.read_diagnostics(self.root)
        self.assertEqual([r["action"] for r in records], ["good", "good2"])
        self.assertEqual(info["malformed_skipped"], 2)

    def test_missing_stream_is_honest_unavailable(self):
        records, info = diagnostics.read_diagnostics(self.root)
        self.assertEqual(records, [])
        self.assertIn("unavailable", info)
        text = diagnostics.format_diagnostics_text(records, info)
        self.assertIn("unavailable", text)

    def test_category_and_since_filters(self):
        old = make_record("startup", "boot")
        old["at"] = "2001-01-01T00:00:00+00:00"
        diagnostics.record_diagnostic(self.root, old)
        diagnostics.record_diagnostic(self.root, make_record("prompt", "sent"))
        records, _ = diagnostics.read_diagnostics(self.root, categories=("prompt",))
        self.assertEqual([r["action"] for r in records], ["sent"])
        records, _ = diagnostics.read_diagnostics(
            self.root, since="2020-01-01T00:00:00+00:00"
        )
        self.assertEqual([r["action"] for r in records], ["sent"])

    def test_concurrent_writers_never_interleave(self):
        def worker(n):
            for i in range(25):
                diagnostics.record_diagnostic(
                    self.root, make_record(action=f"w{n} line {i}")
                )

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        records, info = diagnostics.read_diagnostics(self.root, limit=-1)
        self.assertEqual(len(records), 100)
        self.assertEqual(info["malformed_skipped"], 0)

    def test_try_record_reports_failure_without_raising(self):
        stream = diagnostics.diagnostics_path(self.root)
        stream.parent.mkdir(parents=True, exist_ok=True)
        stream.mkdir()  # a directory at the stream path breaks appends
        self.assertFalse(diagnostics.try_record(self.root, make_record(action="x")))

    def test_retention_prunes_oldest_first(self):
        old = make_record(action="old")
        old["at"] = "2001-01-01T00:00:00+00:00"
        diagnostics.record_diagnostic(self.root, old)
        diagnostics.record_diagnostic(self.root, make_record(action="new"))
        report = diagnostics.apply_retention(self.root, retention_days=30)
        self.assertEqual(report["removed_lines"], 1)
        records, _ = diagnostics.read_diagnostics(self.root)
        self.assertEqual([r["action"] for r in records], ["new"])

    def test_retention_keeps_malformed_for_age_but_trims_for_size(self):
        diagnostics.record_diagnostic(self.root, make_record(action="good"))
        stream = diagnostics.diagnostics_path(self.root)
        with open(stream, "a", encoding="utf-8") as handle:
            handle.write("broken line\n")
        report = diagnostics.apply_retention(self.root, max_bytes=10)
        self.assertGreaterEqual(report["removed_lines"], 1)
        self.assertLessEqual(stream.stat().st_size, 10 + 200)

    def test_secure_permissions(self):
        diagnostics.record_diagnostic(self.root, make_record())
        stream = diagnostics.diagnostics_path(self.root)
        import os

        if os.name != "nt":
            self.assertEqual(stream.stat().st_mode & 0o777, 0o600)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def init_project(self):
        from ariadex import cli as cli_mod

        self.assertEqual(cli_mod.cmd_init(self.root), 0)

    def run_cmd(self, func, *args, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = func(*args, **kwargs)
        return code, out.getvalue(), err.getvalue()

    def test_diagnostics_empty_stream_reports_unavailable(self):
        from ariadex import cli as cli_mod

        self.init_project()
        code, out, _ = self.run_cmd(cli_mod.cmd_diagnostics, self.root)
        self.assertEqual(code, 0)
        self.assertIn("unavailable", out)

    def test_diagnostics_text_and_json(self):
        from ariadex import cli as cli_mod

        self.init_project()
        diagnostics.record_diagnostic(
            self.root, make_record("boundary", "verified", result="complete")
        )
        code, out, _ = self.run_cmd(cli_mod.cmd_diagnostics, self.root)
        self.assertEqual(code, 0)
        self.assertIn("verified", out)
        code, out, _ = self.run_cmd(cli_mod.cmd_diagnostics, self.root, as_json=True)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(len(payload["records"]), 1)

    def test_diagnostics_rejects_unknown_category_and_negative_limit(self):
        from ariadex import cli as cli_mod

        self.init_project()
        code, _, err = self.run_cmd(
            cli_mod.cmd_diagnostics, self.root, categories=["nope"]
        )
        self.assertEqual(code, 1)
        self.assertIn("unknown", err)
        code, _, err = self.run_cmd(cli_mod.cmd_diagnostics, self.root, limit=-1)
        self.assertEqual(code, 1)
        self.assertIn("--limit", err)

    def test_export_bundle_manifest_and_redaction(self):
        from ariadex import cli as cli_mod

        self.init_project()
        diagnostics.record_diagnostic(
            self.root,
            make_record(
                "boundary", "blocked", message="api_key=supersecret-value-here"
            ),
        )
        dest = self.root / "bundle"
        code, _, _ = self.run_cmd(
            cli_mod.cmd_export_diagnostics, self.root, out=str(dest)
        )
        self.assertEqual(code, 0)
        bundle = json.loads((dest / "bundle.json").read_text(encoding="utf-8"))
        self.assertEqual(bundle["schema_version"], DIAGNOSTIC_SCHEMA_VERSION)
        self.assertIn("state", bundle)
        self.assertIn("openspec", bundle)
        self.assertIn("diagnostics", bundle)
        self.assertIn("metrics_summary", bundle)
        self.assertNotIn("supersecret-value-here", (dest / "bundle.json").read_text())
        manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], DIAGNOSTIC_SCHEMA_VERSION)

    def test_export_bundle_refuses_above_bound(self):
        from ariadex import cli as cli_mod

        self.init_project()
        diagnostics.record_diagnostic(self.root, make_record())
        code, _, err = self.run_cmd(
            cli_mod.cmd_export_diagnostics,
            self.root,
            out=str(self.root / "b"),
            max_bytes=10,
        )
        self.assertEqual(code, 1)
        self.assertIn("refused", err)

    def test_export_with_telemetry(self):
        from ariadex import cli as cli_mod

        self.init_project()
        dest = self.root / "bundle2"
        code, out, _ = self.run_cmd(
            cli_mod.cmd_export_diagnostics,
            self.root,
            out=str(dest),
            with_telemetry=True,
            as_json=True,
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIn("telemetry", payload)

    def test_admin_aliases_route(self):
        from ariadex import cli as cli_mod

        self.init_project()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli_mod.cmd_admin(self.root, ["diagnostics"], False)
        self.assertEqual(code, 0)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli_mod.cmd_admin(
                self.root,
                ["export-diagnostics", "--out", str(self.root / "b3")],
                False,
            )
        self.assertEqual(code, 0)


class InstrumentationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_blocked_boundary_records_diagnostics_without_input(self):
        from ariadex import handoff as handoff_mod
        from ariadex import providers as providers_mod
        from ariadex import robot as robot_mod
        from ariadex import terminal as terminal_mod

        (self.root / ".ariadex").mkdir(parents=True)
        handoff_mod.write_handoff(
            self.root / "HANDOFF.md", handoff_mod.empty_handoff("s")
        )
        (self.root / "openspec" / "changes").mkdir(parents=True)
        driver = terminal_mod.FakeTerminalDriver()
        adapter = providers_mod.get_adapter("opencode", driver, "agent", self.root)
        config = robot_mod.RobotConfig(
            session="agent",
            provider="opencode",
            initial_prompt="please start",
            debounce_polls=1,
            poll_interval_s=0.01,
        )
        watcher = robot_mod.RobotWatcher(
            self.root,
            config,
            driver,
            adapter,
            evidence_runner=evidence_fakes.make_runner(self.root),
        )
        watcher._diag("startup", "watcher started", result="started")
        watcher.request_pause()
        watcher.request_resume()
        records, _ = diagnostics.read_diagnostics(self.root, limit=-1)
        categories = [r["category"] for r in records]
        self.assertIn("startup", categories)
        self.assertIn("pause", categories)
        self.assertEqual(watcher.prompts_sent, 0)
        sends = [c for c in driver.calls if c[0] == "send"]
        self.assertEqual(sends, [])

    def test_diagnostic_failure_never_changes_scheduling(self):
        from ariadex import handoff as handoff_mod
        from ariadex import providers as providers_mod
        from ariadex import robot as robot_mod
        from ariadex import terminal as terminal_mod

        (self.root / ".ariadex").mkdir(parents=True)
        handoff_mod.write_handoff(
            self.root / "HANDOFF.md", handoff_mod.empty_handoff("s")
        )
        (self.root / "openspec" / "changes").mkdir(parents=True)
        stream = diagnostics.diagnostics_path(self.root)
        stream.parent.mkdir(parents=True, exist_ok=True)
        stream.mkdir()  # break the stream: every record fails
        driver = terminal_mod.FakeTerminalDriver()
        adapter = providers_mod.get_adapter("opencode", driver, "agent", self.root)
        config = robot_mod.RobotConfig(
            session="agent",
            provider="opencode",
            initial_prompt="please start",
        )
        watcher = robot_mod.RobotWatcher(self.root, config, driver, adapter)
        watcher.request_pause()
        self.assertTrue(watcher.paused)
        self.assertEqual(watcher.phase, robot_mod.PAUSED)


if __name__ == "__main__":
    unittest.main()
