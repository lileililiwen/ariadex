"""Tests for the handoff schema and unresolved-item lifecycle."""

import tempfile
import unittest
from pathlib import Path

from ariadex import handoff
from ariadex.handoff import (
    HandoffError,
    add_item,
    count_unresolved,
    get_item,
    open_items,
    read_handoff,
    set_item_status,
    write_handoff,
)


class SchemaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / ".ariadex" / "handoff.md"

    def test_missing_file_yields_empty_handoff(self):
        loaded = read_handoff(self.path)
        self.assertEqual(loaded.status, "idle")
        self.assertEqual(loaded.unresolved, [])

    def test_plain_markdown_is_adopted_not_rejected(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("# notes\n\nhuman text\n", encoding="utf-8")
        loaded = read_handoff(self.path)
        self.assertEqual(loaded.status, "idle")
        write_handoff(self.path, loaded)
        self.assertIn("human text", self.path.read_text(encoding="utf-8"))

    def test_write_then_read_round_trip(self):
        original = handoff.empty_handoff(session_id="s1")
        original.status = "in-progress"
        original.current_spec = "demo"
        original.current_spec_file = "openspec/changes/demo"
        original.next_action = "resolve u-1"
        original.next_spec = "next"
        add_item(original, "issue", "broken billing", priority="high", item_id="u-1")
        write_handoff(self.path, original)
        loaded = read_handoff(self.path)
        self.assertEqual(loaded.session_id, "s1")
        self.assertEqual(loaded.status, "in-progress")
        self.assertEqual(loaded.current_spec, "demo")
        self.assertEqual(loaded.next_action, "resolve u-1")
        self.assertEqual(loaded.next_spec, "next")
        self.assertEqual(len(loaded.unresolved), 1)
        self.assertEqual(loaded.unresolved[0].priority, "high")
        self.assertTrue(loaded.updated_at)

    def test_write_leaves_no_temp_files(self):
        write_handoff(self.path, handoff.empty_handoff())
        leftovers = list(self.path.parent.glob(".handoff.*.tmp"))
        self.assertEqual(leftovers, [])

    def test_malformed_front_matter_rejected(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("---\nnot: [valid\n---\nbody\n", encoding="utf-8")
        with self.assertRaises(HandoffError):
            read_handoff(self.path)

    def test_unclosed_front_matter_rejected(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("---\nversion: 1\n", encoding="utf-8")
        with self.assertRaises(HandoffError):
            read_handoff(self.path)

    def test_unsupported_version_rejected(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("---\nversion: 999\n---\n", encoding="utf-8")
        with self.assertRaises(HandoffError):
            read_handoff(self.path)

    def test_invalid_item_status_rejected(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            "---\nversion: 1\nunresolved:\n"
            "  - id: u-1\n    type: issue\n    description: x\n"
            "    status: MAYBE\n---\n",
            encoding="utf-8",
        )
        with self.assertRaises(HandoffError):
            read_handoff(self.path)

    def test_duplicate_ids_rejected(self):
        doc = handoff.empty_handoff()
        add_item(doc, "issue", "one", item_id="u-1")
        with self.assertRaises(HandoffError):
            add_item(doc, "issue", "two", item_id="u-1")


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.doc = handoff.empty_handoff(session_id="s")

    def test_open_items_high_priority_first(self):
        add_item(self.doc, "issue", "low one", priority="low", item_id="u-low")
        add_item(self.doc, "issue", "high one", priority="high", item_id="u-high")
        add_item(self.doc, "issue", "mid one", priority="medium", item_id="u-mid")
        self.assertEqual(
            [item.id for item in open_items(self.doc)], ["u-high", "u-mid", "u-low"]
        )

    def test_deferred_billing_issue_remains_traceable(self):
        add_item(
            self.doc,
            "issue",
            "billing is not yet implemented",
            priority="high",
            item_id="u-bill",
        )
        set_item_status(
            self.doc,
            "u-bill",
            "DEFERRED",
            target_spec="billing-change",
            reason="billing is not yet implemented",
            note="deferred by operator",
        )
        item = get_item(self.doc, "u-bill")
        self.assertEqual(item.status, "DEFERRED")
        self.assertEqual(item.target_spec, "billing-change")
        self.assertEqual(item.reason, "billing is not yet implemented")
        self.assertTrue(item.history)

    def test_deferred_without_target_and_reason_rejected(self):
        add_item(self.doc, "issue", "x", item_id="u-1")
        with self.assertRaises(HandoffError):
            set_item_status(self.doc, "u-1", "DEFERRED")

    def test_resolution_retains_history(self):
        add_item(self.doc, "issue", "x", item_id="u-1")
        set_item_status(self.doc, "u-1", "RESOLVED", note="verified")
        item = get_item(self.doc, "u-1")
        self.assertEqual(item.status, "RESOLVED")
        self.assertEqual(item.history[0]["from"], "OPEN")
        self.assertEqual(item.history[0]["to"], "RESOLVED")
        # The item is retained, not deleted.
        self.assertEqual(len(self.doc.unresolved), 1)

    def test_unknown_item_rejected(self):
        with self.assertRaises(HandoffError):
            set_item_status(self.doc, "ghost", "RESOLVED")

    def test_count_unresolved_excludes_resolved(self):
        add_item(self.doc, "issue", "a", item_id="u-1")
        add_item(self.doc, "issue", "b", item_id="u-2")
        set_item_status(self.doc, "u-1", "RESOLVED")
        self.assertEqual(count_unresolved(self.doc), 1)


if __name__ == "__main__":
    unittest.main()
