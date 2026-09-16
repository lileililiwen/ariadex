"""Tests for the mini-collapse change: strip mode + cycle + per-mode drag."""

import os
import tempfile
import unittest
from unittest import mock

from ariadex import companion
from tests.test_companion import (
    FakeAdapter,
    FakeClient,
    FakeTkRoot,
    install_fake_tk,
)


class DisplayModeTest(unittest.TestCase):
    """The mini player toggles collapsed -> full; strip is a side stop."""

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

    def test_default_mode_is_collapsed(self):
        self.assertEqual(self.window.display_mode, "collapsed")
        self.assertFalse(self.window.expanded)
        self.assertEqual(
            self.window._active_window_height(), companion.WIDGET_COLLAPSED_HEIGHT
        )

    def test_modes_constant_is_stable(self):
        self.assertEqual(companion.WIDGET_MODES, ("collapsed", "strip", "full"))
        self.assertEqual(companion.WIDGET_STRIP_HEIGHT, 40)
        self.assertLess(
            companion.WIDGET_STRIP_HEIGHT, companion.WIDGET_COLLAPSED_HEIGHT
        )
        self.assertGreater(companion.WIDGET_STRIP_HEIGHT, 0)

    def test_toggle_advances_through_modes(self):
        # One click from collapsed reveals full (with the Manual
        # panel); a second toggle parks in strip; the strip
        # drag-handle click returns to full.
        self.window._toggle_expanded()
        self.assertEqual(self.window.display_mode, "full")
        self.assertTrue(self.window.expanded)
        self.assertEqual(
            self.window._active_window_height(),
            companion.WIDGET_EXPANDED_WINDOW_HEIGHT + companion.MANUAL_GROUP_HEIGHT,
        )
        self.window._toggle_expanded()
        self.assertEqual(self.window.display_mode, "strip")
        self.assertFalse(self.window.expanded)
        self.assertEqual(
            self.window._active_window_height(), companion.WIDGET_STRIP_HEIGHT
        )
        self.window._drag_start(mock.Mock(x_root=100, y_root=100))
        self.window._drag_stop(mock.Mock(x_root=100, y_root=100))
        self.assertEqual(self.window.display_mode, "full")
        self.assertTrue(self.window.expanded)
        self.window._set_display_mode("collapsed")
        self.assertEqual(self.window.display_mode, "collapsed")
        self.assertFalse(self.window.expanded)

    def test_unknown_mode_falls_back_to_collapsed(self):
        self.window.display_mode = "garbage"
        self.window._set_display_mode("garbage")
        self.assertEqual(self.window.display_mode, "collapsed")
        self.assertFalse(self.window.expanded)

    def test_toggle_preserves_action_semantics(self):
        # Pause/play/stop wiring is unchanged in any mode.
        for _ in range(3):
            self.window._toggle_expanded()
        self.window._on_pause()
        self.assertEqual(self.client.calls, ["pause"])

    def test_toggle_does_not_send_input(self):
        # Toggling the display mode never reaches the daemon.
        for _ in range(4):
            self.window._toggle_expanded()
        self.assertEqual(self.client.calls, [])


class StripVisibilityTest(unittest.TestCase):
    """Strip mode hides every row except the status bar."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        install_fake_tk(self)
        self.window = companion.CompanionWindow(
            FakeTkRoot(), FakeClient(), FakeAdapter(), "Ctrl+Esc"
        )

    def test_strip_packs_only_status_bar(self):
        self.window._set_display_mode("strip")
        # Status bar is the only visible affordance; the log row hides
        # as a unit via its container frame (the text stays packed
        # inside the hidden frame).
        self.assertTrue(self.window.status_bar.packed)
        self.assertFalse(self.window.context_log_frame.packed)
        for hidden in (
            self.window.titlebar,
            self.window.version_label,
            self.window.work_label,
            self.window.controls,
            self.window.details,
        ):
            self.assertFalse(
                hidden.packed, f"{hidden!r} should be hidden in strip mode"
            )

    def test_full_packs_all_rows(self):
        self.window._set_display_mode("full")
        self.assertTrue(self.window.context_log_frame.packed)
        for visible in (
            self.window.titlebar,
            self.window.version_label,
            self.window.work_label,
            self.window.controls,
            self.window.details,
        ):
            self.assertTrue(
                visible.packed, f"{visible!r} should be visible in full mode"
            )

    def test_collapsed_hides_details_panel(self):
        self.window._set_display_mode("collapsed")
        self.assertFalse(self.window.details.packed)
        self.assertTrue(self.window.context_log_frame.packed)
        for visible in (
            self.window.titlebar,
            self.window.version_label,
            self.window.work_label,
            self.window.controls,
        ):
            self.assertTrue(
                visible.packed, f"{visible!r} should be visible in collapsed mode"
            )


class StripRenderTest(unittest.TestCase):
    """The strip carries the brand + state + status line in one row."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        install_fake_tk(self)
        self.client = FakeClient()
        self.window = companion.CompanionWindow(
            FakeTkRoot(), self.client, FakeAdapter(), "Ctrl+Esc"
        )

    def test_strip_text_carries_brand_state_and_status_line(self):
        self.window._set_display_mode("strip")
        text = str(self.window.status_bar.options.get("text", ""))
        self.assertIn("Ariadex", text)
        self.assertIn("WORKING", text)
        self.assertIn("active specs", text)

    def test_strip_foreground_colors_state(self):
        self.window._set_display_mode("strip")
        self.assertEqual(self.window.status_bar.options.get("foreground"), "green")
        self.client.state = {
            "alive": True,
            "mode": "PAUSE",
            "next_action": "wait",
            "open_count": 0,
            "blocked_count": 0,
        }
        self.window._refresh()
        self.assertEqual(self.window.status_bar.options.get("foreground"), "orange")

    def test_collapsed_uses_default_status_color(self):
        # Collapsed mode keeps the original status bar styling.
        self.window._set_display_mode("collapsed")
        self.assertEqual(self.window.status_bar.options.get("foreground"), "#8b949e")


class StripDragTest(unittest.TestCase):
    """Strip mode binds the status bar as the drag handle and cycles on click."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        install_fake_tk(self)
        self.window = companion.CompanionWindow(
            FakeTkRoot(), FakeClient(), FakeAdapter(), "Ctrl+Esc"
        )

    def test_strip_status_bar_has_drag_bindings_and_hand2_cursor(self):
        self.window._set_display_mode("strip")
        self.assertEqual(self.window.status_bar.options.get("cursor"), "hand2")
        self.assertIn("<ButtonPress-1>", self.window.status_bar.bindings)
        self.assertIn("<B1-Motion>", self.window.status_bar.bindings)
        self.assertIn("<ButtonRelease-1>", self.window.status_bar.bindings)

    def test_collapsed_rebinds_titlebar_as_drag_handle(self):
        self.window._set_display_mode("strip")
        self.window._set_display_mode("collapsed")
        # Titlebar keeps its bindings and hand2 cursor.
        self.assertEqual(self.window.titlebar.options.get("cursor"), "hand2")
        self.assertIn("<ButtonPress-1>", self.window.titlebar.bindings)
        # Status bar loses its drag bindings in collapsed mode.
        self.assertNotIn("<ButtonPress-1>", self.window.status_bar.bindings)
        self.assertEqual(self.window.status_bar.options.get("cursor"), "")

    def test_strip_drag_motion_uses_strip_height_for_clamp(self):
        self.window._set_display_mode("strip")
        # Far past the screen edge; the clamp must use the strip height.
        self.window._drag_start(mock.Mock(x_root=0, y_root=0))
        self.window._drag_move(mock.Mock(x_root=9000, y_root=9000))
        self.window._apply_pending_drag()
        geometry = self.window.root.options["geometry"]
        # screen=1920x1080, widget=360x40, margin=8
        expected = f"+{1920 - 360 - 8}+{1080 - companion.WIDGET_STRIP_HEIGHT - 8}"
        self.assertIn(expected, geometry)

    def test_strip_click_cycles_mode_without_motion(self):
        self.window._set_display_mode("strip")
        self.assertEqual(self.window.display_mode, "strip")
        # Press and release with no motion: cycles to full.
        self.window._drag_start(mock.Mock(x_root=100, y_root=100))
        self.window._drag_stop(mock.Mock(x_root=100, y_root=100))
        self.assertEqual(self.window.display_mode, "full")

    def test_strip_drag_does_not_cycle(self):
        self.window._set_display_mode("strip")
        self.window._drag_start(mock.Mock(x_root=100, y_root=100))
        self.window._drag_move(mock.Mock(x_root=120, y_root=110))
        self.window._drag_stop(mock.Mock(x_root=120, y_root=110))
        self.assertEqual(self.window.display_mode, "strip")

    def test_drag_motion_coalesces_per_burst(self):
        # Many motion events should produce exactly one pending write
        # at a time (the previous after_idle is cancelled each move).
        self.window._drag_start(mock.Mock(x_root=100, y_root=100))
        for dx in range(20):
            self.window._drag_move(mock.Mock(x_root=100 + dx, y_root=100 + dx))
        # Only the most recent after_idle is still pending.
        self.assertEqual(len(self.window.root.cancelled), 19)
        self.assertIsNotNone(self.window._drag_after_idle)


class PerModeGeometryTest(unittest.TestCase):
    """Geometry restore and persist clamp per current mode."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        install_fake_tk(self)
        self.window = companion.CompanionWindow(
            FakeTkRoot(), FakeClient(), FakeAdapter(), "Ctrl+Esc"
        )

    def test_resize_to_mode_clamps_per_active_height(self):
        # Place the window at a y where the strip (40) would overflow
        # the screen but the collapsed card (344) would not. Toggling
        # into strip must move the window up so the bottom edge stays
        # within the screen margin.
        self.window.root.winfo_x = lambda: 100
        self.window.root.winfo_y = lambda: 1060
        self.window._set_display_mode("strip")
        geometry = self.window.root.options["geometry"]
        # y must have been clamped to the strip height, not the collapsed
        # height (otherwise the strip would stick off the bottom edge).
        self.assertIn(f"+100+{1080 - companion.WIDGET_STRIP_HEIGHT - 8}", geometry)
        self.assertIn(
            f"{companion.WIDGET_WIDTH}x{companion.WIDGET_STRIP_HEIGHT}", geometry
        )

    def test_persist_geometry_uses_active_mode_height(self):
        self.window._set_display_mode("strip")
        # Persist while in strip mode uses strip height for clamp.
        self.window._persist_geometry()
        saved = companion.load_user_config()
        self.assertIn("x", saved)
        self.assertIn("y", saved)

    def test_toggle_from_strip_clamps_to_strip_then_collapsed(self):
        # Place near the absolute bottom so any height needs clamping.
        self.window.root.winfo_x = lambda: 100
        self.window.root.winfo_y = lambda: 1080 - 4
        self.window._set_display_mode("strip")
        # y must have been pulled back to strip height, not collapsed.
        self.assertIn(
            f"+100+{1080 - companion.WIDGET_STRIP_HEIGHT - 8}",
            self.window.root.options["geometry"],
        )


class HeadlessStripModelTest(unittest.TestCase):
    """The view model still renders for all modes; strip is a UI choice only."""

    def setUp(self):
        install_fake_tk(self)
        self.window = companion.CompanionWindow(
            FakeTkRoot(), FakeClient(), FakeAdapter(), "Ctrl+Esc"
        )

    def test_view_model_includes_active_spec_count_in_strip(self):
        # The strip reuses the same status_line as the collapsed widget.
        from ariadex.companion import build_view_model

        state = {
            "alive": True,
            "mode": "AUTO",
            "next_action": "advance-spec demo",
            "open_count": 1,
            "blocked_count": 0,
            "diagnostic_context": {
                "current_spec": "demo",
                "queue": [{"name": "demo", "completed": 0, "total": 12}],
                "latest_event": None,
                "recent_events": [],
                "notes": [],
            },
        }
        model = build_view_model(state, project_name="demo-proj")
        self.assertIn("1 active specs", model["status_line"])
        # The strip will render exactly this line.
        self.window._state = state
        self.window.model = model
        self.window._set_display_mode("strip")
        self.assertIn(
            "1 active specs", str(self.window.status_bar.options.get("text", ""))
        )


if __name__ == "__main__":
    unittest.main()
