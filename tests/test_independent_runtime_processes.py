"""Regression checks for independent control boundaries."""

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class IndependentRuntimeProcessTests(unittest.TestCase):
    def test_companion_uses_nonblocking_managed_path(self) -> None:
        source = (ROOT / "src/ariadex/companion.py").read_text(encoding="utf-8")
        self.assertIn('nonblocking=True', source)
        self.assertIn('name="ariadex-widget-refresh"', source)

    def test_daemon_dispatches_each_socket_connection_to_worker(self) -> None:
        source = (ROOT / "src/ariadex/daemon.py").read_text(encoding="utf-8")
        self.assertIn('name="ariadex-daemon-ipc"', source)
        self.assertIn("target=handle_connection", source)


if __name__ == "__main__":
    unittest.main()
