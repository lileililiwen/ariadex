"""Tests for the operator status projection."""

import unittest
from datetime import datetime, timedelta, timezone

from ariadex.status import elapsed_since, render_status, tests_summary


def base_kwargs(**overrides):
    values = dict(
        mode="AUTO",
        agent="opencode (terminal: tmux)",
        spec="demo",
        session="abc123",
        context_strategy="per-spec",
        elapsed="3m00s",
        open_count=1,
        blocked_count=0,
        tests="passed (exit 0)",
        next_action="resolve-issue u-1",
    )
    values.update(overrides)
    return values


class StatusTest(unittest.TestCase):
    def test_projection_covers_required_fields(self):
        text = render_status(**base_kwargs())
        for expected in (
            "mode: AUTO", "agent: opencode", "spec: demo", "session: abc123",
            "context: per-spec", "elapsed: 3m00s", "unresolved: open=1 blocked=0",
            "tests: passed (exit 0)", "next: resolve-issue u-1",
        ):
            self.assertIn(expected, text)

    def test_absent_record_never_implies_pass(self):
        text = render_status(**base_kwargs(tests=tests_summary(None)))
        self.assertIn("no verification record", text)
        self.assertNotIn("passed", text)

    def test_failure_visible(self):
        text = render_status(
            **base_kwargs(tests=tests_summary(
                {"validation_result": "failed", "exit_code": 2}))
        )
        self.assertIn("tests: failed (exit 2)", text)

    def test_elapsed_formatting(self):
        now = datetime.now(timezone.utc)
        updated = (now - timedelta(minutes=3)).isoformat()
        self.assertEqual(elapsed_since(updated, now), "3m00s")
        self.assertEqual(elapsed_since("not-a-time", now), "unknown")


if __name__ == "__main__":
    unittest.main()
