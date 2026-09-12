"""Live tmux lifecycle test. Skipped unless tmux is installed.

Blocked prerequisite in this environment: the `tmux` binary is not on PATH,
so this test skips and the blocker is recorded in HANDOFF.md.
"""

import shutil
import tempfile
import unittest

from ariadex import providers
from ariadex.adapters import select_reset
from ariadex.terminal import TmuxDriver, session_name_for


@unittest.skipUnless(shutil.which("tmux"), "tmux binary not available")
class LiveTmuxTest(unittest.TestCase):
    def test_create_send_capture_terminate(self):
        driver = TmuxDriver()
        name = session_name_for("integration-probe")
        try:
            driver.terminate(name)
            adapter = providers.OpenCodeAdapter(driver, name, tempfile.gettempdir())
            self.assertEqual(adapter.start(), "created")
            self.assertTrue(driver.session_alive(name))
            adapter.send("echo live-probe")
            captured = adapter.capture_output()
            self.assertIsInstance(captured, str)
            self.assertEqual(select_reset("auto", adapter.capabilities), "soft")
            self.assertEqual(
                driver.attach_command(name)[:2], ["tmux", "attach-session"]
            )
        finally:
            driver.terminate(name)
            self.assertFalse(driver.session_alive(name))


if __name__ == "__main__":
    unittest.main()
