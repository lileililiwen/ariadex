"""Stale daemon records must not suppress a new managed start."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ariadex import cli, daemon


class StaleDaemonRecoveryTest(unittest.TestCase):
    def test_dead_record_and_missing_socket_are_not_live_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".ariadex").mkdir()
            daemon.write_record(
                root,
                daemon.DaemonRecord(pid=999999999, session_id="session"),
            )
            with mock.patch.object(cli, "_report_live_owner") as report:
                self.assertFalse(cli._live_owner(root, False))
            report.assert_not_called()

    def test_live_owner_requires_typed_socket_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".ariadex").mkdir()
            record = daemon.DaemonRecord(pid=123, session_id="session")
            daemon.write_record(root, record)
            with (
                mock.patch.object(daemon, "daemon_alive", return_value=True),
                mock.patch.object(cli, "_daemon_ipc_or_none", return_value=None),
                mock.patch.object(cli, "_report_live_owner") as report,
            ):
                self.assertFalse(cli._live_owner(root, False))
            report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
