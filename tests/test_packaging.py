"""Packaging and distribution contract tests (stdlib only).

Covers `packaging-and-distribution`: installable metadata, single-source
version, console entry point, and honest missing-prerequisite reporting.
"""

from __future__ import annotations

import contextlib
import io
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ariadex
from ariadex import cli as cli_mod
from ariadex import providers as providers_mod
from ariadex.adapters import UnsupportedOperation

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 is unsupported; fail loudly.
    tomllib = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


class PackagingMetadataTests(unittest.TestCase):
    def test_version_is_single_source_semver(self):
        self.assertTrue(
            SEMVER.match(ariadex.__version__),
            f"__version__ `{ariadex.__version__}` is not X.Y.Z",
        )

    def test_pyproject_declares_package_and_entry_point(self):
        if tomllib is None:
            self.fail("tomllib is required (Python >= 3.11)")
        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
        project = data["project"]
        self.assertEqual(project["name"], "ariadex")
        self.assertIn("version", data["tool"]["setuptools"]["dynamic"])
        self.assertNotIn("version", project, "version must be dynamic (single source)")
        self.assertEqual(project["scripts"], {"ariadex": "ariadex.cli:main"})
        self.assertIn("PyYAML", " ".join(project["dependencies"]))
        requires = project["requires-python"]
        self.assertIn("3.11", requires)

    def test_version_flag_reports_package_version(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as ctx:
            cli_mod.build_parser().parse_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)

    def test_version_flag_output_matches_single_source(self):
        proc = subprocess.run(
            [sys.executable, "-m", "ariadex", "--version"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "src"},
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn(ariadex.__version__, proc.stdout)

    def test_version_flag_carries_commit_identity(self):
        from ariadex import upgrade as upgrade_mod

        with mock.patch.object(
            upgrade_mod, "describe_build", return_value="0.1.0+gabc1234-dirty"
        ):
            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                self.assertRaises(SystemExit) as ctx,
            ):
                cli_mod.build_parser().parse_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("ariadex 0.1.0+gabc1234-dirty", stdout.getvalue())

    def test_version_probe_is_lazy(self):
        from ariadex import upgrade as upgrade_mod

        with mock.patch.object(
            upgrade_mod, "describe_build", side_effect=AssertionError("probed")
        ):
            cli_mod.build_parser().parse_args(["init"])

    def test_governance_files_present(self):
        for name in ("LICENSE", "CHANGELOG.md", "SECURITY.md", "pyproject.toml"):
            self.assertTrue(
                (REPO_ROOT / name).is_file(), f"`{name}` must ship with the project"
            )
        changelog = (REPO_ROOT / "CHANGELOG.md").read_text()
        self.assertIn(ariadex.__version__, changelog)


class MissingPrerequisiteTests(unittest.TestCase):
    def test_unsupported_provider_reports_without_claiming_work(self):
        with self.assertRaises(UnsupportedOperation) as ctx:
            providers_mod.get_adapter("no-such-provider", None, "s", Path("."))
        message = str(ctx.exception)
        self.assertIn("unsupported agent provider", message)
        self.assertIn("opencode", message)
        self.assertIn("codex", message)

    def test_run_outside_project_fails_without_claiming_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, "-m", "ariadex", "run"],
                capture_output=True,
                text=True,
                cwd=tmp,
                env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO_ROOT / "src")},
            )
        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertIn("error:", combined)
        self.assertNotIn("complet", combined.lower())


if __name__ == "__main__":
    unittest.main()
