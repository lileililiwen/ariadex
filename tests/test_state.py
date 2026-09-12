"""Tests for durable state read/write and validation."""

import json
import tempfile
import unittest
from pathlib import Path

from ariadex import state


class StateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_initial_state_has_explicit_mode(self):
        st = state.initial_state()
        self.assertIn(st.mode, state.MODES)
        self.assertTrue(st.session_id)
        self.assertGreaterEqual(st.unresolved_count, 0)
        self.assertTrue(st.updated_at)

    def test_write_then_read_round_trip(self):
        original = state.initial_state()
        original.current_spec = "example-change"
        original.unresolved_count = 3
        state.write(self.root, original)
        loaded = state.read(self.root)
        self.assertEqual(loaded.mode, original.mode)
        self.assertEqual(loaded.session_id, original.session_id)
        self.assertEqual(loaded.current_spec, "example-change")
        self.assertEqual(loaded.unresolved_count, 3)

    def test_write_leaves_no_temp_files(self):
        state.write(self.root, state.initial_state())
        leftovers = list((self.root / ".ariadex").glob(".state.*.tmp"))
        self.assertEqual(leftovers, [])

    def test_missing_state_reports_init(self):
        with self.assertRaises(state.StateError) as ctx:
            state.read(self.root)
        self.assertIn("ariadex init", str(ctx.exception))

    def test_corrupt_state_rejected(self):
        path = state.state_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(state.StateError):
            state.read(self.root)

    def test_invalid_mode_rejected(self):
        path = state.state_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mode": "SLEEP", "session_id": "x"}), encoding="utf-8")
        with self.assertRaises(state.StateError):
            state.read(self.root)

    def test_unknown_fields_ignored_on_read(self):
        st = state.initial_state()
        state.write(self.root, st)
        path = state.state_path(self.root)
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["future_field"] = "ignored"
        path.write_text(json.dumps(raw), encoding="utf-8")
        self.assertEqual(state.read(self.root).session_id, st.session_id)


if __name__ == "__main__":
    unittest.main()
