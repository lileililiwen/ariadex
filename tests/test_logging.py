"""Tests for run logs, metrics records, and redaction."""

import json
import tempfile
import unittest
from pathlib import Path

from ariadex import logging as logging_mod
from ariadex.logging import (
    RunLogRecord,
    append_metrics,
    read_metrics,
    redact,
    usage_record,
    write_run_log,
)


def make_record(**overrides) -> RunLogRecord:
    values = dict(
        session_id="s1",
        spec="demo",
        action="resolve-issue u-1",
        input="prompt",
        output="done",
        exit_code=0,
        validation_result="passed",
        reset_reason="soft",
        retry_count=0,
    )
    values.update(overrides)
    return RunLogRecord(**values)


class RedactionTest(unittest.TestCase):
    def test_api_key_redacted(self):
        self.assertEqual(redact("key sk-abcdefghijklmnop123"), "key <redacted>")

    def test_aws_key_redacted(self):
        self.assertEqual(
            redact("id AKIAIOSFODNN7EXAMPLE"), "id <redacted>"
        )

    def test_private_key_block_redacted(self):
        text = "x\n-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----\ny"
        self.assertEqual(redact(text), "x\n<redacted>\ny")

    def test_password_assignment_redacted(self):
        self.assertEqual(
            redact("password=hunter2 ok"), "password=<redacted> ok"
        )

    def test_plain_text_untouched(self):
        text = "build passed in 12s, 3 tests green"
        self.assertEqual(redact(text), text)


class RunLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runs = Path(self.tmp.name) / "runs"

    def test_log_contains_required_fields(self):
        path = write_run_log(self.runs, make_record())
        text = path.read_text(encoding="utf-8")
        for field in ("s1", "demo", "resolve-issue u-1", "passed", "soft"):
            self.assertIn(field, text)
        self.assertIn("--- input ---", text)
        self.assertIn("--- output ---", text)

    def test_log_records_blocker_exit_condition(self):
        path = write_run_log(
            self.runs,
            make_record(
                action="none — blocked", exit_code=None,
                validation_result="unavailable", output="provider gone",
            ),
        )
        text = path.read_text(encoding="utf-8")
        self.assertIn("provider gone", text)
        self.assertIn("exit code: n/a", text)

    def test_log_redacts_secrets(self):
        path = write_run_log(
            self.runs, make_record(output="token sk-abcdefghijklmnop123")
        )
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("sk-abcdefghijklmnop123", text)
        self.assertIn("<redacted>", text)

    def test_log_write_leaves_no_temp_files(self):
        write_run_log(self.runs, make_record())
        leftovers = list((self.runs / "s1").glob(".run.*.tmp"))
        self.assertEqual(leftovers, [])


class MetricsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "metrics.jsonl"

    def test_append_and_read_round_trip(self):
        append_metrics(self.path, {"session": "s1", "usage": "unavailable"})
        append_metrics(self.path, {"session": "s2", "usage": {"input_tokens": 5}})
        records = read_metrics(self.path)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["usage"], "unavailable")
        self.assertEqual(records[1]["usage"]["input_tokens"], 5)

    def test_malformed_lines_skipped(self):
        self.path.write_text(
            '{"session": "s1"}\nnot json\n{"session": "s2"}\n',
            encoding="utf-8",
        )
        records = read_metrics(self.path)
        self.assertEqual([r["session"] for r in records], ["s1", "s2"])

    def test_missing_file_reads_empty(self):
        self.assertEqual(read_metrics(self.path), [])

    def test_unavailable_usage_is_explicit(self):
        self.assertEqual(usage_record(None), "unavailable")
        usage = {"input_tokens": 1, "output_tokens": 2, "cost": 0.01}
        self.assertEqual(usage_record(usage), usage)


if __name__ == "__main__":
    unittest.main()
