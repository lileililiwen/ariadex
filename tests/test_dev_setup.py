"""Tests for the explicit development-environment bootstrap."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ariadex import dev_setup


class DevSetupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "pyproject.toml").write_text("[project]\nname='demo'\n")
        (self.root / "uv.lock").write_text("version = 1\n")

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_uv_without_confirmation_does_not_mutate(self):
        with mock.patch.object(dev_setup, "find_uv", return_value=None):
            result = dev_setup.setup(self.root)

        self.assertEqual(result.state, "manual")
        self.assertIn("--yes", result.detail)

    def test_confirmed_setup_installs_syncs_and_verifies(self):
        commands = []

        def runner(argv, **kwargs):
            commands.append(argv)
            return dev_setup.Completed(0, "", "")

        with (
            mock.patch.object(dev_setup, "find_uv", side_effect=[None, "/tmp/uv"]),
            mock.patch.object(dev_setup, "install_uv", return_value="/tmp/uv"),
        ):
            result = dev_setup.setup(self.root, confirmed=True, runner=runner)

        self.assertEqual(result.state, "ready")
        self.assertEqual(commands[0], ["/tmp/uv", "sync", "--frozen", "--extra", "dev"])
        self.assertEqual(
            commands[1], ["/tmp/uv", "run", "--frozen", "pip-audit", "--version"]
        )

    def test_sync_failure_never_claims_ready(self):
        def runner(argv, **kwargs):
            return dev_setup.Completed(1, "", "lock is stale")

        with mock.patch.object(dev_setup, "find_uv", return_value="/tmp/uv"):
            result = dev_setup.setup(self.root, runner=runner)

        self.assertEqual(result.state, "blocked")
        self.assertIn("lock is stale", result.detail)

    def test_runtime_install_does_not_use_dev_setup(self):
        self.assertNotIn("dev", dev_setup.RUNTIME_INSTALL_SCOPE)


if __name__ == "__main__":
    unittest.main()
