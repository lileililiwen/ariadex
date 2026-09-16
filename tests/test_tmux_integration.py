"""Tmux lifecycle test over a simulated tmux transport (no binary needed).

The full create/send/capture/terminate lifecycle always executes against an
in-memory tmux server stub, so this test never skips on any host. Live
tmux evidence on a real server remains the job of `ariadex evidence`.
"""

import tempfile
import types
import unittest
import unittest.mock

from ariadex import providers
from ariadex.adapters import select_reset
from ariadex.terminal import TmuxDriver, session_name_for


class FakeTmuxServer:
    """In-memory tmux server answering the driver's fixed argv."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.argv_log: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs) -> types.SimpleNamespace:
        self.argv_log.append(list(cmd))
        verb = cmd[1] if len(cmd) > 1 else ""
        if verb == "has-session":
            name = cmd[cmd.index("-t") + 1]
            return self._result(0 if name in self.sessions else 1, "", "")
        if verb == "new-session":
            name = cmd[cmd.index("-s") + 1]
            self.sessions[name] = {"inputs": []}
            return self._result(0, "", "")
        if verb == "send-keys":
            name = cmd[cmd.index("-t") + 1]
            if name not in self.sessions:
                return self._result(1, "", "no such session")
            if "-l" in cmd:
                self.sessions[name]["inputs"].append(cmd[cmd.index("-l") + 1])
            return self._result(0, "", "")
        if verb == "capture-pane":
            name = cmd[cmd.index("-t") + 1]
            if name not in self.sessions:
                return self._result(1, "", "no such session")
            return self._result(0, "\n".join(self.sessions[name]["inputs"]) + "\n", "")
        if verb == "kill-session":
            name = cmd[cmd.index("-t") + 1]
            self.sessions.pop(name, None)
            return self._result(0, "", "")
        if verb == "list-sessions":
            return self._result(0, "\n".join(sorted(self.sessions)), "")
        if verb == "list-panes":
            name = cmd[cmd.index("-t") + 1]
            if name not in self.sessions:
                return self._result(1, "", "no such session")
            # Fresh session with no foreground pid yet: the driver maps
            # empty output to None and the adapter skips runtime-record
            # identity, exactly like the product's unparseable branch.
            return self._result(0, "", "")
        return self._result(1, "", f"unexpected tmux verb {verb!r}")

    @staticmethod
    def _result(returncode: int, stdout: str, stderr: str) -> types.SimpleNamespace:
        return types.SimpleNamespace(
            returncode=returncode, stdout=stdout, stderr=stderr
        )


class TmuxLifecycleTest(unittest.TestCase):
    def test_create_send_capture_terminate(self):
        server = FakeTmuxServer()
        driver = TmuxDriver()
        name = session_name_for("integration-probe")
        with (
            unittest.mock.patch(
                "ariadex.terminal.shutil.which", return_value="/fake/tmux"
            ),
            unittest.mock.patch("ariadex.terminal.subprocess.run", side_effect=server),
        ):
            try:
                driver.terminate(name)
                adapter = providers.OpenCodeAdapter(driver, name, tempfile.gettempdir())
                self.assertEqual(adapter.start(), "created")
                self.assertTrue(driver.session_alive(name))
                adapter.send("echo live-probe")
                captured = adapter.capture_output()
                self.assertIsInstance(captured, str)
                self.assertIn("echo live-probe", captured)
                self.assertEqual(select_reset("auto", adapter.capabilities), "soft")
                self.assertEqual(
                    driver.attach_command(name)[:2], ["tmux", "attach-session"]
                )
            finally:
                driver.terminate(name)
                self.assertFalse(driver.session_alive(name))
        verbs = [argv[1] for argv in server.argv_log]
        self.assertIn("new-session", verbs)
        self.assertIn("send-keys", verbs)
        self.assertIn("capture-pane", verbs)
        self.assertIn("kill-session", verbs)
        self.assertLess(verbs.index("new-session"), verbs.index("kill-session"))


if __name__ == "__main__":
    unittest.main()
