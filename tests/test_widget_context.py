"""Managed widget log copy and context: projection, clipboard, integration."""

import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from ariadex import companion
from ariadex import diagnostics as diagnostics_mod


def live_state(**overrides):
    base = {
        "alive": True,
        "mode": "AUTO",
        "session": "agent",
        "provider": "opencode",
        "next_action": "run_once provider send",
        "open_count": 0,
        "blocked_count": 0,
    }
    base.update(overrides)
    return base


def context_state(**overrides):
    context = {
        "current_spec": "alpha",
        "queue": [
            {"name": "alpha", "completed": 0, "total": 14},
            {"name": "beta", "completed": 3, "total": 5},
        ],
        "latest_event": {
            "category": "boundary",
            "message": "unfinished tasks remain",
        },
        "recent_events": [
            {
                "at": "2026-09-13T00:00:01+00:00",
                "category": "prompt",
                "action": "sent initial prompt",
                "result": "sent",
                "message": "sent initial prompt",
                "current_spec": "alpha",
            },
            {
                "at": "2026-09-13T00:00:02+00:00",
                "category": "boundary",
                "action": "unfinished tasks remain",
                "result": "unfinished",
                "message": "unfinished tasks remain",
                "current_spec": "alpha",
            },
        ],
        "notes": [],
    }
    context.update(overrides)
    return live_state(diagnostic_context=context)


class ProjectionTest(unittest.TestCase):
    def test_two_changes_identify_current_with_task_counts(self):
        projection = companion.build_managed_context(context_state())
        self.assertEqual(projection["current_spec"], "alpha")
        self.assertIn("0/14", projection["task_summary"])
        self.assertIn("OpenSpec tasks", projection["task_summary"])
        self.assertEqual(len(projection["queue"]), 2)
        self.assertEqual(len(projection["events"]), 2)

    def test_handoff_counts_stay_labeled_separately(self):
        state = context_state()
        state["open_count"] = 2
        state["blocked_count"] = 1
        projection = companion.build_managed_context(state)
        self.assertNotIn("2 open", projection["task_summary"])
        snapshot = companion.format_context_snapshot(projection, state)
        self.assertIn("handoff unresolved (separate from OpenSpec tasks)", snapshot)
        self.assertIn("2 open, 1 blocked", snapshot)

    def test_missing_context_is_honest(self):
        projection = companion.build_managed_context(live_state())
        self.assertEqual(projection["current_spec"], "(none recorded)")
        self.assertEqual(projection["events"], [])
        self.assertEqual(projection["latest_text"], "no events yet")
        log = companion.format_managed_log_text(projection)
        self.assertIn("(none yet)", log)

    def test_malformed_entries_skipped(self):
        state = context_state(queue=["nope", {"name": "x"}], recent_events=[42])
        projection = companion.build_managed_context(state)
        self.assertEqual(
            [(i["name"], i["completed"], i["total"]) for i in projection["queue"]],
            [("x", 0, 0)],
        )
        self.assertEqual(projection["events"], [])

    def test_secret_redacted_and_fields_truncated(self):
        state = context_state(
            recent_events=[
                {
                    "at": "t",
                    "category": "boundary",
                    "action": "blocked",
                    "result": "",
                    "message": "token=supersecret-value-here " + "x" * 500,
                    "current_spec": "alpha",
                }
            ]
        )
        projection = companion.build_managed_context(state)
        message = projection["events"][0]["message"]
        self.assertNotIn("supersecret-value-here", message)
        self.assertIn("<redacted>", message)
        self.assertLessEqual(len(message), 320)

    def test_snapshot_carries_export_compatible_fields(self):
        state = context_state()
        projection = companion.build_managed_context(state)
        snapshot = companion.format_context_snapshot(projection, state)
        self.assertIn(f"schema v{diagnostics_mod.DIAGNOSTIC_SCHEMA_VERSION}", snapshot)
        self.assertIn("current spec: alpha", snapshot)
        self.assertIn("alpha: 0/14 tasks complete", snapshot)
        self.assertIn("beta: 3/5 tasks complete", snapshot)
        self.assertIn("next decision:", snapshot)
        self.assertIn("recent events:", snapshot)


class ClipboardTest(unittest.TestCase):
    def test_copy_reports_success_without_raising(self):
        root = FakeTkRoot()
        self.assertIsNone(companion.copy_to_clipboard(root, "hello"))
        self.assertEqual(root.clipboard, "hello")

    def test_copy_reports_failure_without_raising(self):
        class Broken:
            def clipboard_clear(self):
                raise RuntimeError("no clipboard")

            def clipboard_append(self, text):
                raise RuntimeError("no clipboard")

        error = companion.copy_to_clipboard(Broken(), "hello")
        self.assertIn("clipboard copy failed", error)


class FakeTkWidget:
    def __init__(self, master=None, **options):
        self.master = master
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

    def cget(self, key):
        return self.options.get(key)

    def bind(self, sequence, func):
        pass

    def invoke(self):
        if self.command is not None:
            self.command()


class FakeTkText(FakeTkWidget):
    def __init__(self, master=None, **options):
        super().__init__(master, **options)
        self.content = ""
        self.see_calls: list[str] = []

    def delete(self, start, end=None):
        self.content = ""

    def insert(self, index, text):
        self.content += text

    def see(self, index):
        self.see_calls.append(str(index))

    def yview(self, *args):
        return None

    def index(self, pos):
        return str(pos)


class FakeTkScrollbar(FakeTkWidget):
    def __init__(self, master=None, **options):
        orient = options.pop("orient", "vertical")
        command = options.pop("command", None)
        super().__init__(master, **options)
        self.options["orient"] = orient
        self.command = command
        self.set_calls: list[tuple[float, float]] = []

    def set(self, first, last):
        self.set_calls.append((first, last))


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
        self._after_seq = 0
        self.clipboard = ""
        self.break_clipboard = False
        self.destroyed = False

    def title(self, text):
        pass

    def overrideredirect(self, flag):
        pass

    def attributes(self, *args):
        pass

    def geometry(self, spec):
        pass

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
        return f"after{self._after_seq}"

    def after_cancel(self, token):
        pass

    def destroy(self):
        self.destroyed = True

    def clipboard_clear(self):
        if self.break_clipboard:
            raise RuntimeError("no clipboard")
        self.clipboard = ""

    def clipboard_append(self, text):
        if self.break_clipboard:
            raise RuntimeError("no clipboard")
        self.clipboard += text

    def update(self):
        pass


class FakeTkModule:
    Tk = FakeTkRoot
    Frame = FakeTkWidget
    Label = FakeTkWidget
    Button = FakeTkWidget
    Text = FakeTkText
    Scrollbar = FakeTkScrollbar
    Entry = FakeTkWidget
    StringVar = FakeTkStringVar
    TclError = Exception


class FakeMessagebox:
    @staticmethod
    def askyesno(title, message, parent=None):
        return True


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

    def register(self, hotkey, callback):
        self.registered.append(hotkey)

    def unregister(self):
        self.unregistered += 1


def install_fake_tk():
    tk_mod = types.ModuleType("tkinter")
    for attr in (
        "Tk",
        "Frame",
        "Label",
        "Button",
        "Text",
        "Scrollbar",
        "Entry",
        "StringVar",
        "TclError",
    ):
        setattr(tk_mod, attr, getattr(FakeTkModule, attr))
    msg_mod = types.ModuleType("tkinter.messagebox")
    msg_mod.askyesno = FakeMessagebox.askyesno
    tk_mod.messagebox = msg_mod
    saved = {}
    for name, module in (("tkinter", tk_mod), ("tkinter.messagebox", msg_mod)):
        saved[name] = sys.modules.get(name)
        sys.modules[name] = module
    return saved


def restore_fake_tk(saved):
    for name, module in saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


class ManagedWindowTest(unittest.TestCase):
    def setUp(self):
        self.saved = install_fake_tk()
        self.addCleanup(restore_fake_tk, self.saved)

    def make_window(self, state=None):
        root = FakeTkRoot()
        client = FakeClient(state)
        return companion.CompanionWindow(root, client, FakeAdapter(), "Ctrl+Esc")

    def test_collapsed_label_shows_spec_tasks_and_latest(self):
        window = self.make_window(context_state())
        text = str(window.work_label.options.get("text", ""))
        self.assertIn("alpha", text)
        self.assertIn("0/14", text)

    def test_copy_buttons_do_not_steal_focus(self):
        window = self.make_window(context_state())
        self.assertFalse(window.copy_log_button.options.get("takefocus"))
        self.assertFalse(window.copy_context_button.options.get("takefocus"))

    def test_copy_log_button_is_visible_when_collapsed(self):
        window = self.make_window(context_state())
        self.assertFalse(window.expanded)
        self.assertIs(window.copy_log_button.master, window.controls)
        self.assertTrue(window.controls.packed)

    def test_collapsed_widget_shows_live_log_and_remaining_specs(self):
        window = self.make_window(context_state())
        self.assertFalse(window.expanded)
        self.assertTrue(window.context_log_frame.packed)
        self.assertIn("beta", window.context_log.content)
        self.assertIn("2 active", str(window.work_label.options.get("text", "")))

    def test_copy_log_places_bounded_log_on_clipboard(self):
        window = self.make_window(context_state())
        window._on_copy_log()
        root = window.root
        self.assertIn("current spec: alpha", root.clipboard)
        self.assertIn("0/14", root.clipboard)
        self.assertEqual([c for c in window.client.calls if c != "status"], [])

    def test_copy_context_places_snapshot_on_clipboard(self):
        window = self.make_window(context_state())
        window._on_copy_context()
        clipboard = window.root.clipboard
        self.assertIn("current spec: alpha", clipboard)
        self.assertIn("alpha: 0/14 tasks complete", clipboard)
        self.assertIn("handoff unresolved", clipboard)

    def test_copy_failure_shows_feedback_and_keeps_state(self):
        window = self.make_window(context_state())
        window.root.break_clipboard = True
        window._on_copy_context()
        self.assertEqual(window.root.clipboard, "")
        self.assertIn("clipboard copy failed", str(window.model.get("failure")))
        self.assertTrue(window.model.get("alive"))

    def test_copy_without_context_reports_honestly(self):
        window = self.make_window(live_state())
        window._on_copy_log()
        self.assertIn("nothing to copy", str(window.model.get("failure")))

    def test_expand_collapse_preserves_pause_gating(self):
        window = self.make_window(context_state())
        self.assertFalse(window.expanded)
        # Cycle: collapsed → strip → full (expanded).
        window._toggle_expanded()
        window._toggle_expanded()
        self.assertTrue(window.expanded)
        actions = window.model.get("actions", {})
        self.assertTrue(actions.get("pause"))
        self.assertFalse(actions.get("play"))
        window._toggle_expanded()
        self.assertFalse(window.expanded)

    def test_rendered_log_matches_projection(self):
        window = self.make_window(context_state())
        content = window.context_log.content
        self.assertIn("current spec: alpha", content)
        self.assertIn("[boundary]", content)

    def test_unreachable_daemon_renders_honest_log(self):
        client = FakeClient(live_state())
        client.failure = "daemon down"
        root = FakeTkRoot()
        window = companion.CompanionWindow(root, client, FakeAdapter(), "Ctrl+Esc")
        self.assertIn("unreachable", window.context_log.content)


class DaemonContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_empty_project_reports_gaps_without_input(self):
        from ariadex import daemon as daemon_mod

        (self.root / ".ariadex").mkdir(parents=True)
        context = daemon_mod.managed_diagnostic_context(self.root)
        self.assertIsNone(context["current_spec"])
        self.assertEqual(context["queue"], [])
        self.assertEqual(context["recent_events"], [])
        self.assertTrue(context["notes"])

    def test_recorded_diagnostics_surface_in_context(self):
        from ariadex import daemon as daemon_mod

        (self.root / ".ariadex").mkdir(parents=True)
        diagnostics_mod.record_diagnostic(
            self.root,
            diagnostics_mod.build_diagnostic(
                "boundary", "verified", result="complete", current_spec="alpha"
            ),
        )
        context = daemon_mod.managed_diagnostic_context(self.root)
        self.assertEqual(len(context["recent_events"]), 1)
        self.assertEqual(context["recent_events"][0]["category"], "boundary")
        self.assertEqual(context["recent_events"][0]["current_spec"], "alpha")

    def test_status_view_carries_bounded_context(self):
        from ariadex import cli as cli_mod
        from ariadex import daemon as daemon_mod

        self.assertEqual(cli_mod.cmd_init(self.root), 0)
        view = daemon_mod.daemon_status_view(self.root)
        self.assertIn("diagnostic_context", view)
        self.assertIn("provider", view)
        payload = __import__("json").dumps(view)
        self.assertLessEqual(len(payload.encode("utf-8")), daemon_mod.MAX_MESSAGE_BYTES)


class SingleWatcherTest(unittest.TestCase):
    """Managed start keeps one watcher; the widget stays IPC-only."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_start_builds_one_watcher_and_ipc_widget(self):
        try:
            import test_managed_start
        except ModuleNotFoundError:
            from tests import test_managed_start  # type: ignore[no-redef]

        test_managed_start.make_project(self.root)
        harness = test_managed_start.Harness(self.root, watcher_outcome="done")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = harness.run()
        self.assertEqual(code, 0)
        self.assertEqual(harness.calls.count("make_watcher"), 1)
        self.assertIn("spawn_widget", harness.calls)
        self.assertIn("watcher.run", harness.calls)


if __name__ == "__main__":
    unittest.main()
