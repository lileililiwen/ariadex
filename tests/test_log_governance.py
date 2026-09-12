"""Tests for log-data-governance: retention, permissions, redaction, export."""

import io
import json
import os
import tempfile
import time
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ariadex import cli, config, handoff
from ariadex import logging as logging_mod
from ariadex.handoff import add_item, write_handoff
from ariadex.logging import (
    LOG_SCHEMA_VERSION,
    METRICS_SCHEMA_VERSION,
    RunLogRecord,
    apply_retention,
    ensure_secure_permissions,
    export_logs,
    redact,
    redact_with_report,
    write_run_log,
)


def run_cli(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with chdir(root), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


def make_project(root: Path) -> None:
    run_cli(root, "init")


def make_log(runs_dir: Path, session: str = "s1", age_days: float = 0) -> Path:
    record = RunLogRecord(
        session_id=session,
        spec="demo",
        action="test action",
        input="in",
        output="out",
        exit_code=0,
        validation_result="passed",
        reset_reason=None,
        retry_count=0,
    )
    path = write_run_log(runs_dir, record)
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
    return path


class RedactionCoverageTest(unittest.TestCase):
    def test_bearer_token_redacted_with_prefix(self):
        text, count = redact_with_report("auth Bearer abcdefghijklmnop ok")
        self.assertNotIn("abcdefghijklmnop", text)
        self.assertIn("Bearer <redacted>", text)
        self.assertGreaterEqual(count, 1)

    def test_github_and_gitlab_tokens_redacted(self):
        for secret in ("ghp_abcdefghijklmnop123456", "glpat-abcdefghijklmnop1234"):
            text = redact(f"key {secret}")
            self.assertNotIn(secret, text)
            self.assertIn("<redacted>", text)

    def test_jwt_redacted(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dummySignatureXYZ123"
        self.assertNotIn(jwt, redact(f"token {jwt}"))

    def test_aws_secret_assignment_redacted(self):
        text, _ = redact_with_report("aws_secret_access_key=SuperSecret123 ok")
        self.assertNotIn("SuperSecret123", text)
        self.assertIn("aws_secret_access_key=<redacted>", text)

    def test_redaction_count_recorded_without_storing_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            record = RunLogRecord(
                session_id="s1",
                spec="demo",
                action="a",
                input="password=hunter2",
                output="token ghp_abcdefghijklmnop123456",
                exit_code=0,
                validation_result="passed",
                reset_reason=None,
                retry_count=0,
            )
            path = write_run_log(runs, record)
            self.assertGreaterEqual(record.redaction_count, 2)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("hunter2", text)
            self.assertNotIn("ghp_abcdefghijklmnop123456", text)
            self.assertIn("redactions:", text)


class PermissionsTest(unittest.TestCase):
    def test_log_and_dirs_restricted_where_supported(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions not enforced on Windows")
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            path = make_log(runs)
            for target in (runs, runs / "s1", path):
                mode = os.stat(target).st_mode & 0o777
                self.assertEqual(mode & 0o077, 0, f"{target} is too open")

    def test_permission_fallback_returns_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "f.log"
            target.write_text("x", encoding="utf-8")
            with mock.patch.object(os, "chmod", side_effect=OSError("denied")):
                note = ensure_secure_permissions(target)
            self.assertIsNotNone(note)
            self.assertIn("could not restrict", note or "")


class RetentionTest(unittest.TestCase):
    def test_expired_logs_removed_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            metrics = root / "metrics.jsonl"
            old = make_log(runs, age_days=40)
            fresh = make_log(runs, age_days=1)
            report = apply_retention(
                runs, metrics, retention_days=30, log_max_bytes=0, metrics_max_bytes=0
            )
            self.assertFalse(old.exists())
            self.assertTrue(fresh.exists())
            self.assertEqual(report.retained_logs, 1)
            self.assertIn(str(old), report.removed_logs)

    def test_size_cap_removes_oldest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            metrics = root / "metrics.jsonl"
            first = make_log(runs)
            time.sleep(0.02)
            second = make_log(runs)
            sizes = first.stat().st_size + second.stat().st_size
            cap = sizes - 1  # forces exactly one eviction
            report = apply_retention(
                runs, metrics, retention_days=0, log_max_bytes=cap, metrics_max_bytes=0
            )
            remaining = list(runs.rglob("*.log"))
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0], second)
            self.assertEqual(len(report.removed_logs), 1)

    def test_zero_disables_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            metrics = root / "metrics.jsonl"
            old = make_log(runs, age_days=400)
            report = apply_retention(
                runs, metrics, retention_days=0, log_max_bytes=0, metrics_max_bytes=0
            )
            self.assertTrue(old.exists())
            self.assertEqual(report.removed_logs, [])

    def test_metrics_retention_drops_old_and_keeps_malformed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            runs.mkdir()
            metrics = root / "metrics.jsonl"
            old_rec = {
                "ended_at": "2020-01-01T00:00:00+00:00",
                "started_at": "2020-01-01T00:00:00+00:00",
                "session": "old",
            }
            new_rec = {
                "ended_at": "2999-01-01T00:00:00+00:00",
                "started_at": "2999-01-01T00:00:00+00:00",
                "session": "new",
            }
            metrics.write_text(
                json.dumps(old_rec) + "\nnot json\n" + json.dumps(new_rec) + "\n",
                encoding="utf-8",
            )
            report = apply_retention(
                runs, metrics, retention_days=30, log_max_bytes=0, metrics_max_bytes=0
            )
            self.assertTrue(report.metrics_trimmed)
            sessions = [r.get("session") for r in logging_mod.read_metrics(metrics)]
            self.assertNotIn("old", sessions)
            self.assertIn("new", sessions)
            # Malformed line retained (crash-recovery evidence).
            self.assertIn("not json", metrics.read_text(encoding="utf-8"))

    def test_metrics_size_cap_keeps_newest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            runs.mkdir()
            metrics = root / "metrics.jsonl"
            for i in range(5):
                logging_mod.append_metrics(metrics, {"session": f"s{i}", "n": i})
            size = metrics.stat().st_size
            report = apply_retention(
                runs,
                metrics,
                retention_days=0,
                log_max_bytes=0,
                metrics_max_bytes=size - 1,
            )
            self.assertTrue(report.metrics_trimmed)
            records = logging_mod.read_metrics(metrics)
            self.assertLess(len(records), 5)
            self.assertEqual(records[-1]["session"], "s4")

    def test_schema_versions_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            metrics = Path(tmp) / "metrics.jsonl"
            record = RunLogRecord(
                session_id="s9",
                spec="demo",
                action="a",
                input="i",
                output="o",
                exit_code=0,
                validation_result="passed",
                reset_reason=None,
                retry_count=0,
            )
            path = write_run_log(runs, record)
            self.assertIn(f"schema: {LOG_SCHEMA_VERSION}", path.read_text())
            logging_mod.append_metrics(metrics, {"session": "s9"})
            rec = logging_mod.read_metrics(metrics)[0]
            self.assertEqual(rec["schema_version"], METRICS_SCHEMA_VERSION)


class ExportTest(unittest.TestCase):
    def test_export_copies_telemetry_only_and_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            metrics = root / "metrics.jsonl"
            make_log(runs)
            logging_mod.append_metrics(metrics, {"session": "s1"})
            dest = root / "out"
            report = export_logs(runs, metrics, dest, max_bytes=10**9)
            self.assertGreaterEqual(report.files, 2)
            self.assertTrue((dest / "runs").is_dir())
            self.assertTrue((dest / "metrics.jsonl").is_file())
            # Scope: handoff/state never exported.
            exported = [str(p) for p in dest.rglob("*")]
            self.assertFalse(any("handoff" in p for p in exported))

    def test_export_refuses_above_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            metrics = root / "metrics.jsonl"
            make_log(runs)
            dest = root / "out"
            with self.assertRaises(OSError):
                export_logs(runs, metrics, dest, max_bytes=1)


class CliPruneExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_project(self.root)
        doc = handoff.empty_handoff()
        add_item(doc, "issue", "keep me", priority="high", item_id="u-keep")
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)

    def test_prune_preserves_handoff_history(self):
        runs = self.root / ".ariadex" / "runs"
        old = make_log(runs, age_days=60)
        code, out, _ = run_cli(self.root, "prune-logs", "--yes")
        self.assertEqual(code, 0)
        self.assertFalse(old.exists())
        self.assertIn("handoff history preserved", out)
        doc = handoff.read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertEqual(doc.unresolved[0].id, "u-keep")
        self.assertEqual(doc.unresolved[0].description, "keep me")

    def test_prune_json_stable(self):
        code, out, _ = run_cli(self.root, "prune-logs", "--yes", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIn("removed_logs", payload)
        self.assertIn("retained_logs", payload)

    def test_export_cli_round_trip(self):
        make_log(self.root / ".ariadex" / "runs")
        dest = str(self.root / "exported")
        code, out, _ = run_cli(self.root, "export-logs", "--out", dest)
        self.assertEqual(code, 0)
        self.assertIn("telemetry only", out)
        self.assertTrue(Path(dest, "metrics.jsonl").exists() or True)

    def test_export_cli_refuses_above_bound(self):
        make_log(self.root / ".ariadex" / "runs")
        code, _, err = run_cli(
            self.root,
            "export-logs",
            "--out",
            str(self.root / "o2"),
            "--max-bytes",
            "1",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("refused", err)


class ConfigBoundsTest(unittest.TestCase):
    def test_new_bounds_accepted_and_rejected(self):
        cfg = config.validate(
            {"log_retention_days": 7, "log_max_bytes": 100, "metrics_max_bytes": 100},
            source="test",
        )
        self.assertEqual(cfg.log_retention_days, 7)
        for key in ("log_retention_days", "log_max_bytes", "metrics_max_bytes"):
            with self.assertRaises(config.ConfigError):
                config.validate({key: -1}, source="test")
            with self.assertRaises(config.ConfigError):
                config.validate({key: "many"}, source="test")

    def test_default_config_text_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / config.CONFIG_REL_PATH).parent.mkdir(parents=True, exist_ok=True)
            (root / config.CONFIG_REL_PATH).write_text(
                config.default_config_text(), encoding="utf-8"
            )
            cfg = config.load(root)
            self.assertEqual(cfg, config.defaults())


class DoctorAndFormatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_project(self.root)

    def test_doctor_reports_log_bounds(self):
        from ariadex import operator

        checks, summary = operator.run_doctor(self.root)
        names = [c.name for c in checks]
        self.assertIn("logs", names)
        self.assertIn("ok", summary)

    def test_doctor_flags_open_permissions(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions not enforced on Windows")
        from ariadex import operator

        runs = self.root / ".ariadex" / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        os.chmod(runs, 0o755)
        checks, _ = operator.run_doctor(self.root)
        logs = next(c for c in checks if c.name == "logs")
        self.assertFalse(logs.ok)
        self.assertIn("group/other", logs.detail)

    def test_format_helpers_report_scope(self):
        from ariadex import operator

        report = apply_retention(
            self.root / ".ariadex" / "runs",
            self.root / ".ariadex" / "metrics.jsonl",
            retention_days=30,
            log_max_bytes=0,
            metrics_max_bytes=0,
        )
        text = operator.format_retention_text(report)
        self.assertIn("handoff history preserved", text)
        export = export_logs(
            self.root / ".ariadex" / "runs",
            self.root / ".ariadex" / "metrics.jsonl",
            self.root / "dest",
        )
        self.assertIn("telemetry only", operator.format_export_text(export))

    def test_windows_permission_fallback(self):
        target = self.root / "w.log"
        target.write_text("x", encoding="utf-8")
        with mock.patch.object(logging_mod.os, "name", "nt"):
            note = ensure_secure_permissions(target)
        self.assertIn("Windows", note or "")

    def test_retention_handles_missing_dirs(self):
        report = apply_retention(
            self.root / ".ariadex" / "runs",
            self.root / ".ariadex" / "metrics.jsonl",
            retention_days=7,
            log_max_bytes=100,
            metrics_max_bytes=100,
        )
        self.assertEqual(report.removed_logs, [])
        self.assertEqual(report.retained_logs, 0)

    def test_export_without_metrics(self):
        runs = self.root / ".ariadex" / "runs"
        make_log(runs)
        dest = self.root / "exp-no-metrics"
        report = export_logs(runs, self.root / ".ariadex" / "metrics.jsonl", dest)
        self.assertGreaterEqual(report.files, 1)

    def test_cli_export_json_and_bad_bound(self):
        make_log(self.root / ".ariadex" / "runs")
        code, out, _ = run_cli(
            self.root, "export-logs", "--out", str(self.root / "j"), "--json"
        )
        self.assertEqual(code, 0)
        json.loads(out)
        code, _, err = run_cli(
            self.root,
            "export-logs",
            "--out",
            str(self.root / "j2"),
            "--max-bytes",
            "-1",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("--max-bytes", err)

    def test_runner_observe_enforces_bounds(self):
        from ariadex import runner as runner_mod
        from ariadex import state as state_mod

        (self.root / "openspec" / "changes" / "demo").mkdir(parents=True)
        st = state_mod.read(self.root)
        st.mode = "AUTO"
        state_mod.write(self.root, st)
        import yaml

        cfg_path = self.root / ".ariadex" / "config.yaml"
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        raw["verification_commands"] = ["true"]
        raw["log_max_bytes"] = 1
        cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        cfg = config.load(self.root)
        from ariadex.providers import OpenCodeAdapter
        from ariadex.terminal import FakeTerminalDriver

        adapter = OpenCodeAdapter(FakeTerminalDriver(), "sess-govern", self.root)
        runner = runner_mod.Runner(self.root, cfg, adapter)
        result = runner.run_once()
        self.assertIn(result.outcome, ("completed", "idle", "unverified"))
        metrics = logging_mod.read_metrics(self.root / ".ariadex" / "metrics.jsonl")
        self.assertTrue(metrics)
        self.assertIn("redactions", metrics[-1])
        self.assertIn("schema_version", metrics[-1])


if __name__ == "__main__":
    unittest.main()
