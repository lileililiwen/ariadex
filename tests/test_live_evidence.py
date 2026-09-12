"""Tests for the opt-in live evidence harness.

All live-tmux paths are skipped-or-blocked when tmux is absent; the
install fixture is fully mocked so no host package manager ever runs.
"""

import io
import os
import stat
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ariadex import cli, live_evidence
from ariadex.live_evidence import (
    BLOCKED,
    PASSED,
    SKIPPED,
    format_report,
    gate_exit_code,
    isolated_tmux_session,
    run_all,
    scenario_install_fixture,
    scenario_provider_smoke,
    scenario_tmux_lifecycle,
    temp_project,
    unique_session_name,
    write_fake_provider,
)


class FixtureTest(unittest.TestCase):
    def test_session_names_unique(self):
        self.assertNotEqual(unique_session_name(), unique_session_name())

    def test_temp_project_cleanup_on_failure(self):
        captured = []
        try:
            with temp_project() as root:
                captured.append(str(root))
                self.assertTrue((root / ".ariadex").is_dir())
                raise RuntimeError("probe failure")
        except RuntimeError:
            pass
        self.assertFalse(Path(captured[0]).exists())

    def test_fake_provider_executable_and_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = write_fake_provider(tmp)
            self.assertTrue(os.access(fake, os.X_OK))
            text = fake.read_text(encoding="utf-8")
            self.assertIn("fake-echo", text)
            self.assertNotIn("http", text.lower())

    def test_isolated_session_always_terminates(self):
        from ariadex.terminal import FakeTerminalDriver

        driver = FakeTerminalDriver()
        name = unique_session_name("cleanup")
        with self.assertRaises(RuntimeError):
            with isolated_tmux_session(driver, name, "/tmp", ["fake"]):
                self.assertTrue(driver.session_alive(name))
                raise RuntimeError("boom")
        self.assertFalse(driver.session_alive(name))


class ClassificationTest(unittest.TestCase):
    def test_tmux_missing_is_skipped_with_prerequisite(self):
        with mock.patch("shutil.which", return_value=None):
            result = scenario_tmux_lifecycle(timeout_s=1)
        self.assertEqual(result.status, SKIPPED)
        self.assertIn("tmux", result.reason)
        self.assertIn("PATH", result.reason + result.diagnostics)

    def test_gate_requires_all_passed(self):
        ok = [live_evidence.EvidenceResult("a", PASSED, "fine")]
        mixed = ok + [live_evidence.EvidenceResult("b", SKIPPED, "no tmux")]
        self.assertEqual(gate_exit_code(ok), 0)
        self.assertNotEqual(gate_exit_code(mixed), 0)

    def test_report_never_calls_skipped_passing(self):
        results = [
            live_evidence.EvidenceResult("a", PASSED, "fine"),
            live_evidence.EvidenceResult("b", SKIPPED, "no tmux"),
        ]
        report = format_report(results)
        self.assertIn("1 passed, 1 skipped, 0 blocked", report)
        self.assertIn("not passing evidence", report)

    def test_run_all_classifies_harness_errors(self):
        with mock.patch.object(
            live_evidence, "SCENARIOS",
            [("boom", lambda **_: (_ for _ in ()).throw(RuntimeError("x")))],
        ):
            results = run_all()
        self.assertEqual(results[0].status, BLOCKED)

    def test_provider_smoke_skips_without_binaries(self):
        with mock.patch("shutil.which", return_value=None):
            result = scenario_provider_smoke(timeout_s=1)
        self.assertEqual(result.status, SKIPPED)


class ScenarioTest(unittest.TestCase):
    def test_provider_startup_passes_on_fake_driver(self):
        result = live_evidence.scenario_provider_startup()
        self.assertEqual(result.status, PASSED)

    def test_continuity_restart_passes(self):
        result = live_evidence.scenario_continuity_restart()
        self.assertEqual(result.status, PASSED)

    def test_verification_gating_passes(self):
        result = live_evidence.scenario_verification_gating()
        self.assertEqual(result.status, PASSED)

    def test_takeover_resync_passes(self):
        result = live_evidence.scenario_takeover_resync()
        self.assertEqual(result.status, PASSED)

    def test_install_fixture_never_touches_host(self):
        with mock.patch("subprocess.run") as run:
            result = scenario_install_fixture()
            run.assert_not_called()  # module patches its own subprocess ref
        self.assertEqual(result.status, PASSED)


class ProvisionTest(unittest.TestCase):
    def test_provision_installs_only_when_missing(self):
        from ariadex import tmux_setup
        with mock.patch.object(tmux_setup, "find_tmux", return_value="/usr/bin/tmux"):
            with mock.patch.object(tmux_setup, "ensure_tmux") as ensure:
                path, note = live_evidence.provision_tmux()
        self.assertEqual(path, "/usr/bin/tmux")
        self.assertEqual(note, "")
        ensure.assert_not_called()

    def test_provision_marks_provisional_install(self):
        from ariadex import tmux_setup
        with mock.patch.object(tmux_setup, "find_tmux", return_value=None):
            with mock.patch.object(
                tmux_setup, "ensure_tmux", return_value="/usr/bin/tmux",
            ):
                path, note = live_evidence.provision_tmux()
        self.assertEqual(note, "provisioned")

    def test_unprovision_never_touches_preexisting_tmux(self):
        from ariadex import tmux_setup
        with mock.patch.object(tmux_setup, "uninstall_tmux") as uninstall:
            self.assertEqual(live_evidence.unprovision_tmux(False), "")
        uninstall.assert_not_called()

    def test_unprovision_removes_only_provisional_tmux(self):
        from ariadex import tmux_setup
        with mock.patch.object(
            tmux_setup, "uninstall_tmux", return_value="apt-get",
        ):
            with mock.patch.object(tmux_setup, "find_tmux", return_value=None):
                note = live_evidence.unprovision_tmux(True)
        self.assertIn("removed via apt-get", note)

    def test_unprovision_failure_is_warning_not_crash(self):
        from ariadex import tmux_setup
        with mock.patch.object(
            tmux_setup, "uninstall_tmux",
            side_effect=tmux_setup.TmuxSetupError("dpkg locked"),
        ):
            note = live_evidence.unprovision_tmux(True)
        self.assertIn("warning", note)

    def test_failed_provision_blocks_live_scenario_honestly(self):
        from ariadex import tmux_setup
        with mock.patch.object(
            live_evidence, "provision_tmux",
            side_effect=tmux_setup.TmuxSetupError("no passwordless sudo"),
        ):
            results = run_all(only=["tmux-lifecycle"], provision=True)
        by_name = {r.name: r for r in results}
        self.assertEqual(by_name["tmux-lifecycle"].status, BLOCKED)
        self.assertIn("provisioning failed", by_name["tmux-lifecycle"].reason)

    def test_provision_roundtrip_recorded_as_evidence(self):
        with mock.patch.object(
            live_evidence, "provision_tmux", return_value=("/usr/bin/tmux", "provisioned"),
        ):
            with mock.patch.object(
                live_evidence, "unprovision_tmux", return_value="provisional tmux removed",
            ):
                results = run_all(only=["provider-startup"], provision=True)
        by_name = {r.name: r for r in results}
        # tmux-lifecycle not requested, so no provisioning attempted at all
        self.assertNotIn("tmux-provision", by_name)
        self.assertEqual(by_name["provider-startup"].status, PASSED)

    def test_remove_command_per_manager(self):
        from ariadex import tmux_setup
        with mock.patch.object(tmux_setup, "needs_sudo", return_value=False):
            self.assertEqual(
                tmux_setup.remove_command("apt-get"),
                ["apt-get", "remove", "-y", "tmux"],
            )
            self.assertEqual(
                tmux_setup.remove_command("brew"), ["brew", "uninstall", "tmux"],
            )
        with self.assertRaises(tmux_setup.TmuxSetupError):
            tmux_setup.remove_command("choco")

    def test_uninstall_uses_detected_manager(self):
        from subprocess import CompletedProcess
        from ariadex import tmux_setup
        with mock.patch.object(tmux_setup.shutil, "which",
                               side_effect=lambda n: "/usr/bin/apt-get" if n == "apt-get" else None):
            with mock.patch.object(tmux_setup, "needs_sudo", return_value=True):
                # no sudo binary -> no sudo prefix
                with mock.patch.object(
                    tmux_setup.subprocess, "run",
                    return_value=CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
                ) as run:
                    self.assertEqual(tmux_setup.uninstall_tmux(), "apt-get")
        self.assertEqual(run.call_args.args[0], ["apt-get", "remove", "-y", "tmux"])


class LocalTmuxTest(unittest.TestCase):
    def test_resolve_explicit_missing_binary_is_blocked(self):
        result = live_evidence.scenario_tmux_lifecycle(
            timeout_s=1, executable="/nonexistent/tmux")
        self.assertEqual(result.status, BLOCKED)
        self.assertIn("unusable", result.reason)

    def test_resolve_explicit_binary_used_when_present(self):
        from ariadex import tmux_setup
        with tempfile.TemporaryDirectory() as tmp:
            fake_bin = Path(tmp) / "tmux"
            fake_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_bin.chmod(0o755)
            with mock.patch.object(
                tmux_setup, "find_tmux", return_value=None,
            ):
                path, note = live_evidence.resolve_tmux(str(fake_bin))
        self.assertEqual(path, str(fake_bin))
        self.assertEqual(note, "")

    def test_local_fetch_failure_blocks_honestly(self):
        from ariadex import tmux_setup
        with mock.patch.object(
            tmux_setup, "fetch_local_tmux",
            side_effect=tmux_setup.TmuxSetupError("no apt here"),
        ):
            results = run_all(only=["tmux-lifecycle"], local_tmux=True)
        by_name = {r.name: r for r in results}
        self.assertEqual(by_name["tmux-lifecycle"].status, BLOCKED)
        self.assertIn("fetch failed", by_name["tmux-lifecycle"].reason)

    def test_local_tmux_tempdir_removed_after_run(self):
        from ariadex import tmux_setup
        seen = {}

        def fake_fetch(dest):
            seen["dest"] = str(dest)
            wrapper = Path(dest) / "bin" / "tmux"
            wrapper.parent.mkdir(parents=True, exist_ok=True)
            wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            wrapper.chmod(0o755)
            return wrapper

        fake_result = live_evidence.EvidenceResult(
            "tmux-lifecycle", PASSED, "mocked live pass")
        patched = tuple(
            (n, (lambda **kw: fake_result) if n == "tmux-lifecycle" else f)
            for n, f in live_evidence.SCENARIOS
        )
        with mock.patch.object(tmux_setup, "fetch_local_tmux",
                               side_effect=fake_fetch):
            with mock.patch.object(live_evidence, "SCENARIOS", patched):
                results = run_all(only=["tmux-lifecycle"], local_tmux=True)
        self.assertFalse(Path(seen["dest"]).exists())  # unpath == uninstall
        by_name = {r.name: r for r in results}
        self.assertEqual(by_name["tmux-lifecycle"].status, PASSED)
        self.assertEqual(by_name["tmux-provision"].status, PASSED)

    def test_read_depends_parses_names(self):
        from subprocess import CompletedProcess
        from ariadex import tmux_setup
        out = "tmux\n  Depends: libc6\n  Depends: libutempter0\n  PreDepends: x\n"
        with mock.patch.object(
            tmux_setup.subprocess, "run",
            return_value=CompletedProcess(args=[], returncode=0,
                                          stdout=out, stderr=""),
        ):
            self.assertEqual(tmux_setup.read_depends("tmux"),
                             ["libc6", "libutempter0"])

    def test_missing_libs_parsing(self):
        from subprocess import CompletedProcess
        from ariadex import tmux_setup
        out = ("\tlibutempter.so.0 => not found\n"
               "\tlibc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x123)\n")
        with mock.patch.object(
            tmux_setup.subprocess, "run",
            return_value=CompletedProcess(args=[], returncode=0,
                                          stdout=out, stderr=""),
        ) as run:
            self.assertEqual(tmux_setup.missing_shared_libs("/bin/x"),
                             ["libutempter.so.0"])
        self.assertIn("ldd", run.call_args.args[0])

    def test_wrapper_executes_with_lib_path(self):
        import subprocess as sp
        from ariadex import tmux_setup
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "real"
            target.write_text("#!/bin/sh\necho LIB=$LD_LIBRARY_PATH\n",
                              encoding="utf-8")
            target.chmod(0o755)
            libdir = Path(tmp) / "lib"
            libdir.mkdir()
            wrapper = tmux_setup.write_tmux_wrapper(
                Path(tmp) / "bin" / "tmux", target, [libdir])
            proc = sp.run([str(wrapper)], capture_output=True, text=True,
                          timeout=30)
        self.assertEqual(proc.returncode, 0)
        self.assertIn(str(libdir), proc.stdout)


def run_cli(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with chdir(root), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


class EvidenceCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        run_cli(self.root, "init")

    def test_evidence_reports_without_scheduling(self):
        code, out, _ = run_cli(self.root, "evidence", "--only",
                               "provider-startup,takeover-resync")
        self.assertEqual(code, 0)
        self.assertIn("provider-startup: passed", out)
        self.assertIn("takeover-resync: passed", out)
        self.assertIn("summary:", out)

    def test_evidence_gate_fails_on_skipped_tmux(self):
        with mock.patch("shutil.which", return_value=None):
            code, out, _ = run_cli(self.root, "evidence", "--gate", "--only",
                                   "tmux-lifecycle")
        self.assertNotEqual(code, 0)
        self.assertIn("skipped", out)

    def test_evidence_provision_flag_reaches_runner(self):
        with mock.patch.object(
            live_evidence, "run_all", return_value=[],
        ) as run_all_mock:
            code, _, _ = run_cli(self.root, "evidence", "--provision", "--only",
                                 "provider-startup")
        self.assertEqual(code, 0)
        self.assertTrue(run_all_mock.call_args.kwargs["provision"])

    def test_tmux_bin_flag_reaches_runner(self):
        with mock.patch.object(
            live_evidence, "run_all", return_value=[],
        ) as run_all_mock:
            code, _, _ = run_cli(self.root, "evidence", "--tmux-bin",
                                 "/tmp/custom/tmux", "--only", "tmux-lifecycle")
        self.assertEqual(code, 0)
        self.assertEqual(run_all_mock.call_args.kwargs["tmux_bin"],
                         "/tmp/custom/tmux")

    def test_other_commands_still_work(self):
        code, _, _ = run_cli(self.root, "status")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
