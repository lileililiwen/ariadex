"""Tests for unified prerequisite coordination (managed-start readiness)."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from ariadex.prerequisites import (
    CoordinatorReport,
    PrerequisiteResult,
    check_provider,
    check_runtime,
    check_tmux,
    check_widget,
    coordinate,
    format_report,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def ready_probes(**overrides):
    """All-present probe set; individual checks overridden per test."""
    from ariadex import companion as companion_mod

    params = {
        "version_info": (3, 12, 0),
        "yaml_available": True,
        "which": lambda name: f"/usr/bin/{name}",
        "find_tmux": lambda *args: "/usr/bin/tmux",
        "detect_manager": lambda: "apt-get",
        "ensure_tmux": mock.Mock(return_value="/usr/bin/tmux"),
        "widget_prerequisites": lambda: {
            "tkinter_available": True,
            "desktop": companion_mod.DesktopInfo("x11", True, "x11"),
            "hotkey": "Ctrl+Esc",
            "hotkey_ok": True,
        },
        "prepare_widget": mock.Mock(),
    }
    params.update(overrides)
    return params


def coordinate_ready(**overrides):
    return coordinate("opencode", **ready_probes(**overrides))


class RuntimeCheckTest(unittest.TestCase):
    def test_supported_runtime_is_present(self):
        result = check_runtime(version_info=(3, 11, 0), yaml_available=True)
        self.assertEqual(result.state, "present")
        self.assertTrue(result.ready)

    def test_old_python_blocks_with_recovery(self):
        result = check_runtime(version_info=(3, 10, 0), yaml_available=True)
        self.assertEqual(result.state, "blocked")
        self.assertIn("3.11", result.detail)
        self.assertIn("pyyaml", result.recovery.lower())

    def test_missing_yaml_blocks(self):
        result = check_runtime(version_info=(3, 12, 0), yaml_available=False)
        self.assertEqual(result.state, "blocked")
        self.assertTrue(result.recovery)

    def test_default_probes_use_live_interpreter(self):
        result = check_runtime()
        self.assertEqual(result.state, "present")

    def test_unimportable_yaml_blocks(self):
        with mock.patch.dict(sys.modules, {"yaml": None}):
            result = check_runtime()
        self.assertEqual(result.state, "blocked")


class ProviderCheckTest(unittest.TestCase):
    def test_present_provider_is_silent_and_path_free(self):
        result = check_provider("codex", which=lambda name: "/usr/bin/codex")
        self.assertEqual(result.state, "present")
        self.assertNotIn("/usr/bin", result.detail + result.recovery)

    def test_missing_provider_blocks_with_guidance_and_no_install(self):
        calls = []
        result = check_provider(
            "opencode", which=lambda name: calls.append(name) or None
        )
        self.assertEqual(result.state, "blocked")
        self.assertIn("opencode", result.recovery)
        self.assertEqual(calls, ["opencode"])

    def test_unknown_provider_blocks_with_supported_list(self):
        result = check_provider("wat", which=lambda name: None)
        self.assertEqual(result.state, "blocked")
        self.assertIn("opencode", result.detail)


class TmuxCheckTest(unittest.TestCase):
    def test_present_tmux_needs_no_runner(self):
        runner = mock.Mock(side_effect=AssertionError("must not install"))
        result = check_tmux(find=lambda: "/bin/tmux", ensure=runner)
        self.assertEqual(result.state, "present")
        runner.assert_not_called()

    def test_missing_tmux_declined_without_install(self):
        installer = mock.Mock(side_effect=AssertionError("must not install"))
        result = check_tmux(allow_install=False, find=lambda: None, ensure=installer)
        self.assertEqual(result.state, "declined")
        self.assertIn("tmux", result.recovery)
        installer.assert_not_called()

    def test_missing_manager_is_unsupported(self):
        installer = mock.Mock(side_effect=AssertionError("must not install"))
        result = check_tmux(
            find=lambda: None, detect_manager=lambda: None, ensure=installer
        )
        self.assertEqual(result.state, "unsupported")
        installer.assert_not_called()

    def test_successful_install_verifies_and_reports_installed(self):
        seen = {"found": False}

        def find():
            return "/usr/bin/tmux" if seen["found"] else None

        def ensure(**kwargs):
            seen["found"] = True
            return "/usr/bin/tmux"

        result = check_tmux(find=find, ensure=ensure)
        self.assertEqual(result.state, "installed")

    def test_failed_install_blocks_with_package_and_hint(self):
        from ariadex import tmux_setup as tmux_setup_mod

        def ensure(**kwargs):
            raise tmux_setup_mod.TmuxSetupError("boom")

        result = check_tmux(
            find=lambda: None, detect_manager=lambda: "apt-get", ensure=ensure
        )
        self.assertEqual(result.state, "blocked")
        self.assertIn("tmux", result.recovery)
        self.assertNotIn("sudo", result.detail)

    def test_install_success_without_probe_blocks(self):
        from ariadex import tmux_setup as tmux_setup_mod

        def ensure(**kwargs):
            return "/usr/bin/tmux"  # claims success; probe still misses

        with mock.patch.object(tmux_setup_mod, "find_tmux", return_value=None):
            result = check_tmux(
                find=lambda: None,
                detect_manager=lambda: "apt-get",
                ensure=ensure,
            )
        self.assertEqual(result.state, "blocked")

    def test_interactive_flag_reaches_installer(self):
        seen = {}
        state = {"found": False}

        def find():
            return "/usr/bin/tmux" if state["found"] else None

        def ensure(**kwargs):
            seen.update(kwargs)
            state["found"] = True
            return "/usr/bin/tmux"

        result = check_tmux(
            find=find,
            detect_manager=lambda: "apt-get",
            ensure=ensure,
            interactive=True,
        )
        self.assertEqual(result.state, "installed")
        self.assertTrue(seen.get("interactive_sudo"))

    def test_noninteractive_installer_gets_no_sudo_prompt(self):
        from ariadex import tmux_setup as tmux_setup_mod

        argv = tmux_setup_mod.install_command("apt-get")
        self.assertIn("-n", argv)


class InteractiveSudoTest(unittest.TestCase):
    def test_interactive_tmux_argv_has_no_passwordless_flag(self):
        from ariadex import tmux_setup as tmux_setup_mod

        argv = tmux_setup_mod.install_command("apt-get", interactive_sudo=True)
        self.assertNotIn("-n", argv)
        self.assertIn("tmux", argv)

    def test_interactive_run_inherits_terminal(self):
        from ariadex import tmux_setup as tmux_setup_mod

        calls = {}

        def runner(cmd, **kwargs):
            calls.update(kwargs)

            class Proc:
                returncode = 0
                stdout = ""
                stderr = ""

            return Proc()

        with (
            mock.patch.object(tmux_setup_mod, "find_tmux", return_value="/bin/tmux"),
        ):
            tmux_setup_mod.ensure_tmux(interactive_sudo=True, runner=runner)
        self.assertFalse(calls.get("capture_output"))

    def test_noninteractive_run_stays_captured(self):
        from ariadex import tmux_setup as tmux_setup_mod

        calls = {}

        def runner(cmd, **kwargs):
            calls.update(kwargs)

            class Proc:
                returncode = 0
                stdout = ""
                stderr = ""

            return Proc()

        with (
            mock.patch.object(
                tmux_setup_mod, "find_tmux", side_effect=[None, "/bin/tmux"]
            ),
            mock.patch.object(tmux_setup_mod, "detect_manager", return_value="brew"),
        ):
            tmux_setup_mod.ensure_tmux(runner=runner)
        self.assertTrue(calls.get("capture_output"))


class WidgetCheckTest(unittest.TestCase):
    def test_ready_widget_is_present(self):
        from ariadex import companion as companion_mod

        result = check_widget(
            prerequisites=lambda: {
                "tkinter_available": True,
                "desktop": companion_mod.DesktopInfo("x11", True, "x11"),
                "hotkey": "Ctrl+Esc",
                "hotkey_ok": True,
            },
            prepare=mock.Mock(side_effect=AssertionError("must not install")),
        )
        self.assertEqual(result.state, "present")

    def test_unsupported_desktop_never_claims_widget(self):
        from ariadex import companion as companion_mod

        result = check_widget(
            prerequisites=lambda: {
                "tkinter_available": False,
                "desktop": companion_mod.DesktopInfo("wayland", False, "wayland"),
                "hotkey": "Ctrl+Esc",
                "hotkey_ok": True,
            },
            prepare=mock.Mock(side_effect=AssertionError("must not install")),
        )
        self.assertEqual(result.state, "unsupported")
        self.assertIn("pause", result.recovery)

    def test_missing_tkinter_declined_without_confirmation(self):
        from ariadex import companion as companion_mod

        prepare = mock.Mock(side_effect=AssertionError("must not install"))
        result = check_widget(
            confirmed=False,
            prerequisites=lambda: {
                "tkinter_available": False,
                "desktop": companion_mod.DesktopInfo("x11", True, "x11"),
                "hotkey": "Ctrl+Esc",
                "hotkey_ok": True,
            },
            prepare=prepare,
        )
        self.assertEqual(result.state, "declined")
        prepare.assert_not_called()

    def test_confirmed_tkinter_install_verifies(self):
        from ariadex import companion as companion_mod
        from ariadex import deploy as deploy_mod

        outcome = deploy_mod.ArtifactResult("companion-dependencies", "installed", "ok")
        with mock.patch.object(companion_mod, "tkinter_available", return_value=True):
            result = check_widget(
                confirmed=True,
                prerequisites=lambda: {
                    "tkinter_available": False,
                    "desktop": companion_mod.DesktopInfo("x11", True, "x11"),
                    "hotkey": "Ctrl+Esc",
                    "hotkey_ok": True,
                },
                prepare=mock.Mock(return_value=outcome),
            )
        self.assertEqual(result.state, "installed")

    def test_failed_tkinter_install_blocks(self):
        from ariadex import companion as companion_mod
        from ariadex import deploy as deploy_mod

        outcome = deploy_mod.ArtifactResult(
            "companion-dependencies", "blocked", "no root"
        )
        result = check_widget(
            confirmed=True,
            prerequisites=lambda: {
                "tkinter_available": False,
                "desktop": companion_mod.DesktopInfo("x11", True, "x11"),
                "hotkey": "Ctrl+Esc",
                "hotkey_ok": True,
            },
            prepare=mock.Mock(return_value=outcome),
        )
        self.assertEqual(result.state, "blocked")
        self.assertTrue(result.recovery)

    def test_default_probes_never_mutate_without_confirmation(self):
        # Live desktop/Tkinter probes; unconfirmed, so no host mutation.
        result = check_widget()
        self.assertIn(result.state, ("present", "unsupported", "declined"))

    def test_display_unavailable_does_not_claim_widget_ready(self):
        from ariadex import companion as companion_mod

        result = check_widget(
            prerequisites=lambda: {
                "tkinter_available": True,
                "display_available": False,
                "desktop": companion_mod.DesktopInfo("x11", True, "x11"),
                "hotkey": "Ctrl+Esc",
                "hotkey_ok": True,
            },
        )
        self.assertEqual(result.state, "unsupported")
        self.assertIn("display", result.detail.lower())


class CoordinateTest(unittest.TestCase):
    def test_ready_host_is_silent_with_no_mutation(self):
        installer = mock.Mock(side_effect=AssertionError("must not install"))
        preparer = mock.Mock(side_effect=AssertionError("must not prepare"))
        out = io.StringIO()
        with redirect_stdout(out):
            report = coordinate(
                "opencode",
                **ready_probes(ensure_tmux=installer, prepare_widget=preparer),
            )
        self.assertTrue(report.ready)
        self.assertEqual(out.getvalue(), "")
        installer.assert_not_called()
        preparer.assert_not_called()
        self.assertEqual(
            [r.name for r in report.results],
            ["runtime", "provider", "tmux", "widget"],
        )

    def test_first_failure_stops_later_preparation(self):
        installer = mock.Mock(side_effect=AssertionError("must not install"))
        report = coordinate(
            "opencode",
            **ready_probes(which=lambda name: None, ensure_tmux=installer),
        )
        self.assertFalse(report.ready)
        self.assertEqual([r.name for r in report.results], ["runtime", "provider"])
        installer.assert_not_called()

    def test_runtime_failure_reports_first(self):
        report = coordinate_ready(yaml_available=False)
        self.assertFalse(report.ready)
        self.assertEqual(report.results[0].name, "runtime")

    def test_optional_widget_does_not_block(self):
        from ariadex import companion as companion_mod

        report = coordinate_ready(
            widget_prerequisites=lambda: {
                "tkinter_available": False,
                "desktop": companion_mod.DesktopInfo("headless", False, "headless"),
                "hotkey": "Ctrl+Esc",
                "hotkey_ok": True,
            },
        )
        self.assertTrue(report.ready)
        self.assertEqual(report.results[-1].state, "unsupported")

    def test_required_widget_blocks(self):
        from ariadex import companion as companion_mod

        report = coordinate(
            "opencode",
            require_widget=True,
            **ready_probes(
                widget_prerequisites=lambda: {
                    "tkinter_available": False,
                    "desktop": companion_mod.DesktopInfo("headless", False, "headless"),
                    "hotkey": "Ctrl+Esc",
                    "hotkey_ok": True,
                },
            ),
        )
        self.assertFalse(report.ready)

    def test_tmux_decline_stops_before_widget(self):
        preparer = mock.Mock(side_effect=AssertionError("must not prepare"))
        report = coordinate(
            "opencode",
            allow_install=False,
            **ready_probes(find_tmux=lambda *args: None, prepare_widget=preparer),
        )
        self.assertFalse(report.ready)
        self.assertEqual(report.results[-1].name, "tmux")
        preparer.assert_not_called()

    def test_report_serializes(self):
        report = coordinate_ready()
        payload = report.to_dict()
        self.assertTrue(payload["ready"])
        self.assertEqual(len(payload["results"]), 4)

    def test_format_hides_internals_on_success(self):
        text = format_report(coordinate_ready())
        self.assertIn("ready: yes", text)
        self.assertNotIn("sudo", text)
        self.assertNotIn("/usr/bin", text)

    def test_format_names_prerequisite_and_recovery_on_failure(self):
        report = coordinate_ready(which=lambda name: None)
        text = format_report(report)
        self.assertIn("ready: no", text)
        self.assertIn("provider", text)
        self.assertIn("recovery:", text)

    def test_format_omits_missing_recovery_line(self):
        report = CoordinatorReport(
            results=[PrerequisiteResult(name="tmux", state="blocked", detail="down")],
            ready=False,
        )
        text = format_report(report)
        self.assertIn("tmux: blocked", text)
        self.assertNotIn("recovery:", text)

    def test_boundaries_stay_explicit(self):
        source = (REPO_ROOT / "src" / "ariadex" / "prerequisites.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("dev_setup", source)
        self.assertNotIn("install_uv", source)
        for token in ("opencode [project]", "codex [project]", "/new"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
