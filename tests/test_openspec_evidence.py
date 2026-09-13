"""OpenSpec-authoritative current-spec lifecycle evidence.

Covers the bounded no-shell command boundary (missing binary, timeout,
non-zero, malformed, and contradictory payloads), atomic versioned
conversation records with handoff synchronization, archival proof, and
the recorded-spec boundary decisions (unfinished, ready-to-archive,
archived, renamed/deleted, empty, invalid) without sending unverified
provider input.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from ariadex import handoff as handoff_mod
from ariadex import openspec_evidence as evidence_mod
from ariadex import providers as providers_mod
from ariadex import robot as robot_mod
from ariadex import terminal as terminal_mod

try:
    import evidence_fakes
except ModuleNotFoundError:
    from tests import evidence_fakes  # type: ignore[no-redef]

READY = "Welcome back\nAsk anything · tab agents\n> "


class StubResult:
    """Minimal completed-process surface for stubbed runners."""

    def __init__(self, returncode: int, stdout: str, stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def stub_runner(handler, *, calls: list | None = None):
    """Wrap a handler(argv, kwargs) into a runner callable."""

    def run(argv, **kwargs):
        if calls is not None:
            calls.append(list(argv))
        return handler(list(argv), kwargs)

    return run


def list_payload(changes, source: str = "nearest") -> str:
    return json.dumps(
        {
            "changes": list(changes),
            "root": {"path": "/fake", "source": source},
        }
    )


def change_entry(name: str, completed: int, total: int) -> dict:
    return {"name": name, "completedTasks": completed, "totalTasks": total}


def make_project(state: list, *, with_openspec: bool = True) -> Path:
    tmp = tempfile.TemporaryDirectory()
    state.append(tmp)
    root = Path(tmp.name)
    (root / ".ariadex").mkdir(parents=True)
    handoff_mod.write_handoff(root / "HANDOFF.md", handoff_mod.empty_handoff("s"))
    if with_openspec:
        (root / "openspec" / "changes").mkdir(parents=True)
    return root


def make_change(root: Path, name: str, tasks: str, current: bool = True) -> None:
    change = root / "openspec" / "changes" / name
    change.mkdir(parents=True, exist_ok=True)
    (change / "tasks.md").write_text(tasks, encoding="utf-8")
    if current:
        handoff = handoff_mod.read_handoff(root / "HANDOFF.md")
        handoff.current_spec = name
        handoff_mod.write_handoff(root / "HANDOFF.md", handoff)


def make_config(**overrides):
    params = {
        "session": "agent",
        "provider": "opencode",
        "initial_prompt": "please start",
        "continuation_prompt": "please continue",
        "confirmation_prompt": "please finish the rest",
        "debounce_polls": 1,
        "poll_interval_s": 0.01,
    }
    params.update(overrides)
    return robot_mod.RobotConfig(**params)


def clean_git(test: unittest.TestCase):
    return unittest.mock.patch.object(
        robot_mod, "_git_tree_clean", return_value=(True, "")
    )


class CommandBoundaryTest(unittest.TestCase):
    def test_missing_binary_is_a_blocked_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "openspec").mkdir()
            runner = stub_runner(
                lambda argv, kwargs: (_ for _ in ()).throw(
                    FileNotFoundError("openspec")
                )
            )
            with self.assertRaises(evidence_mod.EvidenceBlocked) as ctx:
                evidence_mod.run_openspec(root, ["list", "--json"], runner=runner)
        self.assertIn("not available", str(ctx.exception))

    def test_timeout_is_a_blocked_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "openspec").mkdir()

            def handler(argv, kwargs):
                raise subprocess.TimeoutExpired(argv, 30)

            with self.assertRaises(evidence_mod.EvidenceBlocked) as ctx:
                evidence_mod.run_openspec(
                    root, ["list", "--json"], runner=stub_runner(handler)
                )
        self.assertIn("timed out", str(ctx.exception))

    def test_os_error_is_a_blocked_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "openspec").mkdir()

            def handler(argv, kwargs):
                raise OSError("pipe broken")

            with self.assertRaises(evidence_mod.EvidenceBlocked):
                evidence_mod.run_openspec(
                    root, ["list", "--json"], runner=stub_runner(handler)
                )

    def test_nonzero_exit_reports_bounded_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "openspec").mkdir()
            runner = stub_runner(lambda argv, kwargs: StubResult(1, "", "boom detail"))
            with self.assertRaises(evidence_mod.EvidenceBlocked) as ctx:
                evidence_mod.run_openspec(root, ["list", "--json"], runner=runner)
        self.assertIn("boom detail", str(ctx.exception))

    def test_success_returns_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "openspec").mkdir()
            runner = stub_runner(lambda argv, kwargs: StubResult(0, '{"a": 1}'))
            self.assertEqual(
                evidence_mod.run_openspec(root, ["list"], runner=runner), '{"a": 1}'
            )

    def test_filesystem_access_means_not_a_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "openspec").mkdir()
            runner = stub_runner(
                lambda argv, kwargs: StubResult(
                    1, "", "NotFound: FileSystem.access (/x)"
                )
            )
            with self.assertRaises(evidence_mod.NotOpenSpecRoot):
                evidence_mod.run_openspec(root, ["list", "--json"], runner=runner)

    def test_huge_output_is_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "openspec").mkdir()
            big = "x" * (evidence_mod.MAX_OUTPUT_CHARS + 100)
            runner = stub_runner(lambda argv, kwargs: StubResult(0, big))
            out = evidence_mod.run_openspec(root, ["list"], runner=runner)
        self.assertLessEqual(len(out), evidence_mod.MAX_OUTPUT_CHARS + 20)
        self.assertIn("truncated", out)


class RootDiscoveryTest(unittest.TestCase):
    def test_marker_dir_resolves_and_bare_dir_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(evidence_mod.find_openspec_root(root))
            (root / "openspec").mkdir()
            self.assertEqual(evidence_mod.find_openspec_root(root), root.resolve())

    def test_nested_project_resolves_ancestor_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "openspec").mkdir()
            nested = root / "work" / "proj"
            nested.mkdir(parents=True)
            self.assertEqual(evidence_mod.find_openspec_root(nested), root.resolve())

    def test_query_without_marker_never_runs_the_cli(self) -> None:
        calls: list = []

        def handler(argv, kwargs):
            calls.append(argv)
            return StubResult(0, list_payload([]))

        with (
            tempfile.TemporaryDirectory() as tmp,
            self.assertRaises(evidence_mod.NotOpenSpecRoot),
        ):
            evidence_mod.query_changes(
                Path(tmp), runner=stub_runner(handler, calls=calls)
            )
        self.assertEqual(calls, [])

    def test_implicit_source_falls_back_without_claims(self) -> None:
        state: list = []
        root = make_project(state)
        runner = stub_runner(
            lambda argv, kwargs: StubResult(0, list_payload([], source="implicit"))
        )
        with self.assertRaises(evidence_mod.NotOpenSpecRoot):
            evidence_mod.query_changes(root, runner=runner)
        for tmp in state:
            tmp.cleanup()


class QueryChangesTest(unittest.TestCase):
    def test_valid_queue_parses_progress(self) -> None:
        state: list = []
        root = make_project(state)
        runner = stub_runner(
            lambda argv, kwargs: StubResult(
                0,
                list_payload(
                    [
                        change_entry("b-change", 1, 3),
                        change_entry("a-change", 2, 2),
                    ]
                ),
            )
        )
        changes = evidence_mod.query_changes(root, runner=runner)
        self.assertEqual(changes.order, ["a-change", "b-change"])
        self.assertEqual(changes.entries["b-change"].open_tasks, 2)
        self.assertEqual(changes.entries["a-change"].open_tasks, 0)
        for tmp in state:
            tmp.cleanup()

    def test_malformed_and_contradictory_payloads_block(self) -> None:
        state: list = []
        root = make_project(state)
        bad_payloads = [
            "{not json",
            "[1, 2]",
            json.dumps({"changes": {}, "root": {"source": "nearest"}}),
            json.dumps(
                {
                    "changes": [{"completedTasks": 0, "totalTasks": 0}],
                    "root": {"source": "nearest"},
                }
            ),
            json.dumps(
                {
                    "changes": [{"name": "x", "completedTasks": -1, "totalTasks": 0}],
                    "root": {"source": "nearest"},
                }
            ),
            json.dumps(
                {
                    "changes": [{"name": "x", "completedTasks": True, "totalTasks": 1}],
                    "root": {"source": "nearest"},
                }
            ),
            json.dumps(
                {
                    "changes": [{"name": "x", "completedTasks": 3, "totalTasks": 2}],
                    "root": {"source": "nearest"},
                }
            ),
        ]
        for payload in bad_payloads:
            with self.subTest(payload=payload[:40]):
                runner = stub_runner(lambda argv, kwargs, p=payload: StubResult(0, p))
                with self.assertRaises(evidence_mod.EvidenceBlocked):
                    evidence_mod.query_changes(root, runner=runner)
        for tmp in state:
            tmp.cleanup()


class QueryStatusTest(unittest.TestCase):
    def _runner(self, payload: str):
        return stub_runner(lambda argv, kwargs: StubResult(0, payload))

    def test_found_and_complete(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            status = evidence_mod.query_change_status(
                root,
                "demo",
                runner=self._runner(
                    json.dumps({"changeName": "demo", "isComplete": True})
                ),
            )
            self.assertTrue(status.found)
            self.assertTrue(status.is_complete)
        finally:
            for tmp in state:
                tmp.cleanup()

    def test_not_found_reports_absent(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            payload = json.dumps(
                {
                    "status": [
                        {
                            "severity": "error",
                            "message": "Change 'demo' not found. Available…",
                        }
                    ]
                }
            )
            status = evidence_mod.query_change_status(
                root, "demo", runner=self._runner(payload)
            )
            self.assertFalse(status.found)
        finally:
            for tmp in state:
                tmp.cleanup()

    def test_other_status_errors_block(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            payload = json.dumps(
                {
                    "status": [
                        {
                            "severity": "error",
                            "message": "Invalid change name '9x'",
                        }
                    ]
                }
            )
            with self.assertRaises(evidence_mod.EvidenceBlocked):
                evidence_mod.query_change_status(
                    root, "9x", runner=self._runner(payload)
                )
        finally:
            for tmp in state:
                tmp.cleanup()

    def test_mismatched_change_or_bad_flag_blocks(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            with self.assertRaises(evidence_mod.EvidenceBlocked):
                evidence_mod.query_change_status(
                    root,
                    "demo",
                    runner=self._runner(
                        json.dumps({"changeName": "other", "isComplete": True})
                    ),
                )
            with self.assertRaises(evidence_mod.EvidenceBlocked):
                evidence_mod.query_change_status(
                    root,
                    "demo",
                    runner=self._runner(
                        json.dumps({"changeName": "demo", "isComplete": "yes"})
                    ),
                )
        finally:
            for tmp in state:
                tmp.cleanup()


class QuerySpecsTest(unittest.TestCase):
    def test_spec_ids_parse(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            runner = stub_runner(
                lambda argv, kwargs: StubResult(
                    0, json.dumps({"specs": [{"id": "b"}, {"id": "a"}]})
                )
            )
            self.assertEqual(
                evidence_mod.query_spec_ids(root, runner=runner), {"a", "b"}
            )
        finally:
            for tmp in state:
                tmp.cleanup()

    def test_malformed_specs_block(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            for payload in (
                json.dumps({"specs": {}}),
                json.dumps({"specs": [{"noid": 1}]}),
                json.dumps({"specs": [{"id": "  "}]}),
            ):
                runner = stub_runner(lambda argv, kwargs, p=payload: StubResult(0, p))
                with (
                    self.subTest(payload=payload[:30]),
                    self.assertRaises(evidence_mod.EvidenceBlocked),
                ):
                    evidence_mod.query_spec_ids(root, runner=runner)
        finally:
            for tmp in state:
                tmp.cleanup()

    def test_validation_gate_pass_and_fail(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            evidence_mod.check_specs_valid(
                root,
                runner=stub_runner(lambda argv, kwargs: StubResult(0, "ok")),
            )
            with self.assertRaises(evidence_mod.EvidenceBlocked):
                evidence_mod.check_specs_valid(
                    root,
                    runner=stub_runner(
                        lambda argv, kwargs: StubResult(1, "Totals: 0/1")
                    ),
                )
        finally:
            for tmp in state:
                tmp.cleanup()


class ArchiveProofTest(unittest.TestCase):
    def _archive(self, root: Path, entry: str, deltas: tuple[str, ...]) -> None:
        target = root / "openspec" / "changes" / "archive" / entry
        for delta in deltas:
            (target / "specs" / delta).mkdir(parents=True)
            (target / "specs" / delta / "spec.md").write_text(
                "# Spec\n", encoding="utf-8"
            )
        if not deltas:
            target.mkdir(parents=True)

    def test_suffix_archive_with_specs_proves_archival(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            self._archive(root, "2026-09-13-demo", ("widget",))
            detail = evidence_mod.check_archive_proof(
                root, "openspec/changes", "demo", {"widget", "other"}
            )
            self.assertIn("2026-09-13-demo", detail)
            self.assertIn("widget", detail)
        finally:
            for tmp in state:
                tmp.cleanup()

    def test_exact_name_and_skipless_archive_prove_archival(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            self._archive(root, "infra", ())
            detail = evidence_mod.check_archive_proof(
                root, "openspec/changes", "infra", set()
            )
            self.assertIn("no delta specs", detail)
        finally:
            for tmp in state:
                tmp.cleanup()

    def test_missing_archive_or_spec_blocks(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            with self.assertRaises(evidence_mod.EvidenceBlocked) as ctx:
                evidence_mod.check_archive_proof(
                    root, "openspec/changes", "ghost", set()
                )
            self.assertIn("renamed or deleted", str(ctx.exception))
            self._archive(root, "2026-09-13-demo", ("widget",))
            with self.assertRaises(evidence_mod.EvidenceBlocked) as ctx2:
                evidence_mod.check_archive_proof(
                    root, "openspec/changes", "demo", {"other"}
                )
            self.assertIn("widget", str(ctx2.exception))
        finally:
            for tmp in state:
                tmp.cleanup()

    def test_non_directories_are_ignored(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            archive = root / "openspec" / "changes" / "archive"
            archive.mkdir(parents=True)
            (archive / "2026-09-13-demo").write_text("stray", encoding="utf-8")
            self.assertIsNone(
                evidence_mod.find_archive_entry(root / "openspec" / "changes", "demo")
            )
        finally:
            for tmp in state:
                tmp.cleanup()


class ConversationRecordTest(unittest.TestCase):
    def test_round_trip_and_fresh_ids(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            make_change(root, "demo", "# Tasks\n\n- [ ] Open\n")
            first = evidence_mod.record_conversation(
                root, "first", "demo", "openspec/changes", ["demo"]
            )
            second = evidence_mod.record_conversation(
                root, "continuation", "demo", "openspec/changes", ["demo"]
            )
            self.assertNotEqual(first.conversation_id, second.conversation_id)
            loaded = evidence_mod.read_conversation(root)
            assert loaded is not None
            self.assertEqual(loaded.conversation_id, second.conversation_id)
            self.assertEqual(loaded.role, "continuation")
            self.assertEqual(loaded.spec_path, "openspec/changes/demo")
            self.assertEqual(loaded.queue, ["demo"])
            handoff = handoff_mod.read_handoff(root / "HANDOFF.md")
            self.assertEqual(handoff.current_spec, "demo")
            self.assertEqual(handoff.current_spec_file, "openspec/changes/demo")
        finally:
            for tmp in state:
                tmp.cleanup()

    def test_handoff_history_is_preserved(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            handoff = handoff_mod.read_handoff(root / "HANDOFF.md")
            handoff_mod.add_item(handoff, "risk", "keep me", priority="high")
            handoff.completed.append(
                handoff_mod.CompletedItem(id="c-1", summary="completed spec `old`")
            )
            handoff_mod.write_handoff(root / "HANDOFF.md", handoff)
            make_change(root, "demo", "# Tasks\n\n- [ ] Open\n", current=False)
            evidence_mod.record_conversation(
                root, "first", "demo", "openspec/changes", ["demo"]
            )
            updated = handoff_mod.read_handoff(root / "HANDOFF.md")
            self.assertEqual(updated.current_spec, "demo")
            self.assertEqual(len(updated.completed), 1)
            self.assertEqual(len(updated.unresolved), 1)
            self.assertEqual(updated.unresolved[0].description, "keep me")
        finally:
            for tmp in state:
                tmp.cleanup()

    def test_missing_record_reads_none(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            self.assertIsNone(evidence_mod.read_conversation(root))
        finally:
            for tmp in state:
                tmp.cleanup()

    def test_malformed_records_raise(self) -> None:
        state: list = []
        root = make_project(state)
        try:
            path = evidence_mod.conversation_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{bad json", encoding="utf-8")
            with self.assertRaises(evidence_mod.ConversationError):
                evidence_mod.read_conversation(root)
            for raw in (
                {"version": 999},
                {
                    "version": 1,
                    "conversation_id": "c-1",
                    "role": "nope",
                    "current_spec": "d",
                    "spec_path": "p",
                    "started_at": "t",
                    "queue": [],
                },
                {
                    "version": 1,
                    "conversation_id": "",
                    "role": "first",
                    "current_spec": "d",
                    "spec_path": "p",
                    "started_at": "t",
                    "queue": [],
                },
                {
                    "version": 1,
                    "conversation_id": "c-1",
                    "role": "first",
                    "current_spec": "d",
                    "spec_path": "p",
                    "started_at": "t",
                    "queue": "demo",
                },
                ["not", "an", "object"],
            ):
                path.write_text(json.dumps(raw), encoding="utf-8")
                with (
                    self.subTest(raw=str(raw)[:40]),
                    self.assertRaises(evidence_mod.ConversationError),
                ):
                    evidence_mod.read_conversation(root)
            with self.assertRaises(evidence_mod.ConversationError):
                evidence_mod.record_conversation(
                    root, "bogus", "demo", "openspec/changes", []
                )
            with self.assertRaises(evidence_mod.ConversationError):
                evidence_mod.record_conversation(
                    root, "first", "  ", "openspec/changes", []
                )
        finally:
            for tmp in state:
                tmp.cleanup()


class RecordedBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def test_recorded_change_gates_over_stale_handoff(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "recorded", "# Tasks\n\n- [ ] Work\n")
        handoff = handoff_mod.read_handoff(project / "HANDOFF.md")
        handoff.current_spec = "stale-other"
        handoff_mod.write_handoff(project / "HANDOFF.md", handoff)
        evidence_mod.record_conversation(
            project, "first", "recorded", "openspec/changes", ["recorded"]
        )
        with clean_git(self):
            check = robot_mod.check_boundary(
                project,
                make_config(),
                evidence_fakes.make_runner(project),
            )
        self.assertTrue(check.ok)
        self.assertEqual(check.decision, "unfinished")
        self.assertEqual(check.current_spec, "recorded")
        self.assertEqual(check.evidence_source, "openspec")

    def test_next_action_is_never_a_boundary_target(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Work\n")
        handoff = handoff_mod.read_handoff(project / "HANDOFF.md")
        handoff.current_spec = "demo"
        handoff.next_action = "finish archived `ghost` and stop"
        handoff_mod.write_handoff(project / "HANDOFF.md", handoff)
        with clean_git(self):
            check = robot_mod.check_boundary(
                project,
                make_config(),
                evidence_fakes.make_runner(project),
            )
        self.assertEqual(check.current_spec, "demo")
        self.assertNotIn("ghost", check.current_spec)

    def test_archived_record_advances_to_next_active(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "next", "# Tasks\n\n- [ ] Work\n", current=False)
        handoff = handoff_mod.read_handoff(project / "HANDOFF.md")
        handoff.current_spec = "done"
        handoff_mod.write_handoff(project / "HANDOFF.md", handoff)
        archive = project / "openspec" / "changes" / "archive" / "2026-09-13-done"
        (archive / "specs" / "widget").mkdir(parents=True)
        (archive / "specs" / "widget" / "spec.md").write_text(
            "# Spec\n", encoding="utf-8"
        )
        evidence_mod.record_conversation(
            project, "first", "done", "openspec/changes", ["done", "next"]
        )
        runner = evidence_fakes.make_runner(project, spec_ids=("widget",))
        with clean_git(self):
            check = robot_mod.check_boundary(project, make_config(), runner)
        self.assertTrue(check.ok, check.reason)
        self.assertEqual(check.decision, "complete")
        self.assertEqual(check.active, ["next"])
        self.assertIn("archived", check.task_detail)

    def test_archived_record_with_empty_queue_stops(self) -> None:
        project = make_project(self._tmp)
        (project / "openspec" / "changes" / "archive" / "2026-09-13-done").mkdir(
            parents=True
        )
        handoff = handoff_mod.read_handoff(project / "HANDOFF.md")
        handoff.current_spec = "done"
        handoff_mod.write_handoff(project / "HANDOFF.md", handoff)
        evidence_mod.record_conversation(
            project, "first", "done", "openspec/changes", ["done"]
        )
        # The active change directory is gone; only the archive remains.
        runner = evidence_fakes.make_runner(project)
        with clean_git(self):
            check = robot_mod.check_boundary(project, make_config(), runner)
        self.assertTrue(check.ok, check.reason)
        self.assertEqual(check.decision, "empty")
        self.assertIn("archived", check.task_detail)

    def test_renamed_record_blocks_without_prompt(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "next", "# Tasks\n\n- [ ] Work\n", current=False)
        evidence_mod.record_conversation(
            project, "first", "vanished", "openspec/changes", ["vanished"]
        )
        runner = evidence_fakes.make_runner(project)
        with clean_git(self):
            check = robot_mod.check_boundary(project, make_config(), runner)
        self.assertFalse(check.ok)
        self.assertEqual(check.decision, "blocked")
        self.assertIn("vanished", check.reason)

    def test_missing_tooling_blocks_without_input(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Work\n")
        runner = evidence_fakes.make_runner(project, missing_binary=True)
        with clean_git(self):
            check = robot_mod.check_boundary(project, make_config(), runner)
        self.assertFalse(check.ok)
        self.assertEqual(check.decision, "blocked")
        self.assertIn("not available", check.reason)

    def test_malformed_json_blocks_without_input(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Work\n")
        runner = evidence_fakes.make_runner(project, malformed_list=True)
        with clean_git(self):
            check = robot_mod.check_boundary(project, make_config(), runner)
        self.assertFalse(check.ok)
        self.assertEqual(check.decision, "blocked")
        self.assertIn("malformed JSON", check.reason)

    def test_contradictory_evidence_blocks(self) -> None:
        project = make_project(self._tmp)
        # tasks.md is fully checked, but OpenSpec JSON reports open work.
        make_change(project, "demo", "# Tasks\n\n- [x] Done\n")

        def handler(argv, kwargs):
            if argv[:2] == ["openspec", "list"]:
                return StubResult(
                    0,
                    list_payload([change_entry("demo", 0, 2)]),
                )
            return StubResult(0, json.dumps({"specs": []}))

        with clean_git(self):
            check = robot_mod.check_boundary(
                project, make_config(), stub_runner(handler)
            )
        self.assertFalse(check.ok)
        self.assertEqual(check.decision, "blocked")
        self.assertIn("contradictory", check.reason)

    def test_malformed_record_blocks(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Work\n")
        path = evidence_mod.conversation_path(project)
        path.write_text("{bad", encoding="utf-8")
        with clean_git(self):
            check = robot_mod.check_boundary(
                project,
                make_config(),
                evidence_fakes.make_runner(project),
            )
        self.assertFalse(check.ok)
        self.assertIn("conversation record", check.reason)

    def test_non_root_project_uses_internal_discovery(self) -> None:
        project = make_project(self._tmp, with_openspec=False)
        changes = project / "changes"
        (changes / "demo").mkdir(parents=True)
        (changes / "demo" / "tasks.md").write_text(
            "# Tasks\n\n- [ ] Work\n", encoding="utf-8"
        )
        handoff = handoff_mod.read_handoff(project / "HANDOFF.md")
        handoff.current_spec = "demo"
        handoff_mod.write_handoff(project / "HANDOFF.md", handoff)
        config = make_config(spec_dir="changes")
        with clean_git(self):
            check = robot_mod.check_boundary(project, config, runner=None)
        self.assertTrue(check.ok)
        self.assertEqual(check.decision, "unfinished")
        self.assertEqual(check.evidence_source, "internal")


class FirstTargetTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def test_empty_queue_selects_nothing(self) -> None:
        project = make_project(self._tmp)
        handoff = handoff_mod.read_handoff(project / "HANDOFF.md")
        target, queue = robot_mod.select_first_target(
            project, make_config(), handoff, evidence_fakes.make_runner(project)
        )
        self.assertEqual((target, queue), ("", []))

    def test_recorded_target_wins_over_handoff(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "aaa", "# Tasks\n\n- [ ] A\n", current=False)
        make_change(project, "zzz", "# Tasks\n\n- [ ] Z\n")
        evidence_mod.record_conversation(
            project, "first", "zzz", "openspec/changes", ["aaa", "zzz"]
        )
        handoff = handoff_mod.read_handoff(project / "HANDOFF.md")
        handoff.current_spec = "aaa"
        handoff_mod.write_handoff(project / "HANDOFF.md", handoff)
        target, queue = robot_mod.select_first_target(
            project, make_config(), handoff, evidence_fakes.make_runner(project)
        )
        self.assertEqual(target, "zzz")
        self.assertEqual(queue, ["aaa", "zzz"])

    def test_override_outside_queue_blocks(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Work\n")
        handoff = handoff_mod.read_handoff(project / "HANDOFF.md")
        with self.assertRaises(evidence_mod.EvidenceBlocked):
            robot_mod.select_first_target(
                project,
                make_config(finished_change="ghost"),
                handoff,
                evidence_fakes.make_runner(project),
            )


class WatcherRecordingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def _watcher(self, project, output=READY, **overrides):
        driver = terminal_mod.FakeTerminalDriver()
        driver.sessions["agent"] = {"command": [], "output": output, "workdir": "/t"}
        adapter = providers_mod.get_adapter("opencode", driver, "agent", project)
        params = {
            "session": "agent",
            "provider": "opencode",
            "initial_prompt": "please start",
            "continuation_prompt": "please continue",
            "confirmation_prompt": "please finish the rest",
            "debounce_polls": 1,
            "poll_interval_s": 0.01,
        }
        params.update(overrides)
        watcher = robot_mod.RobotWatcher(
            project,
            robot_mod.RobotConfig(**params),
            driver,
            adapter,
            evidence_runner=evidence_fakes.make_runner(project),
        )
        return watcher, driver

    def test_first_prompt_records_before_sending(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Work\n")
        watcher, driver = self._watcher(project)
        with clean_git(self):
            self.assertEqual(watcher.poll(), "continuing")
        self.assertEqual(driver.sent_inputs("agent"), ["please start"])
        record = evidence_mod.read_conversation(project)
        assert record is not None
        self.assertEqual((record.role, record.current_spec), ("first", "demo"))
        handoff = handoff_mod.read_handoff(project / "HANDOFF.md")
        self.assertEqual(handoff.current_spec, "demo")
        self.assertEqual(handoff.current_spec_file, "openspec/changes/demo")

    def test_recovery_event_logged_once(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Work\n")
        evidence_mod.record_conversation(
            project, "first", "demo", "openspec/changes", ["demo"]
        )
        watcher, _driver = self._watcher(project)
        self.assertEqual(watcher._log_recovery_once(), "")
        self.assertEqual(watcher._log_recovery_once(), "")
        recovered = [
            event
            for event in watcher.activity_events
            if event["category"] == "recovery"
        ]
        self.assertEqual(len(recovered), 1)
        self.assertIn("demo", recovered[0]["message"])

    def test_unreadable_record_blocks_first_prompt(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Work\n")
        evidence_mod.conversation_path(project).write_text("{bad", encoding="utf-8")
        watcher, driver = self._watcher(project)
        with clean_git(self):
            self.assertEqual(watcher.poll(), "blocked")
        self.assertIn("conversation record", watcher.block_reason)
        self.assertEqual(driver.sent_inputs("agent"), [])

    def test_record_failure_sends_no_prompt(self) -> None:
        project = make_project(self._tmp)
        make_change(project, "demo", "# Tasks\n\n- [ ] Work\n")
        watcher, driver = self._watcher(project)
        with (
            clean_git(self),
            unittest.mock.patch.object(
                evidence_mod,
                "write_record_atomically",
                side_effect=OSError("disk full"),
            ),
        ):
            self.assertEqual(watcher.poll(), "blocked")
        self.assertIn("could not be recorded", watcher.block_reason)
        self.assertEqual(driver.sent_inputs("agent"), [])

    def test_confirmation_without_target_blocks(self) -> None:
        project = make_project(self._tmp)
        watcher, _driver = self._watcher(project)
        check = robot_mod.BoundaryCheck(
            ok=True, active=["demo"], decision="complete", current_spec=""
        )
        self.assertEqual(watcher._open_confirmation(check), robot_mod.BLOCKED)
        self.assertIn("no recorded change", watcher.block_reason)

    def test_continuation_without_target_stops(self) -> None:
        project = make_project(self._tmp)
        watcher, _driver = self._watcher(project)
        check = robot_mod.BoundaryCheck(
            ok=True, active=[], decision="complete", current_spec=""
        )
        self.assertEqual(watcher._open_continuation(check), robot_mod.DONE)


if __name__ == "__main__":
    unittest.main()
