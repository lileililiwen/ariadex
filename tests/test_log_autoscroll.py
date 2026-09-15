"""Tests for the log-autoscroll change: viewport follows latest + scrollbar."""

import os
import tempfile
import unittest
from unittest import mock

from ariadex import companion


class MiniLogAutoscrollTest(unittest.TestCase):
    """Mini context log follows the latest entry and carries a scrollbar."""

    def setUp(self):
        from tests.test_companion import (
            FakeAdapter,
            FakeClient,
            FakeTkRoot,
            install_fake_tk,
        )

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        install_fake_tk(self)
        self.window = companion.CompanionWindow(
            FakeTkRoot(), FakeClient(), FakeAdapter(), "Ctrl+Esc"
        )

    def test_rewrite_follows_latest(self):
        self.window._render_context_log(self.window.model)
        self.assertTrue(self.window.context_log.see_calls)
        self.assertEqual(self.window.context_log.see_calls[-1], "end")

    def test_follow_repeats_on_every_rewrite(self):
        self.window._render_context_log(self.window.model)
        self.window._render_context_log(self.window.model)
        self.assertEqual(
            self.window.context_log.see_calls,
            ["end", "end", "end"],
        )

    def test_follow_applies_to_unreachable_state(self):
        self.window._render_context_log({})
        self.assertIn("unreachable", self.window.context_log.content)
        self.assertEqual(self.window.context_log.see_calls[-1], "end")

    def test_scrollbar_tracks_context_log(self):
        scrollbar = self.window.context_log_scrollbar
        self.assertEqual(scrollbar.options.get("orient"), "vertical")
        self.assertEqual(
            self.window.context_log.options.get("yscrollcommand"), scrollbar.set
        )
        self.assertEqual(
            scrollbar.options.get("command"), self.window.context_log.yview
        )

    def test_scrollbar_shares_row_without_new_config(self):
        # No geometry growth: the scrollbar packs inside the existing
        # log row frame, which keeps the row's own padding.
        self.assertTrue(self.window.context_log_frame.packed)
        self.assertTrue(self.window.context_log_scrollbar.packed)

    def test_see_failure_never_raises(self):
        self.window.context_log.see = mock.Mock(side_effect=RuntimeError("nope"))
        self.window._render_context_log(self.window.model)  # must not raise
        self.assertTrue(self.window.context_log.content)


class HubLogAutoscrollTest(unittest.TestCase):
    """Hub detail log follows the latest entry and carries a scrollbar."""

    def setUp(self):
        import sys

        sys.path.insert(0, "tests")
        from test_robot_hub import FakeTkRoot, install_fake_tk, make_tab

        install_fake_tk(self)
        tab, _watcher = make_tab("/home/u/a", "opencode", "s1", "working")
        self.window = companion.RobotHubWindow(FakeTkRoot(), [tab])
        self.window.models[0]["activity"] = [
            {"category": "prompt", "message": f"line {i}"} for i in range(30)
        ]

    def test_panel_builds_frame_text_and_scrollbar(self):
        self.assertIsNotNone(self.window.log_text_frame)
        self.assertIsNotNone(self.window.log_text)
        self.assertIsNotNone(self.window.log_scrollbar)
        self.assertEqual(self.window.log_scrollbar.options.get("orient"), "vertical")

    def test_scrollbar_tracks_hub_log(self):
        self.assertEqual(
            self.window.log_text.options.get("yscrollcommand"),
            self.window.log_scrollbar.set,
        )
        self.assertEqual(
            self.window.log_scrollbar.options.get("command"),
            self.window.log_text.yview,
        )

    def test_expanded_render_follows_latest(self):
        self.window._on_toggle()
        self.assertTrue(self.window.expanded)
        self.window._render()
        self.assertEqual(self.window.log_text.options.get("see"), "end")
        self.assertIn("line 29", self.window.log_text.text)

    def test_collapsed_render_never_seeks(self):
        self.assertFalse(self.window.expanded)
        self.window._render()
        self.assertNotIn("see", self.window.log_text.options)

    def test_toggle_packs_frame_not_text(self):
        self.window._on_toggle()
        self.assertTrue(self.window.log_text_frame.packed)
        self.window._on_toggle()
        self.assertFalse(self.window.log_text_frame.packed)

    def test_log_bounds_unchanged(self):
        # Viewport-only change: the bounded activity window still caps
        # the rendered lines at ROBOT_LOG_VIEW_LINES.
        self.window._on_toggle()
        self.window._render()
        rendered = self.window.log_text.text.splitlines()
        self.assertLessEqual(len(rendered), companion.ROBOT_LOG_VIEW_LINES)


if __name__ == "__main__":
    unittest.main()
