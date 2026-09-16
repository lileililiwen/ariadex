"""Bounded retry for persisted approved surfaces (permission-approval-retry).

A persisted approved surface is retried at most twice more at spaced
polls (same input first, then the alternate selector/text input),
then parks visibly naming input, operation, path, and the manual
step. The dedup key resets outside approval class, identical waiting
diagnostics are throttled, and waiting/deny surfaces never send
input.
"""

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from ariadex import diagnostics as diagnostics_mod
from ariadex import handoff as handoff_mod
from ariadex import providers as providers_mod
from ariadex import robot as robot_mod
from ariadex import terminal as terminal_mod

try:
    import evidence_fakes
except ModuleNotFoundError:
    from tests import evidence_fakes  # type: ignore[no-redef]

APPROVAL_WRITE = "Ask anything\nApproval required: allow write to `/tmp/a.txt`? [y/n]\n"
APPROVAL_SUDO = "Ask anything\nApproval required: allow `sudo rm -rf /tmp/x`? [y/n]\n"
APPROVAL_AMBIGUOUS = (
    "Ask anything\nApproval required: allow write to `/a.txt` or `/b.txt`? [y/n]\n"
)
BUSY = "running tool `pytest` …\nesc to interrupt\n"


def directory_selector_capture(directory: str) -> str:
    return (
        "test output line 1\ntest output line 2\nBuild\nPermission required\n"
        f"Access external directory {directory}\nPatterns\n- {directory}/*\n\n"
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


def auto_config() -> str:
    return (
        "agent_provider: opencode\n"
        "permission_policy: auto\n"
        "permission_temp_root: .ariadex/tmp\n"
        "permission_actions: [read, write, create, delete]\n"
        "permission_allowlist: []\n"
    )


def make_watcher(project: Path, driver: FakeDriver, output: str):
    adapter = providers_mod.get_adapter("opencode", driver, "agent", project)
    driver.sessions["agent"] = {"command": [], "output": output, "workdir": "/t"}
    return robot_mod.RobotWatcher(
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


def all_records(project: Path) -> list:
    records, _ = diagnostics_mod.read_diagnostics(project, limit=200)
    return records


class RetryThenParkTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def test_persisting_surface_sends_thrice_then_parks(self) -> None:
        project = make_project(self._tmp, auto_config())
        driver = FakeDriver()
        watcher = make_watcher(project, driver, APPROVAL_WRITE)
        for _ in range(14):
            self.assertEqual(watcher.poll(), robot_mod.WAITING)
        self.assertEqual(driver.sent_inputs("agent"), ["y", "y", "y"])
        self.assertEqual(watcher.permissions_granted, 3)
        self.assertIn("3 times without progress", watcher.block_reason)
        self.assertIn("write", watcher.block_reason)
        self.assertIn("/tmp/a.txt", watcher.block_reason)

    def test_waiting_and_deny_surfaces_never_send_approval_input(self) -> None:
        for capture in (APPROVAL_SUDO, APPROVAL_AMBIGUOUS):
            project = make_project(self._tmp, auto_config())
            driver = FakeDriver()
            watcher = make_watcher(project, driver, capture)
            for _ in range(6):
                self.assertEqual(watcher.poll(), robot_mod.WAITING)
            self.assertNotIn("y", driver.sent_inputs("agent"))
            self.assertEqual(watcher.permissions_granted, 0)

    def test_key_resets_when_surface_clears(self) -> None:
        project = make_project(self._tmp, auto_config())
        driver = FakeDriver()
        watcher = make_watcher(project, driver, APPROVAL_WRITE)
        script = [APPROVAL_WRITE, BUSY, APPROVAL_WRITE, APPROVAL_WRITE]
        with unittest.mock.patch.object(watcher, "_capture", side_effect=script):
            for _ in range(4):
                watcher.poll()
        self.assertEqual(driver.sent_inputs("agent"), ["y", "y"])
        self.assertEqual(watcher.permissions_granted, 2)

    def test_identical_waiting_diagnostics_are_throttled(self) -> None:
        project = make_project(self._tmp, auto_config())
        driver = FakeDriver()
        watcher = make_watcher(project, driver, APPROVAL_WRITE)
        for _ in range(14):
            watcher.poll()
        waiting = [
            record
            for record in all_records(project)
            if record.get("decision") == "waiting"
            and record.get("classification") == "approval"
        ]
        self.assertLessEqual(len(waiting), 6)


class SelectorRetryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list = []
        self.addCleanup(lambda: [tmp.cleanup() for tmp in self._tmp])

    def test_selector_retry_alternates_to_text_then_parks(self) -> None:
        project = make_project(self._tmp, auto_config())
        driver = FakeDriver()
        with tempfile.TemporaryDirectory() as tmp:
            target = tmp + "/work"
            watcher = make_watcher(project, driver, directory_selector_capture(target))
            for _ in range(14):
                self.assertEqual(watcher.poll(), robot_mod.WAITING)
            self.assertEqual(driver.sent_key_sequences("agent"), [["Enter"], ["Enter"]])
            self.assertEqual(driver.sent_inputs("agent"), ["y"])
            self.assertEqual(watcher.permissions_granted, 3)
            self.assertIn("3 times without progress", watcher.block_reason)

    def test_full_pane_selector_sends_keys(self) -> None:
        project = make_project(self._tmp, auto_config())
        driver = FakeDriver()
        adapter = providers_mod.get_adapter("opencode", driver, "agent", project)
        with tempfile.TemporaryDirectory() as tmp:
            target = tmp + "/work"
            capture = directory_selector_capture(target)
            self.assertTrue(adapter.recognize_selector(capture))
            watcher = make_watcher(project, driver, capture)
            self.assertEqual(watcher.poll(), robot_mod.WAITING)
            self.assertEqual(driver.sent_key_sequences("agent"), [["Enter"]])
            self.assertEqual(driver.sent_inputs("agent"), [])


if __name__ == "__main__":
    unittest.main()
