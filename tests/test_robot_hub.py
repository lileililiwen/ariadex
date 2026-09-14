"""Regression coverage for the multi-project robot hub window."""

import sys
import types
import unittest
from unittest import mock

from ariadex import companion as companion_mod


class FakeTkWidget:
    def __init__(self, master=None, **options):
        self.options = dict(options)
        self.packed = False
        self.forgotten = False
        self.command = options.get("command")
        self.text = ""
        self._children: list = []
        self._destroyed = False
        if master is not None and hasattr(master, "_children"):
            master._children.append(self)

    def pack(self, **kwargs):
        self.packed = True
        self.forgotten = False

    def pack_forget(self):
        self.forgotten = True
        self.packed = False

    def winfo_children(self):
        return [c for c in self._children if not c._destroyed]

    def destroy(self):
        self._destroyed = True

    def configure(self, **options):
        self.options.update(options)

    config = configure

    def bind(self, sequence, callback):
        self.options[f"bind:{sequence}"] = callback

    def delete(self, start, end=None):
        self.text = ""

    def insert(self, index, text):
        self.text = text

    def invoke(self):
        if self.command is not None:
            self.command()


class FakeTkRoot(FakeTkWidget):
    def __init__(self):
        super().__init__(None)
        self.after_calls: list = []
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

    def protocol(self, name, func):
        self.options[f"protocol:{name}"] = func

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    def winfo_x(self):
        return 100

    def winfo_y(self):
        return 100

    def after(self, ms, func=None):
        self._seq += 1
        token = f"after{self._seq}"
        if func is not None:
            self.after_calls.append((ms, func))
        return token

    def after_cancel(self, token):
        pass

    def mainloop(self):
        pass

    def destroy(self):
        self.destroyed = True


def install_fake_tk(test: unittest.TestCase):
    tk_mod = types.ModuleType("tkinter")
    tk_mod.Tk = FakeTkRoot  # type: ignore[attr-defined]
    tk_mod.Frame = FakeTkWidget  # type: ignore[attr-defined]
    tk_mod.Label = FakeTkWidget  # type: ignore[attr-defined]
    tk_mod.Button = FakeTkWidget  # type: ignore[attr-defined]
    tk_mod.Text = FakeTkWidget  # type: ignore[attr-defined]
    saved = sys.modules.get("tkinter")
    sys.modules["tkinter"] = tk_mod

    def restore():
        if saved is None:
            sys.modules.pop("tkinter", None)
        else:
            sys.modules["tkinter"] = saved

    test.addCleanup(restore)


class FakeWatcher:
    """Minimal RobotWatcherBoundary double with call recording."""

    def __init__(self, status):
        self._status = dict(status)
        self.calls: list[str] = []

    def status_view(self):
        return dict(self._status)

    def set_status(self, status):
        self._status = dict(status)

    def request_pause(self):
        self.calls.append("pause")
        return "paused"

    def request_resume(self):
        self.calls.append("resume")
        return "resumed"

    def request_quit(self):
        self.calls.append("quit")
        return "quit"

    def run(self):
        self.calls.append("run")
        return None


class FakeHotkeyAdapter:
    def __init__(self):
        self.registered: list = []
        self.unregistered = 0

    def register(self, hotkey, callback):
        self.registered.append((hotkey, callback))

    def unregister(self):
        self.unregistered += 1


def make_tab(
    project, provider="opencode", session="agent", phase="working", queue=None
):
    watcher = FakeWatcher({"provider": provider, "session": session, "phase": phase})
    tab = companion_mod.RobotHubTab(
        project=project,
        label=companion_mod.hub_tab_label(project, provider),
        status_fn=watcher.status_view,
        on_pause=watcher.request_pause,
        on_resume=watcher.request_resume,
        on_quit=watcher.request_quit,
        run_fn=watcher.run,
        queue_fn=(lambda: dict(queue)) if queue is not None else None,
    )
    return tab, watcher


class HubLabelTest(unittest.TestCase):
    def test_label_is_folder_plus_provider(self):
        self.assertEqual(
            companion_mod.hub_tab_label("/home/user/a", "opencode"), "a [opencode]"
        )
        self.assertEqual(
            companion_mod.hub_tab_label("/home/user/b", "codebuddy"), "b [codebuddy]"
        )

    def test_long_basename_truncates(self):
        label = companion_mod.hub_tab_label("/x/" + "a" * 40, "codex")
        self.assertTrue(label.endswith("[codex]"))
        name = label[: -len(" [codex]")]
        self.assertEqual(len(name), companion_mod.HUB_TAB_LABEL_MAX)

    def test_root_falls_back_to_full_path(self):
        label = companion_mod.hub_tab_label("/", "opencode")
        self.assertIn("[opencode]", label)
        self.assertTrue(label.startswith("/"))


class HubDisambiguationTest(unittest.TestCase):
    def test_distinct_basenames_unchanged(self):
        labels = companion_mod.disambiguate_hub_labels(
            [("/home/u/a", "opencode", "s1"), ("/home/u/b", "codex", "s2")]
        )
        self.assertEqual(labels, ["a [opencode]", "b [codex]"])

    def test_basename_collision_gains_parent(self):
        labels = companion_mod.disambiguate_hub_labels(
            [("/x/a", "opencode", "s1"), ("/y/a", "opencode", "s2")]
        )
        self.assertEqual(labels, ["x/a [opencode]", "y/a [opencode]"])

    def test_deep_collision_falls_back_to_session(self):
        labels = companion_mod.disambiguate_hub_labels(
            [("/x/a", "opencode", "s1"), ("/x/a", "opencode", "s2")]
        )
        self.assertEqual(labels, ["x/a@s1 [opencode]", "x/a@s2 [opencode]"])

    def test_fully_identical_entries_still_terminate_unique(self):
        labels = companion_mod.disambiguate_hub_labels(
            [("/x/a", "opencode", "s"), ("/x/a", "opencode", "s")]
        )
        self.assertEqual(len(set(labels)), 2)

    def test_provider_distinguishes_same_project(self):
        labels = companion_mod.disambiguate_hub_labels(
            [("/x/api", "opencode", "s1"), ("/x/api", "codex", "s2")]
        )
        self.assertEqual(labels, ["api [opencode]", "api [codex]"])


class HubViewModelTest(unittest.TestCase):
    def _models(self, phases):
        return [
            companion_mod.build_robot_view_model({"phase": phase}) for phase in phases
        ]

    def test_blocked_beats_working(self):
        hub = companion_mod.build_hub_view_model(
            self._models(["working", "blocked"]), ["a", "b"]
        )
        self.assertEqual(hub["hub_indicator"], "blocked")
        self.assertEqual(hub["hub_indicator_text"], "BLOCKED")
        self.assertIn("2", hub["title"])

    def test_unreachable_beats_working(self):
        models = self._models(["working"])
        models[0]["indicator"] = "stopped"
        models[0]["indicator_text"] = "UNREACHABLE"
        hub = companion_mod.build_hub_view_model(models, ["a"])
        self.assertEqual(hub["hub_indicator"], "unreachable")
        self.assertEqual(hub["hub_indicator_text"], "UNREACHABLE")

    def test_all_stopped_is_stopped(self):
        hub = companion_mod.build_hub_view_model(
            self._models(["stopped", "stopped"]), ["a", "b"]
        )
        self.assertEqual(hub["hub_indicator"], "stopped")

    def test_terminal_mix_prefers_completed(self):
        hub = companion_mod.build_hub_view_model(
            self._models(["stopped", "done"]), ["a", "b"]
        )
        self.assertEqual(hub["hub_indicator"], "completed")

    def test_active_index_is_clamped(self):
        hub = companion_mod.build_hub_view_model(self._models(["working"]), ["a"], 9)
        self.assertEqual(hub["active"], 0)


class RobotHubWindowTest(unittest.TestCase):
    def setUp(self):
        install_fake_tk(self)

    def _window(
        self,
        entries=(
            ("a", "opencode", "s1", "working"),
            ("b", "codex", "s2", "working"),
            ("c", "codebuddy", "s3", "paused"),
        ),
    ):
        made = [
            make_tab(f"/home/u/{p}", prov, sess, phase)
            for p, prov, sess, phase in entries
        ]
        tabs = [tab for tab, _ in made]
        watchers = [watcher for _, watcher in made]
        root = FakeTkRoot()
        window = companion_mod.RobotHubWindow(root, tabs)
        return window, root, watchers

    def test_empty_hub_allowed_for_auto_join(self):
        window = companion_mod.RobotHubWindow(FakeTkRoot(), [])
        self.assertEqual(window.tabs, [])
        self.assertEqual(window.tab_buttons, [])

    def test_add_and_remove_tab(self):
        root = FakeTkRoot()
        window = companion_mod.RobotHubWindow(root, [])
        tab, _watcher = make_tab("/home/u/a")
        window.add_tab(tab)
        self.assertEqual(len(window.tabs), 1)
        self.assertEqual(len(window.tab_buttons), 1)
        window.add_tab(tab)
        self.assertEqual(len(window.tabs), 1)
        window.remove_project("/home/u/a")
        self.assertEqual(window.tabs, [])
        self.assertTrue(root.destroyed)

    def test_remove_unknown_project_is_noop(self):
        window, root, _watchers = self._window()
        window.remove_project("/home/u/nope")
        self.assertEqual(len(window.tabs), 3)
        self.assertFalse(root.destroyed)

    def test_tab_buttons_match_entries(self):
        window, _root, _watchers = self._window()
        self.assertEqual(len(window.tab_buttons), 3)
        texts = [b.options.get("text", "") for b in window.tab_buttons]
        self.assertTrue(any("a [opencode]" in t for t in texts))
        self.assertTrue(any("b [codex]" in t for t in texts))
        self.assertTrue(any("c [codebuddy]" in t for t in texts))

    def test_pause_active_tab_only(self):
        window, _root, watchers = self._window()
        window.active = 1
        window._on_pause_active()
        self.assertEqual(watchers[0].calls, [])
        self.assertIn("pause", watchers[1].calls)
        self.assertEqual(watchers[2].calls, [])

    def test_resume_when_active_tab_paused(self):
        window, _root, watchers = self._window((("a", "opencode", "s1", "paused"),))
        window._on_pause_active()
        self.assertIn("resume", watchers[0].calls)
        self.assertNotIn("pause", watchers[0].calls)

    def test_pause_all_fan_out_skips_stopped(self):
        window, _root, watchers = self._window(
            (("a", "opencode", "s1", "working"), ("b", "codex", "s2", "stopped"))
        )
        window._on_pause_all()
        self.assertIn("pause", watchers[0].calls)
        self.assertEqual(watchers[1].calls, [])

    def test_hotkey_scoped_to_active_tab(self):
        window, _root, watchers = self._window()
        window.active = 2
        window._on_hotkey()
        # Hotkey marshals through root.after; drain the queued callback.
        for _ms, func in list(window.root.after_calls):
            func()
        self.assertEqual(watchers[0].calls, [])
        self.assertEqual(watchers[1].calls, [])
        self.assertTrue(watchers[2].calls)

    def test_tab_switch_sends_no_input(self):
        window, _root, watchers = self._window()
        window._select_fn(2)()
        for watcher in watchers:
            self.assertEqual(watcher.calls, [])
        self.assertEqual(window.active, 2)
        identity = window.identity_label.options.get("text", "")
        self.assertIn("/home/u/c", identity)

    def test_unreachable_tab_isolated(self):
        window, _root, _watchers = self._window()
        window.tabs[1].status_fn = _raising_status
        window._refresh()
        self.assertEqual(window.models[1]["indicator_text"], "UNREACHABLE")
        self.assertEqual(window.models[0]["indicator"], "working")
        self.assertEqual(window.models[2]["indicator"], "paused")

    def test_quit_active_detaches_only_that_tab(self):
        window, root, watchers = self._window()
        window.active = 1
        window._on_quit_active()
        self.assertIn("quit", watchers[1].calls)
        self.assertNotIn("quit", watchers[0].calls)
        self.assertNotIn("quit", watchers[2].calls)
        self.assertFalse(root.destroyed)
        self.assertEqual(len(window.tabs), 2)

    def test_quit_middle_tab_keeps_buttons_consistent(self):
        window, _root, watchers = self._window()
        window.active = 1
        window._on_quit_active()
        self.assertIn("quit", watchers[1].calls)
        self.assertEqual(len(window.tabs), 2)
        self.assertEqual(len(window.tab_buttons), 2)
        self.assertEqual(len(window.models), 2)
        self.assertEqual(len(window.queue_texts), 2)
        window.tab_buttons[1].invoke()
        self.assertEqual(window.active, 1)
        self.assertIn("/home/u/c", window.identity_label.options.get("text", ""))
        window._on_toggle()
        self.assertTrue(window.expanded)
        self.assertIn("prompts", window.stats_label.options.get("text", ""))

    def test_quit_last_tab_destroys_hub(self):
        window, root, watchers = self._window((("a", "opencode", "s1", "working"),))
        adapter = FakeHotkeyAdapter()
        window.hotkey_adapter = adapter
        window._on_quit_active()
        self.assertIn("quit", watchers[0].calls)
        self.assertTrue(root.destroyed)
        self.assertEqual(adapter.unregistered, 1)

    def test_close_quits_all_in_tab_order(self):
        window, root, _watchers = self._window()
        order: list[str] = []
        for i, tab in enumerate(window.tabs):
            tab.on_quit = _recording_quit(order, i)
        adapter = FakeHotkeyAdapter()
        window.hotkey_adapter = adapter
        window._on_quit_all()
        self.assertEqual(order, [0, 1, 2])
        self.assertTrue(root.destroyed)
        self.assertEqual(adapter.unregistered, 1)

    def test_initial_placement_is_bounded(self):
        _window, root, _watchers = self._window()
        geometry = root.options["geometry"]
        self.assertIn("+", geometry)
        coords = geometry.split("+")[1:]
        x, y = int(coords[0]), int(coords[1])
        self.assertLessEqual(x + companion_mod.WIDGET_WIDTH, 1920)
        self.assertLessEqual(y + companion_mod.HUB_COLLAPSED_HEIGHT, 1080)

    def test_geometry_uses_hub_heights(self):
        window, root, _watchers = self._window()
        self.assertGreater(
            companion_mod.HUB_COLLAPSED_HEIGHT,
            companion_mod.WIDGET_COLLAPSED_HEIGHT,
        )
        window._on_toggle()
        size = root.options["geometry"].split("+")[0]
        self.assertTrue(
            size.startswith(
                f"{companion_mod.WIDGET_WIDTH}x{companion_mod.HUB_EXPANDED_HEIGHT}"
            ),
            size,
        )
        window._on_toggle()
        size = root.options["geometry"].split("+")[0]
        self.assertTrue(
            size.startswith(
                f"{companion_mod.WIDGET_WIDTH}x{companion_mod.HUB_COLLAPSED_HEIGHT}"
            ),
            size,
        )

    def test_close_button_closes_only_the_window(self):
        window, root, watchers = self._window()
        self.assertEqual(window.close_button.options.get("text"), "Close")
        window.close_button.invoke()
        self.assertTrue(root.destroyed)
        for watcher in watchers:
            self.assertEqual(watcher.calls, [])

    def test_hub_titlebar_drag_moves_window(self):
        window, root, _watchers = self._window()
        window._drag_start(mock.Mock(x_root=150, y_root=250))
        window._drag_move(mock.Mock(x_root=300, y_root=400))
        self.assertIn("+", root.options["geometry"])
        window._drag_stop(mock.Mock())

    def test_hub_copy_log_button_copies_active_log(self):
        window, _root, _watchers = self._window()
        window.models[0]["activity"] = [
            {"category": "provider", "message": "backend is ready"}
        ]
        with mock.patch.object(
            companion_mod, "copy_to_clipboard", return_value=None
        ) as copy:
            window.copy_log_button.invoke()
        copy.assert_called_once()
        self.assertIn("backend is ready", copy.call_args.args[1])

    def test_toggle_expands_without_input(self):
        window, _root, watchers = self._window()
        window._on_toggle()
        self.assertTrue(window.expanded)
        for watcher in watchers:
            self.assertEqual(watcher.calls, [])


def _raising_status():
    raise RuntimeError("boom")


def _recording_quit(order, index):
    def quit_tab():
        order.append(index)
        return "quit"

    return quit_tab


class ParseHubEntryTest(unittest.TestCase):
    def test_two_part_entry(self):
        from ariadex import cli as cli_mod

        self.assertEqual(
            cli_mod.parse_hub_entry("/home/u/a:agent"),
            ("/home/u/a", "agent", None),
        )

    def test_three_part_entry(self):
        from ariadex import cli as cli_mod

        self.assertEqual(
            cli_mod.parse_hub_entry("/home/u/a:agent:codex"),
            ("/home/u/a", "agent", "codex"),
        )

    def test_malformed_entries_refused(self):
        from ariadex import cli as cli_mod
        from ariadex import robot as robot_mod

        for bad in ["justpath", "a:b:c:d", ":agent", "/x/a:  ", "/x/a:s:  "]:
            with self.subTest(entry=bad), self.assertRaises(robot_mod.RobotError):
                cli_mod.parse_hub_entry(bad)


class WatchHubCommandTest(unittest.TestCase):
    def test_no_widget_combination_refused(self):
        from pathlib import Path

        from ariadex import cli as cli_mod

        rc = cli_mod.cmd_watch_hub(
            Path("/tmp"), ["/tmp/a:s"], widget=False, auto_install=False
        )
        self.assertNotEqual(rc, 0)

    def test_duplicate_entries_start_nothing(self):
        import tempfile
        from pathlib import Path

        from ariadex import cli as cli_mod

        with tempfile.TemporaryDirectory() as tmp:
            rc = cli_mod.cmd_watch_hub(
                Path(tmp),
                [f"{tmp}/a:s", f"{tmp}/a:s"],
                initial_prompt="hi",
                auto_install=False,
            )
            self.assertNotEqual(rc, 0)

    def test_missing_project_dir_refused(self):
        import tempfile
        from pathlib import Path

        from ariadex import cli as cli_mod

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                cli_mod.tmux_setup_mod, "ensure_tmux", return_value="tmux"
            ):
                rc = cli_mod.cmd_watch_hub(
                    Path(tmp),
                    [f"{tmp}/nope:s"],
                    initial_prompt="hi",
                    auto_install=True,
                )
            self.assertNotEqual(rc, 0)

    def test_unsupported_entry_provider_refused(self):
        import tempfile
        from pathlib import Path

        from ariadex import cli as cli_mod

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                cli_mod.tmux_setup_mod, "ensure_tmux", return_value="tmux"
            ):
                rc = cli_mod.cmd_watch_hub(
                    Path(tmp),
                    [f"{tmp}:s:claude"],
                    initial_prompt="hi",
                    auto_install=True,
                )
            self.assertNotEqual(rc, 0)


class FakeHubAdapter:
    def __init__(self, provider):
        self.provider_name = provider
        self.started = 0

    def start(self):
        self.started += 1


class WatchHubSuccessTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path

        from ariadex import cli as cli_mod
        from ariadex import terminal as terminal_mod

        self.cli_mod = cli_mod
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ("a", "b"):
            (self.root / name).mkdir()
        self.driver = terminal_mod.FakeTerminalDriver()
        self.adapters: dict[str, FakeHubAdapter] = {}
        self.alive = lambda *names: [
            self.driver.create_or_connect(n, str(self.root), ["opencode"])
            for n in names
        ]

        def make_adapter(provider, driver, session, workdir):
            adapter = FakeHubAdapter(provider)
            self.adapters[session] = adapter
            return adapter

        self.tmux_patch = mock.patch.object(
            cli_mod.tmux_setup_mod, "ensure_tmux", return_value="tmux"
        )
        self.tmux_patch.start()
        self.addCleanup(self.tmux_patch.stop)
        self.adapter_patch = mock.patch.object(
            cli_mod.providers_mod, "get_adapter", side_effect=make_adapter
        )
        self.adapter_patch.start()
        self.addCleanup(self.adapter_patch.stop)
        self.hub_patch = mock.patch.object(
            cli_mod.companion_mod, "run_robot_hub", return_value=0
        )
        self.run_hub = self.hub_patch.start()
        self.addCleanup(self.hub_patch.stop)

    def _hub(self, *specs, **kwargs):
        kwargs.setdefault("initial_prompt", "go")
        kwargs.setdefault("provider", "opencode")
        kwargs.setdefault("driver", self.driver)
        return self.cli_mod.cmd_watch_hub(self.root, list(specs), **kwargs)

    def test_two_entries_open_one_hub(self):
        self.alive("sa", "sb")
        rc = self._hub(f"{self.root}/a:sa", f"{self.root}/b:sb:codex")
        self.assertEqual(rc, 0)
        (tabs,), _ = self.run_hub.call_args
        for tab in tabs:
            self.assertIsNotNone(tab.queue_fn)
            assert tab.queue_fn is not None
            summary = tab.queue_fn()
            self.assertIn("not an OpenSpec project", summary["unavailable"])
        self.assertEqual([t.label for t in tabs], ["a [opencode]", "b [codex]"])
        self.assertEqual(
            [t.project for t in tabs],
            [str(self.root / "a"), str(self.root / "b")],
        )
        for tab in tabs:
            self.assertTrue(callable(tab.run_fn))
            self.assertEqual(tab.status_fn(), tab.status_fn())

    def test_duplicate_basenames_disambiguated(self):
        (self.root / "x").mkdir()
        (self.root / "x" / "a").mkdir()
        (self.root / "y").mkdir()
        (self.root / "y" / "a").mkdir()
        self.alive("sa", "sb")
        rc = self._hub(f"{self.root}/x/a:sa", f"{self.root}/y/a:sb")
        self.assertEqual(rc, 0)
        (tabs,), _ = self.run_hub.call_args
        self.assertEqual([t.label for t in tabs], ["x/a [opencode]", "y/a [opencode]"])

    def test_missing_initial_prompt_refused(self):
        rc = self.cli_mod.cmd_watch_hub(
            self.root,
            [f"{self.root}/a:sa"],
            provider="opencode",
            driver=self.driver,
        )
        self.assertNotEqual(rc, 0)
        self.run_hub.assert_not_called()

    def test_dead_session_without_create_refused(self):
        rc = self._hub(f"{self.root}/a:missing")
        self.assertNotEqual(rc, 0)
        self.run_hub.assert_not_called()

    def test_create_starts_missing_session(self):
        rc = self._hub(f"{self.root}/a:created", create=True)
        self.assertEqual(rc, 0)
        self.assertEqual(self.adapters["created"].started, 1)
        self.run_hub.assert_called_once()

    def test_adapter_failure_refused(self):
        self.alive("sa")
        with mock.patch.object(
            self.cli_mod.providers_mod,
            "get_adapter",
            side_effect=Exception("nope"),
        ):
            rc = self._hub(f"{self.root}/a:sa")
        self.assertNotEqual(rc, 0)
        self.run_hub.assert_not_called()

    def test_entry_config_supplies_prompts(self):
        import types as _types

        cfg = _types.SimpleNamespace(
            agent_provider="codex",
            continuation_prompt="cont",
            confirmation_prompt="conf",
            spec_dir="openspec/changes",
            handoff_file="HANDOFF.md",
        )
        self.alive("sa")
        with mock.patch.object(self.cli_mod, "_load_config", return_value=cfg):
            rc = self.cli_mod.cmd_watch_hub(
                self.root,
                [f"{self.root}/a:sa"],
                initial_prompt="go",
                driver=self.driver,
            )
        self.assertEqual(rc, 0)
        (tabs,), _ = self.run_hub.call_args
        self.assertEqual(tabs[0].label, "a [codex]")

    def test_hub_failure_returns_error(self):
        self.alive("sa")
        with mock.patch.object(
            self.cli_mod.companion_mod,
            "run_robot_hub",
            side_effect=self.cli_mod.companion_mod.CompanionError("no display"),
        ):
            rc = self._hub(f"{self.root}/a:sa")
        self.assertNotEqual(rc, 0)

    def test_keyboard_interrupt_quits_tabs(self):
        tabs_holder: dict = {}

        def fake_hub(tabs, **kwargs):
            tabs_holder["tabs"] = tabs
            raise KeyboardInterrupt

        self.alive("sa")
        with mock.patch.object(
            self.cli_mod.companion_mod, "run_robot_hub", side_effect=fake_hub
        ):
            rc = self._hub(f"{self.root}/a:sa")
        self.assertEqual(rc, 0)
        self.assertEqual(len(tabs_holder["tabs"]), 1)


class QueueSummaryTest(unittest.TestCase):
    def _config(self, **overrides):
        kwargs = {
            "spec_dir": "openspec/changes",
            "handoff_file": "HANDOFF.md",
            "finished_change": "",
        }
        kwargs.update(overrides)
        return kwargs

    def _project(self, tmp, changes=("a", "b"), current="a", tasks=None):
        from pathlib import Path

        from ariadex import handoff as handoff_mod

        root = Path(tmp) / "proj"
        root.mkdir()
        specdir = root / "openspec" / "changes"
        specdir.mkdir(parents=True)
        for change in changes:
            (specdir / change).mkdir()
        if current is not None and current in changes:
            (specdir / current / "tasks.md").write_text(
                tasks if tasks is not None else "- [ ] one\n- [x] two\n- [ ] three\n",
                encoding="utf-8",
            )
        handoff = handoff_mod.empty_handoff()
        handoff.current_spec = current
        handoff_mod.write_handoff(root / "HANDOFF.md", handoff)
        return root

    def test_full_evidence(self):
        import tempfile

        from ariadex import robot as robot_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            summary = robot_mod.queue_summary(root, **self._config())
        self.assertEqual(summary["active_count"], 2)
        self.assertEqual(summary["current_spec"], "a")
        self.assertEqual(summary["open_tasks"], 2)
        self.assertEqual(summary["total_tasks"], 3)
        self.assertEqual(summary["unavailable"], "")

    def test_finished_change_override_selects_target(self):
        import tempfile

        from ariadex import robot as robot_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            (root / "openspec" / "changes" / "b" / "tasks.md").write_text(
                "- [x] done\n", encoding="utf-8"
            )
            summary = robot_mod.queue_summary(root, **self._config(finished_change="b"))
        self.assertEqual(summary["current_spec"], "b")
        self.assertEqual(summary["open_tasks"], 0)
        self.assertEqual(summary["total_tasks"], 1)

    def test_missing_spec_dir_is_not_openspec(self):
        import tempfile
        from pathlib import Path

        from ariadex import robot as robot_mod

        with tempfile.TemporaryDirectory() as tmp:
            summary = robot_mod.queue_summary(Path(tmp), **self._config())
        self.assertEqual(summary["active_count"], 0)
        self.assertIn("not an OpenSpec project", summary["unavailable"])

    def test_empty_queue_has_no_current_spec(self):
        import tempfile

        from ariadex import robot as robot_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp, changes=(), current=None)
            summary = robot_mod.queue_summary(root, **self._config())
        self.assertEqual(summary["active_count"], 0)
        self.assertEqual(summary["current_spec"], "")
        self.assertEqual(summary["unavailable"], "")

    def test_missing_tasks_md_is_unavailable(self):
        import tempfile

        from ariadex import robot as robot_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp, tasks=None)
            (root / "openspec" / "changes" / "a" / "tasks.md").unlink()
            summary = robot_mod.queue_summary(root, **self._config())
        self.assertEqual(summary["current_spec"], "a")
        self.assertIn("tasks.md", summary["unavailable"])

    def test_malformed_handoff_is_unavailable(self):
        import tempfile

        from ariadex import robot as robot_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            (root / ".ariadex" / "handoff.md").write_text(
                "---\nversion: 1\ncurrent_spec: a\n", encoding="utf-8"
            )
            summary = robot_mod.queue_summary(root, **self._config())
        self.assertEqual(summary["active_count"], 2)
        self.assertIn("handoff", summary["unavailable"])

    def test_watcher_method_matches_function(self):
        import tempfile

        from ariadex import robot as robot_mod
        from ariadex import terminal as terminal_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            watcher = robot_mod.RobotWatcher(
                root,
                robot_mod.RobotConfig(
                    session="s",
                    provider="opencode",
                    initial_prompt="go",
                    continuation_prompt="cont",
                    confirmation_prompt="conf",
                    **self._config(),
                ),
                terminal_mod.FakeTerminalDriver(),
                FakeHubAdapter("opencode"),
            )
            self.assertEqual(
                watcher.queue_summary(),
                robot_mod.queue_summary(root, **self._config()),
            )

    def test_never_raises_on_unreadable_tree(self):
        from pathlib import Path

        from ariadex import robot as robot_mod

        summary = robot_mod.queue_summary(
            Path("/nonexistent-ariadex-hub-probe"), **self._config()
        )
        self.assertTrue(summary["unavailable"])


class FormatHubQueueTextTest(unittest.TestCase):
    def test_full_summary(self):
        self.assertEqual(
            companion_mod.format_hub_queue_text(
                {
                    "active_count": 2,
                    "current_spec": "my-change",
                    "open_tasks": 2,
                    "total_tasks": 5,
                    "unavailable": "",
                }
            ),
            "queue: 2 active · my-change 2/5 open",
        )

    def test_empty_queue(self):
        self.assertEqual(
            companion_mod.format_hub_queue_text(
                {
                    "active_count": 0,
                    "current_spec": "",
                    "open_tasks": 0,
                    "total_tasks": 0,
                    "unavailable": "",
                }
            ),
            "queue: empty",
        )

    def test_active_without_current_spec(self):
        self.assertEqual(
            companion_mod.format_hub_queue_text(
                {
                    "active_count": 3,
                    "current_spec": "",
                    "open_tasks": 0,
                    "total_tasks": 0,
                    "unavailable": "",
                }
            ),
            "queue: 3 active · no current spec",
        )

    def test_unavailable_reason_shown(self):
        self.assertEqual(
            companion_mod.format_hub_queue_text(
                {
                    "active_count": 0,
                    "current_spec": "",
                    "open_tasks": 0,
                    "total_tasks": 0,
                    "unavailable": "not an OpenSpec project",
                }
            ),
            "queue: n/a (not an OpenSpec project)",
        )

    def test_invalid_numbers_coerced(self):
        text = companion_mod.format_hub_queue_text(
            {
                "active_count": "many",
                "current_spec": "c",
                "open_tasks": None,
                "total_tasks": "x",
                "unavailable": "",
            }
        )
        self.assertEqual(text, "queue: 0 active · c 0/0 open")


class HubDetailRowsTest(unittest.TestCase):
    def setUp(self):
        install_fake_tk(self)

    def _window(self, queue):
        tab, _watcher = make_tab("/home/u/a", "opencode", "s1", "working", queue=queue)
        root = FakeTkRoot()
        return companion_mod.RobotHubWindow(root, [tab]), root

    def test_rows_render_active_tab(self):
        window, _root = self._window(
            {
                "active_count": 2,
                "current_spec": "my-change",
                "open_tasks": 2,
                "total_tasks": 5,
                "unavailable": "",
            }
        )
        header = window.state_label.options.get("text", "")
        self.assertIn("WORKING", header)
        self.assertIn("my-change", header)
        self.assertIn("/home/u/a", window.identity_label.options.get("text", ""))
        self.assertIn("opencode @ s1", window.session_label.options.get("text", ""))
        self.assertEqual(
            window.queue_label.options.get("text", ""),
            "queue: 2 active · my-change 2/5 open",
        )
        latest = window.event_label.options.get("text", "")
        self.assertTrue(latest.startswith("latest"))

    def test_stats_visible_only_when_expanded(self):
        window, _root = self._window(
            {
                "active_count": 0,
                "current_spec": "",
                "open_tasks": 0,
                "total_tasks": 0,
                "unavailable": "",
            }
        )
        self.assertIn("prompts 0", window.stats_label.options.get("text", ""))
        self.assertTrue(window.stats_label.forgotten)
        window._on_toggle()
        self.assertFalse(window.stats_label.forgotten)
        window._on_toggle()
        self.assertTrue(window.stats_label.forgotten)

    def test_failing_queue_fn_isolated(self):
        tab, _watcher = make_tab("/home/u/a")
        tab.queue_fn = _raising_queue
        other, _ = make_tab(
            "/home/u/b",
            "codex",
            "s2",
            "working",
            queue={
                "active_count": 1,
                "current_spec": "c",
                "open_tasks": 0,
                "total_tasks": 1,
                "unavailable": "",
            },
        )
        root = FakeTkRoot()
        window = companion_mod.RobotHubWindow(root, [tab, other])
        self.assertIn("n/a (boom)", window.queue_texts[0])
        self.assertEqual(window.queue_specs[0], "")
        self.assertIn("c 0/1 open", window.queue_texts[1])
        header = window.state_label.options.get("text", "")
        self.assertIn("a [opencode]", header)

    def test_missing_queue_fn_honest(self):
        window, _root = self._window(None)
        self.assertIn("no queue source", window.queue_label.options.get("text", ""))

    def test_tab_switch_updates_rows_without_input(self):
        first, watcher_a = make_tab(
            "/home/u/a",
            queue={
                "active_count": 1,
                "current_spec": "spec-a",
                "open_tasks": 1,
                "total_tasks": 2,
                "unavailable": "",
            },
        )
        second, watcher_b = make_tab(
            "/home/u/b",
            "codex",
            "s2",
            queue={
                "active_count": 1,
                "current_spec": "spec-b",
                "open_tasks": 0,
                "total_tasks": 1,
                "unavailable": "",
            },
        )
        root = FakeTkRoot()
        window = companion_mod.RobotHubWindow(root, [first, second])
        window._select_fn(1)()
        self.assertIn("spec-b", window.state_label.options.get("text", ""))
        self.assertIn("spec-b 0/1 open", window.queue_label.options.get("text", ""))
        self.assertEqual(watcher_a.calls, [])
        self.assertEqual(watcher_b.calls, [])


def _raising_queue():
    raise RuntimeError("boom")


class RunRobotHubTest(unittest.TestCase):
    def setUp(self):
        install_fake_tk(self)

    def test_empty_tabs_refused(self):
        with self.assertRaises(companion_mod.CompanionError):
            companion_mod.run_robot_hub([])

    def test_unsupported_desktop_starts_nothing(self):
        tab, watcher = make_tab("/home/u/a")
        with (
            mock.patch.object(
                companion_mod,
                "detect_desktop",
                return_value=companion_mod.DesktopInfo("headless", False, "no display"),
            ),
            self.assertRaises(companion_mod.CompanionError),
        ):
            companion_mod.run_robot_hub([tab])
        self.assertEqual(watcher.calls, [])


if __name__ == "__main__":
    unittest.main()
