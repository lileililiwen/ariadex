"""Task-aware confirmation recovery and widget activity log.

Covers the fourth managed prompt (`confirmation_prompt`), the task-aware
boundary decision (complete/unfinished/empty/blocked), watcher prompt
selection with bounded repeated confirmation, readiness/quota/error
safety, bounded redacted activity events, pure widget view models, and
Tk expand/collapse wiring.
"""

import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

from ariadex import config as config_mod
from ariadex import handoff as handoff_mod
from ariadex import providers as providers_mod
from ariadex import robot as robot_mod
from ariadex import terminal as terminal_mod

try:
    import evidence_fakes
except ModuleNotFoundError:
    from tests import evidence_fakes  # type: ignore[no-redef]

READY = "Welcome back\nAsk anything · tab agents\n> "
BUSY = "running tool `pytest` …\nesc to interrupt\n"
QUOTA = "Ask anything · tab agents\nModel quota expired. Switch model.\n> "
APPROVAL = "Ask anything\nApproval required: allow `rm`? [y/n]\n"
ERROR = "Ask anything\nerror: provider exploded\n"
MAX_STEP_LIMIT = "Ask anything\nerror: maximum step limit reached\n"


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


def make_change(root: Path, name: str, tasks: str, current: bool = True) -> None:
    change = root / "openspec" / "changes" / name
    change.mkdir(parents=True, exist_ok=True)
    (change / "tasks.md").write_text(tasks, encoding="utf-8")
    if current:
        handoff = handoff_mod.read_handoff(root / "HANDOFF.md")
        handoff.current_spec = name
        handoff_mod.write_handoff(root / "HANDOFF.md", handoff)


def make_watcher(
    project: Path, driver: FakeDriver, provider: str = "opencode", **overrides
):
    adapter = providers_mod.get_adapter(provider, driver, "agent", project)
    params = {
        "session": "agent",
        "provider": provider,
        "initial_prompt": "please start",
        "continuation_prompt": "please continue",
        "confirmation_prompt": "please finish the rest",
        "debounce_polls": 1,
        "poll_interval_s": 0.01,
    }
    params.update(overrides)
    evidence_runner = params.pop("evidence_runner", None)
    if evidence_runner is None:
        evidence_runner = evidence_fakes.make_runner(project)
    return robot_mod.RobotWatcher(
        project,
        robot_mod.RobotConfig(**params),
        driver,
        adapter,
        evidence_runner=evidence_runner,
    )


def clean_git(test: unittest.TestCase):
    return unittest.mock.patch.object(
        robot_mod, "_git_tree_clean", return_value=(True, "")
    )


class ConfirmationConfigTest(unittest.TestCase):
    def test_robot_and_config_defaults_agree_and_stay_distinct(self) -> None:
        self.assertEqual(
            robot_mod.DEFAULT_ROBOT_CONFIRMATION_PROMPT,
            config_mod.DEFAULT_CONFIRMATION_PROMPT,
        )
        self.assertTrue(config_mod.DEFAULT_CONFIRMATION_PROMPT.strip())
        self.assertNotEqual(
            config_mod.DEFAULT_CONFIRMATION_PROMPT,
            config_mod.DEFAULT_MANAGED_PROMPT,
        )
        cfg = config_mod.defaults()
        self.assertEqual(
            cfg.confirmation_prompt, config_mod.DEFAULT_CONFIRMATION_PROMPT
        )

    def test_blank_confirmation_rejected_everywhere(self) -> None:
        with self.assertRaises(config_mod.ConfigError):
            config_mod.validate({"confirmation_prompt": "  "}, source="test")
        with self.assertRaises(config_mod.ConfigError):
            config_mod.validate({"confirmation_prompt": ["x"]}, source="test")
        with self.assertRaises(robot_mod.RobotError):
            robot_mod.validate_config(
                robot_mod.RobotConfig(
                    session="s", initial_prompt="go", confirmation_prompt=" "
                )
            )

    def test_existing_config_gains_default_without_touching_others(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / config_mod.CONFIG_REL_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "agent_provider: codex\n"
                "first_prompt: First!\n"
                "continuation_prompt: Next!\n",
                encoding="utf-8",
            )
            missing = config_mod.migrate_managed_prompt_keys(root)
            self.assertEqual(missing, ["confirmation_prompt"])
            cfg = config_mod.load(root)
            self.assertEqual(cfg.first_prompt, "First!")
            self.assertEqual(cfg.continuation_prompt, "Next!")
            self.assertEqual(
                cfg.confirmation_prompt, config_mod.DEFAULT_CONFIRMATION_PROMPT
            )


class BoundaryDecisionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def _config(self, **overrides):
        params = {
            "session": "agent",
            "provider": "opencode",
            "initial_prompt": "go",
        }
        params.update(overrides)
        return robot_mod.RobotConfig(**params)

    def _check(self, project, config):
        return robot_mod.check_boundary(
            project, config, evidence_fakes.make_runner(project)
        )

    def test_unfinished_tasks_are_ok_but_marked_unfinished(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [x] Done\n- [ ] Open it\n")
        with clean_git(self):
            check = self._check(project, self._config())
        self.assertTrue(check.ok)
        self.assertEqual(check.decision, "unfinished")
        self.assertEqual(check.current_spec, "demo")
        self.assertEqual(check.open_tasks, 1)
        self.assertIn("Open it", check.task_detail)

    def test_completed_tasks_request_archival_not_advancement(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [x] Done\n")
        with clean_git(self):
            check = self._check(project, self._config())
        self.assertTrue(check.ok)
        self.assertEqual(check.decision, "ready-to-archive")
        self.assertEqual(check.current_spec, "demo")
        self.assertEqual(check.open_tasks, 0)
        self.assertIn("archive", check.task_detail)
        self.assertEqual(check.evidence_source, "openspec")

    def test_empty_queue_is_marked_empty(self) -> None:
        project = make_project(self._tmp)
        with clean_git(self):
            check = self._check(project, self._config())
        self.assertTrue(check.ok)
        self.assertEqual(check.decision, "empty")
        self.assertEqual(check.active, [])

    def test_invalid_task_metadata_blocks_without_prompt_equivalence(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [x] Done\n")
        (project / "openspec" / "changes" / "demo" / "tasks.md").unlink()
        with clean_git(self):
            check = self._check(project, self._config())
        self.assertFalse(check.ok)
        self.assertEqual(check.decision, "blocked")
        self.assertIn("tasks.md", check.reason)

    def test_finished_change_override_selects_target(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "other", "# Tasks\n\n- [ ] Other work\n", current=False)
        make_change(project, "demo", "# Tasks\n\n- [x] Done\n")
        with clean_git(self):
            check = self._check(project, self._config(finished_change="other"))
        self.assertTrue(check.ok)
        self.assertEqual(check.decision, "unfinished")
        self.assertEqual(check.current_spec, "other")


class PromptSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def test_unfinished_tasks_send_confirmation_in_fresh_conversation(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [x] Done\n- [ ] Open it\n")
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        with clean_git(self):
            watcher.poll()  # initial prompt
            self.assertEqual(watcher.poll(), "continuing")
        sent = driver.sent_inputs("agent")
        self.assertEqual(sent[0], "please start")
        self.assertIn("/new", sent)
        self.assertEqual(sent[-1], "please finish the rest")
        self.assertEqual(watcher.confirmations_sent, 1)
        view = watcher.status_view()
        self.assertTrue(
            any("confirmation" in entry["message"] for entry in view["activity"])
        )

    def test_dirty_partial_work_still_sends_confirmation(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Open it\n")
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        with unittest.mock.patch.object(
            robot_mod, "_git_tree_clean", return_value=(False, "uncommitted changes")
        ):
            watcher.poll()  # initial prompt
            self.assertEqual(watcher.poll(), "continuing")
        self.assertEqual(driver.sent_inputs("agent")[-1], "please finish the rest")
        self.assertEqual(watcher.confirmations_sent, 1)

    def test_complete_but_active_tasks_request_archival_confirmation(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [x] Done\n")
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        with clean_git(self):
            watcher.poll()
            self.assertEqual(watcher.poll(), "continuing")
        sent = driver.sent_inputs("agent")
        self.assertEqual(sent[0], "please start")
        self.assertIn("/new", sent)
        # Tasks are complete but the change is still active: the watcher
        # must not advance. It recovers with the confirmation prompt and
        # an archival instruction instead.
        self.assertEqual(sent[-1], "please finish the rest")
        self.assertEqual(watcher.confirmations_sent, 1)
        view = watcher.status_view()
        self.assertTrue(
            any("archive" in entry["message"] for entry in view["activity"])
        )

    def test_empty_queue_stops_without_any_prompt(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        with clean_git(self):
            self.assertEqual(watcher.poll(), "done")
        self.assertEqual(driver.sent_inputs("agent"), [])
        self.assertEqual(watcher.prompts_sent, 0)

    def test_repeated_confirmation_then_archival_recovery(self) -> None:
        project = make_project(self._tmp)
        tasks = project / "openspec" / "changes" / "demo" / "tasks.md"
        make_change(project, "demo", "# Tasks\n\n- [ ] One\n- [ ] Two\n")
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        with clean_git(self):
            watcher.poll()
            self.assertEqual(watcher.poll(), "continuing")
            self.assertEqual(watcher.confirmations_sent, 1)
            driver.sessions["agent"]["output"] = READY
            watcher.stable_polls = 0
            self.assertEqual(watcher.poll(), "continuing")
            self.assertEqual(watcher.confirmations_sent, 2)
            tasks.write_text("# Tasks\n\n- [x] One\n- [x] Two\n", encoding="utf-8")
            driver.sessions["agent"]["output"] = READY
            watcher.stable_polls = 0
            self.assertEqual(watcher.poll(), "continuing")
        sent = driver.sent_inputs("agent")
        # Two task-recovery confirmations plus the archival follow-up: a
        # complete-but-active change must not advance to continuation.
        self.assertEqual(sent.count("please finish the rest"), 3)
        self.assertEqual(sent[-1], "please finish the rest")
        self.assertEqual(watcher.confirmations_sent, 3)
        view = watcher.status_view()
        self.assertTrue(
            any("archive" in entry["message"] for entry in view["activity"])
        )

    def test_quota_approval_error_never_trigger_confirmation(self) -> None:
        for surface, phase in (
            (QUOTA, robot_mod.WAITING),
            (APPROVAL, robot_mod.WAITING),
            (ERROR, robot_mod.BLOCKED),
        ):
            with self.subTest(surface=phase):
                project = make_project(self._tmp)
                make_change(project, "demo", "# Tasks\n\n- [ ] Open\n")
                driver = FakeDriver()
                driver.sessions["agent"] = {
                    "command": [],
                    "output": surface,
                    "workdir": "/t",
                }
                watcher = make_watcher(project, driver)
                with clean_git(self):
                    self.assertEqual(watcher.poll(), phase)
                self.assertEqual(driver.sent_inputs("agent"), [])
                self.assertEqual(watcher.confirmations_sent, 0)

    def test_confirmation_refires_when_fresh_surface_missing(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Open\n")
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver, fresh_ready_attempts=1)
        with clean_git(self):
            watcher.poll()  # initial prompt
            with unittest.mock.patch.object(
                watcher, "_capture", side_effect=[READY, READY, "blank screen"]
            ):
                self.assertEqual(watcher.poll(), "working")
        self.assertEqual(watcher.block_reason, "")
        self.assertNotIn("please finish the rest", driver.sent_inputs("agent"))
        self.assertEqual(watcher.confirmations_sent, 0)

    def test_max_step_limit_opens_recovery_conversation(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Open\n")
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        watcher.initial_sent = True
        with (
            clean_git(self),
            unittest.mock.patch.object(
                watcher, "_capture", side_effect=[MAX_STEP_LIMIT, READY, READY]
            ),
            unittest.mock.patch.object(watcher.adapter, "new_conversation"),
        ):
            self.assertEqual(watcher.poll(), "continuing")
        self.assertEqual(driver.sent_inputs("agent"), ["please finish the rest"])
        self.assertEqual(watcher.confirmations_sent, 1)

    def test_invalid_metadata_sends_no_confirmation(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [x] Done\n")
        (project / "openspec" / "changes" / "demo" / "tasks.md").unlink()
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        with clean_git(self):
            watcher.poll()
            self.assertEqual(watcher.poll(), "blocked")
        self.assertIn("tasks.md", watcher.block_reason)
        self.assertEqual(driver.sent_inputs("agent"), ["please start"])


class ActivityEventTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def test_events_are_bounded(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": BUSY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        for index in range(robot_mod.MAX_ACTIVITY_EVENTS + 15):
            watcher._record("working", f"event {index}")
        self.assertEqual(len(watcher.activity_events), robot_mod.MAX_ACTIVITY_EVENTS)
        view = watcher.status_view()
        self.assertLessEqual(len(view["activity"]), robot_mod.MAX_ACTIVITY_VIEW)
        self.assertEqual(view["latest_event"]["message"], "event 64")

    def test_events_redact_truncate_and_exclude_captures(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": BUSY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        watcher._record("boundary", "token=supersecretvalue " + "x" * 500)
        event = watcher.activity_events[-1]
        self.assertNotIn("supersecretvalue", event["message"])
        self.assertLessEqual(len(event["message"]), robot_mod.MAX_ACTIVITY_MESSAGE)
        self.assertNotIn(READY, event["message"])


class ActivityViewModelTest(unittest.TestCase):
    def test_collapsed_model_carries_latest_and_bounded_activity(self) -> None:
        from ariadex import companion as companion_mod

        status = {
            "phase": "continuing",
            "provider": "opencode",
            "session": "agent",
            "latest_event": {"category": "prompt", "message": "sent confirmation"},
            "activity": [
                {"category": "boundary", "message": "unfinished: 1 open"},
                {"category": "prompt", "message": "sent confirmation"},
            ],
        }
        model = companion_mod.build_robot_view_model(status)
        self.assertEqual(model["indicator"], "working")
        self.assertIn("sent confirmation", model["latest_text"])
        self.assertEqual(len(model["activity"]), 2)
        text = companion_mod.format_robot_text(model)
        self.assertIn("latest: prompt: sent confirmation", text)
        self.assertIn("- boundary: unfinished: 1 open", text)

    def test_empty_model_is_honest(self) -> None:
        from ariadex import companion as companion_mod

        model = companion_mod.build_robot_view_model({})
        self.assertEqual(model["latest_text"], "no activity yet")
        self.assertEqual(model["activity"], [])
        self.assertIn("activity: (none)", companion_mod.format_robot_text(model))

    def test_long_or_sensitive_entries_are_truncated(self) -> None:
        from ariadex import companion as companion_mod

        model = companion_mod.build_robot_view_model(
            {
                "phase": "blocked",
                "block_reason": "b" * 500,
                "activity": [{"category": "error", "message": "x" * 500}],
            }
        )
        self.assertLessEqual(len(model["activity"][0]["message"]), 280)


class FakeTkWidget:
    def __init__(self, master=None, **options):
        self.options = dict(options)
        self.packed = False
        self.command = options.get("command")

    def pack(self, **kwargs):
        self.packed = True

    def pack_forget(self):
        self.packed = False

    def configure(self, **options):
        self.options.update(options)

    config = configure

    def invoke(self):
        if self.command is not None:
            self.command()


class FakeTkText(FakeTkWidget):
    def __init__(self, master=None, **options):
        super().__init__(master, **options)
        self.content = ""

    def delete(self, start, end):
        self.content = ""

    def insert(self, index, text):
        self.content = text


class FakeTkRoot(FakeTkWidget):
    def __init__(self):
        super().__init__(None)
        self.destroyed = False
        self._seq = 0

    def title(self, text):
        self.options["title"] = text

    def overrideredirect(self, flag):
        pass

    def attributes(self, *args):
        pass

    def geometry(self, spec):
        self.options["geometry"] = spec

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    def after(self, ms, func=None):
        self._seq += 1
        return f"after{self._seq}"

    def after_cancel(self, token):
        pass

    def destroy(self):
        self.destroyed = True


def install_fake_tk(test: unittest.TestCase):
    tk_mod = types.ModuleType("tkinter")
    tk_mod.Tk = FakeTkRoot  # type: ignore[attr-defined]
    tk_mod.Frame = FakeTkWidget  # type: ignore[attr-defined]
    tk_mod.Label = FakeTkWidget  # type: ignore[attr-defined]
    tk_mod.Button = FakeTkWidget  # type: ignore[attr-defined]
    tk_mod.Text = FakeTkText  # type: ignore[attr-defined]
    saved = sys.modules.get("tkinter")
    sys.modules["tkinter"] = tk_mod

    def restore():
        if saved is None:
            sys.modules.pop("tkinter", None)
        else:
            sys.modules["tkinter"] = saved

    test.addCleanup(restore)


class RobotLogWidgetTest(unittest.TestCase):
    def setUp(self) -> None:
        install_fake_tk(self)

    def _window(self, status):
        from ariadex import companion as companion_mod

        def status_fn():
            return dict(status)

        return companion_mod.RobotWindow(
            FakeTkRoot(),
            status_fn,
            on_pause=lambda: "paused",
            on_quit=lambda: "stopped",
        )

    def test_collapsed_shows_latest_event(self) -> None:
        window = self._window(
            {
                "phase": "continuing",
                "provider": "opencode",
                "session": "agent",
                "latest_event": {
                    "category": "prompt",
                    "message": "confirmation recovery selected",
                },
                "activity": [
                    {
                        "category": "prompt",
                        "message": "confirmation recovery selected",
                    }
                ],
            }
        )
        self.assertIn(
            "confirmation recovery selected", window.event_label.options["text"]
        )
        self.assertFalse(window.expanded)
        self.assertEqual(window.toggle_button.options["text"], "Show log")

    def test_expand_collapse_renders_read_only_log(self) -> None:
        window = self._window(
            {
                "phase": "working",
                "provider": "opencode",
                "session": "agent",
                "activity": [{"category": "boundary", "message": "verified"}],
            }
        )
        window.toggle_button.invoke()
        self.assertTrue(window.expanded)
        self.assertEqual(window.toggle_button.options["text"], "Hide log")
        self.assertIn("verified", window.log_text.content)
        self.assertEqual(window.log_text.options.get("state"), "disabled")
        self.assertFalse(window.log_text.options.get("takefocus", False))
        window.toggle_button.invoke()
        self.assertFalse(window.expanded)
        self.assertFalse(window.log_text.packed)

    def test_empty_log_is_honest(self) -> None:
        window = self._window({"phase": "working"})
        window.toggle_button.invoke()
        self.assertIn("(no activity yet)", window.log_text.content)

    def test_unreachable_log_keeps_controls(self) -> None:
        from ariadex import companion as companion_mod

        window = companion_mod.RobotWindow(
            FakeTkRoot(),
            lambda: (_ for _ in ()).throw(RuntimeError("no watcher")),
            on_pause=lambda: "paused",
            on_quit=lambda: "stopped",
        )
        window.toggle_button.invoke()
        self.assertIn("unreachable", window.log_text.content.lower())
        self.assertEqual(window.state_label.options["text"], "UNREACHABLE")

    def test_blocked_log_preserves_reason(self) -> None:
        window = self._window({"phase": "blocked", "block_reason": "tasks.md missing"})
        window.toggle_button.invoke()
        self.assertIn("tasks.md missing", window.log_text.content)


DRAFT = "Ask anything\n┃ user is typing a correction\n▣ Build · x\n"


class ConfirmationDraftGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def test_confirmation_defers_while_draft_present(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Open it\n")
        driver = FakeDriver()
        driver.sessions["agent"] = {"command": [], "output": READY, "workdir": "/t"}
        watcher = make_watcher(project, driver)
        with clean_git(self):
            watcher.poll()  # initial prompt
            driver.sessions["agent"]["output"] = DRAFT
            # Production TmuxDriver path: the backend reports idle while the
            # composer holds a draft, so the boundary fires and the guard
            # must defer instead of sending `/new` over the draft.
            with (
                unittest.mock.patch.object(
                    watcher.adapter, "provider_state", return_value="idle"
                ),
                unittest.mock.patch.object(
                    type(watcher.adapter),
                    "provider_state_required",
                    new_callable=unittest.mock.PropertyMock,
                    return_value=True,
                ),
            ):
                self.assertEqual(watcher.poll(), robot_mod.PAUSED)
        sent = driver.sent_inputs("agent")
        self.assertEqual(sent, ["please start"])
        self.assertNotIn("/new", sent)
        self.assertEqual(watcher.confirmations_sent, 0)


if __name__ == "__main__":
    unittest.main()
