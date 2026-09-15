"""Tests for the hub-keymap change: keymap menu with per-tab quit."""

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from ariadex import companion
from tests.test_robot_hub import (
    FakeHotkeyAdapter,
    FakeTkRoot,
    install_fake_tk,
    make_tab,
)


class ConfigMixin:
    def isolate_config(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        patch.start()
        self.addCleanup(patch.stop)
        return tmp


class KeymapStorageTest(unittest.TestCase, ConfigMixin):
    def setUp(self):
        self.isolate_config()

    def test_defaults(self):
        self.assertEqual(companion.effective_keymap(), dict(companion.DEFAULT_KEYMAP))

    def test_legacy_hotkey_migrates_to_yield(self):
        companion.save_user_config({"hotkey": "Alt+F9"})
        keymap = companion.effective_keymap()
        self.assertEqual(keymap["yield"], "Alt+F9")
        self.assertEqual(keymap["quit_tab"], companion.DEFAULT_KEYMAP["quit_tab"])

    def test_corrupt_file_falls_back_to_defaults(self):
        path = companion.user_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{nope", encoding="utf-8")
        self.assertEqual(companion.effective_keymap(), dict(companion.DEFAULT_KEYMAP))

    def test_non_dict_map_falls_back(self):
        companion.save_user_config({"keymap": "nope"})
        self.assertEqual(companion.effective_keymap(), dict(companion.DEFAULT_KEYMAP))

    def test_bad_entry_falls_back_per_action(self):
        companion.save_user_config({"keymap": {"quit_tab": "Hyper+Esc"}})
        keymap = companion.effective_keymap()
        self.assertEqual(keymap["quit_tab"], companion.DEFAULT_KEYMAP["quit_tab"])
        self.assertEqual(keymap["yield"], companion.DEFAULT_KEYMAP["yield"])

    def test_unknown_actions_ignored(self):
        companion.save_user_config({"keymap": {"nope": "X", "yield": "Alt+A"}})
        keymap = companion.effective_keymap()
        self.assertEqual(keymap["yield"], "Alt+A")
        self.assertNotIn("nope", keymap)

    def test_save_canonicalizes_and_preserves_settings(self):
        companion.save_user_config({"geometry": "1x1"})
        ok, reason = companion.save_keymap({"quit_tab": "ctrl+shift+q"})
        self.assertTrue(ok, reason)
        stored = companion.load_user_config()
        self.assertEqual(stored["keymap"]["quit_tab"], "Ctrl+Shift+Q")
        self.assertEqual(stored["geometry"], "1x1")

    def test_duplicate_refused_with_reason(self):
        ok, reason = companion.save_keymap(
            {"quit_tab": companion.DEFAULT_KEYMAP["yield"]}
        )
        self.assertFalse(ok)
        self.assertIn("already bound", reason)
        self.assertNotIn("keymap", companion.load_user_config())

    def test_duplicate_detected_across_case(self):
        ok, reason = companion.save_keymap({"quit_all": "ctrl+shift+q"})
        self.assertFalse(ok)
        self.assertIn("already bound", reason)

    def test_unknown_action_refused(self):
        ok, reason = companion.save_keymap({"nope": "Alt+A"})
        self.assertFalse(ok)
        self.assertIn("unknown binding", reason)

    def test_empty_value_refused(self):
        ok, reason = companion.save_keymap({"quit_tab": "  "})
        self.assertFalse(ok)
        self.assertIn("empty", reason)

    def test_unparsable_value_refused(self):
        ok, reason = companion.save_keymap({"quit_tab": "Hyper+Esc"})
        self.assertFalse(ok)
        self.assertIn("Hyper", reason)

    def test_configured_hotkey_prefers_map_yield(self):
        companion.save_user_config({"hotkey": "Alt+F9"})
        companion.save_keymap({"yield": "Alt+A"})
        self.assertEqual(companion.configured_hotkey(), "Alt+A")
        self.assertEqual(companion.configured_hotkey("Ctrl+Esc"), "Ctrl+Esc")

    def test_configured_hotkey_legacy_fallback(self):
        companion.save_user_config({"hotkey": "Alt+F9"})
        self.assertEqual(companion.configured_hotkey(), "Alt+F9")


class CaptureEventTest(unittest.TestCase):
    def test_plain_key(self):
        event = SimpleNamespace(keysym="Q", state=0)
        self.assertEqual(companion.keymap_event_to_text(event), "Q")

    def test_modifiers_prefix_in_fixed_order(self):
        event = SimpleNamespace(keysym="q", state=0x1 | 0x4)
        self.assertEqual(companion.keymap_event_to_text(event), "Shift+Ctrl+q")

    def test_escape_cancels(self):
        event = SimpleNamespace(keysym="Escape", state=0x4)
        with self.assertRaises(companion.CompanionError):
            companion.keymap_event_to_text(event)

    def test_modifier_only_keeps_waiting(self):
        for keysym in ("Shift_L", "Control_L", "Alt_L", "Super_R", "Caps_Lock"):
            self.assertIsNone(
                companion.keymap_event_to_text(SimpleNamespace(keysym=keysym, state=0))
            )

    def test_empty_keysym_keeps_waiting(self):
        self.assertIsNone(companion.keymap_event_to_text(SimpleNamespace()))


class RecordingFactory:
    def __init__(self):
        self.adapters: list[FakeHotkeyAdapter] = []

    def __call__(self):
        adapter = FakeHotkeyAdapter()
        self.adapters.append(adapter)
        return adapter


class HubKeymapTest(unittest.TestCase, ConfigMixin):
    def setUp(self):
        install_fake_tk(self)
        self.isolate_config()
        self.factory = RecordingFactory()

    def _window(self, entries=("a", "b", "c"), active=0):
        made = [make_tab(f"/home/u/{p}") for p in entries]
        tabs = [tab for tab, _ in made]
        watchers = [watcher for _, watcher in made]
        root = FakeTkRoot()
        window = companion.RobotHubWindow(
            root, tabs, adapter_factory=self.factory, active=active
        )
        return window, root, watchers

    def _callbacks(self):
        return {
            hotkey: callback
            for adapter in self.factory.adapters
            for hotkey, callback in adapter.registered
        }

    def test_one_grab_per_action(self):
        window, _root, _watchers = self._window()
        self.assertEqual(len(self.factory.adapters), 4)
        grabbed = sorted(h for a in self.factory.adapters for h, _ in a.registered)
        self.assertEqual(grabbed, sorted(window.keymap.values()))
        self.assertEqual(len(set(grabbed)), 4)

    def test_yield_never_quits(self):
        window, root, watchers = self._window()
        self._callbacks()[window.keymap["yield"]]()
        marshalled = [
            func for _, func in root.after_calls if func.__name__ == "_on_pause_active"
        ]
        self.assertEqual(len(marshalled), 1)
        marshalled[0]()
        self.assertEqual(len(window.tabs), 3)
        self.assertIn("pause", watchers[window.active].calls)
        for watcher in watchers:
            self.assertNotIn("quit", watcher.calls)

    def test_quit_tab_detaches_only_visible_tab(self):
        window, _root, watchers = self._window(active=1)
        self._callbacks()[window.keymap["quit_tab"]]()
        # Marshal runs on the Tk thread; nothing happens before it.
        self.assertEqual(len(window.tabs), 3)
        for _, func in list(window.root.after_calls):
            if func.__name__ == "_on_quit_active":
                func()
        self.assertEqual([t.project for t in window.tabs], ["/home/u/a", "/home/u/c"])
        self.assertIn("quit", watchers[1].calls)
        self.assertNotIn("quit", watchers[0].calls)
        self.assertNotIn("quit", watchers[2].calls)
        self.assertIsNotNone(window._poll_after)

    def test_quit_all_ends_hub(self):
        window, root, watchers = self._window()
        self._callbacks()[window.keymap["quit_all"]]()
        for _, func in list(root.after_calls):
            if func.__name__ == "_on_quit_all":
                func()
        self.assertTrue(root.destroyed)
        for watcher in watchers:
            self.assertIn("quit", watcher.calls)
        for adapter in self.factory.adapters:
            self.assertEqual(adapter.unregistered, 1)

    def test_last_tab_quit_matches_quit_button_path(self):
        window, root, watchers = self._window(entries=("a",))
        self._callbacks()[window.keymap["quit_tab"]]()
        for _, func in list(root.after_calls):
            if func.__name__ == "_on_quit_active":
                func()
        self.assertEqual(window.tabs, [])
        self.assertTrue(root.destroyed)
        self.assertIsNone(window._poll_after)
        for adapter in self.factory.adapters:
            self.assertEqual(adapter.unregistered, 1)
        self.assertIn("quit", watchers[0].calls)

    def test_toggle_key_expands_log(self):
        window, _root, _watchers = self._window()
        self.assertFalse(window.expanded)
        self._callbacks()[window.keymap["toggle_expand"]]()
        for _, func in list(window.root.after_calls):
            if func.__name__ == "_on_toggle":
                func()
        self.assertTrue(window.expanded)

    def test_rebind_regrabs_without_stacking(self):
        window, _root, _watchers = self._window()
        ok, reason = companion.save_keymap({"quit_tab": "Alt+T"})
        self.assertTrue(ok, reason)
        window.keymap["quit_tab"] = "Alt+T"
        window._register_keymap()
        self.assertEqual(len(self.factory.adapters), 8)
        for adapter in self.factory.adapters[:4]:
            self.assertEqual(adapter.unregistered, 1)
        grabbed = [h for a in self.factory.adapters[4:] for h, _ in a.registered]
        self.assertIn("Alt+T", grabbed)

    def test_refused_binding_recorded_not_crash(self):
        def failing():
            adapter = FakeHotkeyAdapter()
            adapter.register = lambda *a: (_ for _ in ()).throw(
                companion.CompanionError("taken")
            )
            return adapter

        root = FakeTkRoot()
        made = [make_tab("/home/u/a")]
        window = companion.RobotHubWindow(
            root, [tab for tab, _ in made], adapter_factory=failing
        )
        self.assertEqual(len(window.keymap_errors), 4)
        self.assertEqual(window.tabs, [tab for tab, _ in made])


class KeymapMenuTest(unittest.TestCase, ConfigMixin):
    def setUp(self):
        install_fake_tk(self)
        self.isolate_config()
        self.factory = RecordingFactory()
        made = [make_tab("/home/u/a")]
        self.root = FakeTkRoot()
        self.window = companion.RobotHubWindow(
            self.root, [tab for tab, _ in made], adapter_factory=self.factory
        )

    def test_menu_lists_every_binding(self):
        self.window.keys_button.invoke()
        self.assertTrue(self.window.keymap_frame.packed)
        for action in companion.KEYMAP_ACTIONS:
            label = self.window.key_labels[action]
            self.assertIn(self.window.keymap[action], label.options.get("text", ""))

    def test_menu_toggle_hides(self):
        self.window.keys_button.invoke()
        self.window.keys_button.invoke()
        self.assertFalse(self.window.keymap_frame.packed)

    def _capture(self, action, keysym, state=0):
        set_button = self.window.key_set_buttons[action]
        set_button.invoke()
        handler = self.root.options.get("bind:<KeyPress>")
        self.assertIsNotNone(handler)
        handler(SimpleNamespace(keysym=keysym, state=state))

    def test_capture_rebinds_and_regrabs(self):
        self.window.keys_button.invoke()
        self._capture("quit_tab", "T", state=0x8)
        self.assertEqual(self.window.keymap["quit_tab"], "Alt+T")
        self.assertIn("Alt+T", self.window.key_labels["quit_tab"].options["text"])
        self.assertIn("is now", self.window.keymap_feedback.options["text"])
        self.assertNotIn("bind:<KeyPress>", self.root.options)
        grabbed = [h for a in self.factory.adapters for h, _ in a.registered]
        self.assertIn("Alt+T", grabbed)
        self.assertNotIn(
            companion.DEFAULT_KEYMAP["quit_tab"],
            [h for a in self.factory.adapters[4:] for h, _ in a.registered],
        )

    def test_capture_duplicate_refused_inline(self):
        self.window.keys_button.invoke()
        before = dict(self.window.keymap)
        self._capture("quit_tab", "Esc", state=0x4)  # Ctrl+Esc == yield
        self.assertEqual(self.window.keymap, before)
        self.assertIn("already bound", self.window.keymap_feedback.options["text"])

    def test_capture_escape_cancels(self):
        self.window.keys_button.invoke()
        before = dict(self.window.keymap)
        self._capture("quit_tab", "Escape")
        self.assertEqual(self.window.keymap, before)
        self.assertIn("cancelled", self.window.keymap_feedback.options["text"])

    def test_capture_modifier_only_keeps_waiting(self):
        self.window.keys_button.invoke()
        before = dict(self.window.keymap)
        self._capture("quit_tab", "Shift_L")
        self.assertEqual(self.window.keymap, before)
        self.assertIn("bind:<KeyPress>", self.root.options)


class MiniYieldTest(unittest.TestCase, ConfigMixin):
    def setUp(self):
        from tests.test_companion import (
            FakeAdapter,
            FakeClient,
            FakeTkRoot,
            install_fake_tk,
        )

        self.isolate_config()
        install_fake_tk(self)
        self.window = companion.CompanionWindow(
            FakeTkRoot(), FakeClient(), FakeAdapter(), "Ctrl+Esc"
        )

    def test_apply_hotkey_persists_map_and_legacy(self):
        self.window.hotkey_var.set("Alt+F9")
        self.window._apply_hotkey()
        self.assertEqual(self.window.hotkey, "Alt+F9")
        stored = companion.load_user_config()
        self.assertEqual(stored["keymap"]["yield"], "Alt+F9")
        self.assertEqual(stored["hotkey"], "Alt+F9")
        self.assertEqual(companion.configured_hotkey(), "Alt+F9")

    def test_apply_duplicate_hotkey_refused(self):
        companion.save_keymap(
            {"quit_tab": "Alt+T", "quit_all": "Alt+X", "toggle_expand": "Alt+E"}
        )
        self.window.hotkey_var.set("Alt+T")
        self.window._apply_hotkey()
        self.assertEqual(self.window.hotkey, "Ctrl+Esc")
        self.assertIn("already bound", str(self.window.model.get("failure")))

    def test_keys_line_lists_bindings(self):
        companion.save_keymap({"quit_tab": "Alt+T"})
        self.window._render()
        text = self.window.keymap_label.options.get("text", "")
        self.assertIn("Alt+T", text)
        self.assertIn(companion.configured_hotkey(), text)
        self.assertIn("quit all", text)


if __name__ == "__main__":
    unittest.main()
