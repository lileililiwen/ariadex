"""End the draft-defer stall loop (watcher-stall-loop).

Covers the structural composer-region draft rule (scrollback output
above the composer is never a draft), diagnosed draft/pause defers
with record-after-gate ordering and debounce reset, the multi-poll
loop proof (one conversation record, eventual prompt delivery), and
the once-guard 3-tuple key shape.
"""

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from ariadex import diagnostics as diagnostics_mod
from ariadex import handoff as handoff_mod
from ariadex import openspec_evidence as evidence_mod
from ariadex import providers as providers_mod
from ariadex import robot as robot_mod
from ariadex import terminal as terminal_mod
from ariadex.adapters import InputSurface

try:
    import evidence_fakes
except ModuleNotFoundError:
    from tests import evidence_fakes  # type: ignore[no-redef]

# Incident shape (2026-09-16): `┃`-prefixed assistant/test scrollback
# above a blank idle composer with its status bar and bottom border.
# The old marker-tight rule read the scrollback as a human draft and
# deferred every poll while rewriting the conversation record.
IDLE_SCROLLBACK = (
    "┃ 483 passed in 12.7s\n"
    "┃ coverage: 86 percent, floors pass\n"
    "done: verification complete, 0 problems\n"
    "\n"
    "▣  Build · minimax-m3 · 4m 25s\n"
    "\n"
    "┃\n"
    "┃\n"
    "┃\n"
    "┃  Build · minimax-m3 newapi\n"
    "╹▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀\n"
    "/home/paul/code/ariadex\n"
)

GENUINE_DRAFT = (
    "▣  Build · minimax-m3 · 4m 25s\n"
    "\n"
    "┃\n"
    "┃ operator-typed correction\n"
    "┃  Build · minimax-m3 newapi\n"
    "╹▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀\n"
    "/home/paul/code/ariadex\n"
)

LEGACY_BORDERLESS_DRAFT = "Ask anything\n┃ unfinished request\n▣ Build · x\n"


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


class StructuralDraftTest(unittest.TestCase):
    def _adapter(self):
        driver = FakeDriver()
        return providers_mod.get_adapter("opencode", driver, "s", "/tmp")

    def test_scrollback_over_idle_composer_is_not_a_draft(self) -> None:
        self.assertIs(
            self._adapter().input_surface(IDLE_SCROLLBACK), InputSurface.EMPTY
        )

    def test_genuine_composer_draft_still_defers(self) -> None:
        self.assertIs(self._adapter().input_surface(GENUINE_DRAFT), InputSurface.DRAFT)

    def test_unverifiable_surface_without_border_fails_closed(self) -> None:
        # No border structure: the legacy rule applies unchanged, so a
        # `┃`-prefixed line still fails closed toward DRAFT.
        self.assertIs(
            self._adapter().input_surface(LEGACY_BORDERLESS_DRAFT),
            InputSurface.DRAFT,
        )


class DeferDiagnosticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def _idle_provider(self, watcher):
        return (
            unittest.mock.patch.object(
                watcher.adapter, "provider_state", return_value="idle"
            ),
            unittest.mock.patch.object(
                type(watcher.adapter),
                "provider_state_required",
                new_callable=unittest.mock.PropertyMock,
                return_value=True,
            ),
        )

    def test_confirmation_draft_defer_is_diagnosed_without_record_churn(
        self,
    ) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo")
        driver = FakeDriver()
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        watcher.stable_polls = 5
        driver.sessions["agent"]["output"] = GENUINE_DRAFT
        state_patch, required_patch = self._idle_provider(watcher)
        calls: list = []
        orig = evidence_mod.record_conversation

        def counting(*args, **kwargs):
            calls.append(1)
            return orig(*args, **kwargs)

        with (
            state_patch,
            required_patch,
            unittest.mock.patch.object(
                evidence_mod, "record_conversation", side_effect=counting
            ),
        ):
            self.assertEqual(watcher.poll(), robot_mod.PAUSED)
        self.assertEqual(calls, [])
        self.assertEqual(watcher.stable_polls, 0)
        self.assertEqual(watcher.confirmations_sent, 0)
        sent = driver.sent_inputs("agent")
        self.assertNotIn("/new", sent)
        self.assertNotIn("please finish the rest", sent)
        record = last_record(project)
        self.assertEqual(record["decision"], "deferred")
        self.assertEqual(record["current_spec"], "demo")
        self.assertEqual(record["operation"], "new-conversation")
        self.assertTrue(record["blocker"])
        self.assertTrue(record["next_action"])

    def test_confirmation_pause_defer_is_diagnosed_without_record_churn(
        self,
    ) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo")
        driver = FakeDriver()
        mode = ["AUTO"]
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        watcher.stable_polls = 5
        watcher.mode_requested = lambda: mode[0]

        def flipping_capture() -> str:
            # The boundary fires on the first read; PAUSE lands before
            # the confirmation gate runs.
            if flipping_capture.calls == 0:
                flipping_capture.calls += 1
                return IDLE_SCROLLBACK
            mode[0] = "PAUSE"
            return IDLE_SCROLLBACK

        flipping_capture.calls = 0  # type: ignore[attr-defined]
        calls: list = []
        orig = evidence_mod.record_conversation

        def counting(*args, **kwargs):
            calls.append(1)
            return orig(*args, **kwargs)

        with (
            unittest.mock.patch.object(
                watcher, "_capture", side_effect=flipping_capture
            ),
            unittest.mock.patch.object(
                evidence_mod, "record_conversation", side_effect=counting
            ),
        ):
            self.assertEqual(watcher.poll(), robot_mod.PAUSED)
        self.assertEqual(calls, [])
        self.assertEqual(watcher.stable_polls, 0)
        self.assertEqual(driver.sent_inputs("agent"), [])
        record = last_record(project)
        self.assertEqual(record["decision"], "deferred")
        self.assertEqual(record["current_spec"], "demo")
        self.assertTrue(record["next_action"])

    def test_continuation_draft_defer_is_diagnosed_without_record_churn(
        self,
    ) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo")
        driver = FakeDriver()
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        watcher.stable_polls = 3
        driver.sessions["agent"]["output"] = GENUINE_DRAFT
        check = robot_mod.BoundaryCheck(
            ok=True,
            reason="",
            active=["demo"],
            decision="complete",
            current_spec="",
            open_tasks=0,
            task_detail="",
            evidence_source="internal",
        )
        calls: list = []
        orig = evidence_mod.record_conversation

        def counting(*args, **kwargs):
            calls.append(1)
            return orig(*args, **kwargs)

        with unittest.mock.patch.object(
            evidence_mod, "record_conversation", side_effect=counting
        ):
            self.assertEqual(watcher._open_continuation(check), robot_mod.PAUSED)
        self.assertEqual(calls, [])
        self.assertEqual(watcher.stable_polls, 0)
        self.assertEqual(driver.sent_inputs("agent"), [])
        record = last_record(project)
        self.assertEqual(record["decision"], "deferred")
        self.assertEqual(record["current_spec"], "demo")
        self.assertTrue(record["next_action"])


class StallLoopRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def test_scrollback_boundary_sends_one_recorded_confirmation(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo")
        driver = FakeDriver()
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        echo = "provider echoed the readiness ask"
        echo_done = echo + "\nDONE"
        script = [IDLE_SCROLLBACK, IDLE_SCROLLBACK, echo, echo_done, echo_done]
        script.append(IDLE_SCROLLBACK)  # fresh-ready surface
        calls: list = []
        orig = evidence_mod.record_conversation

        def counting(*args, **kwargs):
            calls.append(1)
            return orig(*args, **kwargs)

        with (
            unittest.mock.patch.object(watcher, "_capture", side_effect=script),
            unittest.mock.patch.object(watcher.adapter, "new_conversation"),
            unittest.mock.patch.object(
                evidence_mod, "record_conversation", side_effect=counting
            ),
        ):
            self.assertEqual(watcher.poll(), robot_mod.CONTINUING)
        self.assertEqual(len(calls), 1)
        self.assertEqual(watcher.confirmations_sent, 1)
        self.assertEqual(watcher.stable_polls, 0)
        sent = driver.sent_inputs("agent")
        self.assertTrue(any("DONE or WORKING" in text for text in sent), sent)
        self.assertIn("please finish the rest", sent)

    def test_once_guard_skips_on_matching_three_tuple_key(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        watcher = make_watcher(project, driver)
        watcher._readiness_asked = ("demo", "tasks", 1)
        self.assertEqual(
            watcher._ask_readiness("demo", 1, ["demo"], "internal"), "unknown"
        )
        self.assertEqual(driver.sent_inputs("agent"), [])


if __name__ == "__main__":
    unittest.main()
