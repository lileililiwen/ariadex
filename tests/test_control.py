"""Tests for mode transitions and input ownership."""

import unittest

from ariadex.control import (
    TransitionError,
    allows_scheduling,
    owns_input,
    transition,
)


class TransitionTest(unittest.TestCase):
    def test_pause_from_any_mode(self):
        for current in ("AUTO", "MANUAL", "PAUSE"):
            self.assertEqual(transition(current, "PAUSE", via="pause"), "PAUSE")

    def test_takeover_enters_manual(self):
        for current in ("AUTO", "MANUAL", "PAUSE"):
            self.assertEqual(transition(current, "MANUAL", via="takeover"), "MANUAL")

    def test_auto_enters_auto(self):
        for current in ("AUTO", "MANUAL", "PAUSE"):
            self.assertEqual(transition(current, "AUTO", via="auto"), "AUTO")

    def test_resume_from_pause(self):
        self.assertEqual(transition("PAUSE", "AUTO", via="resume"), "AUTO")

    def test_idempotent_repeats_succeed(self):
        self.assertEqual(transition("PAUSE", "PAUSE", via="pause"), "PAUSE")
        self.assertEqual(transition("MANUAL", "MANUAL", via="takeover"), "MANUAL")
        self.assertEqual(transition("AUTO", "AUTO", via="auto"), "AUTO")

    def test_resume_rejected_outside_pause(self):
        for current in ("AUTO", "MANUAL"):
            with self.assertRaises(TransitionError) as ctx:
                transition(current, "AUTO", via="resume")
            self.assertIn("resume rejected", str(ctx.exception))

    def test_via_target_mismatch_rejected(self):
        with self.assertRaises(TransitionError):
            transition("AUTO", "PAUSE", via="takeover")

    def test_unknown_transition_rejected(self):
        with self.assertRaises(TransitionError):
            transition("AUTO", "MANUAL", via="hypnotize")

    def test_invalid_modes_rejected(self):
        with self.assertRaises(TransitionError):
            transition("SLEEP", "MANUAL", via="takeover")
        with self.assertRaises(TransitionError):
            transition("AUTO", "SLEEP", via="takeover")


class OwnershipTest(unittest.TestCase):
    def test_only_auto_owns_input(self):
        self.assertTrue(owns_input("AUTO"))
        self.assertFalse(owns_input("MANUAL"))
        self.assertFalse(owns_input("PAUSE"))

    def test_only_auto_schedules(self):
        self.assertTrue(allows_scheduling("AUTO"))
        self.assertFalse(allows_scheduling("MANUAL"))
        self.assertFalse(allows_scheduling("PAUSE"))


if __name__ == "__main__":
    unittest.main()
