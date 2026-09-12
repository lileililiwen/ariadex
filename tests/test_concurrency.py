"""Tests for single-runner ownership and interruption recovery."""

import io
import json
import os
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ariadex import cli, concurrency, handoff, state
from ariadex.concurrency import (
    ActiveLockError,
    StaleLockError,
)
from ariadex.handoff import add_item, write_handoff


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


def write_stale_lock(root: Path, session_id: str = "s-old", age_s: int = 3600) -> None:
    path = root / concurrency.LOCK_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    old = (datetime.now(UTC) - timedelta(seconds=age_s)).isoformat(timespec="seconds")
    payload = {
        "version": 1,
        "pid": 999999,
        "hostname": "dead-host",
        "session_id": session_id,
        "started_at": old,
        "heartbeat_at": old,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_active_lock(root: Path, session_id: str = "s-live") -> None:
    path = root / concurrency.LOCK_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = concurrency.now_iso()
    payload = {
        "version": 1,
        "pid": os.getpid(),
        "hostname": "live-host",
        "session_id": session_id,
        "started_at": stamp,
        "heartbeat_at": stamp,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


class OwnershipTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)
        self.session = state.read(self.root).session_id

    def tearDown(self):
        concurrency.release(self.root)

    def test_acquire_release_owner_metadata_and_heartbeat(self):
        info = concurrency.acquire(self.root, self.session)
        self.assertEqual(info.pid, os.getpid())
        self.assertEqual(info.session_id, self.session)
        self.assertTrue(info.hostname)
        self.assertTrue(info.started_at)
        first_beat = info.heartbeat_at
        self.assertTrue(concurrency.heartbeat(self.root))
        reloaded = concurrency.read_lock(self.root)
        assert reloaded is not None
        self.assertEqual(reloaded.pid, os.getpid())
        self.assertGreaterEqual(reloaded.heartbeat_at, first_beat)
        self.assertTrue(concurrency.release(self.root))
        self.assertIsNone(concurrency.read_lock(self.root))

    def test_release_never_deletes_other_owner(self):
        write_active_lock(self.root, session_id="someone-else")
        # Current pid matches the fake active lock pid (os.getpid), so
        # craft a truly foreign lock instead.
        path = self.root / concurrency.LOCK_REL_PATH
        raw = json.loads(path.read_text())
        raw["pid"] = 999998
        raw["heartbeat_at"] = concurrency.now_iso()
        # PID dead but heartbeat fresh -> live by heartbeat rule.
        path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n")
        self.assertFalse(concurrency.release(self.root))
        self.assertIsNotNone(concurrency.read_lock(self.root))

    def test_second_acquire_refuses_active_without_deletion(self):
        first = concurrency.acquire(self.root, self.session)
        before = (self.root / concurrency.LOCK_REL_PATH).read_text()
        with self.assertRaises(ActiveLockError) as ctx:
            concurrency.acquire(self.root, "other-session")
        self.assertIn(str(first.pid), str(ctx.exception))
        after = (self.root / concurrency.LOCK_REL_PATH).read_text()
        self.assertEqual(before, after)

    def test_stale_lock_raises_without_deletion(self):
        write_stale_lock(self.root)
        with self.assertRaises(StaleLockError) as ctx:
            concurrency.acquire(self.root, self.session)
        self.assertIn("999999", str(ctx.exception))
        # Nothing deleted implicitly.
        self.assertIsNotNone(concurrency.read_lock(self.root))

    def test_diagnose_free_active_stale(self):
        self.assertEqual(concurrency.diagnose(self.root)["state"], "free")
        concurrency.acquire(self.root, self.session)
        diag = concurrency.diagnose(self.root)
        self.assertEqual(diag["state"], "active")
        assert diag["owner"] is not None
        self.assertEqual(diag["owner"]["pid"], os.getpid())
        concurrency.release(self.root)
        write_stale_lock(self.root)
        diag = concurrency.diagnose(self.root)
        self.assertEqual(diag["state"], "stale")


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)
        st = state.read(self.root)
        st.mode = "AUTO"
        state.write(self.root, st)

    def tearDown(self):
        concurrency.release(self.root)
        # Remove any lock a refused run should never have deleted.
        pass

    def test_run_refuses_active_owner_without_input(self):
        write_active_lock(self.root)
        code, _, err = run_cli(self.root, "--no-auto-install", "run")
        self.assertNotEqual(code, 0)
        self.assertIn("owns", err)
        self.assertFalse((self.root / ".ariadex" / "metrics.jsonl").exists())
        # The foreign lock is preserved.
        self.assertIsNotNone(concurrency.read_lock(self.root))

    def test_auto_refuses_stale_owner_with_recover_hint(self):
        write_stale_lock(self.root)
        code, _, err = run_cli(self.root, "--no-auto-install", "auto")
        self.assertNotEqual(code, 0)
        self.assertIn("recover", err)
        self.assertIsNotNone(concurrency.read_lock(self.root))

    def test_failed_run_releases_lease(self):
        # No tmux here: _run_loop fails, but the lease must be released.
        code, _, _ = run_cli(self.root, "--no-auto-install", "run")
        self.assertNotEqual(code, 0)
        self.assertIsNone(concurrency.read_lock(self.root))

    def test_preview_only_sends_no_input_and_holds_no_lock(self):
        code, out, _ = run_cli(self.root, "--no-auto-install", "run", "--preview")
        self.assertEqual(code, 0)
        self.assertIn("next:", out)
        self.assertIsNone(concurrency.read_lock(self.root))


class PhaseRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def test_before_send_recovers_without_blocker(self):
        write_stale_lock(self.root)
        concurrency.write_cycle(
            self.root, concurrency.PHASE_BEFORE_SEND, "resolve-issue u-1: x"
        )
        code, out, _ = run_cli(self.root, "recover")
        self.assertEqual(code, 0)
        self.assertIn("stale-recovered", out)
        self.assertIn("safe to retry", out)
        doc = handoff.read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertFalse([i for i in doc.unresolved if i.status == "BLOCKED"])
        self.assertIsNone(concurrency.read_lock(self.root))
        self.assertIsNone(concurrency.read_cycle(self.root))

    def test_each_uncertain_phase_records_blocker(self):
        for phase in concurrency.UNCERTAIN_PHASES:
            with self.subTest(phase=phase):
                sub = tempfile.TemporaryDirectory()
                self.addCleanup(sub.cleanup)
                root = Path(sub.name)
                init_project(root)
                write_stale_lock(root)
                concurrency.write_cycle(root, phase, "advance-spec demo")
                code, out, _ = run_cli(root, "recover")
                self.assertEqual(code, 0, out)
                self.assertIn("uncertain", out)
                doc = handoff.read_handoff(root / ".ariadex" / "handoff.md")
                blocked = [i for i in doc.unresolved if i.status == "BLOCKED"]
                self.assertEqual(len(blocked), 1)
                self.assertIn(phase, blocked[0].description)
                self.assertTrue(blocked[0].history)
                stored = state.read(root)
                self.assertEqual(stored.unresolved_count, 1)

    def test_recovery_is_bounded_no_duplicate_blocker(self):
        write_stale_lock(self.root)
        concurrency.write_cycle(self.root, concurrency.PHASE_SENT, "advance-spec demo")
        run_cli(self.root, "recover")
        doc = handoff.read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertEqual(len(doc.unresolved), 1)
        # Second recovery finds nothing to do and adds no duplicate.
        code, out, _ = run_cli(self.root, "recover")
        self.assertEqual(code, 0)
        self.assertIn("nothing-to-do", out)
        doc2 = handoff.read_handoff(self.root / ".ariadex" / "handoff.md")
        self.assertEqual(len(doc2.unresolved), 1)

    def test_recover_refuses_live_owner_without_deletion(self):
        info = concurrency.acquire(self.root, state.read(self.root).session_id)
        try:
            code, out, _ = run_cli(self.root, "recover")
            self.assertNotEqual(code, 0)
            self.assertIn("active-refused", out)
            self.assertIn(str(info.pid), out)
            self.assertIsNotNone(concurrency.read_lock(self.root))
        finally:
            concurrency.release(self.root)

    def test_runner_stops_on_unreconciled_interruption(self):
        from ariadex import config as config_mod
        from ariadex import providers
        from ariadex.runner import Runner
        from ariadex.terminal import FakeTerminalDriver

        cfg = config_mod.load(self.root)
        (self.root / cfg.spec_dir / "demo").mkdir(parents=True)
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)
        st = state.read(self.root)
        st.mode = "AUTO"
        state.write(self.root, st)
        concurrency.write_cycle(self.root, concurrency.PHASE_SENT, "start-spec demo")
        driver = FakeTerminalDriver()
        adapter = providers.get_adapter("opencode", driver, "s", self.root)
        result = Runner(self.root, cfg, adapter).run_once()
        self.assertTrue(result.stopped)
        self.assertEqual(result.outcome, "interrupted")
        self.assertEqual(driver.calls, [])

    def test_successful_cycle_clears_phase(self):
        from ariadex import config as config_mod
        from ariadex import providers
        from ariadex.runner import Runner
        from ariadex.terminal import FakeTerminalDriver

        cfg = config_mod.load(self.root)
        (self.root / cfg.spec_dir / "demo").mkdir(parents=True)
        doc = handoff.empty_handoff()
        doc.next_spec = "demo"
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)
        st = state.read(self.root)
        st.mode = "AUTO"
        state.write(self.root, st)
        driver = FakeTerminalDriver()
        adapter = providers.get_adapter("opencode", driver, "s", self.root)
        result = Runner(self.root, cfg, adapter).run_once()
        self.assertEqual(result.outcome, "unverified")
        self.assertIsNone(concurrency.read_cycle(self.root))


class RecoverModesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def test_recover_works_in_every_mode(self):
        for mode in ("AUTO", "MANUAL", "PAUSE"):
            st = state.read(self.root)
            st.mode = mode
            state.write(self.root, st)
            code, out, _ = run_cli(self.root, "recover")
            self.assertEqual(code, 0, mode)
            self.assertIn("recovery:", out)

    def test_recover_json_stable(self):
        code, out, _ = run_cli(self.root, "recover", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        for key in ("lock_state", "owner", "phase", "notes"):
            self.assertIn(key, payload)

    def test_doctor_names_lock_and_interruption(self):
        _, out, _ = run_cli(self.root, "doctor")
        self.assertIn("lock:", out)
        self.assertIn("interruption:", out)
        write_stale_lock(self.root)
        _, out, _ = run_cli(self.root, "doctor")
        self.assertIn("recover", out)

    def test_history_preserved_across_recovery(self):
        doc = handoff.empty_handoff()
        add_item(doc, "issue", "keep me", priority="high", item_id="u-1")
        write_handoff(self.root / ".ariadex" / "handoff.md", doc)
        run_cli(self.root, "resolve", "u-1")
        write_stale_lock(self.root)
        concurrency.write_cycle(
            self.root, concurrency.PHASE_CAPTURED, "advance-spec demo"
        )
        run_cli(self.root, "recover")
        reloaded = handoff.read_handoff(self.root / ".ariadex" / "handoff.md")
        resolved = [i for i in reloaded.unresolved if i.id == "u-1"]
        self.assertEqual(resolved[0].status, "RESOLVED")
        self.assertTrue(resolved[0].history)


if __name__ == "__main__":
    unittest.main()
