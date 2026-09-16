"""Approval replies get a recovery path (approval-reply-recovery).

Covers the bounded per-episode re-ask (NOT DONE re-arms once after a
quiet interval, a repeated NOT DONE parks visibly, DONE/garbage/
timeout behave as today), the redacted request shape in
waiting/deny reasons, and the episode reset when the surface
clears. Replies never approve anything and no reset is ever sent.
"""

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from ariadex import diagnostics as diagnostics_mod
from ariadex import handoff as handoff_mod
from ariadex import permissions as permissions_mod
from ariadex import providers as providers_mod
from ariadex import robot as robot_mod
from ariadex import terminal as terminal_mod

try:
    import evidence_fakes
except ModuleNotFoundError:
    from tests import evidence_fakes  # type: ignore[no-redef]

APPROVAL_UNKNOWN = "Ask anything\nApproval required: frobnicator engaged? [y/n]\n"
APPROVAL_SUDO = "Ask anything\nApproval required: allow `sudo rm -rf /tmp/x`? [y/n]\n"
APPROVAL_AMBIGUOUS = (
    "Ask anything\nApproval required: allow write to `/a.txt` or `/b.txt`? [y/n]\n"
)
BUSY = "running tool `pytest` …\nesc to interrupt\n"


class FakeDriver(terminal_mod.FakeTerminalDriver):
    def __init__(self) -> None:
        super().__init__()
        self.executable = "tmux"


def make_project(state: list) -> Path:
    tmp = tempfile.TemporaryDirectory()
    state.append(tmp)
    root = Path(tmp.name)
    (root / ".ariadex").mkdir(parents=True)
    handoff_mod.write_handoff(root / "HANDOFF.md", handoff_mod.empty_handoff("s"))
    (root / "openspec" / "changes").mkdir(parents=True)
    return root


def make_change(root: Path, name: str) -> None:
    change = root / "openspec" / "changes" / name
    change.mkdir(parents=True, exist_ok=True)
    (change / "tasks.md").write_text("# Tasks\n\n- [ ] Open\n", encoding="utf-8")
    handoff = handoff_mod.read_handoff(root / "HANDOFF.md")
    handoff.current_spec = name
    handoff_mod.write_handoff(root / "HANDOFF.md", handoff)


def make_watcher(project: Path, driver: FakeDriver, **overrides):
    adapter = providers_mod.get_adapter("opencode", driver, "agent", project)
    params = {
        "session": "agent",
        "provider": "opencode",
        "initial_prompt": "please start",
        "continuation_prompt": "please continue",
        "confirmation_prompt": "please finish the rest",
        "debounce_polls": 1,
        "poll_interval_s": 0.01,
        "fresh_ready_attempts": 5,
        "fresh_ready_interval_s": 0,
    }
    params.update(overrides)
    driver.sessions["agent"] = {"command": [], "output": "", "workdir": "/t"}
    return robot_mod.RobotWatcher(
        project,
        robot_mod.RobotConfig(**params),
        driver,
        adapter,
        evidence_runner=evidence_fakes.make_runner(project),
    )


def last_record(project: Path) -> dict:
    records, _ = diagnostics_mod.read_diagnostics(project, limit=1)
    assert records, "expected at least one diagnostic record"
    return records[-1]


def approval_sends(driver: FakeDriver) -> list:
    return list(driver.sent_inputs("agent"))


class ReaskMatrixTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def test_done_reply_resumes_as_today_with_one_ask(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        asked = APPROVAL_UNKNOWN + "agent is thinking\n"
        asked_done = asked + "DONE\n"
        script = [APPROVAL_UNKNOWN, APPROVAL_UNKNOWN, asked, asked_done, asked_done]
        with unittest.mock.patch.object(watcher, "_capture", side_effect=script):
            self.assertEqual(watcher.poll(), robot_mod.WAITING)
            # Surface persists but the episode stays single-ask.
            driver.sessions["agent"]["output"] = APPROVAL_UNKNOWN
        self.assertEqual(watcher.poll(), robot_mod.WAITING)
        sent = approval_sends(driver)
        self.assertEqual(len(sent), 1)
        self.assertIn("approval prompt is showing", sent[0])
        self.assertNotIn("/new", sent)
        self.assertEqual(watcher._approval_asks, 1)
        self.assertFalse(watcher._approval_escalated)
        self.assertIn("approval", watcher.block_reason)

    def test_not_done_rearms_once_then_parks_visibly(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        asked = APPROVAL_UNKNOWN + "agent is thinking\n"
        refusing = asked + "NOT DONE\n"
        script = [
            # First poll: guard, ask baseline, settled NOT DONE reply.
            APPROVAL_UNKNOWN,
            APPROVAL_UNKNOWN,
            asked,
            refusing,
            refusing,
            # Quiet interval: three polls, guard reads only.
            APPROVAL_UNKNOWN,
            APPROVAL_UNKNOWN,
            APPROVAL_UNKNOWN,
            # Re-ask poll: guard, baseline, settled NOT DONE again.
            APPROVAL_UNKNOWN,
            APPROVAL_UNKNOWN,
            asked,
            refusing,
            refusing,
            # Parked poll: guard read only.
            APPROVAL_UNKNOWN,
        ]
        with unittest.mock.patch.object(watcher, "_capture", side_effect=script):
            for _ in range(6):
                self.assertEqual(watcher.poll(), robot_mod.WAITING)
        sent = approval_sends(driver)
        # Exactly two unconfirmed questions (natural wording only: a
        # clear NOT DONE never triggers the strict backup).
        self.assertEqual(len(sent), 2)
        for text in sent:
            self.assertIn("approval prompt is showing", text)
        self.assertNotIn(robot_mod.CONFIRM_BACKUP_TEXT, sent)
        self.assertNotIn("/new", sent)
        self.assertEqual(watcher._approval_asks, 2)
        self.assertTrue(watcher._approval_escalated)
        self.assertIn("asked twice", watcher.block_reason)
        self.assertIn("[no-operation-word]", watcher.block_reason)
        self.assertIn(
            "answer the approval in the provider session", watcher.block_reason
        )
        record = last_record(project)
        self.assertEqual(record["decision"], "waiting")
        self.assertIn("asked twice", record["blocker"])
        self.assertIn("[no-operation-word]", record["blocker"])

    def test_garbage_reply_keeps_single_ask_wait(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        watcher = make_watcher(project, driver, fresh_ready_attempts=1)
        watcher.initial_sent = True
        # Natural ask (baseline + 2 settled silent reads) plus the
        # strict backup (same shape), then three quiet guard polls.
        script = [APPROVAL_UNKNOWN] * (1 + 1 + 2 + 1 + 2 + 3)
        with unittest.mock.patch.object(watcher, "_capture", side_effect=script):
            for _ in range(4):
                self.assertEqual(watcher.poll(), robot_mod.WAITING)
        sent = approval_sends(driver)
        self.assertEqual(len(sent), 2)
        self.assertIn("approval prompt is showing", sent[0])
        self.assertEqual(sent[1], robot_mod.CONFIRM_BACKUP_TEXT)
        self.assertFalse(watcher._approval_rearm)
        self.assertFalse(watcher._approval_escalated)
        self.assertNotIn("asked twice", watcher.block_reason)

    def test_silent_surface_outlasting_reask_parks_visibly(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        asked = APPROVAL_UNKNOWN + "agent is thinking\n"
        refusing = asked + "NOT DONE\n"
        garbled = APPROVAL_UNKNOWN + "hmm\n"
        script = [
            APPROVAL_UNKNOWN,
            APPROVAL_UNKNOWN,
            asked,
            refusing,
            refusing,
            APPROVAL_UNKNOWN,
            APPROVAL_UNKNOWN,
            APPROVAL_UNKNOWN,
            # Re-ask poll: NOT DONE history, but the second ask hears
            # only garbage (natural + backup), so the outlasted surface
            # still escalates.
            APPROVAL_UNKNOWN,
            APPROVAL_UNKNOWN,
            garbled,
            garbled,
            APPROVAL_UNKNOWN,
            garbled,
            garbled,
            APPROVAL_UNKNOWN,
        ]
        with unittest.mock.patch.object(watcher, "_capture", side_effect=script):
            for _ in range(6):
                self.assertEqual(watcher.poll(), robot_mod.WAITING)
        self.assertTrue(watcher._approval_escalated)
        self.assertIn("asked twice", watcher.block_reason)
        self.assertNotIn("/new", approval_sends(driver))

    def test_cleared_surface_resets_the_episode(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        asked = APPROVAL_UNKNOWN + "agent is thinking\n"
        asked_done = asked + "DONE\n"
        script = [APPROVAL_UNKNOWN, APPROVAL_UNKNOWN, asked, asked_done, asked_done]
        with unittest.mock.patch.object(watcher, "_capture", side_effect=script):
            self.assertEqual(watcher.poll(), robot_mod.WAITING)
        self.assertEqual(watcher._approval_asks, 1)
        driver.sessions["agent"]["output"] = BUSY
        self.assertEqual(watcher.poll(), robot_mod.WORKING)
        self.assertEqual(watcher._approval_asks, 0)
        self.assertFalse(watcher._approval_rearm)
        self.assertFalse(watcher._approval_escalated)
        # A fresh stuck dialog asks again: the reset is per episode.
        driver.sessions["agent"]["output"] = APPROVAL_UNKNOWN
        self.assertEqual(watcher.poll(), robot_mod.WAITING)
        self.assertEqual(watcher._approval_asks, 1)


class RequestShapeTest(unittest.TestCase):
    def _decision(self, raw: str, policy: str = "auto"):
        # All three fixtures are unparsable surfaces (no single
        # operation + contained path), so parsed is None by contract.
        return permissions_mod.evaluate(
            provider="opencode",
            parsed=None,
            raw_tail=raw,
            policy=policy,
        )

    def test_shape_fixtures_are_unparsable_surfaces(self) -> None:
        adapter = providers_mod.get_adapter("opencode", FakeDriver(), "agent", "/tmp")
        for raw in (APPROVAL_SUDO, APPROVAL_UNKNOWN, APPROVAL_AMBIGUOUS):
            self.assertIsNone(adapter.recognize_permission(raw), raw)

    def test_privileged_surface_denies_with_shape(self) -> None:
        decision = self._decision(APPROVAL_SUDO)
        self.assertEqual(decision.result, "deny")
        self.assertIn("[privileged-markers]", decision.reason)
        self.assertNotIn("rm -rf", decision.reason)
        self.assertLessEqual(len(decision.reason), permissions_mod.MAX_REASON_CHARS)

    def test_pathless_surface_waits_with_shape(self) -> None:
        decision = self._decision(APPROVAL_UNKNOWN)
        self.assertEqual(decision.result, "waiting")
        self.assertIn("[no-operation-word]", decision.reason)
        self.assertNotIn("frobnicator", decision.reason)
        self.assertLessEqual(len(decision.reason), permissions_mod.MAX_REASON_CHARS)

    def test_ambiguous_surface_waits_with_path_count(self) -> None:
        decision = self._decision(APPROVAL_AMBIGUOUS)
        self.assertEqual(decision.result, "waiting")
        self.assertIn("[ambiguous-paths(2)]", decision.reason)
        self.assertNotIn("/a.txt", decision.reason)
        self.assertLessEqual(len(decision.reason), permissions_mod.MAX_REASON_CHARS)

    def test_shape_helper_names_all_three_classes(self) -> None:
        self.assertEqual(
            permissions_mod.request_shape(APPROVAL_SUDO), "privileged-markers"
        )
        self.assertEqual(
            permissions_mod.request_shape(APPROVAL_UNKNOWN), "no-operation-word"
        )
        self.assertEqual(
            permissions_mod.request_shape(APPROVAL_AMBIGUOUS), "ambiguous-paths(2)"
        )

    def test_waiting_blocker_carries_shape_without_raw_text(self) -> None:
        state: list = []
        project = make_project(state)
        self.addCleanup(lambda: [tmp.cleanup() for tmp in state])
        driver = FakeDriver()
        watcher = make_watcher(project, driver)
        driver.sessions["agent"]["output"] = APPROVAL_UNKNOWN
        self.assertEqual(watcher.poll(), robot_mod.WAITING)
        self.assertIn("[no-operation-word]", watcher.block_reason)
        self.assertNotIn("frobnicator", watcher.block_reason)


if __name__ == "__main__":
    unittest.main()
