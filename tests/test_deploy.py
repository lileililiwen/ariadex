"""Tests for user-scoped install, uninstall, and deployment readiness."""

import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ariadex import cli, deploy, operator


def run_cli(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with chdir(root), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


def init_project(root: Path) -> None:
    code, _, _ = run_cli(root, "init")
    assert code == 0


class IsolatedHomeTest(unittest.TestCase):
    """Every test gets a fresh HOME so the real user tree is untouched."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        init_project(self.root)
        self.env = mock.patch.dict(
            os.environ,
            {"HOME": str(self.home), "XDG_DATA_HOME": "", "XDG_CONFIG_HOME": ""},
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        # Deterministic entry point: the module invocation, not PATH luck.
        self.entry = mock.patch.object(
            deploy, "resolve_entry", return_value=[os.devnull, "-m", "ariadex.cli"]
        )
        self.entry.start()
        self.addCleanup(self.entry.stop)


def fake_systemctl_ok(argv, **kwargs):
    out = ""
    if argv[-1] == "is-enabled":
        out = "enabled\n"
    if argv[-1] == "is-active":
        out = "active\n"
    return subprocess.CompletedProcess(argv, 0, out, "")


class ManifestTest(IsolatedHomeTest):
    def test_missing_manifest_is_empty(self):
        self.assertEqual(deploy.load_manifest(), {})

    def test_corrupt_and_foreign_manifests_refused(self):
        path = deploy.manifest_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        for bad in ("{not json", "[1, 2]", '{"version": 99, "owned": []}'):
            with self.subTest(bad=bad):
                path.write_text(bad, encoding="utf-8")
                self.assertEqual(deploy.load_manifest(), {})

    def test_manifest_round_trip_is_restrictive(self):
        deploy.save_manifest(["/tmp/x"], "/tmp/proj")
        loaded = deploy.load_manifest()
        self.assertEqual(loaded["owned"], ["/tmp/x"])
        self.assertEqual(loaded["project_dir"], "/tmp/proj")
        mode = stat.S_IMODE(deploy.manifest_path().stat().st_mode)
        self.assertEqual(mode, 0o600)


class EntryResolutionTest(IsolatedHomeTest):
    def test_prefers_installed_console_script(self):
        self.entry.stop()
        with mock.patch.object(
            deploy.shutil, "which", return_value="/usr/local/bin/ariadex"
        ):
            self.assertEqual(deploy.resolve_entry(), ["/usr/local/bin/ariadex"])

    def test_falls_back_to_module_without_checkout(self):
        self.entry.stop()
        with mock.patch.object(deploy.shutil, "which", return_value=None):
            entry = deploy.resolve_entry()
            self.assertEqual(entry[1:], ["-m", "ariadex.cli"])
            self.assertTrue(Path(entry[0]).is_absolute())


class SystemdAdapterTest(IsolatedHomeTest):
    def test_unit_invokes_entry_not_checkout(self):
        unit = deploy.systemd_unit_text(["/usr/local/bin/ariadex"], self.root)
        self.assertIn("ExecStart=/usr/local/bin/ariadex start", unit)
        self.assertIn(f"WorkingDirectory={self.root}", unit)
        self.assertNotIn(".ariadex", unit)

    def test_autostart_invokes_entry(self):
        text = deploy.autostart_desktop_text(["/usr/local/bin/ariadex"], self.root)
        self.assertIn("/usr/local/bin/ariadex", text)
        self.assertIn("companion", text)

    def test_no_systemctl_is_manual(self):
        adapter = deploy.SystemdUserAdapter()
        with mock.patch.object(deploy.shutil, "which", return_value=None):
            result = adapter.install_unit(["ariadex"], self.root)
        self.assertEqual(result.state, "manual")
        self.assertIn("start the daemon", result.detail)

    def test_successful_enable(self):
        adapter = deploy.SystemdUserAdapter(runner=fake_systemctl_ok)
        with mock.patch.object(deploy.shutil, "which", return_value="/bin/systemctl"):
            result = adapter.install_unit(["ariadex"], self.root)
        self.assertEqual(result.state, "installed")
        unit_path = deploy.config_home() / "systemd" / "user" / deploy.DAEMON_UNIT_NAME
        self.assertTrue(unit_path.is_file())

    def test_failed_enable_rolls_back_unit(self):
        def failing(argv, **kwargs):
            code = 0 if argv[-1] == "daemon-reload" else 1
            return subprocess.CompletedProcess(argv, code, "", "refused")

        adapter = deploy.SystemdUserAdapter(runner=failing)
        with (
            mock.patch.object(deploy.shutil, "which", return_value="/bin/systemctl"),
            self.assertRaises(deploy.DeployError) as ctx,
        ):
            adapter.install_unit(["ariadex"], self.root)
        self.assertIn("enable refused", str(ctx.exception))
        unit_path = deploy.config_home() / "systemd" / "user" / deploy.DAEMON_UNIT_NAME
        self.assertFalse(unit_path.exists())

    def test_autostart_refuses_without_desktop(self):
        from ariadex import companion as companion_mod

        adapter = deploy.SystemdUserAdapter()
        # Unsupported desktop reports manual, never pretends.
        with mock.patch.object(
            companion_mod,
            "detect_desktop",
            return_value=companion_mod.DesktopInfo("wayland", False, "no adapter"),
        ):
            result = adapter.install_autostart(["ariadex"])
        self.assertEqual(result.state, "manual")
        self.assertIn("wayland", result.detail)


class UnsupportedAdapterTest(unittest.TestCase):
    def test_platform_selection(self):
        with mock.patch.object(deploy.sys, "platform", "darwin"):
            adapter = deploy.adapter_for_platform()
            self.assertIsInstance(adapter, deploy.UnsupportedAdapter)
            result = adapter.install_unit(["ariadex"], Path("."))
            self.assertEqual(result.state, "blocked")
            self.assertIn("foreground", result.detail)
        with mock.patch.object(deploy.sys, "platform", "win32"):
            adapter = deploy.adapter_for_platform()
            self.assertIsInstance(adapter, deploy.UnsupportedAdapter)
        with mock.patch.object(deploy.sys, "platform", "linux"):
            self.assertIsInstance(
                deploy.adapter_for_platform(), deploy.SystemdUserAdapter
            )

    def test_unsupported_remove_is_absent(self):
        adapter = deploy.UnsupportedAdapter("nope")
        self.assertEqual(adapter.remove()[0].state, "absent")
        self.assertEqual(adapter.service_state().state, "blocked")


class InstallFlowTest(IsolatedHomeTest):
    def _adapter(self):
        return deploy.SystemdUserAdapter(runner=fake_systemctl_ok)

    def _patch_platform(self, test):
        which = mock.patch.object(deploy.shutil, "which", return_value="/bin/systemctl")
        which.start()
        test.addCleanup(which.stop)
        desktop = mock.patch(
            "ariadex.companion.detect_desktop",
            return_value=__import__(
                "ariadex.companion", fromlist=["DesktopInfo"]
            ).DesktopInfo("x11", True, "ok"),
        )
        desktop.start()
        test.addCleanup(desktop.stop)
        tk = mock.patch("ariadex.companion.tkinter_available", return_value=True)
        tk.start()
        test.addCleanup(tk.stop)

    def test_install_is_idempotent(self):
        self._patch_platform(self)
        first = deploy.install_project(self.root, adapter=self._adapter())
        self.assertTrue(all(a.state == "installed" for a in first.artifacts))
        second = deploy.install_project(self.root, adapter=self._adapter())
        self.assertEqual(second.artifacts[0].state, "already")

    def test_install_creates_executable_launchers(self):
        self._patch_platform(self)
        deploy.install_project(self.root, adapter=self._adapter())
        for name in (deploy.DAEMON_LAUNCHER_NAME, deploy.COMPANION_LAUNCHER_NAME):
            launcher = deploy.bin_home() / name
            self.assertTrue(launcher.is_file())
            mode = stat.S_IMODE(launcher.stat().st_mode)
            self.assertEqual(mode & 0o111, 0o111)
            self.assertIn("ariadex.cli", launcher.read_text(encoding="utf-8"))

    def test_install_refuses_without_project_config(self):
        with self.assertRaises(deploy.DeployError):
            deploy.install_project(
                Path(self.tmp.name) / "nobody", adapter=self._adapter()
            )

    def test_failed_service_registration_rolls_back(self):
        self._patch_platform(self)

        def failing(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 1, "", "refused")

        with self.assertRaises(deploy.DeployError) as ctx:
            deploy.install_project(
                self.root, adapter=deploy.SystemdUserAdapter(runner=failing)
            )
        self.assertIn("manifest", str(ctx.exception))
        # Launchers stay (owned, recorded); the unit is rolled back.
        self.assertTrue((deploy.bin_home() / deploy.DAEMON_LAUNCHER_NAME).exists())
        unit_path = deploy.config_home() / "systemd" / "user" / deploy.DAEMON_UNIT_NAME
        self.assertFalse(unit_path.exists())
        manifest = deploy.load_manifest()
        self.assertEqual(len(manifest["owned"]), 2)

    def test_generated_files_carry_no_secrets(self):
        self._patch_platform(self)
        marker = "ghp_testmarker12345"
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": marker}):
            deploy.install_project(self.root, adapter=self._adapter())
        haystacks = [deploy.manifest_path().read_text(encoding="utf-8")]
        for path_str in deploy.load_manifest()["owned"]:
            haystacks.append(Path(path_str).read_text(encoding="utf-8"))
        for hay in haystacks:
            self.assertNotIn(marker, hay)
            self.assertNotIn("GITHUB_TOKEN", hay)

    def test_uninstall_twice_second_is_noop(self):
        self._patch_platform(self)
        deploy.install_project(self.root, adapter=self._adapter())
        first = deploy.uninstall_project(adapter=self._adapter())
        states = {a.name: a.state for a in first.artifacts}
        self.assertEqual(states["artifacts"], "removed")
        for path_str in deploy.load_manifest().get("owned", []):
            self.assertFalse(Path(path_str).exists())
        second = deploy.uninstall_project(adapter=self._adapter())
        self.assertEqual(second.artifacts[0].state, "already")

    def test_uninstall_preserves_project_and_config(self):
        self._patch_platform(self)
        deploy.install_project(self.root, adapter=self._adapter())
        deploy.uninstall_project(adapter=self._adapter())
        self.assertTrue((self.root / ".ariadex" / "state.json").exists())
        self.assertTrue((self.root / ".ariadex" / "config.yaml").exists())

    def test_uninstall_purge_removes_user_config(self):
        self._patch_platform(self)
        from ariadex import companion as companion_mod

        companion_mod.save_user_config({"hotkey": "Alt+F9"})
        config_path = companion_mod.user_config_path()
        self.assertTrue(config_path.exists())
        deploy.install_project(self.root, adapter=self._adapter())
        deploy.uninstall_project(adapter=self._adapter(), purge_config=True)
        self.assertFalse(config_path.exists())


class CliDeployTest(IsolatedHomeTest):
    def _patch_platform(self, test):
        which = mock.patch.object(deploy.shutil, "which", return_value="/bin/systemctl")
        which.start()
        test.addCleanup(which.stop)
        fake = subprocess.CompletedProcess(["systemctl"], 0, "", "")
        runner = mock.patch.object(
            deploy.SystemdUserAdapter, "_systemctl", return_value=fake
        )
        runner.start()
        test.addCleanup(runner.stop)
        # Hermetic companion prerequisites: the CLI dependency step stays
        # covered by test_companion_dependencies; here Tkinter is present.
        desktop = mock.patch(
            "ariadex.companion.detect_desktop",
            return_value=__import__(
                "ariadex.companion", fromlist=["DesktopInfo"]
            ).DesktopInfo("x11", True, "ok"),
        )
        desktop.start()
        test.addCleanup(desktop.stop)
        tk = mock.patch("ariadex.companion.tkinter_available", return_value=True)
        tk.start()
        test.addCleanup(tk.stop)

    def test_install_cli_reports_plan_and_capabilities(self):
        self._patch_platform(self)
        code, out, _ = run_cli(self.root, "install", "--yes")
        self.assertEqual(code, 0)
        self.assertIn("plan: entry point:", out)
        self.assertIn("install:", out)
        self.assertIn("provider:", out)
        self.assertIn("tmux:", out)

    def test_install_cli_json_is_stable(self):
        self._patch_platform(self)
        code, out, _ = run_cli(self.root, "install", "--yes", "--json")
        self.assertEqual(code, 0)
        # Plan lines precede the JSON payload; parse from the first brace.
        payload = json.loads(out[out.index("{") :])
        self.assertEqual(payload["action"], "install")
        self.assertIn("artifacts", payload)
        self.assertIn("capabilities", payload)

    def test_uninstall_cli_and_admin_alias(self):
        self._patch_platform(self)
        code, _, _ = run_cli(self.root, "install", "--yes")
        self.assertEqual(code, 0)
        code, out, _ = run_cli(self.root, "admin", "uninstall", "--yes")
        self.assertEqual(code, 0)
        self.assertIn("uninstall:", out)
        code, _, _ = run_cli(self.root, "uninstall", "--yes")
        self.assertEqual(code, 0)

    def test_install_requires_project(self):
        empty = Path(self.tmp.name) / "nobody"
        empty.mkdir()
        code, _, err = run_cli(empty, "install", "--yes")
        self.assertNotEqual(code, 0)
        self.assertIn("error:", err)


class DoctorDeployTest(IsolatedHomeTest):
    def test_doctor_reports_package_launchers_ipc_service(self):
        checks, _ = operator.run_doctor(self.root)
        names = [c.name for c in checks]
        for expected in ("package", "launchers", "ipc", "service"):
            self.assertIn(expected, names)
        by_name = {c.name: c for c in checks}
        self.assertTrue(by_name["package"].ok)
        self.assertFalse(by_name["package"].required is False)
        # Not installed yet: launchers opt-in note, no socket, manual service.
        self.assertIn("not installed", by_name["launchers"].detail)
        self.assertIn("no daemon socket", by_name["ipc"].detail)

    def test_doctor_json_includes_deployment_checks(self):
        code, out, _ = run_cli(self.root, "doctor", "--json")
        _ = code  # exit depends on tmux presence; output is the contract
        payload = json.loads(out)
        names = [c["name"] for c in payload["checks"]]
        for expected in ("package", "launchers", "ipc", "service"):
            self.assertIn(expected, names)

    def test_ipc_flags_group_accessible_socket(self):
        from ariadex import daemon as daemon_mod

        sock = daemon_mod.socket_path(self.root)
        sock.write_text("fake", encoding="utf-8")
        os.chmod(sock, 0o640)
        try:
            checks, _ = operator.run_doctor(self.root)
            ipc = next(c for c in checks if c.name == "ipc")
            self.assertFalse(ipc.ok)
            self.assertIn("group/other-accessible", ipc.detail)
        finally:
            sock.unlink()


class CleanDirectorySmokeTest(IsolatedHomeTest):
    def test_start_status_stop_from_clean_directory(self):
        work = Path(self.tmp.name) / "clean"
        work.mkdir()
        init_project(work)
        code, out, _ = run_cli(work, "start")
        self.assertEqual(code, 0)
        try:
            code, out, _ = run_cli(work, "status")
            self.assertEqual(code, 0)
            self.assertIn("daemon:", out)
            code, _, _ = run_cli(work, "stop")
            self.assertEqual(code, 0)
        finally:
            run_cli(work, "stop")


if __name__ == "__main__":
    unittest.main()
