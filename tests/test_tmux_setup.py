"""Tests for unattended tmux setup. Installs are always mocked."""

import io
import subprocess
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ariadex import cli, state
from ariadex.tmux_setup import (
    TmuxSetupError,
    detect_manager,
    ensure_tmux,
    install_command,
    manual_hint,
    require_tmux,
)


def completed(returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stderr=stderr)


class DetectionTest(unittest.TestCase):
    def test_present_binary_returned_without_install(self):
        with (
            mock.patch("shutil.which", return_value="/usr/bin/tmux"),
            mock.patch("subprocess.run") as run,
        ):
            self.assertEqual(ensure_tmux(), "/usr/bin/tmux")
            run.assert_not_called()

    def test_first_manager_wins(self):
        def which(name):
            return f"/bin/{name}" if name in ("dnf", "brew") else None

        with mock.patch("shutil.which", side_effect=which):
            self.assertEqual(detect_manager(), "dnf")

    def test_no_manager_detected(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertIsNone(detect_manager())
            with self.assertRaises(TmuxSetupError) as ctx:
                ensure_tmux()
        self.assertIn("package manager", str(ctx.exception))


class InstallCommandTest(unittest.TestCase):
    def test_apt_command_as_root(self):
        with mock.patch("os.geteuid", return_value=0):
            self.assertEqual(
                install_command("apt-get"), ["apt-get", "install", "-y", "tmux"]
            )

    def test_sudo_prefix_for_non_root(self):
        def which(name):
            return f"/bin/{name}" if name == "sudo" else None

        with (
            mock.patch("os.geteuid", return_value=1000),
            mock.patch("shutil.which", side_effect=which),
        ):
            self.assertEqual(
                install_command("dnf"),
                ["sudo", "-n", "dnf", "install", "-y", "tmux"],
            )

    def test_no_sudo_prefix_without_sudo_binary(self):
        with (
            mock.patch("os.geteuid", return_value=1000),
            mock.patch("shutil.which", return_value=None),
        ):
            self.assertEqual(install_command("apk"), ["apk", "add", "tmux"])

    def test_unsupported_manager_rejected(self):
        with self.assertRaises(TmuxSetupError):
            install_command("choco")

    def test_manual_hints(self):
        self.assertIn("apt-get", manual_hint("apt-get"))
        self.assertIn("package manager", manual_hint(None))


class EnsureTest(unittest.TestCase):
    def run_install(self, which_calls, run_results, euid=0):
        which_mock = mock.patch("shutil.which", side_effect=which_calls)
        run_mock = mock.patch("subprocess.run", side_effect=run_results)
        euid_mock = mock.patch("os.geteuid", return_value=euid)
        return which_mock, run_mock, euid_mock

    def test_apt_install_updates_then_installs(self):
        tmux_probes = []

        def which(name):
            if name == "tmux":
                tmux_probes.append(name)
                return "/usr/bin/tmux" if len(tmux_probes) > 1 else None
            return f"/bin/{name}"

        with (
            mock.patch("shutil.which", side_effect=which),
            mock.patch("os.geteuid", return_value=0),
            mock.patch("subprocess.run", return_value=completed()) as run,
        ):
            self.assertEqual(ensure_tmux(), "/usr/bin/tmux")
        invocations = [call.args[0] for call in run.call_args_list]
        self.assertEqual(invocations[0], ["apt-get", "update"])
        self.assertEqual(invocations[1], ["apt-get", "install", "-y", "tmux"])

    def test_failed_install_is_actionable(self):
        def which(name):
            return "/bin/apt-get" if name == "apt-get" else None

        with (
            mock.patch("shutil.which", side_effect=which),
            mock.patch("os.geteuid", return_value=0),
            mock.patch(
                "subprocess.run",
                return_value=completed(1, "boom"),
            ),
            self.assertRaises(TmuxSetupError) as ctx,
        ):
            ensure_tmux()
        message = str(ctx.exception)
        self.assertIn("boom", message)
        self.assertIn("apt-get install", message)

    def test_success_without_binary_is_actionable(self):
        def which(name):
            return "/bin/brew" if name == "brew" else None

        with (
            mock.patch("shutil.which", side_effect=which),
            mock.patch("subprocess.run", return_value=completed()),
            self.assertRaises(TmuxSetupError) as ctx,
        ):
            ensure_tmux()
        self.assertIn("still not on PATH", str(ctx.exception))


class RequireTest(unittest.TestCase):
    def test_present_binary_passes(self):
        with mock.patch("shutil.which", return_value="/usr/bin/tmux"):
            self.assertEqual(require_tmux(), "/usr/bin/tmux")

    def test_missing_binary_stops_before_work(self):
        with (
            mock.patch("shutil.which", return_value=None),
            self.assertRaises(TmuxSetupError) as ctx,
        ):
            require_tmux()
        self.assertIn("before sending work", str(ctx.exception))


def run_cli(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with chdir(root), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


class WiringTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        run_cli(self.root, "init")
        stored = state.read(self.root)
        stored.mode = "AUTO"
        state.write(self.root, stored)

    def test_failed_auto_install_surfaces_actionably(self):
        with mock.patch(
            "ariadex.cli.tmux_setup_mod.ensure_tmux",
            side_effect=TmuxSetupError("no manager here"),
        ):
            code, _, err = run_cli(self.root, "run")
        self.assertNotEqual(code, 0)
        self.assertIn("no manager here", err)

    def test_opt_out_skips_install_attempt(self):
        with (
            mock.patch("shutil.which", return_value=None),
            mock.patch("subprocess.run") as run,
        ):
            code, _, err = run_cli(self.root, "--no-auto-install", "run")
        self.assertNotEqual(code, 0)
        self.assertIn("before sending work", err)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
