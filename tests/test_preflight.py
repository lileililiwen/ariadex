"""Unit tests for the release evidence preflight report."""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from ariadex import preflight
from ariadex.preflight import (
    ToolStatus,
    collect,
    format_report,
    main,
    probe_cli_tool,
    probe_dist_tool,
    probe_tmux,
)


class ProbeTest(unittest.TestCase):
    def test_missing_cli_is_missing_with_hint(self):
        with mock.patch("shutil.which", return_value=None):
            status = probe_cli_tool("opencode", "install hint")
        self.assertFalse(status.present)
        self.assertIn("install hint", status.detail)

    def test_present_cli_reports_path_and_version(self):
        with (
            mock.patch("shutil.which", return_value="/usr/bin/opencode"),
            mock.patch.object(preflight, "_run_version", return_value="1.2.3"),
        ):
            status = probe_cli_tool("opencode", "hint")
        self.assertTrue(status.present)
        self.assertEqual(status.path, "/usr/bin/opencode")
        self.assertEqual(status.version, "1.2.3")

    def test_missing_dist_tool_names_consequence(self):
        from importlib.metadata import PackageNotFoundError

        with (
            mock.patch("shutil.which", return_value=None),
            mock.patch.object(
                preflight.importlib_metadata,
                "version",
                side_effect=PackageNotFoundError,
            ),
        ):
            status = probe_dist_tool("pip-audit", "pip-audit", "cannot be claimed")
        self.assertFalse(status.present)
        self.assertIn("cannot be claimed", status.detail)

    def test_explicit_tmux_bin_resolves_absolute(self):
        status = probe_tmux("/bin/sh")
        self.assertTrue(status.present)
        self.assertTrue(status.path.startswith("/"))
        self.assertIn("no install", status.detail)

    def test_explicit_tmux_bin_absent_is_missing(self):
        status = probe_tmux("/nonexistent/tmux-xyz")
        self.assertFalse(status.present)
        self.assertIn("--tmux-bin", status.detail)

    def test_path_tmux_absent_suggests_modes(self):
        with mock.patch("shutil.which", return_value=None):
            status = probe_tmux(None)
        self.assertFalse(status.present)
        self.assertIn("--local-tmux", status.detail)


class ReportTest(unittest.TestCase):
    def test_missing_rows_never_read_as_passed(self):
        report = format_report(
            [
                ToolStatus("python", True, "/usr/bin/python3", "3.12"),
                ToolStatus("pip-audit", False, detail="not installed"),
            ]
        )
        self.assertIn("MISSING", report)
        self.assertNotIn("pip-audit: present", report)
        self.assertNotIn("passed", report)

    def test_collect_covers_every_toolchain_row(self):
        names = [status.name for status in collect()]
        self.assertEqual(
            names,
            [
                "python",
                "ariadex-package",
                "pip-audit",
                "build",
                "opencode",
                "codex",
                "tmux",
            ],
        )

    def test_local_python_is_always_present(self):
        by_name = {status.name: status for status in collect()}
        self.assertTrue(by_name["python"].present)
        self.assertTrue(by_name["python"].version)

    def test_main_prints_report_and_exits_zero(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main([]), 0)
        self.assertIn("preflight toolchain report:", out.getvalue())

    def test_main_passes_tmux_bin_through(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["--tmux-bin", "/bin/sh"]), 0)
        self.assertIn("no install or removal", out.getvalue())


if __name__ == "__main__":
    unittest.main()
