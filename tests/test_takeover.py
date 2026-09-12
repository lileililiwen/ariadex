"""Tests for takeover/pause cancellation and scheduler coordination."""

import io
import json
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path

from ariadex import cli, concurrency, config, handoff, providers, state
from ariadex.handoff import add_item, read_handoff, write_handoff
from ariadex.runner import Runner, VerificationResult, Verifier
from ariadex.terminal import FakeTerminalDriver


class PassVerifier(Verifier):
    def verify(self, action, output):
        return VerificationResult(passed=True, detail="stub pass", exit_code=0)


class CancelOnSendAdapter(providers.OpenCodeAdapter):
    """Requests takeover immediately after delivering provider input."""

    project_root: Path | None = None

    def send(self, text: str) -> None:
        super().send(text)
        assert self.project_root is not None
        concurrency.request_cancellation(
            self.project_root,
            requested_by="takeover",
            reason="test takeover after send",
        )


class CancelOnVerify(Verifier):
    """Requests takeover while verification is running."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def verify(self, action, output):
        concurrency.request_cancellation(
            self.root,
            requested_by="takeover",
            reason="test takeover during verification",
        )
        return VerificationResult(passed=True, detail="stub pass", exit_code=0)


def run_cli(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with chdir(root), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


def init_project(root: Path) -> None:
    code, _, _ = run_cli(root, "init")
    assert code == 0
    (root / "openspec" / "changes").mkdir(parents=True, exist_ok=True)


def set_auto(root: Path) -> None:
    stored = state.read(root)
    stored.mode = "AUTO"
    state.write(root, stored)


def make_runner(root: Path, adapter=None, verifier=None):
    cfg = config.load(root)
    set_auto(root)
    driver = adapter.driver if adapter is not None else FakeTerminalDriver()
    if adapter is None:
        adapter = providers.get_adapter("opencode", driver, "test-session", root)
    return Runner(root, cfg, adapter, verifier or PassVerifier()), driver


def write_issues(root: Path, count: int = 1) -> None:
    doc = handoff.empty_handoff()
    for i in range(1, count + 1):
        add_item(doc, "issue", f"work {i}", priority="high", item_id=f"u-{i}")
    write_handoff(handoff_path(root), doc)


def handoff_path(root: Path) -> Path:
    """Configured durable handoff location (default root `HANDOFF.md`)."""
    return root / config.load(root).handoff_file


class CancelBeforeSendTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def test_takeover_before_send_sends_no_input_and_is_retryable(self):
        run, driver = make_runner(self.root)
        write_issues(self.root)
        concurrency.request_cancellation(
            self.root, requested_by="takeover", reason="operator took over"
        )
        result = run.run_once()
        self.assertTrue(result.stopped)
        self.assertEqual(result.outcome, "cancelled")
        self.assertEqual(result.stop_reason, "cancelled")
        self.assertEqual(driver.calls, [])
        # Safe checkpoint: phase cleared, work preserved verbatim.
        self.assertIsNone(concurrency.read_cycle(self.root))
        reloaded = read_handoff(handoff_path(self.root))
        self.assertTrue(reloaded.next_action.startswith("resolve-issue u-1"))
        self.assertEqual(handoff.get_item(reloaded, "u-1").status, "OPEN")
        self.assertIsNone(reloaded.current_spec)
        # Signal consumed once honored; exit mapping is non-zero.
        self.assertIsNone(concurrency.cancellation_requested(self.root))
        self.assertEqual(cli.exit_for_cycles([result]), cli.EXIT_ERROR)

    def test_cancelled_outcome_is_distinct_in_metrics(self):
        from ariadex.logging import read_metrics

        run, _ = make_runner(self.root)
        write_issues(self.root)
        concurrency.request_cancellation(self.root, requested_by="pause")
        run.run_once()
        records = read_metrics(self.root / ".ariadex" / "metrics.jsonl")
        self.assertEqual(records[-1]["outcome"], "cancelled")


class CancelAfterSendTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def make_sending_runner(self):
        cfg = config.load(self.root)
        set_auto(self.root)
        driver = FakeTerminalDriver()
        adapter = CancelOnSendAdapter(driver, "test-session", self.root)
        adapter.project_root = self.root
        return Runner(self.root, cfg, adapter, PassVerifier()), driver

    def test_takeover_after_send_preserves_uncertain_phase(self):
        run, driver = self.make_sending_runner()
        write_issues(self.root)
        result = run.run_once()
        self.assertTrue(result.stopped)
        self.assertEqual(result.outcome, "cancelled")
        # Input was delivered, but nothing after the request: no reset input,
        # no second prompt, no completion.
        sent = [c[2] for c in driver.calls if c[0] == "send_input"]
        self.assertEqual(len(sent), 1)
        self.assertNotIn("/new", sent[0])
        cycle = concurrency.read_cycle(self.root)
        self.assertIsNotNone(cycle)
        assert cycle is not None
        self.assertEqual(cycle.phase, concurrency.PHASE_CAPTURED)
        reloaded = read_handoff(handoff_path(self.root))
        self.assertTrue(reloaded.next_action.startswith("resolve-issue u-1"))
        self.assertEqual(handoff.get_item(reloaded, "u-1").status, "OPEN")
        self.assertEqual(reloaded.completed, [])
        self.assertEqual(cli.exit_for_cycles([result]), cli.EXIT_ERROR)

    def test_restart_requires_recovery_and_records_one_blocker(self):
        _, _ = make_runner(self.root)
        run, _ = self.make_sending_runner()
        write_issues(self.root)
        run.run_once()
        # A fresh process instance must not schedule over uncertainty.
        cfg = config.load(self.root)
        fresh = Runner(
            self.root,
            cfg,
            providers.get_adapter(
                "opencode", FakeTerminalDriver(), "test-session", self.root
            ),
            PassVerifier(),
        )
        restarted = fresh.run_once()
        self.assertTrue(restarted.stopped)
        self.assertEqual(restarted.outcome, "interrupted")
        # Recovery records the uncertain delivery once and stays bounded.
        first = concurrency.recover_project(self.root)
        self.assertTrue(first.blocker_added)
        self.assertIsNotNone(first.blocker_id)
        second = concurrency.recover_project(self.root)
        self.assertEqual(second.lock_state, "nothing-to-do")
        self.assertFalse(second.blocker_added)
        reloaded = read_handoff(handoff_path(self.root))
        uncertain = [
            item
            for item in reloaded.unresolved
            if item.status == "BLOCKED" and "uncertain" in item.description
        ]
        self.assertEqual(len(uncertain), 1)
        # No completion was fabricated and no tmux session was harmed.
        self.assertEqual(reloaded.completed, [])


class CancelDuringVerificationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def test_takeover_during_verification_claims_no_completion(self):
        run, driver = make_runner(self.root, verifier=CancelOnVerify(self.root))
        write_issues(self.root)
        result = run.run_once()
        self.assertTrue(result.stopped)
        self.assertEqual(result.outcome, "cancelled")
        # Verification had passed, yet persistence is withheld: the phase
        # stays for explicit recovery and the issue stays OPEN.
        cycle = concurrency.read_cycle(self.root)
        self.assertIsNotNone(cycle)
        assert cycle is not None
        self.assertEqual(cycle.phase, concurrency.PHASE_COMPLETING)
        reloaded = read_handoff(handoff_path(self.root))
        self.assertEqual(handoff.get_item(reloaded, "u-1").status, "OPEN")
        self.assertEqual(reloaded.completed, [])
        # The next scheduling step is not started: restart stops unreconciled.
        cfg = config.load(self.root)
        fresh = Runner(
            self.root,
            cfg,
            providers.get_adapter(
                "opencode", FakeTerminalDriver(), "test-session", self.root
            ),
            PassVerifier(),
        )
        restarted = fresh.run_once()
        self.assertEqual(restarted.outcome, "interrupted")
        sent = [c for c in driver.calls if c[0] == "send_input"]
        self.assertEqual(len(sent), 1)

    def test_cancel_between_completion_and_reset_skips_reset_input(self):
        cfg = config.load(self.root)
        set_auto(self.root)
        driver = FakeTerminalDriver()
        adapter = providers.get_adapter("opencode", driver, "test-session", self.root)
        run = Runner(self.root, cfg, adapter, PassVerifier())
        write_issues(self.root)
        original = Runner._apply_completion

        def hooked(self, handoff_doc, kind, target):
            concurrency.request_cancellation(
                self.project_dir,
                requested_by="takeover",
                reason="race between completion and reset",
            )
            return original(self, handoff_doc, kind, target)

        Runner._apply_completion = hooked  # type: ignore[method-assign]
        try:
            result = run.run_once()
        finally:
            Runner._apply_completion = original  # type: ignore[method-assign]
        # Verified completion stands (evidence existed), but reset input is
        # skipped and the cancellation is consumed.
        self.assertEqual(result.outcome, "completed")
        reloaded = read_handoff(handoff_path(self.root))
        self.assertEqual(handoff.get_item(reloaded, "u-1").status, "RESOLVED")
        sent = [c[2] for c in driver.calls if c[0] == "send_input"]
        self.assertEqual(len(sent), 1)
        self.assertFalse(any("/new" in text for text in sent))
        self.assertIsNone(concurrency.cancellation_requested(self.root))


class CommandCoordinationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def test_takeover_signals_and_reports_idle_scheduler(self):
        set_auto(self.root)
        code, out, _ = run_cli(self.root, "takeover")
        self.assertEqual(code, 0)
        self.assertIn("MANUAL", out)
        self.assertIn("no active scheduler", out)
        signal = concurrency.cancellation_requested(self.root)
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal["requested_by"], "takeover")
        # Lease untouched: none created by the command.
        self.assertFalse(concurrency.lock_path(self.root).exists())
        self.assertEqual(state.read(self.root).mode, "MANUAL")

    def test_pause_with_live_owner_reports_pending_and_keeps_lease(self):
        set_auto(self.root)
        with concurrency.owned_lock(self.root, state.read(self.root).session_id):
            before = concurrency.lock_path(self.root).read_bytes()
            code, out, _ = run_cli(self.root, "pause")
            self.assertEqual(code, 0)
            self.assertIn("PAUSE", out)
            self.assertIn("cancellation pending", out)
            self.assertIn("untouched", out)
            after = concurrency.lock_path(self.root).read_bytes()
            self.assertEqual(before, after)
            signal = concurrency.cancellation_requested(self.root)
            self.assertIsNotNone(signal)
            assert signal is not None
            self.assertEqual(signal["requested_by"], "pause")
        self.assertEqual(state.read(self.root).mode, "PAUSE")

    def test_pause_with_stale_lock_points_at_recover_without_deleting(self):
        set_auto(self.root)
        stale = concurrency.LockInfo(
            pid=999999,
            hostname="gone",
            session_id="s",
            started_at="2000-01-01T00:00:00+00:00",
            heartbeat_at="2000-01-01T00:00:00+00:00",
        )
        concurrency.lock_path(self.root).parent.mkdir(parents=True, exist_ok=True)
        concurrency.lock_path(self.root).write_text(
            json.dumps(stale.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        code, out, _ = run_cli(self.root, "pause")
        self.assertEqual(code, 0)
        self.assertIn("recover", out)
        self.assertIn("untouched", out)
        self.assertTrue(concurrency.lock_path(self.root).exists())

    def test_auto_clears_cancellation(self):
        run_cli(self.root, "takeover")
        concurrency.request_cancellation(self.root, requested_by="takeover")
        code, out, _ = run_cli(self.root, "--no-auto-install", "auto", "--preview")
        self.assertEqual(code, 0)
        self.assertIn("cancellation: cleared", out)
        self.assertIsNone(concurrency.cancellation_requested(self.root))

    def test_recover_refuses_live_owner(self):
        set_auto(self.root)
        with concurrency.owned_lock(self.root, state.read(self.root).session_id):
            concurrency.write_cycle(
                self.root, concurrency.PHASE_SENT, "resolve-issue u-1: work"
            )
            report = concurrency.recover_project(self.root)
            self.assertEqual(report.lock_state, "active-refused")
            self.assertFalse(report.blocker_added)
            self.assertTrue(concurrency.lock_path(self.root).exists())
            # Uncertain phase left for the owner; nothing fabricated.
            self.assertIsNotNone(concurrency.read_cycle(self.root))


if __name__ == "__main__":
    unittest.main()
