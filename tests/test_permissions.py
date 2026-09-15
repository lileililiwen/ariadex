"""Safe temporary permission policy: contained auto-approval, fail-closed.

Covers validated permission configuration and migration, private
project-scoped temp-root creation with secure permissions, adapter
permission recognition, policy evaluation (containment, traversal,
symlink escape, shared /tmp, privileged operations, malformed input),
single-shot approval delivery, and bounded redacted decision evidence
in diagnostics and the widget projection.
"""

import os
import tempfile
import unittest
from pathlib import Path

from ariadex import companion as companion_mod
from ariadex import config as config_mod
from ariadex import daemon as daemon_mod
from ariadex import diagnostics as diagnostics_mod
from ariadex import handoff as handoff_mod
from ariadex import permissions as permissions_mod
from ariadex import providers as providers_mod
from ariadex import robot as robot_mod
from ariadex import terminal as terminal_mod

try:
    import evidence_fakes
except ModuleNotFoundError:
    from tests import evidence_fakes  # type: ignore[no-redef]

APPROVAL_TMP_WRITE = (
    "Ask anything\nApproval required: allow write to "
    "`/proj/.ariadex/tmp/draft.txt`? [y/n]\n"
)
APPROVAL_SHARED_TMP = (
    "Ask anything\nApproval required: allow write to `/tmp/shared/out.txt`? [y/n]\n"
)
APPROVAL_TRAVERSAL = (
    "Ask anything\nApproval required: allow read of "
    "`/proj/.ariadex/tmp/../../etc/passwd`? [y/n]\n"
)
APPROVAL_SUDO = "Ask anything\nApproval required: allow `sudo rm -rf /tmp/x`? [y/n]\n"
APPROVAL_AMBIGUOUS = (
    "Ask anything\nApproval required: allow write to `/a.txt` or `/b.txt`? [y/n]\n"
)
APPROVAL_UNKNOWN = "Ask anything\nApproval required: frobnicator engaged? [y/n]\n"


def directory_selector_capture(directory: str) -> str:
    """Generic directory-access selector surface for one directory."""
    return (
        "Build\nPermission required\nAccess external directory "
        f"{directory}\nPatterns\n- {directory}/*\n\n"
        "Allow once   Allow always   Reject   select  enter confirm\n"
    )


class FakeDriver(terminal_mod.FakeTerminalDriver):
    def __init__(self) -> None:
        super().__init__()
        self.executable = "tmux"


def make_project(state: list, config_text: str | None = None) -> Path:
    tmp = tempfile.TemporaryDirectory()
    state.append(tmp)
    root = Path(tmp.name)
    (root / ".ariadex").mkdir(parents=True)
    handoff_mod.write_handoff(root / "HANDOFF.md", handoff_mod.empty_handoff("s"))
    (root / "openspec" / "changes").mkdir(parents=True)
    if config_text is not None:
        (root / ".ariadex" / "config.yaml").write_text(config_text, encoding="utf-8")
    return root


def make_watcher(
    project: Path, driver: FakeDriver, output: str, provider: str = "opencode"
) -> robot_mod.RobotWatcher:
    adapter = providers_mod.get_adapter(provider, driver, "agent", project)
    driver.sessions["agent"] = {"command": [], "output": output, "workdir": "/t"}
    return robot_mod.RobotWatcher(
        project,
        robot_mod.RobotConfig(
            session="agent",
            provider=provider,
            initial_prompt="please start",
            debounce_polls=1,
            poll_interval_s=0.01,
        ),
        driver,
        adapter,
        evidence_runner=evidence_fakes.make_runner(project),
    )


def last_record(project: Path) -> dict:
    records, _ = diagnostics_mod.read_diagnostics(project, limit=1)
    assert records, "expected at least one diagnostic record"
    return records[-1]


class PermissionConfigTest(unittest.TestCase):
    def test_defaults_are_safe_prompt(self) -> None:
        cfg = config_mod.defaults()
        self.assertEqual(cfg.permission_policy, "prompt")
        self.assertEqual(cfg.permission_temp_root, ".ariadex/tmp")
        self.assertEqual(cfg.permission_actions, ["read", "write", "create", "delete"])
        self.assertEqual(cfg.permission_allowlist, [])

    def test_default_config_text_loads_with_permission_keys(self) -> None:
        import yaml

        cfg = config_mod.validate(
            yaml.safe_load(config_mod.default_config_text()), source="test"
        )
        self.assertEqual(cfg.permission_policy, "prompt")
        self.assertIn("permission_policy", config_mod.default_config_text())

    def test_invalid_policy_rejected(self) -> None:
        with self.assertRaises(config_mod.ConfigError):
            config_mod.validate({"permission_policy": "yes-to-everything"})

    def test_auto_policy_accepted_explicitly(self) -> None:
        cfg = config_mod.validate({"permission_policy": "auto"})
        self.assertEqual(cfg.permission_policy, "auto")
        self.assertEqual(config_mod.defaults().permission_policy, "prompt")

    def test_invalid_actions_rejected(self) -> None:
        with self.assertRaises(config_mod.ConfigError):
            config_mod.validate({"permission_actions": ["read", "execute"]})
        with self.assertRaises(config_mod.ConfigError):
            config_mod.validate({"permission_actions": "read"})

    def test_invalid_temp_root_rejected(self) -> None:
        with self.assertRaises(config_mod.ConfigError):
            config_mod.validate({"permission_temp_root": ""})
        with self.assertRaises(config_mod.ConfigError):
            config_mod.validate({"permission_temp_root": 42})

    def test_invalid_allowlist_rejected(self) -> None:
        with self.assertRaises(config_mod.ConfigError):
            config_mod.validate({"permission_allowlist": ["", "  "]})
        with self.assertRaises(config_mod.ConfigError):
            config_mod.validate({"permission_allowlist": "docs"})

    def test_migration_adds_safe_defaults_and_preserves_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".ariadex").mkdir(parents=True)
            (root / ".ariadex" / "config.yaml").write_text(
                "agent_provider: codex\n", encoding="utf-8"
            )
            missing = config_mod.migrate_permission_keys(root)
            self.assertEqual(
                missing,
                [
                    "permission_policy",
                    "permission_temp_root",
                    "permission_actions",
                    "permission_allowlist",
                ],
            )
            cfg = config_mod.load(root)
            self.assertEqual(cfg.permission_policy, "prompt")
            self.assertEqual(cfg.agent_provider, "codex")
            self.assertEqual(config_mod.migrate_permission_keys(root), [])

    def test_migration_keeps_explicit_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".ariadex").mkdir(parents=True)
            (root / ".ariadex" / "config.yaml").write_text(
                "permission_policy: deny\n", encoding="utf-8"
            )
            missing = config_mod.migrate_permission_keys(root)
            self.assertNotIn("permission_policy", missing)
            self.assertEqual(config_mod.load(root).permission_policy, "deny")


class ParseTest(unittest.TestCase):
    def test_operation_synonyms_canonicalize(self) -> None:
        parsed = permissions_mod.parse_permission_request(
            "allow `cat` of `/proj/.ariadex/tmp/a.txt`? [y/n]"
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.operation, "read")
        self.assertEqual(parsed.requested_path, "/proj/.ariadex/tmp/a.txt")

    def test_bare_path_parses(self) -> None:
        parsed = permissions_mod.parse_permission_request(
            "Approval required: write /proj/.ariadex/tmp/b.txt [y/n]"
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(
            (parsed.operation, parsed.requested_path),
            ("write", "/proj/.ariadex/tmp/b.txt"),
        )

    def test_no_path_is_unknown(self) -> None:
        self.assertIsNone(
            permissions_mod.parse_permission_request(
                "Approval required: proceed? [y/n]"
            )
        )

    def test_two_paths_are_ambiguous(self) -> None:
        self.assertIsNone(permissions_mod.parse_permission_request(APPROVAL_AMBIGUOUS))

    def test_unknown_surface_is_none(self) -> None:
        self.assertIsNone(permissions_mod.parse_permission_request(APPROVAL_UNKNOWN))
        self.assertIsNone(permissions_mod.parse_permission_request(""))

    def test_privileged_markers_never_parse(self) -> None:
        for text in (
            APPROVAL_SUDO,
            "allow `chmod 600 /proj/x`? [y/n]",
            "Approval: run shell command? [y/n]",
            "allow `rm`? [y/n]",
        ):
            with self.subTest(text=text):
                self.assertIsNone(permissions_mod.parse_permission_request(text))

    def test_shell_metacharacters_never_parse(self) -> None:
        self.assertIsNone(
            permissions_mod.parse_permission_request(
                "allow write to `/proj/a.txt; cat /etc/passwd`? [y/n]"
            )
        )
        self.assertIsNone(
            permissions_mod.parse_permission_request(
                "allow write to `/proj/a.txt | tee /tmp/x`? [y/n]"
            )
        )

    def test_execute_word_does_not_parse_as_file_action(self) -> None:
        self.assertIsNone(
            permissions_mod.parse_permission_request(
                "Approval required: execute `/proj/run.sh`? [y/n]"
            )
        )

    def test_adapter_recognition_never_raises(self) -> None:
        driver = FakeDriver()
        adapter = providers_mod.get_adapter("opencode", driver, "agent", "/t")
        parsed = adapter.recognize_permission(APPROVAL_SHARED_TMP)
        self.assertIsNotNone(parsed)
        self.assertIsNone(adapter.recognize_permission(APPROVAL_UNKNOWN))
        self.assertEqual(adapter.permission_approve_input, "y")
        for provider in ("codex", "codebuddy"):
            other = providers_mod.get_adapter(provider, driver, "agent", "/t")
            self.assertEqual(other.permission_approve_input, "y")
            self.assertIsNone(other.recognize_permission(APPROVAL_UNKNOWN))

    def test_directory_access_parses_single_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "work")
            parsed = permissions_mod.parse_permission_request(
                directory_selector_capture(target)
            )
            self.assertIsNotNone(parsed)
            assert parsed is not None
            self.assertEqual(
                (parsed.operation, parsed.requested_path), ("read", target)
            )

    def test_directory_access_ignores_surrounding_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "work")
            capture = (
                f"cp {tmp}/a.rs {target}/src/main.rs\n"
                f"cargo run --manifest-path {target}/Cargo.toml\n"
                + directory_selector_capture(target)
                + f"- {tmp}/*\n"
            )
            parsed = permissions_mod.parse_permission_request(capture)
            self.assertIsNotNone(parsed)
            assert parsed is not None
            self.assertEqual(
                (parsed.operation, parsed.requested_path), ("read", target)
            )

    def test_directory_access_two_directories_are_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = os.path.join(tmp, "one")
            second = os.path.join(tmp, "two")
            self.assertIsNone(
                permissions_mod.parse_permission_request(
                    f"Access external directory {first} and {second}\n"
                    "Allow once   Allow always\n"
                )
            )

    def test_directory_access_glob_primary_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(
                permissions_mod.parse_permission_request(
                    f"Access external directory {tmp}/*\nAllow once   Allow always\n"
                )
            )

    def test_selector_recognition(self) -> None:
        driver = FakeDriver()
        opencode = providers_mod.get_adapter("opencode", driver, "agent", "/t")
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "work")
            self.assertTrue(
                opencode.recognize_selector(directory_selector_capture(target))
            )
        self.assertFalse(opencode.recognize_selector(APPROVAL_SHARED_TMP))
        self.assertEqual(opencode.permission_approve_keys, ("Enter",))
        for provider in ("codex", "codebuddy"):
            other = providers_mod.get_adapter(provider, driver, "agent", "/t")
            with tempfile.TemporaryDirectory() as tmp:
                self.assertFalse(
                    other.recognize_selector(
                        directory_selector_capture(os.path.join(tmp, "work"))
                    )
                )
            self.assertIsNone(other.permission_approve_keys)


class TempRootTest(unittest.TestCase):
    def test_creates_owner_only_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = permissions_mod.ensure_temp_root(Path(tmp), ".ariadex/tmp")
            self.assertTrue(root.is_dir())
            if os.name != "nt":
                self.assertEqual(root.stat().st_mode & 0o777, 0o700)

    def test_absolute_root_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            permissions_mod.ensure_temp_root(Path(tmp), "/tmp/ariadex")

    def test_escaping_root_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            permissions_mod.ensure_temp_root(Path(tmp), "../outside")

    def test_repairs_loose_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".ariadex" / "tmp"
            root.mkdir(parents=True)
            os.chmod(root, 0o755)
            repaired = permissions_mod.ensure_temp_root(Path(tmp), ".ariadex/tmp")
            self.assertEqual(repaired, root)
            if os.name != "nt":
                self.assertEqual(root.stat().st_mode & 0o777, 0o700)


class EvaluateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.temp_root = permissions_mod.ensure_temp_root(self.project, ".ariadex/tmp")

    def _evaluate(self, requested: str, **overrides):
        parsed = permissions_mod.parse_permission_request(
            f"allow write to `{requested}`? [y/n]"
        )
        params = {
            "provider": "opencode",
            "parsed": parsed,
            "raw_tail": f"allow write to `{requested}`? [y/n]",
            "policy": "project-temp-auto",
            "temp_root": self.temp_root,
            "allowlist": [],
            "allowed_actions": ["read", "write", "create", "delete"],
            "approve_input": "y",
            "project_dir": self.project,
        }
        params.update(overrides)
        return permissions_mod.evaluate(**params)

    def test_prompt_policy_waits_without_input(self) -> None:
        decision = self._evaluate(str(self.temp_root / "a.txt"), policy="prompt")
        self.assertEqual(decision.result, "waiting")
        self.assertEqual(decision.approve_input, "")

    def test_deny_policy_denies(self) -> None:
        decision = self._evaluate(str(self.temp_root / "a.txt"), policy="deny")
        self.assertEqual(decision.result, "deny")

    def test_unknown_policy_waits(self) -> None:
        decision = self._evaluate(
            str(self.temp_root / "a.txt"), policy="yes-to-everything"
        )
        self.assertEqual(decision.result, "waiting")

    def test_contained_temp_request_allowed(self) -> None:
        target = self.temp_root / "draft.txt"
        decision = self._evaluate(str(target))
        self.assertEqual(decision.result, "allow")
        self.assertEqual(decision.operation, "write")
        self.assertEqual(decision.normalized_path, str(target.resolve()))
        self.assertEqual(decision.approve_input, "y")

    def test_shared_tmp_waits(self) -> None:
        decision = self._evaluate("/tmp/shared/out.txt")
        self.assertEqual(decision.result, "waiting")
        self.assertIn("/tmp", decision.reason)
        self.assertEqual(decision.approve_input, "")

    def test_auto_policy_allows_any_parsed_path(self) -> None:
        for target in ("/tmp/shared/out.txt", "/etc/app/config.txt"):
            decision = self._evaluate(target, policy="auto", temp_root=None)
            self.assertEqual(decision.result, "allow", target)
            self.assertEqual(decision.approve_input, "y")

    def _evaluate_directory(self, requested_dir: str, **overrides):
        parsed = permissions_mod.parse_permission_request(
            directory_selector_capture(requested_dir)
        )
        assert parsed is not None, f"directory surface did not parse: {requested_dir}"
        params = {
            "provider": "opencode",
            "parsed": parsed,
            "raw_tail": directory_selector_capture(requested_dir),
            "policy": "allowlist",
            "temp_root": None,
            "allowlist": [],
            "allowed_actions": ["read", "write", "create", "delete"],
            "approve_input": "y",
            "project_dir": self.project,
        }
        params.update(overrides)
        return permissions_mod.evaluate(**params)

    def test_directory_allowlisted_approves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "work")
            roots = permissions_mod.allowlist_roots(self.project, [tmp])
            decision = self._evaluate_directory(target, allowlist=roots)
            self.assertEqual(decision.result, "allow")
            self.assertEqual(decision.operation, "read")
            self.assertEqual(decision.requested_path, target)

    def test_directory_auto_approves_any_parsed_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "work")
            decision = self._evaluate_directory(target, policy="auto")
            self.assertEqual(decision.result, "allow")

    def test_directory_prompt_waits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "work")
            decision = self._evaluate_directory(target, policy="prompt")
            self.assertEqual(decision.result, "waiting")
            self.assertEqual(decision.approve_input, "")

    def test_directory_outside_allowlist_waits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "work")
            roots = permissions_mod.allowlist_roots(self.project, ["docs"])
            decision = self._evaluate_directory(target, allowlist=roots)
            self.assertEqual(decision.result, "waiting")

    def test_auto_policy_still_waits_on_unparsed(self) -> None:
        decision = permissions_mod.evaluate(
            provider="opencode",
            parsed=None,
            raw_tail="approve this thing? [y/n]",
            policy="auto",
            temp_root=None,
            allowlist=[],
            allowed_actions=["read", "write", "create", "delete"],
            approve_input="y",
            project_dir=self.project,
        )
        self.assertEqual(decision.result, "waiting")
        self.assertEqual(decision.approve_input, "")

    def test_auto_policy_denies_privileged_markers(self) -> None:
        decision = permissions_mod.evaluate(
            provider="opencode",
            parsed=None,
            raw_tail="run `rm -rf /` with sudo? [y/n]",
            policy="auto",
            temp_root=None,
            allowlist=[],
            allowed_actions=["read", "write", "create", "delete"],
            approve_input="y",
            project_dir=self.project,
        )
        self.assertEqual(decision.result, "deny")

    def test_auto_policy_denies_disabled_operation(self) -> None:
        decision = self._evaluate(
            str(self.temp_root / "a.txt"),
            policy="auto",
            allowed_actions=["read"],
        )
        self.assertEqual(decision.result, "deny")

    def test_allowlist_policy_allows_listed_entry(self) -> None:
        allowed = self.project / "docs"
        allowed.mkdir(exist_ok=True)
        roots = permissions_mod.allowlist_roots(self.project, ["docs"])
        decision = self._evaluate(
            str(allowed / "note.txt"),
            policy="allowlist",
            temp_root=None,
            allowlist=roots,
        )
        self.assertEqual(decision.result, "allow")

    def test_allowlist_policy_waits_outside_entry(self) -> None:
        roots = permissions_mod.allowlist_roots(self.project, ["docs"])
        decision = self._evaluate(
            str(self.temp_root / "a.txt"),
            policy="allowlist",
            temp_root=None,
            allowlist=roots,
        )
        self.assertEqual(decision.result, "waiting")

    def test_traversal_denied(self) -> None:
        decision = self._evaluate(str(self.temp_root / ".." / "escape.txt"))
        self.assertEqual(decision.result, "deny")
        self.assertIn("traversal", decision.reason)

    def test_symlink_escape_denied(self) -> None:
        link = self.project / ".ariadex" / "tmp" / "link"
        try:
            os.symlink("/tmp", link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        decision = self._evaluate(str(link / "evil.txt"))
        self.assertEqual(decision.result, "deny")
        self.assertIn("symlink", decision.reason)

    def test_home_expansion_denied(self) -> None:
        decision = self._evaluate("~/.bashrc")
        self.assertEqual(decision.result, "deny")

    def test_privileged_raw_request_denied(self) -> None:
        decision = permissions_mod.evaluate(
            provider="opencode",
            parsed=None,
            raw_tail=APPROVAL_SUDO,
            policy="project-temp-auto",
            temp_root=self.temp_root,
            allowlist=[],
            allowed_actions=["read", "write", "create", "delete"],
            approve_input="y",
            project_dir=self.project,
        )
        self.assertEqual(decision.result, "deny")

    def test_unparsable_request_waits(self) -> None:
        decision = permissions_mod.evaluate(
            provider="opencode",
            parsed=None,
            raw_tail=APPROVAL_UNKNOWN,
            policy="project-temp-auto",
            temp_root=self.temp_root,
            allowlist=[],
            allowed_actions=["read", "write", "create", "delete"],
            approve_input="y",
            project_dir=self.project,
        )
        self.assertEqual(decision.result, "waiting")

    def test_disabled_operation_denied(self) -> None:
        decision = self._evaluate(
            str(self.temp_root / "a.txt"), allowed_actions=["read"]
        )
        self.assertEqual(decision.result, "deny")
        self.assertIn("permission_actions", decision.reason)


class WatcherApprovalTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def _config(self, policy: str) -> str:
        return (
            "agent_provider: opencode\n"
            f"permission_policy: {policy}\n"
            "permission_temp_root: .ariadex/tmp\n"
            "permission_actions: [read, write, create, delete]\n"
            "permission_allowlist: []\n"
        )

    def _tmp_write_capture(self, project: Path, path: str) -> str:
        return f"Ask anything\nApproval required: allow write to `{path}`? [y/n]\n"

    def test_default_policy_waits_without_input(self) -> None:
        project = make_project(self._tmp)
        driver = FakeDriver()
        watcher = make_watcher(
            project,
            driver,
            "Ask anything\nApproval required: allow write to `/t/a.txt`? [y/n]\n",
        )
        self.assertEqual(watcher.poll(), robot_mod.WAITING)
        self.assertIn("approval", watcher.block_reason)
        self.assertEqual(driver.sent_inputs("agent"), [])
        self.assertEqual(watcher.permissions_granted, 0)
        record = last_record(project)
        self.assertEqual(record["decision"], "waiting")
        self.assertEqual(record["policy"], "prompt")
        self.assertEqual(record["operation"], "write")

    def test_contained_request_approved_once_with_owned_keystroke(self) -> None:
        project = make_project(self._tmp, self._config("project-temp-auto"))
        target = project / ".ariadex" / "tmp" / "draft.txt"
        driver = FakeDriver()
        watcher = make_watcher(
            project, driver, self._tmp_write_capture(project, str(target))
        )
        self.assertEqual(watcher.poll(), robot_mod.WAITING)
        self.assertEqual(driver.sent_inputs("agent"), ["y"])
        self.assertEqual(watcher.permissions_granted, 1)
        record = last_record(project)
        self.assertEqual(record["decision"], "allow")
        self.assertEqual(record["operation"], "write")
        self.assertEqual(record["policy"], "project-temp-auto")
        self.assertEqual(record["requested_path"], str(target))
        self.assertEqual(record["normalized_path"], str(target.resolve()))

    def test_repeated_surface_never_resends(self) -> None:
        project = make_project(self._tmp, self._config("project-temp-auto"))
        target = project / ".ariadex" / "tmp" / "draft.txt"
        driver = FakeDriver()
        watcher = make_watcher(
            project, driver, self._tmp_write_capture(project, str(target))
        )
        watcher.poll()
        watcher.poll()
        self.assertEqual(driver.sent_inputs("agent"), ["y"])
        self.assertEqual(watcher.permissions_granted, 1)
        record = last_record(project)
        self.assertEqual(record["decision"], "waiting")
        self.assertIn("already approved", record["blocker"])

    def test_shared_tmp_never_approved(self) -> None:
        project = make_project(self._tmp, self._config("project-temp-auto"))
        driver = FakeDriver()
        watcher = make_watcher(project, driver, APPROVAL_SHARED_TMP)
        self.assertEqual(watcher.poll(), robot_mod.WAITING)
        self.assertEqual(driver.sent_inputs("agent"), [])
        self.assertEqual(watcher.permissions_granted, 0)
        record = last_record(project)
        self.assertEqual(record["decision"], "waiting")
        self.assertIn("/tmp", record["blocker"])

    def test_traversal_records_deny_without_input(self) -> None:
        project = make_project(self._tmp, self._config("project-temp-auto"))
        driver = FakeDriver()
        capture = self._tmp_write_capture(
            project, str(project / ".ariadex" / "tmp" / ".." / "escape.txt")
        )
        watcher = make_watcher(project, driver, capture)
        self.assertEqual(watcher.poll(), robot_mod.WAITING)
        self.assertEqual(driver.sent_inputs("agent"), [])
        record = last_record(project)
        self.assertEqual(record["decision"], "deny")
        self.assertIn("traversal", record["blocker"])

    def test_privileged_request_denied_without_input(self) -> None:
        project = make_project(self._tmp, self._config("project-temp-auto"))
        driver = FakeDriver()
        watcher = make_watcher(project, driver, APPROVAL_SUDO)
        self.assertEqual(watcher.poll(), robot_mod.WAITING)
        self.assertEqual(driver.sent_inputs("agent"), [])
        record = last_record(project)
        self.assertEqual(record["decision"], "deny")

    def test_unknown_request_waits_without_input(self) -> None:
        project = make_project(self._tmp, self._config("project-temp-auto"))
        driver = FakeDriver()
        watcher = make_watcher(project, driver, APPROVAL_UNKNOWN)
        self.assertEqual(watcher.poll(), robot_mod.WAITING)
        self.assertEqual(driver.sent_inputs("agent"), [])
        record = last_record(project)
        self.assertEqual(record["decision"], "waiting")

    def test_undeclared_approve_input_waits(self) -> None:
        project = make_project(self._tmp, self._config("project-temp-auto"))
        target = project / ".ariadex" / "tmp" / "draft.txt"
        driver = FakeDriver()
        adapter = providers_mod.get_adapter("opencode", driver, "agent", project)
        adapter.permission_approve_input = None
        driver.sessions["agent"] = {
            "command": [],
            "output": self._tmp_write_capture(project, str(target)),
            "workdir": "/t",
        }
        watcher = robot_mod.RobotWatcher(
            project,
            robot_mod.RobotConfig(
                session="agent",
                provider="opencode",
                initial_prompt="please start",
                debounce_polls=1,
                poll_interval_s=0.01,
            ),
            driver,
            adapter,
            evidence_runner=evidence_fakes.make_runner(project),
        )
        self.assertEqual(watcher.poll(), robot_mod.WAITING)
        self.assertEqual(driver.sent_inputs("agent"), [])
        self.assertEqual(watcher.permissions_granted, 0)

    def test_status_view_reports_grants(self) -> None:
        project = make_project(self._tmp, self._config("project-temp-auto"))
        target = project / ".ariadex" / "tmp" / "draft.txt"
        driver = FakeDriver()
        watcher = make_watcher(
            project, driver, self._tmp_write_capture(project, str(target))
        )
        watcher.poll()
        self.assertEqual(watcher.status_view()["permissions_granted"], 1)

    def test_busy_provider_with_approval_reaches_policy_branch(self) -> None:
        class BusyOpenCode(providers_mod.OpenCodeAdapter):
            @property
            def provider_state_required(self):  # type: ignore[override]
                return True

            def provider_state(self):  # type: ignore[override]
                return "active"

        project = make_project(self._tmp, self._config("project-temp-auto"))
        target = project / ".ariadex" / "tmp" / "draft.txt"
        driver = FakeDriver()
        adapter = BusyOpenCode(driver, "agent", project)
        driver.sessions["agent"] = {
            "command": [],
            "output": self._tmp_write_capture(project, str(target)),
            "workdir": "/t",
        }
        watcher = robot_mod.RobotWatcher(
            project,
            robot_mod.RobotConfig(
                session="agent",
                provider="opencode",
                initial_prompt="please start",
                debounce_polls=1,
                poll_interval_s=0.01,
            ),
            driver,
            adapter,
            evidence_runner=evidence_fakes.make_runner(project),
        )
        self.assertEqual(watcher.poll(), robot_mod.WAITING)
        self.assertEqual(driver.sent_inputs("agent"), ["y"])
        self.assertEqual(watcher.permissions_granted, 1)
        record = last_record(project)
        self.assertEqual(record["decision"], "allow")
        self.assertEqual(record["classification"], "approval")

    def test_selector_surface_sends_keys_once(self) -> None:
        project = make_project(self._tmp, self._config("auto"))
        driver = FakeDriver()
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "work")
            watcher = make_watcher(project, driver, directory_selector_capture(target))
            self.assertEqual(watcher.poll(), robot_mod.WAITING)
            self.assertEqual(driver.sent_inputs("agent"), [])
            self.assertEqual(driver.sent_key_sequences("agent"), [["Enter"]])
            self.assertEqual(watcher.permissions_granted, 1)
            record = last_record(project)
            self.assertEqual(record["decision"], "allow")
            self.assertEqual(record["operation"], "read")
            self.assertEqual(record["requested_path"], target)
            watcher.poll()
            self.assertEqual(driver.sent_key_sequences("agent"), [["Enter"]])
            self.assertEqual(watcher.permissions_granted, 1)


class WidgetProjectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def _record_permission(self, project: Path) -> None:
        diagnostics_mod.try_record(
            project,
            diagnostics_mod.build_diagnostic(
                "provider",
                "permission decision (waiting)",
                result="waiting",
                message="permission waiting: policy=project-temp-auto "
                "operation=write path=/tmp/shared/out.txt; path is outside",
                provider="opencode",
                classification="approval",
                decision="waiting",
                blocker="path is outside the private project temp root",
                operation="write",
                next_action="answer the approval in the provider session",
                requested_path="/tmp/shared/out.txt",
                normalized_path="/tmp/shared/out.txt",
                policy="project-temp-auto",
            ),
        )

    def test_managed_context_carries_permission_fields(self) -> None:
        project = make_project(self._tmp)
        self._record_permission(project)
        context = daemon_mod.managed_diagnostic_context(project)
        event = context["recent_events"][-1]
        self.assertEqual(event["policy"], "project-temp-auto")
        self.assertEqual(event["requested_path"], "/tmp/shared/out.txt")
        self.assertEqual(event["normalized_path"], "/tmp/shared/out.txt")
        self.assertEqual(event["operation"], "write")

    def test_log_text_shows_policy_and_path(self) -> None:
        project = make_project(self._tmp)
        self._record_permission(project)
        context = daemon_mod.managed_diagnostic_context(project)
        viewer = companion_mod.build_managed_context({"diagnostic_context": context})
        text = companion_mod.format_managed_log_text(viewer)
        self.assertIn("policy=project-temp-auto", text)
        self.assertIn("path=/tmp/shared/out.txt", text)
        snapshot = companion_mod.format_context_snapshot(
            viewer, {"provider": "opencode", "session": "s", "mode": "AUTO"}
        )
        self.assertIn("policy=project-temp-auto", snapshot)
        self.assertIn("path=/tmp/shared/out.txt", snapshot)


if __name__ == "__main__":
    unittest.main()
