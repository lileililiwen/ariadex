"""Hermetic tests for the managed-start facade (`ariadex start`)."""

import contextlib
import io
import shutil
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ariadex import cli, config, prerequisites, state
from ariadex.terminal import FakeTerminalDriver


def run_cli(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with chdir(root), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


def ready_report(widget_state: str = "present"):
    return prerequisites.CoordinatorReport(
        results=[
            prerequisites.PrerequisiteResult("runtime", "present", "runtime ready"),
            prerequisites.PrerequisiteResult("provider", "present", "provider ready"),
            prerequisites.PrerequisiteResult("tmux", "present", "tmux ready"),
            prerequisites.PrerequisiteResult("widget", widget_state, "widget"),
        ],
        ready=True,
    )


def failed_report():
    return prerequisites.CoordinatorReport(
        results=[
            prerequisites.PrerequisiteResult("runtime", "present", "runtime ready"),
            prerequisites.PrerequisiteResult(
                "provider", "blocked", "missing", "install it"
            ),
        ],
        ready=False,
    )


class FakeAdapter:
    """Adapter double recording lifecycle calls over a fake driver."""

    def __init__(self, driver, session, calls):
        self.driver = driver
        self.session_name = session
        self.calls = calls
        self.workdir = Path(".")

    def start(self):
        self.calls.append("adapter.start")
        return self.driver.create_or_connect(
            self.session_name, self.workdir, ["provider"]
        )

    def terminate(self):
        self.calls.append("adapter.terminate")
        self.driver.terminate(self.session_name)


class FakeWatcher:
    """Supervision double with a canned report and quit tracking."""

    def __init__(self, outcome="done", calls=None):
        self.outcome = outcome
        self.calls = calls if calls is not None else []

    def run(self):
        self.calls.append("watcher.run")
        return SimpleNamespace(outcome=self.outcome, detail="fake")

    def request_quit(self):
        self.calls.append("watcher.request_quit")
        return "quit requested"


class FakeWidgetProc:
    def __init__(self, calls):
        self.calls = calls
        self._alive = True

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.calls.append("widget.terminate")
        self._alive = False

    def kill(self):
        self.calls.append("widget.kill")
        self._alive = False


class Harness:
    """Injectable facade dependencies recording phase order."""

    def __init__(self, root, *, widget_state="present", watcher_outcome="done"):
        self.root = root
        self.calls = []
        self.driver = FakeTerminalDriver()
        self.widget_state = widget_state
        self.watcher_outcome = watcher_outcome
        self.watcher = FakeWatcher(outcome=watcher_outcome, calls=self.calls)
        self.widget_proc = FakeWidgetProc(self.calls)

    def coordinate(self, provider, **kwargs):
        self.calls.append("coordinate")
        return ready_report(self.widget_state)

    def start_daemon(self, project_dir, as_json=False):
        self.calls.append("start_daemon")
        return 0

    def make_adapter(self, provider, driver, session, project_dir):
        self.calls.append("make_adapter")
        assert session == f"ariadex-{state.read(project_dir).session_id}"
        return FakeAdapter(self.driver, session, self.calls)

    def spawn_widget(self, project_dir):
        self.calls.append("spawn_widget")
        return self.widget_proc

    def attach(self, argv):
        self.calls.append("attach")
        return 0

    def make_watcher(self, project_dir, cfg, driver, adapter, session, resolved):
        self.calls.append("make_watcher")
        return self.watcher

    def run(self, **overrides):
        cfg = config.load(self.root)
        st = state.read(self.root)
        params = {
            "coordinate_fn": self.coordinate,
            "start_daemon_fn": self.start_daemon,
            "adapter_factory": self.make_adapter,
            "spawn_widget_fn": self.spawn_widget,
            "attach_fn": self.attach,
            "watcher_factory": self.make_watcher,
        }
        params.update(overrides)
        return cli.run_managed_start(
            self.root,
            cfg,
            st,
            provider=cfg.agent_provider,
            first_prompt=cfg.first_prompt,
            continuation_prompt=cfg.continuation_prompt,
            interactive=False,
            **params,
        )


def make_project(root: Path) -> None:
    code, _, _ = run_cli(root, "init")
    assert code == 0


class OverrideResolutionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_project(self.root)

    def test_config_values_resolve_by_default(self):
        cfg = config.load(self.root)
        resolved = cli._resolve_managed_config(cfg)
        self.assertEqual(
            resolved,
            (cfg.agent_provider, cfg.first_prompt, cfg.continuation_prompt),
        )

    def test_flags_override_config(self):
        cfg = config.load(self.root)
        resolved = cli._resolve_managed_config(
            cfg, agent="codex", first_prompt="first!", continuation_prompt="next!"
        )
        self.assertEqual(resolved, ("codex", "first!", "next!"))

    def test_unknown_agent_rejected(self):
        cfg = config.load(self.root)
        _, _, err = io.StringIO(), io.StringIO(), io.StringIO()
        with redirect_stderr(err):
            self.assertIsNone(cli._resolve_managed_config(cfg, agent="wat"))
        self.assertIn("supports:", err.getvalue())

    def test_blank_override_prompts_rejected(self):
        cfg = config.load(self.root)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertIsNone(cli._resolve_managed_config(cfg, first_prompt="  "))
        with redirect_stderr(io.StringIO()):
            self.assertIsNone(cli._resolve_managed_config(cfg, continuation_prompt=""))

    def test_cli_flags_reach_facade(self):
        seen = {}

        def coordinate(provider, **kwargs):
            seen["provider"] = provider
            return failed_report()

        with (
            mock.patch.object(cli.prerequisites_mod, "coordinate", coordinate),
        ):
            code, _, _ = run_cli(
                self.root,
                "start",
                "--agent",
                "codex",
                "--first-prompt",
                "f",
                "--continuation-prompt",
                "c",
            )
        self.assertNotEqual(code, 0)
        self.assertEqual(seen["provider"], "codex")


class OrderingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_project(self.root)
        self.harness = Harness(self.root)

    def test_phases_run_in_documented_order(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = self.harness.run()
        self.assertEqual(code, 0)
        self.assertEqual(
            self.harness.calls,
            [
                "coordinate",
                "start_daemon",
                "make_adapter",
                "adapter.start",
                "spawn_widget",
                "make_watcher",
                "watcher.run",
                "attach",
                "watcher.request_quit",
                # queue-empty completion teardown:
                "adapter.terminate",
                "widget.terminate",
            ],
        )

    def test_session_name_derived_from_state_never_cli(self):
        code, out, _ = run_cli(self.root, "start", "--help")
        self.assertEqual(code, 0)
        for token in ("--session", "--tmux", "--provider-path", "--watcher"):
            self.assertNotIn(token, out)

    def test_uninitialized_start_refuses_before_facade(self):
        fresh = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(fresh, True))
        code, _, err = run_cli(fresh, "start")
        self.assertNotEqual(code, 0)
        self.assertIn("ariadex init", err)


class FailureOrderingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_project(self.root)

    def test_coordinator_failure_starts_nothing(self):
        harness = Harness(self.root)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = harness.run(coordinate_fn=lambda *a, **k: failed_report())
        self.assertNotEqual(code, 0)
        self.assertEqual(harness.calls, [])
        self.assertIn("recovery:", err.getvalue())

    def test_daemon_failure_starts_no_session(self):
        harness = Harness(self.root)
        code = harness.run(start_daemon_fn=lambda *a, **k: 1)
        self.assertNotEqual(code, 0)
        self.assertEqual(harness.calls, ["coordinate"])

    def test_adapter_failure_stops_daemon(self):
        harness = Harness(self.root)
        with redirect_stderr(io.StringIO()):
            code = harness.run(
                adapter_factory=mock.Mock(
                    side_effect=RuntimeError("no launch command")
                ),
            )
        self.assertNotEqual(code, 0)
        # The adapter never started a session.
        self.assertNotIn("adapter.start", harness.calls)

    def test_session_launch_failure_reports_phase(self):
        harness = Harness(self.root)

        class BadAdapter(FakeAdapter):
            def start(self):
                raise RuntimeError("tmux gone")

        def make_adapter(provider, driver, session, project_dir):
            harness.calls.append("make_adapter")
            return BadAdapter(harness.driver, session, harness.calls)

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = harness.run(adapter_factory=make_adapter)
        self.assertNotEqual(code, 0)
        self.assertIn("provider session failed", err.getvalue())

    def test_widget_failure_tears_down_session(self):
        harness = Harness(self.root)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = harness.run(
                spawn_widget_fn=mock.Mock(side_effect=OSError("no display"))
            )
        self.assertNotEqual(code, 0)
        self.assertIn("widget startup failed", err.getvalue())
        self.assertIn("adapter.terminate", harness.calls)
        self.assertNotIn("attach", harness.calls)

    def test_widget_skipped_when_unavailable(self):
        harness = Harness(self.root, widget_state="unsupported")
        out = io.StringIO()
        with redirect_stdout(out):
            code = harness.run()
        self.assertEqual(code, 0)
        self.assertNotIn("spawn_widget", harness.calls)
        self.assertIn("terminal controls", out.getvalue())


class ReconcileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_project(self.root)

    def test_provider_exit_stops_widget_and_daemon(self):
        harness = Harness(self.root, watcher_outcome="max-polls")

        def attach(argv):
            harness.calls.append("attach")
            harness.driver.kill_session(f"ariadex-{state.read(self.root).session_id}")
            return 0

        stops = []
        out = io.StringIO()
        with redirect_stdout(out):
            code = harness.run(
                attach_fn=attach,
                start_daemon_fn=lambda *a, **k: stops.append("daemon") or 0,
            )
        self.assertEqual(code, 0)
        self.assertIn("provider session ended", out.getvalue())
        self.assertIn("adapter.terminate", harness.calls)
        self.assertIn("widget.terminate", harness.calls)

    def test_detach_leaves_workflow_running(self):
        harness = Harness(self.root, watcher_outcome="max-polls")
        out = io.StringIO()
        with redirect_stdout(out):
            code = harness.run()
        self.assertEqual(code, 0)
        self.assertIn("detached", out.getvalue())
        self.assertNotIn("adapter.terminate", harness.calls)
        self.assertNotIn("widget.terminate", harness.calls)

    def test_keyboard_interrupt_reconciles_gracefully(self):
        harness = Harness(self.root, watcher_outcome="max-polls")

        def attach(argv):
            raise KeyboardInterrupt

        out = io.StringIO()
        with redirect_stdout(out):
            code = harness.run(attach_fn=attach)
        self.assertEqual(code, 0)
        self.assertIn("watcher.request_quit", harness.calls)
        self.assertIn("interrupted:", out.getvalue())

    def test_headless_attach_failure_leaves_workflow_running(self):
        harness = Harness(self.root, watcher_outcome="max-polls")
        out = io.StringIO()
        with redirect_stdout(out):
            code = harness.run(attach_fn=lambda argv: 1, has_terminal=False)
        self.assertEqual(code, 0)
        self.assertIn("no terminal available", out.getvalue())
        self.assertNotIn("adapter.terminate", harness.calls)

    def test_terminal_attach_failure_reports_detach(self):
        harness = Harness(self.root, watcher_outcome="max-polls")
        out = io.StringIO()
        with redirect_stdout(out):
            code = harness.run(attach_fn=lambda argv: 1, has_terminal=True)
        self.assertEqual(code, 0)
        self.assertIn("detached:", out.getvalue())

    def test_duplicate_owner_creates_nothing(self):
        harness = Harness(self.root)
        sentinel = SimpleNamespace(pid=999999, endpoint="sock", status="running")
        with (
            mock.patch.object(cli.daemon_mod, "read_record", return_value=sentinel),
            mock.patch.object(cli.daemon_mod, "daemon_alive", return_value=True),
            mock.patch.object(cli, "_daemon_ipc_or_none", return_value={"ok": True}),
            mock.patch.object(cli, "_repair_live_runtime", return_value=0) as repair,
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.cmd_start(self.root)
        self.assertEqual(code, 0)
        repair.assert_called_once()
        self.assertEqual(harness.calls, [])


class FirstPromptSingularTest(unittest.TestCase):
    """Real watcher over a fake driver: first prompt sent exactly once."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_project(self.root)
        (self.root / "openspec" / "changes" / "demo").mkdir(parents=True)

    def test_first_prompt_sent_once_after_ready(self):
        from ariadex import providers as providers_mod

        cfg = config.load(self.root)
        st = state.read(self.root)
        session = f"ariadex-{st.session_id}"
        driver = FakeTerminalDriver()
        adapter = providers_mod.get_adapter("opencode", driver, session, self.root)
        adapter.start()
        driver.append_output(session, "Ask anything")
        watcher = cli._build_managed_watcher(
            self.root,
            cfg,
            driver,
            adapter,
            session,
            ("opencode", "FIRST-UNIQUE-PROMPT", cfg.continuation_prompt),
        )
        polls = {"count": 0}

        def bounded_sleep(seconds):
            polls["count"] += 1
            if polls["count"] > 30:
                raise TimeoutError("test poll budget spent")

        with contextlib.suppress(TimeoutError):
            watcher.run(sleep=bounded_sleep)
        sent = driver.sent_inputs(session)
        firsts = [text for text in sent if "FIRST-UNIQUE-PROMPT" in text]
        self.assertEqual(len(firsts), 1)


if __name__ == "__main__":
    unittest.main()
