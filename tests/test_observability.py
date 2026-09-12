"""Tests for versioned events, export isolation, and bounded notifications."""

import json
import tempfile
import unittest
from pathlib import Path

from ariadex import config, handoff, observability, providers, state
from ariadex.handoff import write_handoff
from ariadex.observability import (
    EVENT_SCHEMA_VERSION,
    CommandSink,
    ExportError,
    ExportSink,
    FileSink,
)
from ariadex.runner import Runner
from ariadex.terminal import FakeTerminalDriver
from ariadex.verify import ShellVerifier, VerificationResult, Verifier


class PassVerifier(Verifier):
    def verify(self, action, output):
        return VerificationResult(passed=True, detail="stub pass", exit_code=0)


class FailingSink(ExportSink):
    name = "failing"

    def __init__(self):
        self.calls = 0

    def send(self, payload):
        self.calls += 1
        raise ExportError("sink down")


class RecordingSink(ExportSink):
    name = "recording"

    def __init__(self):
        self.payloads = []

    def send(self, payload):
        self.payloads.append(payload)


def make_cfg(root: Path, **overrides) -> config.Config:
    values = {"spec_dir": "openspec/changes", "handoff_file": ".ariadex/handoff.md"}
    values.update(overrides)
    raw = {
        "agent_provider": "opencode",
        "terminal_driver": "tmux",
        "context_strategy": "per-spec",
        "reset_mode": "auto",
        "retry_limit": 2,
        "blocker_policy": "stop-on-blocker",
        "verification_commands": [],
        **values,
    }
    return config.validate(raw)


def make_runner(root: Path, cfg=None, verifier=None, specs=("demo",)):
    cfg = cfg or make_cfg(root)
    for name in specs:
        (root / cfg.spec_dir / name).mkdir(parents=True, exist_ok=True)
    (root / ".ariadex").mkdir(parents=True, exist_ok=True)
    stored = state.initial_state()
    stored.mode = "AUTO"
    state.write(root, stored)
    driver = FakeTerminalDriver()
    adapter = providers.get_adapter("opencode", driver, "test-session", root)
    return Runner(root, cfg, adapter, verifier or PassVerifier()), driver


class SchemaTest(unittest.TestCase):
    def test_event_has_versioned_stable_keys(self):
        event = observability.build_event(
            observability.EVENT_BLOCKER,
            session="s",
            spec="demo",
            action="advance-spec demo",
            outcome="blocked",
            detail="adapter gone",
            retry_count=2,
            usage_available=True,
        )
        self.assertEqual(event["schema_version"], EVENT_SCHEMA_VERSION)
        self.assertEqual(
            sorted(event),
            sorted(
                [
                    "schema_version",
                    "type",
                    "at",
                    "session",
                    "spec",
                    "action",
                    "outcome",
                    "detail",
                    "retry_count",
                    "usage",
                    "redactions",
                ]
            ),
        )
        self.assertEqual(event["usage"], "available")

    def test_secret_redacted_before_persistence(self):
        event = observability.build_event(
            observability.EVENT_BLOCKER,
            detail="token=sk-abcdefghijklmnopqrst leaked here",
        )
        self.assertNotIn("sk-abcdefghijklmnopqrst", event["detail"])
        self.assertIn("<redacted>", event["detail"])
        self.assertGreaterEqual(event["redactions"], 1)

    def test_non_attention_outcomes_map_to_no_event(self):
        class Result:
            outcome = "idle"
            action = "none — idle"
            detail = "nothing"

        self.assertIsNone(observability.event_for_result(Result()))


class AggregationTest(unittest.TestCase):
    def test_summary_counts_durations_retries_usage(self):
        records = [
            {
                "outcome": "completed",
                "retry_count": 0,
                "started_at": "2026-09-12T10:00:00+00:00",
                "ended_at": "2026-09-12T10:00:10+00:00",
                "usage": {"input_tokens": 3},
                "validation_result": "passed",
            },
            {
                "outcome": "verification-failed",
                "retry_count": 2,
                "started_at": "2026-09-12T10:01:00+00:00",
                "ended_at": "2026-09-12T10:01:20+00:00",
                "usage": "unavailable",
                "validation_result": "failed",
            },
            {
                "outcome": "blocked",
                "retry_count": 1,
                # No timestamps: excluded from durations, counted elsewhere.
                "usage": "unavailable",
                "validation_result": "failed",
            },
        ]
        summary = observability.summarize_metrics(records)
        self.assertEqual(summary["schema_version"], EVENT_SCHEMA_VERSION)
        self.assertEqual(summary["cycles"], 3)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["verification_failed"], 1)
        self.assertEqual(summary["blocked"], 1)
        self.assertEqual(summary["retries_total"], 3)
        self.assertEqual(summary["retries_max"], 2)
        self.assertEqual(summary["cycle_duration_s"]["count"], 2)
        self.assertEqual(summary["cycle_duration_s"]["min"], 10.0)
        self.assertEqual(summary["cycle_duration_s"]["max"], 20.0)
        self.assertEqual(summary["usage"], {"available": 1, "unavailable": 2})

    def test_empty_records_summarize_without_error(self):
        summary = observability.summarize_metrics([])
        self.assertEqual(summary["cycles"], 0)
        self.assertIsNone(summary["cycle_duration_s"]["avg"])


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_failing_sink_recorded_locally_no_success_claimed(self):
        sink = FailingSink()
        results = observability.export_snapshot(self.root, [sink], session="s")
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertIn("sink down", results[0].detail)
        events = observability.read_events(self.root)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], observability.EVENT_EXPORT_FAILED)
        self.assertEqual(events[0]["schema_version"], EVENT_SCHEMA_VERSION)

    def test_failure_does_not_stop_remaining_sinks(self):
        failing, recording = FailingSink(), RecordingSink()
        results = observability.export_snapshot(
            self.root, [failing, recording], session="s"
        )
        self.assertFalse(results[0].ok)
        self.assertTrue(results[1].ok)
        self.assertEqual(len(recording.payloads), 1)
        self.assertEqual(recording.payloads[0]["schema_version"], EVENT_SCHEMA_VERSION)

    def test_snapshot_carries_summary_and_redacted_events(self):
        observability.record_event(
            self.root,
            observability.build_event(
                observability.EVENT_BLOCKER, detail="api_key=SECRETVALUEShown?"
            ),
        )
        snapshot = observability.build_snapshot(self.root, session="s")
        self.assertEqual(snapshot["schema_version"], EVENT_SCHEMA_VERSION)
        self.assertIn("summary", snapshot)
        self.assertEqual(len(snapshot["events"]), 1)

    def test_file_sink_round_trips_snapshot(self):
        dest = self.root / "out" / "snapshot.json"
        results = observability.export_snapshot(
            self.root, [FileSink(dest)], session="s"
        )
        self.assertTrue(results[0].ok)
        payload = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], EVENT_SCHEMA_VERSION)

    def test_command_sink_failure_is_export_error(self):
        sink = CommandSink(["exit", "3"])
        with self.assertRaises(ExportError):
            sink.send({"schema_version": 1})


class NotifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_repeated_blocker_rate_limited_and_deduped(self):
        sink = RecordingSink()
        event = observability.build_event(
            observability.EVENT_BLOCKER, action="advance-spec demo", detail="down"
        )
        first = observability.notify_event(
            self.root, event, [sink], rate_limit=2, window_s=3600, now_s=1000.0
        )
        second = observability.notify_event(
            self.root, event, [sink], rate_limit=2, window_s=3600, now_s=1001.0
        )
        third = observability.notify_event(
            self.root, event, [sink], rate_limit=2, window_s=3600, now_s=1002.0
        )
        self.assertTrue(first.delivered)
        self.assertTrue(second.delivered)
        self.assertFalse(third.delivered)
        self.assertTrue(third.suppressed)
        self.assertEqual(len(sink.payloads), 2)

    def test_window_expiry_readmits_key(self):
        sink = RecordingSink()
        event = observability.build_event(
            observability.EVENT_BLOCKER, action="x", detail="down"
        )
        observability.notify_event(
            self.root, event, [sink], rate_limit=1, window_s=60, now_s=1000.0
        )
        later = observability.notify_event(
            self.root, event, [sink], rate_limit=1, window_s=60, now_s=2000.0
        )
        self.assertTrue(later.delivered)
        self.assertEqual(len(sink.payloads), 2)

    def test_failed_delivery_single_attempt_recorded_no_retry_storm(self):
        sink = FailingSink()
        event = observability.build_event(
            observability.EVENT_BLOCKER, action="x", detail="down"
        )
        result = observability.notify_event(
            self.root, event, [sink], rate_limit=5, window_s=3600, now_s=1000.0
        )
        self.assertFalse(result.delivered)
        self.assertFalse(result.suppressed)
        self.assertEqual(sink.calls, 1)
        failures = [
            e
            for e in observability.read_events(self.root)
            if e["type"] == observability.EVENT_NOTIFICATION_FAILED
        ]
        self.assertEqual(len(failures), 1)
        # Budget unconsumed by the failure: the next observation retries once.
        result2 = observability.notify_event(
            self.root, event, [sink], rate_limit=5, window_s=3600, now_s=1001.0
        )
        self.assertFalse(result2.suppressed)
        self.assertEqual(sink.calls, 2)

    def test_state_stays_bounded(self):
        now = 1000.0
        big_state = {f"k-{i}": [now] for i in range(500)}
        allowed, updated = observability.notify_allowed(
            big_state, "fresh", rate_limit=5, window_s=3600, now_s=now
        )
        self.assertTrue(allowed)
        self.assertLessEqual(len(updated), observability.MAX_NOTIFY_KEYS)

    def test_no_sinks_suppresses_without_state(self):
        event = observability.build_event(observability.EVENT_COMPLETED)
        result = observability.notify_event(self.root, event, [])
        self.assertTrue(result.suppressed)
        self.assertFalse(
            (self.root / ".ariadex" / observability.NOTIFY_STATE_FILENAME).exists()
        )


class RunnerIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write_doc(self, doc):
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)

    def events_of(self, event_type):
        return [
            e
            for e in observability.read_events(self.root, limit=-1)
            if e["type"] == event_type
        ]

    def test_blocked_cycle_records_blocker_event(self):
        run, driver = make_runner(self.root)
        driver.missing_binary = True
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.outcome, "blocked")
        blockers = self.events_of(observability.EVENT_BLOCKER)
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0]["outcome"], "blocked")

    def test_completed_cycle_records_completion_event(self):
        run, _ = make_runner(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.outcome, "completed")
        completed = self.events_of(observability.EVENT_COMPLETED)
        self.assertEqual(len(completed), 1)

    def test_verification_failure_records_event_with_retries(self):
        cfg = make_cfg(self.root)
        run, _ = make_runner(
            self.root, cfg=cfg, verifier=ShellVerifier(["exit 1"], self.root)
        )
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.outcome, "verification-failed")
        failures = self.events_of(observability.EVENT_VERIFICATION_FAILED)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["retry_count"], 1)

    def test_interrupted_cycle_records_stale_session_event(self):
        from ariadex import concurrency as concurrency_mod

        run, _ = make_runner(self.root)
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        self.write_doc(doc)
        concurrency_mod.write_cycle(
            self.root, concurrency_mod.PHASE_SENT, "start-spec demo"
        )
        result = run.run_once()
        self.assertEqual(result.outcome, "interrupted")
        stale = self.events_of(observability.EVENT_STALE_SESSION)
        self.assertEqual(len(stale), 1)

    def test_idle_cycle_records_no_attention_event(self):
        run, _ = make_runner(self.root, specs=())
        # Missing spec dir blocks; use an empty-but-present dir for true idle.
        (self.root / "openspec" / "changes").mkdir(parents=True, exist_ok=True)
        doc = handoff.empty_handoff()
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.outcome, "idle")
        self.assertEqual(observability.read_events(self.root, limit=-1), [])

    def test_notifications_disabled_by_default(self):
        cfg = make_cfg(self.root)
        self.assertFalse(cfg.notifications_enabled)
        run, driver = make_runner(self.root, cfg=cfg)
        driver.missing_binary = True
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        self.write_doc(doc)
        run.run_once()
        # Local event recorded, but no sink state created (nothing delivered).
        self.assertEqual(len(self.events_of(observability.EVENT_BLOCKER)), 1)
        self.assertFalse(
            (self.root / ".ariadex" / observability.NOTIFY_STATE_FILENAME).exists()
        )

    def test_failing_notification_never_changes_scheduling(self):
        cfg = make_cfg(
            self.root,
            notifications_enabled=True,
            notification_command=["exit", "1"],
            notification_rate_limit=5,
        )
        run, _ = make_runner(self.root, cfg=cfg)
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        self.write_doc(doc)
        result = run.run_once()
        self.assertEqual(result.outcome, "completed")
        self.assertFalse(result.stopped)
        failures = self.events_of(observability.EVENT_NOTIFICATION_FAILED)
        self.assertEqual(len(failures), 1)
        reloaded = handoff.read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertEqual(reloaded.current_spec, "demo")


class ConfigValidationTest(unittest.TestCase):
    def base_raw(self, **overrides):
        raw = {
            "agent_provider": "opencode",
            "terminal_driver": "tmux",
            "context_strategy": "per-spec",
            "reset_mode": "auto",
            "spec_dir": "openspec/changes",
            "handoff_file": ".ariadex/handoff.md",
            "verification_commands": [],
            "retry_limit": 2,
            "blocker_policy": "stop-on-blocker",
            "log_retention_days": 30,
            "log_max_bytes": 10485760,
            "metrics_max_bytes": 5242880,
        }
        raw.update(overrides)
        return raw

    def test_defaults_opt_out(self):
        cfg = config.validate(self.base_raw())
        self.assertFalse(cfg.notifications_enabled)
        self.assertEqual(cfg.notification_command, [])
        self.assertEqual(cfg.notification_webhook, "")
        self.assertEqual(observability.notification_sinks(cfg), [])

    def test_rejects_non_http_webhook(self):
        with self.assertRaises(config.ConfigError):
            config.validate(self.base_raw(notification_webhook="ftp://x/y"))

    def test_rejects_non_list_command(self):
        with self.assertRaises(config.ConfigError):
            config.validate(self.base_raw(notification_command="send it"))

    def test_rejects_negative_rate_limit(self):
        with self.assertRaises(config.ConfigError):
            config.validate(self.base_raw(notification_rate_limit=-1))

    def test_sinks_built_from_config(self):
        cfg = config.validate(
            self.base_raw(
                notifications_enabled=True,
                notification_command=["mail", "ops"],
                notification_webhook="https://example.test/hook",
            )
        )
        sinks = observability.notification_sinks(cfg)
        self.assertEqual([s.name for s in sinks], ["command", "webhook"])


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def init_project(self, **overrides):
        from ariadex import cli as cli_mod

        self.assertEqual(cli_mod.cmd_init(self.root), 0)
        if overrides:
            import yaml

            path = self.root / ".ariadex" / "config.yaml"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            data.update(overrides)
            path.write_text(yaml.safe_dump(data), encoding="utf-8")

    def test_events_command_read_only(self):
        from ariadex import cli as cli_mod

        self.init_project()
        observability.record_event(
            self.root, observability.build_event(observability.EVENT_COMPLETED)
        )
        self.assertEqual(cli_mod.cmd_events(self.root), 0)
        self.assertEqual(cli_mod.cmd_events(self.root, as_json=True), 0)

    def test_export_events_bound_refuses(self):
        from ariadex import cli as cli_mod

        self.init_project()
        self.assertEqual(
            cli_mod.cmd_export_events(
                self.root, out=str(self.root / "snap.json"), max_bytes=10
            ),
            1,
        )
        self.assertFalse((self.root / "snap.json").exists())

    def test_export_events_writes_snapshot(self):
        from ariadex import cli as cli_mod

        self.init_project()
        dest = self.root / "snap.json"
        self.assertEqual(cli_mod.cmd_export_events(self.root, out=str(dest)), 0)
        payload = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], EVENT_SCHEMA_VERSION)
        self.assertIn("summary", payload)


if __name__ == "__main__":
    unittest.main()
