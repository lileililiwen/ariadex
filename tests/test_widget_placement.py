"""Regression coverage for bounded widget screen placement."""

import os
import tempfile
import unittest
from unittest import mock

from ariadex import companion
from tests.test_companion import FakeAdapter, FakeClient, FakeTkRoot, install_fake_tk


class ClampHelperTest(unittest.TestCase):
    def test_inside_bounds_unchanged(self):
        self.assertEqual(
            companion.clamp_widget_position(100, 200, 360, 116, 0, 0, 1920, 1080),
            (100, 200),
        )

    def test_drag_beyond_edges_clamps(self):
        self.assertEqual(
            companion.clamp_widget_position(5000, -5000, 360, 116, 0, 0, 1920, 1080),
            (1920 - 360 - 8, 8),
        )
        self.assertEqual(
            companion.clamp_widget_position(-100, -100, 360, 116, 0, 0, 1920, 1080),
            (8, 8),
        )

    def test_negative_origin_multimonitor(self):
        # Virtual screen starting at -1920 keeps the dialog reachable there.
        self.assertEqual(
            companion.clamp_widget_position(-5000, 100, 360, 116, -1920, 0, 3840, 1080),
            (-1920 + 8, 100),
        )
        self.assertEqual(
            companion.clamp_widget_position(5000, 5000, 360, 116, -1920, 0, 3840, 1080),
            (-1920 + 3840 - 360 - 8, 1080 - 116 - 8),
        )

    def test_small_screen_clamps_to_origin(self):
        self.assertEqual(
            companion.clamp_widget_position(100, 100, 360, 340, 0, 0, 200, 100),
            (0, 0),
        )

    def test_virtual_bounds_prefers_vroot(self):
        root = mock.Mock()
        root.winfo_screenwidth.return_value = 1920
        root.winfo_screenheight.return_value = 1080
        root.winfo_vrootx.return_value = -1920
        root.winfo_vrooty.return_value = 0
        root.winfo_vrootwidth.return_value = 3840
        root.winfo_vrootheight.return_value = 1080
        self.assertEqual(companion.virtual_screen_bounds(root), (-1920, 0, 3840, 1080))

    def test_virtual_bounds_falls_back_without_vroot(self):
        root = FakeTkRoot()
        self.assertEqual(companion.virtual_screen_bounds(root), (0, 0, 1920, 1080))

    def test_clamp_to_screen_fail_soft(self):
        root = mock.Mock()
        root.winfo_screenwidth.side_effect = Exception("no display")
        root.winfo_screenheight.side_effect = Exception("no display")
        self.assertEqual(companion.clamp_to_screen(root, 50, 60, 360, 116), (50, 60))


class PlacementPathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        install_fake_tk(self)

    def _window(self, root=None, client=None):
        return companion.CompanionWindow(
            root or FakeTkRoot(),
            client or FakeClient(),
            FakeAdapter(),
            "Ctrl+Esc",
        )

    def test_restored_offscreen_is_corrected_and_persisted(self):
        companion.save_user_config({"x": 5000, "y": 5000})
        window = self._window()
        geometry = window.root.options["geometry"]
        self.assertIn("+", geometry)
        # Corrected to the nearest valid collapsed position.
        self.assertEqual(
            geometry,
            f"+{1920 - 360 - 8}+{1080 - companion.WIDGET_COLLAPSED_HEIGHT - 8}",
        )
        saved = companion.load_user_config()
        self.assertEqual(
            (saved["x"], saved["y"]),
            (1920 - 360 - 8, 1080 - companion.WIDGET_COLLAPSED_HEIGHT - 8),
        )

    def test_drag_motion_is_clamped(self):
        window = self._window()
        window._drag_start(mock.Mock(x_root=150, y_root=250))
        window._drag_move(mock.Mock(x_root=9000, y_root=9000))
        # The motion is coalesced: flush the pending after_idle callback
        # so the test sees the clamped geometry without mainloop spin.
        window._apply_pending_drag()
        geometry = window.root.options["geometry"]
        self.assertEqual(
            geometry,
            f"+{1920 - 360 - 8}+{1080 - companion.WIDGET_COLLAPSED_HEIGHT - 8}",
        )

    def test_expanded_transition_keeps_dialog_visible(self):
        window = self._window()
        # Move near the bottom edge, then expand: position must move up.
        window.root.winfo_x = lambda: 100
        window.root.winfo_y = lambda: 1080 - companion.WIDGET_COLLAPSED_HEIGHT - 8
        # Cycle: collapsed → strip → full.
        window._toggle_expanded()
        window._toggle_expanded()
        self.assertTrue(window.expanded)
        geometry = window.root.options["geometry"]
        full_height = (
            companion.WIDGET_EXPANDED_WINDOW_HEIGHT + companion.MANUAL_GROUP_HEIGHT
        )
        self.assertIn(
            f"{companion.WIDGET_WIDTH}x{full_height}",
            geometry,
        )
        self.assertIn(f"+100+{1080 - full_height - 8}", geometry)
        window._toggle_expanded()
        self.assertFalse(window.expanded)
        self.assertEqual(window.display_mode, "collapsed")

    def test_persist_clamps_before_save(self):
        window = self._window()
        window.root.geometry("+5000+5000")
        with (
            mock.patch.object(type(window.root), "winfo_x", lambda self: 5000),
            mock.patch.object(type(window.root), "winfo_y", lambda self: 5000),
        ):
            window._persist_geometry()
        saved = companion.load_user_config()
        self.assertEqual(
            (saved["x"], saved["y"]),
            (1920 - 360 - 8, 1080 - companion.WIDGET_COLLAPSED_HEIGHT - 8),
        )

    def test_titlebar_close_reachable_after_clamp(self):
        # Every clamped position keeps the top-left (title bar) on-screen.
        for raw in [(-5000, -5000), (9000, 9000), (100, 200)]:
            clamped = companion.clamp_to_screen(
                FakeTkRoot(),
                raw[0],
                raw[1],
                companion.WIDGET_WIDTH,
                companion.WIDGET_COLLAPSED_HEIGHT,
            )
            self.assertGreaterEqual(clamped[0], 0)
            self.assertGreaterEqual(clamped[1], 0)
            self.assertLessEqual(clamped[0] + companion.WIDGET_WIDTH, 1920)
            self.assertLessEqual(clamped[1] + companion.WIDGET_COLLAPSED_HEIGHT, 1080)


class RobotPlacementTest(unittest.TestCase):
    def setUp(self):
        install_fake_tk(self)

    def test_robot_initial_placement_is_bounded(self):
        root = FakeTkRoot()
        companion.RobotWindow(
            root,
            status_fn=lambda: {},
            on_pause=lambda: "paused",
            on_quit=lambda: "quit",
        )
        geometry = root.options["geometry"]
        self.assertIn("+", geometry)
        coords = geometry.split("+")[1:]
        x, y = int(coords[0]), int(coords[1])
        self.assertLessEqual(x + companion.WIDGET_WIDTH, 1920)
        self.assertLessEqual(y + companion.WIDGET_COLLAPSED_HEIGHT, 1080)

    def test_robot_toggle_keeps_dialog_visible(self):
        root = FakeTkRoot()
        window = companion.RobotWindow(
            root,
            status_fn=lambda: {},
            on_pause=lambda: "paused",
            on_quit=lambda: "quit",
        )
        window._on_toggle()
        self.assertTrue(window.expanded)
        geometry = root.options["geometry"]
        self.assertIn(str(companion.WIDGET_EXPANDED_HEIGHT), geometry)
        self.assertIn("+", geometry)


if __name__ == "__main__":
    unittest.main()
