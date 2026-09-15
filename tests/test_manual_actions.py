"""Tests for the manual-actions change: retry, model, message."""

import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ariadex import cli, companion, config, daemon
from tests.test_daemon import init_project
from tests.test_robot_hub import FakeTkRoot, install_fake_tk, make_tab

READY = "┃\n\n▣  Build · opencode · 1m\n"
DRAFT = "┃ write the tests first\n\n▣  Build · opencode · 1m\n"


def make_driver():
    from tests.test_robot import FakeDriver

    return FakeDriver()


def make_watcher(project, driver, provider="opencode", **overrides):
    from tests.test_robot import make_watcher as harness

    return harness(project, driver, provider, **overrides)


def make_project():
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    (root / ".ariadex").mkdir(parents=True)
    return tmp, root


class ConfigModelsTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = make_project()
        self.addCleanup(self.tmp.cleanup)

    def test_models_default_empty(self):
        self.assertEqual(config.defaults().models, [])

    def test_init_prompt_round_trips_models(self):
        answers = iter(["", "", "", "", "", "", "", "", "opencode/gpt-5,codex/o3"])
        code = cli.cmd_init(self.root, read_answer=lambda prompt: next(answers))
        self.assertEqual(code, 0)
        self.assertEqual(config.load(self.root).models, ["opencode/gpt-5", "codex/o3"])

    def test_blank_models_answer_means_none(self):
        code = cli.cmd_init(self.root, read_answer=lambda prompt: "")
        self.assertEqual(code, 0)
        self.assertEqual(config.load(self.root).models, [])

    def test_invalid_models_rejected(self):
        (self.root / ".ariadex" / "config.yaml").write_text(
            "models: [ok, 7]\n", encoding="utf-8"
        )
        with self.assertRaises(config.ConfigError):
            config.load(self.root)

    def test_missing_models_key_migrates_to_default(self):
        code = cli.cmd_init(self.root, read_answer=lambda prompt: "")
        self.assertEqual(code, 0)
        path = self.root / ".ariadex" / "config.yaml"
        text = "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.startswith("models:")
        )
        path.write_text(text + "\n", encoding="utf-8")
        self.assertEqual(config.load(self.root).models, [])


class IPCPayloadTest(unittest.TestCase):
    def test_send_message_round_trip(self):
        built = daemon.build_request("send_message", {"text": "hi"})
        request_type, payload = daemon.parse_request(json.dumps(built))
        self.assertEqual((request_type, payload), ("send_message", {"text": "hi"}))

    def test_switch_model_round_trip(self):
        built = daemon.build_request("switch_model", {"model": "codex/o3"})
        request_type, payload = daemon.parse_request(json.dumps(built))
        self.assertEqual(
            (request_type, payload), ("switch_model", {"model": "codex/o3"})
        )

    def test_retry_takes_no_payload(self):
        self.assertEqual(daemon.build_request("retry"), {"version": 1, "type": "retry"})
        _, payload = daemon.parse_request(json.dumps({"type": "retry"}))
        self.assertEqual(payload, {})

    def test_empty_text_refused(self):
        with self.assertRaises(daemon.DaemonError):
            daemon.build_request("send_message", {"text": "  "})

    def test_oversize_text_refused(self):
        with self.assertRaises(daemon.DaemonError):
            daemon.build_request("send_message", {"text": "x" * 4001})

    def test_extra_keys_refused(self):
        with self.assertRaises(daemon.DaemonError):
            daemon.parse_request(
                json.dumps({"type": "send_message", "payload": {"text": "hi", "x": 1}})
            )

    def test_non_string_values_refused(self):
        with self.assertRaises(daemon.DaemonError):
            daemon.parse_request(
                json.dumps({"type": "switch_model", "payload": {"model": 7}})
            )

    def test_payload_on_plain_action_refused(self):
        with self.assertRaises(daemon.DaemonError):
            daemon.parse_request(
                json.dumps({"type": "pause", "payload": {"text": "hi"}})
            )

    def test_unknown_type_still_rejected(self):
        with self.assertRaises(daemon.DaemonError):
            daemon.build_request("nudge", {"text": "hi"})


class WatcherManualTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = make_project()
        self.addCleanup(self.tmp.cleanup)
        self.driver = make_driver()
        self.driver.create_or_connect("agent", self.root, ["opencode"])
        self.driver.append_output("agent", READY)

    def _watcher(self, **overrides):
        return make_watcher(self.root, self.driver, **overrides)

    def test_retry_unavailable_before_any_send(self):
        watcher = self._watcher()
        self.assertFalse(watcher.status_view()["retry_available"])
        note = watcher.request_retry()
        self.assertIn("nothing was ever sent", note)
        self.assertEqual(self.driver.sent_inputs("agent"), [])

    def test_prompt_send_arms_retry(self):
        watcher = self._watcher()
        watcher._remember_prompt("please start")
        self.assertTrue(watcher.status_view()["retry_available"])
        note = watcher.request_retry()
        self.assertTrue(note.startswith("retried:"))
        self.assertIn("please start", self.driver.sent_inputs("agent"))

    def test_send_records_retry_source(self):
        watcher = self._watcher()
        note = watcher.request_send("check again")
        self.assertTrue(note.startswith("sent:"))
        self.assertIn("check again", self.driver.sent_inputs("agent"))
        self.assertTrue(watcher.status_view()["retry_available"])

    def test_empty_send_refused_locally(self):
        watcher = self._watcher()
        self.assertIn("empty", watcher.request_send("   "))
        self.assertEqual(self.driver.sent_inputs("agent"), [])

    def test_pause_refuses_manual_sends(self):
        watcher = self._watcher(mode_requested=lambda: "PAUSE")
        watcher._remember_prompt("please start")
        self.assertIn("paused", watcher.request_retry())
        self.assertIn("paused", watcher.request_send("hello"))
        self.assertEqual(self.driver.sent_inputs("agent"), [])

    def test_held_pause_refuses(self):
        watcher = self._watcher()
        watcher.request_pause()
        watcher._remember_prompt("please start")
        self.assertIn("paused", watcher.request_send("hello"))

    def test_draft_refuses_send(self):
        watcher = self._watcher()
        self.driver.append_output("agent", DRAFT)
        watcher._remember_prompt("please start")
        note = watcher.request_send("hello")
        self.assertIn("draft", note)
        self.assertEqual(
            [t for t in self.driver.sent_inputs("agent") if t == "hello"], []
        )

    def test_unverifiable_composer_fails_closed(self):
        watcher = self._watcher()
        self.driver.sessions.pop("agent")
        watcher._remember_prompt("please start")
        self.assertIn("cannot verify", watcher.request_send("hello"))

    def test_switch_validates_against_config(self):
        (self.root / ".ariadex" / "config.yaml").write_text(
            "models: [codex/o3]\n", encoding="utf-8"
        )
        watcher = self._watcher()
        note = watcher.request_switch_model("opencode/nope")
        self.assertIn("not in the configured", note)
        view = watcher.status_view()
        self.assertEqual(view["models"], ["codex/o3"])

    def test_switch_empty_config_refuses(self):
        watcher = self._watcher()
        self.assertEqual(watcher.status_view()["models"], [])
        self.assertIn("not in the configured", watcher.request_switch_model("x/y"))

    def test_status_view_carries_manual_fields(self):
        watcher = self._watcher()
        view = watcher.status_view()
        self.assertFalse(view["retry_available"])
        self.assertEqual(view["models"], [])
        self.assertIsNone(view["model_override"])

    def test_poll_sends_no_manual_input(self):
        watcher = self._watcher(shutdown_requested=lambda: True)
        watcher.poll()
        self.assertIsNone(watcher._last_prompt)
        self.assertEqual(self.driver.sent_inputs("agent"), [])


class DaemonManualTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def tearDown(self):
        daemon.unregister_watcher(self.root)

    def test_no_watcher_fails_closed(self):
        reply = daemon.handle_request(self.root, "retry", {})
        self.assertFalse(reply["ok"])
        self.assertIn("no live watcher", reply["error"])

    def test_retry_routes_to_watcher(self):
        watcher = mock.Mock()
        watcher.request_retry.return_value = "retried: resent it"
        daemon.register_watcher(self.root, watcher)
        reply = daemon.handle_request(self.root, "retry", {})
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["state"]["manual_result"], "retried: resent it")
        watcher.request_retry.assert_called_once_with()

    def test_refusal_returns_error_with_state(self):
        watcher = mock.Mock()
        watcher.request_send.return_value = "manual input refused: watcher is paused"
        daemon.register_watcher(self.root, watcher)
        reply = daemon.handle_request(self.root, "send_message", {"text": "hi"})
        self.assertFalse(reply["ok"])
        self.assertIn("paused", reply["error"])
        self.assertIn("state", reply)

    def test_send_passes_payload(self):
        watcher = mock.Mock()
        watcher.request_send.return_value = "sent: ok"
        daemon.register_watcher(self.root, watcher)
        reply = daemon.handle_request(self.root, "send_message", {"text": "hi"})
        self.assertTrue(reply["ok"])
        watcher.request_send.assert_called_once_with("hi")

    def test_switch_passes_model(self):
        watcher = mock.Mock()
        watcher.request_switch_model.return_value = "switched: ok"
        daemon.register_watcher(self.root, watcher)
        reply = daemon.handle_request(self.root, "switch_model", {"model": "a/b"})
        self.assertTrue(reply["ok"])
        watcher.request_switch_model.assert_called_once_with("a/b")

    def test_watcher_exception_fails_closed(self):
        watcher = mock.Mock()
        watcher.request_retry.side_effect = RuntimeError("boom")
        daemon.register_watcher(self.root, watcher)
        reply = daemon.handle_request(self.root, "retry", {})
        self.assertFalse(reply["ok"])
        self.assertIn("boom", reply["error"])

    def test_status_carries_manual_fields(self):
        watcher = mock.Mock()
        watcher.status_view.return_value = {
            "retry_available": True,
            "models": ["a/b"],
            "model_override": "a/b",
        }
        daemon.register_watcher(self.root, watcher)
        view = daemon.daemon_status_view(self.root)
        self.assertEqual(
            view["manual"],
            {"retry_available": True, "models": ["a/b"], "model_override": "a/b"},
        )

    def test_status_without_watcher_defaults(self):
        view = daemon.daemon_status_view(self.root)
        self.assertEqual(
            view["manual"],
            {"retry_available": False, "models": [], "model_override": None},
        )

    def test_unregister_stops_routing(self):
        watcher = mock.Mock()
        daemon.register_watcher(self.root, watcher)
        daemon.unregister_watcher(self.root)
        reply = daemon.handle_request(self.root, "retry", {})
        self.assertFalse(reply["ok"])

    def test_end_to_end_over_socket(self):
        from tests.test_daemon import start_ipc_server

        watcher = mock.Mock()
        watcher.request_send.return_value = "sent: ok"
        daemon.register_watcher(self.root, watcher)
        stop, _thread = start_ipc_server(self.root)
        try:
            response = daemon.send_request(self.root, "send_message", {"text": "hi"})
        finally:
            stop.set()
        self.assertTrue(response["ok"])
        watcher.request_send.assert_called_once_with("hi")


class ClientManualTest(unittest.TestCase):
    def test_actions_map_to_typed_ipc(self):
        client = companion.CompanionClient(Path("/tmp/x"))
        with mock.patch(
            "ariadex.daemon.send_request",
            return_value={"ok": True, "state": {"alive": True}},
        ) as sender:
            client.retry()
            sender.assert_called_with(Path("/tmp/x"), "retry", timeout_s=5.0)
            client.send_message("hello")
            sender.assert_called_with(
                Path("/tmp/x"), "send_message", payload={"text": "hello"}, timeout_s=5.0
            )
            client.switch_model("a/b")
            sender.assert_called_with(
                Path("/tmp/x"), "switch_model", payload={"model": "a/b"}, timeout_s=5.0
            )

    def test_refusal_surfaces_without_fabrication(self):
        client = companion.CompanionClient(Path("/tmp/x"))
        with mock.patch(
            "ariadex.daemon.send_request",
            return_value={"ok": False, "state": {}, "error": "paused"},
        ):
            with self.assertRaises(companion.CompanionError) as ctx:
                client.send_message("hello")
            self.assertIn("paused", str(ctx.exception))


class MiniManualPanelTest(unittest.TestCase):
    def setUp(self):
        from tests.test_companion import (
            FakeAdapter,
            FakeClient,
            FakeTkRoot,
            install_fake_tk,
            live_state,
        )

        self.live_state = live_state
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        patch.start()
        self.addCleanup(patch.stop)
        install_fake_tk(self)
        self.window = companion.CompanionWindow(
            FakeTkRoot(), FakeClient(), FakeAdapter(), "Ctrl+Esc"
        )

    def test_rows_are_labeled_never_tabs(self):
        manual = self.window.manual
        self.assertTrue(manual["frame"].packed)
        self.assertEqual(
            manual["retry_button"].options.get("text"), "Retry last prompt"
        )
        self.assertEqual(manual["send_button"].options.get("text"), "Send")
        self.assertEqual(manual["feedback"].options.get("name"), "mini-manual-feedback")
        self.assertEqual(
            manual["message_text"].options.get("name"), "mini-manual-message-text"
        )

    def test_retry_disabled_without_availability(self):
        self.window._render()
        self.assertEqual(
            self.window.manual["retry_button"].options.get("state"), "disabled"
        )

    def test_retry_enabled_with_availability(self):
        state = self.live_state()
        state["manual"] = {
            "retry_available": True,
            "models": [],
            "model_override": None,
        }
        self.window._state = state
        self.window.model = self.window._view_model(state)
        self.window._render()
        self.assertEqual(
            self.window.manual["retry_button"].options.get("state"), "normal"
        )

    def test_retry_press_sends_typed_ipc(self):
        self.window._on_manual_retry()
        self.assertIn("retry", self.window.client.calls)

    def test_empty_send_refused_locally(self):
        self.window._on_manual_send()
        self.assertNotIn("send_message", self.window.client.calls)
        self.assertIn("empty", str(self.window.model.get("failure")))

    def test_send_press_delivers_text(self):
        self.window.manual["message_text"].insert("1.0", "check again")
        self.window._on_manual_send()
        self.assertIn("send_message", self.window.client.calls)
        self.assertEqual(
            self.window.manual["message_text"].get("1.0", "end").strip(), ""
        )

    def test_model_options_refresh_from_state(self):
        state = self.live_state()
        state["manual"] = {
            "retry_available": False,
            "models": ["a/b", "c/d"],
            "model_override": None,
        }
        self.window._state = state
        self.window.model = self.window._view_model(state)
        self.window._render()
        menu = self.window.manual["model_option"]["menu"]
        self.assertEqual([label for label, _ in menu.commands], ["a/b", "c/d"])
        self.assertEqual(self.window.manual["model_var"].get(), "a/b")

    def test_model_row_hint_without_config(self):
        self.window._render()
        hint = self.window.manual["model_hint"]
        self.assertIn("no models", hint.options.get("text", ""))
        self.assertTrue(hint.packed)

    def test_switch_press_sends_selected_model(self):
        self.window.manual["model_var"].set("c/d")
        self.window._on_manual_switch()
        self.assertIn("switch_model", self.window.client.calls)

    def test_full_height_grows_by_manual_group(self):
        self.window._set_display_mode("full")
        self.assertEqual(
            self.window._active_window_height(),
            companion.WIDGET_EXPANDED_WINDOW_HEIGHT + companion.MANUAL_GROUP_HEIGHT,
        )


class HubManualPanelTest(unittest.TestCase):
    def setUp(self):
        install_fake_tk(self)
        self.make_tab = make_tab
        made_a = make_tab("/home/u/a")
        made_b = make_tab("/home/u/b")
        self.tabs = [made_a[0], made_b[0]]
        self.root = FakeTkRoot()
        self.window = companion.RobotHubWindow(self.root, self.tabs)

    def test_panel_acts_on_active_tab_project(self):
        self.window.active = 1
        self.window.hub_manual["message_text"].insert("1.0", "hello")
        with mock.patch(
            "ariadex.daemon.send_request",
            return_value={"ok": True, "state": {"manual_result": "sent: ok"}},
        ) as sender:
            self.window._on_hub_send()
            sender.assert_called_once_with(
                Path("/home/u/b"), "send_message", payload={"text": "hello"}
            )

    def test_retry_uses_active_tab(self):
        self.window.active = 0
        with mock.patch(
            "ariadex.daemon.send_request",
            return_value={"ok": True, "state": {"manual_result": "retried: ok"}},
        ) as sender:
            self.window._on_hub_retry()
            sender.assert_called_once_with(Path("/home/u/a"), "retry")

    def test_refusal_shows_reason_and_refreshes_nothing_sent(self):
        self.window.hub_manual["message_text"].insert("1.0", "hello")
        with mock.patch(
            "ariadex.daemon.send_request",
            return_value={"ok": False, "state": {}, "error": "paused"},
        ):
            self.window._on_hub_send()
        self.assertIn(
            "paused", self.window.hub_manual["feedback"].options.get("text", "")
        )

    def test_empty_hub_send_refused_locally(self):
        with mock.patch("ariadex.daemon.send_request") as sender:
            self.window._on_hub_send()
            sender.assert_not_called()

    def test_retry_gating_follows_active_model(self):
        self.window.models[0]["retry_available"] = True
        self.window.models[0]["models"] = ["a/b"]
        self.window.active = 0
        self.window._render()
        manual = self.window.hub_manual
        self.assertEqual(manual["retry_button"].options.get("state"), "normal")
        self.assertEqual(manual["model_apply"].options.get("state"), "normal")

    def test_no_tabs_disables_gracefully(self):
        window = companion.RobotHubWindow(FakeTkRoot(), [])
        with mock.patch("ariadex.daemon.send_request") as sender:
            window._on_hub_retry()
            sender.assert_not_called()
        self.assertIn("no active tab", window.hub_manual["feedback"].options["text"])


class ManualPanelThemeTest(unittest.TestCase):
    """Every Manual surface renders from the theme (no Tk light defaults)."""

    def setUp(self):
        from tests.test_companion import (
            FakeAdapter,
            FakeClient,
            FakeTkRoot,
            install_fake_tk,
            live_state,
        )

        self.live_state = live_state
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        patch.start()
        self.addCleanup(patch.stop)
        install_fake_tk(self)
        self.window = companion.CompanionWindow(
            FakeTkRoot(), FakeClient(), FakeAdapter(), "Ctrl+Esc"
        )

    def test_manual_widgets_carry_dark_backgrounds(self):
        from ariadex import theme as theme_mod

        dark = theme_mod.DARK
        manual = self.window.manual
        for key in (
            "frame",
            "retry_button",
            "model_apply",
            "model_option",
            "message_text",
            "send_button",
            "feedback",
        ):
            bg = manual[key].options.get("background")
            self.assertIn(
                bg,
                {dark.window_bg, dark.input_bg, dark.button_bg},
                f"manual[{key}] background {bg!r} is not themed",
            )

    def test_message_text_is_focusable(self):
        self.assertTrue(self.window.manual["message_text"].options.get("takefocus"))

    def test_buttons_carry_themed_foreground(self):
        from ariadex import theme as theme_mod

        self.assertEqual(
            self.window.manual["send_button"].options.get("foreground"),
            theme_mod.DARK.button_fg,
        )

    def test_light_theme_reaches_manual_panel(self):
        from tests.test_companion import FakeAdapter, FakeClient, FakeTkRoot

        window = companion.CompanionWindow(
            FakeTkRoot(), FakeClient(), FakeAdapter(), "Ctrl+Esc", theme="light"
        )
        bg = window.manual["message_text"].options.get("background")
        self.assertEqual(bg, "#ffffff")
        self.assertEqual(window.manual["frame"].options.get("background"), "#eef1f4")


class RealTkTypingTest(unittest.TestCase):
    """Real display-server typing: fake-Tk `insert` cannot prove focus works."""

    def _make_window(self, root):
        from tests.test_companion import FakeAdapter, live_state

        class RecordingClient(companion.CompanionClient):
            def __init__(self):
                self.project_dir = Path(".")
                self.sent = []

            def refresh(self):
                return live_state()

            def send_message(self, text):
                self.sent.append(text)
                return live_state()

        return companion.CompanionWindow(
            root, RecordingClient(), FakeAdapter(), "Ctrl+Esc"
        )

    def test_typed_keys_land_and_send(self):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("tkinter not installed")
        try:
            root = tk.Tk()
        except Exception as exc:
            self.skipTest(f"no display server: {exc}")
        try:
            window = self._make_window(root)
            window._toggle_expanded()
            window._toggle_expanded()
            root.update()
            self.assertEqual(window.display_mode, "full")

            def find(name):
                found = []

                def walk(widget):
                    if widget.winfo_name() == name:
                        found.append(widget)
                    for child in widget.winfo_children():
                        walk(child)

                walk(root)
                return found[0]

            box = find("mini-manual-message-text")
            self.assertTrue(bool(box.winfo_viewable()), "message box not mapped")
            root.deiconify()
            root.focus_force()
            root.update()
            box.focus_set()
            root.update()
            self.assertEqual(root.focus_get(), box)
            for char in "hi":
                box.event_generate(f"<KeyPress-{char}>")
            root.update()
            self.assertEqual(box.get("1.0", "end").strip(), "hi")
            window._on_manual_send()
            root.update()
            self.assertEqual(window.client.sent, ["hi"])
            self.assertEqual(box.get("1.0", "end").strip(), "")
        finally:
            with contextlib.suppress(Exception):
                root.destroy()


if __name__ == "__main__":
    unittest.main()
