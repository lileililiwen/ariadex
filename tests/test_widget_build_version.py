"""Widget build identity with git commit (widget-build-version).

The daemon status view reports the running build identity (same
`describe_build()` helper `-V` uses); the widget version row prefers
it and matches `-V` output shape. Drift comparison stays on bare
versions, so the commit suffix never reports false drift.
"""

import tempfile
import unittest
from pathlib import Path

from ariadex import companion as companion_mod
from ariadex import status as status_mod
from ariadex import upgrade as upgrade_mod


class BuildSnapshotTest(unittest.TestCase):
    def test_snapshot_carries_build_identity(self) -> None:
        snap = upgrade_mod.version_snapshot()
        self.assertIn("build", snap)
        self.assertTrue(snap["build"].startswith(upgrade_mod.running_version()))

    def test_build_suffix_never_counts_as_drift(self) -> None:
        snap = upgrade_mod.version_snapshot(running="0.1.0", installed="0.1.0")
        self.assertFalse(snap["drift"])

    def test_daemon_status_view_carries_build_version(self) -> None:
        from ariadex import daemon as daemon_mod

        with tempfile.TemporaryDirectory() as tmp:
            view = daemon_mod.daemon_status_view(Path(tmp))
        self.assertIn("build_version", view)
        self.assertTrue(
            str(view["build_version"]).startswith(str(view["package_version"]))
        )
        self.assertIn(str(view["build_version"]), daemon_mod.format_status_text(view))


class DescribeVersionTest(unittest.TestCase):
    def test_prefers_build_version_matching_dash_v(self) -> None:
        text = companion_mod.describe_version(
            {
                "package_version": "0.1.0",
                "installed_version": "0.1.0",
                "package_drift": False,
                "build_version": "0.1.0+gabc1234",
            },
            "",
        )
        self.assertEqual(text, "v0.1.0+gabc1234")

    def test_no_false_drift_from_commit_suffix(self) -> None:
        text = companion_mod.describe_version(
            {
                "package_version": "0.1.0",
                "installed_version": "0.1.0",
                "package_drift": False,
                "build_version": "0.1.0+gabc1234",
            },
            "",
        )
        self.assertNotIn("installed", text)

    def test_real_drift_still_reported_against_bare_version(self) -> None:
        text = companion_mod.describe_version(
            {
                "package_version": "0.1.0",
                "installed_version": "0.2.0",
                "package_drift": True,
                "build_version": "0.1.0+gabc1234",
            },
            "",
        )
        self.assertEqual(text, "v0.1.0+gabc1234 (installed v0.2.0)")

    def test_legacy_state_without_build_unchanged(self) -> None:
        text = companion_mod.describe_version(
            {
                "package_version": "0.1.0",
                "installed_version": "0.1.0",
                "package_drift": False,
            },
            "",
        )
        self.assertEqual(text, "v0.1.0")


class StatusTextTest(unittest.TestCase):
    def test_package_line_shows_build_identity(self) -> None:
        text = status_mod.render_status(
            mode="AUTO",
            agent="opencode (terminal: tmux)",
            spec="demo",
            session="s",
            context_strategy="per-spec",
            elapsed="1s",
            open_count=0,
            blocked_count=0,
            tests="no verification record",
            next_action="none",
            package_version="0.1.0",
            installed_version="0.1.0",
            build_version="0.1.0+gabc1234",
        )
        self.assertIn("package: ariadex 0.1.0+gabc1234", text)
        self.assertNotIn("package drift", text)


if __name__ == "__main__":
    unittest.main()
