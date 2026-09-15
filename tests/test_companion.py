"""Tests for the floating companion: mapping, hotkeys, IPC safety."""

import io
import json
import os
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ariadex import cli, companion, operator


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


def live_state(**overrides: object) -> dict:
    base: dict = {
        "alive": True,
        "mode": "AUTO",
        "next_action": "run_once provider send",
        "open_count": 0,
        "blocked_count": 0,
    }
    base.update(overrides)
    return base


class DesktopDetectionTest(unittest.TestCase):
    def test_x11_display_is_supported(self):
        info = companion.detect_desktop({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"})
        self.assertEqual(info.session, "x11")
        self.assertTrue(info.supported)

    def test_wayland_reports_unsupported(self):
        for env in (
            {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"},
            {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"},
        ):
            with self.subTest(env=env):
                info = companion.detect_desktop(env)
                self.assertEqual(info.session, "wayland")
                self.assertFalse(info.supported)
                self.assertIn("terminal", info.detail)

    def test_missing_display_is_headless(self):
        info = companion.detect_desktop({"XDG_SESSION_TYPE": "x11"})
        self.assertEqual(info.session, "headless")
        self.assertFalse(info.supported)

    def test_macos_and_windows_report_unsupported(self):
        with mock.patch.object(companion.sys, "platform", "darwin"):
            info = companion.detect_desktop({})
            self.assertEqual(info.session, "macos")
            self.assertFalse(info.supported)
        with mock.patch.object(companion.sys, "platform", "win32"):
            info = companion.detect_desktop({})
            self.assertFalse(info.supported)


class HotkeyParseTest(unittest.TestCase):
    def test_default_candidate_parses(self):
        mods, key = companion.parse_hotkey("Ctrl+Esc")
        self.assertEqual(mods, frozenset({"Ctrl"}))
        self.assertEqual(key, "Esc")

    def test_modifiers_canonicalize_and_dedupe(self):
        mods, key = companion.parse_hotkey("ctrl+CTRL+F4")
        self.assertEqual(mods, frozenset({"Ctrl"}))
        self.assertEqual(key, "F4")

    def test_bare_key_parses(self):
        mods, key = companion.parse_hotkey("a")
        self.assertEqual(mods, frozenset())
        self.assertEqual(key, "a")

    def test_invalid_hotkeys_rejected(self):
        for bad in ("", "   ", "Hyper+Esc", "Ctrl+:+x"):
            with self.subTest(bad=bad), self.assertRaises(companion.CompanionError):
                companion.parse_hotkey(bad)


class KeysymTest(unittest.TestCase):
    def test_specials_and_letters(self):
        self.assertEqual(companion._keysym_for("Esc"), 0xFF1B)
        self.assertEqual(companion._keysym_for("F1"), 0xFFBE)
        self.assertEqual(companion._keysym_for("a"), ord("a"))

    def test_unknown_key_rejected(self):
        with self.assertRaises(companion.CompanionError):
            companion._keysym_for("Ctrl")

    def test_grab_masks_cover_lock_states(self):
        masks = companion._grab_masks(frozenset({"Ctrl"}))
        self.assertIn(4, masks)
        self.assertEqual(len(masks), 4)
        self.assertEqual(len(set(masks)), 4)


class AdapterSelectionTest(unittest.TestCase):
    def test_x11_selects_x11_adapter(self):
        adapter = companion.adapter_for_session("x11")
        self.assertIsInstance(adapter, companion.X11HotkeyAdapter)

    def test_unsupported_session_refuses_registration(self):
        for session in ("wayland", "macos", "windows", "headless"):
            with self.subTest(session=session):
                adapter = companion.adapter_for_session(session)
                with self.assertRaises(companion.CompanionError) as ctx:
                    adapter.register("Ctrl+Esc", lambda: None)
                self.assertIn("unsupported", str(ctx.exception))
                adapter.unregister()  # never raises

    def test_x11_without_display_fails_closed(self):
        adapter = companion.X11HotkeyAdapter()
        with (
            mock.patch.dict(os.environ, {"DISPLAY": ":99.99"}),
            self.assertRaises(companion.CompanionError),
        ):
            adapter.register("Ctrl+Esc", lambda: None)
        adapter.unregister()


class UserConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_round_trip_and_merge(self):
        self.assertTrue(companion.save_user_config({"hotkey": "Alt+F9"}))
        self.assertTrue(companion.save_user_config({"x": 10, "y": 20}))
        saved = companion.load_user_config()
        self.assertEqual(saved["hotkey"], "Alt+F9")
        self.assertEqual((saved["x"], saved["y"]), (10, 20))

    def test_corrupt_config_falls_back(self):
        path = companion.user_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(companion.load_user_config(), {})
        self.assertEqual(companion.configured_hotkey(), companion.DEFAULT_HOTKEY)

    def test_hotkey_precedence(self):
        self.assertEqual(companion.configured_hotkey(), "Ctrl+Esc")
        companion.save_user_config({"hotkey": "Super+Y"})
        self.assertEqual(companion.configured_hotkey(), "Super+Y")
        self.assertEqual(companion.configured_hotkey("Ctrl+Esc"), "Ctrl+Esc")


class ViewModelTest(unittest.TestCase):
    def test_working_state(self):
        model = companion.build_view_model(live_state())
        self.assertEqual(model["indicator"], "working")
        self.assertEqual(model["indicator_text"], "WORKING")
        self.assertTrue(model["actions"]["pause"])
        self.assertFalse(model["actions"]["play"])
        self.assertFalse(model["reconciliation_pending"])

    def test_paused_state_pending_reconciliation(self):
        model = companion.build_view_model(live_state(mode="PAUSE"))
        self.assertEqual(model["indicator"], "paused")
        self.assertTrue(model["reconciliation_pending"])
        self.assertTrue(model["actions"]["play"])
        self.assertFalse(model["actions"]["pause"])

    def test_manual_blocked_completed_stopped(self):
        manual = companion.build_view_model(live_state(mode="MANUAL"))
        self.assertEqual(manual["indicator"], "manual")
        blocked = companion.build_view_model(
            live_state(mode="AUTO", blocked_count=1, next_action="none — blocked")
        )
        self.assertEqual(blocked["indicator"], "blocked")
        done = companion.build_view_model(
            live_state(mode="AUTO", next_action="none — idle")
        )
        self.assertEqual(done["indicator"], "completed")
        stopped = companion.build_view_model({"alive": False})
        self.assertEqual(stopped["indicator"], "stopped")
        self.assertFalse(any(stopped["actions"].values()))

    def test_queue_counts_rendered_in_label(self):
        model = companion.build_view_model(
            live_state(next_action="advance", open_count=2, blocked_count=1)
        )
        self.assertIn("2 open, 1 blocked", model["work_label"])

    def test_failure_view_never_fabricates(self):
        model = companion.failure_view_model("daemon unreachable: refused")
        self.assertEqual(model["indicator_text"], "UNREACHABLE")
        self.assertIn("daemon unreachable", model["failure"])
        self.assertFalse(any(model["actions"].values()))
        text = companion.format_view_text(model)
        self.assertIn("UNREACHABLE", text)
        self.assertIn("failure: daemon unreachable: refused", text)

    def test_text_equivalent_covers_states(self):
        for state in (
            live_state(),
            live_state(mode="PAUSE"),
            live_state(mode="MANUAL"),
            {"alive": False},
        ):
            text = companion.format_view_text(companion.build_view_model(state))
            self.assertIn("companion:", text)
            self.assertIn("work:", text)
            self.assertIn("actions:", text)

    def test_default_geometry_is_middle_right(self):
        x, y = companion.default_geometry(1920, 1080)
        self.assertGreater(x, 1920 // 2)
        self.assertEqual(y, 1080 // 2 - 60)


class CompanionClientTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)
        self.client = companion.CompanionClient(self.root)

    def test_actions_map_to_typed_ipc_only(self):
        mapping = {
            "refresh": "status",
            "pause": "pause",
            "resume": "resume",
            "stop": "stop",
            "reconcile": "wake",
        }
        for method, request_type in mapping.items():
            with (
                self.subTest(method=method),
                mock.patch(
                    "ariadex.daemon.send_request",
                    return_value={"ok": True, "state": live_state()},
                ) as sender,
            ):
                state = getattr(self.client, method)()
                sender.assert_called_once_with(
                    self.root, request_type, timeout_s=self.client.timeout_s
                )
                self.assertEqual(state["mode"], "AUTO")

    def test_unreachable_daemon_reports_without_fabrication(self):
        from ariadex import daemon as daemon_mod

        with mock.patch.object(
            daemon_mod,
            "send_request",
            side_effect=daemon_mod.DaemonError("refused"),
        ):
            with self.assertRaises(companion.CompanionError) as ctx:
                self.client.pause()
            self.assertIn("unreachable", str(ctx.exception))

    def test_daemon_refusal_and_missing_state_reported(self):
        with (
            mock.patch(
                "ariadex.daemon.send_request",
                return_value={"ok": False, "error": "busy"},
            ),
            self.assertRaises(companion.CompanionError),
        ):
            self.client.resume()
        with (
            mock.patch("ariadex.daemon.send_request", return_value={"ok": True}),
            self.assertRaises(companion.CompanionError),
        ):
            self.client.refresh()

    def test_never_touches_state_lease_or_tmux(self):
        # The client module surface must stay IPC-only: no scheduler, tmux,
        # or state-write imports beyond the daemon transport boundary.
        import ariadex.companion as companion_mod

        source = Path(companion_mod.__file__).read_text(encoding="utf-8")
        client_part = source.split("class CompanionClient", 1)[1].split(
            "\nINDICATORS", 1
        )[0]
        for forbidden in ("write_handoff", "acquire(", "TmuxDriver", "send_text"):
            self.assertNotIn(forbidden, client_part)


class EditorSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def test_editor_requires_configuration(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EDITOR", None)
            with self.assertRaises(companion.CompanionError) as ctx:
                companion.open_editor(self.root)
            self.assertIn("$EDITOR", str(ctx.exception))

    def test_editor_launches_detached(self):
        note = companion.open_editor(self.root, editor="true")
        self.assertIn("daemon untouched", note)

    def test_missing_editor_binary_reported(self):
        with self.assertRaises(companion.CompanionError):
            companion.open_editor(self.root, editor="/nonexistent-editor-xyz")

    def test_session_guidance_is_read_only(self):
        note = companion.session_guidance(self.root)
        self.assertIn("ariadex attach", note)
        self.assertIn("never injects input", note)


class CliCompanionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def test_companion_refuses_without_toolkit(self):
        with mock.patch.object(companion, "tkinter_available", return_value=False):
            code, _, err = run_cli(self.root, "companion")
        self.assertNotEqual(code, 0)
        self.assertIn("Tkinter", err)

    def test_companion_refuses_unsupported_session(self):
        with mock.patch.object(
            companion,
            "detect_desktop",
            return_value=companion.DesktopInfo("wayland", False, "no adapter"),
        ):
            code, _, err = run_cli(self.root, "companion")
        self.assertNotEqual(code, 0)
        self.assertIn("no adapter", err)

    def test_companion_rejects_bad_hotkey(self):
        code, _, err = run_cli(self.root, "companion", "--hotkey", "Hyper+Esc")
        self.assertNotEqual(code, 0)
        self.assertIn("hotkey", err)

    def test_admin_companion_forwards(self):
        with mock.patch.object(companion, "tkinter_available", return_value=False):
            code, _, err = run_cli(self.root, "admin", "companion")
        self.assertNotEqual(code, 0)
        self.assertIn("Tkinter", err)


class DoctorCompanionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)

    def test_doctor_reports_companion_without_failing(self):
        checks, _summary = operator.run_doctor(self.root)
        found = [c for c in checks if c.name == "companion"]
        self.assertEqual(len(found), 1)
        self.assertFalse(found[0].required)
        self.assertIn("hotkey", found[0].detail)

    def test_doctor_json_includes_companion(self):
        _code, out, _ = run_cli(self.root, "doctor", "--json")
        self.assertIn("companion", out)
        payload = json.loads(out)
        names = [c["name"] for c in payload["checks"]]
        self.assertIn("companion", names)


class WidgetSmokeTest(unittest.TestCase):
    """Real Tk widget assertions; skipped without a display server."""

    def _make_window(self, root):
        class FakeAdapter:
            name = "fake"

            def register(self, hotkey, callback):
                self.callback = callback

            def unregister(self):
                pass

        class FakeClient(companion.CompanionClient):
            def __init__(self):
                self.project_dir = Path(".")
                self.calls = []

            def refresh(self):
                return live_state()

            def pause(self):
                self.calls.append("pause")
                return live_state(mode="PAUSE")

            def resume(self):
                self.calls.append("resume")
                return live_state()

            def stop(self):
                self.calls.append("stop")
                return live_state()

        return companion.CompanionWindow(root, FakeClient(), FakeAdapter(), "Ctrl+Esc")

    def test_mini_player_widgets_and_names(self):
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

            def find(name):
                """Resolve a widget by its stable Tk name anywhere below root."""
                found = []

                def walk(widget):
                    if widget.winfo_name() == name:
                        found.append(widget)
                    for child in widget.winfo_children():
                        walk(child)

                walk(root)
                self.assertTrue(found, f"widget {name!r} not found")
                return found[0]

            for widget_name in (
                "play-button",
                "pause-button",
                "stop-button",
                "copy-log-button",
                "expand-button",
                "close-button",
                "status-text",
                "status-bar",
                "version-label",
            ):
                self.assertTrue(bool(find(widget_name)), widget_name)
            self.assertEqual(
                window.play_button.options["width"],
                companion.WIDGET_ACTION_BUTTON_WIDTH,
            )
            self.assertEqual(
                window.copy_log_button.options["width"],
                companion.WIDGET_COPY_BUTTON_WIDTH,
            )
            # Collapsed by default; expand reveals extra controls.
            self.assertFalse(window.expanded)
            window._toggle_expanded()
            self.assertTrue(window.expanded)
            find("reconcile-button")
            window._toggle_expanded()
            self.assertFalse(window.expanded)
            # Actions render from daemon truth without raising.
            window._on_pause()
            text = companion.format_view_text(window.model)
            self.assertIn("companion:", text)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()


class FakeTkWidget:
    def __init__(self, master=None, **options):
        self.master = master
        self.options = dict(options)
        self.packed = False
        self.bindings = {}
        self.command = options.get("command")

    def pack(self, **kwargs):
        self.packed = True

    def pack_propagate(self, flag):
        self.options["pack_propagate"] = flag

    def pack_forget(self):
        self.packed = False

    def configure(self, **options):
        self.options.update(options)

    config = configure

    def cget(self, key):
        return self.options.get(key)

    def bind(self, sequence, func):
        self.bindings[sequence] = func

    def invoke(self):
        if self.command is not None:
            self.command()


class FakeTkText(FakeTkWidget):
    def __init__(self, master=None, **options):
        super().__init__(master, **options)
        self.content = ""

    def delete(self, start, end=None):
        self.content = ""

    def insert(self, index, text):
        self.content += text


class FakeTkStringVar:
    def __init__(self, value=""):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class FakeTkRoot(FakeTkWidget):
    TkVersion = "fake"

    def __init__(self):
        super().__init__(None)
        self.after_calls = []
        self.cancelled = []
        self.destroyed = False
        self.iconified = False
        self.mainloop_called = False
        self._after_seq = 0

    def title(self, text):
        self.options["title"] = text

    def overrideredirect(self, flag):
        self.options["overrideredirect"] = flag

    def attributes(self, *args):
        pass

    def geometry(self, spec):
        self.options["geometry"] = spec

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    def winfo_x(self):
        return 100

    def winfo_y(self):
        return 200

    def after(self, ms, func=None):
        self._after_seq += 1
        token = f"after{self._after_seq}"
        if func is not None:
            self.after_calls.append((ms, func))
        return token

    def after_cancel(self, token):
        self.cancelled.append(token)

    def mainloop(self):
        self.mainloop_called = True

    def destroy(self):
        self.destroyed = True

    def iconify(self):
        self.iconified = True


class FakeTkModule:
    Tk = FakeTkRoot
    Frame = FakeTkWidget
    Label = FakeTkWidget
    Button = FakeTkWidget
    Text = FakeTkText
    Entry = FakeTkWidget
    StringVar = FakeTkStringVar
    TclError = Exception


class FakeMessagebox:
    answer = True

    @staticmethod
    def askyesno(title, message, parent=None):
        return FakeMessagebox.answer


class FakeClient(companion.CompanionClient):
    def __init__(self, state=None):
        self.project_dir = Path(".")
        self.timeout_s = 1.0
        self.calls = []
        self.state = state if state is not None else live_state()
        self.failure = None

    def _call(self, request_type):
        self.calls.append(request_type)
        if self.failure is not None:
            raise companion.CompanionError(self.failure)
        return dict(self.state)


class FakeAdapter:
    name = "fake"

    def __init__(self):
        self.registered = []
        self.unregistered = 0
        self.callback = None

    def register(self, hotkey, callback):
        self.registered.append(hotkey)
        self.callback = callback

    def unregister(self):
        self.unregistered += 1


def install_fake_tk(test):
    import sys
    import types

    tk_mod = types.ModuleType("tkinter")
    for attr in (
        "Tk",
        "Frame",
        "Label",
        "Button",
        "Text",
        "Entry",
        "StringVar",
        "TclError",
    ):
        setattr(tk_mod, attr, getattr(FakeTkModule, attr))
    msg_mod = types.ModuleType("tkinter.messagebox")
    msg_mod.askyesno = FakeMessagebox.askyesno
    tk_mod.messagebox = msg_mod
    saved = {}
    for name, module in (
        ("tkinter", tk_mod),
        ("tkinter.messagebox", msg_mod),
    ):
        saved[name] = sys.modules.get(name)
        sys.modules[name] = module

    def restore():
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    test.addCleanup(restore)
    return tk_mod


class HeadlessWidgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        install_fake_tk(self)
        self.client = FakeClient()
        self.adapter = FakeAdapter()
        self.root = FakeTkRoot()
        self.window = companion.CompanionWindow(
            self.root, self.client, self.adapter, "Ctrl+Esc"
        )
        self.client.calls.clear()

    def test_initial_render_reflects_daemon_truth(self):
        self.assertEqual(
            self.window._active_window_height(), companion.WIDGET_COLLAPSED_HEIGHT
        )
        self.assertEqual(self.window.titlebar.options["height"], 30)
        self.assertEqual(self.window.controls.options["height"], 36)
        self.assertEqual(self.window.state_label.options["text"], "WORKING")
        self.assertEqual(self.window.pause_button.options.get("state"), "normal")
        self.assertEqual(self.window.play_button.options.get("state"), "disabled")
        self.assertEqual(self.adapter.registered, ["Ctrl+Esc"])
        self.assertTrue(self.window.hotkey_active)

    def test_pause_play_stop_wiring(self):
        self.window._on_pause()
        self.window._on_play()
        self.window._on_stop()  # first press arms, sends nothing
        self.assertEqual(self.client.calls, ["pause", "resume"])
        self.assertTrue(self.window._stop_armed)
        self.window._on_stop()  # second press fires
        self.assertEqual(self.client.calls, ["pause", "resume", "stop"])
        self.assertFalse(self.window._stop_armed)

    def test_stop_confirm_expires_to_safe_default(self):
        self.window._on_stop()
        self.assertTrue(self.window._stop_armed)
        self.assertEqual(self.window.stop_button.options.get("text"), "Confirm stop")
        self.assertEqual(self.client.calls, [])
        self.window._disarm_stop()
        self.assertFalse(self.window._stop_armed)
        self.assertEqual(self.window.stop_button.options.get("text"), "Stop")
        self.assertEqual(self.client.calls, [])

    def test_expanded_height_includes_diagnostic_textareas(self):
        self.window._toggle_expanded()
        self.assertEqual(
            self.window._active_window_height(),
            companion.WIDGET_EXPANDED_WINDOW_HEIGHT,
        )
        self.assertGreaterEqual(companion.WIDGET_EXPANDED_WINDOW_HEIGHT, 500)

    def test_paused_state_keeps_pause_label_and_enables_play(self):
        self.client.state = live_state(mode="PAUSE")
        self.window._refresh()

        self.assertEqual(self.window.pause_button.options.get("text"), "Pause")
        self.assertEqual(self.window.pause_button.options.get("state"), "disabled")
        self.assertEqual(self.window.play_button.options.get("state"), "normal")

    def test_stop_decline_sends_nothing(self):
        FakeMessagebox.answer = False
        try:
            self.window._on_stop()
        finally:
            FakeMessagebox.answer = True
        self.assertEqual(self.client.calls, [])

    def test_expand_toggle(self):
        self.assertFalse(self.window.expanded)
        self.window._toggle_expanded()
        self.assertTrue(self.window.expanded)
        self.assertTrue(self.window.details.packed)
        self.window._toggle_expanded()
        self.assertFalse(self.window.expanded)
        self.assertFalse(self.window.details.packed)

    def test_hotkey_toggle_pauses_when_auto(self):
        self.window._hotkey_toggle()
        self.assertEqual(self.client.calls, ["pause"])

    def test_hotkey_toggle_plays_when_paused(self):
        self.client.state = live_state(mode="PAUSE")
        self.window._refresh()
        self.window._hotkey_toggle()
        self.assertEqual(self.client.calls, ["status", "resume"])

    def test_hotkey_callback_marshals_to_tk_thread(self):
        self.window._on_hotkey()
        self.assertTrue(self.root.after_calls)
        for _, func in list(self.root.after_calls):
            if func.__name__ == "_hotkey_toggle":
                func()
        self.assertIn("pause", self.client.calls)

    def test_failed_refresh_reports_without_fabrication(self):
        # A failed poll surfaces a visible failure banner while preserving
        # last-known daemon truth (never fabricated, never silently dropped).
        self.client.failure = "daemon unreachable: refused"
        self.window._refresh()
        self.assertEqual(self.window.model["indicator"], "working")
        self.assertIn("refused", self.window.model["failure"])
        self.assertIn("failure: daemon unreachable", self.window.status_text.content)

    def test_apply_valid_hotkey_persists(self):
        self.window.hotkey_var.set("Alt+F9")
        self.window._apply_hotkey()
        self.assertEqual(self.window.hotkey, "Alt+F9")
        self.assertEqual(self.adapter.registered[-1], "Alt+F9")
        self.assertEqual(companion.configured_hotkey(), "Alt+F9")

    def test_apply_invalid_hotkey_notices_without_crash(self):
        self.window.hotkey_var.set("Hyper+Esc")
        self.window._apply_hotkey()
        self.assertEqual(self.window.hotkey, "Ctrl+Esc")
        self.assertIn("refused", self.window.model["failure"])

    def test_failed_registration_marks_hotkey_off(self):
        adapter = FakeAdapter()
        adapter.register = lambda hotkey, callback: (_ for _ in ()).throw(
            companion.CompanionError("taken")
        )
        window = companion.CompanionWindow(
            FakeTkRoot(), FakeClient(), adapter, "Ctrl+Esc"
        )
        self.assertFalse(window.hotkey_active)
        self.assertIn("taken", window.status_text.content)

    def test_reconcile_editor_session_notices(self):
        self.window._on_reconcile()
        self.window._on_editor()
        self.window._on_session()
        self.assertEqual(self.client.calls, ["wake"])
        self.assertIsNotNone(self.window.model["failure"])

    def test_geometry_persists_and_restores(self):
        self.window._persist_geometry()
        saved = companion.load_user_config()
        self.assertEqual((saved["x"], saved["y"]), (100, 200))
        window2 = companion.CompanionWindow(
            FakeTkRoot(), FakeClient(), FakeAdapter(), "Ctrl+Esc"
        )
        self.assertEqual(window2.root.options["geometry"], "+100+200")

    def test_drag_handlers_move_window(self):
        event = mock.Mock(x_root=150, y_root=250)
        self.assertEqual(self.window.titlebar.options.get("cursor"), "hand2")
        self.assertIn("<ButtonPress-1>", self.window.titlebar.bindings)
        self.assertNotIn("<B1-Motion>", self.window.pause_button.bindings)
        self.window._drag_start(event)
        self.window._drag_move(mock.Mock(x_root=160, y_root=260))
        self.assertIn("+", self.root.options["geometry"])
        self.window._drag_stop(event)
        self.assertIsNotNone(self.window._save_after)

    def test_button_press_gives_immediate_feedback(self):
        companion._button_press(self.window.pause_button)
        self.assertEqual(self.window.pause_button.options.get("relief"), "sunken")
        self.assertEqual(self.window.pause_button.options.get("background"), "#3b82f6")
        companion._button_release(self.window.pause_button, self.root)
        self.assertEqual(self.window.pause_button.options.get("relief"), "flat")

    def test_buttons_have_feedback_handlers(self):
        for button in (
            self.window.play_button,
            self.window.pause_button,
            self.window.stop_button,
            self.window.copy_log_button,
            self.window.toggle_button,
            self.window.close_button,
        ):
            self.assertIn("<ButtonPress-1>", button.bindings)
            self.assertIn("<ButtonRelease-1>", button.bindings)

    def test_close_button_stops_daemon_and_exits_widget(self):
        self.assertEqual(self.window.close_button.options.get("text"), "\u00d7")
        self.window.close_button.invoke()
        self.assertTrue(self.root.destroyed)
        self.assertEqual(self.client.calls, ["stop"])
        self.assertEqual(self.adapter.unregistered, 1)

    def test_close_button_stays_visible_when_daemon_stop_fails(self):
        self.client.failure = "daemon unreachable"
        self.window.close_button.invoke()
        self.assertFalse(self.root.destroyed)
        self.assertIn("daemon unreachable", self.window.model["failure"])

    def test_poll_loops_bounded(self):
        self.window._poll()
        self.assertTrue(self.root.after_calls)

    def test_nonblocking_poll_does_not_use_synchronous_refresh(self):
        window = companion.CompanionWindow(
            FakeTkRoot(), FakeClient(), FakeAdapter(), "Ctrl+Esc", nonblocking=True
        )
        with mock.patch.object(window, "_refresh_async") as refresh:
            window._poll()
        refresh.assert_called_once_with()

    def test_nonblocking_reconcile_uses_async_ipc(self):
        window = companion.CompanionWindow(
            FakeTkRoot(), FakeClient(), FakeAdapter(), "Ctrl+Esc", nonblocking=True
        )
        with mock.patch.object(window, "_run_client_async") as run_client:
            window._on_reconcile()
        run_client.assert_called_once_with("reconcile")


class RunCompanionHeadlessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_project(self.root)
        install_fake_tk(self)

    def test_successful_launch_runs_mainloop(self):
        adapter = FakeAdapter()
        with (
            mock.patch.object(
                companion,
                "detect_desktop",
                return_value=companion.DesktopInfo("x11", True, "ok"),
            ),
            mock.patch.object(companion, "adapter_for_session", return_value=adapter),
        ):
            code = companion.run_companion(self.root)
        self.assertEqual(code, 0)
        self.assertEqual(adapter.unregistered, 1)

    def test_window_creation_failure_is_reported(self):
        with (
            mock.patch.object(
                companion,
                "detect_desktop",
                return_value=companion.DesktopInfo("x11", True, "ok"),
            ),
            mock.patch("tkinter.Tk", side_effect=Exception("no display")),
        ):
            with self.assertRaises(companion.CompanionError) as ctx:
                companion.run_companion(self.root)
            self.assertIn("cannot open a window", str(ctx.exception))

    def test_main_entry_reports_errors(self):
        with mock.patch.object(
            companion, "run_companion", side_effect=companion.CompanionError("nope")
        ):
            self.assertEqual(companion.main(["."]), 1)


class X11MockAdapterTest(unittest.TestCase):
    def _fake_lib(self, keysym_code=40):
        lib = mock.MagicMock()
        lib.XOpenDisplay.return_value = 9876
        lib.XDefaultRootWindow.return_value = 55
        lib.XKeysymToKeycode.return_value = keysym_code
        lib.XSetErrorHandler.return_value = 0
        return lib

    def test_successful_grab_and_keypress(self):
        import ctypes

        _, XEvent = companion._x_event_classes()
        fired = []
        pending_calls = []

        def fake_pending(display):
            pending_calls.append(display)
            return 1 if len(pending_calls) == 1 else 0

        def fake_next(display, ptr):
            event = ctypes.cast(ptr, ctypes.POINTER(XEvent)).contents
            event.key.type = 2
            event.key.keycode = 40

        lib = self._fake_lib()
        lib.XPending.side_effect = fake_pending
        lib.XNextEvent.side_effect = fake_next
        adapter = companion.X11HotkeyAdapter()
        with (
            mock.patch("ctypes.util.find_library", return_value="libX11"),
            mock.patch("ctypes.CDLL", return_value=lib),
        ):
            adapter.register("Ctrl+Esc", lambda: fired.append(True))
            thread = adapter._thread
            assert thread is not None
            deadline = __import__("time").monotonic() + 5
            while not fired and __import__("time").monotonic() < deadline:
                __import__("time").sleep(0.01)
            adapter.unregister()
        self.assertEqual(fired, [True])
        self.assertEqual(lib.XGrabKey.call_count, 4)
        self.assertFalse(thread.is_alive())

    def test_taken_hotkey_refuses_registration(self):
        lib = self._fake_lib()
        installed = {}

        def fake_set_handler(handler):
            installed["handler"] = handler
            return 0

        def fake_sync(display, discard):
            installed["handler"](display, None)
            return 0

        lib.XSetErrorHandler.side_effect = fake_set_handler
        lib.XSync.side_effect = fake_sync
        adapter = companion.X11HotkeyAdapter()
        with (
            mock.patch("ctypes.util.find_library", return_value="libX11"),
            mock.patch("ctypes.CDLL", return_value=lib),
            self.assertRaises(companion.CompanionError) as ctx,
        ):
            adapter.register("Ctrl+Esc", lambda: None)
        self.assertIn("taken", str(ctx.exception))

    def test_missing_libx11_refuses(self):
        adapter = companion.X11HotkeyAdapter()
        with (
            mock.patch("ctypes.util.find_library", return_value=None),
            self.assertRaises(companion.CompanionError) as ctx,
        ):
            adapter.register("Ctrl+Esc", lambda: None)
        self.assertIn("libX11", str(ctx.exception))


class CompanionEdgeTest(unittest.TestCase):
    def test_unknown_platform(self):
        with mock.patch.object(companion.sys, "platform", "plan9"):
            info = companion.detect_desktop({})
            self.assertEqual(info.session, "unknown")
            self.assertFalse(info.supported)

    def test_non_dict_config_falls_back(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}),
        ):
            path = companion.user_config_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("[1, 2]", encoding="utf-8")
            self.assertEqual(companion.load_user_config(), {})

    def test_unwritable_config_returns_false(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}),
        ):
            path = companion.user_config_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.mkdir()  # a directory where the file belongs
            self.assertFalse(companion.save_user_config({"x": 1}))

    def test_session_guidance_without_state(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            self.assertRaises(companion.CompanionError),
        ):
            companion.session_guidance(Path(tmp))


class ControlRoomTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        install_fake_tk(self)

    def test_waiting_indicator_from_latest_decision(self):
        waiting = live_state(
            mode="AUTO",
            next_action="advance-spec demo",
            diagnostic_context={
                "current_spec": "demo",
                "queue": [{"name": "demo", "completed": 0, "total": 12}],
                "latest_event": {
                    "category": "provider",
                    "message": "fresh input-ready surface not observed",
                    "decision": "refire",
                },
                "recent_events": [],
                "notes": [],
            },
        )
        model = companion.build_view_model(waiting)
        self.assertEqual(model["indicator"], "waiting")
        self.assertEqual(model["indicator_text"], "WAITING")

    def test_job_pile_shows_count_only_in_summary(self):
        state = live_state(
            next_action="advance-spec demo",
            diagnostic_context={
                "current_spec": "demo",
                "queue": [
                    {"name": "demo", "completed": 0, "total": 12},
                    {"name": "next", "completed": 3, "total": 10},
                ],
                "latest_event": None,
                "recent_events": [],
                "notes": [],
            },
        )
        model = companion.build_view_model(state, project_name="demo-proj")
        self.assertIn("2 active specs", model["work_label"])
        self.assertNotIn("demo 0/12", model["work_label"])
        self.assertNotIn("next 3/10", model["work_label"])
        self.assertEqual(model["active_spec_count"], 2)
        self.assertEqual(model["status_line"], "demo-proj — 2 active specs")
        queue = (model["managed_context"] or {}).get("queue", [])
        self.assertEqual([item["name"] for item in queue], ["demo", "next"])

    def test_status_line_without_project_or_specs(self):
        model = companion.build_view_model(live_state())
        self.assertEqual(model["active_spec_count"], 0)
        self.assertEqual(model["status_line"], "no active specs")

    def test_version_text_prefers_daemon_running(self):
        state = live_state()
        state["package_version"] = "0.2.0"
        state["installed_version"] = "0.2.0"
        state["package_drift"] = False
        model = companion.build_view_model(state, local_version="0.1.0")
        self.assertEqual(model["version_text"], "v0.2.0")

    def test_version_text_reports_drift(self):
        state = live_state()
        state["package_version"] = "0.1.0"
        state["installed_version"] = "0.2.0"
        state["package_drift"] = True
        model = companion.build_view_model(state)
        self.assertEqual(model["version_text"], "v0.1.0 (installed v0.2.0)")

    def test_version_text_falls_back_to_unknown(self):
        model = companion.build_view_model(live_state())
        self.assertEqual(model["version_text"], "vunknown")

    def test_busy_click_is_acknowledged_without_duplicate(self):
        root = FakeTkRoot()
        window = companion.CompanionWindow(
            root, FakeClient(), FakeAdapter(), "Ctrl+Esc", nonblocking=True
        )
        window.client.calls.clear()
        window._action_busy = True
        window._on_pause()
        self.assertEqual(window.client.calls, [])
        self.assertIn("in flight", str(window.model.get("failure", "")))


if __name__ == "__main__":
    unittest.main()
