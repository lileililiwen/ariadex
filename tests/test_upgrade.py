"""Tests for version-aware upgrade management (read-only probe, safe plans)."""

import io
import json
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ariadex import cli, release, upgrade
from ariadex import status as status_mod


def make_payload(*versions: str) -> str:
    return json.dumps({"releases": {v: [] for v in versions}})


class FakeDist:
    def __init__(self, location: str = "", direct_url: str = ""):
        self._location = location
        self._direct_url = direct_url

    def locate_file(self, _name: str) -> str:
        return self._location

    def read_text(self, name: str) -> str | None:
        if name == "direct_url.json":
            return self._direct_url
        return None


class VersionCompareTest(unittest.TestCase):
    def test_valid_versions(self) -> None:
        self.assertTrue(upgrade.valid_version("0.1.0"))
        self.assertTrue(upgrade.valid_version("1.2"))
        self.assertFalse(upgrade.valid_version(""))
        self.assertFalse(upgrade.valid_version("not a version!!"))
        self.assertFalse(upgrade.valid_version("x" * 65))

    def test_ordering(self) -> None:
        self.assertEqual(upgrade.compare_versions("0.1.0", "0.1.0"), 0)
        self.assertLess(upgrade.compare_versions("0.1.0", "0.2.0"), 0)
        self.assertGreater(upgrade.compare_versions("1.0.0", "0.9.9"), 0)
        self.assertLess(upgrade.compare_versions("1.0.0a1", "1.0.0"), 0)
        self.assertLess(upgrade.compare_versions("bad", "0.1.0"), 0)

    def test_latest_from_payload(self) -> None:
        self.assertEqual(
            upgrade.latest_from_payload(make_payload("0.1.0", "0.2.0", "0.1.9")),
            "0.2.0",
        )
        with self.assertRaises(ValueError):
            upgrade.latest_from_payload("not json")
        with self.assertRaises(ValueError):
            upgrade.latest_from_payload(json.dumps({"releases": {}}))
        with self.assertRaises(ValueError):
            upgrade.latest_from_payload(json.dumps({"noreleases": 1}))

    def test_index_url_alignment_with_release_gate(self) -> None:
        self.assertEqual(upgrade.DEFAULT_INDEX_URL, release.PYPI_JSON_URL)

    def test_running_version_is_single_source(self) -> None:
        from ariadex import __version__

        self.assertEqual(upgrade.running_version(), __version__)


class ProbeTest(unittest.TestCase):
    def test_current(self) -> None:
        check = upgrade.probe_index("0.2.0", payload=make_payload("0.1.0", "0.2.0"))
        self.assertEqual(check.status, "current")

    def test_update_available(self) -> None:
        check = upgrade.probe_index("0.1.0", payload=make_payload("0.1.0", "0.2.0"))
        self.assertEqual(check.status, "update-available")
        self.assertEqual(check.latest, "0.2.0")

    def test_ahead(self) -> None:
        check = upgrade.probe_index("0.3.0", payload=make_payload("0.1.0", "0.2.0"))
        self.assertEqual(check.status, "ahead")

    def test_unavailable_on_transport_failure(self) -> None:
        def _fail(**_kwargs):
            raise OSError("no network")

        check = upgrade.probe_index("0.1.0", fetcher=_fail)
        self.assertEqual(check.status, "unavailable")
        self.assertIn("unchanged", check.detail)

    def test_invalid_on_bad_payload(self) -> None:
        check = upgrade.probe_index("0.1.0", payload="not json")
        self.assertEqual(check.status, "invalid")
        self.assertIn("unchanged", check.detail)

    def test_invalid_installed(self) -> None:
        check = upgrade.probe_index("bogus!!", payload=make_payload("0.1.0"))
        self.assertEqual(check.status, "invalid")

    def test_fetch_rejects_non_http_index(self) -> None:
        with self.assertRaises(ValueError):
            upgrade.fetch_index_payload("file:///etc/passwd")


class ProvenanceTest(unittest.TestCase):
    def test_pipx_executable(self) -> None:
        prov = upgrade.detect_provenance(
            executable="/home/u/.local/share/pipx/venvs/ariadex/bin/ariadex",
            prefix="/home/u/.local/share/pipx/venvs/ariadex",
            environ={},
            distribution=FakeDist(location="/home/u/.local/share/pipx/venvs/ariadex"),
        )
        self.assertEqual(prov.kind, "pipx")

    def test_pip_install(self) -> None:
        prov = upgrade.detect_provenance(
            executable="/usr/bin/python",
            prefix="/usr",
            environ={},
            distribution=FakeDist(location="/usr/lib/python3/site-packages"),
        )
        self.assertEqual(prov.kind, "pip")

    def test_editable_checkout(self) -> None:
        prov = upgrade.detect_provenance(
            executable="/usr/bin/python",
            prefix="/usr",
            environ={},
            distribution=FakeDist(
                location="/home/u/code/ariadex",
                direct_url='{"dir_info": {"editable": true}}',
            ),
        )
        self.assertEqual(prov.kind, "editable")
        self.assertIn("/home/u/code/ariadex", prov.path)

    def test_source_checkout_without_distribution(self) -> None:
        prov = upgrade.detect_provenance(
            executable="/usr/bin/python",
            prefix="/usr",
            environ={},
            distribution=None,
            location=None,
        )
        # Auto-resolve path depends on the test environment; force the
        # source branch by simulating PackageNotFoundError.
        import importlib.metadata as md

        with mock.patch.object(
            md, "distribution", side_effect=md.PackageNotFoundError("x")
        ):
            prov = upgrade.detect_provenance(distribution=None)
        self.assertEqual(prov.kind, "source")

    def test_unknown_when_metadata_unreadable(self) -> None:
        import importlib.metadata as md

        with mock.patch.object(md, "distribution", side_effect=RuntimeError("boom")):
            prov = upgrade.detect_provenance(distribution=None)
        self.assertEqual(prov.kind, "unknown")


class PlanTest(unittest.TestCase):
    def _check(self, installed="0.1.0", latest="0.2.0") -> upgrade.IndexCheck:
        return upgrade.IndexCheck("update-available", installed, latest, "update")

    def test_pipx_plan_uses_fixed_argv(self) -> None:
        prov = upgrade.Provenance("pipx", "pipx", "/p")
        plan = upgrade.plan_upgrade(self._check(), prov)
        self.assertTrue(plan.allowed)
        self.assertEqual(plan.argv, ["pipx", "upgrade", "ariadex"])

    def test_pip_plan_pins_exact_version(self) -> None:
        prov = upgrade.Provenance("pip", "pip", "/p")
        plan = upgrade.plan_upgrade(
            self._check(), prov, python_executable="/usr/bin/python"
        )
        self.assertTrue(plan.allowed)
        self.assertEqual(
            plan.argv,
            ["/usr/bin/python", "-m", "pip", "install", "--upgrade", "ariadex==0.2.0"],
        )

    def test_editable_refuses_with_checkout_action(self) -> None:
        prov = upgrade.Provenance("editable", "editable", "/home/u/code/ariadex")
        plan = upgrade.plan_upgrade(self._check(), prov)
        self.assertFalse(plan.allowed)
        self.assertEqual(plan.argv, [])
        self.assertIn("/home/u/code/ariadex", plan.reason)
        self.assertIn("git pull", plan.reason)

    def test_source_refuses_with_install_action(self) -> None:
        prov = upgrade.Provenance("source", "source", "/home/u/code/ariadex")
        plan = upgrade.plan_upgrade(self._check(), prov)
        self.assertFalse(plan.allowed)
        self.assertIn("pipx install", plan.reason)

    def test_no_plan_when_current(self) -> None:
        check = upgrade.IndexCheck("current", "0.2.0", "0.2.0", "current")
        plan = upgrade.plan_upgrade(check, upgrade.Provenance("pipx", "x", ""))
        self.assertFalse(plan.allowed)

    def test_unknown_provenance_refuses(self) -> None:
        plan = upgrade.plan_upgrade(
            self._check(), upgrade.Provenance("unknown", "x", "")
        )
        self.assertFalse(plan.allowed)
        self.assertIn("manually", plan.reason)

    def test_execute_runs_fixed_argv_without_shell(self) -> None:
        plan = upgrade.UpgradePlan(True, ["pipx", "upgrade", "ariadex"], "d", "r")
        calls = []

        class _Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        def _runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return _Proc()

        result = upgrade.execute_plan(plan, runner=_runner)
        self.assertTrue(result.ok)
        argv, kwargs = calls[0]
        self.assertEqual(argv, ["pipx", "upgrade", "ariadex"])
        self.assertNotIn("shell", kwargs)

    def test_execute_failure_preserves_install(self) -> None:
        plan = upgrade.UpgradePlan(True, ["pipx", "upgrade", "ariadex"], "d", "r")

        class _Proc:
            returncode = 1
            stdout = ""
            stderr = "boom"

        result = upgrade.execute_plan(plan, runner=lambda *a, **k: _Proc())
        self.assertFalse(result.ok)
        self.assertIn("preserved", result.detail)

    def test_execute_refused_plan_runs_nothing(self) -> None:
        plan = upgrade.UpgradePlan(False, [], "none", "reason")
        called = []
        result = upgrade.execute_plan(plan, runner=lambda *a, **k: called.append(1))
        self.assertFalse(result.ok)
        self.assertEqual(called, [])


class DriftTest(unittest.TestCase):
    def test_no_drift(self) -> None:
        snap = upgrade.version_snapshot(running="0.1.0", installed="0.1.0")
        self.assertFalse(snap["drift"])
        self.assertIn("no drift", upgrade.drift_note(snap, False))

    def test_drift_reports_restart_boundary(self) -> None:
        snap = upgrade.version_snapshot(running="0.1.0", installed="0.2.0")
        self.assertTrue(snap["drift"])
        note = upgrade.drift_note(snap, True)
        self.assertIn("drift", note)
        self.assertIn("future starts", note)

    def test_status_text_carries_package_and_drift(self) -> None:
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
            installed_version="0.2.0",
        )
        self.assertIn("package: ariadex 0.1.0", text)
        self.assertIn("package drift", text)

    def test_daemon_status_view_carries_versions(self) -> None:
        from ariadex import daemon as daemon_mod

        with tempfile.TemporaryDirectory() as tmp:
            view = daemon_mod.daemon_status_view(Path(tmp))
        self.assertIn("package_version", view)
        self.assertIn("installed_version", view)
        rendered = daemon_mod.format_status_text(view)
        self.assertIn("package: ariadex", rendered)


def run_cli(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with chdir(root), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


class UpgradeCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _freeze_tree(self) -> dict:
        before = {
            p.name: p.read_bytes() if p.is_file() else None for p in self.root.iterdir()
        }
        return before

    def test_check_is_read_only_and_reports_versions(self) -> None:
        check = upgrade.IndexCheck("update-available", "0.1.0", "0.2.0", "update")
        prov = upgrade.Provenance("pipx", "pipx-managed", "/p")
        before = self._freeze_tree()
        with (
            mock.patch.object(upgrade, "probe_index", return_value=check),
            mock.patch.object(upgrade, "detect_provenance", return_value=prov),
            mock.patch("subprocess.run") as runner,
        ):
            code, out, _ = run_cli(self.root, "upgrade", "--check")
        self.assertEqual(code, 0)
        self.assertIn("0.1.0", out)
        self.assertIn("0.2.0", out)
        self.assertIn("pipx", out)
        runner.assert_not_called()
        after = self._freeze_tree()
        self.assertEqual(before, after)

    def test_check_unavailable_exits_nonzero_without_mutation(self) -> None:
        check = upgrade.IndexCheck("unavailable", "0.1.0", "", "index down")
        with (
            mock.patch.object(upgrade, "probe_index", return_value=check),
            mock.patch("subprocess.run") as runner,
        ):
            code, out, _ = run_cli(self.root, "upgrade", "--check")
        self.assertNotEqual(code, 0)
        runner.assert_not_called()
        self.assertIn("unavailable", out)

    def test_editable_check_reports_checkout_action(self) -> None:
        check = upgrade.IndexCheck("update-available", "0.1.0", "0.2.0", "update")
        prov = upgrade.Provenance("editable", "editable", "/home/u/code/ariadex")
        with (
            mock.patch.object(upgrade, "probe_index", return_value=check),
            mock.patch.object(upgrade, "detect_provenance", return_value=prov),
            mock.patch("subprocess.run") as runner,
        ):
            code, out, err = run_cli(self.root, "upgrade")
        self.assertNotEqual(code, 0)
        runner.assert_not_called()
        self.assertIn("editable", out + err)

    def test_upgrade_requires_confirmation_without_yes(self) -> None:
        check = upgrade.IndexCheck("update-available", "0.1.0", "0.2.0", "update")
        prov = upgrade.Provenance("pipx", "pipx", "/p")
        with (
            mock.patch.object(upgrade, "probe_index", return_value=check),
            mock.patch.object(upgrade, "detect_provenance", return_value=prov),
            mock.patch.object(
                upgrade, "execute_plan", return_value=upgrade.UpgradeResult(True, "ok")
            ) as execute,
            mock.patch.object(cli.sys.stdin, "isatty", return_value=False),
        ):
            code, _, _ = run_cli(self.root, "upgrade")
        self.assertNotEqual(code, 0)
        execute.assert_not_called()

    def test_upgrade_with_yes_applies_pipx_plan(self) -> None:
        check = upgrade.IndexCheck("update-available", "0.1.0", "0.2.0", "update")
        prov = upgrade.Provenance("pipx", "pipx", "/p")
        with (
            mock.patch.object(upgrade, "probe_index", return_value=check),
            mock.patch.object(upgrade, "detect_provenance", return_value=prov),
            mock.patch.object(
                upgrade, "execute_plan", return_value=upgrade.UpgradeResult(True, "ok")
            ) as execute,
        ):
            code, out, _ = run_cli(self.root, "upgrade", "--yes")
        self.assertEqual(code, 0)
        execute.assert_called_once()
        plan = execute.call_args[0][0]
        self.assertEqual(plan.argv, ["pipx", "upgrade", "ariadex"])
        self.assertIn("pipx upgrade ariadex", out)

    def test_upgrade_leaves_running_daemon_alone(self) -> None:
        check = upgrade.IndexCheck("update-available", "0.1.0", "0.2.0", "update")
        prov = upgrade.Provenance("pipx", "pipx", "/p")
        with (
            mock.patch.object(upgrade, "probe_index", return_value=check),
            mock.patch.object(upgrade, "detect_provenance", return_value=prov),
            mock.patch.object(cli.daemon_mod, "daemon_alive", return_value=True),
            mock.patch.object(
                upgrade, "execute_plan", return_value=upgrade.UpgradeResult(True, "ok")
            ),
            mock.patch.object(cli.daemon_mod, "send_request") as ipc,
        ):
            code, out, _ = run_cli(self.root, "upgrade", "--yes")
        self.assertEqual(code, 0)
        ipc.assert_not_called()
        self.assertIn("left running", out)

    def test_upgrade_reachable_via_admin(self) -> None:
        check = upgrade.IndexCheck("current", "0.2.0", "0.2.0", "current")
        with mock.patch.object(upgrade, "probe_index", return_value=check):
            code, out, _ = run_cli(self.root, "admin", "upgrade", "--check")
        self.assertEqual(code, 0)
        self.assertIn("current", out)

    def test_upgrade_help_hides_runtime_internals(self) -> None:
        code, out, _ = run_cli(self.root, "upgrade", "--help")
        self.assertEqual(code, 0)
        lowered = out.lower()
        self.assertNotIn("provider", lowered)
        self.assertNotIn("tmux", lowered)
        self.assertNotIn("daemon", lowered)

    def test_doctor_reports_version_snapshot_offline(self) -> None:
        run_cli(self.root, "init")
        with (
            mock.patch.object(
                upgrade, "fetch_index_payload", side_effect=AssertionError("no net")
            ),
            mock.patch.object(upgrade, "probe_index") as probe,
        ):
            code, out, _ = run_cli(self.root, "doctor")
        probe.assert_not_called()
        self.assertIn("upgrade", out)
        _ = code


if __name__ == "__main__":
    unittest.main()
