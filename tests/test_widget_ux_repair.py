"""Tests for the widget-ux-repair change.

One-click expand (collapsed -> full on the toggle path, strip kept as
a side stop), a single read-only log surface in the expanded view,
and a themed non-occluding model selector shared by the mini player
and the hub manual panel.
"""

import os
import tempfile
import types
import unittest
from unittest import mock

from ariadex import companion
from ariadex import theme as theme_mod
from tests.test_companion import (
    FakeAdapter,
    FakeClient,
    FakeTkModule,
    FakeTkRoot,
    FakeTkWidget,
    install_fake_tk,
    live_state,
)


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


class OneClickExpandTest(unittest.TestCase):
    """One toggle from collapsed reveals the Manual controls."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        install_fake_tk(self)
        self.client = FakeClient(context_state())
        self.window = companion.CompanionWindow(
            FakeTkRoot(), self.client, FakeAdapter(), "Ctrl+Esc"
        )
        self.client.calls.clear()

    def test_one_click_reveals_manual_controls(self):
        self.assertEqual(self.window.display_mode, "collapsed")
        self.window._toggle_expanded()
        self.assertEqual(self.window.display_mode, "full")
        self.assertTrue(self.window.expanded)
        # The Manual panel (Retry/Model/Message) is visible without
        # passing through strip.
        self.assertTrue(self.window.details.packed)
        self.assertTrue(self.window.manual["frame"].packed)
        self.assertTrue(self.window.manual["retry_button"].packed)
        self.assertTrue(self.window.manual["model_option"].packed)
        self.assertTrue(self.window.manual["message_text"].packed)

    def test_strip_stays_reachable_and_expands_on_click(self):
        self.window._toggle_expanded()
        self.window._toggle_expanded()
        self.assertEqual(self.window.display_mode, "strip")
        # Strip click (press + release, no motion) expands as today.
        self.window._drag_start(mock.Mock(x_root=100, y_root=100))
        self.window._drag_stop(mock.Mock(x_root=100, y_root=100))
        self.assertEqual(self.window.display_mode, "full")
        self.assertTrue(self.window.expanded)

    def test_toggle_sends_no_provider_input(self):
        for _ in range(4):
            self.window._toggle_expanded()
        self.assertEqual(self.client.calls, [])


class SingleLogSurfaceTest(unittest.TestCase):
    """The expanded view carries exactly one read-only log surface."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        install_fake_tk(self)
        self.client = FakeClient(context_state())
        self.window = companion.CompanionWindow(
            FakeTkRoot(), self.client, FakeAdapter(), "Ctrl+Esc"
        )

    def test_merged_log_has_labeled_sections_without_duplicates(self):
        text = companion.format_merged_log_text(self.window.model)
        lines = [line for line in text.splitlines() if line.strip()]
        self.assertIn("[context]", lines)
        self.assertIn("[status]", lines)
        # Both sources present: managed context head, activity body.
        self.assertIn("current spec: alpha", text)
        self.assertIn("ariadex companion:", text)
        # No body line repeats a context-section line: nothing is
        # duplicated across the two former log areas.
        head, _, body = text.partition("[status]")
        head_lines = {line for line in head.splitlines() if line.strip()}
        body_lines = [line for line in body.splitlines() if line.strip()]
        self.assertTrue(body_lines)
        for line in body_lines:
            self.assertNotIn(line, head_lines, f"{line!r} duplicated")
        self.assertEqual(len(body_lines), len(set(body_lines)))

    def test_full_mode_shows_only_the_merged_surface(self):
        self.window._set_display_mode("full")
        content = self.window.context_log.content
        self.assertIn("[context]", content)
        self.assertIn("[status]", content)
        self.assertIn("current spec: alpha", content)
        # The retired second surface is hidden, cleared, and disabled.
        self.assertFalse(self.window.status_text.packed)
        self.assertEqual(self.window.status_text.content, "")
        # The single surface keeps follow-tail and scrollbar behavior.
        self.assertEqual(self.window.context_log.see_calls[-1], "end")
        scrollbar = self.window.context_log_scrollbar
        self.assertEqual(
            self.window.context_log.options.get("yscrollcommand"), scrollbar.set
        )
        self.assertEqual(
            scrollbar.options.get("command"), self.window.context_log.yview
        )

    def test_merged_log_stays_honest_when_unreachable(self):
        self.window.model = companion.failure_view_model("daemon down")
        self.window._render()
        self.assertIn("unreachable", self.window.context_log.content)
        self.assertIn("daemon down", self.window.context_log.content)

    def test_copy_log_addresses_the_single_surface(self):
        captured = {}
        real = companion.copy_to_clipboard
        companion.copy_to_clipboard = lambda root, text: (
            captured.setdefault("text", text) or None
        )
        try:
            self.window._set_display_mode("full")
            # The single surface text before the copy notice re-renders.
            expected = companion.format_merged_log_text(self.window.model)
            self.window._on_copy_log()
        finally:
            companion.copy_to_clipboard = real
        self.assertEqual(captured.get("text"), expected)
        self.assertIn("[context]", captured.get("text", ""))
        self.assertIn("[status]", captured.get("text", ""))


class ThemedSelectorTest(unittest.TestCase):
    """The model selector follows the theme and never covers the input."""

    def setUp(self):
        install_fake_tk(self)

    def _build(self, theme, prefix="mini"):
        tk_mod = types.SimpleNamespace(
            Frame=FakeTkModule.Frame,
            Label=FakeTkModule.Label,
            Button=FakeTkModule.Button,
            Text=FakeTkModule.Text,
            OptionMenu=FakeTkModule.OptionMenu,
            StringVar=FakeTkModule.StringVar,
        )
        return companion.build_manual_panel(
            tk_mod,
            FakeTkWidget(),
            FakeTkRoot(),
            prefix,
            lambda: None,
            lambda: None,
            lambda: None,
            theme,
        )

    def test_refresh_restyles_button_and_popup_per_theme(self):
        refs = self._build(theme_mod.DARK)
        models = ["a", "newapi/minimax-m3"]
        for theme in (theme_mod.DARK, theme_mod.LIGHT, theme_mod.CONTRAST):
            companion.refresh_manual_panel(
                refs,
                retry_enabled=True,
                switch_enabled=True,
                send_enabled=True,
                models=models,
                result="",
                theme=theme,
            )
            self.assertEqual(
                refs["model_option"].options.get("background"), theme.button_bg
            )
            self.assertEqual(
                refs["model_option"]["menu"].options.get("background"),
                theme.input_bg,
            )
            self.assertEqual(
                refs["model_option"]["menu"].options.get("foreground"),
                theme.input_fg,
            )

    def test_refresh_without_theme_keeps_stored_theme(self):
        refs = self._build(theme_mod.LIGHT)
        companion.refresh_manual_panel(
            refs,
            retry_enabled=True,
            switch_enabled=True,
            send_enabled=True,
            models=["a"],
            result="",
        )
        self.assertEqual(
            refs["model_option"].options.get("background"),
            theme_mod.LIGHT.button_bg,
        )

    def test_button_width_tracks_longest_option(self):
        refs = self._build(theme_mod.DARK)
        models = ["a", "newapi/minimax-m3"]
        companion.refresh_manual_panel(
            refs,
            retry_enabled=True,
            switch_enabled=True,
            send_enabled=True,
            models=models,
            result="",
            theme=theme_mod.DARK,
        )
        self.assertEqual(
            refs["model_option"].options.get("width"), len("newapi/minimax-m3")
        )
        self.assertEqual(refs["model_var"].get(), "a")

    def test_model_row_packs_after_message_row(self):
        order: list = []

        class OrderFrame(FakeTkWidget):
            def pack(self, **kwargs):
                order.append(self)
                super().pack(**kwargs)

        tk_mod = types.SimpleNamespace(
            Frame=OrderFrame,
            Label=FakeTkModule.Label,
            Button=FakeTkModule.Button,
            Text=FakeTkModule.Text,
            OptionMenu=FakeTkModule.OptionMenu,
            StringVar=FakeTkModule.StringVar,
        )
        refs = companion.build_manual_panel(
            tk_mod,
            FakeTkWidget(),
            FakeTkRoot(),
            "mini",
            lambda: None,
            lambda: None,
            lambda: None,
            theme_mod.DARK,
        )
        rows = [w for w in order if w.master is refs["frame"]]
        self.assertEqual(len(rows), 3)
        # Retry, message, then model last: the dropdown popup opens
        # over the feedback line, never over the message textarea.
        self.assertIs(refs["message_text"].master, rows[1])
        self.assertIs(refs["model_option"].master, rows[2])

    def test_message_input_stays_visible_and_focusable(self):
        refs = self._build(theme_mod.DARK)
        models = ["newapi/minimax-m3"]
        companion.refresh_manual_panel(
            refs,
            retry_enabled=True,
            switch_enabled=True,
            send_enabled=True,
            models=models,
            result="",
            theme=theme_mod.DARK,
        )
        message = refs["message_text"]
        self.assertTrue(message.packed)
        self.assertTrue(message.options.get("takefocus"))

    def test_hub_manual_panel_shares_selector_behavior(self):
        # The hub builds its Manual group through the same builder,
        # so it inherits theme/size/order behavior.
        refs = self._build(theme_mod.CONTRAST, prefix="hub")
        companion.refresh_manual_panel(
            refs,
            retry_enabled=True,
            switch_enabled=True,
            send_enabled=True,
            models=["newapi/minimax-m3"],
            result="",
            theme=theme_mod.CONTRAST,
        )
        self.assertEqual(
            refs["model_option"].options.get("background"),
            theme_mod.CONTRAST.button_bg,
        )
        self.assertEqual(
            refs["model_option"].options.get("width"), len("newapi/minimax-m3")
        )


if __name__ == "__main__":
    unittest.main()
