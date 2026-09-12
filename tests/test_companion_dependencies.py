"""Tests for automatic companion prerequisite installation (python3-tk).

Covers missing Tkinter detection, package-manager mapping, confirmation and
`--no-dependency-install` opt-out, no-root refusal, install success/failure,
and fail-closed post-install verification. All package-manager invocations
are mocked; no host mutation occurs.
"""

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ariadex import cli, deploy
from ariadex import companion as companion_mod


def run_cli(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with chdir(root), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


def ok_proc(argv=None) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv or ["cmd"], 0, "", "")


def fail_proc(argv=None, detail: str = "refused") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv or ["cmd"], 1, "", detail)


class MappingTest(unittest.TestCase):
    def test_apt_maps_to_python3_tk(self):
        self.assertEqual(deploy.tkinter_package_for_manager("apt-get"), "python3-tk")

    def test_unknown_manager_is_none(self):
        self.assertIsNone(deploy.tkinter_package_for_manager("brew"))
        self.assertIsNone(deploy.tkinter_package_for_manager(None))

    def test_install_command_uses_sudo_policy(self):
        with (
            mock.patch.object(deploy.shutil, "which", return_value="/usr/bin/sudo"),
            mock.patch("ariadex.tmux_setup.needs_sudo", return_value=True),
        ):
            cmd = deploy.tkinter_install_command("apt-get")
        self.assertEqual(cmd[:2], ["sudo", "-n"])
        self.assertIn("python3-tk", cmd)
        self.assertNotIn("tmux", cmd)

    def test_interactive_install_command_allows_sudo_prompt(self):
        with (
            mock.patch.object(deploy.shutil, "which", return_value="/usr/bin/sudo"),
            mock.patch("ariadex.tmux_setup.needs_sudo", return_value=True),
        ):
            cmd = deploy.tkinter_install_command("apt-get", interactive_sudo=True)
        self.assertEqual(cmd[:2], ["sudo", "apt-get"])
        self.assertNotIn("-n", cmd)

    def test_install_command_unsupported_raises(self):
        with self.assertRaises(deploy.DeployError):
            deploy.tkinter_install_command("brew")

    def test_manual_hint_names_package(self):
        self.assertIn("python3-tk", deploy.tkinter_manual_hint("apt-get"))

    def test_prerequisite_states_distinct(self):
        status = deploy.companion_prerequisites()
        self.assertIn("tkinter_available", status)
        self.assertIn("desktop", status)
        self.assertIn("hotkey_ok", status)


class EnsureTest(unittest.TestCase):
    def test_present_tkinter_is_installed_without_runner(self):
        runner = mock.Mock(side_effect=AssertionError("must not run"))
        result = deploy.ensure_companion_dependencies(
            allow_install=True,
            confirmed=True,
            runner=runner,
            tkinter_probe=lambda: True,
        )
        self.assertEqual(result.state, "installed")

    def test_opt_out_is_manual_without_mutation(self):
        runner = mock.Mock(side_effect=AssertionError("must not run"))
        with (
            mock.patch.object(companion_mod, "tkinter_available", return_value=False),
            mock.patch("ariadex.tmux_setup.detect_manager", return_value="apt-get"),
        ):
            result = deploy.ensure_companion_dependencies(
                allow_install=False,
                confirmed=True,
                runner=runner,
                tkinter_probe=lambda: False,
            )
        self.assertEqual(result.state, "manual")
        self.assertIn("python3-tk", result.detail)
        self.assertIn("--no-dependency-install", result.detail)

    def test_unconfirmed_is_manual_without_mutation(self):
        runner = mock.Mock(side_effect=AssertionError("must not run"))
        with (
            mock.patch.object(companion_mod, "tkinter_available", return_value=False),
            mock.patch("ariadex.tmux_setup.detect_manager", return_value="apt-get"),
        ):
            result = deploy.ensure_companion_dependencies(
                allow_install=True,
                confirmed=False,
                runner=runner,
                tkinter_probe=lambda: False,
            )
        self.assertEqual(result.state, "manual")
        self.assertIn("--yes", result.detail)

    def test_unsupported_manager_is_manual(self):
        runner = mock.Mock(side_effect=AssertionError("must not run"))
        with (
            mock.patch.object(companion_mod, "tkinter_available", return_value=False),
            mock.patch("ariadex.tmux_setup.detect_manager", return_value=None),
        ):
            result = deploy.ensure_companion_dependencies(
                allow_install=True,
                confirmed=True,
                runner=runner,
                tkinter_probe=lambda: False,
            )
        self.assertEqual(result.state, "manual")

    def test_success_installs_and_verifies(self):
        calls: list = []

        def runner(argv, **kwargs):
            calls.append(list(argv))
            return ok_proc(argv)

        with (
            mock.patch.object(companion_mod, "tkinter_available", return_value=False),
            mock.patch("ariadex.tmux_setup.detect_manager", return_value="apt-get"),
            mock.patch("ariadex.tmux_setup.needs_sudo", return_value=False),
            mock.patch.object(
                deploy, "verify_tkinter_with_interpreter", return_value=True
            ),
        ):
            result = deploy.ensure_companion_dependencies(
                allow_install=True,
                confirmed=True,
                runner=runner,
                tkinter_probe=lambda: False,
            )
        self.assertEqual(result.state, "installed")
        self.assertTrue(any("python3-tk" in c for c in calls))

    def test_interactive_install_streams_package_manager_output(self):
        kwargs_seen: list[dict] = []

        def runner(argv, **kwargs):
            kwargs_seen.append(kwargs)
            return ok_proc(argv)

        with (
            mock.patch.object(companion_mod, "tkinter_available", return_value=False),
            mock.patch("ariadex.tmux_setup.detect_manager", return_value="apt-get"),
            mock.patch("ariadex.tmux_setup.needs_sudo", return_value=True),
            mock.patch.object(deploy.shutil, "which", return_value="/usr/bin/sudo"),
            mock.patch.object(
                deploy, "verify_tkinter_with_interpreter", return_value=True
            ),
        ):
            result = deploy.ensure_companion_dependencies(
                allow_install=True,
                confirmed=True,
                interactive_sudo=True,
                runner=runner,
                tkinter_probe=lambda: False,
            )
        self.assertEqual(result.state, "installed")
        self.assertEqual([item["capture_output"] for item in kwargs_seen], [False, False])

    def test_failed_install_is_blocked_with_command(self):
        def runner(argv, **kwargs):
            return fail_proc(argv, "no passwordless sudo")

        with (
            mock.patch.object(companion_mod, "tkinter_available", return_value=False),
            mock.patch("ariadex.tmux_setup.detect_manager", return_value="apt-get"),
            mock.patch("ariadex.tmux_setup.needs_sudo", return_value=True),
            mock.patch.object(deploy.shutil, "which", return_value="/usr/bin/sudo"),
        ):
            result = deploy.ensure_companion_dependencies(
                allow_install=True,
                confirmed=True,
                runner=runner,
                tkinter_probe=lambda: False,
            )
        self.assertEqual(result.state, "blocked")
        self.assertIn("sudo -n", result.detail)
        self.assertIn("no passwordless sudo", result.detail)

    def test_no_root_refusal_is_blocked(self):
        # sudo -n without passwordless rights fails fast; surface it blocked.
        def runner(argv, **kwargs):
            self.assertEqual(argv[:2], ["sudo", "-n"])
            return fail_proc(argv, "sudo: a password is required")

        with (
            mock.patch.object(companion_mod, "tkinter_available", return_value=False),
            mock.patch("ariadex.tmux_setup.detect_manager", return_value="apt-get"),
            mock.patch("ariadex.tmux_setup.needs_sudo", return_value=True),
            mock.patch.object(deploy.shutil, "which", return_value="/usr/bin/sudo"),
        ):
            result = deploy.ensure_companion_dependencies(
                allow_install=True,
                confirmed=True,
                runner=runner,
                tkinter_probe=lambda: False,
            )
        self.assertEqual(result.state, "blocked")
        self.assertIn("manually", result.detail)

    def test_success_exit_without_tkinter_is_blocked(self):
        def runner(argv, **kwargs):
            return ok_proc(argv)

        with (
            mock.patch.object(companion_mod, "tkinter_available", return_value=False),
            mock.patch("ariadex.tmux_setup.detect_manager", return_value="apt-get"),
            mock.patch("ariadex.tmux_setup.needs_sudo", return_value=False),
            mock.patch.object(
                deploy, "verify_tkinter_with_interpreter", return_value=False
            ),
        ):
            result = deploy.ensure_companion_dependencies(
                allow_install=True,
                confirmed=True,
                runner=runner,
                tkinter_probe=lambda: False,
            )
        self.assertEqual(result.state, "blocked")
        self.assertIn("still cannot be imported", result.detail)


class IsolatedHomeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        code, _, _ = run_cli(self.root, "init")
        assert code == 0
        self.env = mock.patch.dict(
            os.environ,
            {"HOME": str(self.home), "XDG_DATA_HOME": "", "XDG_CONFIG_HOME": ""},
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.entry = mock.patch.object(
            deploy, "resolve_entry", return_value=[os.devnull, "-m", "ariadex.cli"]
        )
        self.entry.start()
        self.addCleanup(self.entry.stop)


class InstallProjectDependencyTest(IsolatedHomeTest):
    def _adapter(self):
        def ok(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, "", "")

        return deploy.SystemdUserAdapter(runner=ok)

    def test_blocked_dependency_still_installs_files_but_autostart_manual(self):
        with (
            mock.patch.object(companion_mod, "tkinter_available", return_value=False),
            mock.patch.object(
                companion_mod,
                "detect_desktop",
                return_value=companion_mod.DesktopInfo("x11", True, "ok"),
            ),
            mock.patch.object(deploy.shutil, "which", return_value="/bin/systemctl"),
            mock.patch.object(
                deploy,
                "ensure_companion_dependencies",
                return_value=deploy.ArtifactResult(
                    "companion-dependencies", "blocked", "install failed"
                ),
            ) as ensured,
        ):
            report = deploy.install_project(
                self.root,
                adapter=self._adapter(),
                allow_dependency_install=True,
                dependency_confirmed=True,
            )
        ensured.assert_called_once()
        by_name = {a.name: a.state for a in report.artifacts}
        self.assertEqual(by_name["companion-dependencies"], "blocked")
        self.assertEqual(by_name["autostart"], "manual")
        # OS packages never enter the ownership manifest.
        manifest = deploy.load_manifest()
        self.assertNotIn("python3-tk", " ".join(manifest.get("owned", [])))

    def test_uninstall_never_removes_os_packages(self):
        with (
            mock.patch.object(companion_mod, "tkinter_available", return_value=True),
            mock.patch.object(
                companion_mod,
                "detect_desktop",
                return_value=companion_mod.DesktopInfo("x11", True, "ok"),
            ),
            mock.patch.object(deploy.shutil, "which", return_value="/bin/systemctl"),
        ):
            deploy.install_project(self.root, adapter=self._adapter())
            manifest_before = deploy.load_manifest()
            self.assertTrue(manifest_before.get("owned"))
            report = deploy.uninstall_project(adapter=self._adapter())
        names = [a.name for a in report.artifacts]
        self.assertNotIn("companion-dependencies", names)


class CliDependencyFlagTest(IsolatedHomeTest):
    def test_no_dependency_install_reports_manual_without_runner(self):
        with (
            mock.patch.object(companion_mod, "tkinter_available", return_value=False),
            mock.patch.object(
                companion_mod,
                "detect_desktop",
                return_value=companion_mod.DesktopInfo("x11", True, "ok"),
            ),
            mock.patch.object(deploy.shutil, "which", return_value="/bin/systemctl"),
            mock.patch.object(
                deploy.SystemdUserAdapter, "_systemctl", return_value=ok_proc()
            ),
            mock.patch.object(
                deploy,
                "ensure_companion_dependencies",
                wraps=deploy.ensure_companion_dependencies,
            ) as ensured,
            mock.patch.object(deploy, "verify_tkinter_with_interpreter") as _v,
        ):
            code, out, _ = run_cli(
                self.root, "install", "--yes", "--no-dependency-install"
            )
        self.assertEqual(code, 0)
        self.assertIn("companion-dependencies: manual", out)
        self.assertIn("autostart: manual", out)
        # Opt-out path never probes the launch interpreter.
        _v.assert_not_called()
        _, kwargs = ensured.call_args
        self.assertFalse(kwargs.get("allow_install", True))

    def test_install_plan_names_dependency_step(self):
        plan = deploy.install_plan(self.root)
        self.assertTrue(any("prerequisite" in line for line in plan))
        self.assertTrue(any("--no-dependency-install" in line for line in plan))


class DoctorHintTest(IsolatedHomeTest):
    def test_doctor_names_manual_command_when_tkinter_missing(self):
        from ariadex import operator as operator_mod

        with (
            mock.patch.object(companion_mod, "tkinter_available", return_value=False),
            mock.patch.object(
                companion_mod,
                "detect_desktop",
                return_value=companion_mod.DesktopInfo("x11", True, "ok"),
            ),
        ):
            checks, _ = operator_mod.run_doctor(self.root)
        companion = next(c for c in checks if c.name == "companion")
        self.assertFalse(companion.ok)
        self.assertIn("Tkinter", companion.detail)

    def test_capability_report_names_hint_when_tkinter_missing(self):
        with (
            mock.patch.object(companion_mod, "tkinter_available", return_value=False),
            mock.patch.object(
                companion_mod,
                "detect_desktop",
                return_value=companion_mod.DesktopInfo("x11", True, "ok"),
            ),
        ):
            report = deploy.capability_report(self.root)
        self.assertIn("Tkinter", report.desktop)


class ConfirmDependencyTest(unittest.TestCase):
    def test_confirmed_skips_prompt(self):
        with mock.patch.object(cli.sys.stdin, "isatty") as isatty:
            self.assertTrue(cli._confirm_dependency(True, "prompt"))
            isatty.assert_not_called()

    def test_non_interactive_without_yes_declines(self):
        with mock.patch.object(cli.sys.stdin, "isatty", return_value=False):
            self.assertFalse(cli._confirm_dependency(False, "prompt"))

    def test_isatty_error_declines(self):
        with mock.patch.object(cli.sys.stdin, "isatty", side_effect=OSError("no tty")):
            self.assertFalse(cli._confirm_dependency(False, "prompt"))

    def test_interactive_yes_confirms(self):
        with (
            mock.patch.object(cli.sys.stdin, "isatty", return_value=True),
            mock.patch.object(cli, "input", return_value="y"),
        ):
            self.assertTrue(cli._confirm_dependency(False, "prompt"))

    def test_interactive_no_declines(self):
        with (
            mock.patch.object(cli.sys.stdin, "isatty", return_value=True),
            mock.patch.object(cli, "input", return_value="n"),
        ):
            self.assertFalse(cli._confirm_dependency(False, "prompt"))

    def test_interactive_eof_declines(self):
        with (
            mock.patch.object(cli.sys.stdin, "isatty", return_value=True),
            mock.patch.object(cli, "input", side_effect=EOFError),
        ):
            self.assertFalse(cli._confirm_dependency(False, "prompt"))


class CmdInstallDependencyPromptTest(IsolatedHomeTest):
    def _platform(self, test, tkinter_ok: bool):
        which = mock.patch.object(deploy.shutil, "which", return_value="/bin/systemctl")
        which.start()
        test.addCleanup(which.stop)
        fake = subprocess.CompletedProcess(["systemctl"], 0, "", "")
        runner = mock.patch.object(
            deploy.SystemdUserAdapter, "_systemctl", return_value=fake
        )
        runner.start()
        test.addCleanup(runner.stop)
        tk = mock.patch.object(
            companion_mod, "tkinter_available", return_value=tkinter_ok
        )
        tk.start()
        test.addCleanup(tk.stop)
        desktop = mock.patch.object(
            companion_mod,
            "detect_desktop",
            return_value=companion_mod.DesktopInfo("x11", True, "ok"),
        )
        desktop.start()
        test.addCleanup(desktop.stop)

    def test_yes_with_missing_tkinter_confirms_dependency(self):
        self._platform(self, tkinter_ok=False)
        with (
            mock.patch.object(
                deploy,
                "ensure_companion_dependencies",
                wraps=deploy.ensure_companion_dependencies,
            ) as ensured,
            mock.patch.object(
                deploy, "verify_tkinter_with_interpreter", return_value=True
            ),
            mock.patch.object(deploy.shutil, "which", return_value="/bin/systemctl"),
        ):
            code, out, _ = run_cli(self.root, "install", "--yes")
        self.assertEqual(code, 0)
        self.assertIn("dependency:", out)
        _, kwargs = ensured.call_args
        self.assertTrue(kwargs.get("allow_install", False))
        self.assertTrue(kwargs.get("confirmed", False))

    def test_interactive_yes_confirms_dependency(self):
        self._platform(self, tkinter_ok=False)
        with (
            mock.patch.object(cli.sys.stdin, "isatty", return_value=True),
            mock.patch.object(cli, "input", side_effect=["y", "y"]),
            mock.patch.object(
                deploy,
                "ensure_companion_dependencies",
                return_value=deploy.ArtifactResult(
                    "companion-dependencies", "installed", "ok"
                ),
            ) as ensured,
        ):
            code, out, _ = run_cli(self.root, "install")
        self.assertEqual(code, 0)
        self.assertIn("dependency:", out)
        _, kwargs = ensured.call_args
        self.assertTrue(kwargs.get("allow_install", False))
        self.assertTrue(kwargs.get("confirmed", False))

    def test_interactive_decline_keeps_manual(self):
        self._platform(self, tkinter_ok=False)
        with (
            mock.patch.object(cli.sys.stdin, "isatty", return_value=True),
            mock.patch.object(cli, "input", side_effect=["y", "n"]),
            mock.patch.object(
                deploy,
                "ensure_companion_dependencies",
                wraps=deploy.ensure_companion_dependencies,
            ) as ensured,
        ):
            code, out, _ = run_cli(self.root, "install")
        self.assertEqual(code, 0)
        self.assertIn("dependency:", out)
        _, kwargs = ensured.call_args
        self.assertFalse(kwargs.get("allow_install", True))

    def test_non_interactive_without_yes_skips_dependency(self):
        self._platform(self, tkinter_ok=False)
        with (
            mock.patch.object(cli.sys.stdin, "isatty", return_value=False),
            mock.patch.object(
                deploy,
                "ensure_companion_dependencies",
                wraps=deploy.ensure_companion_dependencies,
            ) as ensured,
        ):
            code, out, _ = run_cli(self.root, "install")
        # Install confirmation passes non-interactively; the OS
        # prerequisite step must still decline without --yes.
        self.assertEqual(code, 0)
        self.assertIn("dependency:", out)
        _, kwargs = ensured.call_args
        self.assertFalse(kwargs.get("allow_install", True))

    def test_present_tkinter_skips_dependency_prompt(self):
        self._platform(self, tkinter_ok=True)
        code, out, _ = run_cli(self.root, "install", "--yes")
        self.assertEqual(code, 0)
        self.assertNotIn("dependency:", out)


if __name__ == "__main__":
    unittest.main()
